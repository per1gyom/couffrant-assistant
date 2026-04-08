from fastapi import APIRouter, Request, Body
from fastapi.responses import RedirectResponse
from app.database import get_pg_conn
from app.ai_client import client
from app.config import ANTHROPIC_MODEL_SMART
from app.memory_loader import (
    MEMORY_OK, rebuild_hot_summary, rebuild_contacts,
    load_sent_mails_to_style, get_all_contact_cards,
    purge_old_mails, save_style_example, synthesize_session,
)
from app.routes.deps import require_user

router = APIRouter(tags=["memory"])


@router.get("/build-memory")
def build_memory(request: Request):
    username = require_user(request)
    if not username: return RedirectResponse("/login-app")
    tenant_id = request.session.get("tenant_id", "couffrant_solar")
    if not MEMORY_OK: return {"error": "Module mémoire non disponible"}
    results = {"memory_module": MEMORY_OK, "username": username, "tenant_id": tenant_id}
    try:
        summary = rebuild_hot_summary(username)
        results["hot_summary"] = "✅ Résumé chaud reconstruit"; results["preview"] = summary[:200]
    except Exception as e: results["hot_summary"] = f"❌ {str(e)[:100]}"
    try:
        count = rebuild_contacts(tenant_id=tenant_id)
        results["contacts"] = f"✅ {count} fiches contacts (tenant: {tenant_id})"
    except Exception as e: results["contacts"] = f"❌ {str(e)[:100]}"
    try:
        added = load_sent_mails_to_style(limit=50, username=username)
        results["style"] = f"✅ {added} exemples de style"
    except Exception as e: results["style"] = f"❌ {str(e)[:100]}"
    return results


@router.get("/memory-status")
def memory_status(request: Request):
    username = require_user(request)
    if not username: return RedirectResponse("/login-app")
    conn = None
    try:
        conn = get_pg_conn(); c = conn.cursor()
        try:
            c.execute("SELECT content FROM aria_hot_summary WHERE username = %s", (username,))
            row = c.fetchone()
        except Exception: row = None
        counts = {}
        for table, key in [
            (f"aria_contacts WHERE tenant_id='{request.session.get('tenant_id','couffrant_solar')}'", "contacts"),
            (f"aria_style_examples WHERE username='{username}'", "style_examples"),
            (f"aria_rules WHERE active=true AND username='{username}'", "regles_actives"),
            (f"aria_insights WHERE username='{username}'", "insights"),
            (f"aria_session_digests WHERE username='{username}'", "session_digests"),
            (f"mail_memory WHERE username='{username}'", "mail_memory"),
            (f"aria_memory WHERE username='{username}'", "conversations_brutes"),
            (f"sent_mail_memory WHERE username='{username}'", "sent_mail_memory"),
        ]:
            try:
                c.execute(f"SELECT COUNT(*) FROM {table}")
                counts[key] = c.fetchone()[0]
            except Exception: counts[key] = 0
    finally:
        if conn: conn.close()
    return {
        "username": username, "memory_module": MEMORY_OK,
        "tenant_id": request.session.get("tenant_id", "couffrant_solar"),
        "niveau_1": {"resume_chaud": {"exists": bool(row and row[0])},
                     "contacts": counts.get("contacts", 0),
                     "regles_actives": counts.get("regles_actives", 0),
                     "insights": counts.get("insights", 0)},
        "niveau_2": {"conversations_brutes": counts.get("conversations_brutes", 0),
                     "mail_memory": counts.get("mail_memory", 0),
                     "style_examples": counts.get("style_examples", 0)},
        "niveau_3": {"session_digests": counts.get("session_digests", 0),
                     "sent_mail_memory": counts.get("sent_mail_memory", 0)},
    }


@router.get("/synth")
def trigger_synth(request: Request, n: int = 15):
    username = require_user(request)
    if not username: return RedirectResponse("/login-app")
    if not MEMORY_OK: return {"error": "Module mémoire non disponible"}
    return synthesize_session(n, username)


@router.get("/rules")
def list_rules(request: Request):
    username = require_user(request)
    if not username: return RedirectResponse("/login-app")
    conn = None
    try:
        conn = get_pg_conn(); c = conn.cursor()
        c.execute("SELECT id,category,rule,source,confidence,reinforcements,active,created_at FROM aria_rules WHERE username=%s ORDER BY active DESC,confidence DESC,created_at DESC", (username,))
        columns = [d[0] for d in c.description]
        return [dict(zip(columns, row)) for row in c.fetchall()]
    finally:
        if conn: conn.close()


