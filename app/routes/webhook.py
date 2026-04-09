"""
Endpoint Microsoft Graph webhook.

Reçoit les notifications de nouveaux mails.
Raya décide seule ce qui mérite d'être stocké dans sa mémoire —
aucune règle imposée de l'extérieur.
"""
import threading
from fastapi import APIRouter, Request, Response

router = APIRouter(tags=["webhook"])


@router.get("/webhook/microsoft")
async def webhook_validation(validationToken: str = ""):
    """Validation de l'abonnement — Microsoft envoie un GET avec validationToken."""
    if validationToken:
        return Response(content=validationToken, media_type="text/plain", status_code=200)
    return Response(status_code=200)


@router.post("/webhook/microsoft")
async def webhook_notification(request: Request):
    """
    Reçoit les notifications Microsoft Graph.
    Répond 202 immédiatement (exigé par Microsoft < 3 secondes).
    Le traitement réel se fait en arrière-plan.
    """
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
        # Vérification du client state pour authentifier la notification
        if notification.get("clientState") != sub_info["client_state"]:
            continue

        username = sub_info["username"]
        resource = notification.get("resource", "")
        # Microsoft Graph envoie l'ID du mail dans resourceData ou dans resource
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
    Traite un mail reçu par webhook :
    1. Récupère le mail complet via Graph
    2. Raya décide si elle veut le stocker (micro-appel Claude, son jugement)
    3. Si oui → analyse complète + insertion en base
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

        # Double-check déduplication
        if mail_exists(message_id, username):
            return

        # Récupère le mail
        try:
            msg = graph_get(token, f"/me/messages/{message_id}", params={
                "$select": "id,subject,from,receivedDateTime,bodyPreview,body,isRead"
            })
        except Exception as e:
            print(f"[Webhook] Erreur récupération mail {username}: {e}")
            return

        sender = msg.get("from", {}).get("emailAddress", {}).get("address", "")
        subject = msg.get("subject", "")
        preview = msg.get("bodyPreview", "")

        # Raya décide — micro-appel, son jugement seul, aucune règle imposée
        try:
            response = ai_client.messages.create(
                model=ANTHROPIC_MODEL_FAST,
                max_tokens=5,
                messages=[{"role": "user", "content": (
                    f"Mail reçu :\n"
                    f"De : {sender}\n"
                    f"Sujet : {subject}\n"
                    f"Aperçu : {preview[:400]}\n\n"
                    f"Ce mail mérite-t-il d'être gardé en mémoire ? Réponds uniquement : OUI ou NON."
                )}]
            )
            should_store = "OUI" in response.content[0].text.strip().upper()
        except Exception:
            should_store = True  # En cas d'erreur → stocker par prudence

        if not should_store:
            print(f"[Webhook] Raya ignore : '{subject[:60]}' de {sender}")
            return

        # Analyse complète
        tenant_id = get_tenant_id(username)
        instructions = get_global_instructions(tenant_id=tenant_id)
        try:
            item = analyze_single_mail_with_ai(msg, instructions, username)
            analysis_status = "done_ai"
        except Exception as e:
            print(f"[Webhook] Erreur analyse complète {username}: {e}")
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
