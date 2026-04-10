"""
Endpoints onboarding Raya — Phase 3c.

GET  /onboarding/status    → statut + blocs de questions
POST /onboarding/complete  → soumet les réponses, génère règles + profil via Opus
POST /onboarding/skip      → passe l'onboarding (relançable plus tard)
POST /onboarding/restart   → remet à zéro pour recommencer
"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import Optional

from app.routes.deps import require_user
from app.onboarding import (
    get_onboarding_status, skip_onboarding,
    restart_onboarding, complete_onboarding,
)

router = APIRouter(tags=["onboarding"])


class CompletePayload(BaseModel):
    answers: dict  # {"1": {"Q1": "R1", ...}, "2": {...}, ...}


@router.get("/onboarding/status")
def onboarding_status(user: dict = Depends(require_user)):
    """Retourne le statut d'onboarding + les blocs de questions."""
    return get_onboarding_status(user["username"])


@router.post("/onboarding/skip")
def onboarding_skip(user: dict = Depends(require_user)):
    """Passe l'onboarding. L'utilisateur pourra le relancer depuis les paramètres."""
    ok = skip_onboarding(user["username"], user["tenant_id"])
    return {"status": "skipped" if ok else "error"}


@router.post("/onboarding/restart")
def onboarding_restart(user: dict = Depends(require_user)):
    """Réinitialise l'onboarding pour le recommencer."""
    ok = restart_onboarding(user["username"], user["tenant_id"])
    return {"status": "pending" if ok else "error"}


@router.post("/onboarding/complete")
def onboarding_complete(
    payload: CompletePayload,
    user: dict = Depends(require_user),
):
    """
    Reçoit les réponses des 4 blocs.
    Appel Opus → génère règles + insights + profil.
    Peut prendre 10-20 secondes (appel Opus profond).
    """
    return complete_onboarding(
        username=user["username"],
        tenant_id=user["tenant_id"],
        answers=payload.answers,
    )
