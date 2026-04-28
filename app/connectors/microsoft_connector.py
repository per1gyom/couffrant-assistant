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

    def search_mail(self, query: str, max_results: int = 10) -> list[MailMessage]:
        """Recherche dans la boite Outlook via Microsoft Graph /me/messages.

        Query accepte une syntaxe pseudo-Gmail traduite en filtres Graph :
          - 'is:unread'              -> $filter=isRead eq false
          - 'newer_than:5m'          -> $filter=receivedDateTime ge <now-5min>
          - 'after:2024/01/01'       -> $filter=receivedDateTime ge <date ISO>
          - 'from:foo@bar.com'       -> $search='from:foo@bar.com'
          - vide                     -> tous les mails (max_results)

        Plusieurs filtres peuvent etre combines. Retourne list[MailMessage].
        """
        try:
            from datetime import datetime, timezone, timedelta
            params = {"$top": str(min(max_results, 1000)),
                      "$select": "id,subject,from,receivedDateTime,bodyPreview",
                      "$orderby": "receivedDateTime desc"}
            filters = []
            search_q = None
            for token in (query or "").split():
                if token == "is:unread":
                    filters.append("isRead eq false")
                elif token.startswith("newer_than:"):
                    val = token.split(":", 1)[1]
                    minutes = int(val[:-1]) if val.endswith("m") else (
                        int(val[:-1]) * 60 if val.endswith("h") else (
                        int(val[:-1]) * 1440 if val.endswith("d") else 5))
                    cutoff = (datetime.now(timezone.utc) -
                              timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%SZ")
                    filters.append(f"receivedDateTime ge {cutoff}")
                elif token.startswith("after:"):
                    date_str = token.split(":", 1)[1].replace("/", "-")
                    filters.append(f"receivedDateTime ge {date_str}T00:00:00Z")
                elif token.startswith("from:"):
                    search_q = (search_q or "") + f' "from:{token.split(":",1)[1]}"'
            if filters:
                params["$filter"] = " and ".join(filters)
            if search_q:
                params["$search"] = search_q.strip()
            data = self._get("/me/messages", params)
            messages = []
            for m in data.get("value", []):
                sender = m.get("from", {}).get("emailAddress", {}).get("address", "")
                messages.append(MailMessage(
                    id=m.get("id", ""),
                    subject=m.get("subject", "") or "",
                    sender=sender,
                    body=(m.get("bodyPreview", "") or "")[:500],
                    date=m.get("receivedDateTime", ""),
                    source="microsoft",
                ))
            return messages
        except Exception as e:
            logger.warning("[MSConnector] search_mail: %s", e)
            return []

    def get_agenda(self, days: int = 7) -> list[CalendarEvent]:
        try:
            from datetime import datetime, timezone, timedelta
            now = datetime.now(timezone.utc)
            end = now + timedelta(days=days)
            data = self._get("/me/calendarView", {
                "startDateTime": now.isoformat(),
                "endDateTime": end.isoformat(),
                "$select": "id,subject,start,end,location,bodyPreview,attendees,isAllDay",
                "$top": "50",
                "$orderby": "start/dateTime",
            })
            events = []
            for e in data.get("value", []):
                attendees = [
                    a.get("emailAddress", {}).get("address", "")
                    for a in e.get("attendees", [])
                    if a.get("emailAddress", {}).get("address")
                ]
                events.append(CalendarEvent(
                    id=e.get("id", ""),
                    title=e.get("subject", ""),
                    start=e.get("start", {}).get("dateTime", ""),
                    end=e.get("end", {}).get("dateTime", ""),
                    location=e.get("location", {}).get("displayName", ""),
                    description=e.get("bodyPreview", ""),
                    attendees=attendees,
                    all_day=e.get("isAllDay", False),
                    source="microsoft",
                    calendar_email=self.email,
                ))
            return events
        except Exception as e:
            logger.warning("[MSConnector] get_agenda: %s", e)
            return []

    def create_event(self, title: str, start: str, end: str,
                     location: str = "", description: str = "",
                     attendees: list = None) -> dict:
        try:
            body = {
                "subject": title,
                "start": {"dateTime": start, "timeZone": "Europe/Paris"},
                "end":   {"dateTime": end,   "timeZone": "Europe/Paris"},
            }
            if location:
                body["location"] = {"displayName": location}
            if description:
                body["body"] = {"contentType": "text", "content": description}
            if attendees:
                body["attendees"] = [
                    {"emailAddress": {"address": a}, "type": "required"}
                    for a in attendees if "@" in a
                ]
            result = self._post("/me/events", body)
            return {"ok": True, "message": f"Événement '{title}' créé dans Outlook.", "id": result.get("id", "")}
        except Exception as e:
            return {"ok": False, "message": str(e)[:100]}

    def update_event(self, event_id: str, **kwargs) -> dict:
        try:
            import requests
            body = {}
            if "title" in kwargs:   body["subject"] = kwargs["title"]
            if "start" in kwargs:   body["start"] = {"dateTime": kwargs["start"], "timeZone": "Europe/Paris"}
            if "end" in kwargs:     body["end"]   = {"dateTime": kwargs["end"],   "timeZone": "Europe/Paris"}
            if "location" in kwargs: body["location"] = {"displayName": kwargs["location"]}
            r = requests.patch(f"{_GRAPH}/me/events/{event_id}",
                               headers={"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"},
                               json=body, timeout=10)
            r.raise_for_status()
            return {"ok": True, "message": "Événement mis à jour."}
        except Exception as e:
            return {"ok": False, "message": str(e)[:100]}

    def delete_event(self, event_id: str) -> dict:
        try:
            import requests
            r = requests.delete(f"{_GRAPH}/me/events/{event_id}",
                                headers={"Authorization": f"Bearer {self.token}"}, timeout=10)
            r.raise_for_status()
            return {"ok": True, "message": "Événement supprimé."}
        except Exception as e:
            return {"ok": False, "message": str(e)[:100]}
