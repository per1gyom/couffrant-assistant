import requests

GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"

ARCHIVE_FOLDER_ID = "AQMkAGEwZmJhNTllLWQ3MjUtNDg4ADQtYjdhMi1jMGEyZjRiNmFkNWEALgAAA-6yBmE1L7hGi--BXSl5S2sBAIyf8uOKE0VAkKv1dN8K6xgAAAIBRQAAAA=="

ONEDRIVE_SITE_NAME = "Commun"
ONEDRIVE_FOLDER_NAME = "1_Photovoltaïque"

ONEDRIVE_PATH_CANDIDATES = [
    "1_Photovoltaïque",
    "Documents/1_Photovoltaïque",
    "Shared Documents/1_Photovoltaïque",
    "1_Photovoltaique",
]

SIGNATURE_HTML = """
<div style="font-family:Arial, sans-serif; font-size:13px; color:#222; margin-top:20px; border-top:1px solid #e0e0e0; padding-top:12px;">
    <div style="margin-bottom:2px;">Solairement,</div>
    <div style="font-weight:bold; font-size:14px; margin-bottom:6px;">Guillaume Perrin</div>
    <div style="color:#555; margin-bottom:2px;">&#128222; 06 49 43 09 17</div>
    <div style="color:#555; margin-bottom:8px;">&#127758; <a href="https://www.couffrant-solar.fr" style="color:#2e7d32; text-decoration:none;">www.couffrant-solar.fr</a></div>
    <div>
        <img src="https://couffrant-solar.fr/wp-content/uploads/2025/04/cropped-logo-couffrant-solar-1.png"
             alt="Couffrant Solar"
             style="max-width:280px; height:auto; border:0; margin-top:4px;">
    </div>
</div>
"""


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _graph_get(token: str, path: str, params: dict | None = None) -> dict:
    response = requests.get(f"{GRAPH_BASE_URL}{path}", headers=_headers(token), params=params, timeout=30)
    response.raise_for_status()
    return response.json()


def _graph_post(token: str, path: str, json_body: dict | None = None) -> dict:
    response = requests.post(f"{GRAPH_BASE_URL}{path}", headers=_headers(token), json=json_body or {}, timeout=30)
    response.raise_for_status()
    if response.text.strip():
        return response.json()
    return {}


def _graph_patch(token: str, path: str, json_body: dict) -> dict:
    response = requests.patch(f"{GRAPH_BASE_URL}{path}", headers=_headers(token), json=json_body, timeout=30)
    response.raise_for_status()
    if response.text.strip():
        return response.json()
    return {}


def _graph_delete(token: str, path: str) -> bool:
    response = requests.delete(f"{GRAPH_BASE_URL}{path}", headers=_headers(token), timeout=30)
    return response.status_code == 204


def _build_email_html(body: str) -> str:
    return f"""<div style="font-family:Arial, sans-serif; font-size:14px; color:#222;">
    <div style="white-space:pre-line;">{body}</div>
    {SIGNATURE_HTML}
</div>"""


# ─────────────────────────────────────────
# SHAREPOINT — DÉCOUVERTE
# ─────────────────────────────────────────

def _find_sharepoint_site_and_drive(token: str) -> tuple[str | None, str | None, list]:
    site_id = None
    drive_id = None
    all_drives = []

    try:
        data = _graph_get(token, "/sites", params={"search": ONEDRIVE_SITE_NAME})
        for site in data.get("value", []):
            if ONEDRIVE_SITE_NAME.lower() in site.get("name", "").lower() or \
               ONEDRIVE_SITE_NAME.lower() in site.get("displayName", "").lower():
                site_id = site.get("id")
                break
    except Exception:
        pass

    if not site_id:
        try:
            data = _graph_get(token, "/me/followedSites")
            for site in data.get("value", []):
                if ONEDRIVE_SITE_NAME.lower() in site.get("name", "").lower() or \
                   ONEDRIVE_SITE_NAME.lower() in site.get("displayName", "").lower():
                    site_id = site.get("id")
                    break
        except Exception:
            pass

    if not site_id:
        return None, None, []

    try:
        drives_data = _graph_get(token, f"/sites/{site_id}/drives")
        all_drives = drives_data.get("value", [])
        for drive in all_drives:
            dtype = drive.get("driveType", "")
            dname = drive.get("name", "").lower()
            if dtype == "documentLibrary" and ("document" in dname or dname == "documents"):
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


