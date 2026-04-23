"""
Executeurs des tools exposes a Claude en mode agent (v2).

Chaque tool declare dans raya_tools.py a ici son executeur : la fonction
qui prend les parametres appeles par Claude et retourne le resultat a
lui transmettre dans la boucle.

Principes :
  - Reutilisation maximale des connecteurs existants (odoo_enrich, drive,
    mailbox_manager, etc.). On ne reecrit pas la logique, on l appelle.
  - Retour toujours en JSON serialisable (string, dict, list).
  - Erreurs : on les renvoie brutes a Claude qui decide (pas de try/except
    qui masquerait les problemes).
  - Actions d ecriture : on cree un pending_action et on retourne a Claude
    une confirmation que l action est en attente de validation utilisateur.
"""
import json
from typing import Any

from app.logging_config import get_logger
from app.routes.raya_tools import TOOLS_REQUIRING_CONFIRMATION

logger = get_logger("raya.tools.executors")


# ==========================================================================
# DISPATCHER PRINCIPAL
# ==========================================================================

def execute_tool(
    tool_name: str,
    tool_input: dict,
    username: str,
    tenant_id: str,
    conversation_id: int | None = None,
) -> str:
    """
    Point d entree unique pour l execution d un tool appele par Claude.

    Args:
        tool_name: nom du tool (ex: 'search_graph', 'send_mail')
        tool_input: parametres passes par Claude
        username: utilisateur authentifie
        tenant_id: tenant de l utilisateur
        conversation_id: id de la conversation aria_memory en cours

    Returns:
        Resultat serialise en JSON string, a transmettre a Claude en
        tool_result dans le prochain tour de boucle.
    """
    logger.info(
        "[ToolExec] %s called by %s (tenant=%s, conv=%s) input=%s",
        tool_name, username, tenant_id, conversation_id,
        json.dumps(tool_input)[:200],
    )

    try:
        if tool_name in TOOLS_REQUIRING_CONFIRMATION:
            return _execute_pending_action(
                tool_name, tool_input, username, tenant_id, conversation_id,
            )

        executor = _EXECUTORS.get(tool_name)
        if executor is None:
            return json.dumps({
                "error": f"Tool '{tool_name}' non implemente en v2",
                "hint": "Tool declare mais sans executeur associe",
            })

        result = executor(tool_input, username, tenant_id)
        return json.dumps(result, default=str, ensure_ascii=False)

    except Exception as e:
        logger.exception("[ToolExec] %s raised an error", tool_name)
        return json.dumps({
            "error": type(e).__name__,
            "message": str(e)[:500],
        })


# ==========================================================================
# EXECUTEURS — RECHERCHE / LECTURE
# ==========================================================================

def _execute_search_graph(inp: dict, username: str, tenant_id: str) -> dict:
    """Recherche dans le graphe semantique unifie."""
    from app.retrieval import unified_search, format_unified_results

    query = inp.get("query", "")
    max_results = inp.get("max_results", 20)

    data = unified_search(
        query=query,
        username=username,
        tenant_id=tenant_id,
        top_k_final=max_results,
    )
    formatted = format_unified_results(data, max_items=max_results)
    return {
        "query": query,
        "count": len(data.get("results", [])),
        "formatted": formatted,
        "raw_results": data.get("results", [])[:max_results],
    }


def _execute_search_odoo(inp: dict, username: str, tenant_id: str) -> dict:
    """Recherche semantique dans Odoo uniquement."""
    from app.retrieval import hybrid_search, format_search_results

    query = inp.get("query", "")
    max_results = inp.get("max_results", 10)

    data = hybrid_search(
        query=query,
        tenant_id=tenant_id,
        top_k_final=max_results,
    )
    formatted = format_search_results(data, max_items=max_results)
    return {
        "query": query,
        "count": len(data.get("results", [])) if isinstance(data, dict) else len(data),
        "formatted": formatted,
    }


def _execute_get_client_360(inp: dict, username: str, tenant_id: str) -> dict:
    """Vue 360 consolide d un client via API Odoo directe."""
    from app.connectors.odoo_client_360 import get_client_360

    client = inp.get("client_name_or_id", "")
    return get_client_360(
        key_or_id=client,
        include_mails=True,
        mail_username=username,
    )


