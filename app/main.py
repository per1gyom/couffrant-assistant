import os
import requests
import json
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI, Request, Form, Body
from fastapi.responses import RedirectResponse, HTMLResponse, StreamingResponse
from starlette.middleware.sessions import SessionMiddleware
from pydantic import BaseModel

from app.auth import build_msal_app
from app.config import (
    GRAPH_SCOPES, REDIRECT_URI, SESSION_SECRET,
    AUTHORITY, ANTHROPIC_MODEL_SMART
)
from app.graph_client import graph_get
from app.ai_client import summarize_messages, analyze_single_mail_with_ai, client
from app.feedback_store import init_db, add_global_instruction, get_global_instructions
from app.mail_memory_store import init_mail_db, insert_mail, mail_exists
from app.assistant_analyzer import analyze_single_mail
from app.dashboard_service import get_dashboard
from app.connectors.outlook_connector import perform_outlook_action
from app.database import get_pg_conn, init_postgres
from app.memory_manager import (
    get_hot_summary, rebuild_hot_summary,
    get_contact_card, get_all_contact_cards, rebuild_contacts,
    get_style_examples, save_style_example, learn_from_correction, load_sent_mails_to_style,
    purge_old_mails
)


app = FastAPI(title="Couffrant Solar Assistant")
app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET)


class AriaQuery(BaseModel):
    query: str


@app.on_event("startup")
def startup_event():
    init_postgres()
    init_db()
    init_mail_db()

    import threading
    def auto_ingest():
        import time
        cycle = 0
        while True:
            try:
                from app.token_manager import get_valid_microsoft_token
                from app.graph_client import graph_get
                from app.ai_client import analyze_single_mail_with_ai
                from app.mail_memory_store import mail_exists, insert_mail
                from app.feedback_store import get_global_instructions
                from app.assistant_analyzer import analyze_single_mail

                token = get_valid_microsoft_token()
                if token:
                    data = graph_get(
                        token,
                        "/me/mailFolders/inbox/messages",
                        params={
                            "$top": 10,
                            "$select": "id,subject,from,receivedDateTime,bodyPreview",
                            "$orderby": "receivedDateTime DESC",
                        },
                    )
                    messages = data.get("value", [])
                    instructions = get_global_instructions()
                    for msg in messages:
                        message_id = msg["id"]
                        if mail_exists(message_id):
                            continue
                        try:
                            item = analyze_single_mail_with_ai(msg, instructions)
                            analysis_status = "done_ai"
                        except Exception:
                            item = analyze_single_mail(msg)
                            analysis_status = "fallback"
                        insert_mail({
                            "message_id": message_id,
                            "received_at": msg.get("receivedDateTime"),
                            "from_email": msg.get("from", {}).get("emailAddress", {}).get("address"),
                            "subject": msg.get("subject"),
                            "display_title": item.get("display_title"),
                            "category": item.get("category"),
                            "priority": item.get("priority"),
                            "reason": item.get("reason"),
                            "suggested_action": item.get("suggested_action"),
                            "short_summary": item.get("short_summary"),
                            "group_hints": item.get("group_hints", []),
                            "confidence": item.get("confidence", 0.0),
                            "needs_review": item.get("needs_review", False),
                            "raw_body_preview": msg.get("bodyPreview"),
                            "analysis_status": analysis_status,
                            "needs_reply": item.get("needs_reply"),
                            "reply_urgency": item.get("reply_urgency"),
                            "reply_reason": item.get("reply_reason"),
                            "suggested_reply_subject": item.get("suggested_reply_subject"),
                            "suggested_reply": item.get("suggested_reply"),
                            "mailbox_source": "outlook",
                        })

                cycle += 1
                if cycle % 40 == 0:
                    try:
                        rebuild_hot_summary()
                        print("[Memory] Résumé chaud reconstruit")
                    except Exception as e:
                        print(f"[Memory] Erreur résumé chaud: {e}")

            except Exception as e:
                print(f"[AutoIngest] Erreur: {e}")

            time.sleep(30)

    thread = threading.Thread(target=auto_ingest, daemon=True)
    thread.start()


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/init-db")
def init_db_now():
    init_postgres()
    return {"status": "tables créées"}


@app.get("/chat", response_class=HTMLResponse)
def chat(request: Request, pwd: str = ""):
    if pwd != "couffrant2026":
        return HTMLResponse("""
        <html><body style="background:#0a0a0a;color:#fff;display:flex;align-items:center;justify-content:center;height:100vh;font-family:Arial">
        <form method="get">
            <input name="pwd" type="password" placeholder="Mot de passe"
            style="padding:12px;border-radius:8px;border:none;font-size:16px">
            <button type="submit" style="padding:12px 20px;background:#1565c0;color:white;border:none;border-radius:8px;margin-left:8px;cursor:pointer">
            Accéder</button>
        </form></body></html>
        """)
    with open("app/templates/aria_chat.html", "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())


@app.post("/speak")
def speak_text(payload: dict = Body(...)):
    import re, io

    api_key = os.environ.get("ELEVENLABS_API_KEY", "")
    voice_id = os.environ.get("ELEVENLABS_VOICE_ID", "")

    if not api_key or not voice_id:
        return {"error": "Clés ElevenLabs manquantes"}

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
        json={
            "text": clean,
            "model_id": "eleven_flash_v2_5",
            "voice_settings": {"stability": 0.5, "similarity_boost": 0.8, "style": 0.2, "use_speaker_boost": True}
        },
        timeout=30,
    )

    if resp.status_code != 200:
        return {"error": f"ElevenLabs {resp.status_code}", "detail": resp.text[:200]}

    return StreamingResponse(io.BytesIO(resp.content), media_type="audio/mpeg")