def _find_folder_item_id(token: str, drive_id: str) -> tuple[str | None, str | None]:
    for candidate in ONEDRIVE_PATH_CANDIDATES:
        try:
            meta = _graph_get(token, f"/drives/{drive_id}/root:/{candidate}",
                              params={"$select": "id,name,webUrl"})
            return candidate, meta.get("id")
        except Exception:
            continue
    return None, None


def _format_drive_items(value: list) -> list:
    items = []
    for f in value:
        ext = f.get("name", "").rsplit(".", 1)[-1].lower() if "." in f.get("name", "") else ""
        is_folder = "folder" in f
        items.append({
            "nom": f.get("name"),
            "type": "dossier" if is_folder else "fichier",
            "extension": ext,
            "taille_ko": round(f.get("size", 0) / 1024, 1) if f.get("size") else 0,
            "modifié": f.get("lastModifiedDateTime", "")[:10],
            "lien": f.get("webUrl", ""),
            "id": f.get("id"),
        })
    return items


# ─────────────────────────────────────────
# ONEDRIVE — ACTIONS DRIVE
# ─────────────────────────────────────────

def list_aria_drive(token: str, subfolder: str = "") -> dict:
    """
    Liste les fichiers dans 1_Photovoltaïque.
    subfolder peut être : vide, un nom de sous-dossier, ou un item_id direct (>20 chars).
    """
    try:
        _, drive_id, all_drives = _find_sharepoint_site_and_drive(token)

        if not drive_id:
            try:
                data = _graph_get(token, f"/me/drive/root:/{ONEDRIVE_FOLDER_NAME}:/children", params={
                    "$top": 100, "$select": "name,id,size,folder,file,lastModifiedDateTime,webUrl", "$orderby": "name"
                })
                items = _format_drive_items(data.get("value", []))
                return {"status": "ok", "source": "OneDrive", "dossier": ONEDRIVE_FOLDER_NAME, "count": len(items), "items": items}
            except Exception:
                return {"status": "error", "message": f"Site SharePoint '{ONEDRIVE_SITE_NAME}' introuvable."}

        base_path, base_item_id = _find_folder_item_id(token, drive_id)

        if not base_item_id:
            root_data = _graph_get(token, f"/drives/{drive_id}/root/children",
                                   params={"$top": 50, "$select": "name,folder,id"})
            root_names = [f.get("name") for f in root_data.get("value", [])]
            return {
                "status": "error",
                "message": f"Dossier '{ONEDRIVE_FOLDER_NAME}' introuvable.\nRacine : {', '.join(root_names)}"
            }

        if not subfolder:
            data = _graph_get(token, f"/drives/{drive_id}/items/{base_item_id}/children", params={
                "$top": 100, "$select": "name,id,size,folder,file,lastModifiedDateTime,webUrl", "$orderby": "name"
            })
            items = _format_drive_items(data.get("value", []))
            return {
                "status": "ok", "source": f"SharePoint {ONEDRIVE_SITE_NAME}",
                "dossier": ONEDRIVE_FOLDER_NAME, "root_id": base_item_id,
                "count": len(items), "items": items
            }

        subfolder = subfolder.strip()

        # Si c'est un item_id (long, sans slash ni espace) → navigation directe
        if len(subfolder) > 20 and "/" not in subfolder and " " not in subfolder:
            data = _graph_get(token, f"/drives/{drive_id}/items/{subfolder}/children", params={
                "$top": 100, "$select": "name,id,size,folder,file,lastModifiedDateTime,webUrl", "$orderby": "name"
            })
            items = _format_drive_items(data.get("value", []))
            return {
                "status": "ok", "source": f"SharePoint {ONEDRIVE_SITE_NAME}",
                "dossier": f"(id={subfolder[:12]}…)", "dossier_id": subfolder,
                "count": len(items), "items": items
            }

        # Sous-dossier par nom : cherche dans la racine
        root_data = _graph_get(token, f"/drives/{drive_id}/items/{base_item_id}/children", params={
            "$top": 100, "$select": "name,id,folder", "$orderby": "name"
        })
        target_id = None
        target_name = subfolder
        for item in root_data.get("value", []):
            if "folder" in item and item.get("name", "").lower() == subfolder.lower():
                target_id = item.get("id")
                target_name = item.get("name", subfolder)
                break

        if not target_id:
            return {"status": "error", "message": f"Sous-dossier '{subfolder}' introuvable. Utilise l'id du LISTDRIVE précédent."}

        data = _graph_get(token, f"/drives/{drive_id}/items/{target_id}/children", params={
            "$top": 100, "$select": "name,id,size,folder,file,lastModifiedDateTime,webUrl", "$orderby": "name"
        })
        items = _format_drive_items(data.get("value", []))
        return {
            "status": "ok", "source": f"SharePoint {ONEDRIVE_SITE_NAME}",
            "dossier": target_name, "dossier_id": target_id,
            "count": len(items), "items": items
        }

    except Exception as e:
        return {"status": "error", "message": f"Erreur Drive : {str(e)[:300]}"}


