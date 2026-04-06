import os
import requests
import json
from datetime import datetime, timedelta

from fastapi import FastAPI, Request, Form
from fastapi.responses import RedirectResponse, HTMLResponse
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
from fastapi import Body


app = FastAPI(title="Couffrant Solar Assistant")
app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET)


class AriaQuery(BaseModel):
    query: str

@app.post("/speak")
def speak_text(payload: dict = Body(...)):
    from app.config import ELEVENLABS_API_KEY, ELEVENLABS_VOICE_ID
    from fastapi.responses import StreamingResponse
    import io
    import re

    text = payload.get("text", "")

    clean = re.sub(r'#{1,6}\s+', '', text)
    clean = re.sub(r'\*\*(.*?)\*\*', r'\1', clean)
    clean = re.sub(r'\*(.*?)\*', r'\1', clean)
    clean = re.sub(r'`(.*?)`', r'\1', clean)
    clean = re.sub(r'---+', '', clean)
    clean = re.sub(r'\|.*?\|', '', clean)
    clean = re.sub(r'^\s*[-•]\s', '', clean, flags=re.MULTILINE)
    clean = clean.strip()

    response = requests.post(
        f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE_ID}",
        headers={
            "xi-api-key": ELEVENLABS_API_KEY,
            "Content-Type": "application/json",
        },
        json={
            "text": clean[:2500],
            "model_id": "eleven_multilingual_v2",
            "voice_settings": {
                "stability": 0.5,
                "similarity_boost": 0.8,
                "style": 0.2,
                "use_speaker_boost": True
            }
        },
        timeout=30,
    )

    if response.status_code != 200:
        return {"error": "ElevenLabs error"}

    return StreamingResponse(
        io.BytesIO(response.content),
        media_type="audio/mpeg",
    )

function stopSpeech() {
    if (currentAudio) {
        currentAudio.pause();
        currentAudio.currentTime = 0;
    }
    stopBtn.classList.remove('visible');
}

