"""
Gestion des actions mail (ARCHIVE, READ, REPLY, DELETE, READBODY, CREATEEVENT, CREATE_TASK).
7-ACT : log d'activite apres chaque action.
FIX-MAIL-DUP : set processed_ids pour eviter DELETE+ARCHIVE sur le meme mail.
"""
import re
from app.connectors.outlook_connector import perform_outlook_action
from app.pending_actions import queue_action
from app.activity_log import log_activity


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
                         username, tenant_id, conversation_id, from_email=""):
    confirmed = []
    # FIX-MAIL-DUP : tracker les IDs deja traites pour eviter DELETE+ARCHIVE sur le meme mail
    processed_ids = set()

    if mail_can_delete:
        delete_ids = []
        delete_subjects = []
        for msg_id in re.findall(r'\[ACTION:DELETE:([^\]]+)\]', response):
            msg_id = msg_id.strip()
            if not is_valid_outlook_id(msg_id):
                continue
            if msg_id in processed_ids:
                continue
            orig = next((m for m in live_mails + mails_from_db if m.get('message_id') == msg_id), {})
            delete_ids.append(msg_id)
            delete_subjects.append(orig.get('subject', msg_id[:30]))
            processed_ids.add(msg_id)
        if delete_ids:
            ok_count = 0
            for msg_id in delete_ids:
                try:
                    r = perform_outlook_action("delete_message", {"message_id": msg_id}, token)
                    if r.get("status") == "ok":
                        ok_count += 1
                        log_activity(username, "mail_delete", msg_id, delete_subjects[delete_ids.index(msg_id)][:100], tenant_id=tenant_id)
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
        if msg_id in processed_ids: continue
        processed_ids.add(msg_id)
        try:
            r = perform_outlook_action("archive_message", {"message_id": msg_id}, token)
            if r.get("status") == "ok":
                confirmed.append("\u2705 Archive")
                log_activity(username, "mail_archive", msg_id, "", tenant_id=tenant_id)
            else:
                confirmed.append(f"\u274c {r.get('message')}")
        except Exception as e:
            confirmed.append(f"\u274c {str(e)[:80]}")

    for msg_id in re.findall(r'\[ACTION:READ:([^\]]+)\]', response):
        msg_id = msg_id.strip()
        if not is_valid_outlook_id(msg_id): continue
        try:
            perform_outlook_action("mark_as_read", {"message_id": msg_id}, token)
            log_activity(username, "mail_read", msg_id, "", tenant_id=tenant_id)
        except Exception:
            pass

    for match in re.finditer(r'\[ACTION:REPLY:([^\:\]]{20,}):(.+?)\]', response, re.DOTALL):
        msg_id = match.group(1).strip()
        reply_text = match.group(2).strip()
        # Normaliser les sauts de ligne (LLM ecrit parfois \n litteral)
        reply_text = reply_text.replace('\\n', '\n')
        if not is_valid_outlook_id(msg_id): continue
        # Lookup tolerant : exact d'abord, puis par prefixe de 20 chars
        orig = next((m for m in live_mails + mails_from_db if m.get('message_id') == msg_id), None)
        if orig is None:
            orig = next((m for m in live_mails + mails_from_db
                         if m.get('message_id', '')[:20] == msg_id[:20]), {})
        sender_name = orig.get('from_name') or orig.get('sender') or orig.get('from_email') or '?'
        subject     = orig.get('subject', '')
        to_email    = orig.get('from_email', orig.get('sender_email', ''))
        label = f"Repondre a {sender_name}" + (f" — {subject[:50]}" if subject else "")
        action_id = queue_action(
            tenant_id=tenant_id, username=username, action_type="REPLY",
            payload={"message_id": msg_id, "reply_text": reply_text,
                     "subject": subject, "to": to_email,
                     "sender_name": sender_name,
                     "from_email": from_email},
            label=label, conversation_id=conversation_id,
        )
        log_activity(username, "mail_reply_queued", msg_id, subject[:100], tenant_id=tenant_id)

    for msg_id in re.findall(r'\[ACTION:READBODY:([^\]]+)\]', response):
        msg_id = msg_id.strip()
        if not is_valid_outlook_id(msg_id): continue
        try:
            r = perform_outlook_action("get_message_body", {"message_id": msg_id}, token)
            if r.get("status") == "ok":
                confirmed.append(f"\U0001f4e7 Corps du mail :\n{r.get('body_text', '')[:800]}")
                log_activity(username, "mail_read", msg_id, "(body)", tenant_id=tenant_id)
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
            log_activity(username, "calendar_create", parts[0][:100], parts[1][:20], tenant_id=tenant_id)
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

    # SEND_MAIL : nouveau mail (pas une reponse) — mise en queue + confirmation
    for match in re.finditer(r'\[ACTION:SEND_MAIL:([^\|\]]+)\|([^\|\]]+)\|(.+?)\]', response, re.DOTALL):
        to_email    = match.group(1).strip()
        subject     = match.group(2).strip()
        body        = match.group(3).strip().replace('\\n', '\n')
        label       = f"Envoyer un mail a {to_email} — {subject[:50]}"
        action_id   = queue_action(
            tenant_id=tenant_id, username=username, action_type="SEND_MAIL",
            payload={"to_email": to_email, "subject": subject, "body": body,
                     "from_email": from_email},
            label=label, conversation_id=conversation_id,
        )
        log_activity(username, "mail_send_queued", to_email, subject[:100], tenant_id=tenant_id)

    return confirmed