def create_drive_folder(token: str, parent_item_id: str, folder_name: str, drive_id: str | None = None) -> dict:
    """Crée un dossier dans le SharePoint par ID du parent."""
    try:
        if not drive_id:
            _, drive_id, _ = _find_sharepoint_site_and_drive(token)
        if not drive_id:
            return {"status": "error", "message": "Drive SharePoint introuvable."}
        result = _graph_post(token, f"/drives/{drive_id}/items/{parent_item_id}/children", {
            "name": folder_name,
            "folder": {},
            "@microsoft.graph.conflictBehavior": "rename"
        })
        return {
            "status": "ok",
            "message": f"Dossier '{folder_name}' créé.",
            "id": result.get("id"),
            "lien": result.get("webUrl", ""),
        }
    except Exception as e:
        return {"status": "error", "message": f"Création dossier impossible : {str(e)[:200]}"}


def move_drive_item(token: str, item_id: str, dest_folder_id: str, new_name: str | None = None, drive_id: str | None = None) -> dict:
    """
    Déplace un item vers un nouveau dossier (sans copie — le fichier original change de place).
    Optionnellement renomme l'item au passage.
    """
    try:
        if not drive_id:
            _, drive_id, _ = _find_sharepoint_site_and_drive(token)
        if not drive_id:
            return {"status": "error", "message": "Drive SharePoint introuvable."}
        body: dict = {"parentReference": {"driveId": drive_id, "id": dest_folder_id}}
        if new_name:
            body["name"] = new_name
        result = _graph_patch(token, f"/drives/{drive_id}/items/{item_id}", body)
        label = new_name or result.get("name", item_id[:8])
        return {
            "status": "ok",
            "message": f"'{label}' déplacé avec succès.",
            "id": result.get("id", item_id),
            "new_parent_id": dest_folder_id,
        }
    except Exception as e:
        return {"status": "error", "message": f"Déplacement impossible : {str(e)[:200]}"}


def copy_drive_item(token: str, item_id: str, dest_folder_id: str, new_name: str | None = None, drive_id: str | None = None) -> dict:
    """Copie un fichier/dossier vers un dossier destination (asynchrone)."""
    try:
        if not drive_id:
            _, drive_id, _ = _find_sharepoint_site_and_drive(token)
        if not drive_id:
            return {"status": "error", "message": "Drive SharePoint introuvable."}

        body = {"parentReference": {"driveId": drive_id, "id": dest_folder_id}}
        if new_name:
            body["name"] = new_name

        resp = requests.post(
            f"{GRAPH_BASE_URL}/drives/{drive_id}/items/{item_id}/copy",
            headers=_headers(token),
            json=body,
            timeout=30
        )
        if resp.status_code in (202, 200):
            return {
                "status": "ok",
                "message": f"Copie lancée{' → ' + new_name if new_name else ''}.",
                "async": resp.status_code == 202,
                "monitor_url": resp.headers.get("Location", ""),
            }
        resp.raise_for_status()
        return {"status": "ok", "message": "Copie effectuée."}
    except Exception as e:
        return {"status": "error", "message": f"Copie impossible : {str(e)[:200]}"}


