"""
Exécution des actions Raya.
Parse la réponse de Claude et exécute les [ACTION:...] correspondants.
"""
import re
import threading

from app.connectors.outlook_connector import (
    perform_outlook_action, list_aria_drive, read_aria_drive_file,
    search_aria_drive, create_drive_folder, copy_drive_item, move_drive_item,
)
from app.connectors.teams_connector import (
    list_teams, list_channels, read_channel_messages,
    list_chats, read_chat_messages,
    send_channel_message, send_chat_message,
    send_message_to_user, create_group_chat,
)
from app.memory_loader import (
    MEMORY_OK, save_rule, save_insight, delete_rule,
    synthesize_session, learn_from_correction, save_reply_learning,
)
from app.rule_engine import get_memoire_param


def is_valid_outlook_id(msg_id: str) -> bool:
    return len(msg_id.strip()) > 20


def execute_actions(
    raya_response: str,
    username: str,
    outlook_token: str,
    mails_from_db: list,
    live_mails: list,
    tools: dict,
) -> list:
    """
    Exécute tous les [ACTION:...] trouvés dans la réponse de Raya.
    Retourne la liste des messages de confirmation.
    """
    confirmed = []
    drive_write = tools.get("drive_write", False)
    mail_can_delete = tools.get("mail_can_delete", False)
    synth_threshold = get_memoire_param(username, "synth_threshold", 15)

    if outlook_token:
        confirmed += _handle_mail_actions(raya_response, outlook_token, mail_can_delete,
                                          mails_from_db, live_mails, username)
        confirmed += _handle_drive_actions(raya_response, outlook_token, drive_write)
        confirmed += _handle_teams_actions(raya_response, outlook_token)

    if MEMORY_OK:
        confirmed += _handle_memory_actions(raya_response, username, synth_threshold)

    return confirmed


# ─── MAILS ───

def _handle_mail_actions(response, token, mail_can_delete, mails_from_db, live_mails, username):
    confirmed = []

    if mail_can_delete:
        for msg_id in re.findall(r'\[ACTION:DELETE:([^\]]+)\]', response):
            msg_id = msg_id.strip()
            if not is_valid_outlook_id(msg_id): continue
            try:
                r = perform_outlook_action("delete_message", {"message_id": msg_id}, token)
                confirmed.append("✅ Mis à la corbeille" if r.get("status") == "ok" else f"❌ {r.get('message')}")
            except Exception as e: confirmed.append(f"❌ {str(e)[:80]}")

    for msg_id in re.findall(r'\[ACTION:ARCHIVE:([^\]]+)\]', response):
        msg_id = msg_id.strip()
        if not is_valid_outlook_id(msg_id): continue
        try:
            r = perform_outlook_action("archive_message", {"message_id": msg_id}, token)
            confirmed.append("✅ Archivé" if r.get("status") == "ok" else f"❌ {r.get('message')}")
        except Exception as e: confirmed.append(f"❌ {str(e)[:80]}")

    for msg_id in re.findall(r'\[ACTION:READ:([^\]]+)\]', response):
        msg_id = msg_id.strip()
        if not is_valid_outlook_id(msg_id): continue
        try: perform_outlook_action("mark_as_read", {"message_id": msg_id}, token)
        except Exception: pass

    for match in re.finditer(r'\[ACTION:REPLY:([^:\]]{20,}):(.+?)\]', response, re.DOTALL):
        msg_id = match.group(1).strip(); reply_text = match.group(2).strip()
        if not is_valid_outlook_id(msg_id): continue
        try:
            r = perform_outlook_action("send_reply", {"message_id": msg_id, "reply_body": reply_text}, token)
            if r.get("status") == "ok":
                try: learn_from_correction(original="", corrected=reply_text, context="réponse mail", username=username)
                except Exception: pass
                try:
                    orig = next((m for m in live_mails if m.get('message_id') == msg_id), {})
                    if not orig:
                        orig = next((m for m in mails_from_db if m.get('message_id') == msg_id), {})
                    save_reply_learning(
                        mail_subject=orig.get('subject', ''), mail_from=orig.get('from_email', ''),
                        mail_body_preview=orig.get('raw_body_preview', ''), category=orig.get('category', 'autre'),
                        ai_reply=reply_text, final_reply=reply_text, username=username
                    )
                except Exception: pass
            confirmed.append("✅ Réponse envoyée" if r.get("status") == "ok" else f"❌ {r.get('message')}")
        except Exception as e: confirmed.append(f"❌ {str(e)[:80]}")

    for msg_id in re.findall(r'\[ACTION:READBODY:([^\]]+)\]', response):
        msg_id = msg_id.strip()
        if not is_valid_outlook_id(msg_id): continue
        try:
            r = perform_outlook_action("get_message_body", {"message_id": msg_id}, token)
            if r.get("status") == "ok":
                confirmed.append(f"📧 Corps du mail :\n{r.get('body_text', '')[:800]}")
        except Exception: pass

    for match in re.finditer(r'\[ACTION:CREATEEVENT:([^\]]+)\]', response):
        parts = match.group(1).split('|')
        if len(parts) >= 3:
            try:
                attendees = parts[3].split(',') if len(parts) > 3 else []
                r = perform_outlook_action("create_calendar_event",
                    {"subject": parts[0], "start": parts[1], "end": parts[2], "attendees": attendees}, token)
                confirmed.append("✅ RDV créé" if r.get("status") == "ok" else "❌ RDV échoué")
            except Exception: pass

    for title in re.findall(r'\[ACTION:CREATE_TASK:([^\]]+)\]', response):
        try: perform_outlook_action("create_todo_task", {"title": title.strip()}, token)
        except Exception: pass

    return confirmed


