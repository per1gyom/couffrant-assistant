"""Execution des actions Raya.
Parse la reponse de Claude et execute les [ACTION:...] correspondants.

DELETE = corbeille (recuperable) -> execution directe groupee, pas de queue.
Actions sensibles (REPLY, TEAMS_MSG, MOVEDRIVE...) -> queue pending_actions.
[ACTION:ASK_CHOICE:question|opt1|opt2] -> boutons de choix dans le chat.
[ACTION:LEARN:...] -> validation via rule_validator avant ecriture en base.
5D-2d : [ACTION:LEARN:cat|rule|tenant_id] -> ecrit sur un tenant specifique.
         [ACTION:LEARN:cat|rule|_user]      -> regle personnelle (tenant_id=NULL).
"""
import json
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

# Prefixe special pour transmettre ASK_CHOICE a raya.py sans casser l'API
_ASK_CHOICE_PREFIX = "__CHOICE__:"


def is_valid_outlook_id(msg_id: str) -> bool:
    return len(msg_id.strip()) > 20


def execute_actions(
    raya_response: str,
    username: str,
    outlook_token: str,
    mails_from_db: list,
    live_mails: list,
    tools: dict,
    tenant_id: str = 'couffrant_solar',
    conversation_id: int = None,
) -> list:
    confirmed = []
    drive_write = tools.get("drive_write", False)
    mail_can_delete = tools.get("mail_can_delete", False)
    synth_threshold = get_memoire_param(username, "synth_threshold", 15)

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
        confirmed += _handle_memory_actions(raya_response, username, synth_threshold, tenant_id)

    # ASK_CHOICE : toujours traite (independant des outils)
    confirmed += _handle_ask_choice(raya_response)

    return confirmed


# --- CONFIRM/CANCEL ---

def _handle_confirmations(response, username, tenant_id, outlook_token, tools):
    confirmed = []

    for match in re.finditer(r'\[ACTION:CONFIRM:(\d+)\]', response):
        action_id = int(match.group(1))
        action = confirm_action(action_id, username, tenant_id)
        if not action:
            confirmed.append(f"\u274c Action #{action_id} introuvable, deja traitee ou expiree.")
            continue
        result = _execute_confirmed_action(action, outlook_token, tools)
        if result.get("ok"):
            mark_executed(action_id, result)
            confirmed.append(f"\u2705 {result.get('message', 'Action executee')}")
        else:
            mark_failed(action_id, result.get("error", "erreur inconnue"))
            confirmed.append(f"\u274c Echec : {result.get('error', 'erreur inconnue')}")

    for match in re.finditer(r'\[ACTION:CANCEL:(\d+)\]', response):
        action_id = int(match.group(1))
        ok = cancel_action(action_id, username, tenant_id, reason="Annule par l'utilisateur")
        confirmed.append(
            f"\u23f9\ufe0f Action #{action_id} annulee." if ok
            else f"\u274c Action #{action_id} introuvable."
        )

    return confirmed


