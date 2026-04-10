"""
Exécution des actions Raya.
Parse la réponse de Claude et exécute les [ACTION:...] correspondants.

Actions sensibles (REPLY, DELETE, TEAMS_MSG, MOVEDRIVE, COPYFILE, CREATEEVENT)
→ mises en queue via pending_actions.py, jamais exécutées directement.
Actions sûres (READ, ARCHIVE, LISTDRIVE, LEARN...) → exécution immédiate.
"""
import re
import threading

from app.connectors.outlook_connector import perform_outlook_action
from app.connectors.drive_connector import (
    list_drive, read_drive_file, search_drive,
    create_folder, move_item, copy_item,
    _find_sharepoint_site_and_drive,
)
from app.connectors.teams_connector import (
    list_teams_with_channels, list_channels, read_channel_messages,
    list_chats, read_chat_messages,
    send_channel_message, send_chat_message,
    send_message_to_user, create_group_chat,
)
from app.memory_loader import (
    MEMORY_OK, save_rule, save_insight, delete_rule,
    synthesize_session, learn_from_correction, save_reply_learning,
)
from app.rule_engine import get_memoire_param
from app.pending_actions import (
    queue_action, confirm_action, cancel_action,
    mark_executed, mark_failed, is_sensitive,
)


def is_valid_outlook_id(msg_id: str) -> bool:
    return len(msg_id.strip()) > 20


def execute_actions(
    raya_response: str,
    username: str,
    outlook_token: str,
    mails_from_db: list,
    live_mails: list,
    tools: dict,
    tenant_id: str = "couffrant_solar",
    conversation_id: int = None,
) -> list:
    confirmed = []
    drive_write = tools.get("drive_write", False)
    mail_can_delete = tools.get("mail_can_delete", False)
    synth_threshold = get_memoire_param(username, "synth_threshold", 15)

    # 1. Traiter CONFIRM/CANCEL générés par Raya
    confirmed += _handle_confirmations(raya_response, username, tenant_id, outlook_token, tools)

    if outlook_token:
        confirmed += _handle_mail_actions(
            raya_response, outlook_token, mail_can_delete,
            mails_from_db, live_mails, username, tenant_id, conversation_id
        )
        confirmed += _handle_drive_actions(
            raya_response, outlook_token, drive_write, username, tenant_id, conversation_id
        )
        confirmed += _handle_teams_actions(
            raya_response, outlook_token, username, tenant_id, conversation_id
        )

    if MEMORY_OK:
        confirmed += _handle_memory_actions(raya_response, username, synth_threshold)

    return confirmed


# ─── CONFIRMATIONS / ANNULATIONS ───

def _handle_confirmations(response, username, tenant_id, outlook_token, tools):
    """
    Traite les [ACTION:CONFIRM:id] et [ACTION:CANCEL:id] générés par Raya.
    Quand Guillaume dit "vas-y", Raya répond avec CONFIRM qui exécute l'action en queue.
    """
    confirmed = []

    for match in re.finditer(r'\[ACTION:CONFIRM:(\d+)\]', response):
        action_id = int(match.group(1))
        action = confirm_action(action_id, username, tenant_id)
        if not action:
            confirmed.append(f"❌ Action {action_id} introuvable, déjà traitée ou expirée.")
            continue
        result = _execute_confirmed_action(action, outlook_token, tools)
        if result.get("ok"):
            mark_executed(action_id, result)
            confirmed.append(f"✅ {result.get('message', 'Action exécutée')}")
        else:
            mark_failed(action_id, result.get("error", "erreur inconnue"))
            confirmed.append(f"❌ Échec : {result.get('error', 'erreur inconnue')}")

    for match in re.finditer(r'\[ACTION:CANCEL:(\d+)\]', response):
        action_id = int(match.group(1))
        ok = cancel_action(action_id, username, tenant_id, reason="Annulé par l'utilisateur")
        confirmed.append(
            f"?ude45 Action {action_id} annulée." if ok
            else f"❌ Action {action_id} introuvable."
        )

    return confirmed


