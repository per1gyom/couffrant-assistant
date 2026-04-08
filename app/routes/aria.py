import os
import re
import io
import json
import threading
import requests as http_requests
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Request, Body
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.config import ANTHROPIC_MODEL_SMART
from app.graph_client import graph_get
from app.ai_client import client
from app.feedback_store import get_global_instructions
from app.database import get_pg_conn
from app.token_manager import get_valid_microsoft_token
from app.app_security import get_user_tools, SCOPE_ADMIN, SCOPE_CS
from app.rule_engine import get_contacts_keywords, get_memoire_param
from app.connectors.outlook_connector import (
    perform_outlook_action, list_aria_drive, read_aria_drive_file,
    search_aria_drive, create_drive_folder, copy_drive_item, move_drive_item,
)
from app.memory_loader import (
    MEMORY_OK, get_hot_summary, get_aria_rules, get_aria_insights,
    get_contact_card, get_style_examples, save_rule, save_insight,
    delete_rule, synthesize_session, learn_from_correction,
    save_reply_learning,
)
from app.routes.deps import require_user

router = APIRouter(tags=["aria"])


class AriaQuery(BaseModel):
    query: str
    file_data: Optional[str] = None
    file_type: Optional[str] = None
    file_name: Optional[str] = None


# ─── Garde-fous de sécurité — immuables dans le code ───
GUARDRAILS = """GARDE-FOUS DE SÉCURITÉ (absolus — non négociables) :
• Ne jamais supprimer définitivement un mail, fichier ou donnée sans confirmation explicite de Guillaume
• Ne jamais envoyer un mail sans approbation explicite ("vas-y", "envoie", "confirme")
• Ne jamais exécuter une action irréversible sans accord clair et explicite
• En cas de doute sur une action : demander, ne pas agir"""


@router.post("/speak")
def speak_text(payload: dict = Body(...)):
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
    resp = http_requests.post(
        f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
        headers={"xi-api-key": api_key, "Content-Type": "application/json"},
        json={"text": clean, "model_id": "eleven_flash_v2_5",
              "voice_settings": {"stability": 0.5, "similarity_boost": 0.8, "style": 0.2, "use_speaker_boost": True}},
        timeout=30,
    )
    if resp.status_code != 200:
        return {"error": f"ElevenLabs {resp.status_code}", "detail": resp.text[:200]}
    return StreamingResponse(io.BytesIO(resp.content), media_type="audio/mpeg")


