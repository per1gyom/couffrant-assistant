"""
Fonctions envoi Teams.
Extrait de teams_connector.py -- SPLIT-C2.
"""
import requests
from typing import Optional
from app.logging_config import get_logger
logger=get_logger("raya.teams")
def _headers(token): return {"Authorization":f"Bearer {token}","Content-Type":"application/json"}


def send_channel_message(token: str, team_id: str, channel_id: str, text: str) -> dict:
    try:
        r = requests.post(
            f"{GRAPH}/teams/{team_id}/channels/{channel_id}/messages",
            headers=_headers(token),
            json={"body": {"contentType": "text", "content": text}},
            timeout=15
        )
        if r.status_code not in (200, 201):
            return {"status": "error", "message": f"Graph {r.status_code}: {r.text[:200]}"}
        return {"status": "ok", "message": "Message envoyé dans le canal."}
    except Exception as e:
        return {"status": "error", "message": str(e)[:150]}



def send_chat_message(token: str, chat_id: str, text: str) -> dict:
    try:
        r = requests.post(
            f"{GRAPH}/chats/{chat_id}/messages",
            headers=_headers(token),
            json={"body": {"contentType": "text", "content": text}},
            timeout=15
        )
        if r.status_code not in (200, 201):
            return {"status": "error", "message": f"Graph {r.status_code}: {r.text[:200]}"}
        return {"status": "ok", "message": "Message envoyé."}
    except Exception as e:
        return {"status": "error", "message": str(e)[:150]}



def _get_user_id_by_email(token: str, email: str) -> Optional[str]:
    try:
        r = requests.get(
            f"{GRAPH}/users/{email}",
            headers=_headers(token),
            params={"$select": "id,displayName"},
            timeout=10
        )
        if r.status_code == 200:
            return r.json().get("id")
        return None
    except Exception:
        return None



def find_or_create_chat_with_user(token: str, email: str) -> dict:
    chats_result = list_chats(token)
    if chats_result.get("status") == "ok":
        for chat in chats_result.get("chats", []):
            if chat.get("type") == "oneOnOne":
                members_lower = [m.lower() for m in chat.get("members", [])]
                if any(email.lower() in m for m in members_lower):
                    return {"status": "ok", "chat_id": chat["id"], "created": False}

    user_id = _get_user_id_by_email(token, email)
    if not user_id:
        return {"status": "error", "message": f"Utilisateur '{email}' introuvable dans Azure AD."}

    try:
        me_r = requests.get(f"{GRAPH}/me", headers=_headers(token),
                            params={"$select": "id"}, timeout=10)
        my_id = me_r.json().get("id") if me_r.status_code == 200 else None
    except Exception:
        my_id = None

    if not my_id:
        return {"status": "error", "message": "Impossible de récupérer l'identité de l'utilisateur courant."}

    try:
        r = requests.post(
            f"{GRAPH}/chats",
            headers=_headers(token),
            json={
                "chatType": "oneOnOne",
                "members": [
                    {"@odata.type": "#microsoft.graph.aadUserConversationMember",
                     "roles": ["owner"],
                     "user@odata.bind": f"{GRAPH}/users('{my_id}')"},
                    {"@odata.type": "#microsoft.graph.aadUserConversationMember",
                     "roles": ["owner"],
                     "user@odata.bind": f"{GRAPH}/users('{user_id}')"}
                ]
            },
            timeout=15
        )
        if r.status_code not in (200, 201):
            return {"status": "error", "message": f"Création chat échouée: {r.text[:200]}"}
        return {"status": "ok", "chat_id": r.json().get("id"), "created": True}
    except Exception as e:
        return {"status": "error", "message": str(e)[:150]}



def send_message_to_user(token: str, email: str, text: str) -> dict:
    result = find_or_create_chat_with_user(token, email)
    if result.get("status") != "ok":
        return result
    send_result = send_chat_message(token, result["chat_id"], text)
    if send_result.get("status") == "ok":
        action = "créé et message envoyé" if result.get("created") else "message envoyé"
        return {"status": "ok", "message": f"✅ Teams — {action} à {email}"}
    return send_result



def create_group_chat(token: str, emails: list, topic: str, first_message: str) -> dict:
    members_payload = []
    try:
        me_r = requests.get(f"{GRAPH}/me", headers=_headers(token),
                            params={"$select": "id"}, timeout=10)
        my_id = me_r.json().get("id") if me_r.status_code == 200 else None
    except Exception:
        my_id = None

    if my_id:
        members_payload.append({
            "@odata.type": "#microsoft.graph.aadUserConversationMember",
            "roles": ["owner"],
            "user@odata.bind": f"{GRAPH}/users('{my_id}')"
        })

    for email in emails:
        uid = _get_user_id_by_email(token, email)
        if uid:
            members_payload.append({
                "@odata.type": "#microsoft.graph.aadUserConversationMember",
                "roles": ["owner"],
                "user@odata.bind": f"{GRAPH}/users('{uid}')"
            })
        else:
            return {"status": "error", "message": f"Utilisateur '{email}' introuvable."}

    if len(members_payload) < 2:
        return {"status": "error", "message": "Pas assez de membres valides."}

    try:
        r = requests.post(
            f"{GRAPH}/chats",
            headers=_headers(token),
            json={"chatType": "group", "topic": topic, "members": members_payload},
            timeout=15
        )
        if r.status_code not in (200, 201):
            return {"status": "error", "message": f"Création groupe échouée: {r.text[:200]}"}
        chat_id = r.json().get("id")
        send_result = send_chat_message(token, chat_id, first_message)
        if send_result.get("status") == "ok":
            return {"status": "ok", "message": f"✅ Groupe '{topic}' créé et message envoyé.",
                    "chat_id": chat_id}
        return send_result
    except Exception as e:
        return {"status": "error", "message": str(e)[:150]}

