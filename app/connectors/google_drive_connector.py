"""
GoogleDriveConnector — Google Drive API v3 via DriveConnector.

Scope requis (dans GMAIL_SCOPES) :
  https://www.googleapis.com/auth/drive
  (ou drive.readonly pour lecture seule)
"""
from __future__ import annotations
import requests as http_requests
from app.connectors.drive_connector_base import DriveConnector, DriveItem
from app.logging_config import get_logger

logger = get_logger("raya.gdrive")

_DRIVE = "https://www.googleapis.com/drive/v3"
_MIME_FOLDER = "application/vnd.google-apps.folder"


class GoogleDriveConnector(DriveConnector):

    @property
    def provider(self) -> str:
        return "google_drive"

    def _get(self, path: str, params: dict = None) -> dict:
        r = http_requests.get(f"{_DRIVE}{path}",
                              headers={"Authorization": f"Bearer {self.token}"},
                              params=params or {}, timeout=10)
        if r.status_code == 403:
            logger.warning("[GDrive] 403 — scope manquant")
            return {}
        r.raise_for_status()
        return r.json()

    def _post(self, path: str, body: dict, params: dict = None) -> dict:
        r = http_requests.post(f"{_DRIVE}{path}",
                               headers={"Authorization": f"Bearer {self.token}",
                                        "Content-Type": "application/json"},
                               params=params or {}, json=body, timeout=10)
        r.raise_for_status()
        return r.json()

    def _patch(self, path: str, body: dict) -> dict:
        r = http_requests.patch(f"{_DRIVE}{path}",
                                headers={"Authorization": f"Bearer {self.token}",
                                         "Content-Type": "application/json"},
                                json=body, timeout=10)
        r.raise_for_status()
        return r.json()

    def _to_item(self, f: dict) -> DriveItem:
        is_folder = f.get("mimeType") == _MIME_FOLDER
        return DriveItem(
            id=f.get("id", ""),
            name=f.get("name", ""),
            path=f.get("webViewLink", ""),
            item_type="folder" if is_folder else "file",
            size=int(f.get("size", 0)) if f.get("size") else 0,
            modified=f.get("modifiedTime", ""),
            url=f.get("webViewLink", ""),
            source="google_drive",
            drive_label=self.label,
        )

    def list(self, folder_id: str = "") -> list[DriveItem]:
        try:
            q = f"'{folder_id}' in parents and trashed=false" if folder_id \
                else "trashed=false"
            data = self._get("/files", {
                "q": q, "pageSize": "50",
                "fields": "files(id,name,mimeType,size,modifiedTime,webViewLink)",
                "orderBy": "folder,name",
            })
            return [self._to_item(f) for f in data.get("files", [])]
        except Exception as e:
            logger.warning("[GDrive] list: %s", e)
            return []

    def search(self, query: str, max_results: int = 20) -> list[DriveItem]:
        try:
            data = self._get("/files", {
                "q": f"name contains '{query}' and trashed=false",
                "pageSize": str(max_results),
                "fields": "files(id,name,mimeType,size,modifiedTime,webViewLink)",
            })
            return [self._to_item(f) for f in data.get("files", [])]
        except Exception as e:
            logger.warning("[GDrive] search: %s", e)
            return []

    def read(self, item_id: str) -> str:
        try:
            # Export Google Docs en texte brut
            meta = self._get(f"/files/{item_id}", {"fields": "mimeType"})
            mime = meta.get("mimeType", "")
            if "google-apps" in mime:
                r = http_requests.get(
                    f"{_DRIVE}/files/{item_id}/export",
                    headers={"Authorization": f"Bearer {self.token}"},
                    params={"mimeType": "text/plain"}, timeout=15
                )
                return r.text[:10000]
            else:
                r = http_requests.get(
                    f"{_DRIVE}/files/{item_id}?alt=media",
                    headers={"Authorization": f"Bearer {self.token}"},
                    timeout=15
                )
                return r.text[:10000]
        except Exception as e:
            logger.warning("[GDrive] read: %s", e)
            return ""

    def create_folder(self, parent_id: str, name: str) -> dict:
        try:
            body = {"name": name, "mimeType": _MIME_FOLDER}
            if parent_id:
                body["parents"] = [parent_id]
            data = self._post("/files", body)
            return {"ok": True, "message": f"Dossier '{name}' créé.", "id": data.get("id")}
        except Exception as e:
            return {"ok": False, "message": str(e)[:100]}

    def move(self, item_id: str, dest_folder_id: str, new_name: str = "") -> dict:
        try:
            # Récupérer les parents actuels
            meta = self._get(f"/files/{item_id}", {"fields": "parents"})
            old_parents = ",".join(meta.get("parents", []))
            params = {"addParents": dest_folder_id, "removeParents": old_parents,
                      "fields": "id"}
            body = {"name": new_name} if new_name else {}
            r = http_requests.patch(
                f"{_DRIVE}/files/{item_id}",
                headers={"Authorization": f"Bearer {self.token}",
                         "Content-Type": "application/json"},
                params=params, json=body, timeout=10
            )
            r.raise_for_status()
            return {"ok": True, "message": "Fichier déplacé."}
        except Exception as e:
            return {"ok": False, "message": str(e)[:100]}

    def copy(self, item_id: str, dest_folder_id: str, new_name: str = "") -> dict:
        try:
            body = {}
            if dest_folder_id: body["parents"] = [dest_folder_id]
            if new_name:        body["name"]    = new_name
            data = self._post(f"/files/{item_id}/copy", body)
            return {"ok": True, "message": "Fichier copié.", "id": data.get("id")}
        except Exception as e:
            return {"ok": False, "message": str(e)[:100]}

    def delete(self, item_id: str) -> dict:
        try:
            r = http_requests.delete(
                f"{_DRIVE}/files/{item_id}",
                headers={"Authorization": f"Bearer {self.token}"},
                timeout=10
            )
            r.raise_for_status()
            return {"ok": True, "message": "Fichier supprimé."}
        except Exception as e:
            return {"ok": False, "message": str(e)[:100]}

    def rename(self, item_id: str, new_name: str) -> dict:
        try:
            self._patch(f"/files/{item_id}", {"name": new_name})
            return {"ok": True, "message": f"Renommé en '{new_name}'."}
        except Exception as e:
            return {"ok": False, "message": str(e)[:100]}
