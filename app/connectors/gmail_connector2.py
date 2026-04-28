"""
GmailConnector — implémentation Google API pour MailboxConnector.
Contacts : Google People API
Mail     : Gmail API
"""
from __future__ import annotations
from app.connectors.mailbox_connector import MailboxConnector, Contact, MailMessage, CalendarEvent
from app.logging_config import get_logger

logger = get_logger("raya.gmail_connector2")
_PEOPLE = "https://people.googleapis.com/v1"
_GMAIL  = "https://gmail.googleapis.com/gmail/v1/users/me"


class GmailConnector(MailboxConnector):

    @property
    def provider(self) -> str:
        return "gmail"

    def _get(self, url: str, params: dict = None):
        import requests
        r = requests.get(url, headers={"Authorization": f"Bearer {self.token}"},
                         params=params or {}, timeout=10)
        if r.status_code == 403:
            logger.warning("[GmailConnector] 403 — scope manquant pour %s", url)
            return {}
        r.raise_for_status()
        return r.json()

    def _post(self, url: str, body: dict):
        import requests
        r = requests.post(url, headers={"Authorization": f"Bearer {self.token}",
                          "Content-Type": "application/json"}, json=body, timeout=10)
        r.raise_for_status()
        return r.json()

    # --- CONTACTS ---

    def search_contacts(self, query: str) -> list[Contact]:
        try:
            data = self._get(f"{_PEOPLE}/people:searchContacts", {
                "query": query, "readMask": "names,emailAddresses,phoneNumbers", "pageSize": 10,
            })
            return self._parse_people(data.get("results", []))
        except Exception as e:
            logger.warning("[GmailConnector] search_contacts: %s", e)
            return []

    def list_contacts(self, max_results: int = 100) -> list[Contact]:
        try:
            data = self._get(f"{_PEOPLE}/people/me/connections", {
                "personFields": "names,emailAddresses,phoneNumbers",
                "pageSize": min(max_results, 1000),
            })
            return self._parse_people([{"person": p} for p in data.get("connections", [])])
        except Exception as e:
            logger.warning("[GmailConnector] list_contacts: %s", e)
            return []

    def create_contact(self, name: str, email: str, phone: str = "") -> dict:
        try:
            body = {"names": [{"displayName": name}], "emailAddresses": [{"value": email}]}
            if phone: body["phoneNumbers"] = [{"value": phone}]
            self._post(f"{_PEOPLE}/people:createContact", body)
            return {"ok": True, "message": f"Contact '{name}' créé dans Gmail."}
        except Exception as e:
            return {"ok": False, "message": str(e)[:100]}

    # --- MAIL ---

    def send_mail(self, to: str, subject: str, body: str, from_email: str = "") -> dict:
        try:
            from app.connectors.gmail_connector import send_gmail_message
            body_html = body.replace('\n', '<br>\n')
            result = send_gmail_message(self.username, to, subject, body_html)
            return result
        except Exception as e:
            return {"ok": False, "message": str(e)[:100]}

    def create_draft(self, to: str, subject: str, body: str) -> dict:
        try:
            import base64
            from email.mime.multipart import MIMEMultipart
            from email.mime.text import MIMEText
            from app.connectors.gmail_connector import get_gmail_service
            service = get_gmail_service(self.username)
            if not service:
                return {"ok": False, "message": "Gmail non connecté"}
            msg = MIMEMultipart("alternative")
            msg["To"] = to; msg["Subject"] = subject
            msg.attach(MIMEText(body.replace('\n','<br>\n'), "html", "utf-8"))
            raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
            service.users().drafts().create(userId="me", body={"message": {"raw": raw}}).execute()
            return {"ok": True, "message": "Brouillon Gmail créé."}
        except Exception as e:
            return {"ok": False, "message": str(e)[:100]}

    def search_mail(self, query: str, max_results: int = 10) -> list[MailMessage]:
        """Recherche dans la boite Gmail via l API users/messages/list.
        Query : syntaxe Gmail standard (ex 'is:unread', 'newer_than:5m',
        'from:foo@bar.com', 'after:2024/01/01').
        Retourne list[MailMessage] avec id, subject, sender, body (snippet),
        date, source. Tronque a max_results (defaut 10, max 500 par appel).
        """
        try:
            data = self._get(f"{_GMAIL}/messages", {
                "q": query,
                "maxResults": str(min(max_results, 500)),
            })
            message_ids = [m.get("id") for m in data.get("messages", []) if m.get("id")]
            if not message_ids:
                return []
            messages = []
            for msg_id in message_ids:
                try:
                    msg = self._get(f"{_GMAIL}/messages/{msg_id}", {
                        "format": "metadata",
                        "metadataHeaders": "From,Subject,Date",
                    })
                    headers = {h["name"].lower(): h["value"]
                               for h in msg.get("payload", {}).get("headers", [])}
                    messages.append(MailMessage(
                        id=msg_id,
                        subject=headers.get("subject", ""),
                        sender=headers.get("from", ""),
                        body=msg.get("snippet", "")[:500],
                        date=headers.get("date", ""),
                        source="gmail",
                    ))
                except Exception as e:
                    logger.warning("[GmailConnector] search_mail get %s: %s", msg_id, e)
                    continue
            return messages
        except Exception as e:
            logger.warning("[GmailConnector] search_mail: %s", e)
            return []

    # --- AGENDA (Google Calendar) ---

    def get_agenda(self, days: int = 7) -> list[CalendarEvent]:
        try:
            from datetime import datetime, timezone, timedelta
            now = datetime.now(timezone.utc)
            end = now + timedelta(days=days)
            data = self._get("https://www.googleapis.com/calendar/v3/calendars/primary/events", {
                "timeMin": now.isoformat(),
                "timeMax": end.isoformat(),
                "orderBy": "startTime",
                "singleEvents": "true",
                "maxResults": "50",
            })
            events = []
            for e in data.get("items", []):
                start_data = e.get("start", {})
                end_data   = e.get("end",   {})
                start = start_data.get("dateTime") or start_data.get("date", "")
                end   = end_data.get("dateTime")   or end_data.get("date", "")
                all_day = "date" in start_data and "dateTime" not in start_data
                attendees = [a.get("email", "") for a in e.get("attendees", []) if a.get("email")]
                events.append(CalendarEvent(
                    id=e.get("id", ""),
                    title=e.get("summary", ""),
                    start=start,
                    end=end,
                    location=e.get("location", ""),
                    description=e.get("description", ""),
                    attendees=attendees,
                    all_day=all_day,
                    source="gmail",
                    calendar_email=self.email,
                ))
            return events
        except Exception as e:
            logger.warning("[GmailConnector] get_agenda: %s", e)
            return []

    def create_event(self, title: str, start: str, end: str,
                     location: str = "", description: str = "",
                     attendees: list = None) -> dict:
        try:
            body = {
                "summary": title,
                "start":   {"dateTime": start, "timeZone": "Europe/Paris"},
                "end":     {"dateTime": end,   "timeZone": "Europe/Paris"},
            }
            if location:    body["location"] = location
            if description: body["description"] = description
            if attendees:
                body["attendees"] = [{"email": a} for a in attendees if "@" in a]
            data = self._post(
                "https://www.googleapis.com/calendar/v3/calendars/primary/events",
                body
            )
            return {"ok": True, "message": f"Événement '{title}' créé dans Google Calendar.", "id": data.get("id", "")}
        except Exception as e:
            return {"ok": False, "message": str(e)[:100]}

    def update_event(self, event_id: str, **kwargs) -> dict:
        try:
            import requests
            body = {}
            if "title"    in kwargs: body["summary"]  = kwargs["title"]
            if "location" in kwargs: body["location"] = kwargs["location"]
            if "start"    in kwargs: body["start"] = {"dateTime": kwargs["start"], "timeZone": "Europe/Paris"}
            if "end"      in kwargs: body["end"]   = {"dateTime": kwargs["end"],   "timeZone": "Europe/Paris"}
            url = f"https://www.googleapis.com/calendar/v3/calendars/primary/events/{event_id}"
            r = requests.patch(url, headers={"Authorization": f"Bearer {self.token}",
                               "Content-Type": "application/json"}, json=body, timeout=10)
            if r.status_code == 403:
                return {"ok": False, "message": "Scope calendar manquant — reconnectez Gmail."}
            r.raise_for_status()
            return {"ok": True, "message": "Événement mis à jour."}
        except Exception as e:
            return {"ok": False, "message": str(e)[:100]}

    def delete_event(self, event_id: str) -> dict:
        try:
            import requests
            url = f"https://www.googleapis.com/calendar/v3/calendars/primary/events/{event_id}"
            r = requests.delete(url, headers={"Authorization": f"Bearer {self.token}"}, timeout=10)
            if r.status_code == 403:
                return {"ok": False, "message": "Scope calendar manquant — reconnectez Gmail."}
            r.raise_for_status()
            return {"ok": True, "message": "Événement supprimé."}
        except Exception as e:
            return {"ok": False, "message": str(e)[:100]}

    def _parse_people(self, results: list) -> list[Contact]:
        contacts = []
        for r in results:
            person = r.get("person", r)
            names  = person.get("names", [])
            emails = person.get("emailAddresses", [])
            phones = person.get("phoneNumbers", [])
            name   = names[0].get("displayName", "") if names else ""
            email  = emails[0].get("value", "") if emails else ""
            phone  = phones[0].get("value", "") if phones else ""
            if name or email:
                contacts.append(Contact(name=name, email=email, phone=phone, source="gmail"))
        return contacts
