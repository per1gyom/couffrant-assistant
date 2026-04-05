from fastapi import APIRouter, Request
from app.graph_client import graph_get
from app.assistant_analyzer import analyze_single_mail
from app.mail_memory_store import insert_mail, mail_exists

router = APIRouter()


@router.get("/refresh-mails")
def refresh_mails(request: Request):
    access_token = request.session.get("access_token")

    if not access_token:
        return {"error": "Non connecté"}

    data = graph_get(access_token, "/me/mailFolders/inbox/messages", {"$top": 10})
    messages = data.get("value", [])

    results = []

    for msg in messages:
        message_id = msg.get("id")

        if mail_exists(message_id):
            continue

        analysis = analyze_single_mail(msg)

        data = {
            "message_id": message_id,
            "thread_id": msg.get("conversationId"),
            "received_at": msg.get("receivedDateTime"),
            "from_email": msg.get("from", {}).get("emailAddress", {}).get("address"),
            "subject": msg.get("subject"),
            "display_title": analysis.get("display_title"),
            "category": analysis.get("category"),
            "priority": analysis.get("priority"),
            "reason": analysis.get("reason"),
            "suggested_action": analysis.get("suggested_action"),
            "short_summary": analysis.get("short_summary"),
            "confidence": 0.9,
            "needs_review": False,
            "raw_body_preview": msg.get("bodyPreview"),
            "analysis_status": "done",

            # réponses auto
            "needs_reply": analysis.get("needs_reply"),
            "reply_urgency": analysis.get("reply_urgency"),
            "reply_reason": analysis.get("reply_reason"),
            "suggested_reply_subject": analysis.get("suggested_reply_subject"),
            "suggested_reply": analysis.get("suggested_reply"),
        }

        insert_mail(data)
        results.append(data)

    return {
        "imported": len(results)
    }