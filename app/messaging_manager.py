"""
Messaging Manager — résolution automatique des connecteurs de messagerie.

get_user_messengers(username) → liste tous les MessagingConnector actifs.
get_messenger_for(username, hint) → résout le bon provider selon un hint.

Ajouter un provider :
  1. Créer la classe dans connectors/
  2. L'enregistrer dans PROVIDER_MAP
  C'est tout.
"""
from __future__ import annotations
from app.connectors.messaging_connector import MessagingConnector
from app.logging_config import get_logger

logger = get_logger("raya.messaging_manager")


def _get_provider_map() -> dict:
    from app.connectors.teams_connector2 import TeamsConnector
    return {
        "teams":     TeamsConnector,
        "microsoft": TeamsConnector,
        # "slack":     SlackConnector,     # futur
        # "whatsapp":  WhatsAppConnector,  # futur
    }


def get_user_messengers(username: str) -> list[MessagingConnector]:
    """
    Retourne tous les connecteurs de messagerie actifs pour un utilisateur.
    Ordre : V2 (tenant_connections) → legacy Microsoft token.
    """
    messengers = []
    seen = set()
    provider_map = _get_provider_map()

    # 1. Connexions V2 (tenant_connections)
    try:
        from app.connection_token_manager import get_user_tool_connections
        v2 = get_user_tool_connections(username)
        for tool_type, info in v2.items():
            cls = provider_map.get(tool_type.lower())
            if not cls or tool_type in seen:
                continue
            token = info.get("token", "")
            if not token:
                continue
            seen.add(tool_type)
            messengers.append(cls(username=username, token=token,
                                  config={"label": info.get("label", "")}))
            logger.debug("[MsgMgr] V2: %s", tool_type)
    except Exception as e:
        logger.warning("[MsgMgr] V2 error: %s", e)

    # 2. Legacy — Microsoft Teams token
    if "teams" not in seen and "microsoft" not in seen:
        try:
            from app.connection_token_manager import get_connection_token
            token = get_connection_token(username, "microsoft")
            if token:
                from app.connectors.teams_connector2 import TeamsConnector
                messengers.append(TeamsConnector(username=username, token=token))
                seen.add("teams")
                logger.debug("[MsgMgr] Legacy Teams: %s", username)
        except Exception as e:
            logger.warning("[MsgMgr] Legacy Teams error: %s", e)

    logger.info("[MsgMgr] %s: %d messenger(s)", username, len(messengers))
    return messengers


def get_messenger_for(username: str, hint: str = "") -> MessagingConnector | None:
    """
    Résout le messenger à utiliser selon un hint.
    hint = 'teams' | 'slack' | 'whatsapp' | '' (auto)
    """
    messengers = get_user_messengers(username)
    if not messengers:
        return None
    if not hint:
        return messengers[0]
    h = hint.lower().strip()
    teams_aliases = {"teams", "microsoft", "ms teams", "équipe", "equipe"}
    slack_aliases  = {"slack"}
    wa_aliases     = {"whatsapp", "wp", "wapp"}
    for m in messengers:
        if m.provider == "teams"    and h in teams_aliases: return m
        if m.provider == "slack"    and h in slack_aliases:  return m
        if m.provider == "whatsapp" and h in wa_aliases:     return m
        if h in m.provider:                                   return m
    return messengers[0]


def get_messaging_summary(username: str) -> str:
    """Résumé lisible pour le prompt Raya."""
    messengers = get_user_messengers(username)
    if not messengers:
        return "Aucune messagerie connectée."
    return ", ".join(m.display_name for m in messengers)