def _execute_search_drive(inp: dict, username: str, tenant_id: str) -> dict:
    """Recherche dans les fichiers SharePoint."""
    # Utilise unified_search avec filtre source=drive
    from app.retrieval import unified_search, format_unified_results

    query = inp.get("query", "")
    max_results = inp.get("max_results", 10)

    data = unified_search(
        query=query,
        username=username,
        tenant_id=tenant_id,
        top_k_final=max_results,
        sources=["drive"],
    )
    return {
        "query": query,
        "count": len(data.get("results", [])),
        "formatted": format_unified_results(data, max_items=max_results),
    }


def _execute_search_mail(inp: dict, username: str, tenant_id: str) -> dict:
    """Recherche dans les mails analyses."""
    from app.retrieval import unified_search, format_unified_results

    query = inp.get("query", "")
    max_results = inp.get("max_results", 10)

    data = unified_search(
        query=query,
        username=username,
        tenant_id=tenant_id,
        top_k_final=max_results,
        sources=["mail"],
    )
    return {
        "query": query,
        "count": len(data.get("results", [])),
        "formatted": format_unified_results(data, max_items=max_results),
    }


def _execute_search_conversations(inp: dict, username: str, tenant_id: str) -> dict:
    """Recherche dans l historique des conversations passees."""
    from app.retrieval import unified_search, format_unified_results

    query = inp.get("query", "")
    max_results = inp.get("max_results", 5)

    data = unified_search(
        query=query,
        username=username,
        tenant_id=tenant_id,
        top_k_final=max_results,
        sources=["conversation"],
    )
    return {
        "query": query,
        "count": len(data.get("results", [])),
        "formatted": format_unified_results(data, max_items=max_results),
    }


def _execute_read_mail(inp: dict, username: str, tenant_id: str) -> dict:
    """Lit le contenu complet d un mail par son ID."""
    from app.database import get_pg_conn

    mail_id = inp.get("mail_id", "")
    conn = get_pg_conn()
    try:
        c = conn.cursor()
        c.execute(
            "SELECT subject, from_email, raw_body_preview, short_summary, "
            "received_at, mailbox_source FROM mail_memory "
            "WHERE id = %s AND username = %s "
            "  AND (tenant_id = %s OR tenant_id IS NULL)",
            (mail_id, username, tenant_id),
        )
        row = c.fetchone()
        if not row:
            return {"error": f"Mail {mail_id} introuvable"}
        return {
            "subject": row[0],
            "from": row[1],
            "body": row[2],
            "summary": row[3],
            "received_at": str(row[4]) if row[4] else None,
            "source": row[5],
        }
    finally:
        conn.close()


def _execute_read_drive_file(inp: dict, username: str, tenant_id: str) -> dict:
    """Lit le contenu d un fichier SharePoint par son ID."""
    from app.database import get_pg_conn

    file_id = inp.get("file_id", "")
    conn = get_pg_conn()
    try:
        c = conn.cursor()
        c.execute(
            "SELECT file_name, folder_path, mime_type, text_content, "
            "modified_at FROM drive_files "
            "WHERE id = %s AND tenant_id = %s",
            (file_id, tenant_id),
        )
        row = c.fetchone()
        if not row:
            return {"error": f"Fichier {file_id} introuvable"}
        content = row[3] or ""
        if len(content) > 8000:
            content = content[:8000] + "...(tronque)"
        return {
            "file_name": row[0],
            "folder_path": row[1],
            "mime_type": row[2],
            "content": content,
            "modified_at": str(row[4]) if row[4] else None,
        }
    finally:
        conn.close()


def _execute_web_search(inp: dict, username: str, tenant_id: str) -> dict:
    """
    Recherche web.

    Note : Anthropic expose le web_search nativement dans l API. Si on l active
    via le parametre `tools=[{type: 'web_search_20250305', name: 'web_search'}]`
    dans l appel API, Claude l utilisera sans passer par cet executeur.
    Cet executeur est un fallback si on veut piloter nous-memes.
    """
    # Pour l instant, on delegue a Anthropic. Cet executeur ne sera appele
    # que si on passe en mode "tool custom" plutot que "web_search natif".
    return {
        "notice": "Web search est gere nativement par l API Anthropic. "
                  "Voir la config dans raya_helpers.py."
    }