def _execute_confirmed_action(action: dict, outlook_token: str, tools: dict) -> dict:
    action_type = action["action_type"]
    payload = action["payload"]
    try:
        if action_type == "REPLY":
            r = perform_outlook_action("send_reply", {
                "message_id": payload["message_id"],
                "reply_body": payload["reply_text"],
            }, outlook_token)
            return {"ok": r.get("status") == "ok", "message": "Reponse envoyee",
                    "error": r.get("message", "envoi echoue")}

        if action_type == "DELETE_GROUPED":
            ids = payload.get("message_ids", [])
            ok_count = 0
            for msg_id in ids:
                try:
                    r = perform_outlook_action("delete_message", {"message_id": msg_id}, outlook_token)
                    if r.get("status") == "ok":
                        ok_count += 1
                except Exception:
                    pass
            n = len(ids)
            return {
                "ok": ok_count > 0,
                "message": f"{ok_count} mail{'s' if ok_count > 1 else ''} a la corbeille." if ok_count == n
                           else f"{ok_count}/{n} mails a la corbeille.",
                "error": f"Echec sur {n - ok_count} mail(s)" if ok_count < n else "",
            }

        if action_type == "TEAMS_MSG":
            r = send_message_to_user(outlook_token, payload["email"], payload["text"])
            return {"ok": r.get("status") == "ok", "message": r.get("message", "Message Teams envoye"),
                    "error": r.get("message", "envoi Teams echoue")}

        if action_type == "TEAMS_REPLYCHAT":
            r = send_chat_message(outlook_token, payload["chat_id"], payload["text"])
            return {"ok": r.get("status") == "ok", "message": "Reponse Teams envoyee",
                    "error": r.get("message", "envoi echoue")}

        if action_type == "TEAMS_SENDCHANNEL":
            r = send_channel_message(outlook_token, payload["team_id"], payload["channel_id"], payload["text"])
            return {"ok": r.get("status") == "ok", "message": "Message canal Teams envoye",
                    "error": r.get("message", "envoi echoue")}

        if action_type == "TEAMS_GROUPE":
            r = create_group_chat(outlook_token, payload["emails"], payload["topic"], payload["text"])
            return {"ok": r.get("status") == "ok", "message": r.get("message", "Groupe Teams cree"),
                    "error": r.get("message", "creation echouee")}

        if action_type == "MOVEDRIVE":
            if not tools.get("drive_write"):
                return {"ok": False, "error": "Ecriture Drive non autorisee"}
            _, drive_id, _ = _find_sharepoint_site_and_drive(outlook_token)
            r = move_item(outlook_token, payload["item_id"], payload["dest_id"],
                          payload.get("new_name"), drive_id)
            return {"ok": r.get("status") == "ok", "message": r.get("message", "Deplace"),
                    "error": r.get("message", "deplacement echoue")}

        if action_type == "COPYFILE":
            if not tools.get("drive_write"):
                return {"ok": False, "error": "Ecriture Drive non autorisee"}
            _, drive_id, _ = _find_sharepoint_site_and_drive(outlook_token)
            r = copy_item(outlook_token, payload["source_id"], payload["dest_id"],
                          payload.get("new_name"), drive_id)
            return {"ok": r.get("status") == "ok", "message": r.get("message", "Copie lancee"),
                    "error": r.get("message", "copie echouee")}

        if action_type == "CREATEEVENT":
            r = perform_outlook_action("create_calendar_event", {
                "subject": payload["subject"], "start": payload["start"],
                "end": payload["end"], "attendees": payload.get("attendees", []),
            }, outlook_token)
            return {"ok": r.get("status") == "ok", "message": "RDV cree",
                    "error": r.get("message", "creation RDV echouee")}

        return {"ok": False, "error": f"Type d'action inconnu : {action_type}"}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


# --- MAILS ---

def _build_delete_label(subjects: list) -> str:
    from collections import Counter
    keywords = []
    for s in subjects:
        words = s.split()
        kw = next((w for w in words if len(w) > 3 and w not in ("dans", "pour", "votre", "avec", "vous")), words[0] if words else "?")
        keywords.append(kw.rstrip(".,!:").capitalize())
    counts = Counter(keywords)
    top = sorted(counts.items(), key=lambda x: -x[1])[:4]
    detail = ", ".join(f"{kw} x{n}" if n > 1 else kw for kw, n in top)
    return f"Supprimer {len(subjects)} mail{'s' if len(subjects) > 1 else ''} ({detail})"