@app.post("/aria")
def aria(payload: AriaQuery):
    import re
    from app.token_manager import get_valid_microsoft_token
    instructions = get_global_instructions()

    conn = get_pg_conn()
    c = conn.cursor()

    c.execute("""
        SELECT id as db_id, message_id, from_email, display_title, category, priority,
               short_summary, suggested_reply, raw_body_preview, received_at, mailbox_source
        FROM mail_memory
        ORDER BY received_at DESC NULLS LAST
        LIMIT 10
    """)
    columns = [desc[0] for desc in c.description]
    mails_from_db = [dict(zip(columns, row)) for row in c.fetchall()]

    c.execute("""
        SELECT user_input, aria_response
        FROM aria_memory
        ORDER BY id DESC
        LIMIT 8
    """)
    columns = [desc[0] for desc in c.description]
    history = [dict(zip(columns, row)) for row in c.fetchall()]
    history.reverse()

    c.execute("""
        SELECT content FROM aria_profile
        WHERE profile_type = 'style'
        ORDER BY id DESC LIMIT 1
    """)
    profile_row = c.fetchone()
    profile = profile_row[0] if profile_row else ""
    conn.close()

    hot_summary = get_hot_summary()

    contact_card = ""
    query_lower = payload.query.lower()
    known_contacts = ["arlène", "arlene", "sabrina", "benoit", "maxence", "pinto", "enedis",
                      "adiwatt", "triangle", "eleria", "consuel", "socotec", "charlotte"]
    for name in known_contacts:
        if name in query_lower:
            contact_card = get_contact_card(name)
            if contact_card:
                break

    style_examples = get_style_examples(
        context=payload.query[:100]
        if any(w in query_lower for w in ["répond", "rédige", "écris", "mail"])
        else ""
    )

    outlook_token = get_valid_microsoft_token()

    outlook_live_mails = []
    if outlook_token:
        try:
            data = graph_get(
                outlook_token,
                "/me/mailFolders/inbox/messages",
                params={
                    "$top": 20,
                    "$select": "id,subject,from,receivedDateTime,bodyPreview,isRead",
                    "$orderby": "receivedDateTime DESC",
                },
            )
            for msg in data.get("value", []):
                outlook_live_mails.append({
                    "message_id": msg["id"],
                    "from_email": msg.get("from", {}).get("emailAddress", {}).get("address", ""),
                    "subject": msg.get("subject", "(Sans objet)"),
                    "raw_body_preview": msg.get("bodyPreview", ""),
                    "received_at": msg.get("receivedDateTime", ""),
                    "is_read": msg.get("isRead", False),
                    "mailbox_source": "outlook",
                })
        except Exception as e:
            print(f"[Aria] Erreur Outlook live: {e}")

    agenda_today = []
    if outlook_token:
        try:
            now = datetime.now(timezone.utc)
            start = now.replace(hour=0, minute=0, second=0).isoformat()
            end = now.replace(hour=23, minute=59, second=59).isoformat()
            agenda_result = perform_outlook_action("list_calendar_events", {"start": start, "end": end, "top": 10}, outlook_token)
            agenda_today = agenda_result.get("items", [])
        except Exception:
            pass

    messages = []
    for h in history:
        messages.append({"role": "user", "content": h["user_input"]})
        messages.append({"role": "assistant", "content": h["aria_response"]})
    messages.append({"role": "user", "content": payload.query})

    system = f"""Tu es Aria, l'assistante personnelle de Guillaume Perrin, dirigeant de Couffrant Solar.

Guillaume dirige une PME de 8 personnes dans le photovoltaïque. Direct, efficace, déteste les réponses longues inutiles. Il tutoie Aria.

Profil Guillaume :
{profile[:600] if profile else "Profil en cours de construction."}

=== SITUATION ACTUELLE (résumé — mis à jour toutes les 20 min) ===
{hot_summary if hot_summary else "Résumé pas encore généré — utilise les mails ci-dessous."}

{f"=== FICHE CONTACT ==={chr(10)}{contact_card}" if contact_card else ""}

{f"=== EXEMPLES DE STYLE ==={chr(10)}{style_examples}" if style_examples else ""}

Règles :
- Réponds naturellement, sans structure imposée.
- Si Guillaume dit "oui", "vas-y", "fais-le" → exécute la dernière action proposée.
- Ne dis jamais "c'est fait" sans confirmation API réelle.
- Pour rédiger un mail, utilise les exemples de style.

{"Accès complet Microsoft 365." if outlook_token else "Pas de connexion Microsoft."}

IDENTIFIANTS — CRITIQUE :
- `message_id` : longue chaîne Outlook → TOUJOURS pour les actions
- `db_id` : entier court → JAMAIS pour les actions
- `mailbox_source` : "outlook" (actions OK) | "gmail_perso" (lecture seule)

Actions Outlook :
- [ACTION:DELETE:message_id] → corbeille (récupérable)
- [ACTION:ARCHIVE:message_id]
- [ACTION:READ:message_id]
- [ACTION:REPLY:message_id:texte de la réponse]
- [ACTION:READBODY:message_id]
- [ACTION:CREATEEVENT:sujet|debut_iso|fin_iso|participants]
- [ACTION:CREATE_TASK:titre]

Propose avant d'agir, SAUF si Guillaume dit "fais-le", "vas-y", "oui", "supprime", "archive", "envoie".

Agenda aujourd'hui ({datetime.now().strftime('%A %d %B %Y')}) :
{json.dumps(agenda_today, ensure_ascii=False, default=str) if agenda_today else "Aucun RDV."}

=== MAILS OUTLOOK EN TEMPS RÉEL ({len(outlook_live_mails)} mails inbox) ===
{json.dumps(outlook_live_mails, ensure_ascii=False, default=str) if outlook_live_mails else "Aucun mail Outlook récupéré."}

=== MAILS EN BASE (Gmail + historique) ===
{json.dumps(mails_from_db, ensure_ascii=False, default=str)}

Consignes :
{chr(10).join(instructions) if instructions else "Aucune."}
"""

    response = client.messages.create(
        model=ANTHROPIC_MODEL_SMART,
        max_tokens=2048,
        system=system,
        messages=messages,
    )

    aria_response = response.content[0].text
    actions_confirmed = []

    def is_valid_outlook_id(msg_id: str) -> bool:
        return len(msg_id.strip()) > 20

    if outlook_token:
        # DELETE → corbeille
        for msg_id in re.findall(r'\[ACTION:DELETE:([^\]]+)\]', aria_response):
            msg_id = msg_id.strip()
            if not is_valid_outlook_id(msg_id):
                actions_confirmed.append("❌ ID invalide pour suppression")
                continue
            try:
                result = perform_outlook_action("delete_message", {"message_id": msg_id}, outlook_token)
                actions_confirmed.append("✅ Mis à la corbeille" if result.get("status") == "ok" else f"❌ {result.get('message')}")
            except Exception as e:
                actions_confirmed.append(f"❌ Erreur : {str(e)[:100]}")

        # ARCHIVE
        for msg_id in re.findall(r'\[ACTION:ARCHIVE:([^\]]+)\]', aria_response):
            msg_id = msg_id.strip()
            if not is_valid_outlook_id(msg_id):
                actions_confirmed.append("❌ ID invalide pour archivage")
                continue
            try:
                result = perform_outlook_action("archive_message", {"message_id": msg_id}, outlook_token)
                actions_confirmed.append("✅ Archivé" if result.get("status") == "ok" else f"❌ {result.get('message')}")
            except Exception as e:
                actions_confirmed.append(f"❌ Erreur archivage : {str(e)[:100]}")

        # READ
        for msg_id in re.findall(r'\[ACTION:READ:([^\]]+)\]', aria_response):
            msg_id = msg_id.strip()
            if not is_valid_outlook_id(msg_id):
                continue
            try:
                result = perform_outlook_action("mark_as_read", {"message_id": msg_id}, outlook_token)
                actions_confirmed.append("✅ Marqué lu" if result.get("status") == "ok" else "❌ Erreur")
            except Exception as e:
                actions_confirmed.append(f"❌ Erreur : {str(e)[:100]}")

        # REPLY — regex robuste : message_id ({20,} chars sans ':'), texte = tout jusqu'à ']'
        for match in re.finditer(r'\[ACTION:REPLY:([^:\]]{20,}):(.+?)\]', aria_response, re.DOTALL):
            msg_id = match.group(1).strip()
            reply_text = match.group(2).strip()
            if not is_valid_outlook_id(msg_id):
                actions_confirmed.append("❌ ID invalide pour réponse")
                continue
            try:
                result = perform_outlook_action("send_reply", {"message_id": msg_id, "reply_body": reply_text}, outlook_token)
                if result.get("status") == "ok":
                    try:
                        learn_from_correction(original="", corrected=reply_text, context="réponse mail")
                    except Exception:
                        pass
                actions_confirmed.append("✅ Réponse envoyée" if result.get("status") == "ok" else f"❌ {result.get('message')}")
            except Exception as e:
                actions_confirmed.append(f"❌ Erreur envoi : {str(e)[:100]}")

        # READBODY
        for msg_id in re.findall(r'\[ACTION:READBODY:([^\]]+)\]', aria_response):
            msg_id = msg_id.strip()
            if not is_valid_outlook_id(msg_id):
                actions_confirmed.append("❌ ID invalide pour lecture corps")
                continue
            try:
                result = perform_outlook_action("get_message_body", {"message_id": msg_id}, outlook_token)
                if result.get("status") == "ok":
                    actions_confirmed.append(f"📧 Corps du mail :\n{result.get('body_text', '')[:800]}")
            except Exception as e:
                actions_confirmed.append(f"❌ Erreur lecture corps : {str(e)[:100]}")

        # CREATEEVENT
        for match in re.finditer(r'\[ACTION:CREATEEVENT:([^\]]+)\]', aria_response):
            parts = match.group(1).split('|')
            if len(parts) >= 3:
                try:
                    attendees = parts[3].split(',') if len(parts) > 3 else []
                    result = perform_outlook_action("create_calendar_event", {
                        "subject": parts[0], "start": parts[1], "end": parts[2], "attendees": attendees
                    }, outlook_token)
                    actions_confirmed.append("✅ RDV créé" if result.get("status") == "ok" else "❌ Création RDV échouée")
                except Exception as e:
                    actions_confirmed.append(f"❌ Erreur agenda : {str(e)[:100]}")

        # CREATE_TASK
        for title in re.findall(r'\[ACTION:CREATE_TASK:([^\]]+)\]', aria_response):
            try:
                result = perform_outlook_action("create_todo_task", {"title": title.strip()}, outlook_token)
                actions_confirmed.append("✅ Tâche créée" if result.get("status") == "ok" else "❌ Tâche échouée")
            except Exception as e:
                actions_confirmed.append(f"❌ Erreur tâche : {str(e)[:100]}")

    clean_response = re.sub(r'\[ACTION:[A-Z_]+:[^\]]+\]', '', aria_response).strip()

    if actions_confirmed:
        clean_response += "\n\n" + "\n".join(actions_confirmed)

    conn = get_pg_conn()
    c = conn.cursor()
    c.execute("""
        INSERT INTO aria_memory (user_input, aria_response)
        VALUES (%s, %s)
    """, (payload.query, clean_response))
    conn.commit()
    conn.close()

    return {"answer": clean_response, "actions": actions_confirmed}


