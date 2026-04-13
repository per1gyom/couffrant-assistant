"""
Module actions — execution des actions Raya.
Exporte execute_actions et _ASK_CHOICE_PREFIX.
"""
import re

from app.routes.actions.mail_actions import is_valid_outlook_id
from app.routes.actions.confirmations import _handle_confirmations
from app.routes.actions.mail_actions import _handle_mail_actions
from app.routes.actions.drive_actions import _handle_drive_actions
from app.routes.actions.teams_actions import _handle_teams_actions
from app.routes.actions.memory_actions import _handle_memory_actions, _handle_ask_choice
from app.routes.actions.collab_actions import _handle_collab_actions
from app.rule_engine import get_memoire_param
from app.memory_loader import MEMORY_OK

_ASK_CHOICE_PREFIX = "__CHOICE__:"


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

    # 8-COLLAB : partage d'événements avec l'équipe
    confirmed += _handle_collab_actions(raya_response, username, tenant_id)

    # TOOL-CREATE-FILES : génération PDF et Excel à la demande
    create_matches = re.findall(
        r'\[ACTION:(CREATE_PDF|CREATE_EXCEL):([^\]]*)\]',
        raya_response
    )
    for action_name, action_data in create_matches:
        try:
            from app.router import execute_create_action
            link = execute_create_action(
                f"ACTION:{action_name}:{action_data}",
                username,
                tenant_id,
            )
            confirmed.append(link)
        except Exception as e:
            confirmed.append(f"❌ Erreur création fichier : {str(e)[:80]}")

    confirmed += _handle_ask_choice(raya_response)

    return confirmed


__all__ = ["execute_actions", "_ASK_CHOICE_PREFIX"]
