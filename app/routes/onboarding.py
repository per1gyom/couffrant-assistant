"""
Endpoints onboarding Raya — Phase 3c (mode conversationnel).

GET  /onboarding/status   → statut (pending/in_progress/completed/skipped)
POST /onboarding/start    → démarre l'onboarding, retourne le message d'accueil + question 1
POST /onboarding/answer   → enregistre une réponse, retourne la question suivante ou done
POST /onboarding/skip     → passe l'onboarding
POST /onboarding/restart  → remet à zéro
"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import Optional

from app.routes.deps import require_user
from app.onboarding import (
    get_onboarding_status, start_onboarding,
    record_answer_and_get_next, skip_onboarding,
    restart_onboarding, complete_onboarding,
)

router = APIRouter(tags=["onboarding"])


class AnswerPayload(BaseModel):
    answer: str


class CompletePayload(BaseModel):
    answers: dict


@router.get("/onboarding/status")
def onboarding_status(user: dict = Depends(require_user)):
    """Retourne le statut d'onboarding."""
    return get_onboarding_status(user["username"])


@router.post("/onboarding/start")
def onboarding_start(user: dict = Depends(require_user)):
    """
    Démarre l'onboarding conversationnel.
    Retourne le message d'accueil + question 1 pour l'afficher dans le chat normal.
    """
    message = start_onboarding(user["username"], user["tenant_id"])
    return {"message": message, "total": 12, "question_idx": 0}


@router.post("/onboarding/answer")
def onboarding_answer(
    payload: AnswerPayload,
    user: dict = Depends(require_user),
):
    """
    Enregistre la réponse à la question courante.
    Retourne la question suivante (ou le message de fin si done=True).
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


@router.post("/onboarding/complete")
def onboarding_complete(
    payload: CompletePayload,
    user: dict = Depends(require_user),
):
    """Endpoint legacy — toujours disponible pour appel direct."""
    return complete_onboarding(
        username=user["username"],
        tenant_id=user["tenant_id"],
        answers=payload.answers,
    )
