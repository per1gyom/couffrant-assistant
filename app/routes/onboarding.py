"""
Endpoints onboarding Raya.

GET  /onboarding/status  -> statut (pending/in_progress/done/skipped)
POST /onboarding/start   -> demarre, retourne {message, intro, type, question, options}
POST /onboarding/answer  -> soumet reponse, retourne {next_message, done, type, options?}
POST /onboarding/skip    -> passe l'onboarding
POST /onboarding/restart -> remet a zero
"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.routes.deps import require_user
from app.onboarding import (
    get_onboarding_status,
    start_onboarding,
    record_answer_and_get_next,
    skip_onboarding,
    restart_onboarding,
)

router = APIRouter(tags=["onboarding"])


class AnswerPayload(BaseModel):
    answer: str


@router.get("/onboarding/status")
def onboarding_status(user: dict = Depends(require_user)):
    return get_onboarding_status(user["username"])


@router.post("/onboarding/start")
def onboarding_start(user: dict = Depends(require_user)):
    """
    Demarre l'onboarding dynamique via le moteur d'elicitation.
    Peut prendre 3-5 secondes (appel Sonnet pour la premiere question).

    Returns: {message, intro, type, question, options}
    """
    return start_onboarding(user["username"], user["tenant_id"])


@router.post("/onboarding/answer")
def onboarding_answer(payload: AnswerPayload, user: dict = Depends(require_user)):
    """
    Soumet une reponse. Retourne la question suivante ou la conclusion.

    Returns:
      {type: "open"|"choice", done: false, next_message, options?}
      {type: "done", done: true, next_message}
    """
    return record_answer_and_get_next(
        username=user["username"],
        tenant_id=user["tenant_id"],
        answer=payload.answer,
    )


@router.post("/onboarding/skip")
def onboarding_skip(user: dict = Depends(require_user)):
    ok = skip_onboarding(user["username"], user["tenant_id"])
    return {"status": "skipped" if ok else "error"}


@router.post("/onboarding/restart")
def onboarding_restart(user: dict = Depends(require_user)):
    ok = restart_onboarding(user["username"], user["tenant_id"])
    return {"status": "pending" if ok else "error"}
