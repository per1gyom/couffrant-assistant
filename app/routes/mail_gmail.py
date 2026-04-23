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




@router.get("/ingest-gmail")
def ingest_gmail(request: Request, user: dict = Depends(require_user)):
    username = user["username"]
    tenant_id = user["tenant_id"]
    from app.connectors.gmail_connector import gmail_get_messages, gmail_get_message
    access_token = get_valid_google_token(username)
    if not access_token:
        return {"error": "Google non connecté pour cet utilisateur. Connectez-vous via /login/gmail"}
    inserted = 0
    skip_keywords = get_antispam_keywords(username)
    try:
        messages = gmail_get_messages(access_token, max_results=10)
    except Exception as e:
        return {"error": f"Erreur Gmail : {str(e)[:100]}"}
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        for msg in messages:
            message_id = msg["id"]
            c.execute(
                "SELECT 1 FROM mail_memory WHERE message_id=%s AND username=%s "
                "AND (tenant_id = %s OR tenant_id IS NULL)",
                (message_id, username, tenant_id)
            )
            if c.fetchone():
                continue
            try:
                detail = gmail_get_message(access_token, message_id)
                headers = {h["name"]: h["value"]
                           for h in detail.get("payload", {}).get("headers", [])}
                subject = headers.get("Subject", "(Sans objet)")
                from_email = headers.get("From", "")
                date = headers.get("Date", "")
                snippet = detail.get("snippet", "")
                if any(kw in f"{from_email} {subject} {snippet}".lower() for kw in skip_keywords):
                    continue
                c.execute(
                    "INSERT INTO mail_memory "
                    "(username,tenant_id,message_id,received_at,from_email,subject,"
                    "raw_body_preview,analysis_status,mailbox_source,created_at) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                    (username, tenant_id, message_id, date, from_email, subject, snippet,
                     "gmail_raw", "gmail_perso", datetime.now(timezone.utc).isoformat())
                )
                inserted += 1
            except Exception:
                conn.rollback()
                continue
        conn.commit()
    finally:
        if conn: conn.close()
    return {"inserted": inserted, "total_fetched": len(messages)}



