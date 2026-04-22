"""
Endpoints Raya : /speak, /raya, /token-status, /raya/feedback, /raya/why/{id}.

Phase 3b (B8) : detection de session thematique via detect_session_theme().
Phase 5B-1    : injection dynamique des actions par domaine via detect_query_domains().
5D-2f         : charge les tenants de l'utilisateur et les passe au prompt builder.
7-6D          : marquage automatique du rapport matinal livre via le chat.
WEB-SEARCH    : activation de la recherche web Anthropic via RAYA_WEB_SEARCH_ENABLED.
SPEAK-SPEED   : vitesse de lecture ElevenLabs dynamique via payload.speed.
TOOL-READ-PDF : extraction texte pdfplumber injectee dans le contexte LLM (commit 3/3).
A2a           : import direct depuis app.routes.actions (shim aria_actions supprime).
A4-4          : print() remplaces par logger.
FIX-CLEAN-1   : nettoyage agressif des balises techniques + dedup confirmations.
FIX-ODOO      : nettoyage fragments Odoo inline (pipes + JSON arrays).
"""
import json
import os
import re
import io
import traceback
import threading
import requests as http_requests
import concurrent.futures
from typing import Optional

from fastapi import APIRouter, Request, Body, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.llm_client import llm_complete, log_llm_usage
from app.router import route_query_tier, detect_session_theme, detect_query_domains
from app.database import get_pg_conn
from app.connection_token_manager import get_connection_token


def _get_ms_token(username: str) -> str | None:
    return get_connection_token(username, "microsoft")
from app.memory_loader import MEMORY_OK, synthesize_session
from app.rule_engine import get_memoire_param
from app.feedback_store import get_global_instructions
from app.pending_actions import get_pending
from app.feedback import (
    save_response_metadata, get_response_metadata,
    process_positive_feedback, process_negative_feedback,
)
from app.tenant_manager import get_user_tenants
from app.logging_config import get_logger

from app.routes.aria_context import (
    load_user_tools, load_db_context, load_live_mails,
    load_agenda, load_teams_context, load_mail_filter_summary,
    build_system_prompt,
)
from app.routes.actions import execute_actions, _ASK_CHOICE_PREFIX
from app.routes.deps import require_user
from app.rate_limiter import check_rate_limit
from app.routes.raya_helpers import _raya_core, _build_user_content, RayaQuery, FeedbackPayload  # noqa
# v2 mode agent (active via RAYA_AGENT_MODE=true)
from app.routes.raya_agent_core import _raya_core_agent

logger = get_logger("raya.core")
router = APIRouter(tags=["raya"])


def _is_agent_mode() -> bool:
    """Feature flag : true si RAYA_AGENT_MODE est active."""
    return os.getenv("RAYA_AGENT_MODE", "false").lower() == "true"


# --- ENDPOINTS ---

