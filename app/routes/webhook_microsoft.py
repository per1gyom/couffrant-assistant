"""
Handler Microsoft Graph mail.
Extrait de webhook.py -- SPLIT-R3.
"""
import json,re,threading
from datetime import datetime
from app.database import get_pg_conn
from app.token_manager import get_valid_microsoft_token
from app.logging_config import get_logger
logger=get_logger("raya.webhook.ms")


def _process_mail(username: str, message_id: str):
    """
    Pipeline Microsoft — récupère le mail via Graph puis appelle process_incoming_mail.
    """
    try:
        from app.token_manager import get_valid_microsoft_token
        from app.graph_client import graph_get
        from app.mail_memory_store import mail_exists

        token = get_valid_microsoft_token(username)
        if not token:
            return
        if mail_exists(message_id, username):
            return

        try:
            msg = graph_get(token, f"/me/messages/{message_id}", params={
                "$select": "id,subject,from,receivedDateTime,bodyPreview,body,isRead"
            })
        except Exception as e:
            print(f"[Webhook] Erreur récupération mail {username}: {e}")
            return

        sender = msg.get("from", {}).get("emailAddress", {}).get("address", "")
        subject = msg.get("subject", "") or ""
        preview = msg.get("bodyPreview", "") or ""
        received_at = msg.get("receivedDateTime", "")
        raw_body = msg.get("body", {}).get("content", "")

        process_incoming_mail(
            username=username, sender=sender, subject=subject,
            preview=preview, message_id=message_id,
            received_at=received_at, mailbox_source="outlook",
            raw_body=raw_body,
        )
    except Exception as e:
        print(f"[Webhook] Erreur {username}/{message_id}: {e}")

