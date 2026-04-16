"""
TeamsConnector — Microsoft Teams via MessagingConnector.
Wraps les fonctions existantes de teams_connector.py et teams_actions.py.
"""
from __future__ import annotations
from app.connectors.messaging_connector import (
    MessagingConnector, Message, Channel, Conversation
)
from app.logging_config import get_logger

logger = get_logger("raya.teams")


class TeamsConnector(MessagingConnector):

    @property
    def provider(self) -> str:
        return "teams"

    @property
    def display_name(self) -> str:
        return "Microsoft Teams"

    def list_channels(self) -> list[Channel]:
        try:
            from app.connectors.teams_connector import list_teams_with_channels
            result = list_teams_with_channels(self.token)
            channels = []
            for team in result.get("teams", []):
                for ch in team.get("channels", []):
                    channels.append(Channel(
                        id=ch.get("id", ""),
                        name=ch.get("displayName", ""),
                        team_id=team.get("id", ""),
                        team_name=team.get("displayName", ""),
                        source="teams",
                    ))
            return channels
        except Exception as e:
            logger.warning("[Teams] list_channels: %s", e)
            return []

    def read_channel(self, channel_id: str, team_id: str = "", top: int = 15) -> list[Message]:
        try:
            from app.connectors.teams_connector import read_channel_messages
            result = read_channel_messages(self.token, team_id, channel_id, top=top)
            return [Message(
                id=m.get("id", ""),
                from_name=m.get("from_name", m.get("from", "")),
                text=m.get("body", m.get("text", "")),
                date=m.get("createdDateTime", m.get("date", "")),
                source="teams",
            ) for m in result.get("messages", [])]
        except Exception as e:
            logger.warning("[Teams] read_channel: %s", e)
            return []

    def list_conversations(self) -> list[Conversation]:
        try:
            from app.connectors.teams_connector import list_chats
            result = list_chats(self.token)
            return [Conversation(
                id=c.get("id", ""),
                display_name=c.get("topic") or c.get("display_name", ""),
                topic=c.get("topic", ""),
                conv_type="group" if c.get("chatType") == "group" else "direct",
                members=[m.get("email", "") for m in c.get("members", [])],
                source="teams",
            ) for c in result.get("chats", [])]
        except Exception as e:
            logger.warning("[Teams] list_conversations: %s", e)
            return []

    def read_conversation(self, conv_id: str, top: int = 15) -> list[Message]:
        try:
            from app.connectors.teams_connector import read_chat_messages
            result = read_chat_messages(self.token, conv_id, top=top)
            return [Message(
                id=m.get("id", ""),
                from_name=m.get("from_name", m.get("from", "")),
                text=m.get("body", m.get("text", "")),
                date=m.get("createdDateTime", m.get("date", "")),
                source="teams",
            ) for m in result.get("messages", [])]
        except Exception as e:
            logger.warning("[Teams] read_conversation: %s", e)
            return []

    def send_message(self, to_email: str, text: str) -> dict:
        try:
            from app.connectors.teams_actions import send_message_to_user
            r = send_message_to_user(self.token, to_email, text)
            ok = r.get("status") == "ok"
            return {"ok": ok, "message": r.get("message", "Message envoyé" if ok else "Erreur")}
        except Exception as e:
            return {"ok": False, "message": str(e)[:100]}

    def send_channel(self, team_id: str, channel_id: str, text: str) -> dict:
        try:
            from app.connectors.teams_actions import send_channel_message
            r = send_channel_message(self.token, team_id, channel_id, text)
            ok = r.get("status") == "ok"
            return {"ok": ok, "message": r.get("message", "Envoyé" if ok else "Erreur")}
        except Exception as e:
            return {"ok": False, "message": str(e)[:100]}

    def reply_conversation(self, conv_id: str, text: str) -> dict:
        try:
            from app.connectors.teams_actions import send_chat_message
            r = send_chat_message(self.token, conv_id, text)
            ok = r.get("status") == "ok"
            return {"ok": ok, "message": r.get("message", "Envoyé" if ok else "Erreur")}
        except Exception as e:
            return {"ok": False, "message": str(e)[:100]}

    def send_group(self, emails: list, topic: str, text: str) -> dict:
        try:
            from app.connectors.teams_actions import create_group_chat
            r = create_group_chat(self.token, emails, topic, text)
            ok = r.get("status") == "ok"
            return {"ok": ok, "message": r.get("message", "Groupe créé" if ok else "Erreur")}
        except Exception as e:
            return {"ok": False, "message": str(e)[:100]}
