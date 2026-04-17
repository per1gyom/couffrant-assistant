"""
_raya_core + _build_user_content extraits de raya.py -- SPLIT-R1.
"""
import json,os,re,threading,concurrent.futures
from typing import Optional
from fastapi import Request
from app.llm_client import llm_complete,log_llm_usage
from app.router import route_query_tier,detect_session_theme,detect_query_domains
from app.database import get_pg_conn
from app.connection_token_manager import get_connection_token


def _get_microsoft_token(username: str) -> str | None:
    """Résout le token Microsoft via tenant_connections (V2)."""
    return get_connection_token(username, "microsoft")
from app.memory_loader import MEMORY_OK,synthesize_session
from app.rule_engine import get_memoire_param
from app.feedback_store import get_global_instructions
from app.pending_actions import get_pending
from app.feedback import save_response_metadata
from app.tenant_manager import get_user_tenants
from app.logging_config import get_logger
from app.routes.aria_context import (
    load_user_tools,load_db_context,load_live_mails,load_agenda,
    load_teams_context,load_mail_filter_summary,build_system_prompt,
)
from app.routes.actions import execute_actions,_ASK_CHOICE_PREFIX
from app.rate_limiter import check_rate_limit
from app.routes.raya_content import _build_user_content  # noqa
from pydantic import BaseModel
_SHARED_POOL=concurrent.futures.ThreadPoolExecutor(max_workers=6)
logger=get_logger("raya.core")


def _strip_action_tags(text: str) -> str:
    """Retire les tags [ACTION:...] en gérant les crochets imbriqués (domaines Odoo, JSON)."""
    result = []
    i = 0
    n = len(text)
    while i < n:
        # Détecter le début d'un tag ACTION (avec ou sans backtick)
        rest = text[i:]
        if rest.startswith('[ACTION:') or rest.startswith('`[ACTION:'):
            skip_bt = 1 if text[i] == '`' else 0
            j = i + skip_bt
            depth = 0
            while j < n:
                if text[j] == '[':
                    depth += 1
                elif text[j] == ']':
                    depth -= 1
                    if depth == 0:
                        j += 1
                        break
                j += 1
            # Skip backtick fermant
            if j < n and text[j] == '`':
                j += 1
            i = j
        else:
            result.append(text[i])
            i += 1
    return ''.join(result)


class RayaQuery(BaseModel):
    query: str
    file_data: Optional[str] = None
    file_type: Optional[str] = None
    file_name: Optional[str] = None


class FeedbackPayload(BaseModel):
    aria_memory_id: int
    feedback_type: str
    comment: Optional[str] = None


