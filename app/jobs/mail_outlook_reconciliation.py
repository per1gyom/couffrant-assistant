"""
Reconciliation nocturne mail Outlook — filet ultime contre les fuites.

Phase Connexions Universelles - Semaine 3 (Etape 3.7, 1er mai 2026).
Voir docs/vision_connexions_universelles_01mai.md.

PRINCIPE :
─────────────────────────────────────────────────────────────────
Tous les jours a 4h30 du matin (decale d Odoo a 4h pour ne pas saturer),
pour chaque connexion Outlook active :
  1. count_microsoft = appel API Graph "combien de mails au total" 
     dans Inbox + SentItems + JunkEmail
  2. count_raya = SELECT COUNT(*) FROM mail_memory WHERE username=X 
                  AND mailbox_source='outlook'
  3. Si delta > 1% : alerte WARNING via alert_dispatcher

POURQUOI :
─────────────────────────────────────────────────────────────────
Le polling delta (Etape 3.3) + webhook (existant) + lifecycle (Etape 3.5)
forment 3 niveaux de defense. Mais on veut une garantie ABSOLUE.

Cette reconciliation est le NIVEAU 4 (filet ultime) :
  - Si polling delta a un bug : detecte en max 24h
  - Si Microsoft change ses APIs : detecte en max 24h
  - Si mail_memory est corrompu : detecte en max 24h
  - Si une logique de filtrage est trop agressive : detecte en max 24h

C est ce qui aurait permis de detecter le bug 17 jours en 24h, meme si
toutes les autres defenses avaient echoue.

NOTE : la reconciliation ne FAIT PAS de re-sync forcee (contrairement a
Odoo). Pour Outlook, on n a pas de notion de "tout l historique" via
Graph (la limite varie selon la boite). On se contente de detecter et
alerter ; le re-sync sera fait via /admin/sync ou en re-onboarding.
"""

import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger("raya.outlook_reconciliation")

# Seuil au-dessus duquel on declenche l alerte (1%)
DELTA_ALERT_THRESHOLD_PCT = 1.0

# Seuil minimal absolu : pas d alerte si on a moins de 50 mails de delta
# (evite de spammer pour des differences negligeables sur les petites boites)
DELTA_ALERT_MIN_ABS = 50

# Folders a compter (memes que le polling delta)
FOLDERS_TO_COUNT = ["Inbox", "SentItems", "JunkEmail"]


def run_outlook_reconciliation():
    """Job nocturne (4h30 du matin) : compare count Microsoft vs count Raya
    pour chaque connexion Outlook active. Alerte WARNING si delta > seuil.

    Tourne en mode best effort : ne plante jamais le scheduler.
    """
    started_at = datetime.now()
    total_alerts = 0
    total_connections_checked = 0

    try:
        # Reutilise la fonction _get_outlook_connections du module sync
        from app.jobs.mail_outlook_delta_sync import _get_outlook_connections
        connections = _get_outlook_connections()
    except Exception as e:
        logger.error("[OutlookRecon] Import connections echec : %s", str(e)[:200])
        return

    if not connections:
        logger.debug("[OutlookRecon] Aucune connexion Outlook active, skip")
        return

    for conn_info in connections:
        total_connections_checked += 1
        try:
            result = _reconcile_connection(
                connection_id=conn_info["connection_id"],
                tenant_id=conn_info["tenant_id"],
                username=conn_info["username"],
            )
            if result.get("alert_raised"):
                total_alerts += 1
        except Exception as e:
            logger.error(
                "[OutlookRecon] %s/%s crash : %s",
                conn_info.get("tenant_id"), conn_info.get("username"),
                str(e)[:200],
            )

    duration = (datetime.now() - started_at).total_seconds()
    logger.info(
        "[OutlookRecon] Reconciliation terminee : %d connexions verifiees, "
        "%d alerte(s) en %.1fs",
        total_connections_checked, total_alerts, duration,
    )


