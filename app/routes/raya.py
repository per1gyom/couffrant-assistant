"""
Endpoints Raya : /speak, /raya, /token-status, /raya/feedback, /raya/why/{id}.

Phase 3b (B8) : détection de session thématique via detect_session_theme().
Si les derniers échanges portent sur un sujet cohérent, le contexte RAG
est enrichi avec tout ce qui concerne ce sujet.
"""
import os
import re
import io
import traceback
import threading
import requests as http_requests
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

from fastapi import APIRouter, Request, Body, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.llm_client import llm_complete, log_llm_usage
from app.router import route_query_tier, detect_session_theme
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

from app.routes.aria_context import (
    load_user_tools, load_db_context, load_live_mails,
    load_agenda, load_teams_context, load_mail_filter_summary,
    build_system_prompt,
)
from app.routes.aria_actions import execute_actions
from app.routes.deps import require_user

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


# ─── ENDPOINTS ───

@router.get("/token-status")
def token_status(request: Request, user: dict = Depends(require_user)):
    username = user["username"]
    warnings = []
    try:
        token = get_valid_microsoft_token(username)
        if not token:
            warnings.append({
                "provider": "Microsoft 365",
                "message": "Token expiré — mails, Teams et agenda inaccessibles.",
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
        return {"error": "Clés ElevenLabs manquantes"}
    text = payload.get("text", "")
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
                                  "style": 0.2, "use_speaker_boost": True}},
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
    try:
        return _raya_core(request, payload, username, tenant_id)
    except Exception:
        tb = traceback.format_exc()
        print(f"[Raya] ERREUR ENDPOINT pour {username}:\n{tb}")
        return {
            "answer": "⚠️ Une erreur interne est survenue. L'incident a été loggé.",
            "actions": [], "pending_actions": [],
            "aria_memory_id": None, "model_tier": "smart",
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
    return {"status": "error", "message": "feedback_type doit être 'positive' ou 'negative'"}


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


# ─── CORE ───

def _raya_core(request: Request, payload: RayaQuery, username: str, tenant_id: str) -> dict:

    # 1. Contexte DB + tokens
    tools = load_user_tools(username)
    db_ctx = load_db_context(username)
    instructions = get_global_instructions(tenant_id=tenant_id)
    outlook_token = get_valid_microsoft_token(username)

    # 2. Appels réseau en PARALLÈLE
    live_mails, agenda, teams_ctx, mail_filter = [], [], "", ""
    with ThreadPoolExecutor(max_workers=4) as pool:
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

    # 4. Routage de tier + détection de session thématique (Phase 3b B8)
    # Les deux micro-appels Haiku tournent en parallèle pour ne pas ajouter de latence.
    model_tier    = "smart"
    session_theme = None
    with ThreadPoolExecutor(max_workers=2) as pool:
        f_tier  = pool.submit(route_query_tier, payload.query or "",
                              username, tenant_id, len(db_ctx["history"]))
        f_theme = pool.submit(detect_session_theme, db_ctx["history"])
        try: model_tier    = f_tier.result(timeout=4)
        except Exception: pass
        try: session_theme = f_theme.result(timeout=3)
        except Exception: pass

    if session_theme:
        print(f"[Raya] Session thématique détectée pour {username} : '{session_theme}'")

    # 5. Construction du prompt système
    user_content_parts = _build_user_content(payload)
    system = build_system_prompt(
        username=username, tenant_id=tenant_id, query=payload.query or "",
        tools=tools, db_ctx=db_ctx, outlook_token=outlook_token,
        live_mails=live_mails, agenda=agenda, instructions=instructions,
        teams_context=teams_ctx, mail_filter_summary=mail_filter,
        pending_actions=pending_list,
        session_theme=session_theme,
    )

    # 6. Appel LLM
    messages = []
    for h in db_ctx["history"]:
        messages.append({"role": "user",      "content": h["user_input"]})
        messages.append({"role": "assistant", "content": h["aria_response"]})
    messages.append({"role": "user", "content": user_content_parts})

    result = llm_complete(
        messages=messages, model_tier=model_tier,
        max_tokens=2048, system=system,
    )
    raya_response = result["text"]
    model_name    = result["model"]
    log_llm_usage(result, username=username, tenant_id=tenant_id,
                  purpose="raya_main_conversation")

    # 7. Exécution des actions
    actions_confirmed = execute_actions(
        raya_response=raya_response, username=username, tenant_id=tenant_id,
        outlook_token=outlook_token, mails_from_db=db_ctx["mails_from_db"],
        live_mails=live_mails, tools=tools, conversation_id=None,
    )

    # 8. Réponse propre
    clean_response = re.sub(r'\[ACTION:[A-Z_]+:[^\]]*\]', '', raya_response).strip()
    if actions_confirmed:
        clean_response += "\n\n" + "\n".join(actions_confirmed)

    # 9. Sauvegarde
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

    # 10. Métadonnées en background
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

    # 11. Synthèse auto
    synth_threshold = get_memoire_param(username, "synth_threshold", 15)
    if MEMORY_OK and db_ctx["conv_count"] > 0 and db_ctx["conv_count"] % synth_threshold == 0:
        try:
            threading.Thread(
                target=lambda u=username, t=tenant_id: synthesize_session(synth_threshold, u, tenant_id=t),
                daemon=True
            ).start()
        except Exception:
            pass

    # 12. Actions en attente mises à jour
    updated_pending = get_pending(username=username, tenant_id=tenant_id, limit=10)

    return {
        "answer":          clean_response,
        "actions":         actions_confirmed,
        "pending_actions": updated_pending,
        "aria_memory_id":  aria_memory_id,
        "model_tier":      model_tier,
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
