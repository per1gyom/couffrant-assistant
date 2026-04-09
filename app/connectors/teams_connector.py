import re
import requests
from typing import Optional

GRAPH = "https://graph.microsoft.com/v1.0"


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _strip_html(text: str) -> str:
    return re.sub(r'<[^>]+>', ' ', text or "").strip()


# ─── LECTURE ───

def list_teams(token: str) -> dict:
    """Liste les équipes Teams dont l'utilisateur est membre."""
    try:
        r = requests.get(f"{GRAPH}/me/joinedTeams",
                         headers=_headers(token), timeout=15)
        if r.status_code != 200:
            return {"status": "error", "message": f"Graph {r.status_code}: {r.text[:200]}"}
        teams = []
        for t in r.json().get("value", []):
            teams.append({"id": t["id"], "name": t.get("displayName", ""),
                          "description": t.get("description", "")})
        return {"status": "ok", "teams": teams, "count": len(teams)}
    except Exception as e:
        return {"status": "error", "message": str(e)[:150]}


def list_channels(token: str, team_id: str) -> dict:
    """Liste les canaux d'une équipe."""
    try:
        r = requests.get(
            f"{GRAPH}/teams/{team_id}/channels",
            headers=_headers(token),
            params={"$select": "id,displayName,description"},
            timeout=15
        )
        if r.status_code != 200:
            return {"status": "error", "message": f"Graph {r.status_code}: {r.text[:200]}"}
        channels = []
        for c in r.json().get("value", []):
            channels.append({"id": c["id"], "name": c.get("displayName", ""),
                              "description": c.get("description", "")})
        return {"status": "ok", "channels": channels, "count": len(channels)}
    except Exception as e:
        return {"status": "error", "message": str(e)[:150]}


def read_channel_messages(token: str, team_id: str, channel_id: str, top: int = 15) -> dict:
    """Lit les derniers messages d'un canal. Pas de $orderby — non supporté par Graph."""
    try:
        r = requests.get(
            f"{GRAPH}/teams/{team_id}/channels/{channel_id}/messages",
            headers=_headers(token),
            params={"$top": top},   # $orderby retiré — non supporté
            timeout=15
        )
        if r.status_code != 200:
            return {"status": "error", "message": f"Graph {r.status_code}: {r.text[:200]}"}
        messages = []
        for m in r.json().get("value", []):
            content = _strip_html(m.get("body", {}).get("content", ""))
            sender = (m.get("from") or {}).get("user", {}).get("displayName", "Inconnu")
            messages.append({
                "id": m["id"],
                "sender": sender,
                "content": content[:500],
                "date": m.get("lastModifiedDateTime", ""),
            })
        return {"status": "ok", "messages": messages, "count": len(messages)}
    except Exception as e:
        return {"status": "error", "message": str(e)[:150]}


def list_chats(token: str) -> dict:
    """Liste les chats 1:1 et de groupe actifs. Pas de $orderby — non supporté par Graph."""
    try:
        r = requests.get(
            f"{GRAPH}/me/chats",
            headers=_headers(token),
            params={"$expand": "members", "$top": 20},  # $orderby retiré — non supporté
            timeout=15
        )
        if r.status_code != 200:
            return {"status": "error", "message": f"Graph {r.status_code}: {r.text[:200]}"}
        chats = []
        for c in r.json().get("value", []):
            members = [
                m.get("displayName") or m.get("email", "")
                for m in c.get("members", [])
                if m.get("displayName") or m.get("email")
            ]
            chats.append({
                "id": c["id"],
                "type": c.get("chatType", ""),
                "topic": c.get("topic") or ", ".join(members[:3]) or "(sans titre)",
                "members": members,
                "updated": c.get("lastUpdatedDateTime", ""),
            })
        return {"status": "ok", "chats": chats, "count": len(chats)}
    except Exception as e:
        return {"status": "error", "message": str(e)[:150]}


