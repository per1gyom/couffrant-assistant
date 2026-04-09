"""
Connecteur SharePoint Drive pour Raya.

Isolé d'outlook_connector.py pour séparer les responsabilités :
- drive_connector.py  → SharePoint / OneDrive
- outlook_connector.py → Mails, calendrier, tâches, contacts
"""
import requests

GRAPH = "https://graph.microsoft.com/v1.0"

SITE_NAME = "Commun"
FOLDER_NAME = "1_Photovoltaïque"
PATH_CANDIDATES = [
    "1_Photovoltaïque",
    "Documents/1_Photovoltaïque",
    "Shared Documents/1_Photovoltaïque",
    "1_Photovoltaique",
]


def _h(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


# ─── DÉCOUVERTE SHAREPOINT ───

def _find_sharepoint_site_and_drive(token: str) -> tuple:
    """Trouve le site SharePoint et le drive documentaire."""
    site_id = None
    drive_id = None
    all_drives = []

    for endpoint in ["/sites", "/me/followedSites"]:
        try:
            params = {"search": SITE_NAME} if endpoint == "/sites" else {}
            data = requests.get(f"{GRAPH}{endpoint}", headers=_h(token), params=params, timeout=20).json()
            for site in data.get("value", []):
                if SITE_NAME.lower() in (site.get("name", "") + site.get("displayName", "")).lower():
                    site_id = site.get("id")
                    break
        except Exception:
            pass
        if site_id:
            break

    if not site_id:
        return None, None, []

    try:
        drives_data = requests.get(f"{GRAPH}/sites/{site_id}/drives", headers=_h(token), timeout=15).json()
        all_drives = drives_data.get("value", [])
        for drive in all_drives:
            if drive.get("driveType") == "documentLibrary" and "document" in drive.get("name", "").lower():
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

    return site_id, drive_id, all_drives


def _find_folder_root(token: str, drive_id: str) -> tuple:
    """Trouve l'item_id du dossier racine 1_Photovoltaïque."""
    for candidate in PATH_CANDIDATES:
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
    """Formate les items Drive pour affichage."""
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

def list_drive(token: str, subfolder: str = "") -> dict:
    """
    Liste les fichiers dans 1_Photovoltaïque.
    subfolder : vide (racine), nom de sous-dossier, ou item_id direct.
    """
    try:
        _, drive_id, _ = _find_sharepoint_site_and_drive(token)

        if not drive_id:
            # Fallback OneDrive personnel
            try:
                data = requests.get(
                    f"{GRAPH}/me/drive/root:/{FOLDER_NAME}:/children",
                    headers=_h(token),
                    params={"$top": 100, "$select": "name,id,size,folder,file,lastModifiedDateTime,webUrl", "$orderby": "name"},
                    timeout=20
                ).json()
                items = _fmt(data.get("value", []))
                return {"status": "ok", "source": "OneDrive", "dossier": FOLDER_NAME,
                        "count": len(items), "items": items}
            except Exception:
                return {"status": "error", "message": f"Site SharePoint '{SITE_NAME}' introuvable."}

        base_path, base_id = _find_folder_root(token, drive_id)
        if not base_id:
            return {"status": "error", "message": f"Dossier '{FOLDER_NAME}' introuvable."}

        params_q = {"$top": 100, "$select": "name,id,size,folder,file,lastModifiedDateTime,webUrl", "$orderby": "name"}

        if not subfolder:
            data = requests.get(f"{GRAPH}/drives/{drive_id}/items/{base_id}/children",
                                headers=_h(token), params=params_q, timeout=20).json()
            items = _fmt(data.get("value", []))
            return {"status": "ok", "source": f"SharePoint {SITE_NAME}",
                    "dossier": FOLDER_NAME, "root_id": base_id, "count": len(items), "items": items}

        subfolder = subfolder.strip()
        # item_id direct
        if len(subfolder) > 20 and "/" not in subfolder and " " not in subfolder:
            data = requests.get(f"{GRAPH}/drives/{drive_id}/items/{subfolder}/children",
                                headers=_h(token), params=params_q, timeout=20).json()
            items = _fmt(data.get("value", []))
            return {"status": "ok", "source": f"SharePoint {SITE_NAME}",
                    "dossier": f"(id={subfolder[:12]}…)", "dossier_id": subfolder,
                    "count": len(items), "items": items}

        # Sous-dossier par nom
        root_data = requests.get(f"{GRAPH}/drives/{drive_id}/items/{base_id}/children",
                                 headers=_h(token),
                                 params={"$top": 100, "$select": "name,id,folder"}, timeout=15).json()
        target_id = None
        target_name = subfolder
        for item in root_data.get("value", []):
            if "folder" in item and item.get("name", "").lower() == subfolder.lower():
                target_id = item.get("id")
                target_name = item.get("name", subfolder)
                break

        if not target_id:
            return {"status": "error", "message": f"Sous-dossier '{subfolder}' introuvable."}

        data = requests.get(f"{GRAPH}/drives/{drive_id}/items/{target_id}/children",
                            headers=_h(token), params=params_q, timeout=20).json()
        items = _fmt(data.get("value", []))
        return {"status": "ok", "source": f"SharePoint {SITE_NAME}",
                "dossier": target_name, "dossier_id": target_id, "count": len(items), "items": items}

    except Exception as e:
        return {"status": "error", "message": f"Erreur Drive : {str(e)[:300]}"}


def read_drive_file(token: str, file_path_or_id: str) -> dict:
    """Lit le contenu d'un fichier (par item_id ou chemin)."""
    try:
        _, drive_id, _ = _find_sharepoint_site_and_drive(token)
        base_path, _ = _find_folder_root(token, drive_id) if drive_id else (None, None)

        file_ref = file_path_or_id.strip()
        meta = None
        content_url = None

        if drive_id and len(file_ref) > 20 and "/" not in file_ref and " " not in file_ref:
            resp = requests.get(f"{GRAPH}/drives/{drive_id}/items/{file_ref}",
                                headers=_h(token), params={"$select": "id,name,size,webUrl,file"}, timeout=15)
            if resp.ok:
                meta = resp.json()
                content_url = f"{GRAPH}/drives/{drive_id}/items/{file_ref}/content"
        elif drive_id and base_path:
            sub = file_ref.replace("\\", "/").strip("/")
            for prefix in [base_path, FOLDER_NAME, "Documents"]:
                if sub.lower().startswith(prefix.lower() + "/"):
                    sub = sub[len(prefix)+1:]
                    break
            try:
                target = f"{base_path}/{sub}"
                resp = requests.get(f"{GRAPH}/drives/{drive_id}/root:/{target}",
                                    headers=_h(token), params={"$select": "id,name,size,webUrl,file"}, timeout=15)
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
            resp = requests.get(content_url, headers={"Authorization": f"Bearer {token}"}, timeout=30)
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


def search_drive(token: str, query: str) -> dict:
    """Recherche dans 1_Photovoltaïque par nom."""
    try:
        _, drive_id, _ = _find_sharepoint_site_and_drive(token)
        _, base_id = _find_folder_root(token, drive_id) if drive_id else (None, None)
        q_safe = query.replace("'", "''")

        if drive_id and base_id:
            data = requests.get(
                f"{GRAPH}/drives/{drive_id}/items/{base_id}/search(q='{q_safe}')",
                headers=_h(token),
                params={"$top": 20, "$select": "name,id,size,folder,file,lastModifiedDateTime,webUrl,parentReference"},
                timeout=20
            ).json()
            items = []
            for f in data.get("value", []):
                items.append({
                    "nom": f.get("name"),
                    "type": "dossier" if "folder" in f else "fichier",
                    "dossier_parent": f.get("parentReference", {}).get("name", ""),
                    "id": f.get("id"),
                    "modifié": f.get("lastModifiedDateTime", "")[:10],
                    "lien": f.get("webUrl", ""),
                })
            return {"status": "ok", "source": f"SharePoint {SITE_NAME}",
                    "recherche": query, "count": len(items), "items": items}

        return {"status": "error", "message": "Drive SharePoint introuvable."}
    except Exception as e:
        return {"status": "error", "message": f"Recherche impossible : {str(e)[:300]}"}


def create_folder(token: str, parent_id: str, folder_name: str, drive_id: str = None) -> dict:
    """Crée un sous-dossier dans le Drive."""
    try:
        if not drive_id:
            _, drive_id, _ = _find_sharepoint_site_and_drive(token)
        if not drive_id:
            return {"status": "error", "message": "Drive SharePoint introuvable."}
        resp = requests.post(
            f"{GRAPH}/drives/{drive_id}/items/{parent_id}/children",
            headers=_h(token),
            json={"name": folder_name, "folder": {}, "@microsoft.graph.conflictBehavior": "rename"},
            timeout=20
        ).json()
        return {"status": "ok", "message": f"Dossier '{folder_name}' créé.",
                "id": resp.get("id"), "lien": resp.get("webUrl", "")}
    except Exception as e:
        return {"status": "error", "message": f"Création impossible : {str(e)[:200]}"}


def move_item(token: str, item_id: str, dest_id: str, new_name: str = None, drive_id: str = None) -> dict:
    """Déplace un item vers un dossier destination."""
    try:
        if not drive_id:
            _, drive_id, _ = _find_sharepoint_site_and_drive(token)
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
        return {"status": "ok", "message": f"'{label}' déplacé.", "id": resp.get("id", item_id)}
    except Exception as e:
        return {"status": "error", "message": f"Déplacement impossible : {str(e)[:200]}"}


def copy_item(token: str, item_id: str, dest_id: str, new_name: str = None, drive_id: str = None) -> dict:
    """Copie un fichier/dossier (opération asynchrone)."""
    try:
        if not drive_id:
            _, drive_id, _ = _find_sharepoint_site_and_drive(token)
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


# ─── ALIAS DE COMPATIBILITÉ (ancien code) ───
list_aria_drive = list_drive
read_aria_drive_file = read_drive_file
search_aria_drive = search_drive
create_drive_folder = create_folder
move_drive_item = move_item
copy_drive_item = copy_item
