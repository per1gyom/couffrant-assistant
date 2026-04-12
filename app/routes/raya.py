"""
Endpoints Raya : /speak, /raya, /token-status, /raya/feedback, /raya/why/{id}.

Phase 3b (B8) : detection de session thematique via detect_session_theme().
Phase 5B-1    : injection dynamique des actions par domaine via detect_query_domains().
5D-2f         : charge les tenants de l'utilisateur et les passe au prompt builder.
7-6D          : marquage automatique du rapport matinal livré via le chat.
WEB-SEARCH    : activation de la recherche web Anthropic via RAYA_WEB_SEARCH_ENABLED.
SPEAK-SPEED   : vitesse de lecture ElevenLabs dynamique via payload.speed.
"""
import json
import os
import re
import io
import traceback
import threading
import requests as http_requests
import concurrent.futures
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

from fastapi import APIRouter, Request, Body, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.llm_client import llm_complete, log_llm_usage
from app.router import route_query_tier, detect_session_theme, detect_query_domains
from app.database import get_pg_conn
from app.token_manager import get_valid_microsoft_token
from app.memory_loader import MEMORY_OK, synthesize_session
from app.rule_engine import get_memoire_param
from app.feedback_store import get_global_instructions
from app.pending_actions import get_pending
from app.feedback import (
    save_response_metadata, get_response_metadata,
    process_positive_feedback, process_negative_feedback,
)
from app.tenant_manager import get_user_tenants

from app.routes.aria_context import (
    load_user_tools, load_db_context, load_live_mails,
    load_agenda, load_teams_context, load_mail_filter_summary,
    build_system_prompt,
)
from app.routes.aria_actions import execute_actions, _ASK_CHOICE_PREFIX
from app.routes.deps import require_user
from app.rate_limiter import check_rate_limit

_SHARED_POOL = ThreadPoolExecutor(max_workers=6)

router = APIRouter(tags=["raya"])


class RayaQuery(BaseModel):
    query: str
    file_data: Optional[str] = None
    file_type: Optional[str] = None
    file_name: Optional[str] = None


class FeedbackPayload(BaseModel):
    aria_memory_id: int
    feedback_type: str
    comment: Optional[str] = None


# --- ENDPOINTS ---

@router.get("/token-status")
def token_status(request: Request, user: dict = Depends(require_user)):
    username = user["username"]
    warnings = []
    try:
        token = get_valid_microsoft_token(username)
        if not token:
            warnings.append({
                "provider": "Microsoft 365",
                "message": "Token expire \u2014 mails, Teams et agenda inaccessibles.",
                "action": "Se reconnecter",
                "action_url": "/login",
                "severity": "error",
            })
    except Exception:
        pass
    return {"warnings": warnings, "ok": len(warnings) == 0}


@router.post("/speak")
def speak_text(payload: dict = Body(...)):
    api_key = os.environ.get("ELEVENLABS_API_KEY", "")
    voice_id = os.environ.get("ELEVENLABS_VOICE_ID", "")
    if not api_key or not voice_id:
        return {"error": "Cles ElevenLabs manquantes"}
    text = payload.get("text", "")
    # Vitesse dynamique (0.5-2.5) — défaut ELEVENLABS_SPEED ou 1.2
    speed = payload.get("speed", float(os.getenv("ELEVENLABS_SPEED", "1.2")))
    speed = max(0.5, min(2.5, float(speed)))
    clean = re.sub(r'#{1,6}\s+', '', text)
    clean = re.sub(r'\*\*(.*?)\*\*', r'\1', clean)
    clean = re.sub(r'\*(.*?)\*', r'\1', clean)
    clean = re.sub(r'`(.*?)`', r'\1', clean)
    clean = re.sub(r'---+', '', clean)
    clean = re.sub(r'\|.*?\|', '', clean)
    clean = clean.strip()[:2500]
    resp = http_requests.post(
        f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
        headers={"xi-api-key": api_key, "Content-Type": "application/json"},
        json={"text": clean, "model_id": "eleven_flash_v2_5",
              "voice_settings": {"stability": 0.5, "similarity_boost": 0.8,
                                  "style": 0.2, "use_speaker_boost": True,
                                  "speed": speed}},
        timeout=30,
    )
    if resp.status_code != 200:
        return {"error": f"ElevenLabs {resp.status_code}", "detail": resp.text[:200]}
    return StreamingResponse(io.BytesIO(resp.content), media_type="audio/mpeg")