def _execute_confirmed_action(action: dict, outlook_token: str, tools: dict) -> dict:
    """Exécute effectivement une action confirmée. Retourne {ok, message} ou {ok: False, error}."""
    action_type = action["action_type"]
    payload = action["payload"]

    try:
        if action_type == "REPLY":
            r = perform_outlook_action("send_reply", {
                "message_id": payload["message_id"],
                "reply_body": payload["reply_text"],
            }, outlook_token)
            return {"ok": r.get("status") == "ok", "message": "Réponse envoyée",
                    "error": r.get("message", "envoi échoué")}

        if action_type == "DELETE":
            if not tools.get("mail_can_delete"):
                return {"ok": False, "error": "Suppression mail non autorisée"}
            r = perform_outlook_action("delete_message", {"message_id": payload["message_id"]}, outlook_token)
            return {"ok": r.get("status") == "ok", "message": "Mis à la corbeille",
                    "error": r.get("message", "suppression échouée")}

        if action_type == "TEAMS_MSG":
            r = send_message_to_user(outlook_token, payload["email"], payload["text"])
            return {"ok": r.get("status") == "ok", "message": r.get("message", "Message Teams envoyé"),
                    "error": r.get("message", "envoi échoué")}

        if action_type == "TEAMS_REPLYCHAT":
            r = send_chat_message(outlook_token, payload["chat_id"], payload["text"])
            return {"ok": r.get("status") == "ok", "message": "Réponse Teams envoyée",
                    "error": r.get("message", "envoi échoué")}

        if action_type == "TEAMS_SENDCHANNEL":
            r = send_channel_message(outlook_token, payload["team_id"], payload["channel_id"], payload["text"])
            return {"ok": r.get("status") == "ok", "message": "Message canal Teams envoyé",
                    "error": r.get("message", "envoi échoué")}

        if action_type == "TEAMS_GROUPE":
            r = create_group_chat(outlook_token, payload["emails"], payload["topic"], payload["text"])
            return {"ok": r.get("status") == "ok", "message": r.get("message", "Groupe Teams créé"),
                    "error": r.get("message", "création échouée")}

        if action_type == "MOVEDRIVE":
            if not tools.get("drive_write"):
                return {"ok": False, "error": "Écriture Drive non autorisée"}
            _, drive_id, _ = _find_sharepoint_site_and_drive(outlook_token)
            r = move_item(outlook_token, payload["item_id"], payload["dest_id"],
                          payload.get("new_name"), drive_id)
            return {"ok": r.get("status") == "ok", "message": r.get("message", "Déplacé"),
                    "error": r.get("message", "déplacement échoué")}

        if action_type == "COPYFILE":
            if not tools.get("drive_write"):
                return {"ok": False, "error": "Écriture Drive non autorisée"}
            _, drive_id, _ = _find_sharepoint_site_and_drive(outlook_token)
            r = copy_item(outlook_token, payload["source_id"], payload["dest_id"],
                          payload.get("new_name"), drive_id)
            return {"ok": r.get("status") == "ok", "message": r.get("message", "Copie lancée"),
                    "error": r.get("message", "copie échouée")}

        if action_type == "CREATEEVENT":
            r = perform_outlook_action("create_calendar_event", {
                "subject": payload["subject"],
                "start": payload["start"],
                "end": payload["end"],
                "attendees": payload.get("attendees", []),
            }, outlook_token)
            return {"ok": r.get("status") == "ok", "message": "RDV créé",
                    "error": r.get("message", "création RDV échouée")}

        return {"ok": False, "error": f"Type d'action inconnu : {action_type}"}

    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


# ─── MAILS ───

