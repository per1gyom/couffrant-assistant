"""Drive Delta Sync — synchronisation incrementale Drive/SharePoint.

Phase Connexions Universelles - Semaine 5 (preparation 02/05/2026 nuit).
Voir docs/vision_connexions_universelles_01mai.md (lignes 1515-1545).

OBJECTIF :
─────────────────────────────────────────────────────────────
Detecter en quasi-temps-reel (5 min max) les changements de fichiers
sur les Drive/SharePoint connectes, en complement du drive_scanner
existant qui fait le scan initial complet.

Le drive_scanner.py existant fait l onboarding/refresh complet (utile
au demarrage, ou en rescan periodique). Ce module fait le delta polling
incremental : "qu est-ce qui a change depuis 5 min ?".

ARCHITECTURE (4 niveaux du doc vision section 2 - Pattern delta sync) :
  NIVEAU 1 - polling delta toutes les 5 min          ← CE MODULE
  NIVEAU 2 - webhook accelerateur (futur)
  NIVEAU 3 - Lifecycle Notifications (futur)
  NIVEAU 4 - reconciliation nocturne (drive_reconciliation.py)

DEUX MODES DE FONCTIONNEMENT (variables Railway) :
─────────────────────────────────────────────────────────────

  MODE 1 : ACTIVATION DU JOB
    Variable : SCHEDULER_DRIVE_DELTA_SYNC_ENABLED
    Defaut : FALSE (job pas execute)
    Si TRUE : le job tourne toutes les 5 min

  MODE 2 : COMPORTEMENT (shadow vs write)
    Variable : DRIVE_DELTA_SYNC_WRITE_MODE
    Defaut : FALSE (shadow mode = pas d ecriture)
    Si TRUE : appelle drive_scanner._process_file pour vectoriser
              les fichiers modifies / supprimes / renommes detectes

PROTOCOLE DE BASCULE PROPRE :
─────────────────────────────────────────────────────────────
Etape A : Activer SCHEDULER_DRIVE_DELTA_SYNC_ENABLED=true
          -> Le job tourne en SHADOW MODE
          -> Les changements sont LOGUES mais pas appliques
          -> Verifier que items_seen > 0 quand on modifie un fichier
          -> Verifier qu aucune erreur n apparait pendant 24h

Etape B : Activer DRIVE_DELTA_SYNC_WRITE_MODE=true
          -> Pour chaque fichier modifie : delegate a drive_scanner
          -> Pour chaque fichier supprime : marque deleted_at
          -> Observation 7 jours minimum

Etape C : Une fois validee, evaluer si le drive_scanner periodique
          peut etre desactive (delta + reconciliation suffisent).

PROVIDER SUPPORTE :
─────────────────────────────────────────────────────────────
Pour cette premiere version : SharePoint uniquement (Microsoft Graph).
Google Drive ajoute plus tard (delta API differente, voir
https://developers.google.com/drive/api/v3/reference/changes).

API MICROSOFT GRAPH DELTA :
─────────────────────────────────────────────────────────────
Endpoint : /drives/{drive-id}/root/delta
Doc : https://docs.microsoft.com/en-us/graph/api/driveitem-delta

Premiere requete : pas de token -> retourne TOUS les fichiers (lourd)
Astuce : utiliser ?token=latest -> retourne deltaLink immediat sans
charger l historique (idem Outlook).

Requetes suivantes : utiliser le @odata.deltaLink retourne en derniere
page. Stockee dans connection_health.metadata.drive_delta_link.
"""

import json
import logging
import os
from datetime import datetime, timezone
from typing import Optional

from app.database import get_pg_conn

logger = logging.getLogger("raya.drive_delta_sync")

# Limite de safety : max changements traites par tick par connexion
MAX_CHANGES_PER_TICK = 500

# Microsoft Graph base URL
GRAPH_BASE = "https://graph.microsoft.com/v1.0"


def _is_write_mode_enabled() -> bool:
    """Lit la variable Railway DRIVE_DELTA_SYNC_WRITE_MODE."""
    val = os.getenv("DRIVE_DELTA_SYNC_WRITE_MODE", "").strip().lower()
    return val in ("1", "true", "yes", "on")


