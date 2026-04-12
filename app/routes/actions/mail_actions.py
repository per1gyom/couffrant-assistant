"""
Gestion des actions mail (ARCHIVE, READ, REPLY, DELETE, READBODY, CREATEEVENT, CREATE_TASK).
"""
import re
from app.connectors.outlook_connector import perform_outlook_action
from app.pending_actions import queue_action


def is_valid_outlook_id(msg_id: str) -> bool:
    return len(msg_id.strip()) > 20


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
        if not is_valid_outlook_id(msg_id): continue
        try:
            r = perform_outlook_action("archive_message", {"message_id": msg_id}, token)
            confirmed.append("\u2705 Archive" if r.get("status") == "ok" else f"\u274c {r.get('message')}")
        except Exception as e:
            confirmed.append(f"\u274c {str(e)[:80]}")

    for msg_id in re.findall(r'\[ACTION:READ:([^\]]+)\]', response):
        msg_id = msg_id.strip()
        if not is_valid_outlook_id(msg_id): continue
        try:
            perform_outlook_action("mark_as_read", {"message_id": msg_id}, token)
        except Exception:
            pass

    for match in re.finditer(r'\[ACTION:REPLY:([^\:\]]{20,}):(.+?)\]', response, re.DOTALL):
        msg_id = match.group(1).strip()
        reply_text = match.group(2).strip()
        if not is_valid_outlook_id(msg_id): continue
        orig = next((m for m in live_mails + mails_from_db if m.get('message_id') == msg_id), {})
        label = f"Repondre a '{orig.get('subject', msg_id[:30])}' ({orig.get('from_email', '?')})"
        action_id = queue_action(
            tenant_id=tenant_id, username=username, action_type="REPLY",
            payload={"message_id": msg_id, "reply_text": reply_text,
                     "subject": orig.get('subject', ''), "to": orig.get('from_email', '')},
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
        if not is_valid_outlook_id(msg_id): continue
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