def _handle_mail_actions(response, token, mail_can_delete, mails_from_db, live_mails,
                         username, tenant_id, conversation_id):
    confirmed = []

    if mail_can_delete:
        delete_ids = []
        delete_subjects = []
        for msg_id in re.findall(r'\[ACTION:DELETE:([^\]]+)\]', response):
            msg_id = msg_id.strip()
            if not is_valid_outlook_id(msg_id):
                continue
            orig = next((m for m in live_mails + mails_from_db if m.get('message_id') == msg_id), {})
            delete_ids.append(msg_id)
            delete_subjects.append(orig.get('subject', msg_id[:30]))

        if delete_ids:
            ok_count = 0
            for msg_id in delete_ids:
                try:
                    r = perform_outlook_action("delete_message", {"message_id": msg_id}, token)
                    if r.get("status") == "ok":
                        ok_count += 1
                except Exception:
                    pass
            n = len(delete_ids)
            if ok_count == n:
                confirmed.append(
                    f"\U0001f5d1\ufe0f {n} mail{'s' if n > 1 else ''} a la corbeille."
                    if n > 1 else f"\U0001f5d1\ufe0f '{delete_subjects[0]}' a la corbeille."
                )
            else:
                confirmed.append(f"\U0001f5d1\ufe0f {ok_count}/{n} mails a la corbeille ({n - ok_count} echoue(s)).")

    for msg_id in re.findall(r'\[ACTION:ARCHIVE:([^\]]+)\]', response):
        msg_id = msg_id.strip()
        if not is_valid_outlook_id(msg_id):
            continue
        try:
            r = perform_outlook_action("archive_message", {"message_id": msg_id}, token)
            confirmed.append("\u2705 Archive" if r.get("status") == "ok" else f"\u274c {r.get('message')}")
        except Exception as e:
            confirmed.append(f"\u274c {str(e)[:80]}")

    for msg_id in re.findall(r'\[ACTION:READ:([^\]]+)\]', response):
        msg_id = msg_id.strip()
        if not is_valid_outlook_id(msg_id):
            continue
        try:
            perform_outlook_action("mark_as_read", {"message_id": msg_id}, token)
        except Exception:
            pass

    for match in re.finditer(r'\[ACTION:REPLY:([^:\]]{20,}):(.+?)\]', response, re.DOTALL):
        msg_id = match.group(1).strip()
        reply_text = match.group(2).strip()
        if not is_valid_outlook_id(msg_id):
            continue
        orig = next((m for m in live_mails + mails_from_db if m.get('message_id') == msg_id), {})
        label = f"Repondre a '{orig.get('subject', msg_id[:30])}' ({orig.get('from_email', '?')})"
        action_id = queue_action(
            tenant_id=tenant_id, username=username, action_type="REPLY",
            payload={
                "message_id": msg_id, "reply_text": reply_text,
                "subject": orig.get('subject', ''), "to": orig.get('from_email', ''),
            },
            label=label, conversation_id=conversation_id,
        )
        preview = reply_text[:300] + ("..." if len(reply_text) > 300 else "")
        confirmed.append(
            f"\u23f8\ufe0f Action #{action_id} en attente \u2014 Reponse a envoyer :\n"
            f"   A : {orig.get('from_email', '?')}\n"
            f"   Sujet : {orig.get('subject', '?')}\n"
            f"   Message : {preview}\n"
            f"   Pour envoyer : dites \"confirme action {action_id}\" \u00b7 Pour annuler : \"annule action {action_id}\""
        )

    for msg_id in re.findall(r'\[ACTION:READBODY:([^\]]+)\]', response):
        msg_id = msg_id.strip()
        if not is_valid_outlook_id(msg_id):
            continue
        try:
            r = perform_outlook_action("get_message_body", {"message_id": msg_id}, token)
            if r.get("status") == "ok":
                confirmed.append(f"\U0001f4e7 Corps du mail :\n{r.get('body_text', '')[:800]}")
        except Exception:
            pass

    for match in re.finditer(r'\[ACTION:CREATEEVENT:([^\]]+)\]', response):
        parts = match.group(1).split('|')
        if len(parts) >= 3:
            attendees = parts[3].split(',') if len(parts) > 3 else []
            label = f"Creer RDV '{parts[0]}' le {parts[1][:10]}"
            action_id = queue_action(
                tenant_id=tenant_id, username=username, action_type="CREATEEVENT",
                payload={"subject": parts[0], "start": parts[1], "end": parts[2], "attendees": attendees},
                label=label, conversation_id=conversation_id,
            )
            confirmed.append(
                f"\u23f8\ufe0f Action #{action_id} en attente : {label}\n"
                f"   Participants : {', '.join(attendees) if attendees else 'aucun'}\n"
                f"   Pour confirmer : dites \"confirme action {action_id}\""
            )

    for title in re.findall(r'\[ACTION:CREATE_TASK:([^\]]+)\]', response):
        try:
            perform_outlook_action("create_todo_task", {"title": title.strip()}, token)
        except Exception:
            pass

    return confirmed


# --- DRIVE ---