def _get_delta_link(connection_id: int) -> Optional[str]:
    """Lit le delta_link stocke pour cette connexion Drive.
    Stocke dans connection_health.metadata['drive_delta_link'].
    """
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute(
            "SELECT metadata FROM connection_health WHERE connection_id = %s",
            (connection_id,),
        )
        row = c.fetchone()
        if not row or not row[0]:
            return None
        metadata = (
            row[0] if isinstance(row[0], dict) else json.loads(row[0])
        )
        return metadata.get("drive_delta_link")
    except Exception as e:
        logger.error(
            "[DriveDelta] _get_delta_link conn=%d echec : %s",
            connection_id, str(e)[:200],
        )
        return None
    finally:
        if conn:
            conn.close()


def _store_delta_link(connection_id: int, delta_link: str) -> None:
    """Sauvegarde le delta_link dans connection_health.metadata.
    Merge non destructif avec les autres champs metadata.
    """
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute(
            "SELECT metadata FROM connection_health WHERE connection_id = %s",
            (connection_id,),
        )
        row = c.fetchone()
        if row and row[0]:
            metadata = (
                row[0] if isinstance(row[0], dict) else json.loads(row[0])
            )
        else:
            metadata = {}
        metadata["drive_delta_link"] = delta_link
        metadata["drive_delta_link_updated_at"] = datetime.now(
            timezone.utc,
        ).isoformat()
        c.execute(
            "UPDATE connection_health SET metadata = %s "
            "WHERE connection_id = %s",
            (json.dumps(metadata), connection_id),
        )
        conn.commit()
    except Exception as e:
        logger.error(
            "[DriveDelta] _store_delta_link conn=%d echec : %s",
            connection_id, str(e)[:200],
        )
    finally:
        if conn:
            conn.close()


