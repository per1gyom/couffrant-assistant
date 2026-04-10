"""
Onboarding conversationnel Raya — Phase 3c (correctif voix).

L'onboarding passe par le flux de conversation normal du chat.
Raya pose ses questions comme des messages normaux.
L'utilisateur répond en tapant OU au micro (le micro injecte déjà dans l'input).

Flux :
  POST /onboarding/start   → premier message d'accueil + question 1
  POST /onboarding/answer  → enregistre la réponse, retourne question suivante ou done
  POST /onboarding/skip    → interrompt l'onboarding
  POST /onboarding/restart → remet à zéro
  POST /onboarding/complete → génère règles + insights via Opus (appelé automatiquement)
"""
import json
import threading
from app.database import get_pg_conn

# ─── MIGRATION AUTO ───

def _ensure_table():
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS aria_onboarding (
                id           SERIAL PRIMARY KEY,
                username     TEXT NOT NULL UNIQUE,
                tenant_id    TEXT NOT NULL DEFAULT 'couffrant_solar',
                status       TEXT NOT NULL DEFAULT 'pending',
                current_block INTEGER DEFAULT 0,
                answers_json JSONB DEFAULT '{}',
                completed_at TIMESTAMP,
                created_at   TIMESTAMP DEFAULT NOW(),
                updated_at   TIMESTAMP DEFAULT NOW(),
                CONSTRAINT onboarding_status_check CHECK (
                    status IN ('pending','in_progress','completed','skipped')
                )
            )
        """)
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[Onboarding] Migration table: {e}")

_ensure_table()


# ─── LISTE PLATE DES QUESTIONS (12 au total) ───
# Format : (bloc_id, bloc_titre, question_text)

ALL_QUESTIONS = [
    (1, "Contexte professionnel",        "Quel est ton métier ou ton poste ?"),
    (1, "Contexte professionnel",        "Dans quel secteur travailles-tu ?"),
    (1, "Contexte professionnel",        "Combien de personnes dans ton équipe directe ?"),
    (2, "Outils et habitudes",           "Quels outils utilises-tu au quotidien ? (Outlook, Teams, Drive, Odoo...)"),
    (2, "Outils et habitudes",           "À quelle fréquence consultes-tu tes mails ?"),
    (2, "Outils et habitudes",           "Y a-t-il des expéditeurs ou clients particulièrement prioritaires ?"),
    (3, "Préférences de communication",  "Comment préfères-tu que je te réponde ? (court et factuel / détaillé / conversationnel)"),
    (3, "Préférences de communication",  "Je dois tutoyer ou vouvoyer tes contacts par défaut ?"),
    (3, "Préférences de communication",  "Y a-t-il un ton ou un style particulier à éviter ?"),
    (4, "Contexte métier",               "Quels sont tes projets ou dossiers principaux en ce moment ?"),
    (4, "Contexte métier",               "Quelles informations dois-je toujours avoir en tête ?"),
    (4, "Contexte métier",               "Y a-t-il des règles métier ou process importants à connaître ?"),
]

TOTAL_QUESTIONS = len(ALL_QUESTIONS)  # 12


def _format_question(idx: int) -> str:
    """Formate le message d'une question pour l'affichage dans le chat."""
    _, bloc_titre, question = ALL_QUESTIONS[idx]
    num = idx + 1
    return f"**Question {num} / {TOTAL_QUESTIONS} — {bloc_titre}**\n{question}"


# ─── API PUBLIQUE ───

def get_onboarding_status(username: str) -> dict:
    """Retourne le statut d'onboarding (pending / in_progress / completed / skipped)."""
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute(
            "SELECT status, current_block FROM aria_onboarding WHERE username = %s",
            (username,)
        )
        row = c.fetchone()
        conn.close()
        if not row:
            return {"status": "pending", "current_question": 0, "total": TOTAL_QUESTIONS}
        return {"status": row[0], "current_question": row[1], "total": TOTAL_QUESTIONS}
    except Exception as e:
        print(f"[Onboarding] get_status: {e}")
        return {"status": "pending", "current_question": 0, "total": TOTAL_QUESTIONS}


