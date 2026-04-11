"""
Validation des nouvelles regles avant ecriture en base (B30).

Utilise la recherche semantique (RAG) pour trouver les 5 regles
les plus proches, puis soumet ce sous-ensemble cible a Opus.

Avantage : precision de detection beaucoup plus haute que la comparaison
textuelle en bloc, et cout Opus reduit (5 regles vs 30+).

Decisions :
    NEW       — regle genuinement nouvelle, inserer
    DUPLICATE — doublon semantique d'une regle existante, ignorer
    REFINE    — ameliore une regle existante, remplacer
    SPLIT     — contient deux idees, separer en deux LEARN
    CONFLICT  — contredit une regle existante, demander a l'utilisateur
"""
import json
from app.database import get_pg_conn
from app.llm_client import llm_complete


def validate_rule_before_save(
    username: str,
    tenant_id: str,
    category: str,
    new_rule_text: str,
) -> dict:
    """
    Valide une regle avant insertion.

    Returns:
        {
            "decision": "NEW|DUPLICATE|REFINE|SPLIT|CONFLICT",
            "rules_to_add": [{"category": str, "rule": str}],
            "rules_to_update": [{"id": int, "rule": str}],
            "rules_to_skip": [int],
            "conflict_message": str | None,
        }
    """
    similar = _find_similar_rules(new_rule_text, username, tenant_id)

    if not similar:
        # Pas de regles similaires -> NEW direct, pas besoin d'Opus
        return {
            "decision": "NEW",
            "rules_to_add": [{"category": category, "rule": new_rule_text}],
            "rules_to_update": [],
            "rules_to_skip": [],
            "conflict_message": None,
        }

    return _call_opus(category, new_rule_text, similar)


def _find_similar_rules(rule_text: str, username: str, tenant_id: str) -> list:
    """Cherche les 5 regles existantes les plus proches semantiquement (toutes categories)."""
    try:
        from app.embedding import search_similar, is_available
        if not is_available():
            return _fallback_rules(username, tenant_id)

        rows = search_similar(
            table="aria_rules",
            username=username,
            query_text=rule_text,
            limit=5,
            tenant_id=tenant_id,
            extra_filter="active = true AND category != 'memoire'",
        )
        return rows or []
    except Exception as e:
        print(f"[rule_validator] search_similar error: {e}")
        return []


def _fallback_rules(username: str, tenant_id: str) -> list:
    """Fallback sans embedding : retourne les 10 regles actives par confiance."""
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            SELECT id, category, rule, confidence
            FROM aria_rules
            WHERE username = %s AND active = true AND category != 'memoire'
              AND (tenant_id = %s OR tenant_id IS NULL)
            ORDER BY confidence DESC, reinforcements DESC
            LIMIT 10
        """, (username, tenant_id))
        rows = c.fetchall()
        return [{"id": r[0], "category": r[1], "rule": r[2], "confidence": float(r[3] or 0)} for r in rows]
    except Exception:
        return []
    finally:
        if conn: conn.close()


def _call_opus(category: str, new_rule: str, similar_rules: list) -> dict:
    """Appelle Opus pour decider NEW/DUPLICATE/REFINE/SPLIT/CONFLICT."""
    rules_text = "\n".join([
        f"  [id:{r.get('id', '?')}][{r.get('category', '?')}] {r.get('rule', '')}"
        for r in similar_rules
    ])

    prompt = f"""Tu es un validateur de regles comportementales pour un assistant IA.

Nouvelle regle proposee (categorie cible : {category}) :
  "{new_rule}"

Regles existantes les plus proches semantiquement :
{rules_text}

Analyse et retourne UNIQUEMENT un objet JSON (sans markdown) avec cette structure :
{{
  "decision": "NEW|DUPLICATE|REFINE|SPLIT|CONFLICT",
  "reasoning": "explication courte en une phrase",
  "rules_to_add": [
    {{"category": "{category}", "rule": "texte exact de la regle a inserer"}}
  ],
  "rules_to_update": [
    {{"id": 0, "rule": "nouveau texte de la regle existante"}}
  ],
  "rules_to_skip": [],
  "conflict_message": null
}}

Criteres :
- NEW : apporte quelque chose de genuinement nouveau -> rules_to_add avec la regle, rules_to_update vide
- DUPLICATE : semantiquement identique a une existante -> rules_to_add VIDE, rules_to_skip contient l'id de la regle conservee
- REFINE : ameliore une regle existante -> rules_to_update avec la version amelioree, rules_to_add VIDE
- SPLIT : contient deux idees distinctes -> rules_to_add contient DEUX regles separees
- CONFLICT : contredit une regle existante -> rules_to_add VIDE, conflict_message explique le conflit en francais

Retourne uniquement le JSON brut, sans aucune explication ni balises."""

    try:
        result = llm_complete(
            messages=[{"role": "user", "content": prompt}],
            model_tier="deep",
            max_tokens=1024,
        )
        text = result["text"].strip()
        # Strip markdown fences si presentes
        if "```" in text:
            parts = text.split("```")
            for p in parts:
                p = p.strip()
                if p.startswith("json"):
                    p = p[4:].strip()
                try:
                    return _normalize(json.loads(p), category, new_rule)
                except Exception:
                    pass
        return _normalize(json.loads(text), category, new_rule)
    except Exception as e:
        print(f"[rule_validator] Opus error: {e} — fallback NEW")
        return {
            "decision": "NEW",
            "rules_to_add": [{"category": category, "rule": new_rule}],
            "rules_to_update": [],
            "rules_to_skip": [],
            "conflict_message": None,
        }


def _normalize(data: dict, category: str, new_rule: str) -> dict:
    """Normalise la reponse Opus avec valeurs par defaut."""
    decision = data.get("decision", "NEW").upper()
    if decision not in ("NEW", "DUPLICATE", "REFINE", "SPLIT", "CONFLICT"):
        decision = "NEW"

    rules_to_add = data.get("rules_to_add", [])
    if decision == "NEW" and not rules_to_add:
        rules_to_add = [{"category": category, "rule": new_rule}]

    return {
        "decision": decision,
        "rules_to_add": rules_to_add,
        "rules_to_update": data.get("rules_to_update", []),
        "rules_to_skip": data.get("rules_to_skip", []),
        "conflict_message": data.get("conflict_message"),
    }


def apply_validation_result(result: dict, username: str, tenant_id: str) -> list:
    """
    Applique le resultat de validation en base.
    Retourne la liste des messages de confirmation.
    """
    from app.memory_loader import save_rule
    messages = []

    for item in result.get("rules_to_add", []):
        try:
            save_rule(item["category"], item["rule"], "auto", 0.7, username)
            messages.append(f"+ [{item['category']}]")
        except Exception as e:
            print(f"[rule_validator] save_rule error: {e}")

    for item in result.get("rules_to_update", []):
        conn = None
        try:
            conn = get_pg_conn()
            c = conn.cursor()
            c.execute(
                "UPDATE aria_rules SET rule = %s WHERE id = %s AND username = %s",
                (item["rule"], item["id"], username),
            )
            conn.commit()
            messages.append(f"~ regle #{item['id']} mise a jour")
        except Exception as e:
            print(f"[rule_validator] update_rule error: {e}")
        finally:
            if conn: conn.close()

    return messages