def _reconcile_connection(connection_id: int, tenant_id: str,
                            username: str) -> dict:
    """Compare count Microsoft vs count Raya pour une connexion Outlook.

    Returns:
        Dict avec keys :
          - count_microsoft, count_raya, delta_abs, delta_pct
          - alert_raised : bool
          - status : 'ok' / 'microsoft_error' / 'raya_error'

    Fix 05/05/2026 : utilise le token V2 par-connexion via
    get_all_user_connections au lieu du legacy V1 qui retournait un
    seul token global par user. Sans ce fix, avec 2 boites Outlook,
    la recon comptait la meme boite 2 fois et faussait le delta de
    chacune. Aligne sur le fix bootstrap (8eb31ab) du matin.
    """
    from app.connection_token_manager import get_all_user_connections
    from app.database import get_pg_conn

    # 1. Recupere le token specifique a CETTE connexion (V2)
    token = None
    try:
        for c in get_all_user_connections(username):
            if c.get("connection_id") == connection_id:
                token = c.get("token")
                break
    except Exception:
        pass

    if not token:
        logger.debug(
            "[OutlookRecon] %s/%s/conn#%d : pas de token V2, skip",
            tenant_id, username, connection_id,
        )
        return {"status": "no_token", "alert_raised": False}

    # 2. Compte cote Microsoft (somme des 3 folders)
    count_microsoft = 0
    folders_failed = []
    for folder_name in FOLDERS_TO_COUNT:
        try:
            count = _count_folder_microsoft(token, folder_name)
            if count is not None:
                count_microsoft += count
            else:
                folders_failed.append(folder_name)
        except Exception as e:
            folders_failed.append(folder_name)
            logger.debug(
                "[OutlookRecon] count_folder echec %s/%s : %s",
                username, folder_name, str(e)[:150],
            )

    if folders_failed:
        # Si plus de la moitie des folders echouent, on skip cette connexion
        if len(folders_failed) > len(FOLDERS_TO_COUNT) / 2:
            return {
                "status": "microsoft_error",
                "alert_raised": False,
                "error_detail": f"{len(folders_failed)}/{len(FOLDERS_TO_COUNT)} folders en echec",
            }

    # 3. Compte cote Raya
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            SELECT COUNT(*) FROM mail_memory
            WHERE username = %s
              AND (mailbox_source = 'outlook' OR mailbox_source IS NULL)
        """, (username,))
        count_raya = c.fetchone()[0] or 0
    except Exception as e:
        logger.error(
            "[OutlookRecon] count_raya echec %s : %s",
            username, str(e)[:200],
        )
        return {"status": "raya_error", "alert_raised": False}
    finally:
        if conn: conn.close()

    # 4. Calcul du delta
    delta_abs = count_microsoft - count_raya
    delta_pct = 0.0
    if count_microsoft > 0:
        delta_pct = (delta_abs / count_microsoft) * 100

    # On n alerte que si Raya a MOINS que Microsoft (mails manquants).
    # NOTE : delta peut etre positif normal si user vide regulierement
    # ses mails (Microsoft purge mais Raya garde l historique).
    # On compare donc count_microsoft > count_raya seulement.
    alert_raised = (
        delta_abs > 0
        and abs(delta_abs) >= DELTA_ALERT_MIN_ABS
        and abs(delta_pct) > DELTA_ALERT_THRESHOLD_PCT
    )

    if alert_raised:
        logger.warning(
            "[OutlookRecon] %s/%s : DELTA %d mails (%.1f%%) - "
            "Microsoft=%d Raya=%d",
            tenant_id, username, delta_abs, delta_pct,
            count_microsoft, count_raya,
        )
        _raise_reconciliation_alert(
            tenant_id=tenant_id, username=username,
            count_microsoft=count_microsoft, count_raya=count_raya,
            delta_abs=delta_abs, delta_pct=delta_pct,
        )
    else:
        logger.debug(
            "[OutlookRecon] %s/%s : OK - Microsoft=%d Raya=%d (delta=%d/%.2f%%)",
            tenant_id, username, count_microsoft, count_raya,
            delta_abs, delta_pct,
        )

    return {
        "status": "ok",
        "count_microsoft": count_microsoft,
        "count_raya": count_raya,
        "delta_abs": delta_abs,
        "delta_pct": round(delta_pct, 2),
        "alert_raised": alert_raised,
    }


def _count_folder_microsoft(token: str, folder_name: str) -> Optional[int]:
    """Compte le nombre de mails dans un folder via Microsoft Graph.

    Returns:
        Le count ou None si erreur.
    """
    import requests
    GRAPH_BASE = "https://graph.microsoft.com/v1.0"
    url = f"{GRAPH_BASE}/me/mailFolders/{folder_name}/messages/$count"
    try:
        r = requests.get(
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "ConsistencyLevel": "eventual",  # requis pour $count
            },
            timeout=20,
        )
        if r.status_code == 200:
            return int(r.text)
        return None
    except Exception:
        return None


def _raise_reconciliation_alert(tenant_id: str, username: str,
                                  count_microsoft: int, count_raya: int,
                                  delta_abs: int, delta_pct: float) -> None:
    """Leve une alerte WARNING via le dispatcher universel."""
    try:
        from app.alert_dispatcher import send

        title = f"Reconciliation Outlook : {delta_abs} mails manquants ({username})"
        message = (
            f"La reconciliation nocturne du {datetime.now().strftime('%Y-%m-%d')} "
            f"a detecte {delta_abs} mails manquants dans Raya pour {username} "
            f"(tenant {tenant_id}).\n\n"
            f"Comptage Microsoft : {count_microsoft}\n"
            f"Comptage Raya : {count_raya}\n"
            f"Ecart : {delta_abs} ({delta_pct:.1f}%)\n\n"
            f"Cause possible : crash Raya, bug logique, retention Microsoft, "
            f"webhook bug. Inspecte /admin/health/page pour voir si le polling "
            f"delta est OK et /admin/health/connection/<id> pour les events."
        )

        send(
            severity="warning",
            title=title,
            message=message,
            tenant_id=tenant_id,
            username=username,
            actions=[
                {
                    "label": "Voir /admin/health",
                    "url": "/admin/health/page",
                },
            ],
            source_type="outlook_reconciliation",
            source_id=f"{tenant_id}/{username}",
            component=f"outlook_recon_{username}",
            alert_type="outlook_reconciliation_drift",
        )
    except Exception as e:
        logger.error("[OutlookRecon] Alert dispatch echec : %s", str(e)[:200])
