"""
Actions Outlook (envoi, deplacement, suppression, reponse).
Extrait de outlook_connector.py -- SPLIT-C3.
"""
import requests
from app.logging_config import get_logger
logger=get_logger("raya.outlook")
from app.connectors.outlook_connector import _headers,_graph_get


def _graph_post(token, path, json_body=None):
    r = requests.post(f"{GRAPH_BASE_URL}{path}", headers=_headers(token), json=json_body or {}, timeout=30)
    r.raise_for_status(); return r.json() if r.text.strip() else {}


def _graph_patch(token, path, json_body):
    r = requests.patch(f"{GRAPH_BASE_URL}{path}", headers=_headers(token), json=json_body, timeout=30)
    r.raise_for_status(); return r.json() if r.text.strip() else {}


def _graph_delete(token, path):
    r = requests.delete(f"{GRAPH_BASE_URL}{path}", headers=_headers(token), timeout=30)
    return r.status_code == 204



def _build_email_html(body: str, username: str = "guillaume") -> str:
    """Corps HTML du mail avec signature. EMAIL-SIGNATURE : deleguee a get_email_signature()."""
    from app.email_signature import get_email_signature
    signature = get_email_signature(username)
    return f'<div style="font-family:Arial,sans-serif;font-size:14px;color:#222;"><div style="white-space:pre-line;">{body}</div>{signature}</div>'


# Re-exports Drive
from app.connectors.drive_connector import (
    _find_sharepoint_site_and_drive,
    list_drive as list_aria_drive,
    read_drive_file as read_aria_drive_file,
    search_drive as search_aria_drive,
    create_folder as create_drive_folder,
    move_item as move_drive_item,
    copy_item as copy_drive_item,
)



