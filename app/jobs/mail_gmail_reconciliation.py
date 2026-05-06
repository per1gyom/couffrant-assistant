"""
Reconciliation nocturne mail Gmail — filet ultime contre les fuites.

Phase Connexions Universelles - Semaine 4 (Etape 4.7, 1er mai 2026 soir).
Voir docs/vision_connexions_universelles_01mai.md.

PRINCIPE :
─────────────────────────────────────────────────────────────────
Tous les jours a 5h00 du matin (decale d Outlook a 4h30 et d Odoo
a 4h pour ne pas saturer les APIs en parallele), pour chaque
USERNAME ayant des connexions Gmail :
  1. count_google = somme des messagesTotal de toutes ses boites
                    sur les labels INBOX + SENT + SPAM
  2. count_raya = SELECT COUNT(*) FROM mail_memory WHERE username=X
                  AND mailbox_source IN ('gmail', 'gmail_perso')
  3. Si delta > 1% ET delta absolu > 50 : alerte WARNING via dispatcher

POURQUOI BY USERNAME (pas par connection_id) :
─────────────────────────────────────────────────────────────────
Guillaume a 5 Gmail differents (per1.guillaume, sasgplh, sci.romagui,
sci.gaucherie, sci.mtbr). Tous mappes sur le meme username='guillaume'.
mail_memory n a PAS de colonne connection_id ni email_address pour
distinguer la boite source. Donc on ne peut pas reconcillier par
boite, on doit le faire au niveau username (somme de toutes les boites).

C est une LIMITATION acceptable : si Raya perd des mails pour 1 boite
sur 5, on detecte quand meme un delta global proportionnel.

POURQUOI :
─────────────────────────────────────────────────────────────────
Le polling delta (Etape 4.3) + Pub/Sub watch a venir (Etape 4.5) +
multiples retries forment plusieurs niveaux de defense. Mais on
veut une garantie ABSOLUE.

Cette reconciliation est le NIVEAU 4 (filet ultime) :
  - Si polling delta a un bug : detecte en max 24h
  - Si Google change ses APIs : detecte en max 24h
  - Si mail_memory est corrompu : detecte en max 24h
  - Si une logique de filtrage est trop agressive : detecte en max 24h

C est ce qui aurait permis de detecter un equivalent du bug 17 jours
en 24h, meme si toutes les autres defenses avaient echoue.

NOTE : la reconciliation ne FAIT PAS de re-sync forcee. Pour Gmail,
le re-sync sera fait via /admin/sync (a venir) ou en re-onboarding.
"""

import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger("raya.gmail_reconciliation")

# Seuil au-dessus duquel on declenche l alerte (1%)
DELTA_ALERT_THRESHOLD_PCT = 1.0

# Seuil minimal absolu : pas d alerte si on a moins de 50 mails de delta
# (evite de spammer pour des differences negligeables sur les petites boites)
DELTA_ALERT_MIN_ABS = 50

# Fix 05/05/2026 : seuils 3 niveaux. La reconciliation Gmail compare
# Google (INBOX+SENT+SPAM brut) vs Raya (post-filtrage Haiku). Donc un
# ecart eleve est ATTENDU et legitime (filtrage SPAM + newsletter +
# anti-bulk volontaire). On ne crie au loup que si l ecart est vraiment
# anormal apres prise en compte du filtrage typique (~20-30%).
INFO_THRESHOLD_PCT = 30.0      # < 30% = info (filtrage Haiku normal)
WARNING_THRESHOLD_PCT = 50.0   # 30-50% = warning a surveiller
# > 50% = critical (probablement bug ingestion)
# Note : sera affine au commit #3 avec comptage pommes vs pommes
# (exclusion SPAM cote Google + ajout filtres_haiku cote Raya).

# Labels a compter cote Google (memes que PERIMETRE_LABELS du polling)
# Fix 05/05/2026 : passe en "pommes vs pommes". Avant on comptait
# INBOX+SENT+SPAM cote Google mais SPAM n est jamais bootstrape (le
# pipeline filtre volontairement le spam Gmail). On compare donc
# desormais juste INBOX+SENT cote Google, ce qui correspond a ce
# que Raya pourrait theoriquement avoir en base.
LABELS_TO_COUNT = ["INBOX", "SENT"]

