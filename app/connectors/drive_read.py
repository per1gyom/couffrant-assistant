"""
Fonctions lecture Drive/SharePoint.
Extrait de drive_connector.py -- SPLIT-F2.
"""
import os
import requests
from app.logging_config import get_logger
from app.connectors.drive_connector import (
    _h, _get_config_for_username, _find_sharepoint_site_and_drive,
    _find_folder_root, _fmt, get_drive_config,
)
logger=get_logger("raya.drive")


def list_drive(token: str, subfolder: str = "", username: str = None) -> dict:
    try:
        config = _get_config_for_username(username) if username else get_drive_config()
        folder_name = config["folder_name"]
        site_name = config["site_name"]

        _, drive_id, _ = _find_sharepoint_site_and_drive(token, config)

        if not drive_id:
            try:
                data = requests.get(
                    f"{GRAPH}/me/drive/root:/{folder_name}:/children",
                    headers=_h(token),
                    params={"$top": 100,
                            "$select": "name,id,size,folder,file,lastModifiedDateTime,webUrl",
                            "$orderby": "name"},
                    timeout=20
                ).json()
                items = _fmt(data.get("value", []))
                return {"status": "ok", "source": "OneDrive",
                        "dossier": folder_name, "count": len(items), "items": items}
            except Exception:
                return {"status": "error",
                        "message": f"Site SharePoint '{site_name}' introuvable."}

        base_path, base_id = _find_folder_root(token, drive_id, config)
        if not base_id:
            return {"status": "error",
                    "message": f"Dossier '{folder_name}' introuvable. "
                               f"Vérifiez la config SharePoint dans le panel admin."}

        params_q = {"$top": 100,
                    "$select": "name,id,size,folder,file,lastModifiedDateTime,webUrl",
                    "$orderby": "name"}

        if not subfolder:
            data = requests.get(f"{GRAPH}/drives/{drive_id}/items/{base_id}/children",
                                headers=_h(token), params=params_q, timeout=20).json()
            items = _fmt(data.get("value", []))
            return {"status": "ok", "source": f"SharePoint {site_name}",
                    "dossier": folder_name, "root_id": base_id,
                    "count": len(items), "items": items}

        subfolder = subfolder.strip()
        if len(subfolder) > 20 and "/" not in subfolder and " " not in subfolder:
            data = requests.get(f"{GRAPH}/drives/{drive_id}/items/{subfolder}/children",
                                headers=_h(token), params=params_q, timeout=20).json()
            items = _fmt(data.get("value", []))
            return {"status": "ok", "source": f"SharePoint {site_name}",
                    "dossier": f"(id={subfolder[:12]}…)", "dossier_id": subfolder,
                    "count": len(items), "items": items}

        root_data = requests.get(f"{GRAPH}/drives/{drive_id}/items/{base_id}/children",
                                 headers=_h(token),
                                 params={"$top": 100, "$select": "name,id,folder"},
                                 timeout=15).json()
        target_id = None
        target_name = subfolder
        for item in root_data.get("value", []):
            if "folder" in item and item.get("name", "").lower() == subfolder.lower():
                target_id = item.get("id")
                target_name = item.get("name", subfolder)
                break

        if not target_id:
            return {"status": "error",
                    "message": f"Sous-dossier '{subfolder}' introuvable."}

        data = requests.get(f"{GRAPH}/drives/{drive_id}/items/{target_id}/children",
                            headers=_h(token), params=params_q, timeout=20).json()
        items = _fmt(data.get("value", []))
        return {"status": "ok", "source": f"SharePoint {site_name}",
                "dossier": target_name, "dossier_id": target_id,
                "count": len(items), "items": items}

    except Exception as e:
        return {"status": "error", "message": f"Erreur Drive : {str(e)[:300]}"}



