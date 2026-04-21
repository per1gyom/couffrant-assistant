"""
Endpoints webhooks Raya.

Pipeline Microsoft Graph (5 niveaux) :
  1a. Whitelist Raya (mail_filter autoriser:) → court-circuite le filtre statique
  1b. Filtre heuristique statique (noreply / newsletters / bulk domains)
  1c. Blacklist Raya (mail_filter bloquer:) → bloc supplémentaire
  2.  Règles anti_spam personnalisées
  3.  Triage Haiku : IGNORER / STOCKER_SIMPLE / ANALYSER
  4.  Analyse complète ou stockage simple + stockage
  5.  Scoring d'urgence + alerte shadow ou réelle (Phase 7)

process_incoming_mail() est source-agnostic (7-1b) :
consommé par le webhook Microsoft ET le polling Gmail.

7-7 : heartbeat webhook_microsoft après traitement réussi.
7-8 : endpoint POST /webhook/twilio (WhatsApp entrant).
USER-PHONE : _resolve_user_by_phone cherche d'abord en base (colonne phone),
             puis tombe sur les variables d'env pour la compatibilité.
WHATSAPP-RAYA : texte libre WhatsApp → vraie réponse LLM de Raya (Sonnet,
                max 512 tokens), sauvegardée dans aria_memory.
"""
import re
import threading
from fastapi import APIRouter, Request, Response

# Import du handler qui traite effectivement chaque mail. Sans cet import,
# le thread lance dans webhook_notification() leve un NameError sur
# _process_mail des qu un webhook Microsoft arrive (bug silencieux pour
# l utilisateur mais visible dans les logs Railway).
from app.routes.webhook_ms_handlers import _process_mail

router = APIRouter(tags=["webhook"])


# ─── PATTERNS STATIQUES (filet de base) ───

_NOREPLY_PREFIXES = (
    "noreply@", "no-reply@", "no_reply@", "donotreply@",
    "do-not-reply@", "mailer-daemon@", "postmaster@",
    "bounce@", "bounces@", "notifications@", "notification@",
    "newsletter@", "newsletters@", "alerts@", "alert@",
    "automated@", "auto@", "system@", "support-noreply@",
    "info@noreply.", "reply@",
)

_BULK_DOMAINS = (
    "sendgrid.net", "sendgrid.com", "mailchimp.com", "mandrillapp.com",
    "mailgun.org", "hubspot.com", "salesforce.com", "marketo.com",
    "constantcontact.com", "campaign-monitor.com", "klaviyo.com",
    "brevo.com", "sendinblue.com", "mailjet.com",
    "amazonses.com", "bounce.linkedin.com", "facebookmail.com",
    "twitter.com", "notifications.google.com",
)

_BULK_SUBJECT_KEYWORDS = (
    "unsubscribe", "se désabonner", "newsletter", "digest",
    "weekly recap", "rapport hebdomadaire", "monthly report",
    "invoice #", "facture n°", "receipt for", "reçu de",
    "your order", "votre commande", "order confirmation",
    "confirmation de commande", "tracking", "livraison",
    "automated message", "message automatique",
    "do not reply", "ne pas répondre",
    "verification code", "code de vérification",
    "one-time password", "mot de passe à usage unique",
)


# ─── RÈGLES RAYA (mail_filter) ───
# ─── PIPELINE COMMUN (source-agnostic) ───
@router.get("/webhook/microsoft")
async def webhook_validation_get(validationToken: str = ""):
    if validationToken:
        return Response(content=validationToken, media_type="text/plain", status_code=200)
    return Response(status_code=200)


@router.post("/webhook/microsoft")
async def webhook_notification(request: Request):
    validation_token = request.query_params.get("validationToken")
    if validation_token:
        return Response(content=validation_token, media_type="text/plain", status_code=200)

    try:
        body = await request.json()
    except Exception:
        return Response(status_code=202)

    from app.connectors.microsoft_webhook import get_subscription_info
    from app.mail_memory_store import mail_exists

    for notification in body.get("value", []):
        subscription_id = notification.get("subscriptionId", "")
        sub_info = get_subscription_info(subscription_id)
        if not sub_info:
            continue
        if notification.get("clientState") != sub_info["client_state"]:
            continue

        username = sub_info["username"]
        resource = notification.get("resource", "")
        resource_data = notification.get("resourceData") or {}
        message_id = resource_data.get("id") or ""
        if not message_id and "Messages/" in resource:
            message_id = resource.split("Messages/")[-1]

        if not message_id or mail_exists(message_id, username):
            continue

        threading.Thread(
            target=_process_mail,
            args=(username, message_id),
            daemon=True
        ).start()

    return Response(status_code=202)


@router.post("/webhook/twilio")
async def webhook_twilio(request: Request):
    """
    Webhook Twilio pour les messages WhatsApp entrants. (7-8)
    L'utilisateur répond à un message Raya depuis WhatsApp.
    """
    try:
        form = await request.form()
        from_number = form.get("From", "").replace("whatsapp:", "").strip()
        body = form.get("Body", "").strip()

        if not from_number or not body:
            return Response(status_code=200)

        username = _resolve_user_by_phone(from_number)
        if not username:
            print(f"[Twilio] Numéro inconnu : {from_number}")
            return Response(status_code=200)

        threading.Thread(
            target=_handle_whatsapp_command,
            args=(username, body, from_number),
            daemon=True,
        ).start()

    except Exception as e:
        print(f"[Twilio] Erreur webhook: {e}")

    return Response(status_code=200)