def _handle_drive_actions(response, token, drive_write, username, tenant_id, conversation_id):
    confirmed = []

    for match in re.finditer(r'\[ACTION:LISTDRIVE:([^\]]*)\]', response):
        subfolder = match.group(1).strip()
        try:
            r = list_drive(token, subfolder)
            if r.get("status") == "ok":
                lines = []
                for it in r.get("items", []):
                    icon = "\U0001f4c1" if it.get("type") == "dossier" else "\U0001f4c4"
                    size_str = f"  ({it.get('taille_ko','')} Ko)" if it.get("taille_ko") else ""
                    link = it.get("lien", "")
                    name = it['nom']
                    lines.append(f"  {icon} [**{name}**]({link}){size_str}" if link else f"  {icon} **{name}**{size_str}")
                confirmed.append(f"\U0001f5c2\ufe0f {r.get('dossier', '1_Photovoltaique')} ({r['count']}) :\n" + "\n".join(lines))
            else:
                confirmed.append(f"\u274c {r.get('message', 'Erreur Drive')}")
        except Exception as e:
            confirmed.append(f"\u274c Drive : {str(e)[:80]}")

    for match in re.finditer(r'\[ACTION:READDRIVE:([^\]]+)\]', response):
        file_ref = match.group(1).strip()
        try:
            r = read_drive_file(token, file_ref)
            if r.get("status") == "ok":
                if r.get("type") == "texte":
                    confirmed.append(f"\U0001f4c4 {r['fichier']} :\n{r['contenu'][:2000]}")
                else:
                    link = r.get("lien", "")
                    name = r.get('fichier', file_ref)
                    confirmed.append(
                        f"\U0001f4c4 [{name}]({link}) \u2014 {r.get('message', '')} {r.get('conseil', '')}" if link
                        else f"\U0001f4c4 {name} \u2014 {r.get('message', '')} {r.get('conseil', '')}"
                    )
            else:
                confirmed.append(f"\u274c {r.get('message')}")
        except Exception as e:
            confirmed.append(f"\u274c {str(e)[:80]}")

    for match in re.finditer(r'\[ACTION:SEARCHDRIVE:([^\]]+)\]', response):
        q = match.group(1).strip()
        try:
            r = search_drive(token, q)
            if r.get("status") == "ok":
                lines = []
                for it in r.get("items", []):
                    icon = "\U0001f4c1" if it.get('type') == 'dossier' else "\U0001f4c4"
                    link = it.get("lien", "")
                    name = it['nom']
                    lines.append(f"  {icon} [**{name}**]({link})" if link else f"  {icon} **{name}**")
                confirmed.append(f"\U0001f50d '{q}' \u2014 {r['count']} resultat(s) :\n" + "\n".join(lines))
            else:
                confirmed.append(f"\u274c {r.get('message')}")
        except Exception as e:
            confirmed.append(f"\u274c {str(e)[:80]}")

    if drive_write:
        for match in re.finditer(r'\[ACTION:CREATEFOLDER:([^|^\]]+)\|([^\]]+)\]', response):
            parent_id = match.group(1).strip()
            folder_name = match.group(2).strip()
            try:
                _, drive_id, _ = _find_sharepoint_site_and_drive(token)
                r = create_folder(token, parent_id, folder_name, drive_id)
                confirmed.append(f"\u2705 Dossier '{folder_name}' cree" if r.get("status") == "ok" else f"\u274c {r.get('message')}")
            except Exception as e:
                confirmed.append(f"\u274c {str(e)[:80]}")

        for match in re.finditer(r'\[ACTION:MOVEDRIVE:([^|^\]]+)\|([^|^\]]+)\|?([^\]]*)\]', response):
            item_id = match.group(1).strip()
            dest_id = match.group(2).strip()
            new_name = match.group(3).strip() or None
            label = f"Deplacer '{item_id[:20]}' vers '{dest_id[:20]}'"
            action_id = queue_action(
                tenant_id=tenant_id, username=username, action_type="MOVEDRIVE",
                payload={"item_id": item_id, "dest_id": dest_id, "new_name": new_name},
                label=label, conversation_id=conversation_id,
            )
            confirmed.append(f"\u23f8\ufe0f Action #{action_id} en attente : {label}\n   Pour confirmer : dites \"confirme action {action_id}\"")

        for match in re.finditer(r'\[ACTION:COPYFILE:([^|^\]]+)\|([^|^\]]+)\|?([^\]]*)\]', response):
            source_id = match.group(1).strip()
            dest_id = match.group(2).strip()
            new_name = match.group(3).strip() or None
            label = f"Copier '{source_id[:20]}' vers '{dest_id[:20]}'"
            action_id = queue_action(
                tenant_id=tenant_id, username=username, action_type="COPYFILE",
                payload={"source_id": source_id, "dest_id": dest_id, "new_name": new_name},
                label=label, conversation_id=conversation_id,
            )
            confirmed.append(f"\u23f8\ufe0f Action #{action_id} en attente : {label}\n   Pour confirmer : dites \"confirme action {action_id}\"")

    return confirmed


