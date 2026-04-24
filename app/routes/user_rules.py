"""
Endpoints utilisateur pour la gestion des règles Raya.

Permettent à l'utilisateur de consulter, éditer, supprimer ses propres
règles depuis la page /settings onglet "Mes règles Raya".

  GET    /memory/rules/stats       → compteurs par catégorie
  PUT    /memory/rules/{rule_id}   → éditer une règle (capture dialogue Raya)
  DELETE /memory/rules/{rule_id}   → soft-delete une règle (active=false, feedback)
"""
import json
from fastapi import APIRouter, Request, Body, Depends, Path

from app.database import get_pg_conn
from app.routes.deps import require_user
from app.logging_config import get_logger

logger = get_logger("raya.user_rules")
router = APIRouter(tags=["user_rules"])


@router.get("/rules/stats")
def rules_stats(request: Request, user: dict = Depends(require_user)):
    """Compteurs pour l'onglet 'Mes regles Raya'.

    Retourne :
    - total : nombre total de regles actives
    - review_needed : regles qui beneficieraient d'une revue (voir criteres)
    - by_category : compteurs par categorie

    Le compteur 'review_needed' remplace l'ancien 'new' (qui comptait 69 regles
    dont certaines deja super-renforcees, donc inutile de les revoir).

    Criteres 'a revoir' :
      - creee il y a moins de 14 jours
      - ET (confidence < 0.8 OU reinforcements <= 3)
    Autrement dit : les regles recentes dont Raya n'est pas encore sure.
    """
    username = user["username"]
    tenant_id = user["tenant_id"]
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute(
            "SELECT category, COUNT(*) FROM aria_rules "
            "WHERE username=%s AND (tenant_id=%s OR tenant_id IS NULL) AND active=true "
            "GROUP BY category ORDER BY COUNT(*) DESC",
            (username, tenant_id)
        )
        by_cat = {row[0] or 'Autres': row[1] for row in c.fetchall()}
        total = sum(by_cat.values())
        # Regles a revoir : recentes (7j) ET peu sures (conf<0.8 ET peu renforcees)
        # Le ET logique remplace le OU precedent pour eviter d'inclure
        # 92 regles sur 134 — on se concentre sur celles vraiment incertaines
        c.execute(
            "SELECT COUNT(*) FROM aria_rules "
            "WHERE username=%s AND (tenant_id=%s OR tenant_id IS NULL) AND active=true "
            "AND created_at > NOW() - INTERVAL '7 days' "
            "AND COALESCE(confidence, 0) < 0.8 "
            "AND COALESCE(reinforcements, 0) <= 2",
            (username, tenant_id)
        )
        review_count = c.fetchone()[0] or 0
        # Nouvelles (simple recence, pour l'info) — compat retro
        c.execute(
            "SELECT COUNT(*) FROM aria_rules "
            "WHERE username=%s AND (tenant_id=%s OR tenant_id IS NULL) AND active=true "
            "AND created_at > NOW() - INTERVAL '7 days'",
            (username, tenant_id)
        )
        new_count = c.fetchone()[0] or 0
        return {
            "total": total,
            "new": new_count,
            "review_needed": review_count,
            "by_category": by_cat,
        }
    except Exception as e:
        return {"error": str(e)[:100]}
    finally:
        if conn: conn.close()