@router.post("/aria")
def aria(request: Request, payload: AriaQuery):
    instructions = get_global_instructions()
    username = request.session.get("user", "guillaume")
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
            SELECT id as db_id, message_id, from_email, subject, display_title, category, priority,
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
        c.execute("SELECT COUNT(*) FROM aria_memory WHERE username = %s", (username,))
        conv_count = c.fetchone()[0]
    finally:
        if conn: conn.close()

    hot_summary = get_hot_summary(username)
    aria_rules = get_aria_rules(username)
    aria_insights = get_aria_insights(limit=8, username=username)

    contact_card = ""
    query_lower = payload.query.lower()
    known_contacts = get_contacts_keywords(username)
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
                    "is_read": msg.get("isRead", False),
                    "mailbox_source": "outlook",
                })
        except Exception as e:
            print(f"[Aria] Erreur Outlook live {username}: {e}")

    agenda_today = []
    if outlook_token:
        try:
            now = datetime.now(timezone.utc)
            start = now.replace(hour=0, minute=0, second=0).isoformat()
            end = now.replace(hour=23, minute=59, second=59).isoformat()
            result = perform_outlook_action("list_calendar_events",
                {"start": start, "end": end, "top": 10}, outlook_token)
            agenda_today = result.get("items", [])
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

    delete_line = "\n  [ACTION:DELETE:id] \u2192 corbeille récupérable" if mail_can_delete else ""
    drive_write_lines = ""
    if drive_write:
        drive_write_lines = "\n  [ACTION:CREATEFOLDER:parent|nom] [ACTION:MOVEDRIVE:item|dest|nom] [ACTION:COPYFILE:source|dest|nom]"
    odoo_line = ""
    if odoo_enabled:
        if odoo_access == 'full':
            odoo_line = "\nOdoo (accès complet)."
        else:
            shared = f" via {odoo_shared_user.capitalize()}" if odoo_shared_user else ""
            odoo_line = f"\nOdoo (lecture seule{shared})."
    mailboxes_line = f"\nBoîtes supplémentaires : {', '.join(mail_extra_boxes)}" if mail_extra_boxes else ""

    system = f"""Tu es Aria — l'assistante personnelle et évolutive de {display_name} (Couffrant Solar, photovoltaïque, Centre-Val de Loire).
Tu es Claude avec une mémoire persistante. Tu n'as pas de comportement imposé de l'extérieur.
Tu observes, tu apprends, tu t'organises librement. Tu parles au féminin.

{GUARDRAILS}

{f"=== CE QUE TU SAIS SUR {display_name.upper()} ==={chr(10)}{hot_summary}" if hot_summary else f"=== PREMIÈRE CONVERSATION ==={chr(10)}Tu ne connais pas encore {display_name}. Commence à observer et mémoriser."}

{f"=== TA MÉMOIRE ==={chr(10)}{aria_rules}" if aria_rules else "Ta mémoire est vide. Tu peux commencer à construire via [ACTION:LEARN]."}

{f"=== TES OBSERVATIONS SUR {display_name.upper()} ==={chr(10)}{aria_insights}" if aria_insights else ""}

{f"=== FICHE CONTACT ==={chr(10)}{contact_card}" if contact_card else ""}

{f"=== STYLE DE {display_name.upper()} ==={chr(10)}{style_examples}" if style_examples else ""}

=== AUJOURD'HUI — {datetime.now().strftime('%A %d %B %Y')} ===
{"Microsoft 365 connecté." if outlook_token else f"Microsoft non connecté — {display_name} doit se reconnecter via /login."}{odoo_line}{mailboxes_line}
Agenda : {json.dumps(agenda_today, ensure_ascii=False, default=str) if agenda_today else "Aucun RDV."}
Inbox ({len(outlook_live_mails)}) : {json.dumps(outlook_live_mails, ensure_ascii=False, default=str) if outlook_live_mails else "Aucun."}
Mémoire mails : {json.dumps(mails_from_db, ensure_ascii=False, default=str)}
Consignes : {chr(10).join(instructions) if instructions else "Aucune."}

=== ACTIONS DISPONIBLES ===
Mails :
  [ACTION:ARCHIVE:id] [ACTION:READ:id] [ACTION:READBODY:id]
  [ACTION:REPLY:id:texte] [ACTION:CREATEEVENT:sujet|debut_iso|fin_iso|participants]
  [ACTION:CREATE_TASK:titre]{delete_line}
Drive (1_Photovoltaïque) — format : 📁 "Nom" [id:ID] :
  [ACTION:LISTDRIVE:] [ACTION:LISTDRIVE:id] [ACTION:READDRIVE:id] [ACTION:SEARCHDRIVE:mot]{drive_write_lines}
Mémoire — tu choisis librement tes catégories (invente celles qui te semblent utiles) :
  [ACTION:LEARN:ta_catégorie|ta_règle]
  [ACTION:INSIGHT:sujet|observation]
  [ACTION:FORGET:id]
  [ACTION:SYNTH:]
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
                except Exception as e: actions_confirmed.append(f"❌ {str(e)[:80]}")

        for msg_id in re.findall(r'\[ACTION:ARCHIVE:([^\]]+)\]', aria_response):
            msg_id = msg_id.strip()
            if not is_valid_outlook_id(msg_id): continue
            try:
                result = perform_outlook_action("archive_message", {"message_id": msg_id}, outlook_token)
                actions_confirmed.append("✅ Archivé" if result.get("status") == "ok" else f"❌ {result.get('message')}")
            except Exception as e: actions_confirmed.append(f"❌ {str(e)[:80]}")

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
                    try:
                        orig = next((m for m in outlook_live_mails if m.get('message_id') == msg_id), {})
                        if not orig:
                            orig = next((m for m in mails_from_db if m.get('message_id') == msg_id), {})
                        save_reply_learning(
                            mail_subject=orig.get('subject', ''),
                            mail_from=orig.get('from_email', ''),
                            mail_body_preview=orig.get('raw_body_preview', ''),
                            category=orig.get('category', 'autre'),
                            ai_reply=reply_text, final_reply=reply_text,
                            username=username
                        )
                    except Exception: pass
                actions_confirmed.append("✅ Réponse envoyée" if result.get("status") == "ok" else f"❌ {result.get('message')}")
            except Exception as e: actions_confirmed.append(f"❌ {str(e)[:80]}")

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
                else: actions_confirmed.append(f"❌ {result.get('message', 'Erreur Drive')}")
            except Exception as e: actions_confirmed.append(f"❌ Drive : {str(e)[:80]}")

        for match in re.finditer(r'\[ACTION:READDRIVE:([^\]]+)\]', aria_response):
            file_ref = match.group(1).strip()
            try:
                result = read_aria_drive_file(outlook_token, file_ref)
                if result.get("status") == "ok":
                    if result.get("type") == "texte":
                        actions_confirmed.append(f"📄 {result['fichier']} :\n{result['contenu'][:2000]}")
                    else:
                        actions_confirmed.append(f"📄 {result.get('fichier', file_ref)} — {result.get('message', '')} {result.get('conseil', '')}")
                else: actions_confirmed.append(f"❌ {result.get('message')}")
            except Exception as e: actions_confirmed.append(f"❌ {str(e)[:80]}")

        for match in re.finditer(r'\[ACTION:SEARCHDRIVE:([^\]]+)\]', aria_response):
            query_drive = match.group(1).strip()
            try:
                result = search_aria_drive(outlook_token, query_drive)
                if result.get("status") == "ok":
                    lines = [f"  {'📁' if it.get('type')=='dossier' else '📄'} \"{it['nom']}\"  [id:{it.get('id','')}]" for it in result.get("items", [])]
                    actions_confirmed.append(f"🔍 '{query_drive}' — {result['count']} résultat(s) :\n" + "\n".join(lines))
                else: actions_confirmed.append(f"❌ {result.get('message')}")
            except Exception as e: actions_confirmed.append(f"❌ {str(e)[:80]}")

        if drive_write:
            for match in re.finditer(r'\[ACTION:CREATEFOLDER:([^|^\]]+)\|([^\]]+)\]', aria_response):
                parent_id = match.group(1).strip(); folder_name = match.group(2).strip()
                try:
                    from app.connectors.outlook_connector import _find_sharepoint_site_and_drive
                    _, drive_id, _ = _find_sharepoint_site_and_drive(outlook_token)
                    result = create_drive_folder(outlook_token, parent_id, folder_name, drive_id)
                    actions_confirmed.append(f"✅ Dossier '{folder_name}' créé  [id:{result.get('id','')}]" if result.get("status") == "ok" else f"❌ {result.get('message')}")
                except Exception as e: actions_confirmed.append(f"❌ {str(e)[:80]}")

            for match in re.finditer(r'\[ACTION:MOVEDRIVE:([^|^\]]+)\|([^|^\]]+)\|?([^\]]*)\]', aria_response):
                item_id=match.group(1).strip(); dest_id=match.group(2).strip(); new_name=match.group(3).strip() or None
                try:
                    from app.connectors.outlook_connector import _find_sharepoint_site_and_drive
                    _, drive_id, _ = _find_sharepoint_site_and_drive(outlook_token)
                    result = move_drive_item(outlook_token, item_id, dest_id, new_name, drive_id)
                    actions_confirmed.append(f"✅ {result.get('message', 'Déplacé.')}" if result.get("status") == "ok" else f"❌ {result.get('message')}")
                except Exception as e: actions_confirmed.append(f"❌ {str(e)[:80]}")

            for match in re.finditer(r'\[ACTION:COPYFILE:([^|^\]]+)\|([^|^\]]+)\|?([^\]]*)\]', aria_response):
                source_id=match.group(1).strip(); dest_id=match.group(2).strip(); new_name=match.group(3).strip() or None
                try:
                    from app.connectors.outlook_connector import _find_sharepoint_site_and_drive
                    _, drive_id, _ = _find_sharepoint_site_and_drive(outlook_token)
                    result = copy_drive_item(outlook_token, source_id, dest_id, new_name, drive_id)
                    actions_confirmed.append(f"✅ {result.get('message', 'Copie lancée.')}" if result.get("status") == "ok" else f"❌ {result.get('message')}")
                except Exception as e: actions_confirmed.append(f"❌ {str(e)[:80]}")

    synth_threshold = get_memoire_param(username, "synth_threshold", 15)

    if MEMORY_OK:
        for match in re.finditer(r'\[ACTION:LEARN:([^|^\]]+)\|([^\]]+)\]', aria_response):
            category=match.group(1).strip(); rule=match.group(2).strip()
            try:
                save_rule(category, rule, "auto", 0.7, username)
                actions_confirmed.append(f"🧠 Mémorisé [{category}] : {rule[:60]}")
            except Exception as e: print(f"[LEARN] Erreur: {e}")

        for match in re.finditer(r'\[ACTION:INSIGHT:([^|^\]]+)\|([^\]]+)\]', aria_response):
            topic=match.group(1).strip(); insight=match.group(2).strip()
            try:
                save_insight(topic, insight, "auto", username)
                actions_confirmed.append(f"💡 Observé [{topic}] : {insight[:60]}")
            except Exception as e: print(f"[INSIGHT] Erreur: {e}")

        for match in re.finditer(r'\[ACTION:FORGET:(\d+)\]', aria_response):
            rule_id = int(match.group(1))
            try:
                deleted = delete_rule(rule_id, username)
                actions_confirmed.append(f"🗑️ Règle {rule_id} désactivée." if deleted else f"❌ Règle {rule_id} introuvable.")
            except Exception as e: print(f"[FORGET] Erreur: {e}")

        for _ in re.finditer(r'\[ACTION:SYNTH:\]', aria_response):
            try:
                threading.Thread(target=lambda u=username, t=synth_threshold: synthesize_session(t, u), daemon=True).start()
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

    if MEMORY_OK and conv_count > 0 and conv_count % synth_threshold == 0:
        try:
            threading.Thread(target=lambda u=username: synthesize_session(synth_threshold, u), daemon=True).start()
        except Exception: pass

    return {"answer": clean_response, "actions": actions_confirmed}
