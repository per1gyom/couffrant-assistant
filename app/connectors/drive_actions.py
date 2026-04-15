"""
Actions ecriture Drive/SharePoint.
Extrait de drive_connector.py -- SPLIT-C1.
"""
import requests
from app.logging_config import get_logger
logger=get_logger("raya.drive")
def _h(token): return {"Authorization":f"Bearer {token}","Content-Type":"application/json"}


def save_drive_config(tenant_id: str, site_name: str, folder_name: str,
                      drive_name: str = "Documents") -> dict:
    """Sauvegarde la config SharePoint + invalide le cache."""
    try:
        from app.database import get_pg_conn
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            UPDATE tenants
            SET settings = settings || %s::jsonb
            WHERE id = %s
        """, (
            f'{{"sharepoint_site": "{site_name}", "sharepoint_folder": "{folder_name}", "sharepoint_drive": "{drive_name}"}}',
            tenant_id
        ))
        conn.commit()
        conn.close()
        # Invalide le cache pour ce site
        _cache_invalidate(site_name)
        return {"status": "ok", "message": "Configuration SharePoint mise à jour."}
    except Exception as e:
        return {"status": "error", "message": str(e)[:200]}



def create_folder(token: str, parent_id: str, folder_name: str,
                  drive_id: str = None, username: str = None) -> dict:
    try:
        if not drive_id:
            config = _get_config_for_username(username) if username else get_drive_config()
            _, drive_id, _ = _find_sharepoint_site_and_drive(token, config)
        if not drive_id:
            return {"status": "error", "message": "Drive SharePoint introuvable."}
        resp = requests.post(
            f"{GRAPH}/drives/{drive_id}/items/{parent_id}/children",
            headers=_h(token),
            json={"name": folder_name, "folder": {},
                  "@microsoft.graph.conflictBehavior": "rename"},
            timeout=20
        ).json()
        return {"status": "ok", "message": f"Dossier '{folder_name}' créé.",
                "id": resp.get("id"), "lien": resp.get("webUrl", "")}
    except Exception as e:
        return {"status": "error", "message": f"Création impossible : {str(e)[:200]}"}



def move_item(token: str, item_id: str, dest_id: str,
             new_name: str = None, drive_id: str = None, username: str = None) -> dict:
    try:
        if not drive_id:
            config = _get_config_for_username(username) if username else get_drive_config()
            _, drive_id, _ = _find_sharepoint_site_and_drive(token, config)
        if not drive_id:
            return {"status": "error", "message": "Drive SharePoint introuvable."}
        body = {"parentReference": {"driveId": drive_id, "id": dest_id}}
        if new_name:
            body["name"] = new_name
        resp = requests.patch(
            f"{GRAPH}/drives/{drive_id}/items/{item_id}",
            headers=_h(token), json=body, timeout=20
        ).json()
        label = new_name or resp.get("name", item_id[:8])
        return {"status": "ok", "message": f"'{label}' déplacé.",
                "id": resp.get("id", item_id)}
    except Exception as e:
        return {"status": "error", "message": f"Déplacement impossible : {str(e)[:200]}"}



def copy_item(token: str, item_id: str, dest_id: str,
             new_name: str = None, drive_id: str = None, username: str = None) -> dict:
    try:
        if not drive_id:
            config = _get_config_for_username(username) if username else get_drive_config()
            _, drive_id, _ = _find_sharepoint_site_and_drive(token, config)
        if not drive_id:
            return {"status": "error", "message": "Drive SharePoint introuvable."}
        body = {"parentReference": {"driveId": drive_id, "id": dest_id}}
        if new_name:
            body["name"] = new_name
        resp = requests.post(
            f"{GRAPH}/drives/{drive_id}/items/{item_id}/copy",
            headers=_h(token), json=body, timeout=20
        )
        if resp.status_code in (200, 202):
            return {"status": "ok",
                    "message": f"Copie lancée{' → ' + new_name if new_name else ''}.",
                    "async": resp.status_code == 202,
                    "monitor_url": resp.headers.get("Location", "")}
        resp.raise_for_status()
        return {"status": "ok", "message": "Copie effectuée."}
    except Exception as e:
        return {"status": "error", "message": f"Copie impossible : {str(e)[:200]}"}


# ─── ALIAS DE COMPATIBILITÉ ───
# (list_drive, read_drive_file, search_drive restent dans drive_connector.py)
create_drive_folder = create_folder
move_drive_item = move_item
copy_drive_item = copy_item

