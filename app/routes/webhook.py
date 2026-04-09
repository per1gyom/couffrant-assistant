"""
Endpoint Microsoft Graph webhook.

Pipeline de filtrage à 4 niveaux :
  1a. Whitelist Raya (mail_filter autoriser:) → court-circuite le filtre statique
  1b. Filtre heuristique statique (noreply / newsletters / bulk domains)
  1c. Blacklist Raya (mail_filter bloquer:) → bloc supplémentaire
  2.  Règles anti_spam personnalisées
  3.  Micro-appel Claude OUI/NON
  4.  Analyse complète + stockage

Raya peut affiner le filtre statique via :
  [ACTION:LEARN:mail_filter|autoriser: dupont@example.com]
  [ACTION:LEARN:mail_filter|autoriser: @couffrant-solar.fr]
  [ACTION:LEARN:mail_filter|autoriser: sujet:devis chantier]
  [ACTION:LEARN:mail_filter|bloquer: promo@fournisseur.fr]
"""
import re
import threading
from fastapi import APIRouter, Request, Response

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

def _get_mail_filter_rules(username: str) -> tuple:
    """
    Charge les règles mail_filter que Raya a posées.
    Retourne (whitelist, blacklist).

    Formats supportés :
      autoriser: email@domaine.fr       → email exact
      autoriser: @couffrant-solar.fr    → domaine entier
      autoriser: sujet:devis chantier   → mot-clé dans le sujet
      bloquer:   promo@fournisseur.fr   → bloquer cet expéditeur
      bloquer:   sujet:pub              → bloquer ce mot-clé sujet
    """
    try:
        from app.memory_rules import get_rules_by_category
        rules = get_rules_by_category('mail_filter', username)
        whitelist, blacklist = [], []
        for rule in rules:
            rl = rule.strip().lower()
            if rl.startswith('autoriser:'):
                whitelist.append(rl[10:].strip())
            elif rl.startswith('bloquer:'):
                blacklist.append(rl[8:].strip())
        return whitelist, blacklist
    except Exception:
        return [], []


def _matches_filter(sender: str, subject: str, patterns: list) -> bool:
    """Vérifie si expéditeur ou sujet correspond à un pattern de filtre."""
    sender_l = sender.lower()
    subject_l = (subject or "").lower()
    for pattern in patterns:
        if pattern.startswith('@'):
            # Domaine entier : @couffrant-solar.fr
            if sender_l.endswith(pattern):
                return True
        elif pattern.startswith('sujet:'):
            # Mot-clé dans le sujet
            kw = pattern[6:].strip()
            if kw and kw in subject_l:
                return True
        else:
            # Email exact ou fragment
            if pattern in sender_l:
                return True
    return False


def _is_bulk_heuristic(sender: str, subject: str, preview: str) -> bool:
    """Niveau 1b — Filtre heuristique statique."""
    sender_lower = sender.lower()
    subject_lower = (subject or "").lower()

    if any(sender_lower.startswith(p) for p in _NOREPLY_PREFIXES):
        return True

    domain = sender_lower.split("@")[-1] if "@" in sender_lower else ""
    if any(bulk in domain for bulk in _BULK_DOMAINS):
        return True

    if any(kw in subject_lower for kw in _BULK_SUBJECT_KEYWORDS):
        return True

    preview_lower = (preview or "").lower()
    if "list-unsubscribe" in preview_lower or "view in browser" in preview_lower:
        return True

    return False


def _is_spam_by_rules(sender: str, subject: str, preview: str, username: str) -> bool:
    """Niveau 2 — Règles anti_spam personnalisées."""
    try:
        from app.memory_rules import get_antispam_keywords
        keywords = get_antispam_keywords(username)
        text = f"{sender} {subject} {preview}".lower()
        return any(kw in text for kw in keywords if kw)
    except Exception:
        return False


# ─── WEBHOOK ENDPOINTS ───

@router.get("/webhook/microsoft")
async def webhook_validation(validationToken: str = ""):
    if validationToken:
        return Response(content=validationToken, media_type="text/plain", status_code=200)
    return Response(status_code=200)


@router.post("/webhook/microsoft")
async def webhook_notification(request: Request):
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


