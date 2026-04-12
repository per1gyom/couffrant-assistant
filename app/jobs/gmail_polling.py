"""
Job de polling Gmail pour les utilisateurs avec credentials OAuth2. (7-1b)
"""
from app.logging_config import get_logger

logger = get_logger("raya.scheduler")


def _job_gmail_polling():
    """Polling Gmail toutes les 3 min — désactivé par défaut (SCHEDULER_GMAIL_ENABLED)."""
    try:
        from app.connectors.gmail_connector import fetch_new_messages, is_configured
        from app.routes.webhook import process_incoming_mail
        from app.database import get_pg_conn

        if not is_configured():
            logger.info("[Gmail] GMAIL_CLIENT_ID / GMAIL_CLIENT_SECRET non configurés, skip")
            return

        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("SELECT username FROM users WHERE gmail_credentials IS NOT NULL")
        gmail_users = [r[0] for r in c.fetchall()]
        conn.close()

        if not gmail_users:
            return

        total = 0
        for username in gmail_users:
            try:
                messages = fetch_new_messages(username, max_results=20)
                for msg in messages:
                    process_incoming_mail(
                        username=username,
                        sender=msg["sender"],
                        subject=msg["subject"],
                        preview=msg["preview"],
                        message_id=msg["message_id"],
                        received_at=msg["received_at"],
                        mailbox_source="gmail",
                    )
                    total += 1
            except Exception as e:
                logger.error(f"[Gmail] Erreur polling {username}: {e}")

        if total > 0:
            logger.info(f"[Gmail] {total} nouveau(x) mail(s) traité(s)")

        # Heartbeat monitoring (7-7)
        try:
            from app.database import get_pg_conn as _hb_get
            _hb = _hb_get()
            _hb_c = _hb.cursor()
            _hb_c.execute("""
                INSERT INTO system_heartbeat (component, last_seen_at, status)
                VALUES ('gmail_polling', NOW(), 'ok')
                ON CONFLICT (component)
                DO UPDATE SET last_seen_at = NOW(), status = 'ok'
            """)
            _hb.commit()
            _hb.close()
        except Exception:
            pass

    except Exception as e:
        logger.error(f"[Gmail] ERREUR polling: {e}")