def search_aria_drive(token: str, query: str) -> dict:
    """Recherche dans 1_Photovoltaïque par nom de fichier."""
    try:
        _, drive_id, _ = _find_sharepoint_site_and_drive(token)
        base_path, base_item_id = _find_folder_item_id(token, drive_id) if drive_id else (None, None)
        q_safe = query.replace("'", "''")

        if drive_id and base_item_id:
            data = _graph_get(token,
                f"/drives/{drive_id}/items/{base_item_id}/search(q='{q_safe}')",
                params={"$top": 20, "$select": "name,id,size,folder,file,lastModifiedDateTime,webUrl,parentReference"}
            )
            items = []
            for f in data.get("value", []):
                parent = f.get("parentReference", {}).get("name", "")
                items.append({
                    "nom": f.get("name"),
                    "type": "dossier" if "folder" in f else "fichier",
                    "dossier_parent": parent,
                    "id": f.get("id"),
                    "modifié": f.get("lastModifiedDateTime", "")[:10],
                    "lien": f.get("webUrl", ""),
                })
            return {"status": "ok", "source": f"SharePoint {ONEDRIVE_SITE_NAME}", "recherche": query, "count": len(items), "items": items}

        return {"status": "error", "message": "Drive SharePoint introuvable pour la recherche."}
    except Exception as e:
        return {"status": "error", "message": f"Recherche impossible : {str(e)[:300]}"}


def read_aria_drive_file(token: str, file_path_or_id: str) -> dict:
    """Lit le contenu d'un fichier (par chemin ou item_id)."""
    try:
        _, drive_id, _ = _find_sharepoint_site_and_drive(token)
        base_path, base_item_id = _find_folder_item_id(token, drive_id) if drive_id else (None, None)

        file_ref = file_path_or_id.strip()
        meta = None
        content_url = None

        if drive_id and len(file_ref) > 20 and "/" not in file_ref and " " not in file_ref:
            meta = _graph_get(token, f"/drives/{drive_id}/items/{file_ref}",
                              params={"$select": "id,name,size,webUrl,file"})
            content_url = f"{GRAPH_BASE_URL}/drives/{drive_id}/items/{file_ref}/content"
        elif drive_id and base_path:
            sub = file_ref.replace("\\", "/").strip("/")
            for prefix in [base_path, ONEDRIVE_FOLDER_NAME, "Documents"]:
                if sub.lower().startswith(prefix.lower() + "/"):
                    sub = sub[len(prefix)+1:]
                    break
            try:
                target = f"{base_path}/{sub}"
                meta = _graph_get(token, f"/drives/{drive_id}/root:/{target}",
                                  params={"$select": "id,name,size,webUrl,file"})
                content_url = f"{GRAPH_BASE_URL}/drives/{drive_id}/root:/{target}:/content"
            except Exception:
                pass

        if meta is None:
            return {"status": "error", "message": f"Fichier '{file_ref[:50]}' introuvable."}

        name = meta.get("name", "")
        size = meta.get("size", 0)
        web_url = meta.get("webUrl", "")
        ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""

        if ext in {"txt", "md", "csv", "json", "xml", "log"}:
            resp = requests.get(content_url, headers={"Authorization": f"Bearer {token}"}, timeout=30)
            resp.raise_for_status()
            return {"status": "ok", "fichier": name, "id": meta.get("id"), "type": "texte", "contenu": resp.text[:5000], "lien": web_url}

        if ext in {"docx", "doc"}:
            return {"status": "ok", "fichier": name, "id": meta.get("id"), "type": "word",
                    "taille_ko": round(size/1024, 1), "lien": web_url, "conseil": "Joins via 📎 pour que je l'analyse."}

        if ext in {"xlsx", "xls", "xlsm", "ods"}:
            return {"status": "ok", "fichier": name, "id": meta.get("id"), "type": "tableur",
                    "taille_ko": round(size/1024, 1), "lien": web_url, "conseil": "Joins via 📎 pour que je l'analyse."}

        if ext == "pdf":
            return {"status": "ok", "fichier": name, "id": meta.get("id"), "type": "pdf",
                    "taille_ko": round(size/1024, 1), "lien": web_url, "conseil": "Joins via 📎 pour que je l'analyse."}

        return {"status": "ok", "fichier": name, "id": meta.get("id"), "type": ext or "inconnu",
                "taille_ko": round(size/1024, 1), "lien": web_url}

    except Exception as e:
        return {"status": "error", "message": f"Lecture impossible : {str(e)[:300]}"}


