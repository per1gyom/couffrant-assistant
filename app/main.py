import os
import requests
import json
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import FastAPI, Request, Form, Body
from fastapi.responses import RedirectResponse, HTMLResponse, StreamingResponse
from starlette.middleware.sessions import SessionMiddleware
from pydantic import BaseModel

from app.auth import build_msal_app
from app.config import (
    GRAPH_SCOPES, REDIRECT_URI, SESSION_SECRET,
    AUTHORITY, ANTHROPIC_MODEL_SMART, ANTHROPIC_MODEL_FAST
)
from app.graph_client import graph_get
from app.ai_client import summarize_messages, analyze_single_mail_with_ai, client
from app.feedback_store import init_db, add_global_instruction, get_global_instructions
from app.mail_memory_store import init_mail_db, insert_mail, mail_exists
from app.assistant_analyzer import analyze_single_mail
from app.dashboard_service import get_dashboard
from app.connectors.outlook_connector import (
    perform_outlook_action, list_aria_drive, read_aria_drive_file,
    search_aria_drive, create_drive_folder, copy_drive_item
)
from app.database import get_pg_conn, init_postgres

try:
    from app.memory_manager import (
        get_hot_summary, rebuild_hot_summary,
        get_contact_card, get_all_contact_cards, rebuild_contacts,
        get_style_examples, save_style_example, learn_from_correction, load_sent_mails_to_style,
        purge_old_mails
    )
    MEMORY_OK = True
except Exception as _mem_err:
    print(f"[Memory] Module non disponible: {_mem_err}")
    MEMORY_OK = False
    def get_hot_summary(): return ""
    def rebuild_hot_summary(): return ""
    def get_contact_card(x): return ""
    def get_all_contact_cards(): return []
    def rebuild_contacts(): return 0
    def get_style_examples(**kwargs): return ""
    def save_style_example(**kwargs): pass
    def learn_from_correction(**kwargs): pass
    def load_sent_mails_to_style(**kwargs): return 0
    def purge_old_mails(**kwargs): return 0