def _handle_mail_actions(response, token, mail_can_delete, mails_from_db, live_mails,
                         username, tenant_id, conversation_id):
    confirmed = []
    all_mails = live_mails + mails_from_db

    # DELETE → queue (sensible)
    if mail_can_delete:
        for msg_id in re.findall(r'\[ACTION:DELETE:([^\]]+)\]', response):
            msg_id = msg_id.strip()
            if not is_valid_outlook_id(msg_id):
                continue
            orig = next((m for m in all_mails if m.get('message_id') == msg_id), {})
            label = f"Supprimer : '{orig.get('subject', msg_id[:30])}'"
            aid = queue_action(tenant_id, username, "DELETE",
                               {"message_id": msg_id, "subject": orig.get('subject', '')},
                               label, conversation_id)
            confirmed.append(
                f"⏸️ Action #{aid} en attente : {label}\n"
                f"   Pour confirmer : [ACTION:CONFIRM:{aid}] · Pour annuler : [ACTION:CANCEL:{aid}]"
            )

    # ARCHIVE → immédiat (réversible)
    for msg_id in re.findall(r'\[ACTION:ARCHIVE:([^\]]+)\]', response):
        msg_id = msg_id.strip()
        if not is_valid_outlook_id(msg_id):
            continue
        try:
            r = perform_outlook_action("archive_message", {"message_id": msg_id}, token)
            confirmed.append("✅ Archivé" if r.get("status") == "ok" else f"❌ {r.get('message')}")
        except Exception as e:
            confirmed.append(f"❌ {str(e)[:80]}")

    # READ → immédiat (anodin)
    for msg_id in re.findall(r'\[ACTION:READ:([^\]]+)\]', response):
        msg_id = msg_id.strip()
        if not is_valid_outlook_id(msg_id):
            continue
        try:
            perform_outlook_action("mark_as_read", {"message_id": msg_id}, token)
        except Exception:
            pass

    # REPLY → queue (sensible)
    for match in re.finditer(r'\[ACTION:REPLY:([^:\]]{20,}):(.+?)\]', response, re.DOTALL):
        msg_id = match.group(1).strip()
        reply_text = match.group(2).strip()
        if not is_valid_outlook_id(msg_id):
            continue
        orig = next((m for m in all_mails if m.get('message_id') == msg_id), {})
        label = f"Répondre à '{orig.get('subject', msg_id[:30])}' ({orig.get('from_email', '?')})"
        aid = queue_action(tenant_id, username, "REPLY", {
            "message_id": msg_id, "reply_text": reply_text,
            "subject": orig.get('subject', ''), "to": orig.get('from_email', ''),
        }, label, conversation_id)
        preview = reply_text[:200] + ("..." if len(reply_text) > 200 else "")
        confirmed.append(
            f"⏸️ Action #{aid} en attente — Réponse à envoyer :\n"
            f"   À : {orig.get('from_email', '?')}\n"
            f"   Sujet : {orig.get('subject', '?')}\n"
            f"   Message : {preview}\n"
            f"   Pour envoyer : [ACTION:CONFIRM:{aid}] · Pour annuler : [ACTION:CANCEL:{aid}]"
        )

    # READBODY → immédiat (lecture)
    for msg_id in re.findall(r'\[ACTION:READBODY:([^\]]+)\]', response):
        msg_id = msg_id.strip()
        if not is_valid_outlook_id(msg_id):
            continue
        try:
            r = perform_outlook_action("get_message_body", {"message_id": msg_id}, token)
            if r.get("status") == "ok":
                confirmed.append(f"📧 Corps du mail :\n{r.get('body_text', '')[:800]}")
        except Exception:
            pass

    # CREATEEVENT → queue (envoi à des participants)
    for match in re.finditer(r'\[ACTION:CREATEEVENT:([^\]]+)\]', response):
        parts = match.group(1).split('|')
        if len(parts) >= 3:
            attendees = parts[3].split(',') if len(parts) > 3 else []
            label = f"Créer RDV '{parts[0]}' le {parts[1][:10]}"
            aid = queue_action(tenant_id, username, "CREATEEVENT", {
                "subject": parts[0], "start": parts[1], "end": parts[2], "attendees": attendees,
            }, label, conversation_id)
            confirmed.append(
                f"⏸️ Action #{aid} en attente : {label}\n"
                f"   Participants : {', '.join(attendees) if attendees else 'aucun'}\n"
                f"   Pour confirmer : [ACTION:CONFIRM:{aid}] · Pour annuler : [ACTION:CANCEL:{aid}]"
            )

    # CREATE_TASK → immédiat (anodin, dans son Todo privé)
    for title in re.findall(r'\[ACTION:CREATE_TASK:([^\]]+)\]', response):
        try:
            perform_outlook_action("create_todo_task", {"title": title.strip()}, token)
        except Exception:
            pass

    return confirmed