def _get_drive_connections() -> list:
    """Liste les connexions Drive (SharePoint/Google Drive) actives.

    Filtre :
      - tool_type IN ('drive', 'google_drive', 'sharepoint')
      - status = 'connected'
      - assignment.enabled = true
    Note : en base le tool_type SharePoint est stocke comme 'drive'
    (heritage historique, voir tenant_connections.tool_type). On accepte
    les 3 valeurs pour etre tolerant.

    Retourne une liste de dicts : {connection_id, tenant_id, username,
                                   tool_type, label}
    """
    conn = None
    rows = []
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            SELECT tc.id, ca.tenant_id, ca.username, tc.tool_type,
                   COALESCE(tc.label, tc.tool_type)
            FROM tenant_connections tc
            JOIN connection_assignments ca ON ca.connection_id = tc.id
            WHERE tc.tool_type IN ('drive', 'sharepoint', 'google_drive')
              AND tc.status = 'connected'
              AND ca.enabled = TRUE
            ORDER BY tc.id
        """)
        for r in c.fetchall():
            rows.append({
                "connection_id": r[0],
                "tenant_id": r[1],
                "username": r[2],
                "tool_type": r[3],
                "label": r[4],
            })
    except Exception as e:
        logger.error(
            "[DriveDelta] _get_drive_connections echec : %s",
            str(e)[:200],
        )
    finally:
        if conn:
            conn.close()
    return rows


def _get_blacklist(tenant_id: str, connection_id: int) -> list:
    """Lit la blacklist des dossiers exclus pour ce tenant/connexion.
    Retourne une liste de path_prefix (str) a exclure.
    """
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
            "[DriveDelta] _get_blacklist echec : %s", str(e)[:150],
        )
    finally:
        if conn:
            conn.close()
    return paths


def _is_blacklisted(item_path: str, blacklist: list) -> bool:
    """True si item_path commence par un des prefixes blacklistes.

    DEPRECATED le 02/05/2026 : remplace par _is_path_filtered() qui utilise
    le module drive_path_rules (regle 'le chemin le plus long gagne').
    Conserve uniquement comme failsafe si le nouveau module plante.
    """
    if not item_path or not blacklist:
        return False
    for prefix in blacklist:
        if item_path.startswith(prefix):
            return True
    return False


def _is_path_filtered(connection_id: int, item_path: str,
                       roots: list, rules: list) -> bool:
    """Decide si un item du delta doit etre IGNORE (filtre) au scan.

    Retourne True si le path doit etre EXCLU (donc filtre = skip).
    Retourne False si le path doit etre indexe (=> traitement normal).

    Wrapper sur is_path_indexable() qui respecte la regle "le chemin le
    plus long gagne". Failsafe : en cas d erreur, on indexe (False) pour
    ne pas perdre des items en silence.
    """
    if not item_path:
        # Pas de path -> on indexe par securite (pas de motif de filtrer)
        return False
    try:
        from app.connectors.drive_path_rules import is_path_indexable
        return not is_path_indexable(
            connection_id, item_path, roots=roots, rules=rules,
        )
    except Exception as e:
        logger.warning(
            "[DriveDelta] _is_path_filtered plante : %s (failsafe : indexer)",
            str(e)[:150],
        )
        return False


def _ensure_health_registered(connection_id: int, tenant_id: str,
                                username: str, tool_type: str) -> None:
    """Inscrit la connexion dans connection_health si pas deja fait.
    Idempotent : safe a appeler a chaque tick.
    """
    try:
        from app.connection_health import register_connection
        register_connection(
            connection_id=connection_id,
            tenant_id=tenant_id,
            username=username,
            connection_type=f"drive_{tool_type}",
            expected_poll_interval_seconds=300,    # 5 min
            alert_threshold_seconds=900,           # 15 min
        )
    except Exception as e:
        logger.debug(
            "[DriveDelta] _ensure_health_registered echec : %s",
            str(e)[:150],
        )


def _record_health_event(connection_id: int, status: str,
                           items_seen: int = 0, items_new: int = 0,
                           error_detail: Optional[str] = None) -> None:
    """Enregistre un evenement dans connection_health_events."""
    try:
        from app.connection_health import record_poll_attempt
        record_poll_attempt(
            connection_id=connection_id,
            status=status,
            items_seen=items_seen,
            items_new=items_new,
            error_detail=error_detail,
        )
    except Exception as e:
        logger.debug(
            "[DriveDelta] _record_health_event echec : %s",
            str(e)[:150],
        )


def _fetch_delta(token: str, delta_url: str) -> dict:
    """Appelle l API Microsoft Graph delta. Retourne :
    {
      "items": [...],            # changements detectes (DriveItem)
      "next_link": str | None,   # pagination
      "delta_link": str | None,  # a stocker pour le prochain tick
      "ok": bool,
      "error": str | None,
    }
    """
    import requests
    try:
        r = requests.get(
            delta_url,
            headers={"Authorization": f"Bearer {token}"},
            timeout=30,
        )
        if r.status_code == 410:
            # 410 Gone : delta token expire ou invalide
            # -> on doit refaire un init (drop le delta_link)
            return {
                "items": [], "next_link": None, "delta_link": None,
                "ok": False, "error": "delta_token_expired",
            }
        if not r.ok:
            return {
                "items": [], "next_link": None, "delta_link": None,
                "ok": False,
                "error": f"HTTP {r.status_code}: {(r.text or '')[:200]}",
            }
        data = r.json()
        return {
            "items": data.get("value", []),
            "next_link": data.get("@odata.nextLink"),
            "delta_link": data.get("@odata.deltaLink"),
            "ok": True,
            "error": None,
        }
    except Exception as e:
        return {
            "items": [], "next_link": None, "delta_link": None,
            "ok": False, "error": f"network: {str(e)[:200]}",
        }


def _build_initial_delta_url(token: str, drive_id: str) -> Optional[str]:
    """Premiere requete delta : utilise ?token=latest pour avoir un
    deltaLink immediat sans rapatrier tout l historique. Le rescan
    initial est de la responsabilite de drive_scanner.

    Retourne l URL a utiliser pour le 1er tick, ou None si erreur.
    """
    import requests
    url = f"{GRAPH_BASE}/drives/{drive_id}/root/delta?token=latest"
    try:
        r = requests.get(
            url,
            headers={"Authorization": f"Bearer {token}"},
            timeout=20,
        )
        if not r.ok:
            logger.warning(
                "[DriveDelta] init delta?token=latest HTTP %d", r.status_code,
            )
            return None
        data = r.json()
        # Doit retourner directement un @odata.deltaLink (pas de nextLink)
        return data.get("@odata.deltaLink")
    except Exception as e:
        logger.error(
            "[DriveDelta] init delta crash : %s", str(e)[:200],
        )
        return None


def _resolve_drive_for_connection(token: str, tenant_id: str) -> Optional[str]:
    """Resolution du drive_id SharePoint pour ce tenant.
    Reutilise la config drive_connector existante.

    Retourne drive_id ou None.
    """
    try:
        from app.connectors.drive_connector import (
            get_drive_config, _find_sharepoint_site_and_drive,
        )
        config = get_drive_config(tenant_id)
        if not config.get("configured"):
            return None
        _, drive_id, _ = _find_sharepoint_site_and_drive(token, config)
        return drive_id
    except Exception as e:
        logger.error(
            "[DriveDelta] _resolve_drive crash %s : %s",
            tenant_id, str(e)[:200],
        )
        return None


def _process_change_shadow(item: dict, blacklist: list,
                              connection_id: int = 0,
                              path_roots: Optional[list] = None,
                              path_rules: Optional[list] = None) -> dict:
    """Mode SHADOW : log seulement, ne modifie rien.
    Retourne un dict de stats.

    connection_id + path_roots + path_rules : nouveau systeme
    inclusion/exclusion (Phase Drive multi-racines, 02/05/2026).
    Si fournis, utilise is_path_indexable. Sinon, fallback sur la
    blacklist legacy.
    """
    item_id = item.get("id", "?")
    name = item.get("name", "?")
    is_folder = "folder" in item
    is_deleted = "deleted" in item
    parent = (item.get("parentReference") or {}).get("path", "")
    full_path = f"{parent}/{name}" if parent else name

    # Filtre prioritaire : nouveau systeme include/exclude si dispo
    if connection_id and (path_roots is not None) and (path_rules is not None):
        if _is_path_filtered(connection_id, full_path, path_roots, path_rules):
            return {"action": "skipped_rules", "name": name}
    elif _is_blacklisted(full_path, blacklist):
        # Fallback legacy
        return {"action": "skipped_blacklist", "name": name}

    if is_deleted:
        logger.info(
            "[DriveDelta][SHADOW] DELETED %s (%s)", name, item_id[:12],
        )
        return {"action": "deleted_shadow", "name": name}

    if is_folder:
        return {"action": "folder_shadow", "name": name}

    logger.info(
        "[DriveDelta][SHADOW] MODIFIED %s (%s) path=%s",
        name, item_id[:12], full_path,
    )
    return {"action": "modified_shadow", "name": name}


def _process_change_write(item: dict, blacklist: list, tenant_id: str,
                            username: str, token: str,
                            drive_id: str,
                            connection_id: int = 0,
                            path_roots: Optional[list] = None,
                            path_rules: Optional[list] = None) -> dict:
    """Mode WRITE : applique reellement le changement detecte.

    Pour un fichier modifie : delegue a drive_scanner._process_file
      qui gere download + extract + chunks + embedding + graphe.
    Pour un fichier supprime : marque deleted_at dans
      drive_semantic_content (soft delete).
    Pour un dossier : ignore (drive_scanner gere via path).

    connection_id + path_roots + path_rules : Phase Drive multi-racines.

    Retourne un dict de stats avec action effectuee.
    """
    item_id = item.get("id", "?")
    name = item.get("name", "?")
    is_folder = "folder" in item
    is_deleted = "deleted" in item
    size = item.get("size", 0)
    parent_ref = item.get("parentReference") or {}
    parent_path = parent_ref.get("path", "")
    # Microsoft Graph parentReference.path : "/drive/root:/folder/sub"
    # On veut juste la partie apres ":" pour avoir le path SharePoint
    if ":" in parent_path:
        parent_path = parent_path.split(":", 1)[1].lstrip("/")
    full_path = f"{parent_path}/{name}" if parent_path else name

    # Filtre prioritaire : nouveau systeme include/exclude si dispo
    if connection_id and (path_roots is not None) and (path_rules is not None):
        if _is_path_filtered(connection_id, full_path, path_roots, path_rules):
            return {"action": "skipped_rules", "name": name}
    elif _is_blacklisted(full_path, blacklist):
        # Fallback legacy
        return {"action": "skipped_blacklist", "name": name}

    if is_folder:
        # On ne traite pas les dossiers en eux-memes : leurs fichiers
        # arrivent dans le delta separement
        return {"action": "folder_ignored", "name": name}

    if is_deleted:
        # Soft delete : marque deleted_at
        return _soft_delete_file(tenant_id, item_id, name)

    # Fichier modifie ou cree : delegue a drive_scanner._process_file
    file_info = {
        "id": item_id,
        "name": name,
        "path": full_path,
        "size": size,
        "web_url": item.get("webUrl", ""),
        "mime_type": (item.get("file") or {}).get("mimeType", ""),
        "modified_at": item.get("lastModifiedDateTime", ""),
    }
    return _scan_file_via_scanner(
        tenant_id=tenant_id, username=username, token=token,
        drive_id=drive_id, file_info=file_info,
    )


def _soft_delete_file(tenant_id: str, file_id: str, name: str) -> dict:
    """Marque deleted_at pour toutes les lignes du fichier dans
    drive_semantic_content. Soft delete pour permettre la restauration
    si le fichier est restaure cote SharePoint.
    """
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            UPDATE drive_semantic_content
            SET deleted_at = NOW(), updated_at = NOW()
            WHERE tenant_id = %s AND file_id = %s
              AND deleted_at IS NULL
        """, (tenant_id, file_id))
        rows_affected = c.rowcount
        conn.commit()
        logger.info(
            "[DriveDelta] DELETED %s (%d lignes marquees)",
            name, rows_affected,
        )
        return {"action": "soft_deleted", "name": name,
                "rows_affected": rows_affected}
    except Exception as e:
        logger.error(
            "[DriveDelta] _soft_delete echec %s : %s",
            name, str(e)[:200],
        )
        return {"action": "delete_error", "name": name,
                "error": str(e)[:150]}
    finally:
        if conn:
            conn.close()


