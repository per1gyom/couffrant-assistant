"""
Onboarding structuré Raya — Phase 3c (décision Opus B13).

Ops Opus mène une conversation de découverte en 4 blocs à la première connexion :
  Bloc 1 — Contexte professionnel
  Bloc 2 — Outils et habitudes
  Bloc 3 — Préférences de communication
  Bloc 4 — Contexte métier spécifique au tenant

Génère automatiquement un premier jeu de règles + profil + insights vectorisés.
Skippable avec bouton "Plus tard". Relançable à tout moment via /onboarding/restart.
"""
import json
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


# ─── BLOCS DE QUESTIONS ───

BLOCS = [
    {
        "id": 1,
        "titre": "Contexte professionnel",
        "questions": [
            "Quel est votre métier ou poste ?",
            "Dans quel secteur travaillez-vous ?",
            "Combien de personnes dans votre équipe directe ?",
        ]
    },
    {
        "id": 2,
        "titre": "Outils et habitudes",
        "questions": [
            "Quels outils utilisez-vous au quotidien ? (Outlook, Teams, Drive, Odoo...)",
            "À quelle fréquence consultez-vous vos mails ?",
            "Y a-t-il des expéditeurs ou clients particulièrement prioritaires ?",
        ]
    },
    {
        "id": 3,
        "titre": "Préférences de communication",
        "questions": [
            "Comment préférez-vous que Raya vous réponde ? (court et factuel / détaillé / conversationnel)",
            "Voulez-vous que Raya tutoie ou vouvoie vos contacts par défaut ?",
            "Y a-t-il un ton ou un style particulier à éviter ?",
        ]
    },
    {
        "id": 4,
        "titre": "Contexte métier",
        "questions": [
            "Quels sont vos projets ou dossiers principaux en ce moment ?",
            "Quelles informations Raya doit-elle toujours avoir en tête ?",
            "Y a-t-il des règles métier ou process importants à connaître ?",
        ]
    },
]


# ─── API PUBLIQUE ───

def get_onboarding_status(username: str) -> dict:
    """
    Retourne le statut d'onboarding de l'utilisateur.
    Crée un enregistrement 'pending' s'il n'existe pas.
    """
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute(
            "SELECT status, current_block, answers_json FROM aria_onboarding WHERE username = %s",
            (username,)
        )
        row = c.fetchone()
        conn.close()

        if not row:
            return {"status": "pending", "current_block": 0, "blocs": BLOCS}

        return {
            "status":        row[0],
            "current_block": row[1],
            "blocs":         BLOCS,
            "answers":       row[2] or {},
        }
    except Exception as e:
        print(f"[Onboarding] get_status: {e}")
        return {"status": "pending", "current_block": 0, "blocs": BLOCS}


def skip_onboarding(username: str, tenant_id: str) -> bool:
    """Marque l'onboarding comme skipé (peut être relanceé plus tard)."""
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            INSERT INTO aria_onboarding (username, tenant_id, status, updated_at)
            VALUES (%s, %s, 'skipped', NOW())
            ON CONFLICT (username) DO UPDATE
              SET status='skipped', updated_at=NOW()
        """, (username, tenant_id))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"[Onboarding] skip: {e}")
        return False


def restart_onboarding(username: str, tenant_id: str) -> bool:
    """Réinitialise l'onboarding pour permettre de le refaire."""
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
    Finalise l'onboarding : appel Opus pour générer les règles + insights.

    answers = {
        "1": {"Quel est votre métier ?": "Installateur photovoltaïque", ...},
        "2": {...},
        ...
    }

    Retourne : {status, rules_created, insights_created, profile_summary}
    """
    try:
        # Formate les réponses pour Opus
        answers_text = ""
        for bloc in BLOCS:
            bloc_answers = answers.get(str(bloc["id"]), {})
            if bloc_answers:
                answers_text += f"\n=== {bloc['titre']} ===\n"
                for q, a in bloc_answers.items():
                    if a and str(a).strip():
                        answers_text += f"  Q: {q}\n  R: {a}\n"

        prompt = f"""Tu es Raya. L'utilisateur {username} vient de compléter son onboarding.
