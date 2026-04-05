import requests


GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"


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


def _action_list_unread_messages(token: str, params: dict) -> dict:
    top = params.get("top", 10)
    folder = params.get("folder", "inbox")

    if folder.lower() == "inbox":
        path = "/me/mailFolders/inbox/messages"
    else:
        path = f"/me/mailFolders/{folder}/messages"

    data = _graph_get(
        token,
        path,
        params={
            "$top": top,
            "$filter": "isRead eq false",
            "$orderby": "receivedDateTime DESC",
            "$select": "id,subject,from,receivedDateTime,isRead,bodyPreview",
        },
    )

    return {
        "status": "ok",
        "action": "list_unread_messages",
        "count": len(data.get("value", [])),
        "items": data.get("value", []),
    }


def _action_create_reply_draft(token: str, params: dict) -> dict:
    message_id = params["message_id"]
    reply_body = params.get("reply_body", "")
    subject_override = params.get("subject_override")

    draft = _graph_post(
        token,
        f"/me/messages/{message_id}/createReply",
        {},
    )

    draft_id = draft.get("id")
    if not draft_id:
        raise ValueError("Impossible de créer le brouillon Outlook.")

    patch_body = {
        "body": {
            "contentType": "HTML",
            "content": reply_body,
        }
    }

    if subject_override:
        patch_body["subject"] = subject_override

    _graph_patch(
        token,
        f"/me/messages/{draft_id}",
        patch_body,
    )

    return {
        "status": "ok",
        "action": "create_reply_draft",
        "draft_id": draft_id,
        "message": "Brouillon de réponse créé dans le fil Outlook.",
    }


def _action_mark_as_read(token: str, params: dict) -> dict:
    message_id = params["message_id"]

    _graph_patch(
        token,
        f"/me/messages/{message_id}",
        {"isRead": True},
    )

    return {
        "status": "ok",
        "action": "mark_as_read",
        "message_id": message_id,
        "message": "Mail marqué comme lu.",
    }


def _action_move_message(token: str, params: dict) -> dict:
    message_id = params["message_id"]
    destination_folder_id = params["destination_folder_id"]

    moved = _graph_post(
        token,
        f"/me/messages/{message_id}/move",
        {"destinationId": destination_folder_id},
    )

    return {
        "status": "ok",
        "action": "move_message",
        "old_message_id": message_id,
        "new_message_id": moved.get("id"),
        "destination_folder_id": destination_folder_id,
        "message": "Mail déplacé.",
    }


def perform_outlook_action(action: str, params: dict, token: str) -> dict:
    if action == "list_unread_messages":
        return _action_list_unread_messages(token, params)

    if action == "create_reply_draft":
        return _action_create_reply_draft(token, params)

    if action == "mark_as_read":
        return _action_mark_as_read(token, params)

    if action == "move_message":
        return _action_move_message(token, params)

    return {
        "status": "error",
        "action": action,
        "message": f"Action Outlook inconnue : {action}",
    }