@router.get("/insights")
def list_insights(request: Request):
    username = require_user(request)
    if not username: return RedirectResponse("/login-app")
    conn = None
    try:
        conn = get_pg_conn(); c = conn.cursor()
        c.execute("SELECT id,topic,insight,reinforcements,created_at FROM aria_insights WHERE username=%s ORDER BY reinforcements DESC,updated_at DESC", (username,))
        columns = [d[0] for d in c.description]
        return [dict(zip(columns, row)) for row in c.fetchall()]
    finally:
        if conn: conn.close()


@router.get("/contacts")
def list_contacts_endpoint(request: Request):
    if not require_user(request): return RedirectResponse("/login-app")
    tenant_id = request.session.get("tenant_id", "couffrant_solar")
    return get_all_contact_cards(tenant_id=tenant_id)


@router.get("/purge-memory")
def purge_memory(request: Request, days: int = 90):
    username = require_user(request)
    if not username: return RedirectResponse("/login-app")
    return {"status": "ok", "deleted": purge_old_mails(days=days, username=username)}


@router.post("/learn-style")
def learn_style(request: Request, payload: dict = Body(...)):
    username = require_user(request)
    if not username: return RedirectResponse("/login-app")
    text = payload.get("text", "")
    if not text: return {"error": "Texte manquant"}
    save_style_example(situation=payload.get("situation", "mail"), example_text=text,
                       tags=payload.get("tags", ""), quality_score=2.0, username=username)
    return {"status": "ok"}


@router.get("/memory")
def memory_list(request: Request):
    username = require_user(request)
    if not username: return RedirectResponse("/login-app")
    conn = None
    try:
        conn = get_pg_conn(); c = conn.cursor()
        c.execute("SELECT message_id,received_at,from_email,subject,display_title,category,priority,analysis_status FROM mail_memory WHERE username=%s ORDER BY id DESC LIMIT 20", (username,))
        columns = [desc[0] for desc in c.description]
        return [dict(zip(columns, row)) for row in c.fetchall()]
    finally:
        if conn: conn.close()


@router.get("/rebuild-memory")
def rebuild_memory_mails(request: Request):
    username = require_user(request)
    if not username: return RedirectResponse("/login-app")
    conn = None
    try:
        conn = get_pg_conn(); c = conn.cursor()
        c.execute("DELETE FROM mail_memory WHERE username=%s", (username,)); conn.commit()
    finally:
        if conn: conn.close()
    return {"status": "mail_memory_cleared", "username": username}


@router.get("/build-style-profile")
def build_style_profile(request: Request):
    username = require_user(request)
    if not username: return RedirectResponse("/login-app")
    conn = None
    try:
        conn = get_pg_conn(); c = conn.cursor()
        c.execute("SELECT subject,to_email,body_preview FROM sent_mail_memory WHERE username=%s ORDER BY sent_at DESC LIMIT 100", (username,))
        columns = [desc[0] for desc in c.description]
        rows = [dict(zip(columns, row)) for row in c.fetchall()]
    finally:
        if conn: conn.close()
    if not rows: return {"error": "Aucun mail envoyé en mémoire"}
    display_name = username.capitalize()
    mails_text = "\n\n".join([f"Sujet : {r['subject']}\nDestinataire : {r['to_email']}\nContenu : {r['body_preview']}" for r in rows])
    response = client.messages.create(model=ANTHROPIC_MODEL_SMART, max_tokens=2048,
        messages=[{"role": "user", "content": f"Analyse ces {len(rows)} emails envoyés par {display_name}.\n\n{mails_text}\n\nProduis un profil de son style rédactionnel."}])
    profile_text = response.content[0].text
    conn = None
    try:
        conn = get_pg_conn(); c = conn.cursor()
        c.execute("DELETE FROM aria_profile WHERE username=%s AND profile_type='style'", (username,))
        c.execute("INSERT INTO aria_profile (username,profile_type,content) VALUES (%s,%s,%s)", (username, 'style', profile_text))
        conn.commit()
    finally:
        if conn: conn.close()
    return {"status": "ok", "profile": profile_text}
