"""
Gestion des confirmations / annulations d'actions en attente.
"""
import re
from app.routes.actions.mail_actions import is_valid_outlook_id
from app.pending_actions import confirm_action, cancel_action, mark_executed, mark_failed


def _handle_confirmations(response, username, tenant_id, outlook_token, tools):
    confirmed = []

    for match in re.finditer(r'\[ACTION:CONFIRM:(\d+)\]', response):
        action_id = int(match.group(1))
        action = confirm_action(action_id, username, tenant_id)
        if not action:
            confirmed.append(f"\u274c Action #{action_id} introuvable, deja traitee ou expiree.")
            continue
        action["username"] = username
        action["tenant_id"] = tenant_id
        result = _execute_confirmed_action(action, outlook_token, tools)
        label = action.get("label") or f"#{action_id}"
        if result.get("ok"):
            mark_executed(action_id, result)
            confirmed.append(f"\u2705 {result.get('message', 'Action executee')} — {label}")
        else:
            mark_failed(action_id, result.get("error", "erreur inconnue"))
            confirmed.append(f"\u274c Echec ({label}) : {result.get('error', 'erreur inconnue')}")

    for match in re.finditer(r'\[ACTION:CANCEL:(\d+)\]', response):
        action_id = int(match.group(1))
        # Lire le label avant d'annuler
        from app.pending_actions import get_action
        action_info = get_action(action_id, username, tenant_id)
        label = (action_info.get("label") if action_info else None) or f"#{action_id}"
        ok = cancel_action(action_id, username, tenant_id, reason="Annule par l'utilisateur")
        confirmed.append(
            f"\u23f9\ufe0f Annule : {label}" if ok
            else f"\u274c Action #{action_id} introuvable."
        )

    return confirmed


