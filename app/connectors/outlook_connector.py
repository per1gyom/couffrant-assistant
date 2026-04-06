import requests

GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"

# ID du dossier Archive de Guillaume
ARCHIVE_FOLDER_ID = "AQMkAGEwZmJhNTllLWQ3MjUtNDg4ADQtYjdhMi1jMGEyZjRiNmFkNWEALgAAA-6yBmE1L7hGi--BXSl5S2sBAIyf8uOKE0VAkKv1dN8K6xgAAAIBRQAAAA=="


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


def perform_outlook_action(action: str, params: dict, token: str) -> dict:

    # --- MAILS ---

    if action == "list_unread_messages":
        top = params.get("top", 10)
        data = _graph_get(
            token,
            "/me/mailFolders/inbox/messages",
            params={
                "$top": top,
                "$filter": "isRead eq false",
                "$orderby": "receivedDateTime DESC",
                "$select": "id,subject,from,receivedDateTime,isRead,bodyPreview",
            },
        )
        return {
            "status": "ok",
            "action": action,
            "count": len(data.get("value", [])),
            "items": data.get("value", []),
        }

    if action == "get_message_body":
        message_id = params["message_id"]
        data = _graph_get(
            token,
            f"/me/messages/{message_id}",
            params={"$select": "id,subject,from,receivedDateTime,body,bodyPreview,toRecipients"},
        )
        body_content = data.get("body", {}).get("content", "")
        import re
        body_text = re.sub(r'<[^>]+>', ' ', body_content)
        body_text = re.sub(r'\s+', ' ', body_text).strip()
        return {
            "status": "ok",
            "action": action,
            "message_id": message_id,
            "subject": data.get("subject", ""),
            "from": data.get("from", {}).get("emailAddress", {}).get("address", ""),
            "body_text": body_text[:3000],
            "body_preview": data.get("bodyPreview", ""),
        }

    if action == "create_reply_draft":
        message_id = params["message_id"]
        reply_body = params.get("reply_body", "")
        draft = _graph_post(token, f"/me/messages/{message_id}/createReply", {})
        draft_id = draft.get("id")
        if not draft_id:
            return {"status": "error", "message": "Impossible de créer le brouillon Outlook."}
        patch_body = {"body": {"contentType": "HTML", "content": reply_body}}
        if params.get("subject_override"):
            patch_body["subject"] = params["subject_override"]
        _graph_patch(token, f"/me/messages/{draft_id}", patch_body)
        return {"status": "ok", "action": action, "draft_id": draft_id, "message": "Brouillon créé."}

    if action == "mark_as_read":
        message_id = params["message_id"]
        _graph_patch(token, f"/me/messages/{message_id}", {"isRead": True})
        return {"status": "ok", "action": action, "message": "Mail marqué comme lu."}

    if action == "move_message":
        message_id = params["message_id"]
        moved = _graph_post(
            token,
            f"/me/messages/{message_id}/move",
            {"destinationId": params["destination_folder_id"]},
        )
        return {"status": "ok", "action": action, "new_message_id": moved.get("id"), "message": "Mail déplacé."}

    if action == "delete_message":
        # Déplace vers la corbeille (Deleted Items) — récupérable
        message_id = params["message_id"]
        try:
            moved = _graph_post(
                token,
                f"/me/messages/{message_id}/move",
                {"destinationId": "deleteditems"},
            )
            return {
                "status": "ok",
                "action": action,
                "new_message_id": moved.get("id"),
                "message": "Mail déplacé vers la corbeille (récupérable).",
            }
        except Exception as e:
            return {"status": "error", "action": action, "message": f"Échec : {str(e)}"}

    if action == "delete_message_permanent":
        # Suppression définitive — utiliser avec précaution
        message_id = params["message_id"]
        success = _graph_delete(token, f"/me/messages/{message_id}")
        return {
            "status": "ok" if success else "error",
            "action": action,
            "message": "Mail supprimé définitivement." if success else "Échec suppression.",
        }

    if action == "archive_message":
        message_id = params["message_id"]
        try:
            moved = _graph_post(
                token,
                f"/me/messages/{message_id}/move",
                {"destinationId": ARCHIVE_FOLDER_ID},
            )
            return {
                "status": "ok",
                "action": action,
                "new_message_id": moved.get("id"),
                "message": "Mail archivé.",
            }
        except Exception as e:
            return {"status": "error", "action": action, "message": f"Échec archivage : {str(e)}"}

    if action == "send_reply":
        message_id = params["message_id"]
        reply_body = params.get("reply_body", "")
        html_body = f"""
<div style="font-family:Arial, sans-serif; font-size:14px; color:#222;">
    <div style="white-space:pre-line;">{reply_body}</div>
    <br><br>
    <div>Solairement,</div>
    <div style="font-weight:bold; margin-top:8px;">Guillaume Perrin</div>
    <div>06 49 43 09 17</div>
    <div><a href="https://www.couffrant-solar.fr">www.couffrant-solar.fr</a></div>
</div>"""
        try:
            _graph_post(
                token,
                f"/me/messages/{message_id}/reply",
                {"message": {"body": {"contentType": "HTML", "content": html_body}}}
            )
            return {"status": "ok", "action": action, "message": "Réponse envoyée avec succès."}
        except Exception as e:
            return {"status": "error", "action": action, "message": f"Échec envoi : {str(e)}"}

    if action == "send_new_mail":
        to_email = params["to_email"]
        subject = params["subject"]
        body = params.get("body", "")
        html_body = f"""
<div style="font-family:Arial, sans-serif; font-size:14px; color:#222;">
    <div style="white-space:pre-line;">{body}</div>
    <br><br>
    <div>Solairement,</div>
    <div style="font-weight:bold; margin-top:8px;">Guillaume Perrin</div>
    <div>06 49 43 09 17</div>
    <div><a href="https://www.couffrant-solar.fr">www.couffrant-solar.fr</a></div>
</div>"""
        try:
            _graph_post(
                token,
                "/me/sendMail",
                {
                    "message": {
                        "subject": subject,
                        "body": {"contentType": "HTML", "content": html_body},
                        "toRecipients": [{"emailAddress": {"address": to_email}}]
                    }
                }
            )
            return {"status": "ok", "action": action, "message": f"Mail envoyé à {to_email}."}
        except Exception as e:
            return {"status": "error", "action": action, "message": f"Échec envoi : {str(e)}"}

    # --- AGENDA ---

    if action == "list_calendar_events":
        from datetime import datetime, timezone, timedelta
        start = params.get("start", datetime.now(timezone.utc).isoformat())
        end = params.get("end", (datetime.now(timezone.utc) + timedelta(days=7)).isoformat())
        data = _graph_get(
            token,
            "/me/calendarView",
            params={
                "startDateTime": start,
                "endDateTime": end,
                "$select": "id,subject,start,end,location,organizer,attendees,bodyPreview",
                "$orderby": "start/dateTime",
                "$top": params.get("top", 20),
            }
        )
        return {"status": "ok", "action": action, "count": len(data.get("value", [])), "items": data.get("value", [])}

    if action == "create_calendar_event":
        try:
            event = _graph_post(
                token,
                "/me/events",
                {
                    "subject": params.get("subject", "Nouveau RDV"),
                    "start": {"dateTime": params.get("start"), "timeZone": "Europe/Paris"},
                    "end": {"dateTime": params.get("end"), "timeZone": "Europe/Paris"},
                    "body": {"contentType": "Text", "content": params.get("body", "")},
                    "attendees": [
                        {"emailAddress": {"address": email}, "type": "required"}
                        for email in params.get("attendees", [])
                    ]
                }
            )
            return {"status": "ok", "action": action, "event_id": event.get("id"), "message": f"RDV '{params.get('subject')}' créé."}
        except Exception as e:
            return {"status": "error", "action": action, "message": f"Échec création RDV : {str(e)}"}

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

    # --- TEAMS ---

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
        data = _graph_get(token, "/users", params={"$filter": f"startswith(displayName,'{name}')", "$select": "id,displayName,mail"})
        return {"status": "ok", "action": action, "items": data.get("value", [])}

    # --- ONEDRIVE ---

    if action == "list_onedrive_files":
        path = params.get("path", "root")
        endpoint = "/me/drive/root/children" if path == "root" else f"/me/drive/root:/{path}:/children"
        data = _graph_get(token, endpoint, params={"$top": 50})
        return {
            "status": "ok", "action": action,
            "items": [{"name": f.get("name"), "id": f.get("id"), "size": f.get("size"),
                       "type": "folder" if "folder" in f else "file",
                       "modified": f.get("lastModifiedDateTime"), "webUrl": f.get("webUrl")}
                      for f in data.get("value", [])]
        }

    if action == "move_onedrive_file":
        file_id = params["file_id"]
        body = {"parentReference": {"id": params["new_parent_id"]}}
        if params.get("new_name"): body["name"] = params["new_name"]
        try:
            _graph_patch(token, f"/me/drive/items/{file_id}", body)
            return {"status": "ok", "action": action, "message": "Fichier déplacé."}
        except Exception as e:
            return {"status": "error", "action": action, "message": f"Échec : {str(e)}"}

    if action == "create_onedrive_folder":
        parent_path = params.get("parent_path", "root")
        folder_name = params["folder_name"]
        endpoint = "/me/drive/root/children" if parent_path == "root" else f"/me/drive/root:/{parent_path}:/children"
        try:
            _graph_post(token, endpoint, {"name": folder_name, "folder": {}, "@microsoft.graph.conflictBehavior": "rename"})
            return {"status": "ok", "action": action, "message": f"Dossier '{folder_name}' créé."}
        except Exception as e:
            return {"status": "error", "action": action, "message": f"Échec : {str(e)}"}

    if action == "delete_onedrive_file":
        file_id = params["file_id"]
        success = _graph_delete(token, f"/me/drive/items/{file_id}")
        return {"status": "ok" if success else "error", "message": "Fichier supprimé." if success else "Échec."}

    # --- CONTACTS ---

    if action == "list_contacts":
        data = _graph_get(token, "/me/contacts", params={"$top": 50, "$select": "displayName,emailAddresses,mobilePhone,businessPhones,companyName,jobTitle"})
        return {"status": "ok", "action": action, "items": data.get("value", [])}

    if action == "search_contacts":
        query = params["query"]
        data = _graph_get(token, "/me/contacts", params={
            "$filter": f"startswith(displayName,'{query}')",
            "$select": "displayName,emailAddresses,mobilePhone,businessPhones,companyName",
            "$top": 10
        })
        return {"status": "ok", "action": action, "items": data.get("value", [])}

    # --- TACHES ---

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