def start_onboarding(username: str, tenant_id: str) -> str:
    """
    Démarre l'onboarding et retourne le message d'accueil + question 1.
    Utilisé par POST /onboarding/start depuis chat.js.
    """
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            INSERT INTO aria_onboarding (username, tenant_id, status, current_block, answers_json)
            VALUES (%s, %s, 'in_progress', 0, '{}')
            ON CONFLICT (username) DO UPDATE
              SET status='in_progress', current_block=0, answers_json='{}',
                  completed_at=NULL, updated_at=NOW()
        """, (username, tenant_id))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[Onboarding] start: {e}")

    welcome = (
        "Bienvenue ! Je suis Raya, ton assistante personnelle. \ud83d\ude0a\n\n"
        "Pour mieux te connaître et bien travailler avec toi, je vais te poser "
        f"{TOTAL_QUESTIONS}\u00a0questions rapides en 4 thèmes.\n"
        "Tu peux répondre **à l'écrit ou au micro** (bouton \ud83c\udfa4 en bas).\n\n"
        "---\n\n"
    )
    return welcome + _format_question(0)


def record_answer_and_get_next(username: str, tenant_id: str, answer: str) -> dict:
    """
    Enregistre la réponse à la question courante et retourne la suivante.

    Retourne :
        {next_message: str, done: bool, question_idx: int}

    Quand done=True, complete_onboarding() est appelé en background.
    """
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute(
            "SELECT current_block, answers_json FROM aria_onboarding WHERE username = %s",
            (username,)
        )
        row = c.fetchone()
        conn.close()

        if not row:
            return {"next_message": "", "done": True, "question_idx": 0}

        current_idx = row[0]
        answers = row[1] or {}

        # Enregistre la réponse
        answers[f"q{current_idx}"] = answer.strip()
        next_idx = current_idx + 1

        if next_idx >= TOTAL_QUESTIONS:
            # Toutes les questions répondues — on finalise en background
            conn = get_pg_conn()
            c = conn.cursor()
            c.execute("""
                UPDATE aria_onboarding
                SET current_block=%s, answers_json=%s, updated_at=NOW()
                WHERE username=%s
            """, (next_idx, json.dumps(answers), username))
            conn.commit()
            conn.close()

            # Reconstruit le format bloc pour complete_onboarding
            bloc_answers = _flat_to_bloc_answers(answers)
            threading.Thread(
                target=complete_onboarding,
                args=(username, tenant_id, bloc_answers),
                daemon=True,
            ).start()

            done_msg = (
                "Merci, j'ai tout ce qu'il me faut ! \u2728\n\n"
                "Je construis ton profil... ça prend une dizaine de secondes.\n"
                "_(Tu peux déjà commencer à utiliser le chat.)_"
            )
            return {"next_message": done_msg, "done": True, "question_idx": next_idx}

        # Met à jour l'index et les réponses
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            UPDATE aria_onboarding
            SET current_block=%s, answers_json=%s, updated_at=NOW()
            WHERE username=%s
        """, (next_idx, json.dumps(answers), username))
        conn.commit()
        conn.close()

        return {
            "next_message": _format_question(next_idx),
            "done": False,
            "question_idx": next_idx,
        }

    except Exception as e:
        print(f"[Onboarding] record_answer: {e}")
        return {"next_message": "", "done": True, "question_idx": 0}


def _flat_to_bloc_answers(flat: dict) -> dict:
    """Convertit {q0: r0, q1: r1, ...} vers le format {bloc_id: {question: réponse}}."""
    result = {}
    for i, (bloc_id, _, question) in enumerate(ALL_QUESTIONS):
        answer = flat.get(f"q{i}", "")
        if answer:
            bid = str(bloc_id)
            if bid not in result:
                result[bid] = {}
            result[bid][question] = answer
    return result


def skip_onboarding(username: str, tenant_id: str) -> bool:
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            INSERT INTO aria_onboarding (username, tenant_id, status, updated_at)
            VALUES (%s, %s, 'skipped', NOW())
            ON CONFLICT (username) DO UPDATE SET status='skipped', updated_at=NOW()
        """, (username, tenant_id))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"[Onboarding] skip: {e}")
        return False


def restart_onboarding(username: str, tenant_id: str) -> bool:
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            INSERT INTO aria_onboarding (username, tenant_id, status, current_block, answers_json, updated_at)
            VALUES (%s, %s, 'pending', 0, '{}', NOW())
            ON CONFLICT (username) DO UPDATE
              SET status='pending', current_block=0, answers_json='{}',
                  completed_at=NULL, updated_at=NOW()
        """, (username, tenant_id))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"[Onboarding] restart: {e}")
        return False