@app.on_event("startup")
def startup_event():
    init_postgres()
    init_db()
    init_mail_db()


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/chat", response_class=HTMLResponse)
def chat(request: Request):
    with open("app/templates/aria_chat.html", "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())


@app.get("/init-db")
def init_db_now():
    init_postgres()
    return {"status": "tables créées"}


@app.post("/aria")
def aria(payload: AriaQuery):
    instructions = get_global_instructions()

    conn = get_pg_conn()
    c = conn.cursor()
    c.execute("""
        SELECT display_title, category, priority, short_summary, suggested_reply
        FROM mail_memory
        ORDER BY id DESC
        LIMIT 10
    """)
    columns = [desc[0] for desc in c.description]
    mails = [dict(zip(columns, row)) for row in c.fetchall()]

    c.execute("""
        SELECT user_input, aria_response
        FROM aria_memory
        ORDER BY id DESC
        LIMIT 5
    """)
    columns = [desc[0] for desc in c.description]
    memory = [dict(zip(columns, row)) for row in c.fetchall()]
    conn.close()

    context = {
        "recent_mails": mails,
        "instructions": instructions,
        "memory": memory,
    }

    prompt = f"""
Tu es Aria, assistante stratégique et opérationnelle de Couffrant Solar.
Tu aides Guillaume à piloter son activité avec clarté, efficacité et bon sens.

Règles absolues :
- Tu proposes toujours, Guillaume décide toujours
- Tu n'exécutes aucune action sans validation explicite de Guillaume
- Tu écris comme une assistante expérimentée, pas comme une IA
- Tu es directe, synthétique, utile, sans blabla

Contexte disponible :
{json.dumps(context, ensure_ascii=False)}

Question de Guillaume :
{payload.query}

Réponds en 3 parties :

1. Priorités
- ce qui doit être traité en premier
- ordre clair et logique

2. Risques ou points de vigilance
- retards, oublis, conflits, impacts possibles

3. Recommandations concrètes
- actions immédiates
- décisions à prendre
- prochaines étapes

Si rien n'est critique, dis-le clairement.
Si tu repères un problème ou une opportunité importante, signale-le même si la question ne le demande pas.
""".strip()

    response = client.messages.create(
        model=ANTHROPIC_MODEL_SMART,
        max_tokens=2048,
        messages=[{"role": "user", "content": prompt}]
    )

    aria_response = response.content[0].text

    conn = get_pg_conn()
    c = conn.cursor()
    c.execute("""
        INSERT INTO aria_memory (user_input, aria_response)
        VALUES (%s, %s)
    """, (payload.query, aria_response))
    conn.commit()
    conn.close()

    return {"answer": aria_response}


@app.get("/login")
def login(request: Request, next: str = "/me"):
    msal_app = build_msal_app()
    auth_url = msal_app.get_authorization_request_url(
        scopes=GRAPH_SCOPES,
        redirect_uri=REDIRECT_URI,
        state=next,
    )
    return RedirectResponse(auth_url)


@app.get("/auth/callback")
def auth_callback(request: Request, code: str | None = None, state: str | None = None):
    if not code:
        return HTMLResponse("Code manquant", status_code=400)
    msal_app = build_msal_app()
    result = msal_app.acquire_token_by_authorization_code(
        code,
        scopes=GRAPH_SCOPES,
        redirect_uri=REDIRECT_URI,
    )
    if "access_token" not in result:
        return HTMLResponse(str(result), status_code=400)
    request.session["access_token"] = result["access_token"]
    conn = get_pg_conn()
    c = conn.cursor()
    c.execute("""
        INSERT INTO oauth_tokens (provider, access_token, refresh_token, expires_at)
        VALUES (%s, %s, %s, NOW() + INTERVAL '1 hour')
        ON CONFLICT DO NOTHING
    """, (
        "microsoft",
        result["access_token"],
        result.get("refresh_token", ""),
    ))
    conn.commit()
    conn.close()
    return RedirectResponse(state or "/me")


@app.get("/me")
def me(request: Request):
    token = request.session.get("access_token")
    if not token:
        return RedirectResponse("/login?next=/me")
    try:
        profile = graph_get(token, "/me")
    except requests.HTTPError:
        request.session.pop("access_token", None)
        return RedirectResponse("/login?next=/me")
    return profile


@app.get("/memory")
def memory():
    conn = get_pg_conn()
    c = conn.cursor()
    c.execute("""
        SELECT message_id, received_at, from_email, subject, display_title,
               category, priority, analysis_status, confidence
        FROM mail_memory
        ORDER BY id DESC
        LIMIT 20
    """)
    columns = [desc[0] for desc in c.description]
    rows = [dict(zip(columns, row)) for row in c.fetchall()]
    conn.close()
    return rows


@app.get("/rebuild-memory")
def rebuild_memory():
    conn = get_pg_conn()
    c = conn.cursor()
    c.execute("DELETE FROM mail_memory")
    conn.commit()
    conn.close()
    return {"status": "memory_cleared"}


@app.get("/assistant-dashboard")
def assistant_dashboard(days: int = 2):
    return get_dashboard(days)


@app.get("/reply-queue")
def reply_queue():
    conn = get_pg_conn()
    c = conn.cursor()
    c.execute("""
        SELECT id, received_at, from_email, subject, display_title,
               category, priority, reply_urgency, reply_reason,
               suggested_reply_subject, suggested_reply, reply_status
        FROM mail_memory
        WHERE needs_reply = 1
        ORDER BY id DESC
    """)
    columns = [desc[0] for desc in c.description]
    rows = [dict(zip(columns, row)) for row in c.fetchall()]
    conn.close()
    return rows


@app.get("/reply-learning")
def reply_learning():
    conn = get_pg_conn()
    c = conn.cursor()
    c.execute("""
        SELECT id, mail_subject, mail_from, category, ai_reply, final_reply, created_at
        FROM reply_learning_memory
        ORDER BY id DESC
        LIMIT 20
    """)
    columns = [desc[0] for desc in c.description]
    rows = [dict(zip(columns, row)) for row in c.fetchall()]
    conn.close()
    return rows


@app.get("/digest")
def digest(days: int = 2):
    conn = get_pg_conn()
    c = conn.cursor()
    start_date = (datetime.utcnow() - timedelta(days=days)).isoformat()
    c.execute("""
        SELECT received_at, from_email, display_title, category, priority,
               reason, suggested_action, short_summary
        FROM mail_memory
        WHERE received_at >= %s
        ORDER BY received_at DESC
    """, (start_date,))
    columns = [desc[0] for desc in c.description]
    rows = [dict(zip(columns, row)) for row in c.fetchall()]
    conn.close()
    return {"days": days, "count": len(rows), "items": rows}


@app.get("/digest-readable", response_class=HTMLResponse)
def digest_readable(days: int = 2):
    conn = get_pg_conn()
    c = conn.cursor()
    start_date = (datetime.utcnow() - timedelta(days=days)).isoformat()
    c.execute("""
        SELECT received_at, from_email, display_title, category, priority,
               reason, suggested_action, short_summary
        FROM mail_memory
        WHERE received_at >= %s
        ORDER BY received_at DESC
    """, (start_date,))
    columns = [desc[0] for desc in c.description]
    rows = [dict(zip(columns, row)) for row in c.fetchall()]
    conn.close()

    html = f"""<html><head><meta charset="utf-8"><title>Digest {days} jours</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 30px; background: #f7f7f7; color: #222; }}
        .card {{ background: white; border-radius: 10px; padding: 16px; margin-bottom: 14px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); }}
        .title {{ font-size: 18px; font-weight: bold; margin-bottom: 8px; }}
        .high {{ color: #c62828; }} .medium {{ color: #ef6c00; }} .low {{ color: #888; }}
        .line {{ margin: 4px 0; }} .label {{ font-weight: bold; }}
    </style></head><body>
    <h1>Digest sur {days} jours</h1>
    <div style="color:#666;margin-bottom:20px;">{len(rows)} mails analysés</div>"""
    for item in rows:
        cls = "high" if item["priority"] == "haute" else "medium" if item["priority"] == "moyenne" else "low"
        html += f"""<div class="card">
            <div class="title {cls}">{item['display_title']}</div>
            <div class="line"><span class="label">Date :</span> {item['received_at']}</div>
            <div class="line"><span class="label">Expéditeur :</span> {item['from_email']}</div>
            <div class="line"><span class="label">Catégorie :</span> {item['category']}</div>
            <div class="line"><span class="label">Raison :</span> {item['reason']}</div>
            <div class="line"><span class="label">Action :</span> {item['suggested_action']}</div>
            <div class="line"><span class="label">Résumé :</span> {item['short_summary']}</div>
        </div>"""
    html += "</body></html>"
    return html


@app.get("/ingest-mails-fast")
def ingest_mails_fast(request: Request):
    token = request.session.get("access_token")
    if not token:
        return RedirectResponse("/login?next=/ingest-mails-fast")
    try:
        data = graph_get(
            token,
            "/me/mailFolders/inbox/messages",
            params={
                "$top": 5,
                "$select": "id,subject,from,receivedDateTime,bodyPreview",
                "$orderby": "receivedDateTime DESC",
            },
        )
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
            "analysis_status": "fallback",
            "needs_reply": item.get("needs_reply"),
            "reply_urgency": item.get("reply_urgency"),
            "reply_reason": item.get("reply_reason"),
            "suggested_reply_subject": item.get("suggested_reply_subject"),
            "suggested_reply": item.get("suggested_reply"),
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
        data = graph_get(
            token,
            "/me/mailFolders/inbox/messages",
            params={
                "$top": 1,
                "$select": "id,subject,from,receivedDateTime,bodyPreview",
                "$orderby": "receivedDateTime DESC",
            },
        )
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
        })
        inserted += 1
    return {"inserted": inserted}