def _scan_file_via_scanner(tenant_id: str, username: str, token: str,
                             drive_id: str, file_info: dict) -> dict:
    """Delegue a drive_scanner._process_file pour vectoriser un fichier
    individuel. Necessite folder_db_id qu on resout depuis drive_folders.
    """
    try:
        from app.jobs.drive_scanner import _process_file
        # Resoudre folder_db_id : on cherche la config sharepoint principale
        # du tenant (drive_scanner s en sert pour stocker)
        conn = None
        folder_db_id = None
        try:
            conn = get_pg_conn()
            c = conn.cursor()
            c.execute("""
                SELECT id FROM drive_folders
                WHERE tenant_id = %s AND provider = 'sharepoint'
                  AND drive_id = %s AND enabled = TRUE
                ORDER BY updated_at DESC LIMIT 1
            """, (tenant_id, drive_id))
            row = c.fetchone()
            if row:
                folder_db_id = row[0]
        finally:
            if conn:
                conn.close()

        if not folder_db_id:
            return {"action": "no_folder_config", "name": file_info["name"]}

        # _process_file attend un token_ref mutable [token]
        token_ref = [token]
        result = _process_file(
            tenant_id=tenant_id,
            folder_db_id=folder_db_id,
            token_ref=token_ref,
            username=username,
            drive_id=drive_id,
            file_info=file_info,
            force_rescan=True,  # Le delta a explicitement signale un changement
        )
        return {"action": f"scanner_{result.get('status', 'unknown')}",
                "name": file_info["name"],
                "level1_chunks": result.get("level1_chunks", 0),
                "level2_chunks": result.get("level2_chunks", 0)}
    except Exception as e:
        logger.error(
            "[DriveDelta] _scan_file_via_scanner crash %s : %s",
            file_info.get("name", "?"), str(e)[:200],
        )
        return {"action": "scanner_crash",
                "name": file_info.get("name", "?"),
                "error": str(e)[:150]}