def _process_mail(username: str, message_id: str):
    """
    Pipeline de filtrage :
      1a. Whitelist Raya → bypass heuristique si match
      1b. Heuristique statique
      1c. Blacklist Raya
      2.  Anti-spam personnalisé
      3.  Claude OUI/NON
      4.  Analyse + stockage
    """
    try:
        from app.token_manager import get_valid_microsoft_token
        from app.graph_client import graph_get
        from app.mail_memory_store import mail_exists, insert_mail
        from app.ai_client import analyze_single_mail_with_ai, client as ai_client
        from app.feedback_store import get_global_instructions
        from app.app_security import get_tenant_id
        from app.config import ANTHROPIC_MODEL_FAST

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

        # Charge les règles mail_filter de Raya
        whitelist, blacklist = _get_mail_filter_rules(username)

        # 1a — Whitelist : Raya a explicitement autorisé cet expéditeur/sujet
        whitelisted = _matches_filter(sender, subject, whitelist)
        if whitelisted:
            print(f"[Webhook][L1a-whitelist] Autorisé : '{subject[:50]}' de {sender}")

        # 1b — Heuristique statique (sauté si whitelisted)
        if not whitelisted and _is_bulk_heuristic(sender, subject, preview):
            print(f"[Webhook][L1b-heuristique] Ignoré : '{subject[:50]}' de {sender}")
            return

        # 1c — Blacklist Raya (appliquée même si pas dans l'heuristique)
        if _matches_filter(sender, subject, blacklist):
            print(f"[Webhook][L1c-blacklist] Bloqué : '{subject[:50]}' de {sender}")
            return

        # 2 — Anti-spam personnalisé
        if _is_spam_by_rules(sender, subject, preview, username):
            print(f"[Webhook][L2-règles] Ignoré : '{subject[:50]}' de {sender}")
            return

        # 3 — Claude OUI/NON
        try:
            response = ai_client.messages.create(
                model=ANTHROPIC_MODEL_FAST,
                max_tokens=5,
                messages=[{"role": "user", "content": (
                    f"Mail reçu :\nDe : {sender}\nSujet : {subject}\n"
                    f"Aperçu : {preview[:400]}\n\n"
                    f"Ce mail mérite-t-il d'être gardé en mémoire ? "
                    f"Réponds uniquement : OUI ou NON."
                )}]
            )
            should_store = "OUI" in response.content[0].text.strip().upper()
        except Exception:
            should_store = True

        if not should_store:
            print(f"[Webhook][L3-Claude] Ignoré : '{subject[:50]}' de {sender}")
            return

        # 4 — Analyse complète
        tenant_id = get_tenant_id(username)
        instructions = get_global_instructions(tenant_id=tenant_id)
        try:
            item = analyze_single_mail_with_ai(msg, instructions, username)
            analysis_status = "done_ai"
        except Exception as e:
            print(f"[Webhook] Erreur analyse {username}: {e}")
            from app.assistant_analyzer import analyze_single_mail
            item = analyze_single_mail(msg, username)
            analysis_status = "fallback"

        insert_mail({
            "username": username,
            "message_id": message_id,
            "received_at": msg.get("receivedDateTime"),
            "from_email": sender,
            "subject": subject,
            "display_title": item.get("display_title"),
            "category": item.get("category"),
            "priority": item.get("priority"),
            "reason": item.get("reason"),
            "suggested_action": item.get("suggested_action"),
            "short_summary": item.get("short_summary"),
            "group_hints": item.get("group_hints", []),
            "confidence": item.get("confidence", 0.0),
            "needs_review": item.get("needs_review", False),
            "raw_body_preview": preview,
            "analysis_status": analysis_status,
            "needs_reply": item.get("needs_reply"),
            "reply_urgency": item.get("reply_urgency"),
            "reply_reason": item.get("reply_reason"),
            "suggested_reply_subject": item.get("suggested_reply_subject"),
            "suggested_reply": item.get("suggested_reply"),
            "mailbox_source": "outlook",
        })
        print(f"[Webhook] Mail stocké pour {username}: '{subject[:60]}'")

    except Exception as e:
        print(f"[Webhook] Erreur traitement {username}/{message_id}: {e}")