# ─── DRIVE ───

def _handle_drive_actions(response, token, drive_write):
    confirmed = []

    for match in re.finditer(r'\[ACTION:LISTDRIVE:([^\]]*)\]', response):
        subfolder = match.group(1).strip()
        try:
            r = list_aria_drive(token, subfolder)
            if r.get("status") == "ok":
                lines = []
                for it in r.get("items", []):
                    icon = "📁" if it.get("type") == "dossier" else "📄"
                    size_str = f"  ({it.get('taille_ko','')} Ko)" if it.get("taille_ko") else ""
                    lines.append(f"  {icon} \"{it['nom']}\"  [id:{it.get('id','')}]{size_str}")
                confirmed.append(f"📂 {r.get('dossier', '1_Photovoltaïque')} ({r['count']}) :\n" + "\n".join(lines))
            else: confirmed.append(f"❌ {r.get('message', 'Erreur Drive')}")
        except Exception as e: confirmed.append(f"❌ Drive : {str(e)[:80]}")

    for match in re.finditer(r'\[ACTION:READDRIVE:([^\]]+)\]', response):
        file_ref = match.group(1).strip()
        try:
            r = read_aria_drive_file(token, file_ref)
            if r.get("status") == "ok":
                if r.get("type") == "texte":
                    confirmed.append(f"📄 {r['fichier']} :\n{r['contenu'][:2000]}")
                else:
                    confirmed.append(f"📄 {r.get('fichier', file_ref)} — {r.get('message', '')} {r.get('conseil', '')}")
            else: confirmed.append(f"❌ {r.get('message')}")
        except Exception as e: confirmed.append(f"❌ {str(e)[:80]}")

    for match in re.finditer(r'\[ACTION:SEARCHDRIVE:([^\]]+)\]', response):
        q = match.group(1).strip()
        try:
            r = search_aria_drive(token, q)
            if r.get("status") == "ok":
                lines = [f"  {'📁' if it.get('type')=='dossier' else '📄'} \"{it['nom']}\"  [id:{it.get('id','')}]" for it in r.get("items", [])]
                confirmed.append(f"🔍 '{q}' — {r['count']} résultat(s) :\n" + "\n".join(lines))
            else: confirmed.append(f"❌ {r.get('message')}")
        except Exception as e: confirmed.append(f"❌ {str(e)[:80]}")

    if drive_write:
        for match in re.finditer(r'\[ACTION:CREATEFOLDER:([^|^\]]+)\|([^\]]+)\]', response):
            parent_id = match.group(1).strip(); folder_name = match.group(2).strip()
            try:
                from app.connectors.outlook_connector import _find_sharepoint_site_and_drive
                _, drive_id, _ = _find_sharepoint_site_and_drive(token)
                r = create_drive_folder(token, parent_id, folder_name, drive_id)
                confirmed.append(f"✅ Dossier '{folder_name}' créé  [id:{r.get('id','')}]" if r.get("status") == "ok" else f"❌ {r.get('message')}")
            except Exception as e: confirmed.append(f"❌ {str(e)[:80]}")

        for match in re.finditer(r'\[ACTION:MOVEDRIVE:([^|^\]]+)\|([^|^\]]+)\|?([^\]]*)\]', response):
            item_id = match.group(1).strip(); dest_id = match.group(2).strip(); new_name = match.group(3).strip() or None
            try:
                from app.connectors.outlook_connector import _find_sharepoint_site_and_drive
                _, drive_id, _ = _find_sharepoint_site_and_drive(token)
                r = move_drive_item(token, item_id, dest_id, new_name, drive_id)
                confirmed.append(f"✅ {r.get('message', 'Déplacé.')}" if r.get("status") == "ok" else f"❌ {r.get('message')}")
            except Exception as e: confirmed.append(f"❌ {str(e)[:80]}")

        for match in re.finditer(r'\[ACTION:COPYFILE:([^|^\]]+)\|([^|^\]]+)\|?([^\]]*)\]', response):
            source_id = match.group(1).strip(); dest_id = match.group(2).strip(); new_name = match.group(3).strip() or None
            try:
                from app.connectors.outlook_connector import _find_sharepoint_site_and_drive
                _, drive_id, _ = _find_sharepoint_site_and_drive(token)
                r = copy_drive_item(token, source_id, dest_id, new_name, drive_id)
                confirmed.append(f"✅ {r.get('message', 'Copie lancée.')}" if r.get("status") == "ok" else f"❌ {r.get('message')}")
            except Exception as e: confirmed.append(f"❌ {str(e)[:80]}")

    return confirmed