def _sync_one_connection(conn_info: dict) -> dict:
    """Sync delta pour UNE connexion Drive.
    Retourne stats : items_seen, items_new, items_deleted, errors.
    """
    connection_id = conn_info["connection_id"]
    tenant_id = conn_info["tenant_id"]
    username = conn_info["username"]
    tool_type = conn_info["tool_type"]

    stats = {
        "connection_id": connection_id, "tenant_id": tenant_id,
        "username": username, "tool_type": tool_type,
        "items_seen": 0, "items_new": 0, "items_deleted": 0,
        "items_skipped": 0, "errors": 0, "status": "ok",
    }

    # Pour cette premiere version : sharepoint uniquement
    # En base SharePoint est stocke avec tool_type 'drive' OU 'sharepoint'
    # (heritage). Google Drive (tool_type 'google_drive') ajoute en S6.
    if tool_type not in ("drive", "sharepoint"):
        stats["status"] = "skipped_provider"
        return stats

    write_mode = _is_write_mode_enabled()
    # Normalisation tool_type pour le monitoring : en base 'drive' = SharePoint
    health_type = "sharepoint" if tool_type == "drive" else tool_type
    _ensure_health_registered(connection_id, tenant_id, username, health_type)

    # 1. Token Microsoft Graph
    try:
        from app.token_manager import get_valid_microsoft_token
        token = get_valid_microsoft_token(username)
    except Exception as e:
        stats["status"] = "no_token"
        stats["errors"] += 1
        _record_health_event(
            connection_id, "error", error_detail=f"no_token: {str(e)[:150]}",
        )
        return stats
    if not token:
        stats["status"] = "no_token"
        _record_health_event(
            connection_id, "error", error_detail="no_token",
        )
        return stats

    # 2. Resolution drive_id
    drive_id = _resolve_drive_for_connection(token, tenant_id)
    if not drive_id:
        stats["status"] = "no_drive_config"
        _record_health_event(
            connection_id, "error", error_detail="no_drive_config",
        )
        return stats

    # 3. Recupere ou initialise le delta_link
    delta_link = _get_delta_link(connection_id)
    if not delta_link:
        # Premier passage : init avec ?token=latest
        delta_link = _build_initial_delta_url(token, drive_id)
        if not delta_link:
            stats["status"] = "init_failed"
            _record_health_event(
                connection_id, "error", error_detail="init_delta_failed",
            )
            return stats
        _store_delta_link(connection_id, delta_link)
        # On retourne sans traiter de change : le prochain tick aura un
        # vrai deltaLink avec les changements futurs uniquement.
        stats["status"] = "initialized"
        _record_health_event(
            connection_id, "ok", items_seen=0, items_new=0,
        )
        return stats

    # 4. Lecture blacklist (cache pour ce tick) + nouvelles regles include/exclude
    # Phase Drive multi-racines (02/05/2026) : on charge les roots+rules
    # du nouveau systeme. La _is_blacklisted reste pour failsafe.
    blacklist = _get_blacklist(tenant_id, connection_id)
    rules_enabled = os.environ.get("DRIVE_PATH_RULES_ENABLED", "true").lower() == "true"
    path_roots: list = []
    path_rules: list = []
    if rules_enabled:
        try:
            from app.connectors.drive_path_rules import (
                get_drive_roots, get_path_rules,
            )
            path_roots = get_drive_roots(connection_id)
            path_rules = get_path_rules(connection_id)
            logger.info(
                "[DriveDelta] conn=%d regles chargees : %d racines, %d regles",
                connection_id, len(path_roots), len(path_rules),
            )
        except Exception as e:
            logger.warning(
                "[DriveDelta] conn=%d echec chargement regles path : %s",
                connection_id, str(e)[:150],
            )
            path_roots = []
            path_rules = []

    # 5. Boucle de pagination delta
    current_url = delta_link
    last_delta_link = None
    items_processed_total = 0

    while current_url and items_processed_total < MAX_CHANGES_PER_TICK:
        result = _fetch_delta(token, current_url)
        if not result["ok"]:
            err = result.get("error", "unknown")
            if err == "delta_token_expired":
                # Drop le delta_link, on re-initialisera au prochain tick
                logger.warning(
                    "[DriveDelta] conn=%d delta token expire, re-init au "
                    "prochain tick", connection_id,
                )
                _store_delta_link(connection_id, "")
                stats["status"] = "delta_expired"
            else:
                logger.error(
                    "[DriveDelta] conn=%d fetch echec : %s",
                    connection_id, err,
                )
                stats["status"] = "fetch_error"
                stats["errors"] += 1
            _record_health_event(
                connection_id, "error", error_detail=err,
            )
            return stats

        items = result["items"]
        for item in items:
            stats["items_seen"] += 1
            items_processed_total += 1
            try:
                if write_mode:
                    res = _process_change_write(
                        item=item, blacklist=blacklist,
                        tenant_id=tenant_id, username=username,
                        token=token, drive_id=drive_id,
                        connection_id=connection_id,
                        path_roots=path_roots, path_rules=path_rules,
                    )
                else:
                    res = _process_change_shadow(
                        item, blacklist,
                        connection_id=connection_id,
                        path_roots=path_roots, path_rules=path_rules,
                    )

                action = res.get("action", "")
                if "deleted" in action:
                    stats["items_deleted"] += 1
                elif "modified" in action or "scanner_ok" in action:
                    stats["items_new"] += 1
                elif "skipped" in action or "ignored" in action:
                    stats["items_skipped"] += 1
                elif "error" in action or "crash" in action:
                    stats["errors"] += 1
            except Exception as e:
                stats["errors"] += 1
                logger.error(
                    "[DriveDelta] process item crash : %s", str(e)[:200],
                )

        # Pagination : si nextLink, on continue ; sinon on a un deltaLink
        if result.get("delta_link"):
            last_delta_link = result["delta_link"]
            break
        current_url = result.get("next_link")

    # 6. Stocker le nouveau delta_link pour le prochain tick
    if last_delta_link:
        _store_delta_link(connection_id, last_delta_link)

    # 7. Health event de fin
    event_status = "ok" if stats["errors"] == 0 else "warning"
    _record_health_event(
        connection_id, event_status,
        items_seen=stats["items_seen"],
        items_new=stats["items_new"],
    )

    return stats


