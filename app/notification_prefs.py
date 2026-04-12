"""
Préférences de notification de Raya — Phase 7 (7-5).

Gère les plages silencieuses, les contacts VIP et le canal préféré.
Les préférences sont stockées dans users.notification_prefs (JSONB).

Format du JSONB :
{
  "quiet_start": "22:00",
  "quiet_end": "07:00",
  "quiet_except_critical": true,
  "vip_emails": ["banque@example.com"],
  "vip_domains": ["@ma-banque.fr"],
  "vip_boost": 30,
  "calendar_aware": true,
  "preferred_channel": "whatsapp"   # whatsapp | sms | chat_only
}
"""

DEFAULTS = {
    "quiet_start": "22:00",
    "quiet_end": "07:00",
    "quiet_except_critical": True,
    "vip_emails": [],
    "vip_domains": [],
    "vip_boost": 30,
    "calendar_aware": True,
    "preferred_channel": "whatsapp",
}


def get_notification_prefs(username: str) -> dict:
    """Retourne les préférences de notification, avec valeurs par défaut."""
    conn = None
    try:
        from app.database import get_pg_conn
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("SELECT notification_prefs FROM users WHERE username = %s", (username,))
        row = c.fetchone()
        if row and row[0]:
            return {**DEFAULTS, **row[0]}
        return dict(DEFAULTS)
    except Exception:
        return dict(DEFAULTS)
    finally:
        if conn: conn.close()


def is_quiet_hours(username: str) -> bool:
    """True si on est dans la plage silencieuse de l'utilisateur."""
    from datetime import datetime
    prefs = get_notification_prefs(username)
    now = datetime.now().strftime("%H:%M")
    start = prefs["quiet_start"]
    end = prefs["quiet_end"]
    # Gère le passage de minuit (ex. 22:00 → 07:00)
    if start > end:
        return now >= start or now < end
    return start <= now < end


def is_vip_sender(sender: str, username: str) -> bool:
    """True si l'expéditeur est VIP pour cet utilisateur."""
    prefs = get_notification_prefs(username)
    sender_lower = sender.lower()
    if sender_lower in [e.lower() for e in prefs.get("vip_emails", [])]:
        return True
    return any(sender_lower.endswith(d.lower()) for d in prefs.get("vip_domains", []))


def should_notify(username: str, urgency_level: str) -> bool:
    """
    Détermine si on doit envoyer une notification externe maintenant.
    - chat_only : jamais de WhatsApp
    - plage silencieuse : uniquement critique si quiet_except_critical=True
    - sinon : important + critique passent
    """
    prefs = get_notification_prefs(username)
    if prefs["preferred_channel"] == "chat_only":
        return False
    if is_quiet_hours(username):
        if urgency_level == "critical" and prefs["quiet_except_critical"]:
            return True
        return False
    return urgency_level in ("important", "critical")