def read_chat_messages(token: str, chat_id: str, top: int = 15) -> dict:
    """Lit les derniers messages d'un chat."""
    try:
        # Endpoint correct : /chats/{id}/messages (pas /me/chats)
        r = requests.get(
            f"{GRAPH}/chats/{chat_id}/messages",
            headers=_headers(token),
            params={"$top": top},
            timeout=15
        )
        if r.status_code != 200:
            return {"status": "error", "message": f"Graph {r.status_code}: {r.text[:200]}"}
        messages = []
        for m in r.json().get("value", []):
            content = _strip_html(m.get("body", {}).get("content", ""))
            sender = (m.get("from") or {}).get("user", {}).get("displayName", "Inconnu")
            messages.append({
                "id": m["id"],
                "sender": sender,
                "content": content[:500],
                "date": m.get("lastModifiedDateTime", ""),
            })
        return {"status": "ok", "messages": messages, "count": len(messages)}
    except Exception as e:
        return {"status": "error", "message": str(e)[:150]}


# ─── ÉCRITURE ───

def send_channel_message(token: str, team_id: str, channel_id: str, text: str) -> dict:
    """Envoie un message dans un canal Teams."""
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
    """Envoie un message dans un chat existant."""
    try:
        # Endpoint correct : /chats/{id}/messages (pas /me/chats)
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
    """Récupère l'ID Azure AD d'un utilisateur par son email."""
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
    """
    Trouve ou crée un chat 1:1 avec un utilisateur via son email.
    Retourne le chat_id.
    """
    # 1. Cherche dans les chats existants
    chats_result = list_chats(token)
    if chats_result.get("status") == "ok":
        for chat in chats_result.get("chats", []):
            if chat.get("type") == "oneOnOne":
                members_lower = [m.lower() for m in chat.get("members", [])]
                if any(email.lower() in m for m in members_lower):
                    return {"status": "ok", "chat_id": chat["id"], "created": False}

    # 2. Résout l'ID utilisateur
    user_id = _get_user_id_by_email(token, email)
    if not user_id:
        return {"status": "error", "message": f"Utilisateur '{email}' introuvable dans Azure AD."}

    # 3. Récupère l'ID de l'utilisateur courant
    try:
        me_r = requests.get(f"{GRAPH}/me", headers=_headers(token),
                            params={"$select": "id"}, timeout=10)
        my_id = me_r.json().get("id") if me_r.status_code == 200 else None
    except Exception:
        my_id = None

    if not my_id:
        return {"status": "error", "message": "Impossible de récupérer l'identité de l'utilisateur courant."}

    # 4. Crée le chat 1:1
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
        chat_id = r.json().get("id")
        return {"status": "ok", "chat_id": chat_id, "created": True}
    except Exception as e:
        return {"status": "error", "message": str(e)[:150]}


def send_message_to_user(token: str, email: str, text: str) -> dict:
    """
    Envoie un message Teams à un collègue par email.
    Trouve ou crée le chat 1:1 automatiquement.
    """
    result = find_or_create_chat_with_user(token, email)
    if result.get("status") != "ok":
        return result
    chat_id = result["chat_id"]
    send_result = send_chat_message(token, chat_id, text)
    if send_result.get("status") == "ok":
        action = "créé et message envoyé" if result.get("created") else "message envoyé"
        return {"status": "ok", "message": f"✅ Teams — {action} à {email}"}
    return send_result


def create_group_chat(token: str, emails: list, topic: str, first_message: str) -> dict:
    """
    Crée une conversation de groupe Teams avec plusieurs personnes et envoie le premier message.
    """
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
        return {"status": "error", "message": "Pas assez de membres valides pour créer le groupe."}

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
            return {"status": "ok", "message": f"✅ Groupe '{topic}' créé et message envoyé.", "chat_id": chat_id}
        return send_result
    except Exception as e:
        return {"status": "error", "message": str(e)[:150]}
