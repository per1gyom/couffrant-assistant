"""Reconciliation nocturne Drive — filet ultime contre les pertes.

Phase Connexions Universelles - Semaine 5 (preparation 02/05/2026 nuit).
Voir docs/vision_connexions_universelles_01mai.md.

PRINCIPE :
─────────────────────────────────────────────────────────────────
Tous les jours a 5h30 du matin (decale d Outlook a 4h30 et d Odoo a 4h
pour ne pas saturer Railway), pour chaque connexion Drive active :
  1. count_drive = liste recursive du dossier SharePoint surveille,
     compte les fichiers vectorisables (ext supportee, taille OK),
     hors blacklist
  2. count_raya = SELECT COUNT(DISTINCT file_id) FROM drive_semantic_content
                  WHERE tenant_id=X AND level=1 AND deleted_at IS NULL
  3. Si delta > 5% : alerte WARNING via alert_dispatcher

POURQUOI 5% (vs 1% pour les mails) ?
─────────────────────────────────────────────────────────────────
La reconciliation Drive a plus de sources de variabilite legitime que
les mails :
  - Fichiers en cours d upload SharePoint (transitoirement absents)
  - Drive_scanner skipe les fichiers > 50 Mo et les .doc legacy : ces
    fichiers existent cote Microsoft mais pas cote Raya, par design
  - Les Sensitivity Labels Microsoft Purview peuvent masquer des items
  - La blacklist evolue dans le temps

Tolerer 5% absorbe ces sources sans masquer un vrai bug. Si dans 6 mois
on observe que le drift moyen est < 2%, on pourra resserrer.

POURQUOI 5h30 ?
─────────────────────────────────────────────────────────────────
  4h00  : Odoo reconciliation
  4h30  : Outlook reconciliation
  5h30  : Drive reconciliation (potentiellement long, 3000+ fichiers)
  6h00  : Gmail watch renewal
  6h30  : creneau libre (futur : SharePoint webhook renewal)
"""

import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger("raya.drive_reconciliation")

# Seuil au-dessus duquel on declenche l alerte (5%)
DELTA_ALERT_THRESHOLD_PCT = 5.0

# Seuil minimal absolu : pas d alerte si moins de 50 fichiers de delta
DELTA_ALERT_MIN_ABS = 50

# Extensions vectorisables (memes que drive_scanner)
VECTORIZABLE_EXTENSIONS = {
    "pdf", "docx", "xlsx", "xls", "txt", "md", "csv", "json",
    "xml", "log", "jpg", "jpeg", "png",
}
# .doc explicitement exclu (legacy, drive_scanner ne le gere pas)

# Limite de taille (meme que drive_scanner)
MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024


def run_drive_reconciliation():
    """Job nocturne (5h30 du matin) : compare count Microsoft vs count Raya
    pour chaque connexion Drive active. Alerte WARNING si delta > seuil.

    Tourne en mode best effort : ne plante jamais le scheduler.
    """
    started_at = datetime.now()
    total_alerts = 0
    total_connections_checked = 0

    try:
        from app.jobs.drive_delta_sync import _get_drive_connections
        connections = _get_drive_connections()
    except Exception as e:
        logger.error(
            "[DriveRecon] Import connections echec : %s", str(e)[:200],
        )
        return

    if not connections:
        logger.debug("[DriveRecon] Aucune connexion Drive active, skip")
        return

    for conn_info in connections:
        # Pour cette premiere version : sharepoint uniquement
        # En base le tool_type SharePoint est stocke comme 'drive'
        if conn_info.get("tool_type") not in ("drive", "sharepoint"):
            continue

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
                "[DriveRecon] %s/%s crash : %s",
                conn_info.get("tenant_id"), conn_info.get("username"),
                str(e)[:200],
            )

    duration = (datetime.now() - started_at).total_seconds()
    logger.info(
        "[DriveRecon] Reconciliation terminee : %d connexions verifiees, "
        "%d alerte(s) en %.1fs",
        total_connections_checked, total_alerts, duration,
    )