# --- TEAMS ---

def _handle_teams_actions(response, token, username, tenant_id, conversation_id):
    confirmed = []

    for _ in re.finditer(r'\[ACTION:TEAMS_LIST:\]', response):
        try:
            res = list_teams_with_channels(token)
            if res.get("status") == "ok":
                lines = []
                for t in res.get("teams", []):
                    ch_names = ", ".join(c["name"] for c in t.get("channels", [])[:5]) or "\u2014"
                    lines.append(f"  \U0001f3e2 {t['name']} [id:{t['id']}]\n     Canaux : {ch_names}")
                confirmed.append(f"\U0001f4cb Teams ({res['count']}) :\n" + "\n".join(lines))
            else:
                confirmed.append(f"\u274c Teams : {res.get('message')}")
        except Exception as e:
            confirmed.append(f"\u274c Teams : {str(e)[:80]}")

    for match in re.finditer(r'\[ACTION:TEAMS_CHANNEL:([^|^\]]+)\|([^\]]+)\]', response):
        team_id = match.group(1).strip()
        channel_id = match.group(2).strip()
        try:
            res = read_channel_messages(token, team_id, channel_id)
            if res.get("status") == "ok":
                lines = [f"  [{m['date'][:10]}] {m['sender']} : {m['content'][:120]}" for m in res.get("messages", [])]
                confirmed.append(f"\U0001f4ac Canal ({res['count']}) :\n" + "\n".join(lines))
            else:
                confirmed.append(f"\u274c Canal : {res.get('message')}")
        except Exception as e:
            confirmed.append(f"\u274c Canal : {str(e)[:80]}")

    for _ in re.finditer(r'\[ACTION:TEAMS_CHATS:\]', response):
        try:
            res = list_chats(token)
            if res.get("status") == "ok":
                lines = []
                for c in res.get("chats", []):
                    icon = "\U0001f464" if c['type'] == 'oneOnOne' else "\U0001f465"
                    lines.append(f"  {icon} {c['topic']} [id:{c['id'][:20]}...]")
                confirmed.append(f"\U0001f4ac Chats Teams ({res['count']}) :\n" + "\n".join(lines))
            else:
                confirmed.append(f"\u274c Chats : {res.get('message')}")
        except Exception as e:
            confirmed.append(f"\u274c Chats : {str(e)[:80]}")

    for match in re.finditer(r'\[ACTION:TEAMS_READCHAT:([^\]]+)\]', response):
        chat_id = match.group(1).strip()
        try:
            res = read_chat_messages(token, chat_id)
            if res.get("status") == "ok":
                lines = [f"  [{m['date'][:10]}] {m['sender']} : {m['content'][:150]}" for m in res.get("messages", [])]
                confirmed.append(f"\U0001f4ac Chat ({res['count']}) :\n" + "\n".join(lines))
            else:
                confirmed.append(f"\u274c Chat : {res.get('message')}")
        except Exception as e:
            confirmed.append(f"\u274c Chat : {str(e)[:80]}")

    for match in re.finditer(r'\[ACTION:TEAMS_MSG:([^|^\]]+)\|(.+?)\]', response, re.DOTALL):
        email = match.group(1).strip()
        text = match.group(2).strip()
        label = f"Message Teams a {email}"
        action_id = queue_action(
            tenant_id=tenant_id, username=username, action_type="TEAMS_MSG",
            payload={"email": email, "text": text}, label=label, conversation_id=conversation_id,
        )
        preview = text[:200] + ("..." if len(text) > 200 else "")
        confirmed.append(f"\u23f8\ufe0f Action #{action_id} en attente : {label}\n   Message : {preview}\n   Pour envoyer : dites \"confirme action {action_id}\"")

    for match in re.finditer(r'\[ACTION:TEAMS_REPLYCHAT:([^|^\]]+)\|(.+?)\]', response, re.DOTALL):
        chat_id = match.group(1).strip()
        text = match.group(2).strip()
        action_id = queue_action(
            tenant_id=tenant_id, username=username, action_type="TEAMS_REPLYCHAT",
            payload={"chat_id": chat_id, "text": text},
            label="Repondre dans le chat Teams", conversation_id=conversation_id,
        )
        confirmed.append(f"\u23f8\ufe0f Action #{action_id} en attente : Repondre dans le chat Teams\n   Pour envoyer : dites \"confirme action {action_id}\"")

    for match in re.finditer(r'\[ACTION:TEAMS_SENDCHANNEL:([^|^\]]+)\|([^|^\]]+)\|(.+?)\]', response, re.DOTALL):
        team_id = match.group(1).strip()
        channel_id = match.group(2).strip()
        text = match.group(3).strip()
        action_id = queue_action(
            tenant_id=tenant_id, username=username, action_type="TEAMS_SENDCHANNEL",
            payload={"team_id": team_id, "channel_id": channel_id, "text": text},
            label="Message dans canal Teams", conversation_id=conversation_id,
        )
        confirmed.append(f"\u23f8\ufe0f Action #{action_id} en attente : Message dans canal Teams\n   Pour envoyer : dites \"confirme action {action_id}\"")

    for match in re.finditer(r'\[ACTION:TEAMS_GROUPE:([^|^\]]+)\|([^|^\]]+)\|(.+?)\]', response, re.DOTALL):
        emails_raw = match.group(1).strip()
        topic = match.group(2).strip()
        text = match.group(3).strip()
        emails = [e.strip() for e in emails_raw.split(',') if e.strip()]
        label = f"Creer groupe Teams : {topic}"
        action_id = queue_action(
            tenant_id=tenant_id, username=username, action_type="TEAMS_GROUPE",
            payload={"emails": emails, "topic": topic, "text": text},
            label=label, conversation_id=conversation_id,
        )
        confirmed.append(f"\u23f8\ufe0f Action #{action_id} en attente : {label}\n   Pour creer : dites \"confirme action {action_id}\"")

    for match in re.finditer(r'\[ACTION:TEAMS_MARK:([^|^\]]+)\|([^|^\]]+)\|?([^|^\]]*)\|?([^\]]*)\]', response):
        chat_id = match.group(1).strip()
        message_id = match.group(2).strip()
        label = match.group(3).strip()
        chat_type = match.group(4).strip() or "chat"
        try:
            from app.memory_teams import set_teams_marker
            res = set_teams_marker(username, chat_id, message_id, label, chat_type)
            confirmed.append(res.get("message", "\u2705 Curseur Teams pose."))
        except Exception as e:
            confirmed.append(f"\u274c Teams mark : {str(e)[:80]}")

    for match in re.finditer(r'\[ACTION:TEAMS_SYNC:([^|^\]]+)\|?([^|^\]]*)\|?([^\]]*)\]', response):
        chat_id = match.group(1).strip()
        label = match.group(2).strip()
        chat_type = match.group(3).strip() or "chat"
        try:
            from app.memory_teams import ingest_and_synthesize, get_teams_markers
            markers = get_teams_markers(username)
            marker = next((m for m in markers if m["chat_id"] == chat_id), None)
            since = marker["last_message_id"] if marker else None
            threading.Thread(
                target=lambda: ingest_and_synthesize(token, username, chat_id, label, chat_type, since),
                daemon=True
            ).start()
            confirmed.append(f"\U0001f504 Sync Teams '{label or chat_id[:20]}' lancee en arriere-plan.")
        except Exception as e:
            confirmed.append(f"\u274c Teams sync : {str(e)[:80]}")

    for match in re.finditer(r'\[ACTION:TEAMS_HISTORY:([^|^\]]+)\|?([^|^\]]*)\|?([^\]]*)\]', response):
        chat_id = match.group(1).strip()
        label = match.group(2).strip()
        chat_type = match.group(3).strip() or "chat"
        try:
            from app.memory_teams import explore_history
            threading.Thread(
                target=lambda: explore_history(token, username, chat_id, label, chat_type),
                daemon=True
            ).start()
            confirmed.append(f"\U0001f50d Exploration historique Teams '{label or chat_id[:20]}' lancee.")
        except Exception as e:
            confirmed.append(f"\u274c Teams history : {str(e)[:80]}")

    return confirmed