_GMAIL_API = "https://gmail.googleapis.com/gmail/v1/users/me"


def run_gmail_reconciliation():
    """Job nocturne (5h00 du matin) : compare count Google vs count Raya
    pour chaque USERNAME ayant au moins une connexion Gmail. Alerte
    WARNING si delta > seuil.

    Tourne en mode best effort : ne plante jamais le scheduler.
    """
    started_at = datetime.now()
    total_alerts = 0
    total_users_checked = 0

    try:
        # Reutilise la fonction _get_gmail_connections du module sync
        from app.jobs.mail_gmail_history_sync import _get_gmail_connections
        connections = _get_gmail_connections()
    except Exception as e:
        logger.error(
            "[GmailRecon] Import connections echec : %s", str(e)[:200])
        return

    if not connections:
        logger.debug("[GmailRecon] Aucune connexion Gmail active, skip")
        return

    # Groupe les connexions par (tenant_id, username)
    # car un user peut avoir N boites Gmail
    by_user = {}
    for conn_info in connections:
        key = (conn_info["tenant_id"], conn_info["username"])
        by_user.setdefault(key, []).append(conn_info)

    for (tenant_id, username), user_connections in by_user.items():
        total_users_checked += 1
        try:
            result = _reconcile_user(
                tenant_id=tenant_id,
                username=username,
                connections=user_connections,
            )
            if result.get("alert_raised"):
                total_alerts += 1
        except Exception as e:
            logger.error(
                "[GmailRecon] %s/%s crash : %s",
                tenant_id, username, str(e)[:200],
            )

    duration = (datetime.now() - started_at).total_seconds()
    logger.info(
        "[GmailRecon] Reconciliation terminee : %d users verifies, "
        "%d alerte(s) en %.1fs",
        total_users_checked, total_alerts, duration,
    )