# ─────────────────────────────────────────────
# ENDPOINTS MÉMOIRE
# ─────────────────────────────────────────────

@app.get("/build-memory")
def build_memory():
    results = {}
    try:
        summary = rebuild_hot_summary()
        results["hot_summary"] = "✅ Résumé chaud reconstruit"
        results["preview"] = summary[:200]
    except Exception as e:
        results["hot_summary"] = f"❌ {str(e)[:100]}"
    try:
        count = rebuild_contacts()
        results["contacts"] = f"✅ {count} fiches contacts"
    except Exception as e:
        results["contacts"] = f"❌ {str(e)[:100]}"
    try:
        added = load_sent_mails_to_style(limit=50)
        results["style"] = f"✅ {added} exemples de style"
    except Exception as e:
        results["style"] = f"❌ {str(e)[:100]}"
    return results


@app.get("/memory-status")
def memory_status():
    conn = get_pg_conn()
    c = conn.cursor()
    c.execute("SELECT content, updated_at FROM aria_hot_summary WHERE id = 1")
    row = c.fetchone()
    c.execute("SELECT COUNT(*) FROM aria_contacts")
    contacts_count = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM aria_style_examples")
    style_count = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM mail_memory")
    mails_count = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM sent_mail_memory")
    sent_count = c.fetchone()[0]
    conn.close()
    return {
        "resume_chaud": {"exists": bool(row and row[0]), "preview": (row[0] or "")[:150] if row else "", "updated_at": str(row[1]) if row else None},
        "contacts": contacts_count,
        "style_examples": style_count,
        "mail_memory": mails_count,
        "sent_mail_memory": sent_count,
    }


