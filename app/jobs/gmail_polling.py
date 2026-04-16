"""
Job de polling Gmail pour les utilisateurs avec credentials OAuth2 V2.
"""
from app.logging_config import get_logger

logger = get_logger("raya.scheduler")


def _job_gmail_polling():
    """Polling Gmail toutes les 3 min pour les users avec connexion Gmail V2."""
    try:
        from app.connection_token_manager import get_all_users_with_tool_connections
        from app.routes.webhook import process_incoming_mail

        users = get_all_users_with_tool_connections("gmail")
        if not users:
            return

        total = 0
        for username in users:
            try:
                from app.connectors.gmail_connector2 import GmailConnector
                from app.connection_token_manager import get_connection_token, get_connection_email
                token = get_connection_token(username, "gmail")
                email = get_connection_email(username, "gmail")
                if not token:
                    continue
                connector = GmailConnector(username=username, email=email, token=token)
                messages = connector.search_mail("is:unread newer_than:5m", max_results=10)
                for msg in messages:
                    process_incoming_mail(
                        username=username,
                        sender=msg.sender,
                        subject=msg.subject,
                        preview=msg.body[:300],
                        message_id=msg.id,
                        received_at=msg.date,
                        mailbox_source="gmail",
                    )
                    total += 1
            except Exception as e:
                logger.error(f"[Gmail] Erreur polling {username}: {e}")

        if total > 0:
            logger.info(f"[Gmail] {total} nouveau(x) mail(s) traité(s)")

        # Heartbeat
        try:
            from app.database import get_pg_conn as _hb_get
            _hb = _hb_get(); _hb_c = _hb.cursor()
            _hb_c.execute("""
                INSERT INTO system_heartbeat (component, last_seen_at, status)
                VALUES ('gmail_polling', NOW(), 'ok')
                ON CONFLICT (component) DO UPDATE SET last_seen_at=NOW(), status='ok'
            """)
            _hb.commit(); _hb.close()
        except Exception:
            pass

    except Exception as e:
        logger.error(f"[Gmail] ERREUR polling: {e}")
