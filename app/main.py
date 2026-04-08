import os
import requests
import json
from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI, Request, Form, Body
from fastapi.responses import RedirectResponse, HTMLResponse, StreamingResponse
from starlette.middleware.sessions import SessionMiddleware
from pydantic import BaseModel

from app.auth import build_msal_app
from app.config import (
    GRAPH_SCOPES, REDIRECT_URI, SESSION_SECRET,
    ANTHROPIC_MODEL_SMART, ANTHROPIC_MODEL_FAST
)
from app.graph_client import graph_get
from app.ai_client import summarize_messages, analyze_single_mail_with_ai, client
from app.feedback_store import init_db, add_global_instruction, get_global_instructions
from app.mail_memory_store import init_mail_db, insert_mail, mail_exists
from app.assistant_analyzer import analyze_single_mail
from app.dashboard_service import get_dashboard
from app.connectors.outlook_connector import (
    perform_outlook_action, list_aria_drive, read_aria_drive_file,
    search_aria_drive, create_drive_folder, copy_drive_item, move_drive_item
)
from app.database import get_pg_conn, init_postgres
from app.token_manager import get_valid_microsoft_token, save_microsoft_token, get_all_users_with_tokens
from app.app_security import (
    authenticate, init_default_user, update_last_login,
    check_rate_limit, record_failed_attempt, clear_attempts,
    get_user_scope, create_user, delete_user, list_users,
    get_user_tools, set_user_tool, remove_user_tool,
    LOGIN_PAGE_HTML, SCOPE_ADMIN, SCOPE_CS
)
# Rule engine — règles évolutives d'Aria (zéro règle métier codée en dur)
from app.rule_engine import get_antispam_keywords, get_contacts_keywords, get_memoire_param

try:
    from app.memory_manager import (
        get_hot_summary, rebuild_hot_summary,
        get_contact_card, get_all_contact_cards, rebuild_contacts,
        get_style_examples, save_style_example, learn_from_correction,
        load_sent_mails_to_style, purge_old_mails,
        get_aria_rules, save_rule, delete_rule,
        get_aria_insights, save_insight,
        synthesize_session, seed_default_rules,
    )
    MEMORY_OK = True
except Exception as _mem_err:
    print(f"[Memory] Module non disponible: {_mem_err}")
    MEMORY_OK = False
    def get_hot_summary(username='guillaume'): return ""
    def rebuild_hot_summary(username='guillaume'): return ""
    def get_contact_card(x): return ""
    def get_all_contact_cards(): return []
    def rebuild_contacts(): return 0
    def get_style_examples(**kwargs): return ""
    def save_style_example(**kwargs): pass
    def learn_from_correction(**kwargs): pass
    def load_sent_mails_to_style(**kwargs): return 0
    def purge_old_mails(**kwargs): return 0
    def get_aria_rules(username='guillaume'): return ""
    def save_rule(*a, **kw): return 0
    def delete_rule(*a, **kw): return False
    def get_aria_insights(**kwargs): return ""
    def save_insight(*a, **kw): return 0
    def synthesize_session(**kwargs): return {}
    def seed_default_rules(username='guillaume'): pass


app = FastAPI(title="Couffrant Solar Assistant")
app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET, max_age=30 * 24 * 3600)


class AriaQuery(BaseModel):
    query: str
    file_data: Optional[str] = None
    file_type: Optional[str] = None
    file_name: Optional[str] = None


@app.on_event("startup")
def startup_event():
    init_postgres()
    init_db()
    init_mail_db()
    try:
        init_default_user()
    except Exception as e:
        print(f"[Auth] Erreur init_default_user: {e}")

    try:
        admin_username = os.getenv("APP_USERNAME", "guillaume").strip()
        seed_default_rules(admin_username)
    except Exception as e:
        print(f"[Seed] Erreur seed_default_rules: {e}")

    import threading

    def auto_ingest():
        import time
        cycle = 0
        while True:
            try:
                from app.graph_client import graph_get as _graph_get
                from app.ai_client import analyze_single_mail_with_ai as _analyze_ai
                from app.feedback_store import get_global_instructions as _get_instructions
                from app.assistant_analyzer import analyze_single_mail as _analyze
                from app.rule_engine import get_antispam_keywords as _get_spam, get_memoire_param as _get_param

                users = get_all_users_with_tokens()
                instructions = _get_instructions()

                for username in users:
                    try:
                        token = get_valid_microsoft_token(username)
                        if not token: continue
                        data = _graph_get(token, "/me/mailFolders/inbox/messages",
                            params={"$top": 10, "$select": "id,subject,from,receivedDateTime,bodyPreview",
                                    "$orderby": "receivedDateTime DESC"})
                        spam_kw = _get_spam(username)
                        for msg in data.get("value", []):
                            message_id = msg["id"]
                            if mail_exists(message_id, username): continue
                            _from = msg.get("from", {}).get("emailAddress", {}).get("address", "").lower()
                            _txt = f"{_from} {(msg.get('subject') or '').lower()} {(msg.get('bodyPreview') or '').lower()}"
                            if any(kw in _txt for kw in spam_kw): continue
                            try:
                                item = _analyze_ai(msg, instructions, username); analysis_status = "done_ai"
                            except Exception:
                                item = _analyze(msg, username); analysis_status = "fallback"
                            insert_mail({
                                "username": username, "message_id": message_id,
                                "received_at": msg.get("receivedDateTime"),
                                "from_email": msg.get("from", {}).get("emailAddress", {}).get("address"),
                                "subject": msg.get("subject"), "display_title": item.get("display_title"),
                                "category": item.get("category"), "priority": item.get("priority"),
                                "reason": item.get("reason"), "suggested_action": item.get("suggested_action"),
                                "short_summary": item.get("short_summary"), "group_hints": item.get("group_hints", []),
                                "confidence": item.get("confidence", 0.0), "needs_review": item.get("needs_review", False),
                                "raw_body_preview": msg.get("bodyPreview"), "analysis_status": analysis_status,
                                "needs_reply": item.get("needs_reply"), "reply_urgency": item.get("reply_urgency"),
                                "reply_reason": item.get("reply_reason"),
                                "suggested_reply_subject": item.get("suggested_reply_subject"),
                                "suggested_reply": item.get("suggested_reply"), "mailbox_source": "outlook",
                            })
                    except Exception as e:
                        print(f"[AutoIngest] Erreur pour {username}: {e}")

                cycle += 1
                try:
                    _rebuild_cycle = _get_param(users[0] if users else 'guillaume', "rebuild_cycles", 40)
                except Exception:
                    _rebuild_cycle = 40
                if cycle % _rebuild_cycle == 0 and MEMORY_OK:
                    for username in users:
                        try: rebuild_hot_summary(username)
                        except Exception as e: print(f"[Memory] Erreur rebuild {username}: {e}")

            except Exception as e:
                print(f"[AutoIngest] Erreur générale: {e}")
            time.sleep(30)

    threading.Thread(target=auto_ingest, daemon=True).start()

    def token_refresh_loop():
        import time
        time.sleep(120)
        while True:
            try:
                for username in get_all_users_with_tokens():
                    try:
                        token = get_valid_microsoft_token(username)
                        print(f"[Token] Refresh {username}: {'OK' if token else 'ECHEC'}")
                    except Exception as e:
                        print(f"[Token] Erreur {username}: {e}")
            except Exception as e:
                print(f"[Token] Erreur générale: {e}")
            time.sleep(45 * 60)

    threading.Thread(target=token_refresh_loop, daemon=True).start()


