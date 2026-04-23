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



@router.get("/learn-sent-mails")
def learn_sent_mails(request: Request, user: dict = Depends(require_user), top: int = 50):
    username = user["username"]
    tenant_id = user["tenant_id"]
    token = get_valid_microsoft_token(username)
    if not token:
        return {"error": "Token Microsoft manquant"}
    try:
        data = graph_get(token, "/me/mailFolders/SentItems/messages", params={
            "$top": top,
            "$select": "id,subject,from,receivedDateTime,bodyPreview,toRecipients",
            "$orderby": "receivedDateTime DESC",
        })
    except http_requests.HTTPError:
        return {"error": "Erreur Graph API"}
    inserted = 0
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        for msg in data.get("value", []):
            message_id = msg["id"]
            c.execute(
                "SELECT 1 FROM sent_mail_memory WHERE message_id=%s AND username=%s "
                "AND (tenant_id = %s OR tenant_id IS NULL)",
                (message_id, username, tenant_id)
            )
            if c.fetchone():
                continue
            to_recipients = msg.get("toRecipients", [])
            to_email = (
                to_recipients[0].get("emailAddress", {}).get("address", "")
                if to_recipients else ""
            )
            try:
                c.execute(
                    "INSERT INTO sent_mail_memory "
                    "(username,tenant_id,message_id,sent_at,to_email,subject,body_preview) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                    (username, tenant_id, message_id, msg.get("receivedDateTime"),
                     to_email, msg.get("subject"), msg.get("bodyPreview"))
                )
                inserted += 1
            except Exception:
                continue
        conn.commit()
    finally:
        if conn: conn.close()
    return {"inserted": inserted, "total_fetched": len(data.get("value", []))}


@router.get("/learn-inbox-mails")
def learn_inbox_mails(
    request: Request,
    user: dict = Depends(require_user),
    top: int = 50,
    skip: int = 0,
):
    username = user["username"]
    tenant_id = user["tenant_id"]
    token = get_valid_microsoft_token(username)
    if not token:
        return {"error": "Token Microsoft manquant"}
    try:
        data = graph_get(token, "/me/mailFolders/inbox/messages", params={
            "$top": top, "$skip": skip,
            "$select": "id,subject,from,receivedDateTime,bodyPreview,toRecipients",
            "$orderby": "receivedDateTime DESC",
        })
    except http_requests.HTTPError:
        return {"error": "Erreur Graph API"}
    inserted = skipped_noise = 0
    skip_keywords = get_antispam_keywords(username)
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        for msg in data.get("value", []):
            message_id = msg["id"]
            c.execute(
                "SELECT 1 FROM mail_memory WHERE message_id=%s AND username=%s "
                "AND (tenant_id = %s OR tenant_id IS NULL)",
                (message_id, username, tenant_id)
            )
            if c.fetchone():
                continue
            from_email = msg.get("from", {}).get("emailAddress", {}).get("address", "").lower()
            subject = (msg.get("subject") or "").lower()
            body = (msg.get("bodyPreview") or "").lower()
            if any(kw in f"{from_email} {subject} {body}" for kw in skip_keywords):
                skipped_noise += 1
                continue
            try:
                c.execute(
                    "INSERT INTO mail_memory "
                    "(username,tenant_id,message_id,received_at,from_email,subject,"
                    "raw_body_preview,analysis_status,created_at) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                    (username, tenant_id, message_id, msg.get("receivedDateTime"),
                     msg.get("from", {}).get("emailAddress", {}).get("address", ""),
                     msg.get("subject"), msg.get("bodyPreview"),
                     "inbox_raw", datetime.now(timezone.utc).isoformat())
                )
                inserted += 1
            except Exception:
                continue
        conn.commit()
    finally:
        if conn: conn.close()
    return {"inserted": inserted, "skipped_noise": skipped_noise,
            "total_fetched": len(data.get("value", []))}


@router.get("/analyze-raw-mails")
def analyze_raw_mails(
    request: Request,
    user: dict = Depends(require_user),
    limit: int = 50,
):
    username = user["username"]
    tenant_id = user["tenant_id"]
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            SELECT id, message_id, from_email, subject, raw_body_preview, received_at
            FROM mail_memory WHERE username=%s
              AND (tenant_id = %s OR tenant_id IS NULL)
              AND analysis_status IN ('inbox_raw','archive_raw','gmail_raw')
            ORDER BY received_at DESC NULLS LAST LIMIT %s
        """, (username, tenant_id, limit))
        rows = c.fetchall()
    finally:
        if conn: conn.close()
    if not rows:
        return {"status": "termine", "analyzed": 0}
    instructions = get_global_instructions(tenant_id=tenant_id)
    analyzed = errors = 0
    for row in rows:
        db_id, message_id, from_email, subject, body_preview, received_at = row
        msg = {
            "id": message_id, "subject": subject,
            "from": {"emailAddress": {"address": from_email or ""}},
            "receivedDateTime": str(received_at) if received_at else "",
            "bodyPreview": body_preview or "",
        }
        try:
            item = analyze_single_mail_with_ai(msg, instructions, username)
            conn = None
            try:
                conn = get_pg_conn()
                c = conn.cursor()
                c.execute("""
                    UPDATE mail_memory SET
                      display_title=%s, category=%s, priority=%s, reason=%s,
                      suggested_action=%s, short_summary=%s, confidence=%s,
                      confidence_level=%s, needs_review=%s, needs_reply=%s,
                      reply_urgency=%s, reply_reason=%s, response_type=%s,
                      suggested_reply_subject=%s, suggested_reply=%s,
                      analysis_status='done_ai'
                    WHERE id=%s AND username=%s
                      AND (tenant_id = %s OR tenant_id IS NULL)
                """, (
                    item.get("display_title"), item.get("category"), item.get("priority"),
                    item.get("reason"), item.get("suggested_action"), item.get("short_summary"),
                    item.get("confidence", 0.5), item.get("confidence_level", "moyenne"),
                    int(item.get("needs_review", False)), int(item.get("needs_reply", False)),
                    item.get("reply_urgency"), item.get("reply_reason"),
                    item.get("response_type"), item.get("suggested_reply_subject"),
                    item.get("suggested_reply"), db_id, username, tenant_id,
                ))
                conn.commit()
            finally:
                if conn: conn.close()
            analyzed += 1
        except Exception as e:
            print(f"[AnalyzeRaw] Erreur {db_id}: {e}")
            errors += 1
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute(
            "SELECT COUNT(*) FROM mail_memory WHERE username=%s "
            "AND (tenant_id = %s OR tenant_id IS NULL) "
            "AND analysis_status IN ('inbox_raw','archive_raw','gmail_raw')",
            (username, tenant_id)
        )
        remaining = c.fetchone()[0]
    finally:
        if conn: conn.close()
    return {"status": "ok", "analyzed": analyzed, "errors": errors, "remaining": remaining}


from app.routes.mail_gmail import router as _mg
router.include_router(_mg)