def complete_onboarding(username: str, tenant_id: str, answers: dict) -> dict:
    """
    Appel Opus pour générer règles + insights + profil.
    answers = {"1": {question: réponse, ...}, "2": {...}, ...}
    """
    try:
        answers_text = ""
        bloc_titres = {"1": "Contexte professionnel", "2": "Outils et habitudes",
                       "3": "Préférences de communication", "4": "Contexte métier"}
        for bid, titre in bloc_titres.items():
            bloc_answers = answers.get(bid, {})
            if bloc_answers:
                answers_text += f"\n=== {titre} ===\n"
                for q, a in bloc_answers.items():
                    if a and str(a).strip():
                        answers_text += f"  Q: {q}\n  R: {a}\n"

        prompt = f"""Tu es Raya. L'utilisateur {username} vient de compléter son onboarding conversationnel.
Voici ses réponses :
{answers_text}

Génère en JSON strict (sans backticks) :
{{"profile_summary": "~100 mots, qui est cet utilisateur, comment travailler avec lui",
  "rules": [{{"category": "comportement", "rule": "règle concrète"}}, ...],
  "insights": [{{"topic": "sujet", "text": "observation"}}, ...]}}

Règles : 5-10 règles sur style, priorités, outils, métier.
Insights : 3-5 observations clés.
Profile : factuel, pas de flatterie."""

        from app.llm_client import llm_complete, log_llm_usage
        import re
        result = llm_complete(
            messages=[{"role": "user", "content": prompt}],
            model_tier="deep", max_tokens=1500,
        )
        log_llm_usage(result, username=username, tenant_id=tenant_id,
                      purpose="onboarding_completion")

        raw = re.sub(r'^```(?:json)?\s*', '', result["text"].strip(), flags=re.MULTILINE)
        raw = re.sub(r'\s*```$', '', raw, flags=re.MULTILINE).strip()
        parsed = json.loads(raw)
    except Exception as e:
        print(f"[Onboarding] Erreur Opus: {e}")
        parsed = {"profile_summary": "", "rules": [], "insights": []}

    if parsed.get("profile_summary"):
        try:
            conn = get_pg_conn(); c = conn.cursor()
            c.execute("""
                INSERT INTO aria_hot_summary (username, content, updated_at)
                VALUES (%s, %s, NOW())
                ON CONFLICT (username) DO UPDATE SET content=EXCLUDED.content, updated_at=NOW()
            """, (username, parsed["profile_summary"]))
            conn.commit(); conn.close()
        except Exception as e:
            print(f"[Onboarding] hot_summary: {e}")

    rules_created = 0
    from app.memory_rules import save_rule
    for item in parsed.get("rules", []):
        try:
            if item.get("rule") and len(item["rule"]) > 5:
                save_rule(item.get("category", "comportement"), item["rule"],
                          "onboarding", 0.8, username, tenant_id)
                rules_created += 1
        except Exception: pass

    insights_created = 0
    from app.memory_synthesis import save_insight
    for item in parsed.get("insights", []):
        try:
            if item.get("text") and len(item["text"]) > 5:
                save_insight(item.get("topic", "profil"), item["text"],
                             "onboarding", username=username, tenant_id=tenant_id)
                insights_created += 1
        except Exception: pass

    try:
        conn = get_pg_conn(); c = conn.cursor()
        c.execute("""
            UPDATE aria_onboarding
            SET status='completed', answers_json=%s, completed_at=NOW(), updated_at=NOW()
            WHERE username=%s
        """, (json.dumps(answers), username))
        conn.commit(); conn.close()
    except Exception as e:
        print(f"[Onboarding] sauvegarde finale: {e}")

    print(f"[Onboarding] {username} completé : {rules_created} règles, {insights_created} insights")
    return {"status": "completed", "rules_created": rules_created,
            "insights_created": insights_created,
            "profile_summary": parsed.get("profile_summary", "")}