# ─── TEAMS ───

def _handle_teams_actions(response, token):
    confirmed = []

    for _ in re.finditer(r'\[ACTION:TEAMS_LIST:\]', response):
        try:
            res = list_teams(token)
            if res.get("status") == "ok":
                lines = []
                for t in res.get("teams", []):
                    ch = list_channels(token, t["id"])
                    ch_names = ", ".join(c["name"] for c in ch.get("channels", [])[:5]) if ch.get("status") == "ok" else "—"
                    lines.append(f"  🏢 {t['name']} [id:{t['id']}]\n     Canaux : {ch_names or '—'}")
                confirmed.append(f"📋 Teams ({res['count']}) :\n" + "\n".join(lines))
            else: confirmed.append(f"❌ Teams : {res.get('message')}")
        except Exception as e: confirmed.append(f"❌ Teams : {str(e)[:80]}")

    for match in re.finditer(r'\[ACTION:TEAMS_CHANNEL:([^|\]]+)\|([^\]]+)\]', response):
        team_id = match.group(1).strip(); channel_id = match.group(2).strip()
        try:
            res = read_channel_messages(token, team_id, channel_id)
            if res.get("status") == "ok":
                lines = [f"  [{m['date'][:10]}] {m['sender']} : {m['content'][:120]}" for m in res.get("messages", [])]
                confirmed.append(f"💬 Canal ({res['count']}) :\n" + "\n".join(lines))
            else: confirmed.append(f"❌ Canal : {res.get('message')}")
        except Exception as e: confirmed.append(f"❌ Canal : {str(e)[:80]}")

    for _ in re.finditer(r'\[ACTION:TEAMS_CHATS:\]', response):
        try:
            res = list_chats(token)
            if res.get("status") == "ok":
                lines = [f"  {'👤' if c['type']=='oneOnOne' else '👥'} {c['topic']} [id:{c['id'][:20]}...]" for c in res.get("chats", [])]
                confirmed.append(f"💬 Chats Teams ({res['count']}) :\n" + "\n".join(lines))
            else: confirmed.append(f"❌ Chats : {res.get('message')}")
        except Exception as e: confirmed.append(f"❌ Chats : {str(e)[:80]}")

    for match in re.finditer(r'\[ACTION:TEAMS_READCHAT:([^\]]+)\]', response):
        chat_id = match.group(1).strip()
        try:
            res = read_chat_messages(token, chat_id)
            if res.get("status") == "ok":
                lines = [f"  [{m['date'][:10]}] {m['sender']} : {m['content'][:150]}" for m in res.get("messages", [])]
                confirmed.append(f"💬 Chat ({res['count']}) :\n" + "\n".join(lines))
            else: confirmed.append(f"❌ Chat : {res.get('message')}")
        except Exception as e: confirmed.append(f"❌ Chat : {str(e)[:80]}")

    for match in re.finditer(r'\[ACTION:TEAMS_MSG:([^|\]]+)\|(.+?)\]', response, re.DOTALL):
        email = match.group(1).strip(); text = match.group(2).strip()
        try:
            res = send_message_to_user(token, email, text)
            confirmed.append(res.get("message", "✅ Message Teams envoyé.") if res.get("status") == "ok" else f"❌ {res.get('message')}")
        except Exception as e: confirmed.append(f"❌ Teams MSG : {str(e)[:80]}")

    for match in re.finditer(r'\[ACTION:TEAMS_REPLYCHAT:([^|\]]+)\|(.+?)\]', response, re.DOTALL):
        chat_id = match.group(1).strip(); text = match.group(2).strip()
        try:
            res = send_chat_message(token, chat_id, text)
            confirmed.append("✅ Réponse Teams envoyée." if res.get("status") == "ok" else f"❌ {res.get('message')}")
        except Exception as e: confirmed.append(f"❌ Teams reply : {str(e)[:80]}")

    for match in re.finditer(r'\[ACTION:TEAMS_SENDCHANNEL:([^|\]]+)\|([^|\]]+)\|(.+?)\]', response, re.DOTALL):
        team_id = match.group(1).strip(); channel_id = match.group(2).strip(); text = match.group(3).strip()
        try:
            res = send_channel_message(token, team_id, channel_id, text)
            confirmed.append("✅ Message canal Teams envoyé." if res.get("status") == "ok" else f"❌ {res.get('message')}")
        except Exception as e: confirmed.append(f"❌ Teams canal : {str(e)[:80]}")

    for match in re.finditer(r'\[ACTION:TEAMS_GROUPE:([^|\]]+)\|([^|\]]+)\|(.+?)\]', response, re.DOTALL):
        emails_raw = match.group(1).strip(); topic = match.group(2).strip(); text = match.group(3).strip()
        emails = [e.strip() for e in emails_raw.split(',') if e.strip()]
        try:
            res = create_group_chat(token, emails, topic, text)
            confirmed.append(res.get("message", "✅ Groupe Teams créé.") if res.get("status") == "ok" else f"❌ {res.get('message')}")
        except Exception as e: confirmed.append(f"❌ Teams groupe : {str(e)[:80]}")

    return confirmed