@app.get("/contacts")
def list_contacts_endpoint():
    return get_all_contact_cards()


@app.get("/purge-memory")
def purge_memory(days: int = 90):
    deleted = purge_old_mails(days=days)
    return {"status": "ok", "deleted": deleted, "message": f"{deleted} mails bruts supprimés (restent dans Outlook/Gmail)"}


@app.post("/learn-style")
def learn_style(payload: dict = Body(...)):
    situation = payload.get("situation", "mail envoyé")
    text = payload.get("text", "")
    if not text:
        return {"error": "Texte manquant"}
    save_style_example(situation=situation, example_text=text, tags=payload.get("tags", ""), quality_score=2.0)
    return {"status": "ok"}


# ─────────────────────────────────────────────
# AUTH MICROSOFT
# ─────────────────────────────────────────────

@app.get("/login")
def login(request: Request, next: str = "/chat"):
    msal_app = build_msal_app()
    auth_url = msal_app.get_authorization_request_url(scopes=GRAPH_SCOPES, redirect_uri=REDIRECT_URI, state=next)
    return RedirectResponse(auth_url)


@app.get("/auth/callback")
def auth_callback(request: Request, code: str | None = None, state: str | None = None):
    if not code:
        return HTMLResponse("Code manquant", status_code=400)
    msal_app = build_msal_app()
    result = msal_app.acquire_token_by_authorization_code(code, scopes=GRAPH_SCOPES, redirect_uri=REDIRECT_URI)
    if "access_token" not in result:
        return HTMLResponse(str(result), status_code=400)
    request.session["access_token"] = result["access_token"]
    conn = get_pg_conn()
    c = conn.cursor()
    c.execute("""
        INSERT INTO oauth_tokens (provider, access_token, refresh_token, expires_at)
        VALUES (%s, %s, %s, NOW() + INTERVAL '1 hour')
        ON CONFLICT (provider) DO UPDATE SET
            access_token = EXCLUDED.access_token,
            refresh_token = EXCLUDED.refresh_token,
            expires_at = EXCLUDED.expires_at,
            updated_at = NOW()
    """, ("microsoft", result["access_token"], result.get("refresh_token", "")))
    conn.commit()
    conn.close()
    return RedirectResponse(state or "/chat")


# ─────────────────────────────────────────────
# TRIAGE
# ─────────────────────────────────────────────

@app.get("/triage-queue")
def triage_queue():
    from app.token_manager import get_valid_microsoft_token
    token = get_valid_microsoft_token()
    if not token:
        return {"mails": [], "count": 0, "error": "Token Microsoft manquant"}
    try:
        data = graph_get(token, "/me/mailFolders/inbox/messages", params={
            "$top": 50, "$select": "id,subject,from,receivedDateTime,bodyPreview,isRead",
            "$orderby": "receivedDateTime DESC",
        })
        mails = [{
            "message_id": msg["id"],
            "from_email": msg.get("from", {}).get("emailAddress", {}).get("address", ""),
            "subject": msg.get("subject", "(Sans objet)"),
            "raw_body_preview": msg.get("bodyPreview", ""),
            "received_at": msg.get("receivedDateTime", ""),
            "is_read": msg.get("isRead", False),
        } for msg in data.get("value", [])]
        return {"mails": mails, "count": len(mails)}
    except Exception as e:
        return {"mails": [], "count": 0, "error": str(e)}


