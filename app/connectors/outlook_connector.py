import requests

GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"

ARCHIVE_FOLDER_ID = "AQMkAGEwZmJhNTllLWQ3MjUtNDg4ADQtYjdhMi1jMGEyZjRiNmFkNWEALgAAA-6yBmE1L7hGi--BXSl5S2sBAIyf8uOKE0VAkKv1dN8K6xgAAAIBRQAAAA=="

# Dossier OneDrive autorisé — Aria ne peut pas sortir de ce périmètre
ONEDRIVE_ARIA_ROOT = "1_photovoltaïque"

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
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }


def _graph_get(token: str, path: str, params: dict | None = None) -> dict:
    response = requests.get(
        f"{GRAPH_BASE_URL}{path}",
        headers=_headers(token),
        params=params,
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def _graph_post(token: str, path: str, json_body: dict | None = None) -> dict:
    response = requests.post(
        f"{GRAPH_BASE_URL}{path}",
        headers=_headers(token),
        json=json_body or {},
        timeout=30,
    )
    response.raise_for_status()
    if response.text.strip():
        return response.json()
    return {}


def _graph_patch(token: str, path: str, json_body: dict) -> dict:
    response = requests.patch(
        f"{GRAPH_BASE_URL}{path}",
        headers=_headers(token),
        json=json_body,
        timeout=30,
    )
    response.raise_for_status()
    if response.text.strip():
        return response.json()
    return {}


def _graph_delete(token: str, path: str) -> bool:
    response = requests.delete(
        f"{GRAPH_BASE_URL}{path}",
        headers=_headers(token),
        timeout=30,
    )
    return response.status_code == 204


def _build_email_html(body: str) -> str:
    """Construit le HTML complet d'un mail avec la signature Couffrant Solar."""
    return f"""<div style="font-family:Arial, sans-serif; font-size:14px; color:#222;">
    <div style="white-space:pre-line;">{body}</div>
    {SIGNATURE_HTML}
</div>"""


def _safe_drive_path(path: str) -> str:
    """
    Sécurise le chemin OneDrive — force le préfixe ONEDRIVE_ARIA_ROOT.
    Empêche toute sortie du dossier autorisé.
    """
    path = path.replace("\\", "/").strip("/")
    if path.startswith(ONEDRIVE_ARIA_ROOT):
        path = path[len(ONEDRIVE_ARIA_ROOT):].strip("/")
    parts = [p for p in path.split("/") if p and p != ".."]
    if parts:
        return f"{ONEDRIVE_ARIA_ROOT}/{'/'.join(parts)}"
    return ONEDRIVE_ARIA_ROOT


def _list_root_drive(token: str) -> list:
    """Liste les dossiers à la racine du OneDrive — utile pour diagnostiquer un 404."""
    try:
        data = _graph_get(token, "/me/drive/root/children", params={
            "$top": 50,
            "$select": "name,folder,lastModifiedDateTime",
            "$orderby": "name"
        })
        return [
            {"nom": f.get("name"), "type": "📁 dossier" if "folder" in f else "📄 fichier"}
            for f in data.get("value", [])
        ]
    except Exception:
        return []


# ─────────────────────────────────────────
# ONEDRIVE — ACTIONS RESTREINTES
# ─────────────────────────────────────────

def list_aria_drive(token: str, subfolder: str = "") -> dict:
    """Liste les fichiers dans le dossier OneDrive autorisé (ou un sous-dossier)."""
    try:
        full_path = _safe_drive_path(subfolder) if subfolder else ONEDRIVE_ARIA_ROOT
        endpoint = f"/me/drive/root:/{full_path}:/children"
        try:
            data = _graph_get(token, endpoint, params={
                "$top": 100,
                "$select": "name,id,size,folder,file,lastModifiedDateTime,webUrl",
                "$orderby": "name"
            })
        except Exception as e:
            # Si le dossier est introuvable (404), liste la racine pour aider Guillaume
            if "404" in str(e) or "Not Found" in str(e) or "itemNotFound" in str(e):
                root_items = _list_root_drive(token)
                dossiers = [it["nom"] for it in root_items if "dossier" in it["type"]]
                fichiers = [it["nom"] for it in root_items if "fichier" in it["type"]]
                msg = f"Le dossier '{full_path}' est introuvable sur votre OneDrive."
                if dossiers:
                    msg += f"\n\nDossiers disponibles à la racine : {', '.join(dossiers)}"
                if fichiers:
                    msg += f"\nFichiers à la racine : {', '.join(fichiers[:10])}"
                msg += "\n\nDites-moi le nom exact du dossier à utiliser."
                return {"status": "error", "message": msg}
            raise

        items = []
        for f in data.get("value", []):
            item_type = "📁 dossier" if "folder" in f else "📄 fichier"
            ext = f.get("name", "").rsplit(".", 1)[-1].lower() if "." in f.get("name", "") else ""
            items.append({
                "nom": f.get("name"),
                "type": item_type,
                "extension": ext,
                "taille_ko": round(f.get("size", 0) / 1024, 1) if f.get("size") else 0,
                "modifié": f.get("lastModifiedDateTime", "")[:10],
                "lien": f.get("webUrl", ""),
                "id": f.get("id"),
            })
        return {
            "status": "ok",
            "dossier": full_path,
            "count": len(items),
            "items": items
        }
    except Exception as e:
        return {"status": "error", "message": f"Erreur Drive : {str(e)[:300]}"}


def read_aria_drive_file(token: str, file_path: str) -> dict:
    """Lit le contenu d'un fichier dans le dossier autorisé."""
    try:
        full_path = _safe_drive_path(file_path)
        meta = _graph_get(token, f"/me/drive/root:/{full_path}")
        name = meta.get("name", "")
        size = meta.get("size", 0)
        web_url = meta.get("webUrl", "")
        ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""

        text_types = {"txt", "md", "csv", "json", "xml", "log", "py", "js", "html", "htm", "css"}
        if ext in text_types:
            content_resp = requests.get(
                f"{GRAPH_BASE_URL}/me/drive/root:/{full_path}:/content",
                headers={"Authorization": f"Bearer {token}"},
                timeout=30,
            )
            content_resp.raise_for_status()
            return {
                "status": "ok", "fichier": name, "chemin": full_path,
                "type": "texte", "contenu": content_resp.text[:5000], "lien": web_url,
            }

        if ext in {"docx", "doc"}:
            return {
                "status": "ok", "fichier": name, "chemin": full_path, "type": "word",
                "message": f"Document Word ({round(size/1024, 1)} Ko).",
                "lien": web_url, "conseil": "Joins ce fichier via 📎 pour que je l'analyse."
            }

        if ext in {"xlsx", "xls"}:
            try:
                preview = _graph_get(token, f"/me/drive/root:/{full_path}:/workbook/worksheets")
                sheets = [s.get("name") for s in preview.get("value", [])]
                return {
                    "status": "ok", "fichier": name, "chemin": full_path, "type": "excel",
                    "message": f"Excel avec {len(sheets)} feuille(s) : {', '.join(sheets)}",
                    "lien": web_url, "conseil": "Joins ce fichier via 📎 pour que je l'analyse."
                }
            except Exception:
                pass

        return {
            "status": "ok", "fichier": name, "chemin": full_path,
            "type": ext or "inconnu", "taille_ko": round(size / 1024, 1), "lien": web_url,
            "message": f"Fichier {ext.upper()} ({round(size/1024, 1)} Ko).",
            "conseil": "Joins ce fichier via 📎 pour que je l'analyse."
        }
    except Exception as e:
        return {"status": "error", "message": f"Impossible de lire le fichier : {str(e)[:300]}"}


def search_aria_drive(token: str, query: str) -> dict:
    """Recherche des fichiers dans le dossier autorisé par nom."""
    try:
        q_safe = query.replace("'", "''")
        try:
            data = _graph_get(
                token,
                f"/me/drive/root:/{ONEDRIVE_ARIA_ROOT}:/search(q='{q_safe}')",
                params={"$top": 20, "$select": "name,id,size,folder,file,lastModifiedDateTime,webUrl,parentReference"}
            )
        except Exception as e:
            if "404" in str(e) or "Not Found" in str(e):
                root_items = _list_root_drive(token)
                dossiers = [it["nom"] for it in root_items if "dossier" in it["type"]]
                return {
                    "status": "error",
                    "message": f"Dossier '{ONEDRIVE_ARIA_ROOT}' introuvable. Dossiers disponibles : {', '.join(dossiers) if dossiers else 'aucun'}"
                }
            raise
        items = []
        for f in data.get("value", []):
            parent_path = f.get("parentReference", {}).get("path", "")
            items.append({
                "nom": f.get("name"),
                "type": "📁 dossier" if "folder" in f else "📄 fichier",
                "chemin": parent_path.split("root:")[-1] + "/" + f.get("name", "") if "root:" in parent_path else f.get("name"),
                "modifié": f.get("lastModifiedDateTime", "")[:10],
                "lien": f.get("webUrl", ""),
            })
        return {"status": "ok", "recherche": query, "count": len(items), "items": items}
    except Exception as e:
        return {"status": "error", "message": f"Recherche impossible : {str(e)[:300]}"}


# ─────────────────────────────────────────
# DISPATCHER PRINCIPAL
# ─────────────────────────────────────────

def perform_outlook_action(action: str, params: dict, token: str) -> dict:

    if action == "list_aria_drive":
        return list_aria_drive(token, params.get("subfolder", ""))

    if action == "read_aria_drive_file":
        return read_aria_drive_file(token, params.get("file_path", ""))

    if action == "search_aria_drive":
        return search_aria_drive(token, params.get("query", ""))

    if action == "list_unread_messages":
        top = params.get("top", 10)
        data = _graph_get(
            token, "/me/mailFolders/inbox/messages",
            params={
                "$top": top, "$filter": "isRead eq false",
                "$orderby": "receivedDateTime DESC",
                "$select": "id,subject,from,receivedDateTime,isRead,bodyPreview",
            },
        )
        return {"status": "ok", "action": action, "count": len(data.get("value", [])), "items": data.get("value", [])}

    if action == "get_message_body":
        message_id = params["message_id"]
        data = _graph_get(token, f"/me/messages/{message_id}",
            params={"$select": "id,subject,from,receivedDateTime,body,bodyPreview,toRecipients"})
        body_content = data.get("body", {}).get("content", "")
        import re
        body_text = re.sub(r'<[^>]+>', ' ', body_content)
        body_text = re.sub(r'\s+', ' ', body_text).strip()
        return {
            "status": "ok", "action": action, "message_id": message_id,
            "subject": data.get("subject", ""),
            "from": data.get("from", {}).get("emailAddress", {}).get("address", ""),
            "body_text": body_text[:3000], "body_preview": data.get("bodyPreview", ""),
        }

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
        message_id = params["message_id"]
        _graph_patch(token, f"/me/messages/{message_id}", {"isRead": True})
        return {"status": "ok", "action": action, "message": "Mail marqué comme lu."}

    if action == "move_message":
        message_id = params["message_id"]
        moved = _graph_post(token, f"/me/messages/{message_id}/move", {"destinationId": params["destination_folder_id"]})
        return {"status": "ok", "action": action, "new_message_id": moved.get("id"), "message": "Mail déplacé."}

    if action == "delete_message":
        message_id = params["message_id"]
        try:
            moved = _graph_post(token, f"/me/messages/{message_id}/move", {"destinationId": "deleteditems"})
            return {"status": "ok", "action": action, "new_message_id": moved.get("id"), "message": "Mail mis à la corbeille (récupérable)."}
        except Exception as e:
            return {"status": "error", "action": action, "message": f"Échec : {str(e)}"}

    if action == "delete_message_permanent":
        return {"status": "error", "action": action,
            "message": "Suppression définitive désactivée. Utilisez delete_message."}

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

    if action == "list_calendar_events":
        from datetime import datetime, timezone, timedelta
        start = params.get("start", datetime.now(timezone.utc).isoformat())
        end = params.get("end", (datetime.now(timezone.utc) + timedelta(days=7)).isoformat())
        data = _graph_get(token, "/me/calendarView", params={
            "startDateTime": start, "endDateTime": end,
            "$select": "id,subject,start,end,location,organizer,attendees,bodyPreview",
            "$orderby": "start/dateTime", "$top": params.get("top", 20),
        })
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
        event_id = params["event_id"]
        success = _graph_delete(token, f"/me/events/{event_id}")
        return {"status": "ok" if success else "error", "message": "RDV supprimé." if success else "Échec."}

    if action == "list_teams_chats":
        data = _graph_get(token, "/me/chats", params={"$expand": "members", "$top": 20})
        return {"status": "ok", "action": action, "items": data.get("value", [])}

    if action == "send_teams_message":
        chat_id = params["chat_id"]
        message = params["message"]
        try:
            _graph_post(token, f"/me/chats/{chat_id}/messages", {"body": {"content": message}})
            return {"status": "ok", "action": action, "message": "Message Teams envoyé."}
        except Exception as e:
            return {"status": "error", "action": action, "message": f"Échec Teams : {str(e)}"}

    if action == "get_teams_chat_messages":
        chat_id = params["chat_id"]
        data = _graph_get(token, f"/me/chats/{chat_id}/messages", params={"$top": params.get("top", 20)})
        return {"status": "ok", "action": action, "items": data.get("value", [])}

    if action == "find_teams_user":
        name = params["name"]
        name_safe = name.replace("'", "''")
        data = _graph_get(token, "/users", params={"$filter": f"startswith(displayName,'{name_safe}')", "$select": "id,displayName,mail"})
        return {"status": "ok", "action": action, "items": data.get("value", [])}

    if action == "list_contacts":
        data = _graph_get(token, "/me/contacts", params={"$top": 50, "$select": "displayName,emailAddresses,mobilePhone,businessPhones,companyName,jobTitle"})
        return {"status": "ok", "action": action, "items": data.get("value", [])}

    if action == "search_contacts":
        query = params["query"]
        query_safe = query.replace("'", "''")
        data = _graph_get(token, "/me/contacts", params={
            "$filter": f"startswith(displayName,'{query_safe}')",
            "$select": "displayName,emailAddresses,mobilePhone,businessPhones,companyName", "$top": 10})
        return {"status": "ok", "action": action, "items": data.get("value", [])}

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
