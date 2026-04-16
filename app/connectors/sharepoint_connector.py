"""
SharePointConnector — Microsoft Graph / SharePoint via DriveConnector.
Wraps les fonctions existantes de drive_connector.py.
"""
from __future__ import annotations
from app.connectors.drive_connector_base import DriveConnector, DriveItem
from app.logging_config import get_logger

logger = get_logger("raya.sharepoint")


class SharePointConnector(DriveConnector):

    @property
    def provider(self) -> str:
        return "sharepoint"

    def _perform(self, action: str, params: dict) -> dict:
        from app.connectors.drive_connector import perform_drive_action
        return perform_drive_action(action, params, self.token, self.config)

    def _to_item(self, raw: dict) -> DriveItem:
        return DriveItem(
            id=raw.get("id", raw.get("item_id", "")),
            name=raw.get("name", raw.get("title", "")),
            path=raw.get("path", raw.get("web_url", "")),
            item_type="folder" if raw.get("folder") else "file",
            size=raw.get("size", 0),
            modified=raw.get("lastModifiedDateTime", raw.get("modified", "")),
            url=raw.get("webUrl", raw.get("web_url", "")),
            source="sharepoint",
            drive_label=self.label,
        )

    def list(self, folder_id: str = "") -> list[DriveItem]:
        try:
            result = self._perform("list_children",
                                   {"item_id": folder_id} if folder_id else {})
            return [self._to_item(i) for i in result.get("items", [])]
        except Exception as e:
            logger.warning("[SharePoint] list: %s", e)
            return []

    def search(self, query: str, max_results: int = 20) -> list[DriveItem]:
        try:
            result = self._perform("search_drive", {"query": query, "top": max_results})
            return [self._to_item(i) for i in result.get("items", [])]
        except Exception as e:
            logger.warning("[SharePoint] search: %s", e)
            return []

    def read(self, item_id: str) -> str:
        try:
            result = self._perform("read_file", {"item_id": item_id})
            return result.get("content", result.get("text", ""))
        except Exception as e:
            logger.warning("[SharePoint] read: %s", e)
            return ""

    def create_folder(self, parent_id: str, name: str) -> dict:
        try:
            result = self._perform("create_folder", {"parent_id": parent_id, "name": name})
            ok = result.get("status") == "ok"
            return {"ok": ok, "message": result.get("message", "Dossier créé" if ok else "Erreur")}
        except Exception as e:
            return {"ok": False, "message": str(e)[:100]}

    def move(self, item_id: str, dest_folder_id: str, new_name: str = "") -> dict:
        try:
            result = self._perform("move_item", {
                "item_id": item_id, "dest_id": dest_folder_id, "name": new_name
            })
            ok = result.get("status") == "ok"
            return {"ok": ok, "message": result.get("message", "Déplacé" if ok else "Erreur")}
        except Exception as e:
            return {"ok": False, "message": str(e)[:100]}

    def copy(self, item_id: str, dest_folder_id: str, new_name: str = "") -> dict:
        try:
            result = self._perform("copy_item", {
                "item_id": item_id, "dest_id": dest_folder_id, "name": new_name
            })
            ok = result.get("status") == "ok"
            return {"ok": ok, "message": result.get("message", "Copié" if ok else "Erreur")}
        except Exception as e:
            return {"ok": False, "message": str(e)[:100]}

    def delete(self, item_id: str) -> dict:
        try:
            result = self._perform("delete_item", {"item_id": item_id})
            ok = result.get("status") == "ok"
            return {"ok": ok, "message": result.get("message", "Supprimé" if ok else "Erreur")}
        except Exception as e:
            return {"ok": False, "message": str(e)[:100]}