def _raya_core(request: Request, payload: RayaQuery, username: str, tenant_id: str) -> dict:

    # 1. Contexte DB + tokens
    tools = load_user_tools(username)
    db_ctx = load_db_context(username)
    instructions = get_global_instructions(tenant_id=tenant_id)
    outlook_token = _get_microsoft_token(username)

    # 5D-2f : charger les tenants de l'utilisateur
    user_tenants = get_user_tenants(username)

    # 2. Appels réseau en parallèle
    live_mails, agenda, teams_ctx, mail_filter = [], [], "", ""
    f_mails  = _SHARED_POOL.submit(load_live_mails, outlook_token, username)
    f_agenda = _SHARED_POOL.submit(load_agenda, outlook_token, username)
    f_teams  = _SHARED_POOL.submit(load_teams_context, username)
    f_filter = _SHARED_POOL.submit(load_mail_filter_summary, username)
    try: live_mails  = f_mails.result(timeout=5)
    except Exception: pass
    try: agenda      = f_agenda.result(timeout=5)
    except Exception: pass
    try: teams_ctx   = f_teams.result(timeout=5)
    except Exception: pass
    try: mail_filter = f_filter.result(timeout=3)
    except Exception: pass

    # 3. Actions en attente
    pending_list = get_pending(username=username, tenant_id=tenant_id, limit=10)

    # 4. Routage tier + détection thématique — en parallèle
    model_tier, session_theme = "smart", None
    f_tier  = _SHARED_POOL.submit(route_query_tier, payload.query or "",
                                  username, tenant_id, len(db_ctx["history"]))
    f_theme = _SHARED_POOL.submit(detect_session_theme, db_ctx["history"])
    try: model_tier    = f_tier.result(timeout=4)
    except Exception: pass
    try: session_theme = f_theme.result(timeout=3)
    except Exception: pass

    if session_theme:
        logger.info("[Raya] Session thematique detectee pour %s : '%s'", username, session_theme)

    # 4b. Detection des domaines pertinents pour injection dynamique des actions
    domains = detect_query_domains(payload.query or "")

    # 5. Construction du prompt systeme
    user_content_parts = _build_user_content(payload)
    system = build_system_prompt(
        username=username, tenant_id=tenant_id, query=payload.query or "",
        tools=tools, db_ctx=db_ctx, outlook_token=outlook_token,
        live_mails=live_mails, agenda=agenda, instructions=instructions,
        teams_context=teams_ctx, mail_filter_summary=mail_filter,
        pending_actions=pending_list,
        session_theme=session_theme,
        domains=domains,
        user_tenants=user_tenants,
    )

    # 6. Appel LLM (WEB-SEARCH : active selon variable d'environnement)
    messages = []
    for h in db_ctx["history"]:
        messages.append({"role": "user",      "content": h["user_input"]})
        messages.append({"role": "assistant", "content": h["aria_response"]})
    messages.append({"role": "user", "content": user_content_parts})

    web_enabled = os.getenv("RAYA_WEB_SEARCH_ENABLED", "true").lower() == "true"

    result = llm_complete(
        messages=messages, model_tier=model_tier,
        max_tokens=8192, system=system,
        web_search=web_enabled,
    )
    raya_response = result["text"]
    model_name    = result["model"]
    log_llm_usage(result, username=username, tenant_id=tenant_id,
                  purpose="raya_main_conversation")

    # Nettoyage : retire toutes les balises techniques de la réponse affichée
    clean_response = _strip_action_tags(raya_response)
    speak_speed = None
    speed_match = re.search(r'\[SPEAK_SPEED:([\d.]+)\]', clean_response)
    if speed_match:
        speak_speed = float(speed_match.group(1))
    clean_response = re.sub(r'`?\[SPEAK_SPEED:[^\]]*\]`?', '', clean_response)
    # Fragments Odoo inline
    clean_response = re.sub(r'\|?\["[^"]*"(?:,"[^"]*")*\](?:\|?\d*\]?)?', '', clean_response)
    clean_response = re.sub(r'^\s*\|?\["[^"]+".*$', '', clean_response, flags=re.MULTILINE)
    clean_response = re.sub(r'``', '', clean_response)
    clean_response = re.sub(r'\n{3,}', '\n\n', clean_response).strip()

    # 7→10. Sauvegarde AVANT execute_actions pour avoir l'aria_memory_id comme conversation_id
    aria_memory_id = None
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute(
            "INSERT INTO aria_memory (username, user_input, aria_response) VALUES (%s, %s, %s) RETURNING id",
            (username, payload.query, clean_response)
        )
        aria_memory_id = c.fetchone()[0]
        conn.commit()
    finally:
        if conn: conn.close()

    # 7. Execution des actions (avec aria_memory_id pour lier les cartes à l'échange)
    actions_raw = execute_actions(
        raya_response=raya_response, username=username, tenant_id=tenant_id,
        outlook_token=outlook_token, mails_from_db=db_ctx["mails_from_db"],
        live_mails=live_mails, tools=tools, conversation_id=aria_memory_id,
    )

    # 8. Extraction ASK_CHOICE du flux confirmed
    ask_choice = None
    actions_confirmed = []
    for item in actions_raw:
        if item.startswith(_ASK_CHOICE_PREFIX):
            try:
                ask_choice = json.loads(item[len(_ASK_CHOICE_PREFIX):])
            except Exception:
                pass
        else:
            actions_confirmed.append(item)

    # 10b. Log d'activite (7-ACT)
    try:
        from app.activity_log import log_activity
        log_activity(username, "conversation", str(aria_memory_id),
                     payload.query[:100] if payload.query else "", tenant_id)
    except Exception:
        pass

    # 10c. Marquage rapport livre si l'utilisateur le demande dans le chat (7-6D)
    try:
        from app.routes.actions.report_actions import get_today_report, mark_report_delivered
        report = get_today_report(username)
        if report and not report["delivered"] and len(clean_response) > 200:
            query_lower = (payload.query or "").lower()
            if "rapport" in query_lower or "resume" in query_lower:
                mark_report_delivered(report["id"], "chat")
    except Exception:
        pass

    # 11. Metadonnees en background
    if aria_memory_id:
        try:
            from app.rag import retrieve_rules
            rule_ids = retrieve_rules(payload.query or "", username, tenant_id).get("ids", [])
        except Exception:
            rule_ids = []
        threading.Thread(
            target=save_response_metadata,
            args=(aria_memory_id, username, tenant_id, model_tier, model_name, True, rule_ids),
            daemon=True,
        ).start()

    # 12. Synthese auto
    synth_threshold = get_memoire_param(username, "synth_threshold", 15)
    if MEMORY_OK and db_ctx["conv_count"] > 0 and db_ctx["conv_count"] % synth_threshold == 0:
        try:
            threading.Thread(
                target=lambda u=username, t=tenant_id: synthesize_session(synth_threshold, u, tenant_id=t),
                daemon=True,
            ).start()
        except Exception:
            pass

    # 13. Actions en attente mises a jour
    updated_pending = get_pending(username=username, tenant_id=tenant_id, limit=10)

    return {
        "answer":          clean_response,
        "actions":         actions_confirmed,
        "pending_actions": updated_pending,
        "aria_memory_id":  aria_memory_id,
        "model_tier":      model_tier,
        "ask_choice":      ask_choice,
        "speak_speed":     speak_speed,
    }