def perform_outlook_action(action: str, params: dict, token: str) -> dict:

    if action == "list_aria_drive":
        return list_aria_drive(token, params.get("subfolder", ""))

    if action == "list_drive_by_id":
        item_id = params.get("item_id", "")
        from app.connectors.drive_connector import _find_sharepoint_site_and_drive as _fspd
        _, drive_id, _ = _fspd(token)
        if not drive_id: return {"status": "error", "message": "Drive introuvable."}
        try:
            data = _graph_get(token, f"/drives/{drive_id}/items/{item_id}/children", params={
                "$top": 100, "$select": "name,id,size,folder,file,lastModifiedDateTime,webUrl", "$orderby": "name"})
            from app.connectors.drive_connector import _fmt
            return {"status": "ok", "count": len(data.get("value", [])), "items": _fmt(data.get("value", []))}
        except Exception as e: return {"status": "error", "message": str(e)[:200]}

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

    if action == "list_unread_messages":
        data = _graph_get(token, "/me/mailFolders/inbox/messages", params={
            "$top": params.get("top", 10), "$filter": "isRead eq false",
            "$orderby": "receivedDateTime DESC",
            "$select": "id,subject,from,receivedDateTime,isRead,bodyPreview"})
        return {"status": "ok", "count": len(data.get("value", [])), "items": data.get("value", [])}

    if action == "get_message_body":
        data = _graph_get(token, f"/me/messages/{params['message_id']}",
            params={"$select": "id,subject,from,receivedDateTime,body,bodyPreview,toRecipients"})
        body_text = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', data.get("body", {}).get("content", ""))).strip()
        return {"status": "ok", "message_id": params['message_id'],
                "subject": data.get("subject", ""),
                "from": data.get("from", {}).get("emailAddress", {}).get("address", ""),
                "body_text": body_text[:3000], "body_preview": data.get("bodyPreview", "")}

    if action == "mark_as_read":
        _graph_patch(token, f"/me/messages/{params['message_id']}", {"isRead": True})
        return {"status": "ok", "message": "Mail marque comme lu."}

    if action == "delete_message":
        try:
            moved = _graph_post(token, f"/me/messages/{params['message_id']}/move", {"destinationId": "deleteditems"})
            return {"status": "ok", "new_message_id": moved.get("id"), "message": "Mail mis a la corbeille."}
        except Exception as e: return {"status": "error", "message": f"Echec : {str(e)}"}

    if action == "archive_message":
        try:
            moved = _graph_post(token, f"/me/messages/{params['message_id']}/move", {"destinationId": ARCHIVE_FOLDER_ID})
            return {"status": "ok", "new_message_id": moved.get("id"), "message": "Mail archive."}
        except Exception as e: return {"status": "error", "message": f"Echec archivage : {str(e)}"}

    if action == "send_reply":
        try:
            _graph_post(token, f"/me/messages/{params['message_id']}/reply",
                {"message": {"body": {"contentType": "HTML", "content": _build_email_html(params.get("reply_body", ""))}}})
            return {"status": "ok", "message": "Reponse envoyee avec succes."}
        except Exception as e: return {"status": "error", "message": f"Echec envoi : {str(e)}"}

    if action == "send_new_mail":
        try:
            _graph_post(token, "/me/sendMail", {
                "message": {"subject": params["subject"],
                    "body": {"contentType": "HTML", "content": _build_email_html(params.get("body", ""))},
                    "toRecipients": [{"emailAddress": {"address": params["to_email"]}}]}})
            return {"status": "ok", "message": f"Mail envoye a {params['to_email']}."}
        except Exception as e: return {"status": "error", "message": f"Echec envoi : {str(e)}"}

    if action == "create_reply_draft":
        draft = _graph_post(token, f"/me/messages/{params['message_id']}/createReply", {})
        draft_id = draft.get("id")
        if not draft_id: return {"status": "error", "message": "Impossible de creer le brouillon."}
        _graph_patch(token, f"/me/messages/{draft_id}",
            {"body": {"contentType": "HTML", "content": _build_email_html(params.get("reply_body", ""))}})
        return {"status": "ok", "draft_id": draft_id, "message": "Brouillon cree."}

    if action == "move_message":
        moved = _graph_post(token, f"/me/messages/{params['message_id']}/move",
            {"destinationId": params["destination_folder_id"]})
        return {"status": "ok", "new_message_id": moved.get("id"), "message": "Mail deplace."}

    if action == "list_calendar_events":
        from datetime import datetime, timezone, timedelta
        start = params.get("start", datetime.now(timezone.utc).isoformat())
        end = params.get("end", (datetime.now(timezone.utc) + timedelta(days=7)).isoformat())
        data = _graph_get(token, "/me/calendarView", params={
            "startDateTime": start, "endDateTime": end,
            "$select": "id,subject,start,end,location,organizer,attendees,bodyPreview",
            "$orderby": "start/dateTime", "$top": params.get("top", 20)})
        return {"status": "ok", "count": len(data.get("value", [])), "items": data.get("value", [])}

    if action == "create_calendar_event":
        try:
            event = _graph_post(token, "/me/events", {
                "subject": params.get("subject", "Nouveau RDV"),
                "start": {"dateTime": params.get("start"), "timeZone": "Europe/Paris"},
                "end": {"dateTime": params.get("end"), "timeZone": "Europe/Paris"},
                "body": {"contentType": "Text", "content": params.get("body", "")},
                "attendees": [{"emailAddress": {"address": e}, "type": "required"}
                               for e in params.get("attendees", [])]})
            return {"status": "ok", "event_id": event.get("id"), "message": "RDV cree."}
        except Exception as e: return {"status": "error", "message": f"Echec RDV : {str(e)}"}

    if action == "update_calendar_event":
        body = {}
        if "subject" in params: body["subject"] = params["subject"]
        if "start" in params: body["start"] = {"dateTime": params["start"], "timeZone": "Europe/Paris"}
        if "end" in params: body["end"] = {"dateTime": params["end"], "timeZone": "Europe/Paris"}
        if "body" in params: body["body"] = {"contentType": "Text", "content": params["body"]}
        try:
            _graph_patch(token, f"/me/events/{params['event_id']}", body)
            return {"status": "ok", "message": "RDV mis a jour."}
        except Exception as e: return {"status": "error", "message": f"Echec : {str(e)}"}

    if action == "delete_calendar_event":
        ok = _graph_delete(token, f"/me/events/{params['event_id']}")
        return {"status": "ok" if ok else "error", "message": "RDV supprime." if ok else "Echec."}

    if action == "list_contacts":
        data = _graph_get(token, "/me/contacts", params={
            "$top": 50, "$select": "displayName,emailAddresses,mobilePhone,businessPhones,companyName,jobTitle"})
        return {"status": "ok", "items": data.get("value", [])}

    if action == "search_contacts":
        q = params["query"].replace("'", "''")
        data = _graph_get(token, "/me/contacts", params={
            "$filter": f"startswith(displayName,'{q}')",
            "$select": "displayName,emailAddresses,mobilePhone,businessPhones,companyName", "$top": 10})
        return {"status": "ok", "items": data.get("value", [])}

    if action == "list_todo_tasks":
        lists_data = _graph_get(token, "/me/todo/lists")
        all_tasks = []
        for lst in lists_data.get("value", [])[:3]:
            tasks = _graph_get(token, f"/me/todo/lists/{lst['id']}/tasks", params={"$top": 20})
            for task in tasks.get("value", []):
                task["listName"] = lst.get("displayName"); all_tasks.append(task)
        return {"status": "ok", "items": all_tasks}

    if action == "create_todo_task":
        lists_data = _graph_get(token, "/me/todo/lists")
        if not lists_data.get("value"): return {"status": "error", "message": "Aucune liste trouvee."}
        list_id = lists_data["value"][0]["id"]
        task_body = {"title": params["title"]}
        if "due" in params: task_body["dueDateTime"] = {"dateTime": params["due"], "timeZone": "Europe/Paris"}
        try:
            _graph_post(token, f"/me/todo/lists/{list_id}/tasks", task_body)
            return {"status": "ok", "message": f"Tache '{params['title']}' creee."}
        except Exception as e: return {"status": "error", "message": f"Echec : {str(e)}"}

    if action == "list_teams_chats":
        data = _graph_get(token, "/me/chats", params={"$expand": "members", "$top": 20})
        return {"status": "ok", "items": data.get("value", [])}

    if action == "send_teams_message":
        try:
            _graph_post(token, f"/me/chats/{params['chat_id']}/messages", {"body": {"content": params["message"]}})
            return {"status": "ok", "message": "Message Teams envoye."}
        except Exception as e: return {"status": "error", "message": f"Echec Teams : {str(e)}"}

    if action == "find_teams_user":
        name_safe = params["name"].replace("'", "''")
        data = _graph_get(token, "/users", params={
            "$filter": f"startswith(displayName,'{name_safe}')",
            "$select": "id,displayName,mail"})
        return {"status": "ok", "items": data.get("value", [])}

    return {"status": "error", "message": f"Action inconnue : {action}"}