def _execute_confirmed_action(action: dict, outlook_token: str, tools: dict) -> dict:
    from app.connectors.outlook_connector import perform_outlook_action
    from app.connectors.teams_connector import (
        send_channel_message, send_chat_message,
        send_message_to_user, create_group_chat,
    )

    action_type = action["action_type"]
    payload = action["payload"]
    username = action.get("username", "")
    tenant_id = action.get("tenant_id", "")

    # ── MUR PHYSIQUE PERMISSIONS (defense en profondeur, 04/05/2026) ──
    # Re-check au moment de l execution reelle. Meme si une carte avait
    # ete creee en pending (ce qui ne devrait pas arriver depuis le check
    # dans _execute_pending_action), on verifie une seconde fois ici. Si
    # l admin a modifie la permission entre la creation et la confirmation,
    # le verdict reflete l etat courant.
    _ACTION_TYPE_TO_TOOL = {
        "SEND_MAIL": "send_mail", "SEND_GMAIL": "send_mail",
        "REPLY": "reply_to_mail",
        "ARCHIVE": "archive_mail",
        "DELETE": "delete_mail", "DELETE_GROUPED": "delete_mail",
        "CREATE_EVENT": "create_calendar_event",
        "CREATEEVENT":  "create_calendar_event",
        "UPDATE_EVENT": "create_calendar_event",
        "DELETE_EVENT": "create_calendar_event",
        "TEAMS_MSG": "send_teams_message",
        "TEAMS_REPLYCHAT": "send_teams_message",
        "TEAMS_SENDCHANNEL": "send_teams_message",
        "TEAMS_GROUPE": "send_teams_message",
        "MOVEDRIVE": "move_drive_file",
        "COPYFILE": "move_drive_file",
    }
    tool_name_eq = _ACTION_TYPE_TO_TOOL.get(action_type)
    if tool_name_eq and tenant_id:
        # Construire un tool_input minimal pour la resolution
        if action_type == "DELETE_GROUPED":
            ids = payload.get("message_ids", [])
            check_input = {"mail_id": ids[0]} if ids else {}
        elif action_type in ("DELETE", "ARCHIVE", "REPLY"):
            check_input = {"mail_id": payload.get("message_id") or payload.get("mail_id", "")}
        elif action_type in ("SEND_MAIL", "SEND_GMAIL"):
            provider = "gmail" if action_type == "SEND_GMAIL" else (
                payload.get("mailbox_hint") or payload.get("provider", "")
            )
            check_input = {"provider": provider}
        else:
            check_input = dict(payload) if isinstance(payload, dict) else {}
        try:
            from app.permissions import check_permission_for_tool
            verdict = check_permission_for_tool(
                tenant_id=tenant_id, username=username,
                tool_name=tool_name_eq, tool_input=check_input,
                user_input_excerpt=f"confirm action {action.get('id', '?')}",
            )
            if not verdict.get("allowed", True):
                return {
                    "ok": False,
                    "error": verdict.get("reason", "Action refusee par les permissions"),
                    "permission_denied": True,
                    "details": verdict.get("details", {}),
                }
        except Exception:
            # Erreur du systeme permissions -> on bloque par securite
            return {"ok": False, "error": "Erreur systeme permissions, action bloquee par securite."}

    try:
        if action_type == "REPLY":
            r = perform_outlook_action("send_reply", {
                "message_id": payload["message_id"],
                "reply_body": payload["reply_text"],
            }, outlook_token, username=username)
            to_label = payload.get("sender_name") or payload.get("to") or ""
            msg = f"Reponse envoyee a {to_label}" if to_label else "Reponse envoyee"
            return {"ok": r.get("status") == "ok", "message": msg,
                    "error": r.get("message", "envoi echoue")}

        if action_type in ("SEND_MAIL", "SEND_GMAIL"):
            # Envoi unifié via MailboxConnector
            from app.mailbox_manager import get_connector_for_mailbox
            mailbox_hint = payload.get("mailbox_hint") or payload.get("from_email", "")
            # Pour SEND_GMAIL sans hint → forcer gmail
            if action_type == "SEND_GMAIL" and not mailbox_hint:
                mailbox_hint = "gmail"
            connector = get_connector_for_mailbox(username, mailbox_hint)
            if not connector:
                return {"ok": False, "message": "Aucune boîte mail connectée.", "error": "no_connector"}
            body = payload.get("body", "")
            result = connector.send_mail(
                to=payload.get("to_email", ""),
                subject=payload.get("subject", ""),
                body=body,
                from_email=payload.get("from_email", ""),
            )
            ok = result.get("ok", False)
            return {"ok": ok,
                    "message": result.get("message", f"Mail envoyé à {payload.get('to_email','?')}" if ok else "Erreur envoi"),
                    "error": result.get("message", "") if not ok else ""}

        if action_type == "DELETE":
            # Suppression d UN mail (tool agentique delete_mail).
            # Bug fix 04/05/2026 : avant, seul DELETE_GROUPED etait gere
            # ce qui produisait "Type d action inconnu : DELETE" au clic
            # sur la carte de confirmation.
            mail_id = payload.get("mail_id") or payload.get("message_id", "")
            if not mail_id:
                return {"ok": False, "error": "mail_id manquant dans le payload"}
            try:
                r = perform_outlook_action("delete_message",
                                           {"message_id": mail_id}, outlook_token)
                if r.get("status") == "ok":
                    return {"ok": True, "message": "Mail mis a la corbeille."}
                return {"ok": False, "error": r.get("message", "echec suppression")}
            except Exception as e:
                return {"ok": False, "error": str(e)[:200]}

        if action_type == "ARCHIVE":
            # Archivage d UN mail (tool agentique archive_mail).
            # Bug fix 04/05/2026 : handler manquant.
            mail_id = payload.get("mail_id") or payload.get("message_id", "")
            if not mail_id:
                return {"ok": False, "error": "mail_id manquant dans le payload"}
            try:
                r = perform_outlook_action("archive_message",
                                           {"message_id": mail_id}, outlook_token)
                if r.get("status") == "ok":
                    return {"ok": True, "message": "Mail archive."}
                return {"ok": False, "error": r.get("message", "echec archivage")}
            except Exception as e:
                return {"ok": False, "error": str(e)[:200]}

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

        if action_type in ("TEAMS_MSG", "TEAMS_REPLYCHAT", "TEAMS_SENDCHANNEL", "TEAMS_GROUPE"):
            from app.messaging_manager import get_messenger_for
            provider_hint = payload.get("provider", "teams")
            m = get_messenger_for(username, provider_hint)
            if not m:
                return {"ok": False, "error": "Aucun système de messagerie connecté."}
            if action_type == "TEAMS_MSG":
                r = m.send_message(payload["email"], payload["text"])
            elif action_type == "TEAMS_REPLYCHAT":
                r = m.reply_conversation(payload["chat_id"], payload["text"])
            elif action_type == "TEAMS_SENDCHANNEL":
                r = m.send_channel(payload["team_id"], payload["channel_id"], payload["text"])
            elif action_type == "TEAMS_GROUPE":
                r = m.send_group(payload["emails"], payload["topic"], payload["text"])
            return {"ok": r.get("ok", False), "message": r.get("message", "Envoyé"),
                    "error": r.get("message", "") if not r.get("ok") else ""}

        if action_type == "MOVEDRIVE":
            if not tools.get("drive_write"):
                return {"ok": False, "error": "Écriture Drive non autorisée"}
            from app.drive_manager import get_drive_for
            drive = get_drive_for(username, payload.get("drive_hint", ""))
            if not drive:
                return {"ok": False, "error": "Aucun drive connecté."}
            result = drive.move(payload["item_id"], payload["dest_id"], payload.get("new_name", ""))
            return {"ok": result.get("ok", False), "message": result.get("message", "Déplacé"),
                    "error": result.get("message", "") if not result.get("ok") else ""}

        if action_type == "COPYFILE":
            if not tools.get("drive_write"):
                return {"ok": False, "error": "Écriture Drive non autorisée"}
            from app.drive_manager import get_drive_for
            drive = get_drive_for(username, payload.get("drive_hint", ""))
            if not drive:
                return {"ok": False, "error": "Aucun drive connecté."}
            result = drive.copy(payload["source_id"], payload["dest_id"], payload.get("new_name", ""))
            return {"ok": result.get("ok", False), "message": result.get("message", "Copié"),
                    "error": result.get("message", "") if not result.get("ok") else ""}

        if action_type == "CREATEEVENT":
            # Utiliser le manager unifié (Microsoft + Google Calendar)
            from app.mailbox_manager import execute_calendar_action
            provider = payload.get("calendar_provider", "")  # 'microsoft' | 'gmail' | ''
            result = execute_calendar_action(
                username=username,
                action="create",
                provider_hint=provider,
                title=payload.get("subject", ""),
                start=payload.get("start", ""),
                end=payload.get("end", ""),
                location=payload.get("location", ""),
                description=payload.get("description", ""),
                attendees=payload.get("attendees", []),
            )
            return {"ok": result.get("ok", False), "message": result.get("message", "Événement créé"),
                    "error": result.get("message", "") if not result.get("ok") else ""}

        if action_type == "UPDATE_EVENT":
            from app.mailbox_manager import execute_calendar_action
            result = execute_calendar_action(
                username=username, action="update",
                provider_hint=payload.get("calendar_provider", ""),
                event_id=payload.get("event_id", ""),
                **{k: v for k, v in payload.items() if k not in ("event_id", "calendar_provider")}
            )
            return {"ok": result.get("ok", False), "message": result.get("message", ""),
                    "error": result.get("message", "") if not result.get("ok") else ""}

        if action_type == "DELETE_EVENT":
            from app.mailbox_manager import execute_calendar_action
            result = execute_calendar_action(
                username=username, action="delete",
                provider_hint=payload.get("calendar_provider", ""),
                event_id=payload.get("event_id", ""),
            )
            return {"ok": result.get("ok", False), "message": result.get("message", ""),
                    "error": result.get("message", "") if not result.get("ok") else ""}

        return {"ok": False, "error": f"Type d'action inconnu : {action_type}"}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}
