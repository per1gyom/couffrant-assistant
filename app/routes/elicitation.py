"""
Endpoints REST du moteur d'elicitation.

POST /elicitation/start               -> cree session, retourne premiere question
POST /elicitation/answer              -> soumet reponse, retourne suite ou done
GET  /elicitation/status/{session_id} -> etat complet
POST /elicitation/skip/{session_id}   -> abandonne
GET  /elicitation/test                -> simule 4 tours, valide le moteur sans frontend
"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import Optional

from app.routes.deps import require_user
from app.elicitation import (
    start_elicitation,
    submit_answer,
    get_session,
    skip_session,
)

router = APIRouter(tags=["elicitation"])


class StartPayload(BaseModel):
    objective: str
    topics: list
    context: Optional[dict] = None
    max_turns: int = 8
    session_id: Optional[str] = None


class AnswerPayload(BaseModel):
    session_id: str
    answer: str


@router.post("/elicitation/start")
def elicitation_start(payload: StartPayload, user: dict = Depends(require_user)):
    """
    Cree une session et retourne la premiere question d'Opus.
    Peut prendre 3-5 secondes (appel Opus deep).

    Returns: {session_id, type, question, options?, topic}
    """
    return start_elicitation(
        objective=payload.objective,
        topics=payload.topics,
        username=user["username"],
        tenant_id=user["tenant_id"],
        context=payload.context,
        max_turns=payload.max_turns,
        session_id=payload.session_id,
    )


@router.post("/elicitation/answer")
def elicitation_answer(payload: AnswerPayload, user: dict = Depends(require_user)):
    """
    Soumet une reponse. Opus genere la question suivante ou conclut.

    Returns:
        {type: "open",   question, topic}
        {type: "choice", question, options, topic}
        {type: "done",   summary, structured_data}
    """
    return submit_answer(
        session_id=payload.session_id,
        answer=payload.answer,
        username=user["username"],
    )


@router.get("/elicitation/status/{session_id}")
def elicitation_status(session_id: str, user: dict = Depends(require_user)):
    """Retourne l'etat complet d'une session."""
    return get_session(session_id=session_id, username=user["username"])


@router.post("/elicitation/skip/{session_id}")
def elicitation_skip(session_id: str, user: dict = Depends(require_user)):
    """Abandonne une session active."""
    ok = skip_session(session_id=session_id, username=user["username"])
    return {"skipped": ok, "session_id": session_id}


@router.get("/elicitation/test")
def elicitation_test(user: dict = Depends(require_user)):
    """
    Endpoint de test : simule une session complete avec reponses fictives.
    Valide que le moteur tourne sans frontend.

    GET /elicitation/test  (authentification requise)
    """
    import uuid
    test_session_id = f"test-{uuid.uuid4().hex[:8]}"
    log = []
    errors = []

    # Tour 0 : demarrage
    try:
        step = start_elicitation(
            objective="Comprendre les habitudes de travail et les preferences",
            topics=["metier", "outils", "style_communication", "contexte_projets"],
            username=user["username"],
            tenant_id=user["tenant_id"],
            session_id=test_session_id,
            max_turns=5,
        )
        log.append({"turn": 0, "event": "start", "raya": step})
    except Exception as e:
        return {"status": "error", "step": "start", "error": str(e)}

    # Tours 1-4 : reponses fictives
    simulated_answers = [
        "Je suis responsable commercial dans une PME du batiment, 5 personnes",
        "J'utilise Outlook tous les jours, Teams pour les reunions",
        "Je prefere les reponses courtes et directes",
        "Mon projet principal est la refonte de notre process de devis",
    ]

    current = step
    for i, answer in enumerate(simulated_answers):
        if current.get("type") == "done":
            break
        try:
            current = submit_answer(
                session_id=test_session_id,
                answer=answer,
                username=user["username"],
            )
            log.append({"turn": i + 1, "user": answer, "raya": current})
        except Exception as e:
            errors.append({"turn": i + 1, "error": str(e)})
            break

    final = get_session(test_session_id, user["username"])

    return {
        "status": "ok" if not errors else "partial",
        "session_id": test_session_id,
        "turns_completed": len(log),
        "final_status": final.get("status"),
        "final_result": final.get("result"),
        "errors": errors,
        "log": log,
    }