@router.get("/token-status")
def token_status(request: Request, user: dict = Depends(require_user)):
    username = user["username"]
    warnings = []

    # Vérification Microsoft — V2 d'abord, fallback legacy
    try:
        token = _get_ms_token(username)
        if not token:
            warnings.append({
                "provider": "Microsoft 365",
                "mailbox": "Outlook (boîte pro)",
                "message": "Token expiré — mails, agenda et Teams inaccessibles.",
                "action_url": "/login",
                "severity": "error",
            })
    except Exception:
        pass

    # Vérification Gmail — V2 uniquement
    try:
        from app.connection_token_manager import get_user_tool_connections
        v2 = get_user_tool_connections(username)
        if "gmail" in v2:
            if not v2["gmail"].get("token"):
                gmail_email = v2["gmail"].get("email", "Gmail")
                warnings.append({
                    "provider": "Gmail", "mailbox": gmail_email,
                    "message": "Connexion expirée.",
                    "action_url": "/login/gmail", "severity": "error",
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
            "is_error": True, "error_type": "rate_limit",
        }
    import concurrent.futures
    try:
        # Feature flag : route vers la boucle agent v2 ou l inference single-shot v1
        core_fn = _raya_core_agent if _is_agent_mode() else _raya_core
        logger.info(
            "[Raya] Dispatch vers %s pour user=%s",
            core_fn.__name__, username,
        )
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(core_fn, request, payload, username, tenant_id)
            # Timeout 90s : Opus 4.7 avec max_tokens=8192 + synthèse auto (2e appel LLM)
            # peut légitimement prendre 45-75s sur requête complexe. 30s créait des bugs
            # fantômes (thread non tuable en Python) où la réponse arrivait après coup.
            return future.result(timeout=90)
    except concurrent.futures.TimeoutError:
        return {
            "answer": "\u26a0\ufe0f Raya est momentan\u00e9ment surcharg\u00e9e. R\u00e9essaie dans quelques secondes.",
            "actions": [], "pending_actions": [],
            "aria_memory_id": None, "model_tier": "smart",
            "ask_choice": None,
            "is_error": True, "error_type": "timeout",
        }
    except Exception:
        tb = traceback.format_exc()
        logger.error("[Raya] ERREUR ENDPOINT pour %s:\n%s", username, tb)
        return {
            "answer": "\u26a0\ufe0f Une erreur interne est survenue. L'incident a ete logue.",
            "actions": [], "pending_actions": [],
            "aria_memory_id": None, "model_tier": "smart",
            "ask_choice": None,
            "is_error": True, "error_type": "internal",
        }


@router.post("/raya/continue")
def raya_continue_endpoint(
    request: Request,
    payload: dict,
    user: dict = Depends(require_user),
):
    """
    Reprise d une boucle agent interrompue par un garde-fou.

    Appele par le bouton 'Etendre' cote front. Charge la continuation
    sauvegardee via raya_continuation.load_continuation, verifie l
    ownership, puis relance _raya_core_agent avec existing_continuation
    -> reprise exacte avec budgets etendus (P2 ou P3+).

    Body JSON attendu :
      { "continuation_id": 42 }
    """
    username = user["username"]
    tenant_id = user["tenant_id"]
    if not check_rate_limit(username):
        return {
            "answer": "\u26a0\ufe0f Trop de messages en peu de temps. Attends un moment.",
            "actions": [], "pending_actions": [],
            "aria_memory_id": None, "model_tier": "deep",
            "ask_choice": None,
            "is_error": True, "error_type": "rate_limit",
        }

    continuation_id = payload.get("continuation_id")
    if not continuation_id or not isinstance(continuation_id, int):
        return {
            "answer": "\u26a0\ufe0f Identifiant de continuation invalide.",
            "actions": [], "pending_actions": [],
            "aria_memory_id": None, "model_tier": "deep",
            "ask_choice": None,
            "is_error": True, "error_type": "bad_request",
        }

    # Chargement + verif ownership + verif non expire / non consomme
    from app.routes.raya_continuation import load_continuation
    existing = load_continuation(continuation_id, username, tenant_id)
    if existing is None:
        return {
            "answer": (
                "\u26a0\ufe0f Cette continuation n est plus disponible "
                "(expiree au-dela de 1h ou deja utilisee). Reprends ta "
                "question en la reformulant si besoin."
            ),
            "actions": [], "pending_actions": [],
            "aria_memory_id": None, "model_tier": "deep",
            "ask_choice": None,
            "is_error": True, "error_type": "continuation_expired",
        }

    # Construction d un payload minimal pour _raya_core_agent :
    # on reconstitue un RayaQuery avec la query originale (stockee dans
    # la continuation), sans file ni audio (le contexte visuel etait deja
    # dans les messages precedents, il n y a pas a le rejouer).
    class _ReplayPayload:
        def __init__(self, query):
            self.query = query
            self.file = None
            self.audio = None
            self.speak_speed = None
    replay_payload = _ReplayPayload(existing["query"])

    import concurrent.futures
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            # On appelle _raya_core_agent avec existing_continuation -> reprise
            future = executor.submit(
                _raya_core_agent,
                request, replay_payload, username, tenant_id,
                existing,  # existing_continuation
            )
            # Timeout global plus genereux pour les extensions (P3 peut
            # aller jusqu a 300s de boucle + marges reseau).
            return future.result(timeout=360)
    except concurrent.futures.TimeoutError:
        return {
            "answer": "\u26a0\ufe0f L extension a depasse le timeout serveur. Retente avec une question plus ciblee.",
            "actions": [], "pending_actions": [],
            "aria_memory_id": None, "model_tier": "deep",
            "ask_choice": None,
            "is_error": True, "error_type": "timeout",
        }
    except Exception:
        tb = traceback.format_exc()
        logger.error("[Raya] ERREUR CONTINUE pour %s:\n%s", username, tb)
        return {
            "answer": "\u26a0\ufe0f Une erreur interne est survenue lors de l extension.",
            "actions": [], "pending_actions": [],
            "aria_memory_id": None, "model_tier": "deep",
            "ask_choice": None,
            "is_error": True, "error_type": "internal",
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


@router.get("/raya/pending")
def raya_pending(user: dict = Depends(require_user)):
    """Retourne les actions en attente de confirmation pour l'utilisateur connecté."""
    username = user["username"]
    tenant_id = user["tenant_id"]
    return {"pending_actions": get_pending(username=username, tenant_id=tenant_id, limit=10)}


@router.post("/raya/draft/{action_id}")
def raya_draft_action(
    action_id: int,
    user: dict = Depends(require_user),
):
    """Sauvegarde l'action comme brouillon Outlook (sans envoyer) et l'annule de la queue."""
    username = user["username"]
    tenant_id = user["tenant_id"]
    from app.pending_actions import get_action, cancel_action
    from app.connectors.outlook_connector import perform_outlook_action

    action = get_action(action_id, username, tenant_id)
    if not action or action["status"] != "pending":
        return {"ok": False, "message": "Action introuvable, déjà traitée ou expirée."}

    outlook_token = _get_ms_token(username)
    if not outlook_token:
        return {"ok": False, "message": "Token Microsoft manquant."}

    action_type = action["action_type"]
    payload = action["payload"]

    try:
        if action_type == "SEND_MAIL":
            r = perform_outlook_action("create_draft_mail", {
                "to_email": payload["to_email"],
                "subject":  payload["subject"],
                "body":     payload["body"],
            }, outlook_token)
        elif action_type == "SEND_GMAIL":
            # Brouillon Gmail via connecteur unifié
            try:
                from app.mailbox_manager import get_connector_for_mailbox
                connector = get_connector_for_mailbox(username, "gmail")
                if not connector:
                    return {"ok": False, "message": "Gmail non connecté"}
                result = connector.create_draft(
                    to=payload["to_email"],
                    subject=payload["subject"],
                    body=payload["body"],
                    from_email=payload.get("from_email", ""),
                )
                r = {"status": "ok"} if result.get("ok") else {"status": "error", "message": result.get("message", "")}
            except Exception as e:
                return {"ok": False, "message": f"Erreur brouillon Gmail : {str(e)[:150]}"}
        elif action_type == "REPLY":
            r = perform_outlook_action("create_reply_draft", {
                "message_id": payload["message_id"],
                "reply_body": payload["reply_text"],
            }, outlook_token)
        else:
            return {"ok": False, "message": f"Type {action_type} non supporté en brouillon."}

        if r.get("status") != "ok":
            return {"ok": False, "message": r.get("message", "Erreur création brouillon")}

        # Annuler l'action de la queue (elle est maintenant dans Outlook Drafts)
        cancel_action(action_id, username, tenant_id, reason="Sauvegardé en brouillon Outlook")
        return {"ok": True, "message": "Brouillon enregistré dans Outlook"}

    except Exception as e:
        return {"ok": False, "message": str(e)[:200]}


@router.post("/raya/confirm/{action_id}")
async def raya_confirm_action(
    action_id: int,
    request: Request,
    user: dict = Depends(require_user),
):
    """Confirme et execute une action en attente — avec payload_override optionnel."""
    username  = user["username"]
    tenant_id = user["tenant_id"]
    from app.pending_actions import confirm_action, mark_executing, mark_executed, mark_failed
    from app.routes.actions.confirmations import _execute_confirmed_action

    # Lire le payload_override s'il est fourni
    payload_override = None
    try:
        body = await request.json()
        payload_override = body.get("payload_override") if body else None
    except Exception:
        pass

    action = confirm_action(action_id, username, tenant_id)
    if not action:
        return {"ok": False, "message": "Action introuvable, deja traitee ou expiree."}

    # Injecter username/tenant_id dans l'action pour _execute_confirmed_action
    action["username"] = username
    action["tenant_id"] = tenant_id

    # Mémoriser le corps ORIGINAL avant modification (pour apprentissage)
    original_payload = dict(action.get("payload", {}))

    # Appliquer les modifications de l'utilisateur sur le payload
    if payload_override:
        action["payload"] = {**action.get("payload", {}), **payload_override}

    outlook_token = _get_ms_token(username)
    tools = load_user_tools(username)
    mark_executing(action_id)
    result = _execute_confirmed_action(action, outlook_token, tools)

    if result.get("ok"):
        mark_executed(action_id, result)

        # ── APPRENTISSAGE depuis la correction ──────────────────────────
        # Si l'utilisateur a modifié le corps avant envoi → Raya apprend
        action_type = action.get("action_type", "")
        if payload_override and action_type in ("SEND_MAIL", "SEND_GMAIL", "REPLY"):
            original_body = original_payload.get("body", "") or original_payload.get("reply_text", "")
            final_body    = action["payload"].get("body", "") or action["payload"].get("reply_text", "")
            if original_body and final_body and original_body.strip() != final_body.strip():
                import threading
                def _learn():
                    try:
                        from app.memory_style import learn_from_correction, save_reply_learning
                        context = f"mail à {action['payload'].get('to_email','')}"
                        learn_from_correction(
                            original=original_body,
                            corrected=final_body,
                            context=context,
                            username=username,
                        )
                        save_reply_learning(
                            mail_subject=action["payload"].get("subject", ""),
                            mail_from=action["payload"].get("from_email", ""),
                            ai_reply=original_body,
                            final_reply=final_body,
                            username=username,
                        )
                        # Invalider le cache style pour que la prochaine réponse
                        # bénéficie immédiatement de l'exemple appris
                        import app.cache as _cache
                        _cache.invalidate_prefix(f"style:{username}")
                    except Exception as e:
                        logger.warning("[Confirm] learn_from_correction échoué: %s", e)
                threading.Thread(target=_learn, daemon=True).start()
                return {"ok": True,
                        "message": result.get("message", "Action executee"),
                        "learned": True}

        return {"ok": True, "message": result.get("message", "Action executee")}
    else:
        mark_failed(action_id, result.get("error", ""))
        return {"ok": False, "message": result.get("error", "Echec de l'action")}


@router.post("/raya/cancel/{action_id}")
def raya_cancel_action(
    action_id: int,
    user: dict = Depends(require_user),
):
    """Annule une action en attente — sans passer par le chat."""
    username = user["username"]
    tenant_id = user["tenant_id"]
    from app.pending_actions import cancel_action, get_action
    action_info = get_action(action_id, username, tenant_id)
    label = (action_info.get("label") if action_info else None) or f"#{action_id}"
    ok = cancel_action(action_id, username, tenant_id, reason="Annule par l'utilisateur")
    return {"ok": ok, "message": f"Annule : {label}" if ok else "Action introuvable."}


# --- CORE ---
