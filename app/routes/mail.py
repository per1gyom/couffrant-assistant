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


@router.get("/learn-sent-mails")
def learn_sent_mails(request: Request, user: dict = Depends(require_user), top: int = 50):
    username = user["username"]
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
                "SELECT 1 FROM sent_mail_memory WHERE message_id=%s AND username=%s",
                (message_id, username)
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
                    "(username,message_id,sent_at,to_email,subject,body_preview) "
                    "VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                    (username, message_id, msg.get("receivedDateTime"), to_email,
                     msg.get("subject"), msg.get("bodyPreview"))
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
                "SELECT 1 FROM mail_memory WHERE message_id=%s AND username=%s",
                (message_id, username)
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
                    "(username,message_id,received_at,from_email,subject,"
                    "raw_body_preview,analysis_status,created_at) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                    (username, message_id, msg.get("receivedDateTime"),
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
              AND analysis_status IN ('inbox_raw','archive_raw','gmail_raw')
            ORDER BY received_at DESC NULLS LAST LIMIT %s
        """, (username, limit))
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
                """, (
                    item.get("display_title"), item.get("category"), item.get("priority"),
                    item.get("reason"), item.get("suggested_action"), item.get("short_summary"),
                    item.get("confidence", 0.5), item.get("confidence_level", "moyenne"),
                    int(item.get("needs_review", False)), int(item.get("needs_reply", False)),
                    item.get("reply_urgency"), item.get("reply_reason"),
                    item.get("response_type"), item.get("suggested_reply_subject"),
                    item.get("suggested_reply"), db_id, username,
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
            "AND analysis_status IN ('inbox_raw','archive_raw','gmail_raw')",
            (username,)
        )
        remaining = c.fetchone()[0]
    finally:
        if conn: conn.close()
    return {"status": "ok", "analyzed": analyzed, "errors": errors, "remaining": remaining}


@router.get("/ingest-gmail")
def ingest_gmail(request: Request, user: dict = Depends(require_user)):
    username = user["username"]
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
                "SELECT 1 FROM mail_memory WHERE message_id=%s AND username=%s",
                (message_id, username)
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
                    "(username,message_id,received_at,from_email,subject,"
                    "raw_body_preview,analysis_status,mailbox_source,created_at) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                    (username, message_id, date, from_email, subject, snippet,
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