@app.get("/learn-sent-mails")
def learn_sent_mails(request: Request, top: int = 50):
    token = request.session.get("access_token")
    if not token:
        return RedirectResponse("/login?next=/learn-sent-mails")
    try:
        data = graph_get(
            token,
            "/me/mailFolders/SentItems/messages",
            params={
                "$top": top,
                "$select": "id,subject,from,receivedDateTime,bodyPreview,toRecipients",
                "$orderby": "receivedDateTime DESC",
            },
        )
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
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (message_id) DO NOTHING
            """, (
                message_id,
                msg.get("receivedDateTime"),
                to_email,
                msg.get("subject"),
                msg.get("bodyPreview"),
            ))
            inserted += 1
        except Exception:
            continue

    conn.commit()
    conn.close()
    return {
        "inserted": inserted,
        "total_fetched": len(messages),
        "message": f"{inserted} mails envoyés mémorisés"
    }

@app.get("/learn-inbox-mails")
def learn_inbox_mails(request: Request, top: int = 50, skip: int = 0):
    token = request.session.get("access_token")
    if not token:
        return RedirectResponse("/login?next=/learn-inbox-mails")

    try:
        data = graph_get(
            token,
            "/me/mailFolders/inbox/messages",
            params={
                "$top": top,
                "$skip": skip,
                "$select": "id,subject,from,receivedDateTime,bodyPreview,toRecipients",
                "$orderby": "receivedDateTime DESC",
            },
        )
    except requests.HTTPError:
        request.session.pop("access_token", None)
        return RedirectResponse("/login?next=/learn-inbox-mails")

    messages = data.get("value", [])
    inserted = 0
    skipped_noise = 0
    conn = get_pg_conn()
    c = conn.cursor()

    skip_keywords = [
        "noreply", "no-reply", "donotreply", "newsletter", "unsubscribe",
        "se désabonner", "notification", "mailer-daemon", "marketing",
        "promo", "offre spéciale", "linkedin", "twitter", "facebook",
        "instagram", "jobteaser", "indeed", "welcometothejungle",
        "calendly", "zoom", "teams", "webinar", "webinaire",
        "satisfaction", "avis client", "enquête", "survey",
    ]

    for msg in messages:
        message_id = msg["id"]
        c.execute("SELECT 1 FROM mail_memory WHERE message_id = %s", (message_id,))
        if c.fetchone():
            continue

        from_email = msg.get("from", {}).get("emailAddress", {}).get("address", "").lower()
        subject = (msg.get("subject") or "").lower()
        body = (msg.get("bodyPreview") or "").lower()
        full_text = f"{from_email} {subject} {body}"

        if any(kw in full_text for kw in skip_keywords):
            skipped_noise += 1
            continue

        try:
            c.execute("""
                INSERT INTO mail_memory
                (message_id, received_at, from_email, subject,
                 raw_body_preview, analysis_status, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (message_id) DO NOTHING
            """, (
                message_id,
                msg.get("receivedDateTime"),
                msg.get("from", {}).get("emailAddress", {}).get("address", ""),
                msg.get("subject"),
                msg.get("bodyPreview"),
                "inbox_raw",
                datetime.utcnow().isoformat(),
            ))
            inserted += 1
        except Exception:
            continue

    conn.commit()
    conn.close()

    return {
        "inserted": inserted,
        "skipped_noise": skipped_noise,
        "total_fetched": len(messages),
        "skip": skip,
        "message": f"{inserted} mails utiles stockés, {skipped_noise} bruits ignorés"
    }

@app.get("/build-style-profile")
def build_style_profile(request: Request):
    conn = get_pg_conn()
    c = conn.cursor()
    c.execute("""
        SELECT subject, to_email, body_preview
        FROM sent_mail_memory
        ORDER BY sent_at DESC
        LIMIT 100
    """)
    columns = [desc[0] for desc in c.description]
    rows = [dict(zip(columns, row)) for row in c.fetchall()]
    conn.close()

    if not rows:
        return {"error": "Aucun mail envoyé en mémoire"}

    mails_text = "\n\n".join([
        f"Sujet : {r['subject']}\nDestinataire : {r['to_email']}\nContenu : {r['body_preview']}"
        for r in rows
    ])

    response = client.messages.create(
        model=ANTHROPIC_MODEL_SMART,
        max_tokens=2048,
        messages=[{
            "role": "user",
            "content": f"""Analyse ces {len(rows)} emails envoyés par Guillaume Perrin de Couffrant Solar.

{mails_text}

Produis un profil détaillé de son style de communication :

1. Style d'écriture
- longueur typique des mails
- ton (formel, direct, chaleureux...)
- formules d'ouverture préférées
- formules de clôture préférées
- niveau de détail

2. Vocabulaire métier
- termes techniques récurrents
- expressions caractéristiques
- abréviations utilisées

3. Clients et interlocuteurs récurrents
- types d'interlocuteurs principaux
- sujets récurrents par type

4. Comportements de communication
- délais de réponse habituels si visibles
- sujets traités en priorité
- sujets délégués ou ignorés

5. Recommandations pour Aria
- comment écrire comme Guillaume
- ce qu'il faut éviter
- ce qui lui ressemble"""
        }]
    )

    profile_text = response.content[0].text

    conn = get_pg_conn()
    c = conn.cursor()
    c.execute("DELETE FROM aria_profile WHERE profile_type = 'style'")
    c.execute("""
        INSERT INTO aria_profile (profile_type, content)
        VALUES (%s, %s)
    """, ('style', profile_text))
    conn.commit()
    conn.close()

    return {"status": "ok", "profile": profile_text}


@app.get("/summary")
def summary(request: Request):
    token = request.session.get("access_token")
    if not token:
        return RedirectResponse("/login?next=/summary")
    try:
        data = graph_get(
            token,
            "/me/mailFolders/inbox/messages",
            params={
                "$top": 10,
                "$select": "subject,from,receivedDateTime,isRead,bodyPreview",
                "$orderby": "receivedDateTime DESC",
            },
        )
    except requests.HTTPError:
        request.session.pop("access_token", None)
        return RedirectResponse("/login?next=/summary")
    instructions = get_global_instructions()
    messages = data.get("value", [])
    return summarize_messages(messages, instructions=instructions)


@app.post("/instruction")
def add_instruction(instruction: str = Form(...)):
    add_global_instruction(instruction)
    return RedirectResponse("/summary-readable", status_code=303)


@app.get("/summary-readable", response_class=HTMLResponse)
def summary_readable(request: Request):
    token = request.session.get("access_token")
    if not token:
        return RedirectResponse("/login?next=/summary-readable")
    try:
        data = graph_get(
            token,
            "/me/mailFolders/inbox/messages",
            params={
                "$top": 10,
                "$select": "subject,from,receivedDateTime,isRead,bodyPreview",
                "$orderby": "receivedDateTime DESC",
            },
        )
    except requests.HTTPError:
        request.session.pop("access_token", None)
        return RedirectResponse("/login?next=/summary-readable")

    instructions = get_global_instructions()
    messages = data.get("value", [])
    result = summarize_messages(messages, instructions=instructions)

    urgents = [i for i in result["items"] if i["priority"] == "haute"]
    moyens = [i for i in result["items"] if i["priority"] == "moyenne"]
    faibles = [i for i in result["items"] if i["priority"] not in ["haute", "moyenne"]]

    def render_section(title: str, items: list[dict]) -> str:
        html_section = f"<h2>{title}</h2>"
        if not items:
            return html_section + '<div class="empty">Aucun mail dans cette catégorie.</div>'
        for item in items:
            cls = "title-high" if item["priority"] == "haute" else "title-medium" if item["priority"] == "moyenne" else "title-low"
            count_html = f"<div class='badge'>{item['mail_count']} mails liés</div>" if item.get("mail_count", 1) > 1 else ""
            html_section += f"""<div class="card">
                {count_html}
                <div class="title {cls}">{item['display_title']}</div>
                <div class="line"><span class="label">Expéditeur :</span> {item['from']}</div>
                <div class="line"><span class="label">Date :</span> {item['receivedDateTime']}</div>
                <div class="line"><span class="label">Raison :</span> {item['reason']}</div>
                <div class="line"><span class="label">Action :</span> {item['suggested_action']}</div>
                <div class="line"><span class="label">Résumé :</span> {item['short_summary']}</div>
            </div>"""
        return html_section

    instructions_html = "".join(f"<li>{i}</li>" for i in instructions[:10])

    html = f"""<!DOCTYPE html>
<html lang="fr"><head><meta charset="utf-8"><title>Résumé des mails</title>
<style>
    body {{ font-family: Arial, sans-serif; margin: 30px; background: #f7f7f7; color: #222; }}
    .card {{ background: white; border-radius: 10px; padding: 18px; margin-bottom: 16px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); position: relative; }}
    .title {{ font-size: 18px; font-weight: bold; margin-bottom: 10px; }}
    .title-high {{ color: #c62828; }} .title-medium {{ color: #ef6c00; }} .title-low {{ color: #c9a400; }}
    .line {{ margin: 4px 0; }} .label {{ font-weight: bold; }}
    .empty {{ color: #777; font-style: italic; margin-bottom: 12px; }}
    .panel {{ background: white; border-radius: 10px; padding: 18px; margin-bottom: 20px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); }}
    textarea {{ width: 100%; min-height: 90px; padding: 10px; box-sizing: border-box; margin-top: 8px; }}
    button {{ margin-top: 10px; padding: 10px 14px; border: none; border-radius: 8px; cursor: pointer; }}
    .badge {{ position: absolute; right: 14px; top: 14px; background: #eef3ff; color: #335; font-size: 12px; padding: 5px 8px; border-radius: 999px; }}
</style></head><body>
<h1>Résumé des mails</h1>
<div style="color:#666;margin-bottom:25px;">{result['count']} cartes analysées</div>
<div class="panel">
    <h2>Apprendre à l'assistant</h2>
    <form method="post" action="/instruction">
        <label for="instruction">Donne une consigne globale en langage naturel :</label>
        <textarea id="instruction" name="instruction"></textarea>
        <button type="submit">Enregistrer la consigne</button>
    </form>
</div>
<div class="panel">
    <h2>Consignes mémorisées</h2>
    <ul>{instructions_html or '<li>Aucune consigne enregistrée pour le moment.</li>'}</ul>
</div>"""
    html += render_section("🔴 Urgents", urgents)
    html += render_section("🟠 À traiter", moyens)
    html += render_section("🟡 Secondaires", faibles)
    html += "</body></html>"
    return html


@app.get("/reply-learning-readable", response_class=HTMLResponse)
def reply_learning_readable():
    conn = get_pg_conn()
    c = conn.cursor()
    c.execute("""
        SELECT id, mail_subject, mail_from, category, ai_reply, final_reply, created_at
        FROM reply_learning_memory
        ORDER BY id DESC
        LIMIT 50
    """)
    columns = [desc[0] for desc in c.description]
    rows = [dict(zip(columns, row)) for row in c.fetchall()]
    conn.close()

    html = """<html><head><meta charset="utf-8"><title>Mémoire des corrections</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 30px; background: #f7f7f7; color: #222; }
        .card { background: white; border-radius: 10px; padding: 16px; margin-bottom: 14px; box-shadow: 0 2px 8px rgba(0,0,0,0.08); }
        .title { font-size: 18px; font-weight: bold; margin-bottom: 8px; }
        .line { margin: 4px 0; } .label { font-weight: bold; }
        .box { white-space: pre-wrap; background: #f0f0f0; padding: 10px; border-radius: 6px; margin-top: 8px; }
        .btn { display:inline-block; margin-bottom:20px; background:#1f6feb; color:white; text-decoration:none; padding:10px 14px; border-radius:8px; font-weight:bold; }
    </style></head><body>
    <a class="btn" href="/assistant-dashboard-readable">⬅ Retour dashboard</a>
    <h1>Mémoire des corrections</h1>"""
    for row in rows:
        html += f"""<div class="card">
            <div class="title">{row['mail_subject']}</div>
            <div class="line"><span class="label">Expéditeur :</span> {row['mail_from']}</div>
            <div class="line"><span class="label">Catégorie :</span> {row['category']}</div>
            <div class="line"><span class="label">Date :</span> {row['created_at']}</div>
            <div class="line" style="margin-top:10px;"><span class="label">Réponse IA initiale :</span></div>
            <div class="box">{row['ai_reply'] or ''}</div>
            <div class="line" style="margin-top:10px;"><span class="label">Réponse finale corrigée :</span></div>
            <div class="box">{row['final_reply'] or ''}</div>
        </div>"""
    html += "</body></html>"
    return HTMLResponse(content=html)


@app.post("/save-reply-correction/{mail_id}")
def save_reply_correction(mail_id: int, final_reply: str = Form(...)):
    conn = get_pg_conn()
    c = conn.cursor()
    c.execute("""
        SELECT subject, from_email, raw_body_preview, category, suggested_reply
        FROM mail_memory WHERE id = %s
    """, (mail_id,))
    row = c.fetchone()
    if not row:
        conn.close()
        return {"error": "mail introuvable"}
    c.execute("""
        INSERT INTO reply_learning_memory
        (mail_subject, mail_from, mail_body_preview, category, ai_reply, final_reply)
        VALUES (%s, %s, %s, %s, %s, %s)
    """, (row[0], row[1], row[2], row[3], row[4], final_reply))
    c.execute("UPDATE mail_memory SET suggested_reply = %s WHERE id = %s", (final_reply, mail_id))
    conn.commit()
    conn.close()
    return RedirectResponse("/assistant-dashboard-readable", status_code=303)


@app.get("/validate-reply/{mail_id}")
def validate_reply(mail_id: int):
    conn = get_pg_conn()
    c = conn.cursor()
    c.execute("UPDATE mail_memory SET reply_status='validated' WHERE id=%s", (mail_id,))
    conn.commit()
    conn.close()
    return RedirectResponse("/assistant-dashboard-readable", status_code=303)


@app.get("/send-reply/{mail_id}")
def send_reply(mail_id: int, request: Request):
    token = request.session.get("access_token")
    if not token:
        return RedirectResponse(f"/login?next=/send-reply/{mail_id}")

    conn = get_pg_conn()
    c = conn.cursor()
    c.execute("""
        SELECT from_email, suggested_reply, suggested_reply_subject, reply_status
        FROM mail_memory WHERE id = %s
    """, (mail_id,))
    row = c.fetchone()

    if not row:
        conn.close()
        return {"error": "Mail non trouvé"}
    if row[3] != "validated":
        conn.close()
        return {"error": "Réponse non validée"}

    html_body = f"""
<div style="font-family:Arial, sans-serif; font-size:14px; color:#222;">
    <div style="white-space:pre-line;">{row[1]}</div>
    <br><br>
    <div>Solairement,</div>
    <div style="font-weight:bold; margin-top:8px;">Guillaume Perrin</div>
    <div>06 49 43 09 17</div>
    <div><a href="https://www.couffrant-solar.fr" style="color:#1f6feb;">www.couffrant-solar.fr</a></div>
    <div style="margin-top:12px;">
        <img src="https://www.couffrant-solar.fr/signature/logo-couffrant-solar.jpg"
             alt="Couffrant Solar" style="max-width:420px; height:auto; border:0;">
    </div>
</div>"""
    try:
        resp = requests.post(
            "https://graph.microsoft.com/v1.0/me/sendMail",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={
                "message": {
                    "subject": row[2],
                    "body": {"contentType": "HTML", "content": html_body},
                    "toRecipients": [{"emailAddress": {"address": row[0]}}]
                }
            },
            timeout=30,
        )
        if resp.status_code != 202:
            conn.close()
            return {"error": "Echec envoi mail", "status_code": resp.status_code, "details": resp.text}
        c.execute("UPDATE mail_memory SET reply_status='sent' WHERE id=%s", (mail_id,))
        conn.commit()
    finally:
        conn.close()

    return RedirectResponse("/assistant-dashboard-readable", status_code=303)


@app.get("/assistant-dashboard-readable", response_class=HTMLResponse)
def assistant_dashboard_readable(days: int = 2):
    dashboard = get_dashboard(days)

    def render_block(title: str, items: list[dict]) -> str:
        html = f"<h2>{title}</h2>"
        if not items:
            return html + "<p>Aucun sujet.</p>"

        for i, item in enumerate(items):
            detail_id = f"detail_{title}_{i}".replace(" ", "_")
            color = "#c62828" if item["priority"] == "haute" else "#ef6c00" if item["priority"] == "moyenne" else "#888"
            senders = ", ".join(item.get("senders", [])[:2])
            if len(item.get("senders", [])) > 2:
                senders += f" (+{len(item['senders']) - 2} autres)"
            sender_list = "".join(f"<li>{s}</li>" for s in item.get("senders", []))

            actions_html = ""
            edit_html = ""
            if item.get("suggested_reply"):
                mail_id = item.get("id", "")
                actions_html = f"""<div style="margin-top:10px;" onclick="event.stopPropagation()">
                    <a href="/validate-reply/{mail_id}" onclick="localStorage.setItem('open_dashboard_card','{detail_id}');event.stopPropagation();" style="margin-right:10px;">✅ Valider</a>
                    <a href="/send-reply/{mail_id}" onclick="localStorage.setItem('open_dashboard_card','{detail_id}');event.stopPropagation();" style="margin-right:10px;">📤 Envoyer</a>
                </div>"""
                edit_html = f"""<form method="post" action="/save-reply-correction/{mail_id}" style="margin-top:10px;" onclick="event.stopPropagation()" onsubmit="localStorage.setItem('open_dashboard_card','{detail_id}')">
                    <div><b>✏️ Modifier la réponse :</b></div>
                    <textarea name="final_reply" onclick="event.stopPropagation()" style="width:100%;min-height:120px;margin-top:6px;">{item.get("suggested_reply", "")}</textarea>
                    <button type="submit" onclick="event.stopPropagation()" style="margin-top:8px;">💾 Enregistrer correction</button>
                </form>"""

            html += f"""<div onclick="toggle('{detail_id}')" style="background:white;border-radius:10px;padding:16px;margin-bottom:14px;box-shadow:0 2px 8px rgba(0,0,0,0.08);cursor:pointer;">
                <div style="font-size:20px;font-weight:bold;color:{color};margin-bottom:8px;">{item['topic']}</div>
                <div><b>Priorité :</b> {item['priority']}</div>
                <div><b>Catégorie :</b> {item['category']}</div>
                <div><b>Expéditeurs :</b> {senders}</div>
                <div><b>Mails liés :</b> {item['mail_count']}</div>
                <div><b>Raison :</b> {item['reason']}</div>
                <div style="color:#1f6feb;font-weight:bold;">{"📝 Réponse prête" if item.get("suggested_reply") else ""}</div>
                <div id="{detail_id}" onclick="event.stopPropagation()" style="display:none;margin-top:12px;padding-top:10px;border-top:1px solid #ddd;">
                    <div><b>Action :</b> {item['action']}</div>
                    <div><b>Type :</b> {item.get('response_type', '')}</div>
                    <div><b>Manque :</b> {", ".join(item.get('missing_fields') or [])}</div>
                    <div><b>Confiance :</b> {item.get('confidence_level', '')}</div>
                    <div style="margin-top:12px;"><b>Contenu du mail :</b></div>
                    <div style="white-space:pre-wrap;background:#f8f8f8;padding:10px;border-radius:6px;margin-top:6px;">{item.get('raw_body_preview', '')}</div>
                    <div style="margin-top:8px;"><b>Détail expéditeurs :</b></div>
                    <ul>{sender_list}</ul>
                    {edit_html}
                    {actions_html}
                </div>
            </div>"""
        return html

    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Assistant Dashboard</title>
<script>
function toggle(id) {{
    var el = document.getElementById(id);
    if (!el) return;
    if (el.style.display === "none" || el.style.display === "") {{
        el.style.display = "block";
        localStorage.setItem("open_dashboard_card", id);
    }} else {{
        el.style.display = "none";
        localStorage.removeItem("open_dashboard_card");
    }}
}}
window.addEventListener("load", function () {{
    var openId = localStorage.getItem("open_dashboard_card");
    if (openId) {{ var el = document.getElementById(openId); if (el) el.style.display = "block"; }}
}});
</script>
<style>
    body {{ font-family: Arial, sans-serif; margin: 30px; background: #f7f7f7; color: #222; }}
    h1 {{ margin-bottom: 10px; }} h2 {{ margin-top: 30px; }}
    .topbar {{ display: flex; gap: 10px; align-items: center; margin-bottom: 20px; }}
    .btn {{ display: inline-block; background: #1f6feb; color: white; text-decoration: none; padding: 10px 14px; border-radius: 8px; font-weight: bold; }}
    .btn:hover {{ opacity: 0.9; }}
</style></head><body>
<h1>Assistant Dashboard</h1>
<div class="topbar">
    <a class="btn" href="/ingest-mails-fast">🔄 Rafraîchir</a>
    <a class="btn" href="/assistant-dashboard-readable">📨 File réponses</a>
    <a class="btn" href="/reply-learning-readable">🧠 Mémoire corrections</a>
</div>
<div style="color:#666;margin-bottom:20px;">{dashboard['count']} sujets sur {days} jours</div>"""
    html += render_block("🔴 Urgents", dashboard["urgent"])
    html += render_block("🟠 À suivre", dashboard["normal"])
    html += render_block("⚪ Secondaires", dashboard["low"])
    html += "</body></html>"
    return HTMLResponse(content=html)


@app.get("/test-outlook-unread")
def test_outlook_unread(request: Request):
    token = request.session.get("access_token")
    if not token:
        return RedirectResponse("/login?next=/test-outlook-unread")
    return perform_outlook_action("list_unread_messages", {"top": 5}, token)

@app.get("/login/gmail")
def login_gmail():
    from app.connectors.gmail_connector import get_gmail_auth_url
    auth_url = get_gmail_auth_url()
    return RedirectResponse(auth_url)


@app.get("/auth/gmail/callback")
def auth_gmail_callback(request: Request, code: str | None = None):
    if not code:
        return HTMLResponse("Code manquant", status_code=400)

    from app.connectors.gmail_connector import exchange_code_for_tokens
    tokens = exchange_code_for_tokens(code)

    access_token = tokens.get("access_token")
    refresh_token = tokens.get("refresh_token")

    conn = get_pg_conn()
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS gmail_tokens (
            id SERIAL PRIMARY KEY,
            email TEXT,
            access_token TEXT,
            refresh_token TEXT,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    c.execute("DELETE FROM gmail_tokens WHERE email = %s", ("per1.guillaume@gmail.com",))
    c.execute("""
        INSERT INTO gmail_tokens (email, access_token, refresh_token)
        VALUES (%s, %s, %s)
    """, ("per1.guillaume@gmail.com", access_token, refresh_token))
    conn.commit()
    conn.close()

    return {"status": "ok", "message": "Gmail connecté avec succès !"}


@app.get("/ingest-gmail")
def ingest_gmail(request: Request):
    from app.connectors.gmail_connector import gmail_get_messages, gmail_get_message, refresh_gmail_token

    conn = get_pg_conn()
    c = conn.cursor()
    c.execute("SELECT access_token, refresh_token FROM gmail_tokens WHERE email = %s", ("per1.guillaume@gmail.com",))
    row = c.fetchone()
    conn.close()

    if not row:
        return {"error": "Gmail non connecté — va sur /login/gmail d'abord"}

    access_token = row[0]
    refresh_token = row[1]

    try:
        messages = gmail_get_messages(access_token, max_results=10)
    except Exception:
        access_token = refresh_gmail_token(refresh_token)
        messages = gmail_get_messages(access_token, max_results=10)

    inserted = 0
    conn = get_pg_conn()
    c = conn.cursor()

    skip_keywords = [
        "noreply", "no-reply", "donotreply", "newsletter", "unsubscribe",
        "se désabonner", "notification", "mailer-daemon", "marketing",
        "promo", "offre spéciale", "linkedin", "twitter", "facebook",
        "instagram", "jobteaser", "indeed", "welcometothejungle",
    ]

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
                continue

            c.execute("""
                INSERT INTO mail_memory
                (message_id, received_at, from_email, subject,
                 raw_body_preview, analysis_status, mailbox_source, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (message_id) DO NOTHING
            """, (
                message_id,
                date,
                from_email,
                subject,
                snippet,
                "gmail_raw",
                "gmail_perso",
                datetime.utcnow().isoformat(),
            ))
            inserted += 1
        except Exception:
            conn.rollback()
            continue

    conn.commit()
    conn.close()

    return {"inserted": inserted, "total_fetched": len(messages)}

@app.post("/speak")
def speak_text(payload: dict = Body(...)):
    from app.config import ELEVENLABS_API_KEY, ELEVENLABS_VOICE_ID
    from fastapi.responses import StreamingResponse
    from fastapi import Body
    import re
    import io

    text = payload.get("text", "")
    clean = re.sub(r'#{1,6}\s+', '', text)
    clean = re.sub(r'\*\*(.*?)\*\*', r'\1', clean)
    clean = re.sub(r'\*(.*?)\*', r'\1', clean)
    clean = re.sub(r'`(.*?)`', r'\1', clean)
    clean = re.sub(r'---+', '', clean)
    clean = re.sub(r'\|.*?\|', '', clean)
    clean = re.sub(r'^\s*[-•]\s', '', clean, flags=re.MULTILINE)
    clean = clean.strip()

    resp = requests.post(
        f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE_ID}",
        headers={
            "xi-api-key": ELEVENLABS_API_KEY,
            "Content-Type": "application/json",
        },
        json={
            "text": clean[:2500],
            "model_id": "eleven_multilingual_v2",
            "voice_settings": {
                "stability": 0.5,
                "similarity_boost": 0.8,
                "style": 0.2,
                "use_speaker_boost": True
            }
        },
        timeout=30,
    )

    if resp.status_code != 200:
        return {"error": "ElevenLabs error", "detail": resp.text}

    return StreamingResponse(
        io.BytesIO(resp.content),
        media_type="audio/mpeg",
    )

@app.get("/test-odoo")
def test_odoo():
    from app.connectors.odoo_connector import perform_odoo_action
    result = perform_odoo_action(
        action="get_partner_by_email",
        params={"email": "guillaume@couffrant-solar.fr"}
    )
    return result

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

@app.get("/learn-archive-mails")
def learn_archive_mails(request: Request, top: int = 100, skip: int = 0):
    token = request.session.get("access_token")
    if not token:
        return RedirectResponse("/login?next=/learn-archive-mails")

    folder_id = "AQMkAGEwZmJhNTllLWQ3MjUtNDg4ADQtYjdhMi1jMGEyZjRiNmFkNWEALgAAA-6yBmE1L7hGi--BXSl5S2sBAIyf8uOKE0VAkKv1dN8K6xgAAAIBRQAAAA=="

    try:
        data = graph_get(
            token,
            f"/me/mailFolders/{folder_id}/messages",
            params={
                "$top": top,
                "$skip": skip,
                "$select": "id,subject,from,receivedDateTime,bodyPreview",
                "$orderby": "receivedDateTime DESC",
            },
        )
    except requests.HTTPError:
        request.session.pop("access_token", None)
        return RedirectResponse("/login?next=/learn-archive-mails")

    messages = data.get("value", [])
    inserted = 0
    skipped_noise = 0
    conn = get_pg_conn()
    c = conn.cursor()

    skip_keywords = [
        "noreply", "no-reply", "donotreply", "newsletter", "unsubscribe",
        "se désabonner", "notification", "mailer-daemon", "marketing",
        "promo", "offre spéciale", "linkedin", "twitter", "facebook",
        "instagram", "jobteaser", "indeed", "welcometothejungle",
        "calendly", "zoom", "teams", "webinar", "webinaire",
        "satisfaction", "avis client", "enquête", "survey",
    ]

    for msg in messages:
        message_id = msg["id"]
        c.execute("SELECT 1 FROM mail_memory WHERE message_id = %s", (message_id,))
        if c.fetchone():
            continue

        from_email = msg.get("from", {}).get("emailAddress", {}).get("address", "").lower()
        subject = (msg.get("subject") or "").lower()
        body = (msg.get("bodyPreview") or "").lower()
        full_text = f"{from_email} {subject} {body}"

        if any(kw in full_text for kw in skip_keywords):
            skipped_noise += 1
            continue

        try:
            c.execute("""
                INSERT INTO mail_memory
                (message_id, received_at, from_email, subject,
                 raw_body_preview, analysis_status, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (message_id) DO NOTHING
            """, (
                message_id,
                msg.get("receivedDateTime"),
                msg.get("from", {}).get("emailAddress", {}).get("address", ""),
                msg.get("subject"),
                msg.get("bodyPreview"),
                "archive_raw",
                datetime.utcnow().isoformat(),
            ))
            inserted += 1
        except Exception:
            continue

    conn.commit()
    conn.close()

    return {
        "inserted": inserted,
        "skipped_noise": skipped_noise,
        "total_fetched": len(messages),
        "skip": skip,
        "message": f"{inserted} mails archivés utiles stockés, {skipped_noise} bruits ignorés"
    }

@app.get("/learn-gmail-all")
def learn_gmail_all(request: Request, max_results: int = 100, page_token: str = None):
    from app.connectors.gmail_connector import gmail_get_messages, gmail_get_message, refresh_gmail_token
    from app.config import ANTHROPIC_MODEL_FAST

    conn = get_pg_conn()
    c = conn.cursor()
    c.execute("SELECT access_token, refresh_token FROM gmail_tokens WHERE email = %s", ("per1.guillaume@gmail.com",))
    row = c.fetchone()
    conn.close()

    if not row:
        return {"error": "Gmail non connecté"}

    access_token = row[0]
    refresh_token = row[1]

    try:
        response = requests.get(
            "https://gmail.googleapis.com/gmail/v1/users/me/messages",
            headers={"Authorization": f"Bearer {access_token}"},
            params={
                "maxResults": max_results,
                "pageToken": page_token,
            },
            timeout=30,
        )
        if response.status_code == 401:
            access_token = refresh_gmail_token(refresh_token)
            response = requests.get(
                "https://gmail.googleapis.com/gmail/v1/users/me/messages",
                headers={"Authorization": f"Bearer {access_token}"},
                params={"maxResults": max_results, "pageToken": page_token},
                timeout=30,
            )
        data = response.json()
    except Exception as e:
        return {"error": str(e)}

    messages = data.get("messages", [])
    next_page_token = data.get("nextPageToken")
    inserted = 0
    skipped_noise = 0
    skipped_ai = 0

    skip_keywords = [
        "noreply", "no-reply", "donotreply", "newsletter", "unsubscribe",
        "se désabonner", "notification", "mailer-daemon", "marketing",
        "promo", "offre spéciale", "linkedin", "twitter", "facebook",
        "instagram", "jobteaser", "indeed", "welcometothejungle",
        "calendly", "zoom", "teams", "webinar", "webinaire",
        "satisfaction", "avis client", "enquête", "survey",
    ]

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

            # Niveau 1 — filtre mots-clés gratuit
            if any(kw in full_text for kw in skip_keywords):
                skipped_noise += 1
                continue

            # Niveau 2 — analyse Claude Haiku
            try:
                decision = client.messages.create(
                    model=ANTHROPIC_MODEL_FAST,
                    max_tokens=5,
                    messages=[{
                        "role": "user",
                        "content": f"Mail de : {from_email}\nSujet : {subject}\nContenu : {snippet[:200]}\n\nCe mail est-il pertinent pour un chef d'entreprise dans le solaire photovoltaïque ? Réponds uniquement OUI ou NON."
                    }]
                )
                if "NON" in decision.content[0].text.upper():
                    skipped_ai += 1
                    continue
            except Exception:
                pass

            c.execute("""
                INSERT INTO mail_memory
                (message_id, received_at, from_email, subject,
                 raw_body_preview, analysis_status, mailbox_source, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (message_id) DO NOTHING
            """, (
                message_id,
                date,
                from_email,
                subject,
                snippet,
                "gmail_raw",
                "gmail_perso",
                datetime.utcnow().isoformat(),
            ))
            inserted += 1
        except Exception:
            conn.rollback()
            continue

    conn.commit()
    conn.close()

    return {
        "inserted": inserted,
        "skipped_noise": skipped_noise,
        "skipped_ai": skipped_ai,
        "total_fetched": len(messages),
        "next_page_token": next_page_token,
        "message": f"{inserted} stockés, {skipped_noise} bruits filtrés, {skipped_ai} rejetés par IA"
    }

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

    access_token = row[0]
    refresh_token = row[1]

    try:
        response = requests.get(
            "https://gmail.googleapis.com/gmail/v1/users/me/messages",
            headers={"Authorization": f"Bearer {access_token}"},
            params={
                "maxResults": max_results,
                "labelIds": "SENT",
                "pageToken": page_token,
            },
            timeout=30,
        )
        if response.status_code == 401:
            access_token = refresh_gmail_token(refresh_token)
            response = requests.get(
                "https://gmail.googleapis.com/gmail/v1/users/me/messages",
                headers={"Authorization": f"Bearer {access_token}"},
                params={"maxResults": max_results, "labelIds": "SENT", "pageToken": page_token},
                timeout=30,
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
            subject = headers.get("Subject", "(Sans objet)")
            to_email = headers.get("To", "")
            date = headers.get("Date", "")
            snippet = detail.get("snippet", "")

            c.execute("""
                INSERT INTO sent_mail_memory
                (message_id, sent_at, to_email, subject, body_preview)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (message_id) DO NOTHING
            """, (
                message_id,
                date,
                to_email,
                subject,
                snippet,
            ))
            inserted += 1
        except Exception:
            conn.rollback()
            continue

    conn.commit()
    conn.close()

    return {
        "inserted": inserted,
        "total_fetched": len(messages),
        "next_page_token": next_page_token,
        "message": f"{inserted} mails envoyés Gmail mémorisés"
    }