"""
Drive Manager — résolution automatique des connecteurs de stockage.

get_user_drives(username) → liste tous les DriveConnector actifs.
get_drive_for(username, hint) → résout le bon drive selon un hint.

Ajouter un provider :
  1. Créer la classe dans connectors/
  2. L'enregistrer dans PROVIDER_MAP
  C'est tout.
"""
from __future__ import annotations
from app.connectors.drive_connector_base import DriveConnector, DriveItem
from app.logging_config import get_logger

logger = get_logger("raya.drive_manager")


# ─── REGISTRE ──────────────────────────────────────────────────────

def _get_provider_map() -> dict:
    from app.connectors.sharepoint_connector import SharePointConnector
    from app.connectors.google_drive_connector import GoogleDriveConnector
    return {
        "sharepoint": SharePointConnector,
        "microsoft":  SharePointConnector,
        "office":     SharePointConnector,
        "google_drive": GoogleDriveConnector,
        "gdrive":       GoogleDriveConnector,
        "google":       GoogleDriveConnector,
    }


# ─── RÉSOLUTION ────────────────────────────────────────────────────

def get_user_drives(username: str) -> list[DriveConnector]:
    """
    Retourne tous les drives connectés pour un utilisateur.
    Ordre : V2 (tenant_connections) → legacy SharePoint.
    """
    drives = []
    seen = set()
    provider_map = _get_provider_map()

    # 1. Connexions V2 (tenant_connections)
    try:
        from app.connection_token_manager import get_user_tool_connections
        v2 = get_user_tool_connections(username)
        for tool_type, info in v2.items():
            cls = provider_map.get(tool_type.lower())
            if not cls:
                continue
            token = info.get("token", "")
            if not token or tool_type in seen:
                continue
            seen.add(tool_type)
            config = {"label": info.get("label", tool_type.title())}
            drives.append(cls(username=username, token=token, config=config))
            logger.debug("[DriveMgr] V2: %s", tool_type)
    except Exception as e:
        logger.warning("[DriveMgr] V2 error: %s", e)

    # 2. Legacy — SharePoint (token Microsoft)
    if "sharepoint" not in seen and "microsoft" not in seen:
        try:
            from app.connection_token_manager import get_connection_token
            ms_token = get_connection_token(username, "microsoft")
            if ms_token:
                from app.connectors.sharepoint_connector import SharePointConnector
                from app.database import get_pg_conn
                from app.app_security import get_tenant_id
                tenant_id = get_tenant_id(username)
                config = _get_sp_config(tenant_id)
                drives.append(SharePointConnector(
                    username=username, token=ms_token, config=config
                ))
                seen.add("sharepoint")
                logger.debug("[DriveMgr] Legacy SharePoint: %s", tenant_id)
        except Exception as e:
            logger.warning("[DriveMgr] Legacy SP error: %s", e)

    logger.info("[DriveMgr] %s: %d drive(s) actif(s)", username, len(drives))
    return drives


def get_drive_for(username: str, hint: str = "") -> DriveConnector | None:
    """
    Résout le drive à utiliser selon un hint.
    hint = 'google' | 'sharepoint' | 'gdrive' | 'microsoft' | '' (auto)
    """
    drives = get_user_drives(username)
    if not drives:
        return None
    if not hint:
        return drives[0]

    h = hint.lower().strip()
    google_aliases    = {"google", "gdrive", "google drive", "drive perso", "drive google"}
    ms_aliases        = {"sharepoint", "microsoft", "office", "drive pro", "drive entreprise"}

    for d in drives:
        if d.provider in ("google_drive",) and h in google_aliases: return d
        if d.provider == "sharepoint" and h in ms_aliases:          return d
        if h in d.provider.lower():                                  return d
        if h in (d.config.get("label") or "").lower():               return d

    return drives[0]


def get_drive_summary(username: str) -> str:
    """Résumé lisible pour le prompt Raya."""
    drives = get_user_drives(username)
    if not drives:
        return "Aucun drive connecté."
    return ", ".join(d.display_name for d in drives)


def search_all_drives(username: str, query: str) -> list[dict]:
    """Recherche dans TOUS les drives connectés."""
    results = []
    for drive in get_user_drives(username):
        try:
            items = drive.search(query)
            for item in items:
                results.append({
                    "id": item.id, "name": item.name, "url": item.url,
                    "type": item.item_type, "source": item.source,
                    "drive_label": item.drive_label,
                })
        except Exception as e:
            logger.warning("[DriveMgr] search error (%s): %s", drive.provider, e)
    return results


# ─── HELPERS ───────────────────────────────────────────────────────

def _get_sp_config(tenant_id: str) -> dict:
    try:
        from app.connectors.drive_connector import get_drive_config
        cfg = get_drive_config(tenant_id)
        cfg["label"] = "SharePoint"
        return cfg
    except Exception:
        return {"label": "SharePoint"}
