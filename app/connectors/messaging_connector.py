"""
Messaging Abstraction Layer — interface commune pour tous les providers de messagerie.

Implémentations :
  TeamsConnector    → Microsoft Teams (Graph API)
  SlackConnector    → futur
  WhatsAppConnector → futur

Ajouter un provider :
  1. Créer une classe héritant de MessagingConnector
  2. L'enregistrer dans messaging_manager.PROVIDER_MAP
  C'est tout.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from abc import ABC, abstractmethod
from app.logging_config import get_logger

logger = get_logger("raya.messaging")


# ─── MODÈLES ───────────────────────────────────────────────────────

@dataclass
class Message:
    id:        str = ""
    from_name: str = ""
    from_id:   str = ""
    text:      str = ""
    date:      str = ""
    source:    str = ""

@dataclass
class Channel:
    id:          str = ""
    name:        str = ""
    team_id:     str = ""
    team_name:   str = ""
    description: str = ""
    source:      str = ""

@dataclass
class Conversation:
    id:           str = ""
    display_name: str = ""
    topic:        str = ""
    conv_type:    str = ""   # 'direct' | 'group' | 'channel'
    members:      list = field(default_factory=list)
    source:       str = ""


# ─── INTERFACE ABSTRAITE ───────────────────────────────────────────

class MessagingConnector(ABC):
    """Interface commune pour tous les providers de messagerie."""

    def __init__(self, username: str, token: str, config: dict = None):
        self.username = username
        self.token    = token
        self.config   = config or {}

    @property
    @abstractmethod
    def provider(self) -> str:
        """Identifiant : 'teams' | 'slack' | 'whatsapp'"""

    @property
    def display_name(self) -> str:
        return self.provider.title()

    # --- LECTURE ---

    def list_channels(self) -> list[Channel]:
        """Liste tous les canaux accessibles (teams + channels)."""
        return []

    def read_channel(self, channel_id: str, team_id: str = "", top: int = 15) -> list[Message]:
        """Lit les derniers messages d'un canal."""
        return []

    def list_conversations(self) -> list[Conversation]:
        """Liste les conversations directes et groupes."""
        return []

    def read_conversation(self, conv_id: str, top: int = 15) -> list[Message]:
        """Lit les derniers messages d'une conversation."""
        return []

    # --- ENVOI ---

    def send_message(self, to_email: str, text: str) -> dict:
        """Envoie un message direct à un utilisateur."""
        return {"ok": False, "message": f"send_message non implémenté pour {self.provider}"}

    def send_channel(self, team_id: str, channel_id: str, text: str) -> dict:
        """Envoie un message dans un canal."""
        return {"ok": False, "message": f"send_channel non implémenté pour {self.provider}"}

    def reply_conversation(self, conv_id: str, text: str) -> dict:
        """Répond dans une conversation existante."""
        return {"ok": False, "message": f"reply_conversation non implémenté pour {self.provider}"}

    def send_group(self, emails: list, topic: str, text: str) -> dict:
        """Crée un groupe et envoie un message."""
        return {"ok": False, "message": f"send_group non implémenté pour {self.provider}"}
