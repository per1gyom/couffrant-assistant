"""
Module de feedback pour Raya — Phase 3b.

Gère les boutons 👍👎 sous chaque réponse.

👍 Feedback positif :
  Renforce silencieusement les règles qui étaient dans le contexte de la réponse.
  (+0.05 de confidence sur chaque règle injectée, plafonné à 1.0)

👎 Feedback négatif :
  Ouvre un mini-dialogue côté frontend pour recueillir le problème.
  Appel Opus pour formuler une règle corrective.
  La règle corrective est insérée dans aria_rules avec confidence 0.8.

Table aria_response_metadata : stocke pour chaque réponse :
  - model_tier, model_name, via_rag
  - rule_ids_injected (pour le renforcement/correction ciblé)
  - feedback_type et feedback_comment (remplis après le retour utilisateur)
"""
import json
from app.database import get_pg_conn


# ─── STOCKAGE DES MÉTADONNÉES ───

def save_response_metadata(
    aria_memory_id: int,
    username: str,
    tenant_id: str,
    model_tier: str,
    model_name: str,
    via_rag: bool,
    rule_ids: list,
) -> int | None:
    """
    Stocke les métadonnées de raisonnement d'une réponse.
    Retourne l'ID de la ligne insérée, ou None si échec.
    Non-bloquant : échec ignoré silencieusement.
    """
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            INSERT INTO aria_response_metadata
              (aria_memory_id, username, tenant_id, model_tier, model_name,
               via_rag, rule_ids_injected)
            VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb)
            RETURNING id
        """, (
            aria_memory_id, username, tenant_id,
            model_tier, model_name, via_rag,
            json.dumps(rule_ids or []),
        ))
        meta_id = c.fetchone()[0]
        conn.commit()
        conn.close()
        return meta_id
    except Exception as e:
        print(f"[feedback] save_response_metadata échoué : {e}")
        return None


def get_response_metadata(aria_memory_id: int, username: str) -> dict | None:
    """Récupère les métadonnées d'une réponse. Utilisé par le bouton Pourquoi ?."""
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            SELECT id, model_tier, model_name, via_rag, rule_ids_injected,
                   feedback_type, feedback_comment, created_at
            FROM aria_response_metadata
            WHERE aria_memory_id = %s AND username = %s
            LIMIT 1
        """, (aria_memory_id, username))
        row = c.fetchone()
        conn.close()
        if not row:
            return None
        return {
            "id":              row[0],
            "model_tier":      row[1],
            "model_name":      row[2],
            "via_rag":         row[3],
            "rule_ids":        row[4] or [],
            "feedback_type":   row[5],
            "feedback_comment": row[6],
            "created_at":      row[7].isoformat() if row[7] else None,
        }
    except Exception:
        return None


# ─── TRAITEMENT DU FEEDBACK ───

def process_positive_feedback(
    aria_memory_id: int,
    username: str,
    tenant_id: str,
) -> dict:
    """
    👍 Feedback positif : renforce les règles injectées dans cette réponse.
    +0.05 de confidence (plafond 1.0) sur chaque règle utilisée.
    """
    meta = get_response_metadata(aria_memory_id, username)
    if not meta:
        return {"ok": False, "error": "Métadonnées introuvables"}

    rule_ids = meta.get("rule_ids") or []
    if not rule_ids:
        _save_feedback(aria_memory_id, username, "positive", "")
        return {"ok": True, "rules_reinforced": 0}

    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            UPDATE aria_rules
            SET reinforcements = reinforcements + 1,
                confidence = LEAST(1.0, confidence + 0.05),
                updated_at = NOW()
            WHERE id = ANY(%s) AND username = %s
        """, (rule_ids, username))
        count = c.rowcount
        conn.commit()
        conn.close()
    except Exception as e:
        return {"ok": False, "error": str(e)}

    _save_feedback(aria_memory_id, username, "positive", "")
    print(f"[feedback] 👍 {username} — {count} règles renforcées (ids: {rule_ids})")
    return {"ok": True, "rules_reinforced": count}


