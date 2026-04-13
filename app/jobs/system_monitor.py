"""
Job de monitoring système — vérifie les composants + alerte WhatsApp/SMS. (7-7)
USER-PHONE : utilise get_user_phone(admin) pour la résolution du numéro.
"""
import os
from app.logging_config import get_logger

logger = get_logger("raya.scheduler")


def _job_system_monitor():
    """Vérifie que tous les composants critiques sont actifs — toutes les 10 min."""
    try:
        from app.database import get_pg_conn
        from datetime import datetime, timedelta

        conn = get_pg_conn()
        c = conn.cursor()
        # Heartbeat scheduler
        c.execute("""
            INSERT INTO system_heartbeat (component, last_seen_at, status)
            VALUES ('scheduler', NOW(), 'ok')
            ON CONFLICT (component)
            DO UPDATE SET last_seen_at = NOW(), status = 'ok'
        """)
        conn.commit()

        # Détection des composants inactifs (>15 min)
        threshold = datetime.utcnow() - timedelta(minutes=15)
        c.execute("""
            SELECT component, last_seen_at, status FROM system_heartbeat
            WHERE last_seen_at < %s AND status != 'disabled'
        """, (threshold,))
        stale = c.fetchall()
        conn.close()

        if stale:
            stale_names = [r[0] for r in stale]
            logger.warning(f"[Monitor] Composants inactifs : {stale_names}")
            _send_monitor_alert(stale_names)

    except Exception as e:
        logger.error(f"[Monitor] ERREUR: {e}")


def _send_monitor_alert(stale_components: list):
    """
    Envoie une alerte monitoring via WhatsApp (fallback SMS). (7-7)
    Utilise get_user_phone() pour trouver le numéro de l'admin en base
    ou dans les variables d'environnement (USER-PHONE).
    """
    admin_username = os.getenv("APP_USERNAME", "guillaume").strip()
    try:
        from app.security_users import get_user_phone
        phone = get_user_phone(admin_username)
    except Exception:
        # Fallback direct si security_users non disponible
        phone = os.getenv("NOTIFICATION_PHONE_ADMIN", "").strip()
        if not phone:
            phone = os.getenv("NOTIFICATION_PHONE_GUILLAUME", "").strip()
        if not phone:
            phone = os.getenv("NOTIFICATION_PHONE_DEFAULT", "").strip()

    if not phone:
        return

    message = (
        f"\u26a0\ufe0f Raya Monitor — Composant(s) inactif(s) depuis >15min :\n"
        f"{', '.join(stale_components)}\nVérifier Railway."
    )
    try:
        from app.connectors.twilio_connector import send_whatsapp, send_sms
        result = send_whatsapp(phone, message)
        if result.get("status") != "ok":
            send_sms(phone, message)
    except Exception:
        try:
            from app.connectors.twilio_connector import send_sms
            send_sms(phone, message)
        except Exception as e:
            logger.error(f"[Monitor] Impossible d'alerter: {e}")