# ─────────────────────────────────────────────
# INGESTION MAILS
# ─────────────────────────────────────────────

@app.get("/memory")
def memory():
    conn = get_pg_conn()
    c = conn.cursor()
    c.execute("SELECT message_id, received_at, from_email, subject, display_title, category, priority, analysis_status FROM mail_memory ORDER BY id DESC LIMIT 20")
    columns = [desc[0] for desc in c.description]
    rows = [dict(zip(columns, row)) for row in c.fetchall()]
    conn.close()
    return rows


@app.get("/rebuild-memory")
def rebuild_memory_mails():
    conn = get_pg_conn()
    c = conn.cursor()
    c.execute("DELETE FROM mail_memory")
    conn.commit()
    conn.close()
    return {"status": "mail_memory_cleared"}


@app.get("/ingest-mails-fast")
def ingest_mails_fast(request: Request):
    token = request.session.get("access_token")
    if not token:
        return RedirectResponse("/login?next=/ingest-mails-fast")
    try:
        data = graph_get(token, "/me/mailFolders/inbox/messages", params={
            "$top": 5, "$select": "id,subject,from,receivedDateTime,bodyPreview",
            "$orderby": "receivedDateTime DESC",
        })
    except requests.HTTPError:
        request.session.pop("access_token", None)
        return RedirectResponse("/login?next=/ingest-mails-fast")
    messages = data.get("value", [])
    inserted = 0
    for msg in messages:
        message_id = msg["id"]
        if mail_exists(message_id):
            continue
        item = analyze_single_mail(msg)
        insert_mail({
            "message_id": message_id, "received_at": msg.get("receivedDateTime"),
            "from_email": msg.get("from", {}).get("emailAddress", {}).get("address"),
            "subject": msg.get("subject"), "display_title": item.get("display_title"),
            "category": item.get("category"), "priority": item.get("priority"),
            "reason": item.get("reason"), "suggested_action": item.get("suggested_action"),
            "short_summary": item.get("short_summary"), "group_hints": item.get("group_hints", []),
            "confidence": item.get("confidence", 0.0), "needs_review": item.get("needs_review", False),
            "raw_body_preview": msg.get("bodyPreview"), "analysis_status": "fallback",
            "needs_reply": item.get("needs_reply"), "reply_urgency": item.get("reply_urgency"),
            "reply_reason": item.get("reply_reason"),
            "suggested_reply_subject": item.get("suggested_reply_subject"),
            "suggested_reply": item.get("suggested_reply"), "mailbox_source": "outlook",
        })
        inserted += 1
        break
    return {"inserted": inserted}