# --- ASK_CHOICE (C3) ---

def _handle_ask_choice(response: str) -> list:
    """
    Parse [ACTION:ASK_CHOICE:question|option1|option2|option3].
    Serialise en __CHOICE__:{json} pour extraction dans raya.py.
    """
    confirmed = []
    TAG = '[ACTION:ASK_CHOICE:'
    start = response.find(TAG)
    if start == -1:
        return confirmed

    content_start = start + len(TAG)
    close = response.find(']', content_start)
    if close == -1:
        return confirmed

    content = response[content_start:close]
    parts = [p.strip() for p in content.split('|') if p.strip()]
    if len(parts) < 2:
        return confirmed

    question = parts[0]
    options = parts[1:][:4]

    confirmed.append(
        _ASK_CHOICE_PREFIX + json.dumps(
            {"question": question, "options": options},
            ensure_ascii=False,
        )
    )
    return confirmed


# --- MEMOIRE ---

def _extract_tenant_target(raw_rule: str) -> tuple[str, str | None]:
    """
    5D-2d : extrait le tenant cible optionnel du texte de la regle.

    Format :
      "regle simple"                      -> ("regle simple", None)
      "regle avec tenant|couffrant_solar"  -> ("regle avec tenant", "couffrant_solar")
      "regle perso|_user"                  -> ("regle perso", "_user")

    Le tenant cible est le segment apres le DERNIER pipe,
    s'il correspond a un identifiant valide (alphanum + underscore, <= 50 chars).
    """
    last_pipe = raw_rule.rfind('|')
    if last_pipe == -1:
        return raw_rule, None

    candidate = raw_rule[last_pipe + 1:].strip()
    if candidate and len(candidate) <= 50 and re.match(r'^_?[a-z][a-z0-9_]*$', candidate):
        return raw_rule[:last_pipe].strip(), candidate

    return raw_rule, None


