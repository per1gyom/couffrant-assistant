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


def send_whatsapp_structured(to: str, title: str, body: str,
                             options: list = None) -> dict:
    """
    Envoie un message WhatsApp structure avec des options de reponse rapide (7-3).

    Twilio WhatsApp ne supporte pas nativement les boutons interactifs
    sans template approuve. On formate un message texte structure avec
    des numeros de reponse rapide.

    Exemple de message envoye :
      \U0001f7e0 Raya — Mail important

      De : dupont@client.fr
      Sujet : Relance chantier photovoltaique
      Resume : Dupont demande un point sur l'avancement...

      Repondre :
      1\ufe0f\u20e3 Oui, reponds pour moi
      2\ufe0f\u20e3 Je m'en occupe
      3\ufe0f\u20e3 Rappelle-moi dans 1h
    """
    client = _get_client()
    if not client:
        return {"status": "disabled"}

    from_number = os.getenv("TWILIO_WHATSAPP_FROM", "").strip()
    if not from_number:
        return {"status": "error", "message": "TWILIO_WHATSAPP_FROM non defini"}

    if not to.startswith("whatsapp:"):
        to = f"whatsapp:{to}"
    if not from_number.startswith("whatsapp:"):
        from_number = f"whatsapp:{from_number}"

    # Construction du message structure
    lines = [title, "", body]
    if options:
        lines.append("")
        lines.append("Répondre :")
        emojis = ["1\ufe0f\u20e3", "2\ufe0f\u20e3", "3\ufe0f\u20e3", "4\ufe0f\u20e3"]
        for i, opt in enumerate(options[:4]):
            lines.append(f"  {emojis[i]} {opt}")

    message = "\n".join(lines)[:1600]

    try:
        msg = client.messages.create(body=message, from_=from_number, to=to)
        logger.info(f"[Twilio] WhatsApp structure envoye a {to}")
        return {"status": "ok", "sid": msg.sid}
    except Exception as e:
        logger.error(f"[Twilio] Erreur WhatsApp structure: {e}")
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