def process_negative_feedback(
    aria_memory_id: int,
    username: str,
    tenant_id: str,
    comment: str = "",
) -> dict:
    """
    👎 Feedback négatif : Opus formule une règle corrective.

    Récupère la conversation originale + les règles injectées,
    demande à Opus d'identifier le problème et de formuler une règle corrective,
    puis insère cette règle dans aria_rules avec confidence 0.8.
    """
    meta = get_response_metadata(aria_memory_id, username)
    if not meta:
        return {"ok": False, "error": "Métadonnées introuvables"}

    # Récupérer la conversation originale
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute(
            "SELECT user_input, aria_response FROM aria_memory WHERE id = %s AND username = %s",
            (aria_memory_id, username)
        )
        row = c.fetchone()
        conn.close()
        if not row:
            return {"ok": False, "error": "Conversation introuvable"}
        user_input, aria_response = row
    except Exception as e:
        return {"ok": False, "error": str(e)}

    # Récupérer les règles qui étaient injectées
    rule_ids = meta.get("rule_ids") or []
    injected_rules_text = ""
    if rule_ids:
        try:
            conn = get_pg_conn()
            c = conn.cursor()
            c.execute(
                "SELECT category, rule FROM aria_rules WHERE id = ANY(%s)",
                (rule_ids,)
            )
            injected_rules_text = "\n".join(
                f"[{r[0]}] {r[1]}" for r in c.fetchall()
            )
            conn.close()
        except Exception:
            pass

    # Appel Opus pour formuler la règle corrective
    try:
        from app.llm_client import llm_complete, log_llm_usage
        prompt = f"""L'utilisateur a indiqué que cette réponse de Raya était insatisfaisante.

Question de l'utilisateur : {user_input[:400]}
Réponse de Raya : {aria_response[:600]}
Commentaire de l'utilisateur : {comment or '(aucun)'}

Règles qui étaient actives lors de cette réponse :
{injected_rules_text or '(aucune règle injectée)'}

Formule UNE seule règle corrective courte (max 150 caractères) qui améliorera
les prochaines réponses similaires. La règle doit être concrète et actionnable.
Réponds UNIQUEMENT avec le texte de la règle, sans explication."""

        result = llm_complete(
            messages=[{"role": "user", "content": prompt}],
            model_tier="deep",
            max_tokens=60,
        )
        log_llm_usage(result, username=username, tenant_id=tenant_id,
                      purpose="feedback_corrective_rule")
        corrective_rule = result["text"].strip().strip('"').strip()
    except Exception as e:
        _save_feedback(aria_memory_id, username, "negative", comment)
        return {"ok": False, "error": f"Opus indisponible : {str(e)[:100]}"}

    if not corrective_rule or len(corrective_rule) < 10:
        _save_feedback(aria_memory_id, username, "negative", comment)
        return {"ok": True, "corrective_rule": None, "message": "Règle trop courte — feedback enregistré"}

    # Insérer la règle corrective
    try:
        from app.memory_rules import save_rule
        rule_id = save_rule(
            category="comportement",
            rule=corrective_rule,
            source="feedback_negatif",
            confidence=0.8,
            username=username,
            tenant_id=tenant_id,
        )
    except Exception as e:
        _save_feedback(aria_memory_id, username, "negative", comment)
        return {"ok": False, "error": f"Insertion règle échouée : {str(e)[:100]}"}

    _save_feedback(aria_memory_id, username, "negative", comment,
                   corrective_rule_id=rule_id)
    print(f"[feedback] 👎 {username} — règle corrective créée id={rule_id}: {corrective_rule[:60]}")
    return {
        "ok": True,
        "corrective_rule": corrective_rule,
        "corrective_rule_id": rule_id,
    }


def _save_feedback(
    aria_memory_id: int,
    username: str,
    feedback_type: str,
    comment: str,
    corrective_rule_id: int = None,
):
    """Met à jour la ligne metadata avec le feedback reçu."""
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            UPDATE aria_response_metadata
            SET feedback_type = %s,
                feedback_comment = %s,
                corrective_rule_id = %s
            WHERE aria_memory_id = %s AND username = %s
        """, (feedback_type, comment or None, corrective_rule_id,
               aria_memory_id, username))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[feedback] _save_feedback échoué : {e}")
