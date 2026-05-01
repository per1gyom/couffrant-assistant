"""
Job de polling Gmail pour les utilisateurs avec credentials OAuth2 V2.
Multi-boites 28/04 : itere sur TOUTES les connexions Gmail de chaque user.
"""
from app.logging_config import get_logger

logger = get_logger("raya.scheduler")


def _job_gmail_polling():
    """Polling Gmail toutes les 3 min pour les users avec connexion(s) Gmail V2.

    Multi-boites 28/04 : pour chaque user, on poll TOUTES ses connexions
    Gmail (pas juste la derniere). Si Guillaume a 6 boites Gmail, le job
    creera 6 connectors et fetcha les nouveaux mails de chacun.
    """
    try:
        from app.connection_token_manager import (
            get_all_users_with_tool_connections,
            get_all_user_connections,
        )
        # FIX 01/05/2026 : process_incoming_mail n est PAS dans webhook.py
        # mais dans webhook_ms_handlers.py (split SPLIT-F7). L import
        # incorrect faisait planter le polling Gmail a CHAQUE execution
        # depuis ~3 semaines (vu dans les logs Railway :
        # "[Gmail] ERREUR polling: cannot import name 'process_incoming_mail'
        # from 'app.routes.webhook'").
        from app.routes.webhook_ms_handlers import process_incoming_mail
        from app.connectors.gmail_connector2 import GmailConnector

        users = get_all_users_with_tool_connections("gmail")
        if not users:
            return

        total_mails = 0
        total_boxes = 0
        for username in users:
            try:
                # Recupere TOUTES les connexions de l user, filtre gmail
                all_conns = get_all_user_connections(username)
                gmail_conns = [c for c in all_conns
                               if c.get("tool_type", "").lower() in ("gmail", "google")
                               and c.get("token")]
                if not gmail_conns:
                    continue
                for conn in gmail_conns:
                    total_boxes += 1
                    email = conn.get("email", "") or "?"
                    try:
                        connector = GmailConnector(
                            username=username,
                            email=email,
                            token=conn["token"],
                        )
                        messages = connector.search_mail(
                            "is:unread newer_than:5m", max_results=10)
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
                            total_mails += 1
                    except Exception as e:
                        logger.error(
                            f"[Gmail] Erreur polling {username}/{email}: {e}")
            except Exception as e:
                logger.error(f"[Gmail] Erreur polling user {username}: {e}")

        if total_mails > 0 or total_boxes > 1:
            logger.info(
                f"[Gmail] Polling : {total_boxes} boite(s) verifiee(s), "
                f"{total_mails} nouveau(x) mail(s) traite(s)")

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