def _parse_learn_actions(response: str) -> list:
    """
    C4 — Parser robuste pour [ACTION:LEARN:category|rule] et
    [ACTION:LEARN:category|rule|tenant_target] (5D-2d).

    Gere les ] a l'interieur du texte de la regle.
    Retourne une liste de tuples (category, rule, target_tenant).
    target_tenant est None si non specifie, "_user" pour regle perso,
    ou un tenant_id explicite.
    """
    results = []
    TAG = '[ACTION:LEARN:'
    pos = 0

    while True:
        start = response.find(TAG, pos)
        if start == -1:
            break

        after_tag = start + len(TAG)
        pipe = response.find('|', after_tag)
        if pipe == -1:
            pos = start + 1
            continue

        category = response[after_tag:pipe].strip()
        if not category or ']' in category or '\n' in category or '|' in category:
            pos = start + 1
            continue

        rule_start = pipe + 1
        search = rule_start
        rule_end = -1

        while search < len(response):
            bracket = response.find(']', search)
            if bracket == -1:
                break

            next_pos = bracket + 1

            if next_pos >= len(response):
                rule_end = bracket
                break

            next_char = response[next_pos]

            if next_char in '\n\r[':
                rule_end = bracket
                break

            if next_char == ' ' and next_pos + 1 < len(response) and response[next_pos + 1] == '[':
                rule_end = bracket
                break

            search = bracket + 1

        if rule_end == -1:
            fallback = response.find(']', rule_start)
            if fallback != -1:
                rule_end = fallback
            else:
                pos = start + 1
                continue

        rule = response[rule_start:rule_end].strip()
        if rule:
            clean_rule, target_tenant = _extract_tenant_target(rule)
            results.append((category, clean_rule, target_tenant))

        pos = rule_end + 1

    return results


