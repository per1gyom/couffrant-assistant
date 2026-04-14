"""
Moteur d'elicitation conversationnelle generique.

Permet a Sonnet de mener une conversation structuree pour collecter
des informations selon un objectif et une liste de sujets.

Consommateurs prevus :
  - Onboarding utilisateur (commit 2)
  - Creation de skill [ACTION:CREATE_SKILL] (commit 3)

Pattern stateful : une session par objectif, reprise possible apres interruption.

API publique :
  start_elicitation(objective, topics, username, tenant_id, ...) -> dict
  submit_answer(session_id, answer, username) -> dict
  get_session(session_id, username) -> dict
  skip_session(session_id, username) -> bool

Format de retour LLM (JSON strict) :
  {"type": "open",   "question": "...", "topic": "..."}
  {"type": "choice", "question": "...", "options": [...], "topic": "..."}
  {"type": "done",   "summary": "...", "structured_data": {...}}
"""
import uuid
import json
import re
from app.database import get_pg_conn

from app.elicitation_questions import MAX_TURNS_DEFAULT, LLM_TIER_QUESTIONS, _build_prompt, _call_llm  # noqa

# Tier LLM pour les questions conversationnelles.
# Sonnet suffit largement — Opus est reserve pour la synthese finale.
LLM_TIER_QUESTIONS = "smart"


def _ensure_table():
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS elicitation_sessions (
                id            TEXT PRIMARY KEY,
                username      TEXT NOT NULL,
                tenant_id     TEXT NOT NULL DEFAULT 'couffrant_solar',
                objective     TEXT NOT NULL,
                topics_json   JSONB DEFAULT '[]',
                context_json  JSONB DEFAULT '{}',
                history_json  JSONB DEFAULT '[]',
                turn_count    INTEGER DEFAULT 0,
                max_turns     INTEGER DEFAULT 8,
                status        TEXT NOT NULL DEFAULT 'active',
                result_json   JSONB DEFAULT '{}',
                created_at    TIMESTAMP DEFAULT NOW(),
                updated_at    TIMESTAMP DEFAULT NOW(),
                CONSTRAINT elicitation_status_check CHECK (
                    status IN ('active', 'done', 'skipped')
                )
            )
        """)
        c.execute("""
            CREATE INDEX IF NOT EXISTS idx_elicitation_user
            ON elicitation_sessions (username, status, updated_at DESC)
        """)
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[Elicitation] Migration table: {e}")

_ensure_table()


def start_elicitation(
    objective: str,
    topics: list,
    username: str,
    tenant_id: str,
    context: dict = None,
    max_turns: int = MAX_TURNS_DEFAULT,
    session_id: str = None,
) -> dict:
    """Cree une session et retourne la premiere question. Returns: {session_id, type, question, options?, topic}"""
    if session_id is None:
        session_id = str(uuid.uuid4())
    context = context or {}
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            INSERT INTO elicitation_sessions
              (id, username, tenant_id, objective, topics_json, context_json,
               history_json, turn_count, max_turns, status, result_json)
            VALUES (%s, %s, %s, %s, %s::jsonb, %s::jsonb, '[]', 0, %s, 'active', '{}')
            ON CONFLICT (id) DO UPDATE
              SET status='active', history_json='[]', turn_count=0,
                  result_json='{}', updated_at=NOW()
        """, (session_id, username, tenant_id, objective,
              json.dumps(topics), json.dumps(context), max_turns))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[Elicitation] start DB: {e}")
        raise

    first_q, err = _call_llm(objective, topics, context, [], 0, max_turns)
    entry = {"role": "assistant", "type": first_q["type"],
             "question": first_q.get("question", ""),
             "options": first_q.get("options", []),
             "topic": first_q.get("topic", "")}
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("UPDATE elicitation_sessions SET history_json = history_json || %s::jsonb, updated_at=NOW() WHERE id = %s",
                  (json.dumps([entry]), session_id))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[Elicitation] start save: {e}")

    result = {"session_id": session_id, **first_q}
    if err:
        result["_llm_error"] = err  # visible dans /test, ignore en prod
    return result


def submit_answer(session_id: str, answer: str, username: str) -> dict:
    """Soumet une reponse, retourne la question suivante ou done."""
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""SELECT objective, topics_json, context_json, history_json,
                          turn_count, max_turns, status
                     FROM elicitation_sessions WHERE id = %s AND username = %s""",
                  (session_id, username))
        row = c.fetchone()
        conn.close()
    except Exception as e:
        return {"type": "done", "summary": "Erreur session.", "structured_data": {}}

    if not row:
        return {"type": "done", "summary": "Session introuvable.", "structured_data": {}}

    objective, topics, context, history, turn_count, max_turns, status = row
    if status != "active":
        return {"type": "done", "summary": "Session terminee.", "structured_data": {}}

    history = history or []
    turn_count = (turn_count or 0)
    history.append({"role": "user", "answer": answer.strip()})
    turn_count += 1

    if turn_count >= (max_turns or MAX_TURNS_DEFAULT):
        next_q = {"type": "done", "summary": "Limite d'echanges atteinte.", "structured_data": {}}
        err = None
    else:
        next_q, err = _call_llm(objective, topics or [], context or {},
                                history, turn_count, max_turns or MAX_TURNS_DEFAULT)

    if next_q["type"] != "done":
        history.append({"role": "assistant", "type": next_q["type"],
                        "question": next_q.get("question", ""),
                        "options": next_q.get("options", []),
                        "topic": next_q.get("topic", "")})
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        if next_q["type"] == "done":
            c.execute("""UPDATE elicitation_sessions
                         SET history_json=%s::jsonb, turn_count=%s,
                             status='done', result_json=%s::jsonb, updated_at=NOW()
                         WHERE id = %s""",
                      (json.dumps(history), turn_count,
                       json.dumps(next_q.get("structured_data", {})), session_id))
        else:
            c.execute("UPDATE elicitation_sessions SET history_json=%s::jsonb, turn_count=%s, updated_at=NOW() WHERE id = %s",
                      (json.dumps(history), turn_count, session_id))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[Elicitation] submit save: {e}")

    if err:
        next_q["_llm_error"] = err
    return next_q


def get_session(session_id: str, username: str) -> dict:
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""SELECT id, objective, topics_json, context_json, history_json,
                          turn_count, max_turns, status, result_json, created_at
                     FROM elicitation_sessions WHERE id = %s AND username = %s""",
                  (session_id, username))
        row = c.fetchone()
        conn.close()
        if not row:
            return {"error": "Session introuvable"}
        return {"session_id": row[0], "objective": row[1], "topics": row[2] or [],
                "context": row[3] or {}, "history": row[4] or [],
                "turn_count": row[5], "max_turns": row[6], "status": row[7],
                "result": row[8] or {},
                "created_at": row[9].isoformat() if row[9] else None}
    except Exception as e:
        return {"error": str(e)}


def skip_session(session_id: str, username: str) -> bool:
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("UPDATE elicitation_sessions SET status='skipped', updated_at=NOW() WHERE id = %s AND username = %s AND status='active'",
                  (session_id, username))
        ok = c.rowcount > 0
        conn.commit()
        conn.close()
        return ok
    except Exception as e:
        print(f"[Elicitation] skip: {e}")
        return False