app = FastAPI(title="Couffrant Solar Assistant")
app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET)


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

    import threading
    def auto_ingest():
        import time
        cycle = 0
        while True:
            try:
                from app.token_manager import get_valid_microsoft_token
                from app.graph_client import graph_get as _graph_get
                from app.ai_client import analyze_single_mail_with_ai as _analyze_ai
                from app.mail_memory_store import mail_exists as _mail_exists, insert_mail as _insert_mail
                from app.feedback_store import get_global_instructions as _get_instructions
                from app.assistant_analyzer import analyze_single_mail as _analyze

                token = get_valid_microsoft_token()
                if token:
                    data = _graph_get(
                        token, "/me/mailFolders/inbox/messages",
                        params={"$top": 10, "$select": "id,subject,from,receivedDateTime,bodyPreview", "$orderby": "receivedDateTime DESC"},
                    )
                    messages = data.get("value", [])
                    instructions = _get_instructions()
                    for msg in messages:
                        message_id = msg["id"]
                        if _mail_exists(message_id):
                            continue
                        try:
                            item = _analyze_ai(msg, instructions)
                            analysis_status = "done_ai"
                        except Exception:
                            item = _analyze(msg)
                            analysis_status = "fallback"
                        _insert_mail({
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
                if cycle % 40 == 0 and MEMORY_OK:
                    try:
                        rebuild_hot_summary()
                        print("[Memory] Résumé chaud reconstruit")
                    except Exception as e:
                        print(f"[Memory] Erreur: {e}")

            except Exception as e:
                print(f"[AutoIngest] Erreur: {e}")
            time.sleep(30)

    thread = threading.Thread(target=auto_ingest, daemon=True)
    thread.start()


@app.get("/health")
def health():
    return {"status": "ok", "memory_module": MEMORY_OK}


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
        json={"text": clean, "model_id": "eleven_flash_v2_5", "voice_settings": {"stability": 0.5, "similarity_boost": 0.8, "style": 0.2, "use_speaker_boost": True}},
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

    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            SELECT id as db_id, message_id, from_email, display_title, category, priority,
                   short_summary, suggested_reply, raw_body_preview, received_at, mailbox_source
            FROM mail_memory ORDER BY received_at DESC NULLS LAST LIMIT 10
        """)
        columns = [desc[0] for desc in c.description]
        mails_from_db = [dict(zip(columns, row)) for row in c.fetchall()]

        c.execute("SELECT user_input, aria_response FROM aria_memory ORDER BY id DESC LIMIT 8")
        columns = [desc[0] for desc in c.description]
        history = [dict(zip(columns, row)) for row in c.fetchall()]
        history.reverse()

        c.execute("SELECT content FROM aria_profile WHERE profile_type = 'style' ORDER BY id DESC LIMIT 1")
        profile_row = c.fetchone()
        profile = profile_row[0] if profile_row else ""
    finally:
        if conn:
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
        context=payload.query[:100] if any(w in query_lower for w in ["répond", "rédige", "écris", "mail"]) else ""
    )

    outlook_token = get_valid_microsoft_token()

    outlook_live_mails = []
    if outlook_token:
        try:
            data = graph_get(outlook_token, "/me/mailFolders/inbox/messages", params={
                "$top": 20, "$select": "id,subject,from,receivedDateTime,bodyPreview,isRead",
                "$orderby": "receivedDateTime DESC",
            })
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

    user_content_parts = []
    if payload.file_data and payload.file_type:
        file_name_info = f" ({payload.file_name})" if payload.file_name else ""
        if payload.file_type.startswith("image/"):
            user_content_parts.append({
                "type": "image",
                "source": {"type": "base64", "media_type": payload.file_type, "data": payload.file_data}
            })
            user_content_parts.append({
                "type": "text",
                "text": f"[Fichier joint{file_name_info}]\n{payload.query}" if payload.query else f"[Image jointe{file_name_info}] Analyse ce document."
            })
        elif payload.file_type == "application/pdf":
            user_content_parts.append({
                "type": "document",
                "source": {"type": "base64", "media_type": "application/pdf", "data": payload.file_data}
            })
            user_content_parts.append({
                "type": "text",
                "text": f"[PDF joint{file_name_info}]\n{payload.query}" if payload.query else f"[PDF joint{file_name_info}] Analyse ce document."
            })
        else:
            user_content_parts.append({"type": "text", "text": f"[Fichier joint{file_name_info}]\n{payload.query}"})
    else:
        user_content_parts = payload.query

    system = f"""Tu es Aria, l'assistante personnelle de Guillaume Perrin, dirigeant de Couffrant Solar.

Guillaume dirige une PME de 8 personnes dans le photovoltaïque. Direct, efficace, déteste les réponses longues inutiles. Il te tutoie. Tu parles au féminin.

Profil Guillaume :
{profile[:600] if profile else "Profil en cours de construction."}

{f"=== SITUATION ACTUELLE ==={chr(10)}{hot_summary}" if hot_summary else ""}

{f"=== FICHE CONTACT ==={chr(10)}{contact_card}" if contact_card else ""}

{f"=== EXEMPLES DE STYLE ==={chr(10)}{style_examples}" if style_examples else ""}

Règles :
- Réponds naturellement, sans structure imposée.
- Si Guillaume dit "oui", "vas-y", "fais-le" → exécute la dernière action proposée.
- Ne dis jamais "c'est fait" sans confirmation API réelle.
- Tu es rigoureuse : quand on te demande les mails urgents, tu TOUS les signales sans en oublier.
- Tu proposes toujours, Guillaume décide toujours — aucune action sans validation explicite.

{"Accès complet Microsoft 365." if outlook_token else "Pas de connexion Microsoft."}

IDENTIFIANTS — CRITIQUE :
- `message_id` : longue chaîne Outlook → TOUJOURS pour les actions mail
- `db_id` : entier court → JAMAIS pour les actions
- `mailbox_source` : "outlook" (actions OK) | "gmail_perso" (lecture seule)

Actions Outlook :
- [ACTION:DELETE:message_id] → corbeille récupérable
- [ACTION:ARCHIVE:message_id]
- [ACTION:READ:message_id]
- [ACTION:REPLY:message_id:texte]
- [ACTION:READBODY:message_id]
- [ACTION:CREATEEVENT:sujet|debut_iso|fin_iso|participants]
- [ACTION:CREATE_TASK:titre]

Actions Drive SharePoint (dossier 1_Photovoltaïque uniquement) :
- [ACTION:LISTDRIVE:] → liste la racine (chaque item retourne son 'id')
- [ACTION:LISTDRIVE:nom_dossier] → liste un sous-dossier par son nom
- [ACTION:LISTDRIVE:item_id] → liste par ID — TOUJOURS préférer l'id pour les sous-dossiers
- [ACTION:READDRIVE:item_id] → lit un fichier par son ID
- [ACTION:SEARCHDRIVE:mot-clé] → recherche par nom dans tout le dossier
- [ACTION:CREATEFOLDER:parent_item_id|nom_dossier] → crée un dossier
- [ACTION:COPYFILE:source_item_id|dest_folder_id|nouveau_nom] → copie un fichier

RÈGLE DRIVE : Après LISTDRIVE, chaque item a un 'id'. Toujours utiliser cet id pour naviguer/copier.

Propose avant d'agir, SAUF si Guillaume dit "fais-le", "vas-y", "oui".

Agenda aujourd'hui ({datetime.now().strftime('%A %d %B %Y')}) :
{json.dumps(agenda_today, ensure_ascii=False, default=str) if agenda_today else "Aucun RDV."}

=== MAILS OUTLOOK EN TEMPS RÉEL ({len(outlook_live_mails)} mails inbox) ===
{json.dumps(outlook_live_mails, ensure_ascii=False, default=str) if outlook_live_mails else "Aucun mail Outlook récupéré."}

=== MAILS EN BASE (Gmail + historique) ===
{json.dumps(mails_from_db, ensure_ascii=False, default=str)}

Consignes :
{chr(10).join(instructions) if instructions else "Aucune."}
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
        for msg_id in re.findall(r'\[ACTION:DELETE:([^\]]+)\]', aria_response):
            msg_id = msg_id.strip()
            if not is_valid_outlook_id(msg_id):
                actions_confirmed.append("\u274c ID invalide pour suppression")
                continue
            try:
                result = perform_outlook_action("delete_message", {"message_id": msg_id}, outlook_token)
                actions_confirmed.append("\u2705 Mis à la corbeille" if result.get("status") == "ok" else f"\u274c {result.get('message')}")
            except Exception as e:
                actions_confirmed.append(f"\u274c Erreur : {str(e)[:100]}")

        for msg_id in re.findall(r'\[ACTION:ARCHIVE:([^\]]+)\]', aria_response):
            msg_id = msg_id.strip()
            if not is_valid_outlook_id(msg_id):
                actions_confirmed.append("\u274c ID invalide pour archivage")
                continue
            try:
                result = perform_outlook_action("archive_message", {"message_id": msg_id}, outlook_token)
                actions_confirmed.append("\u2705 Archivé" if result.get("status") == "ok" else f"\u274c {result.get('message')}")
            except Exception as e:
                actions_confirmed.append(f"\u274c Erreur archivage : {str(e)[:100]}")

        for msg_id in re.findall(r'\[ACTION:READ:([^\]]+)\]', aria_response):
            msg_id = msg_id.strip()
            if not is_valid_outlook_id(msg_id):
                continue
            try:
                result = perform_outlook_action("mark_as_read", {"message_id": msg_id}, outlook_token)
                actions_confirmed.append("\u2705 Marqué lu" if result.get("status") == "ok" else "\u274c Erreur")
            except Exception as e:
                actions_confirmed.append(f"\u274c Erreur : {str(e)[:100]}")

        for match in re.finditer(r'\[ACTION:REPLY:([^:\]]{20,}):(.+?)\]', aria_response, re.DOTALL):
            msg_id = match.group(1).strip()
            reply_text = match.group(2).strip()
            if not is_valid_outlook_id(msg_id):
                actions_confirmed.append("\u274c ID invalide pour réponse")
                continue
            try:
                result = perform_outlook_action("send_reply", {"message_id": msg_id, "reply_body": reply_text}, outlook_token)
                if result.get("status") == "ok":
                    try:
                        learn_from_correction(original="", corrected=reply_text, context="réponse mail")
                    except Exception:
                        pass
                actions_confirmed.append("\u2705 Réponse envoyée" if result.get("status") == "ok" else f"\u274c {result.get('message')}")
            except Exception as e:
                actions_confirmed.append(f"\u274c Erreur envoi : {str(e)[:100]}")

        for msg_id in re.findall(r'\[ACTION:READBODY:([^\]]+)\]', aria_response):
            msg_id = msg_id.strip()
            if not is_valid_outlook_id(msg_id):
                actions_confirmed.append("\u274c ID invalide pour lecture corps")
                continue
            try:
                result = perform_outlook_action("get_message_body", {"message_id": msg_id}, outlook_token)
                if result.get("status") == "ok":
                    actions_confirmed.append(f"\U0001f4e7 Corps du mail :\n{result.get('body_text', '')[:800]}")
            except Exception as e:
                actions_confirmed.append(f"\u274c Erreur lecture corps : {str(e)[:100]}")

        for match in re.finditer(r'\[ACTION:CREATEEVENT:([^\]]+)\]', aria_response):
            parts = match.group(1).split('|')
            if len(parts) >= 3:
                try:
                    attendees = parts[3].split(',') if len(parts) > 3 else []
                    result = perform_outlook_action("create_calendar_event", {
                        "subject": parts[0], "start": parts[1], "end": parts[2], "attendees": attendees
                    }, outlook_token)
                    actions_confirmed.append("\u2705 RDV créé" if result.get("status") == "ok" else "\u274c Création RDV échouée")
                except Exception as e:
                    actions_confirmed.append(f"\u274c Erreur agenda : {str(e)[:100]}")

        for title in re.findall(r'\[ACTION:CREATE_TASK:([^\]]+)\]', aria_response):
            try:
                result = perform_outlook_action("create_todo_task", {"title": title.strip()}, outlook_token)
                actions_confirmed.append("\u2705 Tâche créée" if result.get("status") == "ok" else "\u274c Tâche échouée")
            except Exception as e:
                actions_confirmed.append(f"\u274c Erreur tâche : {str(e)[:100]}")

        # ── Drive SharePoint ──
        for match in re.finditer(r'\[ACTION:LISTDRIVE:([^\]]*)\]', aria_response):
            subfolder = match.group(1).strip()
            try:
                result = list_aria_drive(outlook_token, subfolder)
                if result.get("status") == "ok":
                    lines = [f"  {it['type']} {it['nom']} (id:{it.get('id','')[:8]}… {it.get('taille_ko','')} Ko)" for it in result.get("items", [])]
                    actions_confirmed.append(f"\U0001f4c1 {result.get('dossier', subfolder)} ({result['count']} éléments) :\n" + "\n".join(lines))
                else:
                    actions_confirmed.append(f"\u274c {result.get('message', 'Erreur Drive')}")
            except Exception as e:
                actions_confirmed.append(f"\u274c Erreur Drive : {str(e)[:100]}")

        for match in re.finditer(r'\[ACTION:READDRIVE:([^\]]+)\]', aria_response):
            file_ref = match.group(1).strip()
            try:
                result = read_aria_drive_file(outlook_token, file_ref)
                if result.get("status") == "ok":
                    if result.get("type") == "texte":
                        actions_confirmed.append(f"\U0001f4c4 {result['fichier']} :\n{result['contenu'][:2000]}")
                    else:
                        actions_confirmed.append(f"\U0001f4c4 {result.get('fichier', file_ref)} — {result.get('message', '')} {result.get('conseil', '')}")
                else:
                    actions_confirmed.append(f"\u274c {result.get('message', 'Erreur lecture')}")
            except Exception as e:
                actions_confirmed.append(f"\u274c Erreur lecture fichier : {str(e)[:100]}")

        for match in re.finditer(r'\[ACTION:SEARCHDRIVE:([^\]]+)\]', aria_response):
            query_drive = match.group(1).strip()
            try:
                result = search_aria_drive(outlook_token, query_drive)
                if result.get("status") == "ok":
                    lines = [f"  {it['type']} {it['nom']} (id:{it.get('id','')[:8]}…)" for it in result.get("items", [])]
                    actions_confirmed.append(f"\U0001f50d '{query_drive}' — {result['count']} résultat(s) :\n" + "\n".join(lines))
                else:
                    actions_confirmed.append(f"\u274c {result.get('message', 'Erreur recherche')}")
            except Exception as e:
                actions_confirmed.append(f"\u274c Erreur recherche Drive : {str(e)[:100]}")

        for match in re.finditer(r'\[ACTION:CREATEFOLDER:([^|^\]]+)\|([^\]]+)\]', aria_response):
            parent_id = match.group(1).strip()
            folder_name = match.group(2).strip()
            try:
                from app.connectors.outlook_connector import _find_sharepoint_site_and_drive
                _, drive_id, _ = _find_sharepoint_site_and_drive(outlook_token)
                result = create_drive_folder(outlook_token, parent_id, folder_name, drive_id)
                if result.get("status") == "ok":
                    actions_confirmed.append(f"\u2705 Dossier '{folder_name}' créé (id:{result.get('id','')[:8]}…)")
                else:
                    actions_confirmed.append(f"\u274c {result.get('message', 'Erreur création dossier')}")
            except Exception as e:
                actions_confirmed.append(f"\u274c Erreur création dossier : {str(e)[:100]}")

        for match in re.finditer(r'\[ACTION:COPYFILE:([^|^\]]+)\|([^|^\]]+)\|?([^\]]*)\]', aria_response):
            source_id = match.group(1).strip()
            dest_id = match.group(2).strip()
            new_name = match.group(3).strip() or None
            try:
                from app.connectors.outlook_connector import _find_sharepoint_site_and_drive
                _, drive_id, _ = _find_sharepoint_site_and_drive(outlook_token)
                result = copy_drive_item(outlook_token, source_id, dest_id, new_name, drive_id)
                if result.get("status") == "ok":
                    actions_confirmed.append(f"\u2705 {result.get('message', 'Copie effectuée.')}")
                else:
                    actions_confirmed.append(f"\u274c {result.get('message', 'Erreur copie')}")
            except Exception as e:
                actions_confirmed.append(f"\u274c Erreur copie : {str(e)[:100]}")

    clean_response = re.sub(r'\[ACTION:[A-Z_]+:[^\]]*\]', '', aria_response).strip()
    if actions_confirmed:
        clean_response += "\n\n" + "\n".join(actions_confirmed)

    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("INSERT INTO aria_memory (user_input, aria_response) VALUES (%s, %s)", (payload.query, clean_response))
        conn.commit()
    finally:
        if conn:
            conn.close()

    return {"answer": clean_response, "actions": actions_confirmed}


# ─── MÉMOIRE ───

@app.get("/build-memory")
def build_memory():
    results = {"memory_module": MEMORY_OK}
    if not MEMORY_OK:
        return {"error": "Module mémoire non disponible", "memory_module": False}
    try:
        summary = rebuild_hot_summary()
        results["hot_summary"] = "\u2705 Résumé chaud reconstruit"
        results["preview"] = summary[:200]
    except Exception as e:
        results["hot_summary"] = f"\u274c {str(e)[:100]}"
    try:
        count = rebuild_contacts()
        results["contacts"] = f"\u2705 {count} fiches contacts"
    except Exception as e:
        results["contacts"] = f"\u274c {str(e)[:100]}"
    try:
        added = load_sent_mails_to_style(limit=50)
        results["style"] = f"\u2705 {added} exemples de style"
    except Exception as e:
        results["style"] = f"\u274c {str(e)[:100]}"
    return results


@app.get("/memory-status")
def memory_status():
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        try:
            c.execute("SELECT content, updated_at FROM aria_hot_summary WHERE id = 1")
            row = c.fetchone()
        except Exception:
            row = None
        try:
            c.execute("SELECT COUNT(*) FROM aria_contacts")
            contacts_count = c.fetchone()[0]
        except Exception:
            contacts_count = 0
        try:
            c.execute("SELECT COUNT(*) FROM aria_style_examples")
            style_count = c.fetchone()[0]
        except Exception:
            style_count = 0
        c.execute("SELECT COUNT(*) FROM mail_memory")
        mails_count = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM sent_mail_memory")
        sent_count = c.fetchone()[0]
    finally:
        if conn:
            conn.close()
    return {
        "memory_module": MEMORY_OK,
        "resume_chaud": {"exists": bool(row and row[0]), "preview": (row[0] or "")[:150] if row else ""},
        "contacts": contacts_count,
        "style_examples": style_count,
        "mail_memory": mails_count,
        "sent_mail_memory": sent_count,
    }


@app.get("/analyze-raw-mails")
def analyze_raw_mails(limit: int = 50):
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            SELECT id, message_id, from_email, subject, raw_body_preview, received_at
            FROM mail_memory
            WHERE analysis_status IN ('inbox_raw', 'archive_raw', 'gmail_raw')
            ORDER BY received_at DESC NULLS LAST
            LIMIT %s
        """, (limit,))
        rows = c.fetchall()
    finally:
        if conn:
            conn.close()

    if not rows:
        return {"status": "termine", "analyzed": 0, "message": "Tous les mails sont déjà analysés."}

    instructions = get_global_instructions()
    analyzed = 0
    errors = 0

    for row in rows:
        db_id, message_id, from_email, subject, body_preview, received_at = row
        msg = {
            "id": message_id, "subject": subject,
            "from": {"emailAddress": {"address": from_email or ""}},
            "receivedDateTime": str(received_at) if received_at else "",
            "bodyPreview": body_preview or "",
        }
        try:
            item = analyze_single_mail_with_ai(msg, instructions)
            conn = None
            try:
                conn = get_pg_conn()
                c = conn.cursor()
                c.execute("""
                    UPDATE mail_memory SET
                        display_title = %s, category = %s, priority = %s, reason = %s,
                        suggested_action = %s, short_summary = %s, confidence = %s,
                        confidence_level = %s, needs_review = %s, needs_reply = %s,
                        reply_urgency = %s, reply_reason = %s, response_type = %s,
                        suggested_reply_subject = %s, suggested_reply = %s, analysis_status = 'done_ai'
                    WHERE id = %s
                """, (
                    item.get("display_title"), item.get("category"), item.get("priority"),
                    item.get("reason"), item.get("suggested_action"), item.get("short_summary"),
                    item.get("confidence", 0.5), item.get("confidence_level", "moyenne"),
                    int(item.get("needs_review", False)), int(item.get("needs_reply", False)),
                    item.get("reply_urgency"), item.get("reply_reason"), item.get("response_type"),
                    item.get("suggested_reply_subject"), item.get("suggested_reply"), db_id,
                ))
                conn.commit()
            finally:
                if conn:
                    conn.close()
            analyzed += 1
        except Exception as e:
            print(f"[AnalyzeRaw] Erreur mail {db_id}: {e}")
            errors += 1
            continue

    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM mail_memory WHERE analysis_status IN ('inbox_raw', 'archive_raw', 'gmail_raw')")
        remaining = c.fetchone()[0]
    finally:
        if conn:
            conn.close()

    return {
        "status": "ok", "analyzed": analyzed, "errors": errors, "remaining": remaining,
        "message": f"{analyzed} mails analysés. Il reste {remaining} mails bruts."
    }


@app.get("/contacts")
def list_contacts_endpoint():
    return get_all_contact_cards()


@app.get("/purge-memory")
def purge_memory(days: int = 90):
    deleted = purge_old_mails(days=days)
    return {"status": "ok", "deleted": deleted}


@app.post("/learn-style")
def learn_style(payload: dict = Body(...)):
    text = payload.get("text", "")
    if not text:
        return {"error": "Texte manquant"}
    save_style_example(situation=payload.get("situation", "mail"), example_text=text, tags=payload.get("tags", ""), quality_score=2.0)
    return {"status": "ok"}


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
        return HTMLResponse("Erreur d'authentification", status_code=400)
    request.session["access_token"] = result["access_token"]
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            INSERT INTO oauth_tokens (provider, access_token, refresh_token, expires_at)
            VALUES (%s, %s, %s, NOW() + INTERVAL '1 hour')
            ON CONFLICT (provider) DO UPDATE SET
                access_token = EXCLUDED.access_token, refresh_token = EXCLUDED.refresh_token,
                expires_at = EXCLUDED.expires_at, updated_at = NOW()
        """, ("microsoft", result["access_token"], result.get("refresh_token", "")))
        conn.commit()
    finally:
        if conn:
            conn.close()
    return RedirectResponse(state or "/chat")


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


@app.get("/memory")
def memory():
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("SELECT message_id, received_at, from_email, subject, display_title, category, priority, analysis_status FROM mail_memory ORDER BY id DESC LIMIT 20")
        columns = [desc[0] for desc in c.description]
        rows = [dict(zip(columns, row)) for row in c.fetchall()]
        return rows
    finally:
        if conn:
            conn.close()


@app.get("/rebuild-memory")
def rebuild_memory_mails():
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("DELETE FROM mail_memory")
        conn.commit()
    finally:
        if conn:
            conn.close()
    return {"status": "mail_memory_cleared"}


@app.get("/ingest-mails-fast")
def ingest_mails_fast(request: Request):
    token = request.session.get("access_token")
    if not token:
        return RedirectResponse("/login?next=/ingest-mails-fast")
    try:
        data = graph_get(token, "/me/mailFolders/inbox/messages", params={
            "$top": 5, "$select": "id,subject,from,receivedDateTime,bodyPreview", "$orderby": "receivedDateTime DESC",
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
            "$top": 1, "$select": "id,subject,from,receivedDateTime,bodyPreview", "$orderby": "receivedDateTime DESC",
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
            "$top": top, "$select": "id,subject,from,receivedDateTime,bodyPreview,toRecipients", "$orderby": "receivedDateTime DESC",
        })
    except requests.HTTPError:
        request.session.pop("access_token", None)
        return RedirectResponse("/login?next=/learn-sent-mails")
    messages = data.get("value", [])
    inserted = 0
    conn = None
    try:
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
                c.execute("INSERT INTO sent_mail_memory (message_id, sent_at, to_email, subject, body_preview) VALUES (%s, %s, %s, %s, %s) ON CONFLICT (message_id) DO NOTHING",
                          (message_id, msg.get("receivedDateTime"), to_email, msg.get("subject"), msg.get("bodyPreview")))
                inserted += 1
            except Exception:
                continue
        conn.commit()
    finally:
        if conn:
            conn.close()
    return {"inserted": inserted, "total_fetched": len(messages)}


@app.get("/learn-inbox-mails")
def learn_inbox_mails(request: Request, top: int = 50, skip: int = 0):
    token = request.session.get("access_token")
    if not token:
        return RedirectResponse("/login?next=/learn-inbox-mails")
    try:
        data = graph_get(token, "/me/mailFolders/inbox/messages", params={
            "$top": top, "$skip": skip, "$select": "id,subject,from,receivedDateTime,bodyPreview,toRecipients", "$orderby": "receivedDateTime DESC",
        })
    except requests.HTTPError:
        request.session.pop("access_token", None)
        return RedirectResponse("/login?next=/learn-inbox-mails")
    messages = data.get("value", [])
    inserted = skipped_noise = 0
    conn = None
    skip_keywords = ["noreply", "no-reply", "donotreply", "newsletter", "unsubscribe", "se désabonner",
                     "notification", "mailer-daemon", "marketing", "promo", "offre spéciale", "linkedin",
                     "twitter", "facebook", "instagram", "jobteaser", "indeed", "welcometothejungle",
                     "calendly", "zoom", "teams", "webinar", "webinaire", "satisfaction", "avis client", "enquête", "survey"]
    try:
        conn = get_pg_conn()
        c = conn.cursor()
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
                c.execute("INSERT INTO mail_memory (message_id, received_at, from_email, subject, raw_body_preview, analysis_status, created_at) VALUES (%s, %s, %s, %s, %s, %s, %s) ON CONFLICT (message_id) DO NOTHING",
                          (message_id, msg.get("receivedDateTime"), msg.get("from", {}).get("emailAddress", {}).get("address", ""),
                           msg.get("subject"), msg.get("bodyPreview"), "inbox_raw", datetime.utcnow().isoformat()))
                inserted += 1
            except Exception:
                continue
        conn.commit()
    finally:
        if conn:
            conn.close()
    return {"inserted": inserted, "skipped_noise": skipped_noise, "total_fetched": len(messages)}


@app.get("/build-style-profile")
def build_style_profile(request: Request):
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("SELECT subject, to_email, body_preview FROM sent_mail_memory ORDER BY sent_at DESC LIMIT 100")
        columns = [desc[0] for desc in c.description]
        rows = [dict(zip(columns, row)) for row in c.fetchall()]
    finally:
        if conn:
            conn.close()
    if not rows:
        return {"error": "Aucun mail envoyé en mémoire"}
    mails_text = "\n\n".join([f"Sujet : {r['subject']}\nDestinataire : {r['to_email']}\nContenu : {r['body_preview']}" for r in rows])
    response = client.messages.create(
        model=ANTHROPIC_MODEL_SMART, max_tokens=2048,
        messages=[{"role": "user", "content": f"Analyse ces {len(rows)} emails envoyés par Guillaume Perrin.\n\n{mails_text}\n\nProduis un profil détaillé de son style."}]
    )
    profile_text = response.content[0].text
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("DELETE FROM aria_profile WHERE profile_type = 'style'")
        c.execute("INSERT INTO aria_profile (profile_type, content) VALUES (%s, %s)", ('style', profile_text))
        conn.commit()
    finally:
        if conn:
            conn.close()
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
    if not code:
        return HTMLResponse("Code manquant", status_code=400)
    from app.connectors.gmail_connector import exchange_code_for_tokens
    tokens = exchange_code_for_tokens(code)
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("DELETE FROM gmail_tokens WHERE email = %s", ("per1.guillaume@gmail.com",))
        c.execute("INSERT INTO gmail_tokens (email, access_token, refresh_token) VALUES (%s, %s, %s)",
                  ("per1.guillaume@gmail.com", tokens.get("access_token"), tokens.get("refresh_token")))
        conn.commit()
    finally:
        if conn:
            conn.close()
    return {"status": "ok", "message": "Gmail connecté !"}


@app.get("/ingest-gmail")
def ingest_gmail(request: Request):
    from app.connectors.gmail_connector import gmail_get_messages, gmail_get_message, refresh_gmail_token
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("SELECT access_token, refresh_token FROM gmail_tokens WHERE email = %s", ("per1.guillaume@gmail.com",))
        row = c.fetchone()
    finally:
        if conn:
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
    conn = None
    try:
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
                c.execute("INSERT INTO mail_memory (message_id, received_at, from_email, subject, raw_body_preview, analysis_status, mailbox_source, created_at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT (message_id) DO NOTHING",
                          (message_id, date, from_email, subject, snippet, "gmail_raw", "gmail_perso", datetime.utcnow().isoformat()))
                inserted += 1
            except Exception:
                conn.rollback()
                continue
        conn.commit()
    finally:
        if conn:
            conn.close()
    return {"inserted": inserted, "total_fetched": len(messages)}


@app.get("/assistant-dashboard")
def assistant_dashboard(days: int = 2):
    return get_dashboard(days)


@app.get("/test-elevenlabs")
def test_elevenlabs():
    api_key = os.environ.get("ELEVENLABS_API_KEY", "")
    voice_id = os.environ.get("ELEVENLABS_VOICE_ID", "")
    resp = requests.post(f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
        headers={"xi-api-key": api_key, "Content-Type": "application/json"},
        json={"text": "Bonjour Guillaume.", "model_id": "eleven_flash_v2_5", "voice_settings": {"stability": 0.5, "similarity_boost": 0.8}},
        timeout=30)
    return {"status_code": resp.status_code, "api_key_length": len(api_key), "voice_id": voice_id}


@app.get("/test-odoo")
def test_odoo():
    from app.connectors.odoo_connector import perform_odoo_action
    return perform_odoo_action(action="get_partner_by_email", params={"email": "guillaume@couffrant-solar.fr"})


# ─── RÉORGANISATION SHAREPOINT ───

@app.get("/reorganize-drive")
def reorganize_drive():
    """
    Crée 1_Photovoltaïque_V2 dans SharePoint Commun avec une structure réorganisée.
    Copie tous les éléments de 1_Photovoltaïque vers les bons dossiers.
    Les originaux ne sont JAMAIS touchés.
    """
    import time
    from app.token_manager import get_valid_microsoft_token
    from app.connectors.outlook_connector import (
        _find_sharepoint_site_and_drive, _find_folder_item_id, _graph_get
    )

    token = get_valid_microsoft_token()
    if not token:
        return {"error": "Token Microsoft manquant — reconnectez-vous via /login"}

    _, drive_id, _ = _find_sharepoint_site_and_drive(token)
    if not drive_id:
        return {"error": "Drive SharePoint 'Commun' introuvable"}

    _, source_id = _find_folder_item_id(token, drive_id)
    if not source_id:
        return {"error": "Dossier 1_Photovoltaïque introuvable"}

    # Liste tous les éléments sources avec leurs IDs
    data = _graph_get(token, f"/drives/{drive_id}/items/{source_id}/children",
                     params={"$top": 100, "$select": "name,id,folder,file"})
    items_by_name = {f.get("name"): f.get("id") for f in data.get("value", [])}

    # Trouve le dossier parent (racine de la bibliothèque Documents)
    source_meta = _graph_get(token, f"/drives/{drive_id}/items/{source_id}",
                            params={"$select": "id,parentReference"})
    parent_id = source_meta.get("parentReference", {}).get("id")
    if not parent_id:
        return {"error": "Impossible de trouver le dossier parent de 1_Photovoltaïque"}

    log = []
    errors = []

    def make_folder(parent, name):
        r = create_drive_folder(token, parent, name, drive_id)
        if r.get("status") == "ok":
            log.append(f"✅ Dossier créé : {name}")
            return r.get("id")
        errors.append(f"❌ Dossier '{name}' : {r.get('message', '')[:80]}")
        return None

    def copy_item(source_name, dest_id, new_name=None):
        item_id = items_by_name.get(source_name)
        if not item_id:
            errors.append(f"⚠️ '{source_name}' introuvable dans la source")
            return
        r = copy_drive_item(token, item_id, dest_id, new_name, drive_id)
        label = new_name if new_name else source_name
        if r.get("status") == "ok":
            log.append(f"✅ Copie : {source_name} → {label}")
        else:
            errors.append(f"❌ Copie '{source_name}' : {r.get('message', '')[:80]}")

    # ── Étape 1 : Crée la racine V2 ──
    v2_id = make_folder(parent_id, "1_Photovoltaïque_V2")
    if not v2_id:
        return {"error": "Impossible de créer 1_Photovoltaïque_V2", "details": errors}
    time.sleep(1)

    # ── Étape 2 : Crée les 7 catégories ──
    cat01 = make_folder(v2_id, "01_Commercial")
    cat02 = make_folder(v2_id, "02_Chantiers")
    cat03 = make_folder(v2_id, "03_Administratif_Reglementaire")
    cat04 = make_folder(v2_id, "04_Documentation_Technique")
    cat05 = make_folder(v2_id, "05_Fournisseurs_Partenaires")
    cat06 = make_folder(v2_id, "06_Outils_et_Logiciels")
    cat07 = make_folder(v2_id, "07_RH_et_Stock")
    time.sleep(1)

    # ── Étape 3 : Copies — 01_Commercial ──
    if cat01:
        copy_item("1_1 Chiffrage Particulier", cat01, "Chiffrage_Particuliers")
        copy_item("1_Chiffrage Pro", cat01, "Chiffrage_Pro")

    # ── Étape 4 : Copies — 02_Chantiers ──
    if cat02:
        copy_item("Pilotage", cat02)
        copy_item("1_SUIVI CHANTIER PV modifié.xlsm", cat02)
        copy_item("Photo vidéo chantier en cours", cat02, "Photos_et_Videos")
        copy_item("Photos drone", cat02, "Photos_Drone")

    # ── Étape 5 : Copies — 03_Administratif ──
    if cat03:
        copy_item("2_CONSUEL", cat03, "CONSUEL")
        copy_item("3_ENEDIS", cat03, "ENEDIS")
        copy_item("4_Demandes DP Cerfa et Raccordement", cat03, "Demandes_DP")
        copy_item("Procédure d'aide EDF OA.docx", cat03)

    # ── Étape 6 : Copies — 04_Documentation ──
    if cat04:
        copy_item("5_Document technique", cat04, "Docs_Techniques")
        copy_item("Normes", cat04)
        copy_item("Import ELEC", cat04)
        copy_item("6_Audits et rapports", cat04, "Audits")
        copy_item("DOE_Couffrant_Solar_Complet_Modele.docx", cat04)
        copy_item("DOE_Couffrant_Solar_Modele_Reutilisable.docx", cat04)
        copy_item("DOE_Photovoltaique_Couffrant_Solar_Complet.docx", cat04)
        copy_item("PV fin de chantier.docx", cat04)
        copy_item("RAPPORT AUDIT PV.docx", cat04)

    # ── Étape 7 : Copies — 05_Fournisseurs ──
    if cat05:
        copy_item("Adiwatt", cat05)
        copy_item("MADENR", cat05)
        copy_item("Urban Solar", cat05)
        copy_item("Powr Connect", cat05)
        copy_item("formulaire compensation solaredge.pdf", cat05)
        copy_item("Demande garantie Onduleur 1 \u2013 Copie.xlsx", cat05)
        copy_item("Demande garantie Onduleur.xlsx", cat05)

    # ── Étape 8 : Copies — 06_Outils ──
    if cat06:
        copy_item("Formation archelios calc", cat06)
        copy_item("sauvegarde Archelios", cat06)
        copy_item("Logiciels", cat06)
        copy_item("unnamed.png", cat06)

    # ── Étape 9 : Copies — 07_RH_Stock ──
    if cat07:
        copy_item("Certificats et Formations Professionnels", cat07)
        copy_item("8_Stock 2026.ods", cat07)
        copy_item("Suivi panneau publicitaire.xlsx", cat07)

    return {
        "status": "ok",
        "message": f"Réorganisation lancée : {len(log)} succès, {len(errors)} erreurs.",
        "dossier_cree": "1_Photovoltaïque_V2",
        "note": "Les copies sont asynchrones — attendre 2-5 min que SharePoint termine. Les originaux sont intacts.",
        "log": log,
        "errors": errors if errors else "Aucune erreur.",
    }
