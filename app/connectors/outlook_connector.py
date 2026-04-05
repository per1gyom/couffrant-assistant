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


def perform_outlook_action(action: str, params: dict, token: str) -> dict:
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

    if action == "create_reply_draft":
        message_id = params["message_id"]
        reply_body = params.get("reply_body", "")
        draft = _graph_post(token, f"/me/messages/{message_id}/createReply", {})
        draft_id = draft.get("id")
        if not draft_id:
            raise ValueError("Impossible de créer le brouillon Outlook.")
        patch_body = {"body": {"contentType": "HTML", "content": reply_body}}
        if params.get("subject_override"):
            patch_body["subject"] = params["subject_override"]
        _graph_patch(token, f"/me/messages/{draft_id}", patch_body)
        return {
            "status": "ok",
            "action": action,
            "draft_id": draft_id,
            "message": "Brouillon créé.",
        }

    if action == "mark_as_read":
        message_id = params["message_id"]
        _graph_patch(token, f"/me/messages/{message_id}", {"isRead": True})
        return {"status": "ok", "action": action, "message_id": message_id}

    if action == "move_message":
        message_id = params["message_id"]
        moved = _graph_post(
            token,
            f"/me/messages/{message_id}/move",
            {"destinationId": params["destination_folder_id"]},
        )
        return {
            "status": "ok",
            "action": action,
            "new_message_id": moved.get("id"),
        }

    return {"status": "error", "action": action, "message": f"Action inconnue : {action}"}