@router.put("/rules/{rule_id}")
def update_rule(
    request: Request,
    rule_id: int = Path(...),
    payload: dict = Body(...),
    user: dict = Depends(require_user),
):
    """Edite une regle utilisateur + enregistre le dialogue avec Raya.

    Payload :
    {
      "rule": "nouveau texte",
      "category": "Comportement",
      "confidence": 0.9,
      "dialogue_turns": [{"role": "raya", "text": "..."}, {"role": "user", "text": "..."}],
      "feedback_text": "optionnel, resume du feedback"
    }
    """
    username = user["username"]
    tenant_id = user["tenant_id"]
    new_rule = (payload.get("rule") or "").strip()
    new_category = (payload.get("category") or "").strip()
    new_confidence = payload.get("confidence")
    dialogue_turns = payload.get("dialogue_turns") or []
    feedback_text = (payload.get("feedback_text") or "").strip() or None

    if not new_rule:
        return {"status": "error", "message": "Le texte de la regle est obligatoire."}
    if new_confidence is not None:
        try:
            new_confidence = float(new_confidence)
            if not (0.0 <= new_confidence <= 1.0):
                return {"status": "error", "message": "Confiance invalide (0.0 - 1.0)."}
        except Exception:
            new_confidence = None

    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        # Recupere la regle actuelle pour verif d'appartenance + sauvegarde old
        c.execute(
            "SELECT rule, category, confidence FROM aria_rules "
            "WHERE id=%s AND username=%s AND (tenant_id=%s OR tenant_id IS NULL)",
            (rule_id, username, tenant_id)
        )
        row = c.fetchone()
        if not row:
            return {"status": "error", "message": "Regle introuvable ou pas a toi."}
        old_rule, old_category, old_confidence = row

        # Update
        if new_confidence is not None:
            c.execute(
                "UPDATE aria_rules SET rule=%s, category=%s, confidence=%s, "
                "updated_at=NOW() WHERE id=%s",
                (new_rule, new_category or None, new_confidence, rule_id)
            )
        else:
            c.execute(
                "UPDATE aria_rules SET rule=%s, category=%s, updated_at=NOW() WHERE id=%s",
                (new_rule, new_category or None, rule_id)
            )

        # Log dans rule_modifications (pour vectorisation future)
        c.execute(
            "INSERT INTO rule_modifications "
            "(rule_id, username, tenant_id, action_type, dialogue_turns, feedback_text, "
            " old_rule, new_rule, old_category, new_category, old_confidence, new_confidence) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (rule_id, username, tenant_id, 'edit', json.dumps(dialogue_turns),
             feedback_text, old_rule, new_rule, old_category, new_category or None,
             old_confidence, new_confidence)
        )
        conn.commit()
        logger.info("[user_rules] Edit rule %d by %s (dialogue %d turns)",
                    rule_id, username, len(dialogue_turns))
        return {"status": "ok", "message": "Regle mise a jour."}
    except Exception as e:
        if conn: conn.rollback()
        logger.exception("[user_rules] Update error: %s", e)
        return {"status": "error", "message": str(e)[:150]}
    finally:
        if conn: conn.close()


@router.delete("/rules/{rule_id}")
def delete_rule(
    request: Request,
    rule_id: int = Path(...),
    payload: dict = Body(default={}),
    user: dict = Depends(require_user),
):
    """Soft-delete une regle utilisateur (active=false) + feedback obligatoire.

    Payload :
    {
      "feedback_text": "texte du feedback obligatoire",
      "dialogue_turns": [{"role": "raya", "text": "..."}, {"role": "user", "text": "..."}]
    }
    """
    username = user["username"]
    tenant_id = user["tenant_id"]
    feedback_text = (payload.get("feedback_text") or "").strip()
    dialogue_turns = payload.get("dialogue_turns") or []

    if not feedback_text:
        return {"status": "error",
                "message": "Un feedback est obligatoire — explique pourquoi tu supprimes."}

    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute(
            "SELECT rule, category, confidence FROM aria_rules "
            "WHERE id=%s AND username=%s AND (tenant_id=%s OR tenant_id IS NULL)",
            (rule_id, username, tenant_id)
        )
        row = c.fetchone()
        if not row:
            return {"status": "error", "message": "Regle introuvable ou pas a toi."}
        old_rule, old_category, old_confidence = row

        # Soft delete : active = false
        c.execute(
            "UPDATE aria_rules SET active=false, updated_at=NOW() WHERE id=%s",
            (rule_id,)
        )
        # Log
        c.execute(
            "INSERT INTO rule_modifications "
            "(rule_id, username, tenant_id, action_type, dialogue_turns, feedback_text, "
            " old_rule, old_category, old_confidence) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (rule_id, username, tenant_id, 'delete', json.dumps(dialogue_turns),
             feedback_text, old_rule, old_category, old_confidence)
        )
        conn.commit()
        logger.info("[user_rules] Delete rule %d by %s (feedback %d chars)",
                    rule_id, username, len(feedback_text))
        return {"status": "ok", "message": "Regle supprimee."}
    except Exception as e:
        if conn: conn.rollback()
        logger.exception("[user_rules] Delete error: %s", e)
        return {"status": "error", "message": str(e)[:150]}
    finally:
        if conn: conn.close()