# ─── AUTH ───

@app.get("/login-app", response_class=HTMLResponse)
def login_app_get(request: Request):
    if request.session.get("user"): return RedirectResponse("/chat")
    return HTMLResponse(LOGIN_PAGE_HTML.format(error_block=""))


@app.post("/login-app", response_class=HTMLResponse)
async def login_app_post(request: Request, username: str = Form(...), password: str = Form(...)):
    ip = request.client.host if request.client else "unknown"
    allowed, message = check_rate_limit(ip)
    if not allowed:
        return HTMLResponse(LOGIN_PAGE_HTML.format(error_block=f'<div class="error">{message}</div>'))
    if authenticate(username.strip(), password):
        clear_attempts(ip)
        update_last_login(username.strip())
        scope = get_user_scope(username.strip())
        request.session["user"] = username.strip()
        request.session["scope"] = scope
        return RedirectResponse("/chat", status_code=303)
    else:
        record_failed_attempt(ip)
        return HTMLResponse(LOGIN_PAGE_HTML.format(error_block='<div class="error">Identifiant ou mot de passe incorrect.</div>'), status_code=401)


@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login-app")


@app.get("/health")
def health():
    return {"status": "ok", "memory_module": MEMORY_OK}


@app.get("/init-db")
def init_db_now():
    init_postgres()
    try: init_default_user()
    except Exception: pass
    return {"status": "tables créées"}


