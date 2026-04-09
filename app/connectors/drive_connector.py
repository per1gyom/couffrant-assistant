"""
Connecteur SharePoint Drive pour Raya.

La configuration (nom du site, dossier racine) est lue depuis tenants.settings.
Le drive_id est mis en cache 30 min pour éviter les appels Graph redondants.
"""
import time
import requests

GRAPH = "https://graph.microsoft.com/v1.0"

# Valeurs par défaut
_DEFAULTS = {
    "site_name": "Commun",
    "folder_name": "1_Photovoltaïque",
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
    Retourne un dict avec site_name, folder_name, drive_name, path_candidates.
    Toujours fonctionnel même si la table n'est pas configurée.
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
            folder = s.get("sharepoint_folder") or _DEFAULTS["folder_name"]
            return {
                "site_name": s.get("sharepoint_site") or _DEFAULTS["site_name"],
                "folder_name": folder,
                "drive_name": s.get("sharepoint_drive") or _DEFAULTS["drive_name"],
                "path_candidates": _build_candidates(folder),
            }
    except Exception:
        pass
    return {
        "site_name": _DEFAULTS["site_name"],
        "folder_name": _DEFAULTS["folder_name"],
        "drive_name": _DEFAULTS["drive_name"],
        "path_candidates": _build_candidates(_DEFAULTS["folder_name"]),
    }


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
list_aria_drive = list_drive
read_aria_drive_file = read_drive_file
search_aria_drive = search_drive
create_drive_folder = create_folder
move_drive_item = move_item
copy_drive_item = copy_item