# ─── MÉMOIRE ───

def _handle_memory_actions(response, username, synth_threshold):
    confirmed = []

    for match in re.finditer(r'\[ACTION:LEARN:([^|^\]]+)\|([^\]]+)\]', response):
        category = match.group(1).strip(); rule = match.group(2).strip()
        try:
            save_rule(category, rule, "auto", 0.7, username)
            confirmed.append(f"🧠 Mémorisé [{category}] : {rule[:60]}")
        except Exception as e: print(f"[LEARN] Erreur: {e}")

    for match in re.finditer(r'\[ACTION:INSIGHT:([^|^\]]+)\|([^\]]+)\]', response):
        topic = match.group(1).strip(); insight = match.group(2).strip()
        try:
            save_insight(topic, insight, "auto", username)
            confirmed.append(f"💡 Observé [{topic}] : {insight[:60]}")
        except Exception as e: print(f"[INSIGHT] Erreur: {e}")

    for match in re.finditer(r'\[ACTION:FORGET:(\d+)\]', response):
        rule_id = int(match.group(1))
        try:
            deleted = delete_rule(rule_id, username)
            confirmed.append(f"🗑️ Règle {rule_id} désactivée." if deleted else f"❌ Règle {rule_id} introuvable.")
        except Exception as e: print(f"[FORGET] Erreur: {e}")

    for _ in re.finditer(r'\[ACTION:SYNTH:\]', response):
        try:
            threading.Thread(target=lambda u=username, t=synth_threshold: synthesize_session(t, u), daemon=True).start()
            confirmed.append("🔄 Synthèse lancée en arrière-plan.")
        except Exception as e: print(f"[SYNTH] Erreur: {e}")

    return confirmed