def run_drive_delta_sync():
    """Job principal du scheduler. Tourne toutes les 5 minutes.

    Mode SHADOW (defaut) : log les changements detectes sans rien
    modifier en base. Mode WRITE (DRIVE_DELTA_SYNC_WRITE_MODE=true) :
    delegue a drive_scanner pour vectoriser les fichiers modifies.

    Tolerant aux pannes : ne plante jamais le scheduler.
    """
    started_at = datetime.now()
    write_mode = _is_write_mode_enabled()
    mode_label = "WRITE" if write_mode else "SHADOW"

    try:
        connections = _get_drive_connections()
    except Exception as e:
        logger.error(
            "[DriveDelta] Liste connexions echec : %s", str(e)[:200],
        )
        return

    if not connections:
        logger.debug("[DriveDelta] Aucune connexion Drive active, skip")
        return

    total_seen = 0
    total_new = 0
    total_deleted = 0
    total_errors = 0
    total_processed = 0

    for conn_info in connections:
        # Etape 5 (06/05/2026) : polling adaptatif jour/nuit. Skip si
        # hors heures ouvrees Paris ET dernier poll < 30 min.
        try:
            from app.polling_schedule import should_skip_poll_now
            if should_skip_poll_now(conn_info["connection_id"]):
                logger.debug(
                    "[DriveDelta] skip conn=%s (hors heures ouvrees + dernier poll < 30 min)",
                    conn_info["connection_id"],
                )
                continue
        except Exception as _e_sk:
            logger.warning("[DriveDelta] should_skip check echoue : %s", str(_e_sk)[:120])
        try:
            stats = _sync_one_connection(conn_info)
            total_seen += stats.get("items_seen", 0)
            total_new += stats.get("items_new", 0)
            total_deleted += stats.get("items_deleted", 0)
            total_errors += stats.get("errors", 0)
            total_processed += 1
        except Exception as e:
            total_errors += 1
            logger.error(
                "[DriveDelta] conn=%s crash : %s",
                conn_info.get("connection_id"), str(e)[:200],
            )

    duration = (datetime.now() - started_at).total_seconds()
    logger.info(
        "[DriveDelta][%s] Tick termine : %d connexions, %d items vus, "
        "%d new, %d deleted, %d erreurs en %.1fs",
        mode_label, total_processed, total_seen, total_new,
        total_deleted, total_errors, duration,
    )
