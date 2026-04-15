"""
Connecteur SharePoint Drive pour Raya.

La configuration (nom du site, dossier racine) est lue depuis tenants.settings.
Le drive_id est mis en cache 30 min pour éviter les appels Graph redondants.
"""
import time
import requests

GRAPH = "https://graph.microsoft.com/v1.0"

# Valeurs par défaut — NEUTRES (pas de présupposition sur un tenant)
_DEFAULTS = {
    "site_name": "",
    "folder_name": "",
    "drive_name": "Documents",
}

# ─── CACHE DRIVE ───
# Clé : site_name — Valeur : {site_id, drive_id, expires}
_drive_cache: dict = {}
_CACHE_TTL = 1800  # 30 minutes


def _cache_get(site_name: str):
    """Retourne (site_id, drive_id) depuis le cache si encore valide, sinon None."""
    entry = _drive_cache.get(site_name)
    if entry and entry["expires"] > time.time():
        return entry["site_id"], entry["drive_id"]
    return None, None


def _cache_set(site_name: str, site_id: str, drive_id: str):
    """Met en cache le drive pour 30 min."""
    _drive_cache[site_name] = {
        "site_id": site_id,
        "drive_id": drive_id,
        "expires": time.time() + _CACHE_TTL,
    }


def _cache_invalidate(site_name: str = None):
    """Invalide le cache (après mise à jour de config SharePoint)."""
    if site_name:
        _drive_cache.pop(site_name, None)
    else:
        _drive_cache.clear()


def _h(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


# ─── CONFIG DYNAMIQUE ───

def get_drive_config(tenant_id: str = "couffrant_solar") -> dict:
    """
    Charge la config SharePoint depuis tenants.settings.
    Retourne un dict avec site_name, folder_name, drive_name, path_candidates, configured.
    Si le tenant n'a pas de SharePoint configuré, configured=False.
    """
    try:
        from app.database import get_pg_conn
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("SELECT settings FROM tenants WHERE id = %s", (tenant_id,))
        row = c.fetchone()
        conn.close()
        if row and row[0]:
            s = row[0]
            folder = s.get("sharepoint_folder", "")
            site = s.get("sharepoint_site", "")
            if folder and site:
                return {
                    "site_name": site,
                    "folder_name": folder,
                    "drive_name": s.get("sharepoint_drive") or "Documents",
                    "path_candidates": _build_candidates(folder),
                    "configured": True,
                }
    except Exception:
        pass
    return {
        "site_name": "",
        "folder_name": "",
        "drive_name": "Documents",
        "path_candidates": [],
        "configured": False,
    }


def _build_candidates(folder_name: str) -> list:
    return [
        folder_name,
        f"Documents/{folder_name}",
        f"Shared Documents/{folder_name}",
        folder_name.replace("ï", "i"),
    ]


def _get_config_for_username(username: str) -> dict:
    try:
        from app.app_security import get_tenant_id
        tenant_id = get_tenant_id(username)
        return get_drive_config(tenant_id)
    except Exception:
        return get_drive_config()


# ─── DÉCOUVERTE SHAREPOINT (avec cache drive_id) ───

def _find_sharepoint_site_and_drive(token: str, config: dict = None) -> tuple:
    """
    Trouve le site SharePoint et le drive documentaire.
    Le drive_id est mis en cache 30 min pour éviter les appels Graph répétés.
    """
    if config is None:
        config = get_drive_config()
    site_name = config["site_name"]

    # Vérification du cache
    cached_site_id, cached_drive_id = _cache_get(site_name)
    if cached_site_id and cached_drive_id:
        return cached_site_id, cached_drive_id, []

    site_id = None
    drive_id = None
    all_drives = []

    for endpoint in ["/sites", "/me/followedSites"]:
        try:
            params = {"search": site_name} if endpoint == "/sites" else {}
            data = requests.get(f"{GRAPH}{endpoint}", headers=_h(token),
                                params=params, timeout=20).json()
            for site in data.get("value", []):
                if site_name.lower() in (site.get("name", "") + site.get("displayName", "")).lower():
                    site_id = site.get("id")
                    break
        except Exception:
            pass
        if site_id:
            break

    if not site_id:
        return None, None, []

    try:
        drives_data = requests.get(f"{GRAPH}/sites/{site_id}/drives",
                                   headers=_h(token), timeout=15).json()
        all_drives = drives_data.get("value", [])
        drive_name = config.get("drive_name", "Documents").lower()
        for drive in all_drives:
            if drive.get("driveType") == "documentLibrary" and \
               drive_name in drive.get("name", "").lower():
                drive_id = drive.get("id")
                break
        if not drive_id:
            for drive in all_drives:
                if drive.get("driveType") == "documentLibrary":
                    drive_id = drive.get("id")
                    break
        if not drive_id and all_drives:
            drive_id = all_drives[0].get("id")
    except Exception:
        pass

    # Mise en cache si trouvé
    if site_id and drive_id:
        _cache_set(site_name, site_id, drive_id)

    return site_id, drive_id, all_drives


def _find_folder_root(token: str, drive_id: str, config: dict = None) -> tuple:
    if config is None:
        config = get_drive_config()
    for candidate in config["path_candidates"]:
        try:
            meta = requests.get(
                f"{GRAPH}/drives/{drive_id}/root:/{candidate}",
                headers=_h(token), params={"$select": "id,name,webUrl"}, timeout=15
            ).json()
            if meta.get("id"):
                return candidate, meta["id"]
        except Exception:
            continue
    return None, None


def _fmt(items: list) -> list:
    result = []
    for f in items:
        ext = f.get("name", "").rsplit(".", 1)[-1].lower() if "." in f.get("name", "") else ""
        result.append({
            "nom": f.get("name"),
            "type": "dossier" if "folder" in f else "fichier",
            "extension": ext,
            "taille_ko": round(f.get("size", 0) / 1024, 1) if f.get("size") else 0,
            "modifié": f.get("lastModifiedDateTime", "")[:10],
            "lien": f.get("webUrl", ""),
            "id": f.get("id"),
        })
    return result


# ─── ACTIONS DRIVE ───
# Réexport lazy pour éviter l'import circulaire drive_connector ↔ drive_read
def __getattr__(name):
    if name in ('list_drive', 'read_drive_file', 'search_drive'):
        from app.connectors.drive_read import list_drive, read_drive_file, search_drive
        return {'list_drive': list_drive, 'read_drive_file': read_drive_file, 'search_drive': search_drive}[name]
    if name in ('create_folder', 'move_item', 'copy_item', 'save_drive_config'):
        from app.connectors.drive_actions import create_folder, move_item, copy_item, save_drive_config
        return {'create_folder': create_folder, 'move_item': move_item, 'copy_item': copy_item, 'save_drive_config': save_drive_config}[name]
    raise AttributeError(f"module 'app.connectors.drive_connector' has no attribute {name}")