def _execute_get_weather(inp: dict, username: str, tenant_id: str) -> dict:
    """
    Meteo d une localisation.
    Non implemente en v2 initiale (pas de connecteur meteo dans le code
    actuel). A brancher plus tard via OpenWeatherMap ou similaire si besoin.
    """
    return {
        "error": "Connecteur meteo non disponible. Retire du registre v2 "
                 "initiale. Voir docs/a_faire.md pour le brancher plus tard.",
        "location": inp.get("location", "Romorantin-Lanthenay"),
    }


# ==========================================================================
# EXECUTEURS — CREATION DE CONTENU
# ==========================================================================

def _execute_create_file(inp: dict, username: str, tenant_id: str) -> dict:
    """
    Cree un fichier telechargeable (markdown, txt, csv).
    Note v2 : pas de connecteur dedie aux fichiers texte/markdown dans le code
    actuel. On retourne le contenu tel quel pour l instant. A enrichir plus tard
    avec un vrai generateur si besoin.
    """
    return {
        "notice": "create_file (md/txt/csv) sans stockage persistant en v2 initiale. "
                  "Utilise create_pdf ou create_excel pour un fichier reel.",
        "filename": inp.get("filename", "fichier"),
        "format": inp.get("format", "md"),
        "content": inp.get("content", ""),
    }


def _execute_create_pdf(inp: dict, username: str, tenant_id: str) -> dict:
    """Cree un PDF structure via file_creator."""
    from app.connectors.file_creator import create_pdf

    return create_pdf(
        title=inp.get("title", "Document"),
        content=inp.get("markdown_content", ""),
        username=username,
    )


def _execute_create_excel(inp: dict, username: str, tenant_id: str) -> dict:
    """
    Cree un fichier Excel via file_creator.
    Signature file_creator.create_excel : (title, data, headers, username)
    On convertit sheets en data + headers (feuille principale seulement).
    """
    from app.connectors.file_creator import create_excel

    sheets = inp.get("sheets", {})
    # Prendre la premiere feuille comme donnees principales
    if not sheets:
        return {"error": "Aucune donnee fournie dans sheets"}

    first_sheet_name = list(sheets.keys())[0]
    rows = sheets[first_sheet_name]
    if not rows:
        return {"error": "Feuille vide"}

    headers = rows[0] if rows else []
    data = rows[1:] if len(rows) > 1 else []

    return create_excel(
        title=inp.get("filename", "fichier").replace(".xlsx", ""),
        data=data,
        headers=headers,
        username=username,
    )


def _execute_create_image(inp: dict, username: str, tenant_id: str) -> dict:
    """Genere une image via DALL-E."""
    from app.connectors.dalle_connector import generate_image

    return generate_image(
        prompt=inp.get("prompt", ""),
        size=inp.get("size", "1024x1024"),
    )


# ==========================================================================
# EXECUTEURS — PREFERENCES DURABLES
# ==========================================================================

def _execute_remember_preference(inp: dict, username: str, tenant_id: str) -> dict:
    """Enregistre une preference durable dans aria_rules."""
    from app.memory_rules import save_rule

    category = inp.get("category", "general")
    preference = inp.get("preference", "")

    rule_id = save_rule(
        category=category,
        rule=preference,
        source="user_explicit",
        confidence=1.0,
        username=username,
        tenant_id=tenant_id,
        personal=False,
    )
    return {
        "status": "remembered",
        "rule_id": rule_id,
        "category": category,
        "preference": preference,
    }


def _execute_forget_preference(inp: dict, username: str, tenant_id: str) -> dict:
    """Supprime une preference."""
    from app.memory_rules import delete_rule

    preference_id = inp.get("preference_id", "")
    try:
        deleted = delete_rule(rule_id=int(preference_id), username=username)
    except (ValueError, TypeError):
        return {"status": "invalid_id", "preference_id": preference_id}
    return {
        "status": "forgotten" if deleted else "not_found",
        "preference_id": preference_id,
    }


# ==========================================================================
# GESTION DES PENDING_ACTIONS (actions necessitant confirmation)
# ==========================================================================