@router.post("/raya")
def raya_endpoint(
    request: Request,
    payload: RayaQuery,
    user: dict = Depends(require_user),
):
    username = user["username"]
    tenant_id = user["tenant_id"]
    if not check_rate_limit(username):
        return {
            "answer": "\u26a0\ufe0f Trop de messages en peu de temps. Attends un moment avant de continuer.",
            "actions": [], "pending_actions": [],
            "aria_memory_id": None, "model_tier": "smart",
            "ask_choice": None,
        }
    import concurrent.futures
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_raya_core, request, payload, username, tenant_id)
            return future.result(timeout=30)
    except concurrent.futures.TimeoutError:
        return {
            "answer": "\u26a0\ufe0f Raya est momentan\u00e9ment surcharg\u00e9e. R\u00e9essaie dans quelques secondes.",
            "actions": [], "pending_actions": [],
            "aria_memory_id": None, "model_tier": "smart",
            "ask_choice": None,
        }
    except Exception:
        tb = traceback.format_exc()
        print(f"[Raya] ERREUR ENDPOINT pour {username}:\n{tb}")
        return {
            "answer": "\u26a0\ufe0f Une erreur interne est survenue. L'incident a ete logue.",
            "actions": [], "pending_actions": [],
            "aria_memory_id": None, "model_tier": "smart",
            "ask_choice": None,
        }


@router.post("/raya/feedback")
def raya_feedback(
    payload: FeedbackPayload,
    user: dict = Depends(require_user),
):
    username = user["username"]
    tenant_id = user["tenant_id"]
    if payload.feedback_type == "positive":
        threading.Thread(
            target=process_positive_feedback,
            args=(payload.aria_memory_id, username, tenant_id),
            daemon=True,
        ).start()
        return {"status": "ok", "action": "rules_reinforced"}
    if payload.feedback_type == "negative":
        return process_negative_feedback(
            aria_memory_id=payload.aria_memory_id,
            username=username, tenant_id=tenant_id,
            comment=payload.comment or "",
        )
    return {"status": "error", "message": "feedback_type doit etre 'positive' ou 'negative'"}


@router.get("/raya/why/{aria_memory_id}")
def raya_why(
    aria_memory_id: int,
    user: dict = Depends(require_user),
):
    username = user["username"]
    meta = get_response_metadata(aria_memory_id, username)
    if not meta:
        return {"status": "not_found"}
    return {"status": "ok", **meta}


# --- CORE ---

