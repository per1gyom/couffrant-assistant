"""
MicrosoftConnector — implémentation Microsoft Graph pour MailboxConnector.
"""
from __future__ import annotations
from app.connectors.mailbox_connector import MailboxConnector, Contact, MailMessage, CalendarEvent
from app.logging_config import get_logger

logger = get_logger("raya.ms_connector")
_GRAPH = "https://graph.microsoft.com/v1.0"


class MicrosoftConnector(MailboxConnector):

    @property
    def provider(self) -> str:
        return "microsoft"

    def _get(self, path: str, params: dict = None):
        import requests
        r = requests.get(f"{_GRAPH}{path}", headers={"Authorization": f"Bearer {self.token}"},
                         params=params or {}, timeout=10)
        r.raise_for_status()
        return r.json()

    def _post(self, path: str, body: dict):
        import requests
        r = requests.post(f"{_GRAPH}{path}", headers={"Authorization": f"Bearer {self.token}",
                          "Content-Type": "application/json"}, json=body, timeout=10)
        r.raise_for_status()
        return r.json()

    def search_contacts(self, query: str) -> list[Contact]:
        try:
            data = self._get("/me/contacts", {
                "$filter": f"startswith(displayName,'{query}') or startswith(givenName,'{query}')"
                           f" or emailAddresses/any(e:startswith(e/address,'{query}'))",
                "$select": "displayName,emailAddresses,mobilePhone",
                "$top": "10",
            })
            return [Contact(
                name=c.get("displayName",""),
                email=(c.get("emailAddresses",[{}])[0].get("address","") if c.get("emailAddresses") else ""),
                phone=c.get("mobilePhone",""),
                source="microsoft"
            ) for c in data.get("value",[])]
        except Exception as e:
            logger.warning("[MSConnector] search_contacts: %s", e)
            return []

    def create_contact(self, name: str, email: str, phone: str = "") -> dict:
        try:
            body = {"displayName": name, "emailAddresses": [{"address": email, "name": name}]}
            if phone: body["mobilePhone"] = phone
            self._post("/me/contacts", body)
            return {"ok": True, "message": f"Contact '{name}' créé dans Outlook."}
        except Exception as e:
            return {"ok": False, "message": str(e)[:100]}

    def send_mail(self, to: str, subject: str, body: str, from_email: str = "") -> dict:
        try:
            from app.connectors.outlook_connector import perform_outlook_action
            r = perform_outlook_action("send_new_mail", {"to_email": to, "subject": subject, "body": body}, self.token)
            ok = r.get("status") == "ok"
            return {"ok": ok, "message": r.get("message", "Envoyé" if ok else "Erreur")}
        except Exception as e:
            return {"ok": False, "message": str(e)[:100]}

    def create_draft(self, to: str, subject: str, body: str) -> dict:
        try:
            from app.connectors.outlook_connector import perform_outlook_action
            r = perform_outlook_action("create_draft_mail", {"to_email": to, "subject": subject, "body": body}, self.token)
            ok = r.get("status") == "ok"
            return {"ok": ok, "message": r.get("message", "Brouillon créé" if ok else "Erreur")}
        except Exception as e:
            return {"ok": False, "message": str(e)[:100]}

    def get_agenda(self, days: int = 7) -> list[CalendarEvent]:
        try:
            from datetime import datetime, timezone, timedelta
            now = datetime.now(timezone.utc)
            end = now + timedelta(days=days)
            data = self._get("/me/calendarView", {
                "startDateTime": now.isoformat(), "endDateTime": end.isoformat(),
                "$select": "id,subject,start,end,location", "$top": "20",
                "$orderby": "start/dateTime",
            })
            return [CalendarEvent(
                id=e.get("id",""), title=e.get("subject",""),
                start=e.get("start",{}).get("dateTime",""),
                end=e.get("end",{}).get("dateTime",""),
                location=e.get("location",{}).get("displayName",""),
                source="microsoft"
            ) for e in data.get("value",[])]
        except Exception as e:
            logger.warning("[MSConnector] get_agenda: %s", e)
            return []
