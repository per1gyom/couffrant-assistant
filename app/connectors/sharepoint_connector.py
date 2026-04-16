"""
SharePointConnector — Microsoft Graph / SharePoint via DriveConnector.
Wraps les fonctions réelles de drive_read.py et connectors/drive_actions.py.
"""
from __future__ import annotations
from app.connectors.drive_connector_base import DriveConnector, DriveItem
from app.logging_config import get_logger

logger = get_logger("raya.sharepoint")


class SharePointConnector(DriveConnector):

    @property
    def provider(self) -> str:
        return "sharepoint"

    def _cfg(self) -> dict:
        """Config SharePoint depuis tenant ou config du connecteur."""
        if self.config.get("site_name"):
            return self.config
        try:
            from app.app_security import get_tenant_id
            from app.connectors.drive_connector import get_drive_config
            tenant_id = get_tenant_id(self.username)
            return get_drive_config(tenant_id) if tenant_id else {}
        except Exception:
            return {}

    def _to_item(self, raw: dict) -> DriveItem:
        name = raw.get("nom") or raw.get("name") or raw.get("title") or ""
        url  = raw.get("lien") or raw.get("web_url") or raw.get("webUrl") or ""
        is_folder = raw.get("type") == "dossier" or bool(raw.get("folder"))
        return DriveItem(
            id=raw.get("id", raw.get("item_id", "")),
            name=name,
            path=url,
            item_type="folder" if is_folder else "file",
            size=raw.get("taille_ko", raw.get("size", 0)) or 0,
            modified=raw.get("lastModifiedDateTime", raw.get("modified", "")),
            url=url,
            source="sharepoint",
            drive_label=self.label,
        )

    def list(self, folder_id: str = "") -> list[DriveItem]:
        try:
            from app.connectors.drive_read import list_drive
            cfg = self._cfg()
            result = list_drive(self.token, folder_id, config=cfg)
            if result.get("status") == "ok":
                return [self._to_item(i) for i in result.get("items", [])]
            return []
        except Exception as e:
            logger.warning("[SharePoint] list: %s", e)
            return []

    def search(self, query: str, max_results: int = 20) -> list[DriveItem]:
        try:
            from app.connectors.drive_read import search_drive
            cfg = self._cfg()
            result = search_drive(self.token, query, config=cfg)
            if result.get("status") == "ok":
                return [self._to_item(i) for i in result.get("items", [])]
            return []
        except Exception as e:
            logger.warning("[SharePoint] search: %s", e)
            return []

    def read(self, item_id: str) -> str:
        try:
            from app.connectors.drive_read import read_drive_file
            result = read_drive_file(self.token, item_id)
            if result.get("status") == "ok" and result.get("type") == "texte":
                return result.get("contenu", "")
            return ""
        except Exception as e:
            logger.warning("[SharePoint] read: %s", e)
            return ""

    def create_folder(self, parent_id: str, name: str) -> dict:
        try:
            from app.connectors.drive_actions import create_folder
            cfg = self._cfg()
            r = create_folder(self.token, parent_id, name, config=cfg)
            ok = r.get("status") == "ok"
            return {"ok": ok, "message": r.get("message", "Dossier créé" if ok else "Erreur")}
        except Exception as e:
            return {"ok": False, "message": str(e)[:100]}

    def move(self, item_id: str, dest_folder_id: str, new_name: str = "") -> dict:
        try:
            from app.connectors.drive_actions import move_item
            from app.connectors.drive_connector import _find_sharepoint_site_and_drive
            _, drive_id, _ = _find_sharepoint_site_and_drive(self.token, self._cfg())
            r = move_item(self.token, item_id, dest_folder_id, new_name, drive_id)
            ok = r.get("status") == "ok"
            return {"ok": ok, "message": r.get("message", "Déplacé" if ok else "Erreur")}
        except Exception as e:
            return {"ok": False, "message": str(e)[:100]}

    def copy(self, item_id: str, dest_folder_id: str, new_name: str = "") -> dict:
        try:
            from app.connectors.drive_actions import copy_item
            from app.connectors.drive_connector import _find_sharepoint_site_and_drive
            _, drive_id, _ = _find_sharepoint_site_and_drive(self.token, self._cfg())
            r = copy_item(self.token, item_id, dest_folder_id, new_name, drive_id)
            ok = r.get("status") == "ok"
            return {"ok": ok, "message": r.get("message", "Copié" if ok else "Erreur")}
        except Exception as e:
            return {"ok": False, "message": str(e)[:100]}
