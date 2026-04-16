"""
Système de connecteurs unifiés — Mailbox Abstraction Layer.

Architecture :
  MailboxConnector  — interface commune (contacts, mail, agenda)
  MicrosoftConnector — implémentation Microsoft Graph
  GmailConnector     — implémentation Google API
  
  get_user_mailboxes(username) → liste de tous les connecteurs actifs

Ajouter un nouveau provider :
  1. Créer une classe héritant de MailboxConnector
  2. L'enregistrer dans PROVIDER_MAP
  C'est tout — aucune autre modification requise.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
from abc import ABC, abstractmethod
from app.logging_config import get_logger

logger = get_logger("raya.mailbox")


# ─── MODÈLES DE DONNÉES ────────────────────────────────────────────

@dataclass
class Contact:
    name:  str = ""
    email: str = ""
    phone: str = ""
    source: str = ""   # 'microsoft' | 'gmail' | ...

@dataclass
class MailMessage:
    id:       str = ""
    subject:  str = ""
    sender:   str = ""
    body:     str = ""
    date:     str = ""
    source:   str = ""

@dataclass
class CalendarEvent:
    id:       str = ""
    title:    str = ""
    start:    str = ""
    end:      str = ""
    location: str = ""
    source:   str = ""


# ─── INTERFACE ABSTRAITE ───────────────────────────────────────────

class MailboxConnector(ABC):
    """Interface commune pour tous les fournisseurs mail."""

    def __init__(self, username: str, email: str, token: str):
        self.username = username
        self.email    = email
        self.token    = token

    @property
    @abstractmethod
    def provider(self) -> str:
        """Identifiant du provider : 'microsoft', 'gmail', ..."""

    @property
    def display_name(self) -> str:
        return f"{self.provider.title()} ({self.email})"

    # --- CONTACTS ---

    def search_contacts(self, query: str) -> list[Contact]:
        return []

    def list_contacts(self, max_results: int = 100) -> list[Contact]:
        return []

    def create_contact(self, name: str, email: str, phone: str = "") -> dict:
        return {"ok": False, "message": f"create_contact non implémenté pour {self.provider}"}

    def update_contact(self, contact_id: str, **kwargs) -> dict:
        return {"ok": False, "message": f"update_contact non implémenté pour {self.provider}"}

    def delete_contact(self, contact_id: str) -> dict:
        return {"ok": False, "message": f"delete_contact non implémenté pour {self.provider}"}

    # --- MAIL ---

    def send_mail(self, to: str, subject: str, body: str, from_email: str = "") -> dict:
        return {"ok": False, "message": f"send_mail non implémenté pour {self.provider}"}

    def create_draft(self, to: str, subject: str, body: str) -> dict:
        return {"ok": False, "message": f"create_draft non implémenté pour {self.provider}"}

    def search_mail(self, query: str, max_results: int = 10) -> list[MailMessage]:
        return []

    def delete_mail(self, mail_id: str) -> dict:
        return {"ok": False, "message": f"delete_mail non implémenté pour {self.provider}"}

    # --- AGENDA ---

    def get_agenda(self, days: int = 7) -> list[CalendarEvent]:
        return []

    def create_event(self, title: str, start: str, end: str, **kwargs) -> dict:
        return {"ok": False, "message": f"create_event non implémenté pour {self.provider}"}

    def delete_event(self, event_id: str) -> dict:
        return {"ok": False, "message": f"delete_event non implémenté pour {self.provider}"}
