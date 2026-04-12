"""
Endpoint Microsoft Graph webhook.

Pipeline de filtrage à 5 niveaux :
  1a. Whitelist Raya (mail_filter autoriser:) → court-circuite le filtre statique
  1b. Filtre heuristique statique (noreply / newsletters / bulk domains)
  1c. Blacklist Raya (mail_filter bloquer:) → bloc supplémentaire
  2.  Règles anti_spam personnalisées
  3.  Triage Haiku : IGNORER / STOCKER_SIMPLE / ANALYSER
  4.  Analyse complète ou stockage simple + stockage
  5.  Scoring d'urgence + alerte shadow ou réelle (Phase 7)

process_incoming_mail() est source-agnostic (7-1b) :
consommé par le webhook Microsoft ET le polling Gmail.

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
    sender_l = sender.lower()
    subject_l = (subject or "").lower()
    for pattern in patterns:
        if pattern.startswith('@'):
            if sender_l.endswith(pattern):
                return True
        elif pattern.startswith('sujet:'):
            kw = pattern[6:].strip()
            if kw and kw in subject_l:
                return True
        else:
            if pattern in sender_l:
                return True
    return False


def _is_bulk_heuristic(sender: str, subject: str, preview: str) -> bool:
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
    try:
        from app.memory_rules import get_antispam_keywords
        keywords = get_antispam_keywords(username)
        text = f"{sender} {subject} {preview}".lower()
        return any(kw in text for kw in keywords if kw)
    except Exception:
        return False


# ─── PIPELINE COMMUN (source-agnostic) ───

def process_incoming_mail(
    username: str,
    sender: str,
    subject: str,
    preview: str,
    message_id: str,
    received_at: str,
    mailbox_source: str = "outlook",
    raw_body: str = None,
) -> str:
    """
    Pipeline de filtrage commun (7-1b) — source-agnostic.
    Appelé par le webhook Microsoft ET le polling Gmail.

    Retourne : "duplicate", "ignored", "stored_simple", "done_ai", "fallback", "error".
    """
    from datetime import datetime
    from app.mail_memory_store import mail_exists, insert_mail
    from app.ai_client import analyze_single_mail_with_ai
    from app.router import route_mail_action
    from app.feedback_store import get_global_instructions
    from app.app_security import get_tenant_id
    from app.database import get_pg_conn

    try:
        if mail_exists(message_id, username):
            return "duplicate"

        tenant_id = get_tenant_id(username)
        whitelist, blacklist = _get_mail_filter_rules(username)

        # 1a — Whitelist
        whitelisted = _matches_filter(sender, subject, whitelist)

        # 1b — Heuristique statique
        if not whitelisted and _is_bulk_heuristic(sender, subject, preview):
            print(f"[Pipeline][L1b] Ignoré : '{subject[:50]}' de {sender}")
            return "ignored"

        # 1c — Blacklist
        if _matches_filter(sender, subject, blacklist):
            print(f"[Pipeline][L1c] Bloqué : '{subject[:50]}' de {sender}")
            return "ignored"

        # 2 — Anti-spam personnalisé
        if _is_spam_by_rules(sender, subject, preview, username):
            print(f"[Pipeline][L2] Ignoré : '{subject[:50]}' de {sender}")
            return "ignored"

        # 3 — Triage Haiku
        try:
            triage = route_mail_action(sender, subject, preview)
        except Exception:
            triage = "ANALYSER"

        if triage == "IGNORER":
            return "ignored"

        # 4 — Analyse ou stockage simple
        instructions = get_global_instructions(tenant_id=tenant_id)

        if triage == "STOCKER_SIMPLE":
            item = {
                "display_title": subject or "(Sans objet)",
                "category": "autre", "priority": "basse",
                "reason": "Stockage simple (triage)",
                "suggested_action": "Consulter si besoin",
                "short_summary": (preview or "")[:200],
                "group_hints": [],
                "confidence": 0.5, "confidence_level": "moyenne",
                "needs_review": False, "needs_reply": False,
                "reply_urgency": "basse", "reply_reason": "",
                "response_type": "pas_de_reponse", "missing_fields": [],
                "suggested_reply_subject": "", "suggested_reply": "",
            }
            analysis_status = "stored_simple"
        else:
            try:
                # Pseudo-msg compatible avec analyze_single_mail_with_ai
                mock_msg = {
                    "id": message_id, "subject": subject,
                    "from": {"emailAddress": {"address": sender}},
                    "receivedDateTime": received_at,
                    "bodyPreview": preview,
                    "body": {"content": raw_body or preview},
                }
                item = analyze_single_mail_with_ai(mock_msg, instructions, username)
                analysis_status = "done_ai"
            except Exception as e:
                print(f"[Pipeline] Erreur analyse: {e}")
                item = {
                    "display_title": subject or "(Sans objet)",
                    "category": "autre", "priority": "moyenne",
                    "reason": "Analyse échouée", "suggested_action": "Vérifier",
                    "short_summary": (preview or "")[:200], "group_hints": [],
                    "confidence": 0.3, "needs_review": True,
                    "needs_reply": False, "reply_urgency": "basse",
                    "reply_reason": "", "suggested_reply_subject": "",
                    "suggested_reply": "",
                }
                analysis_status = "fallback"

        insert_mail({
            "username": username,
            "message_id": message_id,
            "received_at": received_at,
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
            "mailbox_source": mailbox_source,
        })

        # 5 — Scoring d'urgence + alerte
        try:
            from app.urgency_model import score_mail_urgency
            urgency = score_mail_urgency(sender, subject, preview, username, tenant_id)
            if urgency["level"] in ("important", "critical"):
                _conn = get_pg_conn()
                _c = _conn.cursor()
                _c.execute("SELECT shadow_mode, shadow_mode_until FROM users WHERE username = %s", (username,))
                _row = _c.fetchone()
                _conn.close()
                is_shadow = (_row and _row[0] and (_row[1] is None or _row[1] > datetime.now()))

                from app.proactive_alerts import create_alert
                icon = "\U0001f534" if urgency["level"] == "critical" else "\U0001f7e0"
                prio = "critical" if urgency["level"] == "critical" else "high"
                if is_shadow:
                    create_alert(
                        username=username, tenant_id=tenant_id, alert_type="mail_urgent",
                        priority=prio,
                        title=f"[SHADOW] {icon} WhatsApp : {subject[:60]}",
                        body=f"De : {sender}\nScore : {urgency['score']}/100\nRaisons : {', '.join(urgency['reasons'][:3])}",
                        source_type="mail_shadow", source_id=str(message_id[:50]),
                    )
                else:
                    create_alert(
                        username=username, tenant_id=tenant_id, alert_type="mail_urgent",
                        priority=prio,
                        title=f"Mail {urgency['level']} : {subject[:60]}",
                        body=f"De : {sender}\nScore : {urgency['score']}/100\n{item.get('short_summary', preview[:200])}",
                        source_type="mail", source_id=str(message_id[:50]),
                    )
        except Exception as e:
            print(f"[Pipeline] Erreur urgence: {e}")

        return analysis_status

    except Exception as e:
        print(f"[Pipeline] Erreur {username}/{message_id}: {e}")
        return "error"


# ─── WEBHOOK ENDPOINTS ───

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


def _process_mail(username: str, message_id: str):
    """
    Pipeline Microsoft — récupère le mail via Graph puis appelle process_incoming_mail.
    """
    try:
        from app.token_manager import get_valid_microsoft_token
        from app.graph_client import graph_get
        from app.mail_memory_store import mail_exists

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
        received_at = msg.get("receivedDateTime", "")
        raw_body = msg.get("body", {}).get("content", "")

        process_incoming_mail(
            username=username, sender=sender, subject=subject,
            preview=preview, message_id=message_id,
            received_at=received_at, mailbox_source="outlook",
            raw_body=raw_body,
        )
    except Exception as e:
        print(f"[Webhook] Erreur {username}/{message_id}: {e}")