def read_drive_file(token: str, file_path_or_id: str, username: str = None) -> dict:
    try:
        config = _get_config_for_username(username) if username else get_drive_config()
        _, drive_id, _ = _find_sharepoint_site_and_drive(token, config)
        base_path, _ = _find_folder_root(token, drive_id, config) if drive_id else (None, None)

        file_ref = file_path_or_id.strip()
        meta = None
        content_url = None

        if drive_id and len(file_ref) > 20 and "/" not in file_ref and " " not in file_ref:
            resp = requests.get(f"{GRAPH}/drives/{drive_id}/items/{file_ref}",
                                headers=_h(token),
                                params={"$select": "id,name,size,webUrl,file"}, timeout=15)
            if resp.ok:
                meta = resp.json()
                content_url = f"{GRAPH}/drives/{drive_id}/items/{file_ref}/content"
        elif drive_id and base_path:
            folder_name = config["folder_name"]
            sub = file_ref.replace("\\", "/").strip("/")
            for prefix in [base_path, folder_name, "Documents"]:
                if sub.lower().startswith(prefix.lower() + "/"):
                    sub = sub[len(prefix)+1:]
                    break
            try:
                target = f"{base_path}/{sub}"
                resp = requests.get(f"{GRAPH}/drives/{drive_id}/root:/{target}",
                                    headers=_h(token),
                                    params={"$select": "id,name,size,webUrl,file"}, timeout=15)
                if resp.ok:
                    meta = resp.json()
                    content_url = f"{GRAPH}/drives/{drive_id}/root:/{target}:/content"
            except Exception:
                pass

        if not meta:
            return {"status": "error", "message": f"Fichier '{file_ref[:50]}' introuvable."}

        name = meta.get("name", "")
        size = meta.get("size", 0)
        web_url = meta.get("webUrl", "")
        ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""

        if ext in {"txt", "md", "csv", "json", "xml", "log"}:
            resp = requests.get(content_url,
                                headers={"Authorization": f"Bearer {token}"}, timeout=30)
            resp.raise_for_status()
            return {"status": "ok", "fichier": name, "id": meta.get("id"),
                    "type": "texte", "contenu": resp.text[:5000], "lien": web_url}

        conseil = "Joins via 📎 pour que je l'analyse."
        if ext in {"docx", "doc"}:
            return {"status": "ok", "fichier": name, "id": meta.get("id"), "type": "word",
                    "taille_ko": round(size/1024, 1), "lien": web_url, "conseil": conseil}
        if ext in {"xlsx", "xls", "xlsm", "ods"}:
            return {"status": "ok", "fichier": name, "id": meta.get("id"), "type": "tableur",
                    "taille_ko": round(size/1024, 1), "lien": web_url, "conseil": conseil}
        if ext == "pdf":
            return {"status": "ok", "fichier": name, "id": meta.get("id"), "type": "pdf",
                    "taille_ko": round(size/1024, 1), "lien": web_url, "conseil": conseil}

        return {"status": "ok", "fichier": name, "id": meta.get("id"),
                "type": ext or "inconnu", "taille_ko": round(size/1024, 1), "lien": web_url}

    except Exception as e:
        return {"status": "error", "message": f"Lecture impossible : {str(e)[:300]}"}



def search_drive(token: str, query: str, username: str = None) -> dict:
    try:
        config = _get_config_for_username(username) if username else get_drive_config()
        site_name = config["site_name"]
        _, drive_id, _ = _find_sharepoint_site_and_drive(token, config)
        _, base_id = _find_folder_root(token, drive_id, config) if drive_id else (None, None)
        q_safe = query.replace("'", "''")

        if drive_id and base_id:
            data = requests.get(
                f"{GRAPH}/drives/{drive_id}/items/{base_id}/search(q='{q_safe}')",
                headers=_h(token),
                params={"$top": 20,
                        "$select": "name,id,size,folder,file,lastModifiedDateTime,webUrl,parentReference"},
                timeout=20
            ).json()
            items = [{
                "nom": f.get("name"),
                "type": "dossier" if "folder" in f else "fichier",
                "dossier_parent": f.get("parentReference", {}).get("name", ""),
                "id": f.get("id"),
                "modifié": f.get("lastModifiedDateTime", "")[:10],
                "lien": f.get("webUrl", ""),
            } for f in data.get("value", [])]
            return {"status": "ok", "source": f"SharePoint {site_name}",
                    "recherche": query, "count": len(items), "items": items}

        return {"status": "error", "message": "Drive SharePoint introuvable."}
    except Exception as e:
        return {"status": "error", "message": f"Recherche impossible : {str(e)[:300]}"}
from app.connectors.drive_actions import create_folder,move_item,copy_item,save_drive_config  # noqa