def _handle_memory_actions(response: str, username: str, synth_threshold: int,
                           tenant_id: str = 'couffrant_solar') -> list:
    confirmed = []

    # C4 : parser robuste + C1 : validation via rule_validator
    # 5D-2d : support tenant cible dans LEARN
    for category, rule, target_tenant in _parse_learn_actions(response):
        # 5D-2d : resolution du tenant cible
        if target_tenant == "_user":
            effective_tenant = None
            is_personal = True
        elif target_tenant:
            effective_tenant = target_tenant
            is_personal = False
        else:
            effective_tenant = tenant_id
            is_personal = False

        try:
            try:
                from app.rule_validator import validate_rule_before_save, apply_validation_result
                result = validate_rule_before_save(
                    username, effective_tenant or tenant_id, category, rule
                )
                decision = result.get("decision", "NEW")

                if decision == "CONFLICT":
                    conflict_msg = result.get("conflict_message", "Conflit detecte avec une regle existante.")
                    confirmed.append(f"\u26a0\ufe0f Conflit de regle : {conflict_msg}")
                    continue

                if decision == "DUPLICATE":
                    confirmed.append(f"\U0001f9e0 Deja en memoire [{category}] (doublon ignore)")
                    continue

                messages = apply_validation_result(
                    result, username, effective_tenant or tenant_id
                )
                label = " | ".join(messages) if messages else f"[{category}]"
                tenant_tag = f" @{target_tenant}" if target_tenant else ""
                confirmed.append(
                    f"\U0001f9e0 Memorise {label}{tenant_tag} : "
                    f"{rule[:120]}{'...' if len(rule) > 120 else ''}"
                )

            except ImportError:
                save_rule(category, rule, "auto", 0.7, username,
                          tenant_id=effective_tenant, personal=is_personal)
                tenant_tag = f" @{target_tenant}" if target_tenant else ""
                confirmed.append(
                    f"\U0001f9e0 Memorise [{category}]{tenant_tag} : "
                    f"{rule[:120]}{'...' if len(rule) > 120 else ''}"
                )

        except Exception as e:
            print(f"[LEARN] Erreur: {e}")

    for match in re.finditer(r'\[ACTION:INSIGHT:([^|^\]]+)\|([^\]]+)\]', response):
        topic = match.group(1).strip()
        insight = match.group(2).strip()
        try:
            save_insight(topic, insight, "auto", username)
            confirmed.append(f"\U0001f4a1 Observe [{topic}] : {insight[:120]}{'...' if len(insight) > 120 else ''}")
        except Exception as e:
            print(f"[INSIGHT] Erreur: {e}")

    for match in re.finditer(r'\[ACTION:FORGET:(\d+)\]', response):
        rule_id = int(match.group(1))
        try:
            deleted = delete_rule(rule_id, username)
            confirmed.append(
                f"\U0001f5d1\ufe0f Regle {rule_id} desactivee." if deleted
                else f"\u274c Regle {rule_id} introuvable."
            )
        except Exception as e:
            print(f"[FORGET] Erreur: {e}")

    for _ in re.finditer(r'\[ACTION:SYNTH:\]', response):
        try:
            threading.Thread(
                target=lambda u=username, t=synth_threshold: synthesize_session(t, u),
                daemon=True
            ).start()
            confirmed.append("\U0001f504 Synthese lancee en arriere-plan.")
        except Exception as e:
            print(f"[SYNTH] Erreur: {e}")

    for _ in re.finditer(r'\[ACTION:RESTART_ONBOARDING:\]', response):
        try:
            from app.onboarding import restart_onboarding
            ok = restart_onboarding(username, tenant_id)
            confirmed.append(
                "\U0001f504 Questionnaire relance ! Recharge la page (F5)." if ok
                else "\u274c Impossible de relancer le questionnaire."
            )
        except Exception as e:
            print(f"[RESTART_ONBOARDING] Erreur: {e}")
            confirmed.append("\u274c Erreur lors du redemarrage du questionnaire.")

    return confirmed