def _execute_pending_action(
    tool_name: str,
    tool_input: dict,
    username: str,
    tenant_id: str,
    conversation_id: int | None,
) -> str:
    """
    Pour les tools qui necessitent une carte de confirmation cote front :
      - On cree une entree dans pending_actions
      - On retourne a Claude un resume pour qu elle informe l utilisateur
      - L utilisateur validera/annulera via l UI
    """
    import json as _json
    from app.database import get_pg_conn

    # Mapping tool_name vers type d action attendu par le front
    ACTION_TYPE_MAP = {
        "send_mail": "SEND_MAIL",
        "reply_to_mail": "REPLY",
        "archive_mail": "ARCHIVE",
        "delete_mail": "DELETE",
        "create_calendar_event": "CREATE_EVENT",
        "send_teams_message": "TEAMS_MSG",
        "move_drive_file": "MOVEDRIVE",
    }

    action_type = ACTION_TYPE_MAP.get(tool_name, tool_name.upper())
    label = _generate_action_label(tool_name, tool_input)

    conn = get_pg_conn()
    try:
        c = conn.cursor()
        c.execute(
            """INSERT INTO pending_actions
               (username, tenant_id, action_type, action_label, payload_json,
                status, conversation_id, created_at)
               VALUES (%s, %s, %s, %s, %s, 'pending', %s, NOW())
               RETURNING id""",
            (username, tenant_id, action_type, label,
             _json.dumps(tool_input), conversation_id),
        )
        action_id = c.fetchone()[0]
        conn.commit()
    finally:
        conn.close()

    return _json.dumps({
        "status": "pending_confirmation",
        "action_id": action_id,
        "action_type": action_type,
        "label": label,
        "message": (
            f"Action '{tool_name}' preparee. Une carte de confirmation a ete "
            f"affichee a l utilisateur. L action sera executee apres validation."
        ),
    })


def _generate_action_label(tool_name: str, tool_input: dict) -> str:
    """Genere un label court pour afficher dans la carte de confirmation."""
    if tool_name == "send_mail":
        to = tool_input.get("to", "?")
        subj = tool_input.get("subject", "(sans objet)")[:50]
        return f"Envoyer mail a {to} : {subj}"
    if tool_name == "reply_to_mail":
        return f"Repondre au mail {tool_input.get('mail_id', '?')}"
    if tool_name == "archive_mail":
        return f"Archiver mail {tool_input.get('mail_id', '?')}"
    if tool_name == "delete_mail":
        return f"Mettre a la corbeille mail {tool_input.get('mail_id', '?')}"
    if tool_name == "create_calendar_event":
        return f"Creer RDV '{tool_input.get('title', '?')}' " \
               f"le {tool_input.get('start_time', '?')[:16]}"
    if tool_name == "send_teams_message":
        rcpt = tool_input.get("recipient", "?")
        msg = tool_input.get("message", "")[:40]
        return f"Message Teams a {rcpt} : {msg}"
    if tool_name == "move_drive_file":
        return f"Deplacer fichier {tool_input.get('file_id', '?')}"
    return f"Action {tool_name}"


# ==========================================================================
# MAPPING TOOL_NAME -> EXECUTEUR
# ==========================================================================
# Les tools d ecriture (dans TOOLS_REQUIRING_CONFIRMATION) ne figurent pas
# ici : ils passent par _execute_pending_action.

_EXECUTORS: dict[str, Any] = {
    # Recherche / lecture
    "search_graph": _execute_search_graph,
    "search_odoo": _execute_search_odoo,
    "get_client_360": _execute_get_client_360,
    "search_drive": _execute_search_drive,
    "search_mail": _execute_search_mail,
    "search_conversations": _execute_search_conversations,
    "read_mail": _execute_read_mail,
    "read_drive_file": _execute_read_drive_file,
    "web_search": _execute_web_search,
    # "get_weather": retire en v2 initiale (pas de connecteur meteo)
    # Creation de contenu (sans confirmation)
    "create_file": _execute_create_file,
    "create_pdf": _execute_create_pdf,
    "create_excel": _execute_create_excel,
    "create_image": _execute_create_image,
    # Preferences durables
    "remember_preference": _execute_remember_preference,
    "forget_preference": _execute_forget_preference,
}
