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


def _queue_send_mail(username, tenant_id, mailbox_hint, to_email, subject, body,
                     conversation_id, default_from_email, seen_set, confirmed):
    """
    Met en queue un envoi de mail vers le bon connecteur.
    mailbox_hint : email, 'gmail', 'microsoft', '' (auto)
    """
    # Check permission (Plan : docs/raya_permissions_plan.md etape 3)
    # SEND_MAIL necessite 'read_write' minimum. Si refuse, on skip avec message.
    try:
        from app.permissions import check_permission
        allowed, reason = check_permission(
            tenant_id=tenant_id, username=username,
            action_tag="SEND_MAIL",
            user_input_excerpt=f"To: {to_email} / Subject: {subject[:100]}",
        )
        if not allowed:
            confirmed.append(f"🔒 Envoi mail bloque : {reason}")
            return
    except Exception:
        pass  # En cas d erreur systeme permissions, on autorise par securite

    dedup_key = (to_email.lower(), subject.lower())
    if dedup_key in seen_set:
        return
    seen_set.add(dedup_key)

    # Résoudre le connecteur
    connector = None
    from_email_resolved = default_from_email
    action_type = "SEND_MAIL"
    try:
        from app.mailbox_manager import get_connector_for_mailbox
        connector = get_connector_for_mailbox(username, mailbox_hint)
        if connector:
            from_email_resolved = connector.email
            action_type = "SEND_GMAIL" if connector.provider == "gmail" else "SEND_MAIL"
    except Exception:
        pass

    label = f"{'Gmail' if action_type == 'SEND_GMAIL' else 'Mail'} → {to_email} — {subject[:50]}"
    queue_action(
        tenant_id=tenant_id, username=username, action_type=action_type,
        payload={
            "to_email": to_email, "subject": subject, "body": body,
            "from_email": from_email_resolved,
            "mailbox_hint": mailbox_hint,  # conservé pour la confirmation
        },
        label=label, conversation_id=conversation_id,
    )
    source = "gmail" if action_type == "SEND_GMAIL" else "mail"
    log_activity(username, f"{source}_send_queued", to_email, subject[:100], tenant_id=tenant_id)


def _handle_mail_actions(response, token, mail_can_delete, mails_from_db, live_mails,
                         username, tenant_id, conversation_id, from_email=""):
    confirmed = []
    processed_ids = set()

    # SEARCH_CONTACTS : cherche dans TOUTES les boîtes connectées de l'utilisateur
    for match in re.finditer(r'\[ACTION:SEARCH_CONTACTS:([^\]]+)\]', response):
        query = match.group(1).strip()
        try:
            from app.mailbox_manager import search_contacts_all
            results = search_contacts_all(username, query)
            if results:
                c = results[0]
                confirmed.append(f"📇 Contact trouvé ({c['source']}) : {c['name']} → {c['email']}")
            else:
                confirmed.append(f"📇 Contact '{query}' introuvable dans aucune boîte connectée — demande l'adresse à l'utilisateur.")
        except Exception as e:
            confirmed.append(f"📇 Recherche contact échouée : {str(e)[:80]}")

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

    # Dédup REPLY par message_id pour éviter le double-queue si le LLM génère 2 tags
    _seen_reply_ids = set()
    for match in re.finditer(r'\[ACTION:REPLY:([^\:\]]{20,}):(.+?)\]', response, re.DOTALL):
        msg_id = match.group(1).strip()
        if msg_id in _seen_reply_ids:
            continue
        _seen_reply_ids.add(msg_id)
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

    # ── ENVOI MAIL UNIFIÉ ────────────────────────────────────────────────
    # Format nouveau (4 champs) : [ACTION:SEND_MAIL:boite|to|sujet|corps]
    #   boite = email, 'gmail', 'microsoft', 'perso', 'pro', '' (auto)
    # Format ancien (3 champs) : [ACTION:SEND_MAIL:to|sujet|corps]
    #   → backward compat, utilise le premier connecteur disponible
    _seen_send = set()

    for match in re.finditer(
        r'\[ACTION:SEND_MAIL:([^\|\]]+)\|([^\|\]]+)\|([^\|\]]+)\|(.+?)\]',
        response, re.DOTALL
    ):
        # Nouveau format : boite | to | sujet | corps
        mailbox_hint = match.group(1).strip()
        to_email     = match.group(2).strip()
        subject      = match.group(3).strip()
        body         = match.group(4).strip().replace('\\n', '\n')
        _queue_send_mail(
            username, tenant_id, mailbox_hint, to_email, subject, body,
            conversation_id, from_email, _seen_send, confirmed
        )

    for match in re.finditer(
        r'\[ACTION:SEND_MAIL:([^\|\]]+)\|([^\|\]]+)\|(.+?)\]',
        response, re.DOTALL
    ):
        # Ancien format (3 champs) : to | sujet | corps
        # S'assurer qu'il ne matche pas les 4-champs déjà traités
        full = match.group(0)
        if full.count('|') >= 3:
            continue
        to_email = match.group(1).strip()
        subject  = match.group(2).strip()
        body     = match.group(3).strip().replace('\\n', '\n')
        _queue_send_mail(
            username, tenant_id, "", to_email, subject, body,
            conversation_id, from_email, _seen_send, confirmed
        )

    # Backward compat : SEND_GMAIL → routé vers connecteur Gmail
    for match in re.finditer(
        r'\[ACTION:SEND_GMAIL:([^\|\]]+)\|([^\|\]]+)\|(.+?)\]',
        response, re.DOTALL
    ):
        to_email = match.group(1).strip()
        subject  = match.group(2).strip()
        body     = match.group(3).strip().replace('\\n', '\n')
        _queue_send_mail(
            username, tenant_id, "gmail", to_email, subject, body,
            conversation_id, from_email, _seen_send, confirmed
        )

    # CREATE_CONTACT : [ACTION:CREATE_CONTACT:Nom|email|téléphone_optionnel]
    for match in re.finditer(r'\[ACTION:CREATE_CONTACT:([^\|\]]+)\|([^\|\]]+)(?:\|([^\]]*))?\]', response):
        name  = match.group(1).strip()
        email = match.group(2).strip()
        phone = (match.group(3) or "").strip()
        try:
            from app.mailbox_manager import create_contact_best
            result = create_contact_best(username, name, email, phone)
            confirmed.append(f"📇 {result['message']}")
        except Exception as e:
            confirmed.append(f"📇 Erreur création contact : {str(e)[:80]}")

    return confirmed
