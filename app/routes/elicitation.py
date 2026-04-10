"""
Endpoints REST du moteur d'elicitation.

POST /elicitation/start               -> cree session, retourne premiere question
POST /elicitation/answer              -> soumet reponse, retourne suite ou done
GET  /elicitation/status/{session_id} -> etat complet
POST /elicitation/skip/{session_id}   -> abandonne
GET  /elicitation/test                -> simule 4 tours sans frontend
"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import Optional

from app.routes.deps import require_user
from app.elicitation import start_elicitation, submit_answer, get_session, skip_session

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
    return start_elicitation(
        objective=payload.objective, topics=payload.topics,
        username=user["username"], tenant_id=user["tenant_id"],
        context=payload.context, max_turns=payload.max_turns,
        session_id=payload.session_id,
    )


@router.post("/elicitation/answer")
def elicitation_answer(payload: AnswerPayload, user: dict = Depends(require_user)):
    return submit_answer(session_id=payload.session_id, answer=payload.answer, username=user["username"])


@router.get("/elicitation/status/{session_id}")
def elicitation_status(session_id: str, user: dict = Depends(require_user)):
    return get_session(session_id=session_id, username=user["username"])


@router.post("/elicitation/skip/{session_id}")
def elicitation_skip(session_id: str, user: dict = Depends(require_user)):
    ok = skip_session(session_id=session_id, username=user["username"])
    return {"skipped": ok, "session_id": session_id}


@router.get("/elicitation/test")
def elicitation_test(user: dict = Depends(require_user)):
    """Simule une session complete. Accessible dans le navigateur apres connexion."""
    import uuid
    sid = f"test-{uuid.uuid4().hex[:8]}"
    log = []
    errors = []

    try:
        step = start_elicitation(
            objective="Comprendre les habitudes de travail et preferences",
            topics=["metier", "outils", "style_communication", "contexte_projets"],
            username=user["username"], tenant_id=user["tenant_id"],
            session_id=sid, max_turns=5,
        )
        log.append({"turn": 0, "raya": step})
    except Exception as e:
        return {"status": "error", "error": str(e)}

    answers = [
        "Responsable commercial PME batiment, equipe de 5",
        "Outlook tous les jours, Teams pour les reunions",
        "Reponses courtes et directes",
        "Projet principal : refonte process devis clients",
    ]

    current = step
    for i, ans in enumerate(answers):
        if current.get("type") == "done":
            break
        try:
            current = submit_answer(sid, ans, user["username"])
            log.append({"turn": i + 1, "user": ans, "raya": current})
        except Exception as e:
            errors.append({"turn": i + 1, "error": str(e)})
            break

    final = get_session(sid, user["username"])
    return {
        "status": "ok" if not errors else "partial",
        "session_id": sid,
        "turns": len(log),
        "final_status": final.get("status"),
        "errors": errors,
        "log": log,
    }
