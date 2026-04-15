import requests as http_requests
from datetime import datetime, timezone
from fastapi import APIRouter, Request, Form, Body, Depends
from fastapi.responses import RedirectResponse
from app.database import get_pg_conn
from app.token_manager import get_valid_microsoft_token, get_valid_google_token
from app.graph_client import graph_get
from app.rule_engine import get_antispam_keywords
from app.ai_client import analyze_single_mail_with_ai
from app.feedback_store import get_global_instructions, add_global_instruction
from app.dashboard_service import get_dashboard
from app.routes.deps import require_user

router = APIRouter(tags=["mail"])


@router.get("/triage-queue")
def triage_queue(request: Request, user: dict = Depends(require_user)):
    token = get_valid_microsoft_token(user["username"])
    if not token:
        return {"mails": [], "count": 0, "error": "Token Microsoft manquant"}
    try:
        data = graph_get(token, "/me/mailFolders/inbox/messages", params={
            "$top": 50,
            "$select": "id,subject,from,receivedDateTime,bodyPreview,isRead",
            "$orderby": "receivedDateTime DESC",
        })
        return {
            "mails": [{
                "message_id": m["id"],
                "from_email": m.get("from", {}).get("emailAddress", {}).get("address", ""),
                "subject": m.get("subject", ""),
                "received_at": m.get("receivedDateTime", ""),
                "is_read": m.get("isRead", False),
            } for m in data.get("value", [])],
            "count": len(data.get("value", [])),
        }
    except Exception as e:
        return {"mails": [], "count": 0, "error": str(e)}


@router.get("/assistant-dashboard")
def assistant_dashboard(request: Request, user: dict = Depends(require_user), days: int = 2):
    return get_dashboard(days, user["username"])


@router.post("/instruction")
def add_instruction(
    request: Request,
    user: dict = Depends(require_user),
    instruction: str = Form(...),
):
    """Consigne globale scopée au tenant de l'utilisateur."""
    add_global_instruction(instruction, tenant_id=user["tenant_id"])
    return RedirectResponse("/chat", status_code=303)


@router.post("/correction")
def save_correction(
    request: Request,
    payload: dict = Body(...),
    user: dict = Depends(require_user),
):
    from app.memory_manager import save_reply_learning
    rid = save_reply_learning(
        mail_subject=payload.get("mail_subject", ""),
        mail_from=payload.get("mail_from", ""),
        mail_body_preview=payload.get("mail_body_preview", ""),
        category=payload.get("category", "autre"),
        ai_reply=payload.get("ai_reply", ""),
        final_reply=payload.get("final_reply", ""),
        username=user["username"],
    )
    return {"status": "ok", "id": rid}
from app.routes.mail_analysis import router as _ma
router.include_router(_ma)
