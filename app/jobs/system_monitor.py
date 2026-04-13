"""
Job de monitoring système — vérifie les composants + alerte WhatsApp/SMS. (7-7)
USER-PHONE : utilise get_user_phone(admin) pour la résolution du numéro.

FIX-MONITOR-SPAM :
  - Seuils différenciés par type de composant :
      * scheduler, proactivity_scan, heartbeat_morning : 15 min (actifs en permanence)
      * webhook_microsoft, gmail_polling : 60 min (passifs — actifs seulement si mail)
  - Anti-répétition : une même alerte ne peut pas être renvoyée avant 6h (cooldown)
"""
import os
from datetime import datetime, timedelta
from app.logging_config import get_logger

logger = get_logger("raya.scheduler")

# ─── Cooldown anti-spam ───
# {composant: datetime_derniere_alerte}
_LAST_ALERT_SENT: dict = {}
_ALERT_COOLDOWN_HOURS = 6

# ─── Seuils d'inactivité par composant ───
# Les composants "passifs" (webhook mail) ne sont actifs que quand un mail arrive.
# Un silence prolongé est NORMAL — 60 min avant alerte.
_PASSIVE_COMPONENTS = {"webhook_microsoft", "gmail_polling"}
_THRESHOLD_ACTIVE_MIN   = 15   # scheduler et autres → alerte après 15 min
_THRESHOLD_PASSIVE_MIN  = 60   # webhook mail → alerte après 60 min


def _is_in_cooldown(component: str) -> bool:
    """Retourne True si une alerte pour ce composant a déjà été envoyée récemment."""
    last = _LAST_ALERT_SENT.get(component)
    if last is None:
        return False
    return datetime.utcnow() - last < timedelta(hours=_ALERT_COOLDOWN_HOURS)


def _mark_alert_sent(component: str) -> None:
    """Enregistre le timestamp d'envoi de l'alerte pour ce composant."""
    _LAST_ALERT_SENT[component] = datetime.utcnow()


def _job_system_monitor():
    """Vérifie que tous les composants critiques sont actifs — toutes les 10 min."""
    try:
        from app.database import get_pg_conn

        conn = get_pg_conn()
        c = conn.cursor()

        # Heartbeat scheduler (ce job lui-même prouve que le scheduler tourne)
        c.execute("""
            INSERT INTO system_heartbeat (component, last_seen_at, status)
            VALUES ('scheduler', NOW(), 'ok')
            ON CONFLICT (component)
            DO UPDATE SET last_seen_at = NOW(), status = 'ok'
        """)
        conn.commit()

        # Seuil actif (15 min) — composants toujours en marche
        threshold_active  = datetime.utcnow() - timedelta(minutes=_THRESHOLD_ACTIVE_MIN)
        # Seuil passif (60 min) — composants mail, inactifs entre les mails
        threshold_passive = datetime.utcnow() - timedelta(minutes=_THRESHOLD_PASSIVE_MIN)

        # Requête : composants stale avec seuil adapté
        c.execute("""
            SELECT component, last_seen_at, status FROM system_heartbeat
            WHERE status != 'disabled'
              AND (
                (component = ANY(%s) AND last_seen_at < %s)
                OR
                (component != ALL(%s) AND last_seen_at < %s)
              )
        """, (
            list(_PASSIVE_COMPONENTS), threshold_passive,
            list(_PASSIVE_COMPONENTS), threshold_active,
        ))
        stale_rows = c.fetchall()
        conn.close()

        if not stale_rows:
            return

        # Filtrer les composants déjà alertés récemment (cooldown 6h)
        to_alert = []
        for component, last_seen, status in stale_rows:
            if _is_in_cooldown(component):
                logger.debug(f"[Monitor] {component} stale mais en cooldown, pas d'alerte")
            else:
                to_alert.append(component)

        if not to_alert:
            return

        logger.warning(f"[Monitor] Composants inactifs à alerter : {to_alert}")
        _send_monitor_alert(to_alert)

        # Enregistrer le cooldown pour chaque composant alerté
        for component in to_alert:
            _mark_alert_sent(component)

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
        phone = os.getenv("NOTIFICATION_PHONE_ADMIN", "").strip()
        if not phone:
            phone = os.getenv("NOTIFICATION_PHONE_GUILLAUME", "").strip()
        if not phone:
            phone = os.getenv("NOTIFICATION_PHONE_DEFAULT", "").strip()

    if not phone:
        return

    # Message adapté au seuil : mentionner la durée réelle d'inactivité
    passive = [c for c in stale_components if c in _PASSIVE_COMPONENTS]
    active  = [c for c in stale_components if c not in _PASSIVE_COMPONENTS]

    parts = []
    if active:
        parts.append(f"⏱ >{_THRESHOLD_ACTIVE_MIN}min sans activité : {', '.join(active)}")
    if passive:
        parts.append(f"⏱ >{_THRESHOLD_PASSIVE_MIN}min sans mail entrant : {', '.join(passive)}")

    message = (
        f"⚠️ Raya Monitor — Composant(s) inactif(s) :\n"
        + "\n".join(parts)
        + "\nVérifier Railway si suspect."
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
