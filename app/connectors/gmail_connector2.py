"""
GmailConnector — implémentation Google API pour MailboxConnector.
Contacts : Google People API
Mail     : Gmail API
"""
from __future__ import annotations
from app.connectors.mailbox_connector import MailboxConnector, Contact, MailMessage
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

    # --- HELPERS ---

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