def _reconcile_connection(connection_id: int, tenant_id: str,
                            username: str) -> dict:
    """Compare count Drive (recursif) vs count Raya pour une connexion.

    Returns:
        Dict avec keys :
          - count_drive, count_raya, delta_abs, delta_pct
          - alert_raised : bool
          - status : 'ok' / 'no_token' / 'no_drive_config' / 'drive_error'
    """
    from app.token_manager import get_valid_microsoft_token
    from app.database import get_pg_conn

    # 1. Token
    try:
        token = get_valid_microsoft_token(username)
    except Exception:
        token = None

    if not token:
        return {"status": "no_token", "alert_raised": False}

    # 2. Resolution drive_id + folder_id surveille
    try:
        from app.connectors.drive_connector import (
            get_drive_config, _find_sharepoint_site_and_drive,
            _find_folder_root,
        )
        config = get_drive_config(tenant_id)
        if not config.get("configured"):
            return {"status": "no_drive_config", "alert_raised": False}
        _, drive_id, _ = _find_sharepoint_site_and_drive(token, config)
        if not drive_id:
            return {"status": "no_drive_config", "alert_raised": False}
        _, folder_id = _find_folder_root(token, drive_id, config)
        if not folder_id:
            return {"status": "no_drive_config", "alert_raised": False}
    except Exception as e:
        logger.error(
            "[DriveRecon] %s/%s resolve drive crash : %s",
            tenant_id, username, str(e)[:200],
        )
        return {"status": "drive_error", "alert_raised": False}

    # 3. Liste recursive cote Microsoft + filtre vectorisables
    try:
        from app.jobs.drive_scanner import _list_folder_recursive
        all_files = _list_folder_recursive(token, drive_id, folder_id)
    except Exception as e:
        logger.error(
            "[DriveRecon] %s/%s list folder crash : %s",
            tenant_id, username, str(e)[:200],
        )
        return {"status": "drive_error", "alert_raised": False}

    # 4. Filtre : extensions supportees + taille
    blacklist = _get_blacklist(tenant_id, connection_id)
    count_drive = 0
    for f in all_files:
        name = f.get("name", "")
        size = f.get("size", 0) or 0
        ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
        path = f.get("path", "")

        if ext not in VECTORIZABLE_EXTENSIONS:
            continue
        if size > MAX_FILE_SIZE_BYTES:
            continue
        if _is_blacklisted(path, blacklist):
            continue
        count_drive += 1

    # 5. Count cote Raya
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            SELECT COUNT(DISTINCT file_id)
            FROM drive_semantic_content
            WHERE tenant_id = %s AND level = 1
              AND deleted_at IS NULL
        """, (tenant_id,))
        count_raya = c.fetchone()[0] or 0
    except Exception as e:
        logger.error(
            "[DriveRecon] count_raya echec %s : %s",
            tenant_id, str(e)[:200],
        )
        return {"status": "raya_error", "alert_raised": False}
    finally:
        if conn:
            conn.close()

    # 6. Calcul du delta
    delta_abs = count_drive - count_raya
    delta_pct = 0.0
    if count_drive > 0:
        delta_pct = (delta_abs / count_drive) * 100

    # On n alerte que si Raya a MOINS que Drive (fichiers manquants).
    alert_raised = (
        delta_abs > 0
        and abs(delta_abs) >= DELTA_ALERT_MIN_ABS
        and abs(delta_pct) > DELTA_ALERT_THRESHOLD_PCT
    )

    if alert_raised:
        logger.warning(
            "[DriveRecon] %s/%s : DELTA %d fichiers (%.1f%%) - "
            "Drive=%d Raya=%d",
            tenant_id, username, delta_abs, delta_pct,
            count_drive, count_raya,
        )
        _raise_reconciliation_alert(
            tenant_id=tenant_id, username=username,
            count_drive=count_drive, count_raya=count_raya,
            delta_abs=delta_abs, delta_pct=delta_pct,
        )
    else:
        logger.info(
            "[DriveRecon] %s/%s : OK - Drive=%d Raya=%d (delta=%d/%.2f%%)",
            tenant_id, username, count_drive, count_raya,
            delta_abs, delta_pct,
        )

    return {
        "status": "ok",
        "count_drive": count_drive,
        "count_raya": count_raya,
        "delta_abs": delta_abs,
        "delta_pct": round(delta_pct, 2),
        "alert_raised": alert_raised,
    }


def _get_blacklist(tenant_id: str, connection_id: int) -> list:
    """Lit la blacklist des dossiers exclus pour ce tenant/connexion."""
    from app.database import get_pg_conn
    conn = None
    paths = []
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            SELECT folder_path FROM tenant_drive_blacklist
            WHERE tenant_id = %s AND connection_id = %s
        """, (tenant_id, connection_id))
        for r in c.fetchall():
            if r[0]:
                paths.append(r[0])
    except Exception as e:
        logger.debug(
            "[DriveRecon] _get_blacklist echec : %s", str(e)[:150],
        )
    finally:
        if conn:
            conn.close()
    return paths


def _is_blacklisted(item_path: str, blacklist: list) -> bool:
    """True si item_path commence par un des prefixes blacklistes."""
    if not item_path or not blacklist:
        return False
    for prefix in blacklist:
        if item_path.startswith(prefix):
            return True
    return False


def _raise_reconciliation_alert(tenant_id: str, username: str,
                                  count_drive: int, count_raya: int,
                                  delta_abs: int, delta_pct: float) -> None:
    """Leve une alerte WARNING via le dispatcher universel."""
    try:
        from app.alert_dispatcher import send

        title = (
            f"Reconciliation Drive : {delta_abs} fichiers manquants "
            f"({tenant_id})"
        )
        message = (
            f"La reconciliation nocturne du "
            f"{datetime.now().strftime('%Y-%m-%d')} a detecte {delta_abs} "
            f"fichiers manquants dans Raya pour {tenant_id} (user "
            f"{username}).\n\n"
            f"Comptage Drive (vectorisables) : {count_drive}\n"
            f"Comptage Raya (level=1 non supprimes) : {count_raya}\n"
            f"Ecart : {delta_abs} ({delta_pct:.1f}%)\n\n"
            f"Cause possible : drive_delta_sync bug, drive_scanner "
            f"interrompu, retention SharePoint, blacklist mal configuree, "
            f"Sensitivity Labels Microsoft Purview. Inspecte le panel "
            f"Drive du tenant pour voir les erreurs du dernier scan."
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
            source_type="drive_reconciliation",
            source_id=f"{tenant_id}/{username}",
            component=f"drive_recon_{tenant_id}",
            alert_type="drive_reconciliation_drift",
        )
    except Exception as e:
        logger.error(
            "[DriveRecon] Alert dispatch echec : %s", str(e)[:200],
        )