def _reconcile_user(tenant_id: str, username: str,
                      connections: list) -> dict:
    """Compare la somme des counts Google de toutes les boites Gmail
    d un user vs son count Raya total.

    Args:
        tenant_id: tenant
        username: user
        connections: liste des dicts conn_info (1 par boite Gmail du user)

    Returns:
        Dict avec keys :
          - count_google, count_raya, delta_abs, delta_pct
          - boites_total : nb de boites du user
          - boites_failed : nb de boites pour lesquelles on a pas pu compter
          - alert_raised : bool
          - status : 'ok' / 'all_failed' / 'raya_error'
    """
    from app.connection_token_manager import get_connection_token
    from app.database import get_pg_conn

    # 1. Pour chaque boite du user, compte Google
    count_google = 0
    boites_failed = 0
    boites_total = len(connections)

    for conn_info in connections:
        connection_id = conn_info["connection_id"]
        email = conn_info.get("email", "?")

        # Recupere un token frais (avec refresh auto)
        try:
            token = get_connection_token(
                username=username,
                tool_type="gmail",
                tenant_id=tenant_id,
                email_hint=email if email != "?" else None,
            )
        except Exception:
            token = None

        if not token:
            logger.debug(
                "[GmailRecon] %s/%s/conn#%d : pas de token, skip",
                tenant_id, username, connection_id,
            )
            boites_failed += 1
            continue

        # Compte les labels INBOX + SENT + SPAM pour cette boite
        boite_count = 0
        labels_failed = 0
        for label_id in LABELS_TO_COUNT:
            try:
                label_count = _count_label_google(token, label_id)
                if label_count is not None:
                    boite_count += label_count
                else:
                    labels_failed += 1
            except Exception as e:
                labels_failed += 1
                logger.debug(
                    "[GmailRecon] count_label %s/%s/%s echec : %s",
                    username, email, label_id, str(e)[:150],
                )

        if labels_failed >= len(LABELS_TO_COUNT):
            # Tous les labels en echec pour cette boite -> on la considere KO
            logger.warning(
                "[GmailRecon] %s/%s/%s : tous les labels en echec, "
                "boite ignoree dans le total",
                tenant_id, username, email,
            )
            boites_failed += 1
        else:
            count_google += boite_count
            logger.debug(
                "[GmailRecon] %s/%s/%s : %d mails (%d/%d labels OK)",
                tenant_id, username, email, boite_count,
                len(LABELS_TO_COUNT) - labels_failed, len(LABELS_TO_COUNT),
            )

    # Si toutes les boites sont en echec, on skip
    if boites_failed >= boites_total:
        return {
            "status": "all_failed",
            "alert_raised": False,
            "boites_total": boites_total,
            "boites_failed": boites_failed,
        }

    # 2. Compte cote Raya
    # Fix 05/05/2026 : pommes vs pommes. On ajoute les mails filtres
    # volontairement par Haiku au compteur Raya, pour ne pas comptabiliser
    # comme "manquants" les mails que Raya a vu mais a sciemment ignore
    # (newsletters, notifications, spam non-business).
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            SELECT COUNT(*) FROM mail_memory
            WHERE username = %s
              AND mailbox_source IN ('gmail', 'gmail_perso')
        """, (username,))
        count_raya_base = c.fetchone()[0] or 0

        # Somme des items_filtered_haiku du DERNIER bootstrap par mailbox
        # (et non pas le cumul, sinon on double-compte les mails que les
        # bootstraps successifs ont vu encore et encore).
        c.execute("""
            SELECT COALESCE(SUM(latest_filtered), 0) FROM (
              SELECT DISTINCT ON (mailbox_email)
                     mailbox_email, items_filtered_haiku AS latest_filtered
              FROM mail_bootstrap_runs
              WHERE username = %s
                AND status = 'done'
                AND mailbox_email IS NOT NULL
                AND mailbox_email IN (
                  SELECT DISTINCT mailbox_email FROM mail_memory
                  WHERE mailbox_source IN ('gmail', 'gmail_perso')
                    AND username = %s
                )
              ORDER BY mailbox_email, started_at DESC
            ) sub
        """, (username, username))
        count_filtered = c.fetchone()[0] or 0

        count_raya = count_raya_base + count_filtered
    except Exception as e:
        logger.error(
            "[GmailRecon] count_raya echec %s : %s",
            username, str(e)[:200],
        )
        return {
            "status": "raya_error",
            "alert_raised": False,
            "boites_total": boites_total,
        }
    finally:
        if conn: conn.close()

    # 3. Calcul du delta
    delta_abs = count_google - count_raya
    delta_pct = 0.0
    if count_google > 0:
        delta_pct = (delta_abs / count_google) * 100

    # On alerte uniquement si Raya a MOINS que Google (mails manquants).
    # Si Raya a PLUS, c est normal (historique conserve).
    alert_raised = (
        delta_abs > 0
        and abs(delta_abs) >= DELTA_ALERT_MIN_ABS
        and abs(delta_pct) > DELTA_ALERT_THRESHOLD_PCT
    )

    if alert_raised:
        logger.warning(
            "[GmailRecon] %s/%s : DELTA %d mails (%.1f%%) sur %d boites - "
            "Google=%d Raya=%d",
            tenant_id, username, delta_abs, delta_pct,
            boites_total, count_google, count_raya,
        )
        _raise_reconciliation_alert(
            tenant_id=tenant_id, username=username,
            count_google=count_google, count_raya=count_raya,
            delta_abs=delta_abs, delta_pct=delta_pct,
            boites_total=boites_total, boites_failed=boites_failed,
        )
    else:
        logger.info(
            "[GmailRecon] %s/%s : OK - Google=%d Raya=%d "
            "(delta=%d/%.2f%%) sur %d boites",
            tenant_id, username, count_google, count_raya,
            delta_abs, delta_pct, boites_total,
        )

    return {
        "status": "ok",
        "count_google": count_google,
        "count_raya": count_raya,
        "delta_abs": delta_abs,
        "delta_pct": round(delta_pct, 2),
        "boites_total": boites_total,
        "boites_failed": boites_failed,
        "alert_raised": alert_raised,
    }


def _count_label_google(token: str, label_id: str) -> Optional[int]:
    """Recupere le nombre TOTAL de messages dans un label Gmail.

    Utilise GET /labels/{labelId} qui retourne messagesTotal.

    Returns:
        Le count ou None si erreur.
    """
    import requests
    url = f"{_GMAIL_API}/labels/{label_id}"
    try:
        r = requests.get(
            url,
            headers={"Authorization": f"Bearer {token}"},
            timeout=20,
        )
        if r.status_code == 200:
            data = r.json()
            return int(data.get("messagesTotal", 0))
        return None
    except Exception:
        return None


def _raise_reconciliation_alert(tenant_id: str, username: str,
                                  count_google: int, count_raya: int,
                                  delta_abs: int, delta_pct: float,
                                  boites_total: int,
                                  boites_failed: int) -> None:
    """Leve une alerte avec severite calibree selon l ampleur de l ecart.
    
    Fix 05/05/2026 : 3 niveaux pour ne plus alerter en orange/rouge sur
    le filtrage Haiku legitime (newsletters/spam ignores volontairement).

    Refonte 06/05/2026 : message en francais clair sans jargon, et SI
    l ecart est dans la zone normale ET 0 boite en echec, on ne cree
    plus d alerte INFO du tout (juste log) - evite de polluer le panel
    avec des operations parfaitement normales.
    """
    try:
        from app.alert_dispatcher import send

        delta_pct_abs = abs(delta_pct)
        # Choix de severite
        if delta_pct_abs >= WARNING_THRESHOLD_PCT:
            severity = "critical"
            should_skip_alert = False
            verdict = (
                f"L'ecart de {delta_pct_abs:.0f}% depasse les seuils normaux. "
                f"Le filtrage Haiku ne suffit pas a l'expliquer. "
                f"Probable probleme d'ingestion : verifier /admin/health."
            )
        elif delta_pct_abs >= INFO_THRESHOLD_PCT:
            severity = "warning"
            should_skip_alert = False
            verdict = (
                f"Ecart modere de {delta_pct_abs:.0f}% a surveiller. "
                f"Une partie est due au filtrage Haiku (newsletter/spam "
                f"volontairement ignores). Si l'ecart persiste plusieurs "
                f"jours, investiguer."
            )
        else:
            # Cas 'ecart normal du au filtrage' : skip si rien d anormal
            severity = "info"
            should_skip_alert = (boites_failed == 0)
            verdict = (
                f"Filtrage Gmail normal : {delta_abs} newsletters/spam "
                f"ignores ({delta_pct_abs:.0f}% des mails). "
                f"Raya ne garde que les mails business utiles."
            )

        if should_skip_alert:
            logger.info(
                "[GmailRecon] %s tenant=%s user=%s : %s",
                severity.upper(), tenant_id, username, verdict,
            )
            return

        # Refonte titre + message : francais clair, sans jargon technique.
        # On utilise le verdict comme phrase principale et on met les
        # chiffres bruts en details secondaires.
        if severity == "critical":
            title = f"Reconciliation Gmail anormale : {delta_pct_abs:.0f}% d'ecart"
        elif severity == "warning":
            title = f"Reconciliation Gmail : ecart {delta_pct_abs:.0f}% a surveiller"
        else:
            title = f"Filtrage Gmail : {delta_abs} mails ignores ({delta_pct_abs:.0f}%)"

        message = (
            f"{verdict}\n\n"
            f"Details : Gmail compte {count_google} mails (sur {boites_total} "
            f"boites), Raya en a garde {count_raya}, soit {delta_abs} de "
            f"moins ({delta_pct_abs:.0f}%)."
            + (f"\n\nAttention : {boites_failed}/{boites_total} boites en echec."
               if boites_failed > 0 else "")
        )

        send(
            severity=severity,
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
            source_type="gmail_reconciliation",
            source_id=f"{tenant_id}/{username}",
            component=f"gmail_recon_{username}",
            alert_type="gmail_reconciliation_drift",
        )
    except Exception as e:
        logger.error(
            "[GmailRecon] Alert dispatch echec : %s", str(e)[:200])