# ─── DRIVE ───

def _handle_drive_actions(response, token, drive_write, username, tenant_id, conversation_id):
    confirmed = []

    # LISTDRIVE → immédiat (lecture)
    for match in re.finditer(r'\[ACTION:LISTDRIVE:([^\]]*)\]', response):
        subfolder = match.group(1).strip()
        try:
            r = list_drive(token, subfolder)
            if r.get("status") == "ok":
                lines = []
                for it in r.get("items", []):
                    icon = "📁" if it.get("type") == "dossier" else "📄"
                    size_str = f"  ({it.get('taille_ko','')} Ko)" if it.get("taille_ko") else ""
                    link = it.get('lien', '')
                    if link:
                        lines.append(f"  {icon} [**{it['nom']}**]({link})  [id:{it.get('id','')}]{size_str}")
                    else:
                        lines.append(f"  {icon} **{it['nom']}**  [id:{it.get('id','')}]{size_str}")
                confirmed.append(f"📂 {r.get('dossier', '1_Photovoltaïque')} ({r['count']}) :\n" + "\n".join(lines))
            else:
                confirmed.append(f"❌ {r.get('message', 'Erreur Drive')}")
        except Exception as e:
            confirmed.append(f"❌ Drive : {str(e)[:80]}")

    # READDRIVE → immédiat (lecture)
    for match in re.finditer(r'\[ACTION:READDRIVE:([^\]]+)\]', response):
        file_ref = match.group(1).strip()
        try:
            r = read_drive_file(token, file_ref)
            if r.get("status") == "ok":
                if r.get("type") == "texte":
                    confirmed.append(f"📄 {r['fichier']} :\n{r['contenu'][:2000]}")
                else:
                    confirmed.append(f"📄 {r.get('fichier', file_ref)} — {r.get('message', '')} {r.get('conseil', '')}")
            else:
                confirmed.append(f"❌ {r.get('message')}")
        except Exception as e:
            confirmed.append(f"❌ {str(e)[:80]}")

    # SEARCHDRIVE → immédiat (lecture)
    for match in re.finditer(r'\[ACTION:SEARCHDRIVE:([^\]]+)\]', response):
        q = match.group(1).strip()
        try:
            r = search_drive(token, q)
            if r.get("status") == "ok":
                lines = []
                for it in r.get("items", []):
                    icon = "📁" if it.get("type") == "dossier" else "📄"
                    link = it.get('lien', '')
                    if link:
                        lines.append(f"  {icon} [**{it['nom']}**]({link})  [id:{it.get('id','')}]")
                    else:
                        lines.append(f"  {icon} **{it['nom']}**  [id:{it.get('id','')}]")
                confirmed.append(f"🔍 '{q}' — {r['count']} résultat(s) :\n" + "\n".join(lines))
            else:
                confirmed.append(f"❌ {r.get('message')}")
        except Exception as e:
            confirmed.append(f"❌ {str(e)[:80]}")

    if drive_write:
        # CREATEFOLDER → immédiat (réversible facile)
        for match in re.finditer(r'\[ACTION:CREATEFOLDER:([^|^\]]+)\|([^\]]+)\]', response):
            parent_id = match.group(1).strip()
            folder_name = match.group(2).strip()
            try:
                _, drive_id, _ = _find_sharepoint_site_and_drive(token)
                r = create_folder(token, parent_id, folder_name, drive_id)
                confirmed.append(
                    f"✅ Dossier '{folder_name}' créé  [id:{r.get('id','')}]" if r.get("status") == "ok"
                    else f"❌ {r.get('message')}"
                )
            except Exception as e:
                confirmed.append(f"❌ {str(e)[:80]}")

        # MOVEDRIVE → queue (peut perturber l'organisation Drive)
        for match in re.finditer(r'\[ACTION:MOVEDRIVE:([^|^\]]+)\|([^|^\]]+)\|?([^\]]*)\]', response):
            item_id = match.group(1).strip()
            dest_id = match.group(2).strip()
            new_name = match.group(3).strip() or None
            label = f"Déplacer item {item_id[:20]} vers {dest_id[:20]}"
            aid = queue_action(tenant_id, username, "MOVEDRIVE",
                               {"item_id": item_id, "dest_id": dest_id, "new_name": new_name},
                               label, conversation_id)
            confirmed.append(
                f"⏸️ Action #{aid} en attente : {label}\n"
                f"   Pour confirmer : [ACTION:CONFIRM:{aid}] · Pour annuler : [ACTION:CANCEL:{aid}]"
            )

        # COPYFILE → queue
        for match in re.finditer(r'\[ACTION:COPYFILE:([^|^\]]+)\|([^|^\]]+)\|?([^\]]*)\]', response):
            source_id = match.group(1).strip()
            dest_id = match.group(2).strip()
            new_name = match.group(3).strip() or None
            label = f"Copier {source_id[:20]} vers {dest_id[:20]}"
            aid = queue_action(tenant_id, username, "COPYFILE",
                               {"source_id": source_id, "dest_id": dest_id, "new_name": new_name},
                               label, conversation_id)
            confirmed.append(
                f"⏸️ Action #{aid} en attente : {label}\n"
                f"   Pour confirmer : [ACTION:CONFIRM:{aid}] · Pour annuler : [ACTION:CANCEL:{aid}]"
            )

    return confirmed


