"""
Drive Abstraction Layer — interface commune pour tous les fournisseurs de stockage.

Implémentations :
  SharePointConnector  → Microsoft Graph / SharePoint
  GoogleDriveConnector → Google Drive API v3

Ajouter un provider :
  1. Créer une classe héritant de DriveConnector
  2. L'enregistrer dans drive_manager.PROVIDER_MAP
  C'est tout.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from abc import ABC, abstractmethod
from app.logging_config import get_logger

logger = get_logger("raya.drive")


# ─── MODÈLES ───────────────────────────────────────────────────────

@dataclass
class DriveItem:
    id:           str  = ""
    name:         str  = ""
    path:         str  = ""
    item_type:    str  = ""    # 'file' | 'folder'
    size:         int  = 0     # bytes
    modified:     str  = ""    # ISO datetime
    url:          str  = ""    # lien direct
    source:       str  = ""    # 'sharepoint' | 'google_drive'
    drive_label:  str  = ""    # label de connexion affiché


# ─── INTERFACE ABSTRAITE ───────────────────────────────────────────

class DriveConnector(ABC):
    """Interface commune pour tous les providers de stockage."""

    def __init__(self, username: str, token: str, config: dict = None):
        self.username = username
        self.token    = token
        self.config   = config or {}

    @property
    @abstractmethod
    def provider(self) -> str:
        """Identifiant : 'sharepoint' | 'google_drive'"""

    @property
    def label(self) -> str:
        return self.config.get("label") or self.provider.replace("_", " ").title()

    @property
    def display_name(self) -> str:
        return f"{self.label}"

    # --- LECTURE ---

    def list(self, folder_id: str = "") -> list[DriveItem]:
        """Liste le contenu d'un dossier (racine si folder_id vide)."""
        return []

    def search(self, query: str, max_results: int = 20) -> list[DriveItem]:
        """Recherche par nom ou contenu."""
        return []

    def read(self, item_id: str) -> str:
        """Retourne le contenu texte d'un fichier."""
        return ""

    def get_item(self, item_id: str) -> DriveItem | None:
        """Retourne les métadonnées d'un item."""
        return None

    # --- ÉCRITURE ---

    def create_folder(self, parent_id: str, name: str) -> dict:
        return {"ok": False, "message": f"create_folder non implémenté pour {self.provider}"}

    def move(self, item_id: str, dest_folder_id: str, new_name: str = "") -> dict:
        return {"ok": False, "message": f"move non implémenté pour {self.provider}"}

    def copy(self, item_id: str, dest_folder_id: str, new_name: str = "") -> dict:
        return {"ok": False, "message": f"copy non implémenté pour {self.provider}"}

    def upload(self, parent_id: str, filename: str, content: bytes) -> dict:
        return {"ok": False, "message": f"upload non implémenté pour {self.provider}"}

    def delete(self, item_id: str) -> dict:
        return {"ok": False, "message": f"delete non implémenté pour {self.provider}"}

    def rename(self, item_id: str, new_name: str) -> dict:
        return {"ok": False, "message": f"rename non implémenté pour {self.provider}"}