def _raya_core(request: Request, payload: RayaQuery, username: str, tenant_id: str) -> dict:

    # 1. Contexte DB + tokens
    tools = load_user_tools(username)
    db_ctx = load_db_context(username)
    instructions = get_global_instructions(tenant_id=tenant_id)
    outlook_token = get_valid_microsoft_token(username)

    # 5D-2f : charger les tenants de l'utilisateur
    user_tenants = get_user_tenants(username)

    # 2. Appels reseau en PARALLELE
    live_mails, agenda, teams_ctx, mail_filter = [], [], "", ""
    pool = _SHARED_POOL
    if True:
        f_mails  = pool.submit(load_live_mails, outlook_token, username)
        f_agenda = pool.submit(load_agenda, outlook_token)
        f_teams  = pool.submit(load_teams_context, username)
        f_filter = pool.submit(load_mail_filter_summary, username)
        try: live_mails  = f_mails.result(timeout=8)
        except Exception: pass
        try: agenda      = f_agenda.result(timeout=8)
        except Exception: pass
        try: teams_ctx   = f_teams.result(timeout=5)
        except Exception: pass
        try: mail_filter = f_filter.result(timeout=3)
        except Exception: pass

    # 3. Actions en attente
    pending_list = get_pending(username=username, tenant_id=tenant_id, limit=10)

    # 4. Routage de tier + detection de session thematique
    model_tier    = "smart"
    session_theme = None
    pool = _SHARED_POOL
    if True:
        f_tier  = pool.submit(route_query_tier, payload.query or "",
                              username, tenant_id, len(db_ctx["history"]))
        f_theme = pool.submit(detect_session_theme, db_ctx["history"])
        try: model_tier    = f_tier.result(timeout=4)
        except Exception: pass
        try: session_theme = f_theme.result(timeout=3)
        except Exception: pass

    if session_theme:
        print(f"[Raya] Session thematique detectee pour {username} : '{session_theme}'")

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

    # 6. Appel LLM (WEB-SEARCH : activé selon variable d'environnement)
    messages = []
    for h in db_ctx["history"]:
        messages.append({"role": "user",      "content": h["user_input"]})
        messages.append({"role": "assistant", "content": h["aria_response"]})
    messages.append({"role": "user", "content": user_content_parts})

    web_enabled = os.getenv("RAYA_WEB_SEARCH_ENABLED", "true").lower() == "true"

    result = llm_complete(
        messages=messages, model_tier=model_tier,
        max_tokens=2048, system=system,
        web_search=web_enabled,
    )
    raya_response = result["text"]
    model_name    = result["model"]
    log_llm_usage(result, username=username, tenant_id=tenant_id,
                  purpose="raya_main_conversation")

    # 7. Execution des actions
    actions_raw = execute_actions(
        raya_response=raya_response, username=username, tenant_id=tenant_id,
        outlook_token=outlook_token, mails_from_db=db_ctx["mails_from_db"],
        live_mails=live_mails, tools=tools, conversation_id=None,
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

    # 9. Reponse propre — retire les balises [ACTION:...] du texte affiché
    clean_response = re.sub(r'\[ACTION:[A-Z_]+:[^\]]*\]', '', raya_response).strip()
    if actions_confirmed:
        clean_response += "\n\n" + "\n\n".join(actions_confirmed)

    # 10. Sauvegarde
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

    # 10b. Log d'activité (7-ACT)
    try:
        from app.activity_log import log_activity
        log_activity(username, "conversation", str(aria_memory_id),
                     payload.query[:100] if payload.query else "", tenant_id)
    except Exception:
        pass

    # 10c. Marquage rapport livré si l'utilisateur le demande dans le chat (7-6D)
    try:
        from app.routes.actions.report_actions import get_today_report, mark_report_delivered
        report = get_today_report(username)
        if report and not report["delivered"] and len(clean_response) > 200:
            query_lower = (payload.query or "").lower()
            if "rapport" in query_lower or "résumé" in query_lower or "resume" in query_lower:
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
    }


def _build_user_content(payload: RayaQuery):
    if not payload.file_data or not payload.file_type:
        return payload.query
    file_name_info = f" ({payload.file_name})" if payload.file_name else ""
    parts = []
    if payload.file_type.startswith("image/"):
        parts.append({"type": "image",
                      "source": {"type": "base64", "media_type": payload.file_type,
                                 "data": payload.file_data}})
        parts.append({"type": "text",
                      "text": f"[Image jointe{file_name_info}]\n{payload.query}"
                      if payload.query else f"[Image jointe{file_name_info}] Analyse ce document."})
    elif payload.file_type == "application/pdf":
        parts.append({"type": "document",
                      "source": {"type": "base64", "media_type": "application/pdf",
                                 "data": payload.file_data}})
        parts.append({"type": "text",
                      "text": f"[PDF joint{file_name_info}]\n{payload.query}"
                      if payload.query else f"[PDF joint{file_name_info}] Analyse ce document."})
    else:
        parts.append({"type": "text",
                      "text": f"[Fichier joint{file_name_info}]\n{payload.query}"})
    return parts