# ─────────────────────────────────────────
# DISPATCHER PRINCIPAL
# ─────────────────────────────────────────

def perform_outlook_action(action: str, params: dict, token: str) -> dict:

    # ── Drive SharePoint ──
    if action == "list_aria_drive":
        return list_aria_drive(token, params.get("subfolder", ""))

    if action == "list_drive_by_id":
        item_id = params.get("item_id", "")
        _, drive_id, _ = _find_sharepoint_site_and_drive(token)
        if not drive_id:
            return {"status": "error", "message": "Drive introuvable."}
        try:
            data = _graph_get(token, f"/drives/{drive_id}/items/{item_id}/children", params={
                "$top": 100, "$select": "name,id,size,folder,file,lastModifiedDateTime,webUrl", "$orderby": "name"
            })
            items = _format_drive_items(data.get("value", []))
            return {"status": "ok", "count": len(items), "items": items}
        except Exception as e:
            return {"status": "error", "message": str(e)[:200]}

    if action == "read_aria_drive_file":
        return read_aria_drive_file(token, params.get("file_path", "") or params.get("item_id", ""))

    if action == "search_aria_drive":
        return search_aria_drive(token, params.get("query", ""))

    if action == "create_drive_folder":
        _, drive_id, _ = _find_sharepoint_site_and_drive(token)
        return create_drive_folder(token, params.get("parent_item_id", ""), params.get("folder_name", ""), drive_id)

    if action == "move_drive_item":
        _, drive_id, _ = _find_sharepoint_site_and_drive(token)
        return move_drive_item(token, params.get("item_id", ""), params.get("dest_folder_id", ""), params.get("new_name"), drive_id)

    if action == "copy_drive_item":
        _, drive_id, _ = _find_sharepoint_site_and_drive(token)
        return copy_drive_item(token, params.get("item_id", ""), params.get("dest_folder_id", ""), params.get("new_name"), drive_id)

    # ── Mails ──
    if action == "list_unread_messages":
        top = params.get("top", 10)
        data = _graph_get(token, "/me/mailFolders/inbox/messages",
            params={"$top": top, "$filter": "isRead eq false", "$orderby": "receivedDateTime DESC",
                    "$select": "id,subject,from,receivedDateTime,isRead,bodyPreview"})
        return {"status": "ok", "action": action, "count": len(data.get("value", [])), "items": data.get("value", [])}

    if action == "get_message_body":
        message_id = params["message_id"]
        data = _graph_get(token, f"/me/messages/{message_id}",
            params={"$select": "id,subject,from,receivedDateTime,body,bodyPreview,toRecipients"})
        body_content = data.get("body", {}).get("content", "")
        import re
        body_text = re.sub(r'<[^>]+>', ' ', body_content)
        body_text = re.sub(r'\s+', ' ', body_text).strip()
        return {"status": "ok", "action": action, "message_id": message_id,
                "subject": data.get("subject", ""),
                "from": data.get("from", {}).get("emailAddress", {}).get("address", ""),
                "body_text": body_text[:3000], "body_preview": data.get("bodyPreview", "")}

    if action == "create_reply_draft":
        message_id = params["message_id"]
        reply_body = params.get("reply_body", "")
        draft = _graph_post(token, f"/me/messages/{message_id}/createReply", {})
        draft_id = draft.get("id")
        if not draft_id:
            return {"status": "error", "message": "Impossible de créer le brouillon."}
        _graph_patch(token, f"/me/messages/{draft_id}",
            {"body": {"contentType": "HTML", "content": _build_email_html(reply_body)}})
        return {"status": "ok", "action": action, "draft_id": draft_id, "message": "Brouillon créé."}

    if action == "mark_as_read":
        _graph_patch(token, f"/me/messages/{params['message_id']}", {"isRead": True})
        return {"status": "ok", "action": action, "message": "Mail marqué comme lu."}

    if action == "move_message":
        message_id = params["message_id"]
        moved = _graph_post(token, f"/me/messages/{message_id}/move",
            {"destinationId": params["destination_folder_id"]})
        return {"status": "ok", "action": action, "new_message_id": moved.get("id"), "message": "Mail déplacé."}

    if action == "delete_message":
        message_id = params["message_id"]
        try:
            moved = _graph_post(token, f"/me/messages/{message_id}/move", {"destinationId": "deleteditems"})
            return {"status": "ok", "action": action, "new_message_id": moved.get("id"), "message": "Mail mis à la corbeille (récupérable)."}
        except Exception as e:
            return {"status": "error", "action": action, "message": f"Échec : {str(e)}"}

    if action == "delete_message_permanent":
        return {"status": "error", "action": action, "message": "Suppression définitive désactivée."}

    if action == "archive_message":
        message_id = params["message_id"]
        try:
            moved = _graph_post(token, f"/me/messages/{message_id}/move", {"destinationId": ARCHIVE_FOLDER_ID})
            return {"status": "ok", "action": action, "new_message_id": moved.get("id"), "message": "Mail archivé."}
        except Exception as e:
            return {"status": "error", "action": action, "message": f"Échec archivage : {str(e)}"}

    if action == "send_reply":
        message_id = params["message_id"]
        reply_body = params.get("reply_body", "")
        try:
            _graph_post(token, f"/me/messages/{message_id}/reply",
                {"message": {"body": {"contentType": "HTML", "content": _build_email_html(reply_body)}}})
            return {"status": "ok", "action": action, "message": "Réponse envoyée avec succès."}
        except Exception as e:
            return {"status": "error", "action": action, "message": f"Échec envoi : {str(e)}"}

    if action == "send_new_mail":
        to_email = params["to_email"]
        subject = params["subject"]
        body = params.get("body", "")
        try:
            _graph_post(token, "/me/sendMail",
                {"message": {"subject": subject,
                    "body": {"contentType": "HTML", "content": _build_email_html(body)},
                    "toRecipients": [{"emailAddress": {"address": to_email}}]}})
            return {"status": "ok", "action": action, "message": f"Mail envoyé à {to_email}."}
        except Exception as e:
            return {"status": "error", "action": action, "message": f"Échec envoi : {str(e)}"}

    # ── Calendrier ──
    if action == "list_calendar_events":
        from datetime import datetime, timezone, timedelta
        start = params.get("start", datetime.now(timezone.utc).isoformat())
        end = params.get("end", (datetime.now(timezone.utc) + timedelta(days=7)).isoformat())
        data = _graph_get(token, "/me/calendarView", params={
            "startDateTime": start, "endDateTime": end,
            "$select": "id,subject,start,end,location,organizer,attendees,bodyPreview",
            "$orderby": "start/dateTime", "$top": params.get("top", 20)})
        return {"status": "ok", "action": action, "count": len(data.get("value", [])), "items": data.get("value", [])}

    if action == "create_calendar_event":
        try:
            event = _graph_post(token, "/me/events", {
                "subject": params.get("subject", "Nouveau RDV"),
                "start": {"dateTime": params.get("start"), "timeZone": "Europe/Paris"},
                "end": {"dateTime": params.get("end"), "timeZone": "Europe/Paris"},
                "body": {"contentType": "Text", "content": params.get("body", "")},
                "attendees": [{"emailAddress": {"address": e}, "type": "required"} for e in params.get("attendees", [])]
            })
            return {"status": "ok", "action": action, "event_id": event.get("id"), "message": "RDV créé."}
        except Exception as e:
            return {"status": "error", "action": action, "message": f"Échec RDV : {str(e)}"}

    if action == "update_calendar_event":
        event_id = params["event_id"]
        update_body = {}
        if "subject" in params: update_body["subject"] = params["subject"]
        if "start" in params: update_body["start"] = {"dateTime": params["start"], "timeZone": "Europe/Paris"}
        if "end" in params: update_body["end"] = {"dateTime": params["end"], "timeZone": "Europe/Paris"}
        if "body" in params: update_body["body"] = {"contentType": "Text", "content": params["body"]}
        try:
            _graph_patch(token, f"/me/events/{event_id}", update_body)
            return {"status": "ok", "action": action, "message": "RDV mis à jour."}
        except Exception as e:
            return {"status": "error", "action": action, "message": f"Échec : {str(e)}"}

    if action == "delete_calendar_event":
        success = _graph_delete(token, f"/me/events/{params['event_id']}")
        return {"status": "ok" if success else "error", "message": "RDV supprimé." if success else "Échec."}

    # ── Teams ──
    if action == "list_teams_chats":
        data = _graph_get(token, "/me/chats", params={"$expand": "members", "$top": 20})
        return {"status": "ok", "action": action, "items": data.get("value", [])}

    if action == "send_teams_message":
        try:
            _graph_post(token, f"/me/chats/{params['chat_id']}/messages", {"body": {"content": params["message"]}})
            return {"status": "ok", "action": action, "message": "Message Teams envoyé."}
        except Exception as e:
            return {"status": "error", "action": action, "message": f"Échec Teams : {str(e)}"}

    if action == "get_teams_chat_messages":
        data = _graph_get(token, f"/me/chats/{params['chat_id']}/messages", params={"$top": params.get("top", 20)})
        return {"status": "ok", "action": action, "items": data.get("value", [])}

    if action == "find_teams_user":
        name_safe = params["name"].replace("'", "''")
        data = _graph_get(token, "/users", params={"$filter": f"startswith(displayName,'{name_safe}')", "$select": "id,displayName,mail"})
        return {"status": "ok", "action": action, "items": data.get("value", [])}

    # ── Contacts ──
    if action == "list_contacts":
        data = _graph_get(token, "/me/contacts", params={"$top": 50, "$select": "displayName,emailAddresses,mobilePhone,businessPhones,companyName,jobTitle"})
        return {"status": "ok", "action": action, "items": data.get("value", [])}

    if action == "search_contacts":
        query_safe = params["query"].replace("'", "''")
        data = _graph_get(token, "/me/contacts", params={
            "$filter": f"startswith(displayName,'{query_safe}')",
            "$select": "displayName,emailAddresses,mobilePhone,businessPhones,companyName", "$top": 10})
        return {"status": "ok", "action": action, "items": data.get("value", [])}

    # ── Tâches ──
    if action == "list_todo_tasks":
        lists_data = _graph_get(token, "/me/todo/lists")
        all_tasks = []
        for lst in lists_data.get("value", [])[:3]:
            tasks_data = _graph_get(token, f"/me/todo/lists/{lst['id']}/tasks", params={"$top": 20})
            for task in tasks_data.get("value", []):
                task["listName"] = lst.get("displayName")
                all_tasks.append(task)
        return {"status": "ok", "action": action, "items": all_tasks}

    if action == "create_todo_task":
        lists_data = _graph_get(token, "/me/todo/lists")
        if not lists_data.get("value"):
            return {"status": "error", "message": "Aucune liste trouvée."}
        list_id = lists_data["value"][0]["id"]
        task_body = {"title": params["title"]}
        if "due" in params:
            task_body["dueDateTime"] = {"dateTime": params["due"], "timeZone": "Europe/Paris"}
        try:
            _graph_post(token, f"/me/todo/lists/{list_id}/tasks", task_body)
            return {"status": "ok", "action": action, "message": f"Tâche '{params['title']}' créée."}
        except Exception as e:
            return {"status": "error", "action": action, "message": f"Échec : {str(e)}"}

    return {"status": "error", "action": action, "message": f"Action inconnue : {action}"}