# ─── TEAMS ───

def _handle_teams_actions(response, token, username, tenant_id, conversation_id):
    confirmed = []

    # TEAMS_LIST → immédiat (lecture)
    for _ in re.finditer(r'\[ACTION:TEAMS_LIST:\]', response):
        try:
            res = list_teams_with_channels(token)
            if res.get("status") == "ok":
                lines = []
                for t in res.get("teams", []):
                    ch_names = ", ".join(c["name"] for c in t.get("channels", [])[:5]) or "—"
                    lines.append(f"  🏢 {t['name']} [id:{t['id']}]\n     Canaux : {ch_names}")
                confirmed.append(f"📋 Teams ({res['count']}) :\n" + "\n".join(lines))
            else:
                confirmed.append(f"❌ Teams : {res.get('message')}")
        except Exception as e:
            confirmed.append(f"❌ Teams : {str(e)[:80]}")

    # TEAMS_CHANNEL → immédiat (lecture)
    for match in re.finditer(r'\[ACTION:TEAMS_CHANNEL:([^|\]]+)\|([^\]]+)\]', response):
        team_id = match.group(1).strip()
        channel_id = match.group(2).strip()
        try:
            res = read_channel_messages(token, team_id, channel_id)
            if res.get("status") == "ok":
                lines = [f"  [{m['date'][:10]}] {m['sender']} : {m['content'][:120]}"
                         for m in res.get("messages", [])]
                confirmed.append(f"💬 Canal ({res['count']}) :\n" + "\n".join(lines))
            else:
                confirmed.append(f"❌ Canal : {res.get('message')}")
        except Exception as e:
            confirmed.append(f"❌ Canal : {str(e)[:80]}")

    # TEAMS_CHATS → immédiat (lecture)
    for _ in re.finditer(r'\[ACTION:TEAMS_CHATS:\]', response):
        try:
            res = list_chats(token)
            if res.get("status") == "ok":
                lines = [f"  {'\U0001f464' if c['type']=='oneOnOne' else '\U0001f465'} {c['topic']} [id:{c['id'][:20]}...]" for c in res.get("chats", [])]
                confirmed.append(f"💬 Chats Teams ({res['count']}) :\n" + "\n".join(lines))
            else:
                confirmed.append(f"❌ Chats : {res.get('message')}")
        except Exception as e:
            confirmed.append(f"❌ Chats : {str(e)[:80]}")

    # TEAMS_READCHAT → immédiat (lecture)
    for match in re.finditer(r'\[ACTION:TEAMS_READCHAT:([^\]]+)\]', response):
        chat_id = match.group(1).strip()
        try:
            res = read_chat_messages(token, chat_id)
            if res.get("status") == "ok":
                lines = [f"  [{m['date'][:10]}] {m['sender']} : {m['content'][:150]}"
                         for m in res.get("messages", [])]
                confirmed.append(f"💬 Chat ({res['count']}) :\n" + "\n".join(lines))
            else:
                confirmed.append(f"❌ Chat : {res.get('message')}")
        except Exception as e:
            confirmed.append(f"❌ Chat : {str(e)[:80]}")

    # TEAMS_MSG → queue (envoi sensible)
    for match in re.finditer(r'\[ACTION:TEAMS_MSG:([^|\]]+)\|(.+?)\]', response, re.DOTALL):
        email = match.group(1).strip()
        text = match.group(2).strip()
        label = f"Message Teams à {email}"
        aid = queue_action(tenant_id, username, "TEAMS_MSG",
                           {"email": email, "text": text}, label, conversation_id)
        preview = text[:150] + ("..." if len(text) > 150 else "")
        confirmed.append(
            f"⏸️ Action #{aid} en attente : {label}\n"
            f"   Message : {preview}\n"
            f"   Pour envoyer : [ACTION:CONFIRM:{aid}] · Pour annuler : [ACTION:CANCEL:{aid}]"
        )

    # TEAMS_REPLYCHAT → queue
    for match in re.finditer(r'\[ACTION:TEAMS_REPLYCHAT:([^|\]]+)\|(.+?)\]', response, re.DOTALL):
        chat_id = match.group(1).strip()
        text = match.group(2).strip()
        label = f"Répondre dans chat {chat_id[:20]}"
        aid = queue_action(tenant_id, username, "TEAMS_REPLYCHAT",
                           {"chat_id": chat_id, "text": text}, label, conversation_id)
        confirmed.append(
            f"⏸️ Action #{aid} en attente : {label}\n"
            f"   Pour envoyer : [ACTION:CONFIRM:{aid}] · Pour annuler : [ACTION:CANCEL:{aid}]"
        )

    # TEAMS_SENDCHANNEL → queue
    for match in re.finditer(r'\[ACTION:TEAMS_SENDCHANNEL:([^|\]]+)\|([^|\]]+)\|(.+?)\]', response, re.DOTALL):
        team_id = match.group(1).strip()
        channel_id = match.group(2).strip()
        text = match.group(3).strip()
        label = f"Message canal Teams"
        aid = queue_action(tenant_id, username, "TEAMS_SENDCHANNEL",
                           {"team_id": team_id, "channel_id": channel_id, "text": text},
                           label, conversation_id)
        confirmed.append(
            f"⏸️ Action #{aid} en attente : {label}\n"
            f"   Pour envoyer : [ACTION:CONFIRM:{aid}] · Pour annuler : [ACTION:CANCEL:{aid}]"
        )

    # TEAMS_GROUPE → queue
    for match in re.finditer(r'\[ACTION:TEAMS_GROUPE:([^|\]]+)\|([^|\]]+)\|(.+?)\]', response, re.DOTALL):
        emails_raw = match.group(1).strip()
        topic = match.group(2).strip()
        text = match.group(3).strip()
        emails = [e.strip() for e in emails_raw.split(',') if e.strip()]
        label = f"Créer groupe Teams '{topic}'"
        aid = queue_action(tenant_id, username, "TEAMS_GROUPE",
                           {"emails": emails, "topic": topic, "text": text},
                           label, conversation_id)
        confirmed.append(
            f"⏸️ Action #{aid} en attente : {label}\n"
            f"   Pour confirmer : [ACTION:CONFIRM:{aid}] · Pour annuler : [ACTION:CANCEL:{aid}]"
        )

    # Mémoire Teams (Raya décide librement) → immédiat
    for match in re.finditer(r'\[ACTION:TEAMS_MARK:([^|\]]+)\|([^|\]]+)\|?([^|\]]*)\|?([^\]]*)\]', response):
        chat_id = match.group(1).strip()
        message_id = match.group(2).strip()
        label_val = match.group(3).strip()
        chat_type = match.group(4).strip() or "chat"
        try:
            from app.memory_teams import set_teams_marker
            res = set_teams_marker(username, chat_id, message_id, label_val, chat_type)
            confirmed.append(res.get("message", "✅ Curseur Teams posé."))
        except Exception as e:
            confirmed.append(f"❌ Teams mark : {str(e)[:80]}")

    for match in re.finditer(r'\[ACTION:TEAMS_SYNC:([^|\]]+)\|?([^|\]]*)\|?([^\]]*)\]', response):
        chat_id = match.group(1).strip()
        label_val = match.group(2).strip()
        chat_type = match.group(3).strip() or "chat"
        try:
            from app.memory_teams import ingest_and_synthesize, get_teams_markers
            markers = get_teams_markers(username)
            marker = next((m for m in markers if m["chat_id"] == chat_id), None)
            since = marker["last_message_id"] if marker else None
            threading.Thread(
                target=lambda: ingest_and_synthesize(token, username, chat_id, label_val, chat_type, since),
                daemon=True
            ).start()
            confirmed.append(f"🔄 Sync Teams '{label_val or chat_id[:20]}' lancée en arrière-plan.")
        except Exception as e:
            confirmed.append(f"❌ Teams sync : {str(e)[:80]}")

    for match in re.finditer(r'\[ACTION:TEAMS_HISTORY:([^|\]]+)\|?([^|\]]*)\|?([^\]]*)\]', response):
        chat_id = match.group(1).strip()
        label_val = match.group(2).strip()
        chat_type = match.group(3).strip() or "chat"
        try:
            from app.memory_teams import explore_history
            threading.Thread(
                target=lambda: explore_history(token, username, chat_id, label_val, chat_type),
                daemon=True
            ).start()
            confirmed.append(f"🔍 Exploration historique Teams '{label_val or chat_id[:20]}' lancée.")
        except Exception as e:
            confirmed.append(f"❌ Teams history : {str(e)[:80]}")

    return confirmed


