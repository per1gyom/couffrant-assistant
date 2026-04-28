"""
Gestion des actions Teams (LIST, CHATS, MSG, REPLYCHAT, SENDCHANNEL, GROUPE, MARK, SYNC, HISTORY).
7-ACT : log d'activite apres chaque action.
"""
import re
import threading
from app.connectors.teams_connector import (
    list_teams_with_channels, list_channels, read_channel_messages,
    list_chats, read_chat_messages,
    send_channel_message, send_chat_message,
    send_message_to_user, create_group_chat,
)
from app.pending_actions import queue_action
from app.activity_log import log_activity


def _handle_teams_actions(response, token, username, tenant_id, conversation_id):
    confirmed = []

    for _ in re.finditer(r'\[ACTION:TEAMS_LIST:\]', response):
        try:
            res = list_teams_with_channels(token)
            if res.get("status") == "ok":
                lines = []
                for t in res.get("teams", []):
                    ch_names = ", ".join(c["name"] for c in t.get("channels", [])[:5]) or "\u2014"
                    lines.append(f"  \U0001f3e2 {t['name']} [id:{t['id']}]\n     Canaux : {ch_names}")
                confirmed.append(f"\U0001f4cb Teams ({res['count']}) :\n" + "\n".join(lines))
                log_activity(username, "teams_read", "list", f"{res['count']} teams", tenant_id=tenant_id)
            else:
                confirmed.append(f"\u274c Teams : {res.get('message')}")
        except Exception as e:
            confirmed.append(f"\u274c Teams : {str(e)[:80]}")

    for match in re.finditer(r'\[ACTION:TEAMS_CHANNEL:([^|^\]]+)\|([^\]]+)\]', response):
        team_id = match.group(1).strip()
        channel_id = match.group(2).strip()
        try:
            res = read_channel_messages(token, team_id, channel_id)
            if res.get("status") == "ok":
                lines = [f"  [{m['date'][:10]}] {m['sender']} : {m['content'][:120]}" for m in res.get("messages", [])]
                confirmed.append(f"\U0001f4ac Canal ({res['count']}) :\n" + "\n".join(lines))
                log_activity(username, "teams_read", channel_id[:200], f"{res['count']} messages", tenant_id=tenant_id)
            else:
                confirmed.append(f"\u274c Canal : {res.get('message')}")
        except Exception as e:
            confirmed.append(f"\u274c Canal : {str(e)[:80]}")

    for _ in re.finditer(r'\[ACTION:TEAMS_CHATS:\]', response):
        try:
            res = list_chats(token)
            if res.get("status") == "ok":
                lines = []
                for c in res.get("chats", []):
                    icon = '\U0001f464' if c['type'] == 'oneOnOne' else '\U0001f465'
                    lines.append(f"  {icon} {c['topic']} [id:{c['id'][:20]}...]")
                confirmed.append(f"\U0001f4ac Chats Teams ({res['count']}) :\n" + "\n".join(lines))
                log_activity(username, "teams_read", "chats", f"{res['count']} chats", tenant_id=tenant_id)
            else:
                confirmed.append(f"\u274c Chats : {res.get('message')}")
        except Exception as e:
            confirmed.append(f"\u274c Chats : {str(e)[:80]}")

    for match in re.finditer(r'\[ACTION:TEAMS_READCHAT:([^\]]+)\]', response):
        chat_id = match.group(1).strip()
        try:
            res = read_chat_messages(token, chat_id)
            if res.get("status") == "ok":
                lines = [f"  [{m['date'][:10]}] {m['sender']} : {m['content'][:150]}" for m in res.get("messages", [])]
                confirmed.append(f"\U0001f4ac Chat ({res['count']}) :\n" + "\n".join(lines))
                log_activity(username, "teams_read", chat_id[:200], f"{res['count']} messages", tenant_id=tenant_id)
            else:
                confirmed.append(f"\u274c Chat : {res.get('message')}")
        except Exception as e:
            confirmed.append(f"\u274c Chat : {str(e)[:80]}")

    for match in re.finditer(r'\[ACTION:TEAMS_MSG:([^|^\]]+)\|(.+?)\]', response, re.DOTALL):
        email = match.group(1).strip()
        text = match.group(2).strip()
        label = f"Message Teams a {email}"
        action_id = queue_action(
            tenant_id=tenant_id, username=username, action_type="TEAMS_MSG",
            payload={"email": email, "text": text}, label=label, conversation_id=conversation_id,
        )
        log_activity(username, "teams_send", email[:200], text[:100], tenant_id=tenant_id)
        preview = text[:200] + ("..." if len(text) > 200 else "")
        confirmed.append(f"\u23f8\ufe0f Action #{action_id} en attente : {label}\n   Message : {preview}\n   Pour envoyer : dites \"confirme action {action_id}\"")

    for match in re.finditer(r'\[ACTION:TEAMS_REPLYCHAT:([^|^\]]+)\|(.+?)\]', response, re.DOTALL):
        chat_id = match.group(1).strip()
        text = match.group(2).strip()
        action_id = queue_action(
            tenant_id=tenant_id, username=username, action_type="TEAMS_REPLYCHAT",
            payload={"chat_id": chat_id, "text": text},
            label="Repondre dans le chat Teams", conversation_id=conversation_id,
        )
        log_activity(username, "teams_send", chat_id[:200], text[:100], tenant_id=tenant_id)
        confirmed.append(f"\u23f8\ufe0f Action #{action_id} en attente : Repondre dans le chat Teams\n   Pour envoyer : dites \"confirme action {action_id}\"")

    for match in re.finditer(r'\[ACTION:TEAMS_SENDCHANNEL:([^|^\]]+)\|([^|^\]]+)\|(.+?)\]', response, re.DOTALL):
        team_id = match.group(1).strip()
        channel_id = match.group(2).strip()
        text = match.group(3).strip()
        action_id = queue_action(
            tenant_id=tenant_id, username=username, action_type="TEAMS_SENDCHANNEL",
            payload={"team_id": team_id, "channel_id": channel_id, "text": text},
            label="Message dans canal Teams", conversation_id=conversation_id,
        )
        log_activity(username, "teams_send", channel_id[:200], text[:100], tenant_id=tenant_id)
        confirmed.append(f"\u23f8\ufe0f Action #{action_id} en attente : Message dans canal Teams\n   Pour envoyer : dites \"confirme action {action_id}\"")

    for match in re.finditer(r'\[ACTION:TEAMS_GROUPE:([^|^\]]+)\|([^|^\]]+)\|(.+?)\]', response, re.DOTALL):
        emails_raw = match.group(1).strip()
        topic = match.group(2).strip()
        text = match.group(3).strip()
        emails = [e.strip() for e in emails_raw.split(',') if e.strip()]
        label = f"Creer groupe Teams : {topic}"
        action_id = queue_action(
            tenant_id=tenant_id, username=username, action_type="TEAMS_GROUPE",
            payload={"emails": emails, "topic": topic, "text": text},
            label=label, conversation_id=conversation_id,
        )
        confirmed.append(f"\u23f8\ufe0f Action #{action_id} en attente : {label}\n   Pour creer : dites \"confirme action {action_id}\"")

    for match in re.finditer(r'\[ACTION:TEAMS_MARK:([^|^\]]+)\|([^|^\]]+)\|?([^|^\]]*)\|?([^\]]*)\]', response):
        chat_id = match.group(1).strip()
        message_id = match.group(2).strip()
        label = match.group(3).strip()
        chat_type = match.group(4).strip() or "chat"
        try:
            from app.memory_teams import set_teams_marker
            res = set_teams_marker(username, chat_id, message_id, label,
                                   chat_type, tenant_id=tenant_id)
            confirmed.append(res.get("message", "\u2705 Curseur Teams pose."))
        except Exception as e:
            confirmed.append(f"\u274c Teams mark : {str(e)[:80]}")

    for match in re.finditer(r'\[ACTION:TEAMS_SYNC:([^|^\]]+)\|?([^|^\]]*)\|?([^\]]*)\]', response):
        chat_id = match.group(1).strip()
        label = match.group(2).strip()
        chat_type = match.group(3).strip() or "chat"
        try:
            from app.memory_teams import ingest_and_synthesize, get_teams_markers
            markers = get_teams_markers(username, tenant_id=tenant_id)
            marker = next((m for m in markers if m["chat_id"] == chat_id), None)
            since = marker["last_message_id"] if marker else None
            threading.Thread(
                target=lambda: ingest_and_synthesize(
                    token, username, chat_id, label, chat_type, since,
                    tenant_id=tenant_id),
                daemon=True
            ).start()
            confirmed.append(f"\U0001f504 Sync Teams '{label or chat_id[:20]}' lancee en arriere-plan.")
        except Exception as e:
            confirmed.append(f"\u274c Teams sync : {str(e)[:80]}")

    for match in re.finditer(r'\[ACTION:TEAMS_HISTORY:([^|^\]]+)\|?([^|^\]]*)\|?([^\]]*)\]', response):
        chat_id = match.group(1).strip()
        label = match.group(2).strip()
        chat_type = match.group(3).strip() or "chat"
        try:
            from app.memory_teams import explore_history
            threading.Thread(
                target=lambda: explore_history(token, username, chat_id,
                                                label, chat_type,
                                                tenant_id=tenant_id),
                daemon=True
            ).start()
            confirmed.append(f"\U0001f50d Exploration historique Teams '{label or chat_id[:20]}' lancee.")
        except Exception as e:
            confirmed.append(f"\u274c Teams history : {str(e)[:80]}")

    return confirmed