Voici ses réponses :
{answers_text}

Génère en JSON strict (sans backticks) :
{{
  "profile_summary": "Résumé opérationnel en ~100 mots de qui est cet utilisateur et comment travailler avec lui",
  "rules": [
    {{"category": "comportement", "rule": "règle déduite de ses préférences"}},
    ...
  ],
  "insights": [
    {{"topic": "sujet", "text": "observation sur l'utilisateur"}},
    ...
  ]
}}

Pour les rules : génère 5-10 règles concrètes sur son style de communication, ses priorités, ses outils, son métier.
Pour les insights : génère 3-5 observations clés sur le contexte professionnel de l'utilisateur.
Pour le profile_summary : résumé factuel et utile, pas de flatterie."""

        from app.llm_client import llm_complete, log_llm_usage
        import re
        result = llm_complete(
            messages=[{"role": "user", "content": prompt}],
            model_tier="deep",   # Opus pour la qualité du profil initial
            max_tokens=1500,
        )
        log_llm_usage(result, username=username, tenant_id=tenant_id,
                      purpose="onboarding_completion")

        raw = re.sub(r'^```(?:json)?\s*', '', result["text"].strip(), flags=re.MULTILINE)
        raw = re.sub(r'\s*```$', '', raw, flags=re.MULTILINE).strip()
        parsed = json.loads(raw)

    except Exception as e:
        print(f"[Onboarding] Erreur Opus: {e}")
        # Fallback minimal si Opus échoue
        parsed = {"profile_summary": "", "rules": [], "insights": []}

    # Stocke le profil dans aria_hot_summary si non vide
    if parsed.get("profile_summary"):
        try:
            conn = get_pg_conn()
            c = conn.cursor()
            c.execute("""
                INSERT INTO aria_hot_summary (username, content, updated_at)
                VALUES (%s, %s, NOW())
                ON CONFLICT (username) DO UPDATE
                  SET content = EXCLUDED.content, updated_at = NOW()
            """, (username, parsed["profile_summary"]))
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"[Onboarding] Erreur hot_summary: {e}")

    # Crée les règles
    rules_created = 0
    from app.memory_rules import save_rule
    for rule_item in parsed.get("rules", []):
        try:
            category = rule_item.get("category", "comportement")
            rule_text = rule_item.get("rule", "")
            if rule_text and len(rule_text) > 5:
                save_rule(category, rule_text, "onboarding", 0.8, username, tenant_id)
                rules_created += 1
        except Exception:
            pass

    # Crée les insights
    insights_created = 0
    from app.memory_synthesis import save_insight
    for item in parsed.get("insights", []):
        try:
            topic = item.get("topic", "profil")
            text = item.get("text", "")
            if text and len(text) > 5:
                save_insight(topic, text, "onboarding", username=username, tenant_id=tenant_id)
                insights_created += 1
        except Exception:
            pass

    # Marque comme completé
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            INSERT INTO aria_onboarding
              (username, tenant_id, status, answers_json, completed_at, updated_at)
            VALUES (%s, %s, 'completed', %s, NOW(), NOW())
            ON CONFLICT (username) DO UPDATE
              SET status='completed', answers_json=%s,
                  completed_at=NOW(), updated_at=NOW()
        """, (username, tenant_id, json.dumps(answers), json.dumps(answers)))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[Onboarding] Erreur sauvegarde: {e}")

    print(f"[Onboarding] {username} complet : {rules_created} règles, {insights_created} insights")
    return {
        "status":          "completed",
        "rules_created":   rules_created,
        "insights_created": insights_created,
        "profile_summary": parsed.get("profile_summary", ""),
    }
