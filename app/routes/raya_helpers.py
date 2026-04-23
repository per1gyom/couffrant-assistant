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
    db_ctx = load_db_context(username, tenant_id)
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
    # Log de la réponse brute pour debug
    logger.info("[Raya] Réponse brute pour %s (tier=%s, model=%s): %s",
                username, model_tier, model_name, raya_response[:500])
    # Log des tags ACTION détectés pour debug
    import re as _re
    _tags = _re.findall(r'\[ACTION:([A-Z_]+)', raya_response)
    if _tags:
        logger.info("[Raya] Tags détectés dans la réponse pour %s: %s", username, _tags)
    else:
        logger.warning("[Raya] AUCUN tag ACTION détecté pour %s", username)
    log_llm_usage(result, username=username, tenant_id=tenant_id,
                  purpose="raya_main_conversation")

    # Nettoyage : retire toutes les balises techniques de la réponse affichée.
    # IMPORTANT (fix bug perte contexte conversationnel, 18/04/2026) :
    # - On enlève UNIQUEMENT les vrais tags techniques [ACTION:...] et
    #   [SPEAK_SPEED:...] qui ne doivent jamais apparaître à l'utilisateur.
    # - Les anciennes regex "fragments Odoo inline" étaient trop agressives :
    #   elles supprimaient toute occurrence de ["texte","autre"] dans du
    #   texte légitime, ce qui vidait parfois entièrement la réponse quand
    #   Raya formatait des listes JSON. Conséquence : aria_response stocké
    #   vide ou quasi-vide, et au tour suivant Raya ne voyait plus sa propre
    #   question précédente → "Je n'ai pas de demande de synthèse en cours".
    # - Les ACTION tags extraits par _strip_action_tags() matchent déjà les
    #   crochets imbriqués correctement. Il n'y a plus besoin de regex
    #   agressives en filet de sécurité.
    _original_raya = raya_response
    clean_response = _strip_action_tags(raya_response)
    speak_speed = None
    speed_match = re.search(r'\[SPEAK_SPEED:([\d.]+)\]', clean_response)
    if speed_match:
        speak_speed = float(speed_match.group(1))
    clean_response = re.sub(r'`?\[SPEAK_SPEED:[^\]]*\]`?', '', clean_response)
    # Backticks doubles (artefacts markdown occasionnels)
    clean_response = re.sub(r'``', '', clean_response)
    # Lignes vides multiples → 2 max
    clean_response = re.sub(r'\n{3,}', '\n\n', clean_response).strip()

    # GARDE-FOU anti-vide : si le nettoyage a TOUT vidé (cas edge rare mais
    # déjà observé), on garde au minimum la réponse brute sans les tags
    # ACTION. Sinon le LLM au tour suivant reçoit un historique avec des
    # réponses vides et perd le contexte conversationnel.
    if not clean_response:
        fallback = _strip_action_tags(_original_raya).strip() or _original_raya.strip()
        logger.warning(
            "[Raya] clean_response vidé après nettoyage pour %s "
            "(original=%d chars) — fallback appliqué (%d chars)",
            username, len(_original_raya), len(fallback)
        )
        clean_response = fallback

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
        # Log diagnostic : permet de vérifier que la réponse stockée n'est
        # pas vide et de repérer les cas edge (réponse tronquée par nettoyage).
        logger.info(
            "[Raya] aria_memory saved id=%d user=%s input_len=%d response_len=%d",
            aria_memory_id, username, len(payload.query or ""), len(clean_response or "")
        )
    finally:
        if conn: conn.close()

    # 7. Execution des actions (avec aria_memory_id pour lier les cartes à l'échange)
    actions_raw = execute_actions(
        raya_response=raya_response, username=username, tenant_id=tenant_id,
        outlook_token=outlook_token, mails_from_db=db_ctx["mails_from_db"],
        live_mails=live_mails, tools=tools, conversation_id=aria_memory_id,
    )
    if actions_raw:
        logger.info("[Raya] %d action(s) retournées pour %s : %s",
                     len(actions_raw), username,
                     [a[:80] for a in actions_raw])

    # 7b. SYNTHÈSE AUTO — si des résultats informatifs ou erreurs ont été générés,
    # on fait un 2ème appel LLM pour que Raya fasse la synthèse.
    _INFO_MARKERS = ('📊', '📋', '📇', '🗂️', '🔍', '⚠️', '❌ Odoo')
    info_results = [a for a in actions_raw
                    if any(a.startswith(m) for m in _INFO_MARKERS)
                    or '📊' in a or '📋' in a or '📇' in a]
    if info_results:
        logger.info("[Raya] Synthèse auto : %d résultats informatifs pour %s", len(info_results), username)
        try:
            synth_data = "\n\n".join(info_results)
            # Détecter si les résultats contiennent au moins une erreur (❌).
            # Dans ce cas on donne au LLM des instructions plus riches pour
            # qu'il ne se contente pas d'un laconique "la requête a planté"
            # mais propose une alternative actionnable dans la même réponse.
            has_errors = any(a.startswith('❌') or '❌' in a[:5] for a in info_results)
            if has_errors:
                synth_instruction = (
                    f"Voici les données récupérées (certaines requêtes ont échoué) :\n\n{synth_data}\n\n"
                    f"Réponds à {username} en :\n"
                    f"1. Exploitant TOUTES les données valides que tu viens de recevoir\n"
                    f"2. Pour chaque erreur : explique précisément la cause probable "
                    f"(modèle Odoo inexistant, champ invalide, permissions, etc.) "
                    f"et propose UNE alternative concrète que TU VIENS DE TESTER "
                    f"ou que tu peux tester maintenant — pas 'je tente autrement' "
                    f"sans action. Si aucune alternative technique n'est possible, "
                    f"dis-le clairement et donne la meilleure réponse avec ce que "
                    f"tu sais déjà.\n"
                    f"3. Garde un ton direct et utile, jamais évasif."
                )
            else:
                synth_instruction = (
                    f"Voici les données que tu as obtenues :\n\n{synth_data}\n\n"
                    f"Fais maintenant la synthèse demandée à {username}. "
                    f"Sois précis, concis et actionnable."
                )
            synth_result = llm_complete(
                messages=[
                    {"role": "user", "content": payload.query or ""},
                    {"role": "assistant", "content": clean_response},
                    {"role": "user", "content": synth_instruction},
                ],
                model_tier=model_tier, max_tokens=4096, system=system,
            )
            synthesis = synth_result["text"]
            log_llm_usage(synth_result, username=username, tenant_id=tenant_id,
                          purpose="raya_synthesis_followup")
            # Remplacer la réponse par la synthèse (plus pertinente)
            clean_response = _strip_action_tags(synthesis)
            clean_response = re.sub(r'\n{3,}', '\n\n', clean_response).strip()
            # Retirer les résultats informatifs de actions_raw — la synthèse les a intégrés
            actions_raw = [a for a in actions_raw if a not in info_results]
            # Mettre à jour aria_memory avec la synthèse
            if aria_memory_id:
                try:
                    conn2 = get_pg_conn()
                    c2 = conn2.cursor()
                    c2.execute(
                        "UPDATE aria_memory SET aria_response = %s "
                        "WHERE id = %s AND username = %s "
                        "  AND (tenant_id = %s OR tenant_id IS NULL)",
                        (clean_response, aria_memory_id, username, tenant_id))
                    conn2.commit(); conn2.close()
                except Exception:
                    pass
        except Exception as e:
            logger.warning("[Raya] Synthèse follow-up échouée: %s", e)

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