@app.get("/ingest-mails")
def ingest_mails(request: Request):
    token = request.session.get("access_token")
    if not token:
        return RedirectResponse("/login?next=/ingest-mails")
    try:
        data = graph_get(token, "/me/mailFolders/inbox/messages", params={
            "$top": 1, "$select": "id,subject,from,receivedDateTime,bodyPreview",
            "$orderby": "receivedDateTime DESC",
        })
    except requests.HTTPError:
        request.session.pop("access_token", None)
        return RedirectResponse("/login?next=/ingest-mails")
    messages = data.get("value", [])
    inserted = 0
    instructions = get_global_instructions()
    for msg in messages:
        message_id = msg["id"]
        if mail_exists(message_id):
            continue
        try:
            item = analyze_single_mail_with_ai(msg, instructions)
            analysis_status = "done_ai"
        except Exception:
            item = analyze_single_mail(msg)
            analysis_status = "fallback"
        insert_mail({
            "message_id": message_id, "received_at": msg.get("receivedDateTime"),
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
        inserted += 1
    return {"inserted": inserted}


@app.get("/learn-sent-mails")
def learn_sent_mails(request: Request, top: int = 50):
    token = request.session.get("access_token")
    if not token:
        return RedirectResponse("/login?next=/learn-sent-mails")
    try:
        data = graph_get(token, "/me/mailFolders/SentItems/messages", params={
            "$top": top, "$select": "id,subject,from,receivedDateTime,bodyPreview,toRecipients",
            "$orderby": "receivedDateTime DESC",
        })
    except requests.HTTPError:
        request.session.pop("access_token", None)
        return RedirectResponse("/login?next=/learn-sent-mails")
    messages = data.get("value", [])
    inserted = 0
    conn = get_pg_conn()
    c = conn.cursor()
    for msg in messages:
        message_id = msg["id"]
        c.execute("SELECT 1 FROM sent_mail_memory WHERE message_id = %s", (message_id,))
        if c.fetchone():
            continue
        to_recipients = msg.get("toRecipients", [])
        to_email = to_recipients[0].get("emailAddress", {}).get("address", "") if to_recipients else ""
        try:
            c.execute("""
                INSERT INTO sent_mail_memory (message_id, sent_at, to_email, subject, body_preview)
                VALUES (%s, %s, %s, %s, %s) ON CONFLICT (message_id) DO NOTHING
            """, (message_id, msg.get("receivedDateTime"), to_email, msg.get("subject"), msg.get("bodyPreview")))
            inserted += 1
        except Exception:
            continue
    conn.commit()
    conn.close()
    return {"inserted": inserted, "total_fetched": len(messages)}


@app.get("/learn-inbox-mails")
def learn_inbox_mails(request: Request, top: int = 50, skip: int = 0):
    token = request.session.get("access_token")
    if not token:
        return RedirectResponse("/login?next=/learn-inbox-mails")
    try:
        data = graph_get(token, "/me/mailFolders/inbox/messages", params={
            "$top": top, "$skip": skip,
            "$select": "id,subject,from,receivedDateTime,bodyPreview,toRecipients",
            "$orderby": "receivedDateTime DESC",
        })
    except requests.HTTPError:
        request.session.pop("access_token", None)
        return RedirectResponse("/login?next=/learn-inbox-mails")
    messages = data.get("value", [])
    inserted = skipped_noise = 0
    conn = get_pg_conn()
    c = conn.cursor()
    skip_keywords = ["noreply", "no-reply", "donotreply", "newsletter", "unsubscribe",
                     "se désabonner", "notification", "mailer-daemon", "marketing",
                     "promo", "offre spéciale", "linkedin", "twitter", "facebook",
                     "instagram", "jobteaser", "indeed", "welcometothejungle",
                     "calendly", "zoom", "teams", "webinar", "webinaire",
                     "satisfaction", "avis client", "enquête", "survey"]
    for msg in messages:
        message_id = msg["id"]
        c.execute("SELECT 1 FROM mail_memory WHERE message_id = %s", (message_id,))
        if c.fetchone():
            continue
        from_email = msg.get("from", {}).get("emailAddress", {}).get("address", "").lower()
        subject = (msg.get("subject") or "").lower()
        body = (msg.get("bodyPreview") or "").lower()
        if any(kw in f"{from_email} {subject} {body}" for kw in skip_keywords):
            skipped_noise += 1
            continue
        try:
            c.execute("""
                INSERT INTO mail_memory (message_id, received_at, from_email, subject, raw_body_preview, analysis_status, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s) ON CONFLICT (message_id) DO NOTHING
            """, (message_id, msg.get("receivedDateTime"), msg.get("from", {}).get("emailAddress", {}).get("address", ""),
                   msg.get("subject"), msg.get("bodyPreview"), "inbox_raw", datetime.utcnow().isoformat()))
            inserted += 1
        except Exception:
            continue
    conn.commit()
    conn.close()
    return {"inserted": inserted, "skipped_noise": skipped_noise, "total_fetched": len(messages)}


@app.get("/build-style-profile")
def build_style_profile(request: Request):
    conn = get_pg_conn()
    c = conn.cursor()
    c.execute("SELECT subject, to_email, body_preview FROM sent_mail_memory ORDER BY sent_at DESC LIMIT 100")
    columns = [desc[0] for desc in c.description]
    rows = [dict(zip(columns, row)) for row in c.fetchall()]
    conn.close()
    if not rows:
        return {"error": "Aucun mail envoyé en mémoire"}
    mails_text = "\n\n".join([f"Sujet : {r['subject']}\nDestinataire : {r['to_email']}\nContenu : {r['body_preview']}" for r in rows])
    response = client.messages.create(
        model=ANTHROPIC_MODEL_SMART, max_tokens=2048,
        messages=[{"role": "user", "content": f"Analyse ces {len(rows)} emails envoyés par Guillaume Perrin.\n\n{mails_text}\n\nProduis un profil détaillé de son style : formules, longueur, ton, habitudes, interlocuteurs."}]
    )
    profile_text = response.content[0].text
    conn = get_pg_conn()
    c = conn.cursor()
    c.execute("DELETE FROM aria_profile WHERE profile_type = 'style'")
    c.execute("INSERT INTO aria_profile (profile_type, content) VALUES (%s, %s)", ('style', profile_text))
    conn.commit()
    conn.close()
    return {"status": "ok", "profile": profile_text}


@app.post("/instruction")
def add_instruction(instruction: str = Form(...)):
    add_global_instruction(instruction)
    return RedirectResponse("/chat", status_code=303)


# ─────────────────────────────────────────────
# AUTH GMAIL
# ─────────────────────────────────────────────

@app.get("/login/gmail")
def login_gmail():
    from app.connectors.gmail_connector import get_gmail_auth_url
    return RedirectResponse(get_gmail_auth_url())


@app.get("/auth/gmail/callback")
def auth_gmail_callback(request: Request, code: str | None = None):
    if not code:
        return HTMLResponse("Code manquant", status_code=400)
    from app.connectors.gmail_connector import exchange_code_for_tokens
    tokens = exchange_code_for_tokens(code)
    conn = get_pg_conn()
    c = conn.cursor()
    c.execute("DELETE FROM gmail_tokens WHERE email = %s", ("per1.guillaume@gmail.com",))
    c.execute("INSERT INTO gmail_tokens (email, access_token, refresh_token) VALUES (%s, %s, %s)",
              ("per1.guillaume@gmail.com", tokens.get("access_token"), tokens.get("refresh_token")))
    conn.commit()
    conn.close()
    return {"status": "ok", "message": "Gmail connecté !"}


@app.get("/ingest-gmail")
def ingest_gmail(request: Request):
    from app.connectors.gmail_connector import gmail_get_messages, gmail_get_message, refresh_gmail_token
    conn = get_pg_conn()
    c = conn.cursor()
    c.execute("SELECT access_token, refresh_token FROM gmail_tokens WHERE email = %s", ("per1.guillaume@gmail.com",))
    row = c.fetchone()
    conn.close()
    if not row:
        return {"error": "Gmail non connecté"}
    access_token, refresh_token = row[0], row[1]
    try:
        messages = gmail_get_messages(access_token, max_results=10)
    except Exception:
        access_token = refresh_gmail_token(refresh_token)
        messages = gmail_get_messages(access_token, max_results=10)
    inserted = 0
    skip_keywords = ["noreply", "no-reply", "donotreply", "newsletter", "unsubscribe", "se désabonner",
                     "notification", "mailer-daemon", "marketing", "promo", "offre spéciale",
                     "linkedin", "twitter", "facebook", "instagram", "jobteaser", "indeed", "welcometothejungle"]
    conn = get_pg_conn()
    c = conn.cursor()
    for msg in messages:
        message_id = msg["id"]
        c.execute("SELECT 1 FROM mail_memory WHERE message_id = %s", (message_id,))
        if c.fetchone():
            continue
        try:
            detail = gmail_get_message(access_token, message_id)
            headers = {h["name"]: h["value"] for h in detail.get("payload", {}).get("headers", [])}
            subject = headers.get("Subject", "(Sans objet)")
            from_email = headers.get("From", "")
            date = headers.get("Date", "")
            snippet = detail.get("snippet", "")
            if any(kw in f"{from_email} {subject} {snippet}".lower() for kw in skip_keywords):
                continue
            c.execute("""
                INSERT INTO mail_memory (message_id, received_at, from_email, subject, raw_body_preview, analysis_status, mailbox_source, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT (message_id) DO NOTHING
            """, (message_id, date, from_email, subject, snippet, "gmail_raw", "gmail_perso", datetime.utcnow().isoformat()))
            inserted += 1
        except Exception:
            conn.rollback()
            continue
    conn.commit()
    conn.close()
    return {"inserted": inserted, "total_fetched": len(messages)}


@app.get("/learn-gmail-all")
def learn_gmail_all(request: Request, max_results: int = 100, page_token: str = None):
    from app.connectors.gmail_connector import gmail_get_message, refresh_gmail_token
    from app.config import ANTHROPIC_MODEL_FAST
    conn = get_pg_conn()
    c = conn.cursor()
    c.execute("SELECT access_token, refresh_token FROM gmail_tokens WHERE email = %s", ("per1.guillaume@gmail.com",))
    row = c.fetchone()
    conn.close()
    if not row:
        return {"error": "Gmail non connecté"}
    access_token, refresh_token = row[0], row[1]
    try:
        response = requests.get(
            "https://gmail.googleapis.com/gmail/v1/users/me/messages",
            headers={"Authorization": f"Bearer {access_token}"},
            params={"maxResults": max_results, "pageToken": page_token}, timeout=30,
        )
        if response.status_code == 401:
            access_token = refresh_gmail_token(refresh_token)
            response = requests.get(
                "https://gmail.googleapis.com/gmail/v1/users/me/messages",
                headers={"Authorization": f"Bearer {access_token}"},
                params={"maxResults": max_results, "pageToken": page_token}, timeout=30,
            )
        data = response.json()
    except Exception as e:
        return {"error": str(e)}
    messages = data.get("messages", [])
    next_page_token = data.get("nextPageToken")
    inserted = skipped_noise = skipped_ai = 0
    skip_keywords = ["noreply", "no-reply", "donotreply", "newsletter", "unsubscribe", "se désabonner",
                     "notification", "mailer-daemon", "marketing", "promo", "offre spéciale",
                     "linkedin", "twitter", "facebook", "instagram", "jobteaser", "indeed", "welcometothejungle",
                     "calendly", "zoom", "teams", "webinar", "webinaire", "satisfaction", "avis client", "enquête", "survey"]
    conn = get_pg_conn()
    c = conn.cursor()
    for msg in messages:
        message_id = msg["id"]
        c.execute("SELECT 1 FROM mail_memory WHERE message_id = %s", (message_id,))
        if c.fetchone():
            continue
        try:
            detail = gmail_get_message(access_token, message_id)
            headers = {h["name"]: h["value"] for h in detail.get("payload", {}).get("headers", [])}
            subject = headers.get("Subject", "(Sans objet)")
            from_email = headers.get("From", "")
            date = headers.get("Date", "")
            snippet = detail.get("snippet", "")
            full_text = f"{from_email} {subject} {snippet}".lower()
            if any(kw in full_text for kw in skip_keywords):
                skipped_noise += 1
                continue
            try:
                decision = client.messages.create(
                    model=ANTHROPIC_MODEL_FAST, max_tokens=5,
                    messages=[{"role": "user", "content": f"Mail de : {from_email}\nSujet : {subject}\nContenu : {snippet[:200]}\n\nPertinent pour un dirigeant dans le solaire ? OUI ou NON."}]
                )
                if "NON" in decision.content[0].text.upper():
                    skipped_ai += 1
                    continue
            except Exception:
                pass
            c.execute("""
                INSERT INTO mail_memory (message_id, received_at, from_email, subject, raw_body_preview, analysis_status, mailbox_source, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT (message_id) DO NOTHING
            """, (message_id, date, from_email, subject, snippet, "gmail_raw", "gmail_perso", datetime.utcnow().isoformat()))
            inserted += 1
        except Exception:
            conn.rollback()
            continue
    conn.commit()
    conn.close()
    return {"inserted": inserted, "skipped_noise": skipped_noise, "skipped_ai": skipped_ai,
            "total_fetched": len(messages), "next_page_token": next_page_token}


@app.get("/learn-gmail-sent")
def learn_gmail_sent(request: Request, max_results: int = 200, page_token: str = None):
    from app.connectors.gmail_connector import gmail_get_message, refresh_gmail_token
    conn = get_pg_conn()
    c = conn.cursor()
    c.execute("SELECT access_token, refresh_token FROM gmail_tokens WHERE email = %s", ("per1.guillaume@gmail.com",))
    row = c.fetchone()
    conn.close()
    if not row:
        return {"error": "Gmail non connecté"}
    access_token, refresh_token = row[0], row[1]
    try:
        response = requests.get(
            "https://gmail.googleapis.com/gmail/v1/users/me/messages",
            headers={"Authorization": f"Bearer {access_token}"},
            params={"maxResults": max_results, "labelIds": "SENT", "pageToken": page_token}, timeout=30,
        )
        if response.status_code == 401:
            access_token = refresh_gmail_token(refresh_token)
            response = requests.get(
                "https://gmail.googleapis.com/gmail/v1/users/me/messages",
                headers={"Authorization": f"Bearer {access_token}"},
                params={"maxResults": max_results, "labelIds": "SENT", "pageToken": page_token}, timeout=30,
            )
        data = response.json()
    except Exception as e:
        return {"error": str(e)}
    messages = data.get("messages", [])
    next_page_token = data.get("nextPageToken")
    inserted = 0
    conn = get_pg_conn()
    c = conn.cursor()
    for msg in messages:
        message_id = msg["id"]
        c.execute("SELECT 1 FROM sent_mail_memory WHERE message_id = %s", (message_id,))
        if c.fetchone():
            continue
        try:
            detail = gmail_get_message(access_token, message_id)
            headers = {h["name"]: h["value"] for h in detail.get("payload", {}).get("headers", [])}
            c.execute("""
                INSERT INTO sent_mail_memory (message_id, sent_at, to_email, subject, body_preview)
                VALUES (%s, %s, %s, %s, %s) ON CONFLICT (message_id) DO NOTHING
            """, (message_id, headers.get("Date", ""), headers.get("To", ""),
                   headers.get("Subject", "(Sans objet)"), detail.get("snippet", "")))
            inserted += 1
        except Exception:
            conn.rollback()
            continue
    conn.commit()
    conn.close()
    return {"inserted": inserted, "total_fetched": len(messages), "next_page_token": next_page_token}


@app.get("/learn-archive-mails")
def learn_archive_mails(request: Request, top: int = 100, skip: int = 0):
    token = request.session.get("access_token")
    if not token:
        return RedirectResponse("/login?next=/learn-archive-mails")
    folder_id = "AQMkAGEwZmJhNTllLWQ3MjUtNDg4ADQtYjdhMi1jMGEyZjRiNmFkNWEALgAAA-6yBmE1L7hGi--BXSl5S2sBAIyf8uOKE0VAkKv1dN8K6xgAAAIBRQAAAA=="
    try:
        data = graph_get(token, f"/me/mailFolders/{folder_id}/messages", params={
            "$top": top, "$skip": skip,
            "$select": "id,subject,from,receivedDateTime,bodyPreview",
            "$orderby": "receivedDateTime DESC",
        })
    except requests.HTTPError:
        request.session.pop("access_token", None)
        return RedirectResponse("/login?next=/learn-archive-mails")
    messages = data.get("value", [])
    inserted = skipped_noise = 0
    conn = get_pg_conn()
    c = conn.cursor()
    skip_keywords = ["noreply", "no-reply", "newsletter", "unsubscribe", "notification", "marketing",
                     "promo", "linkedin", "twitter", "facebook", "instagram", "calendly", "webinar"]
    for msg in messages:
        message_id = msg["id"]
        c.execute("SELECT 1 FROM mail_memory WHERE message_id = %s", (message_id,))
        if c.fetchone():
            continue
        from_email = msg.get("from", {}).get("emailAddress", {}).get("address", "").lower()
        subject = (msg.get("subject") or "").lower()
        body = (msg.get("bodyPreview") or "").lower()
        if any(kw in f"{from_email} {subject} {body}" for kw in skip_keywords):
            skipped_noise += 1
            continue
        try:
            c.execute("""
                INSERT INTO mail_memory (message_id, received_at, from_email, subject, raw_body_preview, analysis_status, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s) ON CONFLICT (message_id) DO NOTHING
            """, (message_id, msg.get("receivedDateTime"), msg.get("from", {}).get("emailAddress", {}).get("address", ""),
                   msg.get("subject"), msg.get("bodyPreview"), "archive_raw", datetime.utcnow().isoformat()))
            inserted += 1
        except Exception:
            continue
    conn.commit()
    conn.close()
    return {"inserted": inserted, "skipped_noise": skipped_noise, "total_fetched": len(messages)}


@app.get("/list-mail-folders")
def list_mail_folders(request: Request):
    token = request.session.get("access_token")
    if not token:
        return RedirectResponse("/login?next=/list-mail-folders")
    try:
        data = graph_get(token, "/me/mailFolders")
    except requests.HTTPError:
        request.session.pop("access_token", None)
        return RedirectResponse("/login?next=/list-mail-folders")
    return data.get("value", [])


@app.get("/assistant-dashboard")
def assistant_dashboard(days: int = 2):
    return get_dashboard(days)


@app.get("/test-elevenlabs")
def test_elevenlabs():
    api_key = os.environ.get("ELEVENLABS_API_KEY", "")
    voice_id = os.environ.get("ELEVENLABS_VOICE_ID", "")
    resp = requests.post(
        f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
        headers={"xi-api-key": api_key, "Content-Type": "application/json"},
        json={"text": "Bonjour Guillaume.", "model_id": "eleven_flash_v2_5", "voice_settings": {"stability": 0.5, "similarity_boost": 0.8}},
        timeout=30,
    )
    return {"status_code": resp.status_code, "api_key_length": len(api_key), "voice_id": voice_id}


@app.get("/test-odoo")
def test_odoo():
    from app.connectors.odoo_connector import perform_odoo_action
    return perform_odoo_action(action="get_partner_by_email", params={"email": "guillaume@couffrant-solar.fr"})