@app.get("/chat", response_class=HTMLResponse)
def chat(request: Request):
    if not request.session.get("user"): return RedirectResponse("/login-app")
    with open("app/templates/aria_chat.html", "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())


# ─── ADMIN ───

def _require_admin(request: Request) -> bool:
    return request.session.get("scope", SCOPE_CS) == SCOPE_ADMIN


@app.get("/admin/users")
def admin_list_users(request: Request):
    if not _require_admin(request): return {"error": "Accès refusé."}
    return list_users()


@app.post("/admin/create-user")
def admin_create_user(request: Request, payload: dict = Body(...)):
    if not _require_admin(request): return {"error": "Accès refusé."}
    return create_user(
        payload.get("username", "").strip(),
        payload.get("password", ""),
        payload.get("scope", SCOPE_CS),
        payload.get("tools"),
    )


@app.delete("/admin/delete-user/{target_username}")
def admin_delete_user(request: Request, target_username: str):
    if not _require_admin(request): return {"error": "Accès refusé."}
    return delete_user(target_username, request.session.get("user", ""))


@app.get("/admin/rules")
def admin_rules(request: Request, user: str = ""):
    if not _require_admin(request): return {"error": "Accès refusé."}
    conn = None
    try:
        conn = get_pg_conn(); c = conn.cursor()
        if user:
            c.execute("SELECT id,username,category,rule,confidence,reinforcements,active,created_at FROM aria_rules WHERE username=%s ORDER BY active DESC,confidence DESC", (user,))
        else:
            c.execute("SELECT id,username,category,rule,confidence,reinforcements,active,created_at FROM aria_rules ORDER BY username,active DESC,confidence DESC")
        columns = [d[0] for d in c.description]
        return [dict(zip(columns, row)) for row in c.fetchall()]
    finally:
        if conn: conn.close()


@app.get("/admin/insights")
def admin_insights(request: Request, user: str = ""):
    if not _require_admin(request): return {"error": "Accès refusé."}
    conn = None
    try:
        conn = get_pg_conn(); c = conn.cursor()
        if user:
            c.execute("SELECT id,username,topic,insight,reinforcements,created_at FROM aria_insights WHERE username=%s ORDER BY reinforcements DESC", (user,))
        else:
            c.execute("SELECT id,username,topic,insight,reinforcements,created_at FROM aria_insights ORDER BY username,reinforcements DESC")
        columns = [d[0] for d in c.description]
        return [dict(zip(columns, row)) for row in c.fetchall()]
    finally:
        if conn: conn.close()


@app.get("/admin/memory-status")
def admin_memory_status(request: Request):
    if not _require_admin(request): return {"error": "Accès refusé."}
    conn = None
    try:
        conn = get_pg_conn(); c = conn.cursor()
        c.execute("SELECT username, COUNT(*) FROM aria_memory GROUP BY username")
        conversations = dict(c.fetchall())
        c.execute("SELECT username, COUNT(*) FROM aria_rules WHERE active=true GROUP BY username")
        rules = dict(c.fetchall())
        c.execute("SELECT username, COUNT(*) FROM aria_insights GROUP BY username")
        insights = dict(c.fetchall())
        c.execute("SELECT username, COUNT(*) FROM mail_memory GROUP BY username")
        mails = dict(c.fetchall())
        users_all = set(list(conversations) + list(rules) + list(insights) + list(mails))
        return [{"username": u, "conversations": conversations.get(u, 0), "rules": rules.get(u, 0),
                 "insights": insights.get(u, 0), "mails": mails.get(u, 0)} for u in sorted(users_all)]
    finally:
        if conn: conn.close()


# ─── ADMIN OUTILS ───

@app.get("/admin/user-tools/{target_username}")
def admin_get_user_tools(request: Request, target_username: str):
    if not _require_admin(request): return {"error": "Accès refusé."}
    return get_user_tools(target_username, raw=True)


@app.post("/admin/user-tools/{target_username}/{tool}")
def admin_set_user_tool(request: Request, target_username: str, tool: str, payload: dict = Body(...)):
    if not _require_admin(request): return {"error": "Accès refusé."}
    return set_user_tool(target_username, tool,
        payload.get("access_level", "read_only"), payload.get("enabled", True), payload.get("config", {}))


@app.delete("/admin/user-tools/{target_username}/{tool}")
def admin_remove_user_tool(request: Request, target_username: str, tool: str):
    if not _require_admin(request): return {"error": "Accès refusé."}
    return remove_user_tool(target_username, tool)


# ─── ARIA ───

@app.post("/speak")
def speak_text(payload: dict = Body(...)):
    import re, io
    api_key = os.environ.get("ELEVENLABS_API_KEY", "")
    voice_id = os.environ.get("ELEVENLABS_VOICE_ID", "")
    if not api_key or not voice_id: return {"error": "Clés ElevenLabs manquantes"}
    text = payload.get("text", "")
    clean = re.sub(r'#{1,6}\s+', '', text)
    clean = re.sub(r'\*\*(.*?)\*\*', r'\1', clean)
    clean = re.sub(r'\*(.*?)\*', r'\1', clean)
    clean = re.sub(r'`(.*?)`', r'\1', clean)
    clean = re.sub(r'---+', '', clean)
    clean = re.sub(r'\|.*?\|', '', clean)
    clean = clean.strip()[:2500]
    resp = requests.post(
        f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
        headers={"xi-api-key": api_key, "Content-Type": "application/json"},
        json={"text": clean, "model_id": "eleven_flash_v2_5",
              "voice_settings": {"stability": 0.5, "similarity_boost": 0.8, "style": 0.2, "use_speaker_boost": True}},
        timeout=30,
    )
    if resp.status_code != 200:
        return {"error": f"ElevenLabs {resp.status_code}", "detail": resp.text[:200]}
    return StreamingResponse(io.BytesIO(resp.content), media_type="audio/mpeg")


@app.post("/aria")
def aria(request: Request, payload: AriaQuery):
    import re
    instructions = get_global_instructions()

    username = request.session.get("user", "guillaume")
    user_scope = request.session.get("scope", SCOPE_CS)
    is_admin = user_scope == SCOPE_ADMIN
    display_name = username.capitalize()

    user_tools = get_user_tools(username)
    drive_tool = user_tools.get('drive', {})
    drive_access = drive_tool.get('access_level', 'read_only') if drive_tool.get('enabled', True) else 'none'
    drive_write = drive_access in ('write', 'full')
    drive_can_delete = drive_tool.get('config', {}).get('can_delete', False)
    mail_tool = user_tools.get('outlook', {})
    mail_can_delete = mail_tool.get('config', {}).get('can_delete_mail', False)
    mail_extra_boxes = mail_tool.get('config', {}).get('mailboxes', [])
    odoo_tool = user_tools.get('odoo', {})
    odoo_enabled = odoo_tool.get('enabled', False) and odoo_tool.get('access_level', 'none') != 'none'
    odoo_access = odoo_tool.get('access_level', 'none')
    odoo_shared_user = odoo_tool.get('config', {}).get('shared_user')

    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            SELECT id as db_id, message_id, from_email, display_title, category, priority,
                   short_summary, suggested_reply, raw_body_preview, received_at, mailbox_source
            FROM mail_memory WHERE username = %s
            ORDER BY received_at DESC NULLS LAST LIMIT 10
        """, (username,))
        columns = [desc[0] for desc in c.description]
        mails_from_db = [dict(zip(columns, row)) for row in c.fetchall()]
        c.execute("SELECT user_input, aria_response FROM aria_memory WHERE username = %s ORDER BY id DESC LIMIT 6", (username,))
        columns = [desc[0] for desc in c.description]
        history = [dict(zip(columns, row)) for row in c.fetchall()]
        history.reverse()
        c.execute("SELECT content FROM aria_profile WHERE username = %s AND profile_type = 'style' ORDER BY id DESC LIMIT 1", (username,))
        profile_row = c.fetchone()
        c.execute("SELECT COUNT(*) FROM aria_memory WHERE username = %s", (username,))
        conv_count = c.fetchone()[0]
    finally:
        if conn: conn.close()

    hot_summary = get_hot_summary(username)
    aria_rules = get_aria_rules(username)
    aria_insights = get_aria_insights(limit=6, username=username)

    contact_card = ""
    query_lower = payload.query.lower()
    known_contacts = get_contacts_keywords(username)  # dynamique depuis aria_contacts + règles
    for name in known_contacts:
        if name in query_lower:
            contact_card = get_contact_card(name)
            if contact_card: break

    style_examples = get_style_examples(
        context=payload.query[:100] if any(w in query_lower for w in ["répond", "rédige", "écris", "mail"]) else "",
        username=username
    )

    outlook_token = get_valid_microsoft_token(username)
    outlook_live_mails = []
    if outlook_token:
        try:
            data = graph_get(outlook_token, "/me/mailFolders/inbox/messages", params={
                "$top": 20, "$select": "id,subject,from,receivedDateTime,bodyPreview,isRead",
                "$orderby": "receivedDateTime DESC"})
            for msg in data.get("value", []):
                outlook_live_mails.append({
                    "message_id": msg["id"],
                    "from_email": msg.get("from", {}).get("emailAddress", {}).get("address", ""),
                    "subject": msg.get("subject", "(Sans objet)"),
                    "raw_body_preview": msg.get("bodyPreview", ""),
                    "received_at": msg.get("receivedDateTime", ""),
                    "is_read": msg.get("isRead", False), "mailbox_source": "outlook",
                })
        except Exception as e:
            print(f"[Aria] Erreur Outlook live {username}: {e}")

    agenda_today = []
    if outlook_token:
        try:
            now = datetime.now(timezone.utc)
            start = now.replace(hour=0, minute=0, second=0).isoformat()
            end = now.replace(hour=23, minute=59, second=59).isoformat()
            agenda_result = perform_outlook_action("list_calendar_events",
                {"start": start, "end": end, "top": 10}, outlook_token)
            agenda_today = agenda_result.get("items", [])
        except Exception: pass

    user_content_parts = []
    if payload.file_data and payload.file_type:
        file_name_info = f" ({payload.file_name})" if payload.file_name else ""
        if payload.file_type.startswith("image/"):
            user_content_parts.append({"type": "image", "source": {"type": "base64", "media_type": payload.file_type, "data": payload.file_data}})
            user_content_parts.append({"type": "text", "text": f"[Fichier joint{file_name_info}]\n{payload.query}" if payload.query else f"[Image jointe{file_name_info}] Analyse ce document."})
        elif payload.file_type == "application/pdf":
            user_content_parts.append({"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": payload.file_data}})
            user_content_parts.append({"type": "text", "text": f"[PDF joint{file_name_info}]\n{payload.query}" if payload.query else f"[PDF joint{file_name_info}] Analyse ce document."})
        else:
            user_content_parts.append({"type": "text", "text": f"[Fichier joint{file_name_info}]\n{payload.query}"})
    else:
        user_content_parts = payload.query

    if is_admin:
        identity = f"""Tu es Aria, l'assistante personnelle de {display_name} — Couffrant Solar (photovoltaïque, 8 personnes, Centre-Val de Loire).
Tu es autonome et apprenante. Tu n'as pas de règles imposées de l'extérieur — tes règles viennent de ce que tu as appris au fil des échanges.
Tu parles au féminin. Tu proposes avant d'agir sauf si {display_name} dit explicitement de procéder."""
    else:
        identity = f"""Tu es Aria, l'assistante de {display_name} — Couffrant Solar (photovoltaïque, Centre-Val de Loire).
Tu aides {display_name} dans son travail quotidien et apprends ses habitudes au fil des échanges.
Tu parles au féminin. Tu proposes avant d'agir."""

    mail_delete_line = "[ACTION:DELETE:message_id] → corbeille récupérable" if mail_can_delete else ""
    mailboxes_line = f"Boîtes mail configurées : {', '.join(mail_extra_boxes)}" if mail_extra_boxes else ""
    drive_section = """\nActions Drive SharePoint (1_Photovoltaïque) :
Affichage : 📁 "Nom"  [id:ID_COMPLET] — utilise l'ID complet
[ACTION:LISTDRIVE:] [ACTION:LISTDRIVE:ID] [ACTION:READDRIVE:ID] [ACTION:SEARCHDRIVE:mot-clé]"""
    if drive_write:
        drive_section += "\n[ACTION:CREATEFOLDER:parent_id|nom] [ACTION:MOVEDRIVE:item_id|dest_id|nom] [ACTION:COPYFILE:source_id|dest_id|nom]"
    if drive_can_delete:
        drive_section += "\n(Suppression de fichiers disponible — sera implémentée dans une prochaine version.)"
    if not drive_write:
        drive_section += "\n(Drive en lecture seule pour ton compte.)"
    odoo_section = ""
    if odoo_enabled:
        if odoo_access == 'full':
            odoo_section = f"\nOdoo (accès complet) — tu peux lire et agir sur les données."
        else:
            shared_info = f" via les credentials de {odoo_shared_user.capitalize()}" if odoo_shared_user else ""
            odoo_section = f"\nOdoo (lecture seule{shared_info}) — tu peux consulter les données mais pas les modifier."
    auto_evolution_section = f"""
Auto-évolution — tu es juge de l'apprentissage de {display_name} :
LEARN et INSIGHT sont personnels à {display_name} et persistent entre les sessions. Tu apprends en silence.
[ACTION:LEARN:category|rule] [ACTION:INSIGHT:topic|texte] [ACTION:FORGET:rule_id] [ACTION:SYNTH:]"""

    system = f"""{identity}

{f"=== CONTEXTE OPÉRATIONNEL ==={chr(10)}{hot_summary}" if hot_summary else ""}

{f"=== TES RÈGLES ==={chr(10)}{aria_rules}" if aria_rules else f"Pas encore de règles pour {display_name}."}

{f"=== TES INSIGHTS ==={chr(10)}{aria_insights}" if aria_insights else ""}

{f"=== FICHE CONTACT ==={chr(10)}{contact_card}" if contact_card else ""}

{f"=== STYLE ==={chr(10)}{style_examples}" if style_examples else ""}

{mailboxes_line}
{"Microsoft 365 connecté." if outlook_token else f"Pas de connexion Microsoft — {display_name} doit se connecter via /login."}
{odoo_section}

IDENTIFIANTS : message_id Outlook (long) → actions mail | gmail_perso = lecture seule

Actions mail :
[ACTION:ARCHIVE:message_id] [ACTION:READ:message_id] [ACTION:READBODY:message_id]
[ACTION:REPLY:message_id:texte] [ACTION:CREATEEVENT:sujet|debut_iso|fin_iso|participants]
[ACTION:CREATE_TASK:titre]{chr(10) + mail_delete_line if mail_delete_line else ''}
{drive_section}
{auto_evolution_section}

Agenda ({datetime.now().strftime('%A %d %B %Y')}) :
{json.dumps(agenda_today, ensure_ascii=False, default=str) if agenda_today else "Aucun RDV."}

=== MAILS {display_name.upper()} ({len(outlook_live_mails)} inbox) ===
{json.dumps(outlook_live_mails, ensure_ascii=False, default=str) if outlook_live_mails else "Aucun."}

=== MAILS BASE ===
{json.dumps(mails_from_db, ensure_ascii=False, default=str)}

Consignes : {chr(10).join(instructions) if instructions else "Aucune."}
"""

    messages = []
    for h in history:
        messages.append({"role": "user", "content": h["user_input"]})
        messages.append({"role": "assistant", "content": h["aria_response"]})
    messages.append({"role": "user", "content": user_content_parts})

    response = client.messages.create(
        model=ANTHROPIC_MODEL_SMART, max_tokens=2048, system=system, messages=messages,
    )
    aria_response = response.content[0].text
    actions_confirmed = []

    def is_valid_outlook_id(msg_id: str) -> bool:
        return len(msg_id.strip()) > 20

    if outlook_token:
        if mail_can_delete:
            for msg_id in re.findall(r'\[ACTION:DELETE:([^\]]+)\]', aria_response):
                msg_id = msg_id.strip()
                if not is_valid_outlook_id(msg_id): continue
                try:
                    result = perform_outlook_action("delete_message", {"message_id": msg_id}, outlook_token)
                    actions_confirmed.append("✅ Mis à la corbeille" if result.get("status") == "ok" else f"❌ {result.get('message')}")
                except Exception as e:
                    actions_confirmed.append(f"❌ {str(e)[:80]}")

        for msg_id in re.findall(r'\[ACTION:ARCHIVE:([^\]]+)\]', aria_response):
            msg_id = msg_id.strip()
            if not is_valid_outlook_id(msg_id): continue
            try:
                result = perform_outlook_action("archive_message", {"message_id": msg_id}, outlook_token)
                actions_confirmed.append("✅ Archivé" if result.get("status") == "ok" else f"❌ {result.get('message')}")
            except Exception as e:
                actions_confirmed.append(f"❌ {str(e)[:80]}")

        for msg_id in re.findall(r'\[ACTION:READ:([^\]]+)\]', aria_response):
            msg_id = msg_id.strip()
            if not is_valid_outlook_id(msg_id): continue
            try: perform_outlook_action("mark_as_read", {"message_id": msg_id}, outlook_token)
            except Exception: pass

        for match in re.finditer(r'\[ACTION:REPLY:([^:\]]{20,}):(.+?)\]', aria_response, re.DOTALL):
            msg_id = match.group(1).strip(); reply_text = match.group(2).strip()
            if not is_valid_outlook_id(msg_id): continue
            try:
                result = perform_outlook_action("send_reply", {"message_id": msg_id, "reply_body": reply_text}, outlook_token)
                if result.get("status") == "ok":
                    try: learn_from_correction(original="", corrected=reply_text, context="réponse mail", username=username)
                    except Exception: pass
                actions_confirmed.append("✅ Réponse envoyée" if result.get("status") == "ok" else f"❌ {result.get('message')}")
            except Exception as e:
                actions_confirmed.append(f"❌ {str(e)[:80]}")

        for msg_id in re.findall(r'\[ACTION:READBODY:([^\]]+)\]', aria_response):
            msg_id = msg_id.strip()
            if not is_valid_outlook_id(msg_id): continue
            try:
                result = perform_outlook_action("get_message_body", {"message_id": msg_id}, outlook_token)
                if result.get("status") == "ok":
                    actions_confirmed.append(f"📧 Corps du mail :\n{result.get('body_text', '')[:800]}")
            except Exception: pass

        for match in re.finditer(r'\[ACTION:CREATEEVENT:([^\]]+)\]', aria_response):
            parts = match.group(1).split('|')
            if len(parts) >= 3:
                try:
                    attendees = parts[3].split(',') if len(parts) > 3 else []
                    result = perform_outlook_action("create_calendar_event",
                        {"subject": parts[0], "start": parts[1], "end": parts[2], "attendees": attendees}, outlook_token)
                    actions_confirmed.append("✅ RDV créé" if result.get("status") == "ok" else "❌ RDV échoué")
                except Exception: pass

        for title in re.findall(r'\[ACTION:CREATE_TASK:([^\]]+)\]', aria_response):
            try: perform_outlook_action("create_todo_task", {"title": title.strip()}, outlook_token)
            except Exception: pass

        for match in re.finditer(r'\[ACTION:LISTDRIVE:([^\]]*)\]', aria_response):
            subfolder = match.group(1).strip()
            try:
                result = list_aria_drive(outlook_token, subfolder)
                if result.get("status") == "ok":
                    lines = []
                    for it in result.get("items", []):
                        icon = "📁" if it.get("type") == "dossier" else "📄"
                        size_str = f"  ({it.get('taille_ko','')} Ko)" if it.get("taille_ko") else ""
                        lines.append(f"  {icon} \"{it['nom']}\"  [id:{it.get('id','')}]{size_str}")
                    actions_confirmed.append(f"📂 {result.get('dossier', '1_Photovoltaïque')} ({result['count']}) :\n" + "\n".join(lines))
                else:
                    actions_confirmed.append(f"❌ {result.get('message', 'Erreur Drive')}")
            except Exception as e:
                actions_confirmed.append(f"❌ Drive : {str(e)[:80]}")

        for match in re.finditer(r'\[ACTION:READDRIVE:([^\]]+)\]', aria_response):
            file_ref = match.group(1).strip()
            try:
                result = read_aria_drive_file(outlook_token, file_ref)
                if result.get("status") == "ok":
                    if result.get("type") == "texte":
                        actions_confirmed.append(f"📄 {result['fichier']} :\n{result['contenu'][:2000]}")
                    else:
                        actions_confirmed.append(f"📄 {result.get('fichier', file_ref)} — {result.get('message', '')} {result.get('conseil', '')}")
                else:
                    actions_confirmed.append(f"❌ {result.get('message')}")
            except Exception as e:
                actions_confirmed.append(f"❌ {str(e)[:80]}")

        for match in re.finditer(r'\[ACTION:SEARCHDRIVE:([^\]]+)\]', aria_response):
            query_drive = match.group(1).strip()
            try:
                result = search_aria_drive(outlook_token, query_drive)
                if result.get("status") == "ok":
                    lines = [f"  {'📁' if it.get('type')=='dossier' else '📄'} \"{it['nom']}\"  [id:{it.get('id','')}]" for it in result.get("items", [])]
                    actions_confirmed.append(f"🔍 '{query_drive}' — {result['count']} résultat(s) :\n" + "\n".join(lines))
                else:
                    actions_confirmed.append(f"❌ {result.get('message')}")
            except Exception as e:
                actions_confirmed.append(f"❌ {str(e)[:80]}")

        if drive_write:
            for match in re.finditer(r'\[ACTION:CREATEFOLDER:([^|^\]]+)\|([^\]]+)\]', aria_response):
                parent_id = match.group(1).strip(); folder_name = match.group(2).strip()
                try:
                    from app.connectors.outlook_connector import _find_sharepoint_site_and_drive
                    _, drive_id, _ = _find_sharepoint_site_and_drive(outlook_token)
                    result = create_drive_folder(outlook_token, parent_id, folder_name, drive_id)
                    actions_confirmed.append(f"✅ Dossier '{folder_name}' créé  [id:{result.get('id','')}]" if result.get("status") == "ok" else f"❌ {result.get('message')}")
                except Exception as e:
                    actions_confirmed.append(f"❌ {str(e)[:80]}")

            for match in re.finditer(r'\[ACTION:MOVEDRIVE:([^|^\]]+)\|([^|^\]]+)\|?([^\]]*)\]', aria_response):
                item_id=match.group(1).strip(); dest_id=match.group(2).strip(); new_name=match.group(3).strip() or None
                try:
                    from app.connectors.outlook_connector import _find_sharepoint_site_and_drive
                    _, drive_id, _ = _find_sharepoint_site_and_drive(outlook_token)
                    result = move_drive_item(outlook_token, item_id, dest_id, new_name, drive_id)
                    actions_confirmed.append(f"✅ {result.get('message', 'Déplacé.')}" if result.get("status") == "ok" else f"❌ {result.get('message')}")
                except Exception as e:
                    actions_confirmed.append(f"❌ {str(e)[:80]}")

            for match in re.finditer(r'\[ACTION:COPYFILE:([^|^\]]+)\|([^|^\]]+)\|?([^\]]*)\]', aria_response):
                source_id=match.group(1).strip(); dest_id=match.group(2).strip(); new_name=match.group(3).strip() or None
                try:
                    from app.connectors.outlook_connector import _find_sharepoint_site_and_drive
                    _, drive_id, _ = _find_sharepoint_site_and_drive(outlook_token)
                    result = copy_drive_item(outlook_token, source_id, dest_id, new_name, drive_id)
                    actions_confirmed.append(f"✅ {result.get('message', 'Copie lancée.')}" if result.get("status") == "ok" else f"❌ {result.get('message')}")
                except Exception as e:
                    actions_confirmed.append(f"❌ {str(e)[:80]}")

    if MEMORY_OK:
        for match in re.finditer(r'\[ACTION:LEARN:([^|^\]]+)\|([^\]]+)\]', aria_response):
            category=match.group(1).strip(); rule=match.group(2).strip()
            try:
                save_rule(category, rule, "auto", 0.7, username)
                actions_confirmed.append(f"🧠 Règle mémorisée [{category}] : {rule[:60]}")
            except Exception as e: print(f"[LEARN] Erreur: {e}")

        for match in re.finditer(r'\[ACTION:INSIGHT:([^|^\]]+)\|([^\]]+)\]', aria_response):
            topic=match.group(1).strip(); insight=match.group(2).strip()
            try:
                save_insight(topic, insight, "auto", username)
                actions_confirmed.append(f"💡 Insight noté [{topic}] : {insight[:60]}")
            except Exception as e: print(f"[INSIGHT] Erreur: {e}")

        for match in re.finditer(r'\[ACTION:FORGET:(\d+)\]', aria_response):
            rule_id = int(match.group(1))
            try:
                deleted = delete_rule(rule_id, username)
                actions_confirmed.append(f"🗑️ Règle {rule_id} désactivée." if deleted else f"❌ Règle {rule_id} introuvable.")
            except Exception as e: print(f"[FORGET] Erreur: {e}")

        for _ in re.finditer(r'\[ACTION:SYNTH:\]', aria_response):
            try:
                import threading
                threading.Thread(target=lambda u=username: synthesize_session(15, u), daemon=True).start()
                actions_confirmed.append("🔄 Synthèse lancée en arrière-plan.")
            except Exception as e: print(f"[SYNTH] Erreur: {e}")

    clean_response = re.sub(r'\[ACTION:[A-Z_]+:[^\]]*\]', '', aria_response).strip()
    if actions_confirmed:
        clean_response += "\n\n" + "\n".join(actions_confirmed)

    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("INSERT INTO aria_memory (username, user_input, aria_response) VALUES (%s, %s, %s)",
                  (username, payload.query, clean_response))
        conn.commit()
    finally:
        if conn: conn.close()

    synth_threshold = get_memoire_param(username, "synth_threshold", 15)
    if MEMORY_OK and conv_count >= synth_threshold:
        try:
            import threading
            threading.Thread(target=lambda u=username: synthesize_session(synth_threshold, u), daemon=True).start()
        except Exception: pass

    return {"answer": clean_response, "actions": actions_confirmed}


# ─── MÉMOIRE ───

@app.get("/build-memory")
def build_memory(request: Request):
    username = request.session.get("user", "guillaume")
    results = {"memory_module": MEMORY_OK, "username": username}
    if not MEMORY_OK: return {"error": "Module mémoire non disponible"}
    try:
        summary = rebuild_hot_summary(username)
        results["hot_summary"] = "✅ Résumé chaud reconstruit"; results["preview"] = summary[:200]
    except Exception as e: results["hot_summary"] = f"❌ {str(e)[:100]}"
    try:
        count = rebuild_contacts(); results["contacts"] = f"✅ {count} fiches contacts (partagées)"
    except Exception as e: results["contacts"] = f"❌ {str(e)[:100]}"
    try:
        added = load_sent_mails_to_style(limit=50, username=username)
        results["style"] = f"✅ {added} exemples de style"
    except Exception as e: results["style"] = f"❌ {str(e)[:100]}"
    return results


@app.get("/memory-status")
def memory_status(request: Request):
    username = request.session.get("user", "guillaume")
    conn = None
    try:
        conn = get_pg_conn(); c = conn.cursor()
        try:
            c.execute("SELECT content FROM aria_hot_summary WHERE username = %s", (username,))
            row = c.fetchone()
        except Exception: row = None
        counts = {}
        for table, key in [
            ("aria_contacts", "contacts"),
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


@app.get("/synth")
def trigger_synth(request: Request, n: int = 15):
    username = request.session.get("user", "guillaume")
    if not MEMORY_OK: return {"error": "Module mémoire non disponible"}
    return synthesize_session(n, username)


@app.get("/rules")
def list_rules(request: Request):
    username = request.session.get("user", "guillaume")
    conn = None
    try:
        conn = get_pg_conn(); c = conn.cursor()
        c.execute("SELECT id,category,rule,source,confidence,reinforcements,active,created_at FROM aria_rules WHERE username=%s ORDER BY active DESC,confidence DESC,created_at DESC", (username,))
        columns = [d[0] for d in c.description]
        return [dict(zip(columns, row)) for row in c.fetchall()]
    finally:
        if conn: conn.close()


@app.get("/insights")
def list_insights(request: Request):
    username = request.session.get("user", "guillaume")
    conn = None
    try:
        conn = get_pg_conn(); c = conn.cursor()
        c.execute("SELECT id,topic,insight,reinforcements,created_at FROM aria_insights WHERE username=%s ORDER BY reinforcements DESC,updated_at DESC", (username,))
        columns = [d[0] for d in c.description]
        return [dict(zip(columns, row)) for row in c.fetchall()]
    finally:
        if conn: conn.close()


@app.get("/analyze-raw-mails")
def analyze_raw_mails(request: Request, limit: int = 50):
    username = request.session.get("user", "guillaume")
    conn = None
    try:
        conn = get_pg_conn(); c = conn.cursor()
        c.execute("""
            SELECT id, message_id, from_email, subject, raw_body_preview, received_at
            FROM mail_memory WHERE username=%s AND analysis_status IN ('inbox_raw','archive_raw','gmail_raw')
            ORDER BY received_at DESC NULLS LAST LIMIT %s
        """, (username, limit))
        rows = c.fetchall()
    finally:
        if conn: conn.close()
    if not rows: return {"status": "termine", "analyzed": 0}
    instructions = get_global_instructions()
    analyzed = errors = 0
    for row in rows:
        db_id, message_id, from_email, subject, body_preview, received_at = row
        msg = {"id": message_id, "subject": subject, "from": {"emailAddress": {"address": from_email or ""}},
               "receivedDateTime": str(received_at) if received_at else "", "bodyPreview": body_preview or ""}
        try:
            item = analyze_single_mail_with_ai(msg, instructions, username)
            conn = None
            try:
                conn = get_pg_conn(); c = conn.cursor()
                c.execute("""
                    UPDATE mail_memory SET display_title=%s,category=%s,priority=%s,reason=%s,
                    suggested_action=%s,short_summary=%s,confidence=%s,confidence_level=%s,
                    needs_review=%s,needs_reply=%s,reply_urgency=%s,reply_reason=%s,
                    response_type=%s,suggested_reply_subject=%s,suggested_reply=%s,analysis_status='done_ai'
                    WHERE id=%s AND username=%s
                """, (item.get("display_title"),item.get("category"),item.get("priority"),item.get("reason"),
                       item.get("suggested_action"),item.get("short_summary"),item.get("confidence",0.5),
                       item.get("confidence_level","moyenne"),int(item.get("needs_review",False)),
                       int(item.get("needs_reply",False)),item.get("reply_urgency"),item.get("reply_reason"),
                       item.get("response_type"),item.get("suggested_reply_subject"),item.get("suggested_reply"),
                       db_id, username))
                conn.commit()
            finally:
                if conn: conn.close()
            analyzed += 1
        except Exception as e:
            print(f"[AnalyzeRaw] Erreur {db_id}: {e}"); errors += 1
    conn = None
    try:
        conn = get_pg_conn(); c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM mail_memory WHERE username=%s AND analysis_status IN ('inbox_raw','archive_raw','gmail_raw')", (username,))
        remaining = c.fetchone()[0]
    finally:
        if conn: conn.close()
    return {"status": "ok", "analyzed": analyzed, "errors": errors, "remaining": remaining}


@app.get("/contacts")
def list_contacts_endpoint():
    return get_all_contact_cards()


@app.get("/purge-memory")
def purge_memory(request: Request, days: int = 90):
    username = request.session.get("user", "guillaume")
    return {"status": "ok", "deleted": purge_old_mails(days=days, username=username)}


@app.post("/learn-style")
def learn_style(request: Request, payload: dict = Body(...)):
    username = request.session.get("user", "guillaume")
    text = payload.get("text", "")
    if not text: return {"error": "Texte manquant"}
    save_style_example(situation=payload.get("situation", "mail"), example_text=text,
                       tags=payload.get("tags", ""), quality_score=2.0, username=username)
    return {"status": "ok"}


@app.get("/login")
def login(request: Request, next: str = "/chat"):
    msal_app = build_msal_app()
    auth_url = msal_app.get_authorization_request_url(scopes=GRAPH_SCOPES, redirect_uri=REDIRECT_URI, state=next)
    return RedirectResponse(auth_url)


@app.get("/auth/callback")
def auth_callback(request: Request, code: str | None = None, state: str | None = None):
    if not code: return HTMLResponse("Code manquant", status_code=400)
    msal_app = build_msal_app()
    result = msal_app.acquire_token_by_authorization_code(code, scopes=GRAPH_SCOPES, redirect_uri=REDIRECT_URI)
    if "access_token" not in result: return HTMLResponse("Erreur d'authentification", status_code=400)
    request.session["access_token"] = result["access_token"]
    username = request.session.get("user", "guillaume")
    save_microsoft_token(username, result["access_token"], result.get("refresh_token", ""),
                         result.get("expires_in", 3600))
    return RedirectResponse(state or "/chat")


@app.get("/triage-queue")
def triage_queue(request: Request):
    username = request.session.get("user", "guillaume")
    token = get_valid_microsoft_token(username)
    if not token: return {"mails": [], "count": 0, "error": "Token Microsoft manquant"}
    try:
        data = graph_get(token, "/me/mailFolders/inbox/messages", params={
            "$top": 50, "$select": "id,subject,from,receivedDateTime,bodyPreview,isRead",
            "$orderby": "receivedDateTime DESC"})
        return {"mails": [{"message_id": m["id"],
                           "from_email": m.get("from",{}).get("emailAddress",{}).get("address",""),
                           "subject": m.get("subject",""), "received_at": m.get("receivedDateTime",""),
                           "is_read": m.get("isRead", False)} for m in data.get("value", [])],
                "count": len(data.get("value", []))}
    except Exception as e:
        return {"mails": [], "count": 0, "error": str(e)}


@app.get("/memory")
def memory(request: Request):
    username = request.session.get("user", "guillaume")
    conn = None
    try:
        conn = get_pg_conn(); c = conn.cursor()
        c.execute("SELECT message_id,received_at,from_email,subject,display_title,category,priority,analysis_status FROM mail_memory WHERE username=%s ORDER BY id DESC LIMIT 20", (username,))
        columns = [desc[0] for desc in c.description]
        return [dict(zip(columns, row)) for row in c.fetchall()]
    finally:
        if conn: conn.close()


@app.get("/rebuild-memory")
def rebuild_memory_mails(request: Request):
    username = request.session.get("user", "guillaume")
    conn = None
    try:
        conn = get_pg_conn(); c = conn.cursor()
        c.execute("DELETE FROM mail_memory WHERE username=%s", (username,)); conn.commit()
    finally:
        if conn: conn.close()
    return {"status": "mail_memory_cleared", "username": username}


@app.get("/learn-sent-mails")
def learn_sent_mails(request: Request, top: int = 50):
    username = request.session.get("user", "guillaume")
    token = get_valid_microsoft_token(username)
    if not token: return RedirectResponse("/login?next=/learn-sent-mails")
    try:
        data = graph_get(token, "/me/mailFolders/SentItems/messages", params={
            "$top": top, "$select": "id,subject,from,receivedDateTime,bodyPreview,toRecipients",
            "$orderby": "receivedDateTime DESC"})
    except requests.HTTPError:
        return RedirectResponse("/login?next=/learn-sent-mails")
    inserted = 0
    conn = None
    try:
        conn = get_pg_conn(); c = conn.cursor()
        for msg in data.get("value", []):
            message_id = msg["id"]
            c.execute("SELECT 1 FROM sent_mail_memory WHERE message_id=%s AND username=%s", (message_id, username))
            if c.fetchone(): continue
            to_recipients = msg.get("toRecipients", [])
            to_email = to_recipients[0].get("emailAddress",{}).get("address","") if to_recipients else ""
            try:
                c.execute("INSERT INTO sent_mail_memory (username,message_id,sent_at,to_email,subject,body_preview) VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                          (username, message_id, msg.get("receivedDateTime"), to_email, msg.get("subject"), msg.get("bodyPreview")))
                inserted += 1
            except Exception: continue
        conn.commit()
    finally:
        if conn: conn.close()
    return {"inserted": inserted, "total_fetched": len(data.get("value", []))}


@app.get("/learn-inbox-mails")
def learn_inbox_mails(request: Request, top: int = 50, skip: int = 0):
    username = request.session.get("user", "guillaume")
    token = get_valid_microsoft_token(username)
    if not token: return RedirectResponse("/login?next=/learn-inbox-mails")
    try:
        data = graph_get(token, "/me/mailFolders/inbox/messages", params={
            "$top": top, "$skip": skip,
            "$select": "id,subject,from,receivedDateTime,bodyPreview,toRecipients",
            "$orderby": "receivedDateTime DESC"})
    except requests.HTTPError:
        return RedirectResponse("/login?next=/learn-inbox-mails")
    inserted = skipped_noise = 0
    skip_keywords = get_antispam_keywords(username)  # dynamique depuis aria_rules
    conn = None
    try:
        conn = get_pg_conn(); c = conn.cursor()
        for msg in data.get("value", []):
            message_id = msg["id"]
            c.execute("SELECT 1 FROM mail_memory WHERE message_id=%s AND username=%s", (message_id, username))
            if c.fetchone(): continue
            from_email = msg.get("from",{}).get("emailAddress",{}).get("address","").lower()
            subject = (msg.get("subject") or "").lower()
            body = (msg.get("bodyPreview") or "").lower()
            if any(kw in f"{from_email} {subject} {body}" for kw in skip_keywords):
                skipped_noise += 1; continue
            try:
                c.execute("INSERT INTO mail_memory (username,message_id,received_at,from_email,subject,raw_body_preview,analysis_status,created_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                          (username, message_id, msg.get("receivedDateTime"),
                           msg.get("from",{}).get("emailAddress",{}).get("address",""),
                           msg.get("subject"), msg.get("bodyPreview"), "inbox_raw", datetime.utcnow().isoformat()))
                inserted += 1
            except Exception: continue
        conn.commit()
    finally:
        if conn: conn.close()
    return {"inserted": inserted, "skipped_noise": skipped_noise, "total_fetched": len(data.get("value", []))}


@app.get("/build-style-profile")
def build_style_profile(request: Request):
    username = request.session.get("user", "guillaume")
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


@app.post("/instruction")
def add_instruction(instruction: str = Form(...)):
    add_global_instruction(instruction)
    return RedirectResponse("/chat", status_code=303)


@app.get("/login/gmail")
def login_gmail():
    from app.connectors.gmail_connector import get_gmail_auth_url
    return RedirectResponse(get_gmail_auth_url())


@app.get("/auth/gmail/callback")
def auth_gmail_callback(request: Request, code: str | None = None):
    if not code: return HTMLResponse("Code manquant", status_code=400)
    from app.connectors.gmail_connector import exchange_code_for_tokens
    tokens = exchange_code_for_tokens(code)
    conn = None
    try:
        conn = get_pg_conn(); c = conn.cursor()
        c.execute("DELETE FROM gmail_tokens WHERE email=%s", ("per1.guillaume@gmail.com",))
        c.execute("INSERT INTO gmail_tokens (email,access_token,refresh_token) VALUES (%s,%s,%s)",
                  ("per1.guillaume@gmail.com", tokens.get("access_token"), tokens.get("refresh_token")))
        conn.commit()
    finally:
        if conn: conn.close()
    return {"status": "ok", "message": "Gmail connecté !"}


@app.get("/ingest-gmail")
def ingest_gmail(request: Request):
    username = request.session.get("user", "guillaume")
    from app.connectors.gmail_connector import gmail_get_messages, gmail_get_message, refresh_gmail_token
    conn = None
    try:
        conn = get_pg_conn(); c = conn.cursor()
        c.execute("SELECT access_token,refresh_token FROM gmail_tokens WHERE email=%s", ("per1.guillaume@gmail.com",))
        row = c.fetchone()
    finally:
        if conn: conn.close()
    if not row: return {"error": "Gmail non connecté"}
    access_token, refresh_token = row[0], row[1]
    try:
        messages = gmail_get_messages(access_token, max_results=10)
    except Exception:
        access_token = refresh_gmail_token(refresh_token)
        messages = gmail_get_messages(access_token, max_results=10)
    inserted = 0
    skip_keywords = ["noreply","no-reply","donotreply","newsletter","unsubscribe","se désabonner",
                     "notification","mailer-daemon","marketing","promo","offre spéciale",
                     "linkedin","twitter","facebook","instagram","jobteaser","indeed","welcometothejungle"]
    conn = None
    try:
        conn = get_pg_conn(); c = conn.cursor()
        for msg in messages:
            message_id = msg["id"]
            c.execute("SELECT 1 FROM mail_memory WHERE message_id=%s AND username=%s", (message_id, username))
            if c.fetchone(): continue
            try:
                detail = gmail_get_message(access_token, message_id)
                headers = {h["name"]: h["value"] for h in detail.get("payload",{}).get("headers",[])}
                subject = headers.get("Subject", "(Sans objet)")
                from_email = headers.get("From", "")
                date = headers.get("Date", "")
                snippet = detail.get("snippet", "")
                if any(kw in f"{from_email} {subject} {snippet}".lower() for kw in skip_keywords): continue
                c.execute("INSERT INTO mail_memory (username,message_id,received_at,from_email,subject,raw_body_preview,analysis_status,mailbox_source,created_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                          (username, message_id, date, from_email, subject, snippet, "gmail_raw", "gmail_perso", datetime.utcnow().isoformat()))
                inserted += 1
            except Exception:
                conn.rollback(); continue
        conn.commit()
    finally:
        if conn: conn.close()
    return {"inserted": inserted, "total_fetched": len(messages)}


@app.get("/assistant-dashboard")
def assistant_dashboard(request: Request, days: int = 2):
    username = request.session.get("user", "guillaume")
    return get_dashboard(days, username)


@app.get("/test-elevenlabs")
def test_elevenlabs():
    api_key = os.environ.get("ELEVENLABS_API_KEY", "")
    voice_id = os.environ.get("ELEVENLABS_VOICE_ID", "")
    resp = requests.post(f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
        headers={"xi-api-key": api_key, "Content-Type": "application/json"},
        json={"text": "Bonjour.", "model_id": "eleven_flash_v2_5",
              "voice_settings": {"stability": 0.5, "similarity_boost": 0.8}}, timeout=30)
    return {"status_code": resp.status_code, "api_key_length": len(api_key), "voice_id": voice_id}


@app.get("/test-odoo")
def test_odoo():
    from app.connectors.odoo_connector import perform_odoo_action
    return perform_odoo_action(action="get_partner_by_email", params={"email": "guillaume@couffrant-solar.fr"})


@app.get("/reorganize-drive")
def reorganize_drive(request: Request):
    if not _require_admin(request): return {"error": "Réservé à l'admin."}
    import threading
    from app.connectors.outlook_connector import (_find_sharepoint_site_and_drive, _find_folder_item_id, _graph_get)
    username = request.session.get("user", "guillaume")
    token = get_valid_microsoft_token(username)
    if not token: return {"error": "Token Microsoft manquant"}
    _, drive_id, _ = _find_sharepoint_site_and_drive(token)
    if not drive_id: return {"error": "Drive SharePoint 'Commun' introuvable"}
    _, source_id = _find_folder_item_id(token, drive_id)
    if not source_id: return {"error": "Dossier 1_Photovoltaïque introuvable"}

    def run_reorganize():
        import time
        try:
            data = _graph_get(token, f"/drives/{drive_id}/items/{source_id}/children",
                             params={"$top": 100, "$select": "name,id,folder,file"})
            items_by_name = {f.get("name"): f.get("id") for f in data.get("value", [])}
            source_meta = _graph_get(token, f"/drives/{drive_id}/items/{source_id}", params={"$select": "id,parentReference"})
            parent_id = source_meta.get("parentReference", {}).get("id")
            if not parent_id: return

            def mk(parent, name):
                r = create_drive_folder(token, parent, name, drive_id)
                if r.get("status") == "ok": print(f"[Reorganize] ✅ {name}"); return r.get("id")
                return None

            def cp(source_name, dest_id, new_name=None):
                item_id = items_by_name.get(source_name)
                if not item_id: return
                r = copy_drive_item(token, item_id, dest_id, new_name, drive_id)
                print(f"[Reorganize] {'✅' if r.get('status')=='ok' else '❌'} {source_name}")

            v2_id = mk(parent_id, "1_Photovoltaïque_V2")
            if not v2_id: return
            time.sleep(1)
            cat01=mk(v2_id,"01_Commercial"); cat02=mk(v2_id,"02_Chantiers")
            cat03=mk(v2_id,"03_Administratif_Reglementaire"); cat04=mk(v2_id,"04_Documentation_Technique")
            cat05=mk(v2_id,"05_Fournisseurs_Partenaires"); cat06=mk(v2_id,"06_Outils_et_Logiciels")
            cat07=mk(v2_id,"07_RH_et_Stock"); time.sleep(1)
            if cat01: cp("1_1 Chiffrage Particulier",cat01,"Chiffrage_Particuliers"); cp("1_Chiffrage Pro",cat01,"Chiffrage_Pro")
            if cat02:
                cp("Pilotage",cat02); cp("1_SUIVI CHANTIER PV modifié.xlsm",cat02)
                cp("Photo vidéo chantier en cours",cat02,"Photos_et_Videos"); cp("Photos drone",cat02,"Photos_Drone")
            if cat03:
                cp("2_CONSUEL",cat03,"CONSUEL"); cp("3_ENEDIS",cat03,"ENEDIS")
                cp("4_Demandes DP Cerfa et Raccordement",cat03,"Demandes_DP"); cp("Procédure d'aide EDF OA.docx",cat03)
            if cat04:
                cp("5_Document technique",cat04,"Docs_Techniques"); cp("Normes",cat04); cp("Import ELEC",cat04)
                cp("6_Audits et rapports",cat04,"Audits")
                for f in ["DOE_Couffrant_Solar_Complet_Modele.docx","DOE_Couffrant_Solar_Modele_Reutilisable.docx",
                           "DOE_Photovoltaique_Couffrant_Solar_Complet.docx","PV fin de chantier.docx","RAPPORT AUDIT PV.docx"]:
                    cp(f, cat04)
            if cat05:
                for f in ["Adiwatt","MADENR","Urban Solar","Powr Connect","formulaire compensation solaredge.pdf",
                           "Demande garantie Onduleur 1 – Copie.xlsx","Demande garantie Onduleur.xlsx"]: cp(f,cat05)
            if cat06:
                for f in ["Formation archelios calc","sauvegarde Archelios","Logiciels","unnamed.png"]: cp(f,cat06)
            if cat07:
                for f in ["Certificats et Formations Professionnels","8_Stock 2026.ods","Suivi panneau publicitaire.xlsx"]: cp(f,cat07)
            print("[Reorganize] Terminé.")
        except Exception as e: print(f"[Reorganize] Erreur : {e}")

    threading.Thread(target=run_reorganize, daemon=True).start()
    return {"status": "started", "message": "Réorganisation lancée. Vérifiez SharePoint dans 5-10 minutes.", "note": "Les originaux restent intacts."}
