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
    from app.connectors.drive_connector import (
        move_item, copy_item, _find_sharepoint_site_and_drive,
    )
    from app.connectors.teams_connector import (
        send_channel_message, send_chat_message,
        send_message_to_user, create_group_chat,
    )

    action_type = action["action_type"]
    payload = action["payload"]
    try:
        if action_type == "REPLY":
            r = perform_outlook_action("send_reply", {
                "message_id": payload["message_id"],
                "reply_body": payload["reply_text"],
            }, outlook_token)
            to_label = payload.get("sender_name") or payload.get("to") or ""
            msg = f"Reponse envoyee a {to_label}" if to_label else "Reponse envoyee"
            return {"ok": r.get("status") == "ok", "message": msg,
                    "error": r.get("message", "envoi echoue")}

        if action_type == "SEND_MAIL":
            r = perform_outlook_action("send_new_mail", {
                "to_email": payload["to_email"],
                "subject":  payload["subject"],
                "body":     payload["body"],
            }, outlook_token)
            msg = f"Mail envoye a {payload.get('to_email', '?')}"
            return {"ok": r.get("status") == "ok", "message": msg,
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
