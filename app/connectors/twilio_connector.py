"""
Connecteur Twilio pour notifications sortantes (WhatsApp + SMS).

Variables d'environnement requises :
  TWILIO_ACCOUNT_SID   : SID du compte Twilio
  TWILIO_AUTH_TOKEN     : Token d'authentification
  TWILIO_WHATSAPP_FROM  : Numero WhatsApp Twilio (format: whatsapp:+14155238886)
  TWILIO_SMS_FROM       : Numero SMS Twilio (format: +33xxxxxxxxx) — optionnel, fallback

Degradation gracieuse si variables absentes — les fonctions retournent
{"status": "disabled"} sans erreur.
"""
import os
from app.logging_config import get_logger

logger = get_logger("raya.twilio")


def _get_client():
    """Retourne un client Twilio ou None si non configure."""
    sid = os.getenv("TWILIO_ACCOUNT_SID", "").strip()
    token = os.getenv("TWILIO_AUTH_TOKEN", "").strip()
    if not sid or not token:
        return None
    try:
        from twilio.rest import Client
        return Client(sid, token)
    except ImportError:
        logger.warning("[Twilio] twilio non installe — pip install twilio")
        return None
    except Exception as e:
        logger.error(f"[Twilio] Erreur init: {e}")
        return None


def is_available() -> bool:
    """True si Twilio est configure et operationnel."""
    return _get_client() is not None


def send_whatsapp(to: str, message: str) -> dict:
    """
    Envoie un message WhatsApp via Twilio.
    Args:
        to: numero destinataire (format: +33xxxxxxxxx, le prefixe whatsapp: est ajoute auto)
        message: texte du message (max 1600 chars, tronque si besoin)
    Returns:
        {"status": "ok", "sid": "..."} ou {"status": "error", "message": "..."}
        ou {"status": "disabled"} si non configure
    """
    client = _get_client()
    if not client:
        return {"status": "disabled", "message": "Twilio non configure"}
    from_number = os.getenv("TWILIO_WHATSAPP_FROM", "").strip()
    if not from_number:
        return {"status": "error", "message": "TWILIO_WHATSAPP_FROM non defini"}
    # Normalisation
    if not to.startswith("whatsapp:"):
        to = f"whatsapp:{to}"
    if not from_number.startswith("whatsapp:"):
        from_number = f"whatsapp:{from_number}"
    try:
        msg = client.messages.create(
            body=message[:1600],
            from_=from_number,
            to=to,
        )
        logger.info(f"[Twilio] WhatsApp envoye a {to} — SID: {msg.sid}")
        return {"status": "ok", "sid": msg.sid}
    except Exception as e:
        logger.error(f"[Twilio] Erreur envoi WhatsApp: {e}")
        return {"status": "error", "message": str(e)[:200]}


def send_sms(to: str, message: str) -> dict:
    """
    Envoie un SMS via Twilio (fallback si WhatsApp indisponible).
    Meme signature que send_whatsapp.
    """
    client = _get_client()
    if not client:
        return {"status": "disabled", "message": "Twilio non configure"}
    from_number = os.getenv("TWILIO_SMS_FROM", "").strip()
    if not from_number:
        return {"status": "error", "message": "TWILIO_SMS_FROM non defini"}
    try:
        msg = client.messages.create(
            body=message[:1600],
            from_=from_number,
            to=to,
        )
        logger.info(f"[Twilio] SMS envoye a {to} — SID: {msg.sid}")
        return {"status": "ok", "sid": msg.sid}
    except Exception as e:
        logger.error(f"[Twilio] Erreur envoi SMS: {e}")
        return {"status": "error", "message": str(e)[:200]}
