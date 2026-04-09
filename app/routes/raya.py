"""
Endpoints Raya : /speak et /raya.
La logique est déléguée à raya_context.py (construction du contexte)
et raya_actions.py (exécution des actions).
"""
import os
import re
import io
import threading
import requests as http_requests
from typing import Optional

from fastapi import APIRouter, Request, Body
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.config import ANTHROPIC_MODEL_SMART
from app.ai_client import client
from app.database import get_pg_conn
from app.token_manager import get_valid_microsoft_token
from app.memory_loader import MEMORY_OK, synthesize_session
from app.rule_engine import get_memoire_param
from app.feedback_store import get_global_instructions

from app.routes.raya_context import (
    load_user_tools, load_db_context, load_live_mails,
    load_agenda, build_system_prompt,
)
from app.routes.raya_actions import execute_actions
from app.routes.deps import require_user

router = APIRouter(tags=["raya"])


class RayaQuery(BaseModel):
    query: str
    file_data: Optional[str] = None
    file_type: Optional[str] = None
    file_name: Optional[str] = None


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
def raya_endpoint(request: Request, payload: RayaQuery):
    username = request.session.get("user", "guillaume")
    tenant_id = request.session.get("tenant_id", "couffrant_solar")

    # 1. Contexte
    tools = load_user_tools(username)
    db_ctx = load_db_context(username)
    instructions = get_global_instructions(tenant_id=tenant_id)
    outlook_token = get_valid_microsoft_token(username)
    live_mails = load_live_mails(outlook_token, username)
    agenda = load_agenda(outlook_token)

    # 2. Contenu utilisateur (texte + fichier)
    user_content_parts = _build_user_content(payload)

    # 3. Prompt système
    system = build_system_prompt(
        username=username, tenant_id=tenant_id, query=payload.query or "",
        tools=tools, db_ctx=db_ctx, outlook_token=outlook_token,
        live_mails=live_mails, agenda=agenda, instructions=instructions,
    )

    # 4. Historique + appel Claude
    messages = []
    for h in db_ctx["history"]:
        messages.append({"role": "user", "content": h["user_input"]})
        messages.append({"role": "assistant", "content": h["aria_response"]})  # nom de colonne DB
    messages.append({"role": "user", "content": user_content_parts})

    response = client.messages.create(
        model=ANTHROPIC_MODEL_SMART, max_tokens=2048, system=system, messages=messages,
    )
    raya_response = response.content[0].text

    # 5. Exécution des actions
    actions_confirmed = execute_actions(
        raya_response=raya_response,
        username=username,
        outlook_token=outlook_token,
        mails_from_db=db_ctx["mails_from_db"],
        live_mails=live_mails,
        tools=tools,
    )

    # 6. Réponse propre (supprime les balises [ACTION:...])
    clean_response = re.sub(r'\[ACTION:[A-Z_]+:[^\]]*\]', '', raya_response).strip()
    if actions_confirmed:
        clean_response += "\n\n" + "\n".join(actions_confirmed)

    # 7. Sauvegarde en base
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute(
            "INSERT INTO aria_memory (username, user_input, aria_response) VALUES (%s, %s, %s)",
            (username, payload.query, clean_response)
        )
        conn.commit()
    finally:
        if conn: conn.close()

    # 8. Synthèse auto si seuil atteint
    synth_threshold = get_memoire_param(username, "synth_threshold", 15)
    if MEMORY_OK and db_ctx["conv_count"] > 0 and db_ctx["conv_count"] % synth_threshold == 0:
        try:
            threading.Thread(
                target=lambda u=username: synthesize_session(synth_threshold, u),
                daemon=True
            ).start()
        except Exception:
            pass

    return {"answer": clean_response, "actions": actions_confirmed}


def _build_user_content(payload: RayaQuery):
    """Construit le contenu utilisateur (texte seul ou texte + fichier)."""
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
