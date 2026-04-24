"""
Onboarding Raya — wrapper mince sur le moteur d'elicitation.

Premier consommateur du moteur generique (app/elicitation.py).
Ce module expose l'API attendue par routes/onboarding.py.
Toute la logique conversationnelle est dans elicitation.py.

session_id fixe par utilisateur : "onboarding:{username}"
"""
import json
import re
import threading
from app.database import get_pg_conn
from app.elicitation import (
    start_elicitation,
    submit_answer as _elicitation_submit,
    get_session,
    skip_session,
)

ONBOARDING_OBJECTIVE = (
    "Comprendre l'utilisateur pour personnaliser Raya, son assistante IA. "
    "Decouvrir son metier, ses outils quotidiens, comment il prefere communiquer, "
    "et ses projets en cours."
)

ONBOARDING_TOPICS = [
    "identite_professionnelle",
    "outils_et_habitudes",
    "style_de_communication",
    "contexte_metier_et_projets",
]

MAX_TURNS = 8


def _sid(username: str) -> str:
    return f"onboarding:{username}"


def get_onboarding_status(username: str) -> dict:
    session = get_session(_sid(username), username)
    if "error" in session:
        return {"status": "pending", "exchange_count": 0}
    raw = session.get("status", "active")
    # active -> in_progress pour compat chat.js
    status = "in_progress" if raw == "active" else raw
    return {"status": status, "exchange_count": session.get("turn_count", 0)}


def start_onboarding(username: str, tenant_id: str) -> dict:
    """
    Demarre l'onboarding via le moteur d'elicitation.
    Retourne {message, intro, type, question, options} — compatible chat.js.
    """
    result = start_elicitation(
        objective=ONBOARDING_OBJECTIVE,
        topics=ONBOARDING_TOPICS,
        username=username,
        tenant_id=tenant_id,
        session_id=_sid(username),
        max_turns=MAX_TURNS,
    )
    intro = (
        "Bonjour ! Je suis Raya.\n\n"
        "Pour personnaliser ton experience, je vais te poser quelques questions "
        f"(max {MAX_TURNS} echanges, tout est skippable).\n\n"
    )
    question = result.get("question", "")
    return {
        "message": intro + question,   # compat ancien chat.js
        "intro": intro,
        "type": result["type"],
        "question": question,
        "options": result.get("options", []),
        "session_id": result["session_id"],
    }


def record_answer_and_get_next(username: str, tenant_id: str, answer: str) -> dict:
    """
    Soumet une reponse au moteur.
    Retourne {next_message, done, type, options?} — compatible chat.js.
    """
    result = _elicitation_submit(
        session_id=_sid(username),
        answer=answer,
        username=username,
    )
    if result["type"] == "done":
        threading.Thread(
            target=_generate_profile,
            args=(username, tenant_id),
            daemon=True,
        ).start()
        return {
            "type": "done",
            "done": True,
            "next_message": (
                "Merci ! Je construis ton profil en arriere-plan.\n"
                "_(Tu peux deja utiliser le chat.)_"
            ),
        }
    return {
        "type": result["type"],
        "done": False,
        "next_message": result.get("question", ""),
        "question": result.get("question", ""),
        "options": result.get("options", []),
    }


def skip_onboarding(username: str, tenant_id: str) -> bool:
    return skip_session(_sid(username), username)


def restart_onboarding(username: str, tenant_id: str) -> bool:
    """Remet l'onboarding a zero en supprimant la session."""
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute(
            "DELETE FROM elicitation_sessions WHERE id = %s AND username = %s",
            (_sid(username), username)
        )
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"[Onboarding] restart: {e}")
        return False


def _generate_profile(username: str, tenant_id: str):
    """
    Genere regles + insights + hot_summary a partir de l'historique de session.
    Execute en background apres conclusion de l'onboarding.
    """
    session = get_session(_sid(username), username)
    if "error" in session:
        return

    history = session.get("history", [])
    conv_text = ""
    for entry in history:
        if entry.get("role") == "assistant":
            conv_text += f"Raya: {entry.get('question', '')}\n"
        elif entry.get("role") == "user":
            conv_text += f"Utilisateur: {entry.get('answer', '')}\n"

    if not conv_text.strip():
        return

    prompt = (
        f"Tu es Raya. Voici la conversation d'onboarding avec {username} :\n\n"
        f"{conv_text}\n\n"
        "Genere en JSON strict (sans backticks) :\n"
        "{\"profile_summary\": \"resume ~100 mots\","
        "\"rules\": [{\"category\": \"Comportement\", \"rule\": \"regle concrete\"}],"
        "\"insights\": [{\"topic\": \"sujet\", \"text\": \"observation\"}]}\n\n"
        "rules : 5-10 regles concretes sur style, priorites, outils, metier.\n"
        "insights : 3-5 observations cles.\n"
        "profile_summary : factuel, 100 mots max."
    )

    try:
        from app.llm_client import llm_complete, log_llm_usage
        result = llm_complete(
            messages=[{"role": "user", "content": prompt}],
            model_tier="smart",
            max_tokens=1500,
        )
        log_llm_usage(result, username=username, tenant_id=tenant_id,
                      purpose="onboarding_profile")
        raw = re.sub(r'^```(?:json)?\s*', '', result["text"].strip(), flags=re.MULTILINE)
        raw = re.sub(r'\s*```$', '', raw, flags=re.MULTILINE).strip()
        parsed = json.loads(raw)
    except Exception as e:
        print(f"[Onboarding] generate_profile error: {e}")
        return

    if parsed.get("profile_summary"):
        try:
            conn = get_pg_conn()
            c = conn.cursor()
            c.execute("""
                INSERT INTO aria_hot_summary (username, content, updated_at)
                VALUES (%s, %s, NOW())
                ON CONFLICT (username) DO UPDATE
                  SET content=EXCLUDED.content, updated_at=NOW()
            """, (username, parsed["profile_summary"]))
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"[Onboarding] hot_summary: {e}")

    from app.memory_rules import save_rule
    rules_ok = 0
    for item in parsed.get("rules", []):
        try:
            if item.get("rule") and len(item["rule"]) > 5:
                # Phase 3 : default "Comportement" (forme canonique) au lieu de
                # "comportement" minuscule qui creait un doublon avec la version
                # majuscule au fil du temps.
                save_rule(item.get("category", "Comportement"), item["rule"],
                          "onboarding", 0.8, username, tenant_id)
                rules_ok += 1
        except Exception:
            pass

    from app.memory_synthesis import save_insight
    insights_ok = 0
    for item in parsed.get("insights", []):
        try:
            if item.get("text") and len(item["text"]) > 5:
                save_insight(item.get("topic", "profil"), item["text"],
                             "onboarding", username=username, tenant_id=tenant_id)
                insights_ok += 1
        except Exception:
            pass

    print(f"[Onboarding] {username} profile genere : {rules_ok} regles, {insights_ok} insights")