# ─── MÉMOIRE ───

def _handle_memory_actions(response, username, synth_threshold):
    confirmed = []

    for match in re.finditer(r'\[ACTION:LEARN:([^|^\]]+)\|([^\]]+)\]', response):
        category = match.group(1).strip()
        rule = match.group(2).strip()
        try:
            save_rule(category, rule, "auto", 0.7, username)
            confirmed.append(f"🧠 Mémorisé [{category}] : {rule[:60]}")
        except Exception as e:
            print(f"[LEARN] Erreur: {e}")

    for match in re.finditer(r'\[ACTION:INSIGHT:([^|^\]]+)\|([^\]]+)\]', response):
        topic = match.group(1).strip()
        insight = match.group(2).strip()
        try:
            save_insight(topic, insight, "auto", username)
            confirmed.append(f"💡 Observé [{topic}] : {insight[:60]}")
        except Exception as e:
            print(f"[INSIGHT] Erreur: {e}")

    for match in re.finditer(r'\[ACTION:FORGET:(\d+)\]', response):
        rule_id = int(match.group(1))
        try:
            deleted = delete_rule(rule_id, username)
            confirmed.append(
                f"🗑️ Règle {rule_id} désactivée." if deleted
                else f"❌ Règle {rule_id} introuvable."
            )
        except Exception as e:
            print(f"[FORGET] Erreur: {e}")

    for _ in re.finditer(r'\[ACTION:SYNTH:\]', response):
        try:
            threading.Thread(
                target=lambda u=username, t=synth_threshold: synthesize_session(t, u),
                daemon=True
            ).start()
            confirmed.append("🔄 Synthèse lancée en arrière-plan.")
        except Exception as e:
            print(f"[SYNTH] Erreur: {e}")

    return confirmed
