"""
Module de feedback Raya — Phase 3b.

Gère la boucle de correction par feedback 👍👎 (décision Opus B7) :
  - save_response_metadata() : stocke tier, règles injectées, via_rag à chaque réponse
  - get_response_metadata()  : retrouve ces infos pour le bouton "Pourquoi ?"
  - process_positive_feedback() : renforce les règles injectées (+0.05 confiance)
  - process_negative_feedback() : appel Opus → formule une règle corrective

Tout est non-bloquant : les erreurs ne doivent jamais interrompre la conversation.
"""
import json
from app.database import get_pg_conn


def save_response_metadata(
    aria_memory_id: int,
    username: str,
    tenant_id: str,
    model_tier: str,
    model_name: str,
    via_rag: bool,
    rule_ids: list,
) -> None:
    """
    Stocke les métadonnées de raisonnement d'une réponse Raya.
    Appelé en background thread depuis raya.py — les erreurs sont avalées.
    """
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            INSERT INTO aria_response_metadata
              (aria_memory_id, username, tenant_id, model_tier, model_name, via_rag, rule_ids_injected)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (
            aria_memory_id, username, tenant_id,
            model_tier, model_name, via_rag,
            json.dumps(rule_ids or []),
        ))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[Feedback] save_response_metadata échoué (non bloquant) : {e}")


def get_response_metadata(aria_memory_id: int, username: str,
                          tenant_id: str | None = None) -> dict | None:
    """
    Retourne les métadonnées + détails des règles injectées pour le bouton "Pourquoi ?".
    """
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            SELECT id, model_tier, model_name, via_rag, rule_ids_injected,
                   feedback_type, feedback_comment, corrective_rule_id, created_at
            FROM aria_response_metadata
            WHERE aria_memory_id = %s AND username = %s
              AND (tenant_id = %s OR tenant_id IS NULL)
            LIMIT 1
        """, (aria_memory_id, username, tenant_id))
        row = c.fetchone()
        if not row:
            conn.close()
            return None

        meta_id, tier, model, via_rag, rule_ids_raw, fb_type, fb_comment, corr_id, created = row
        # psycopg2 deserialize JSONB en list/dict Python automatiquement.
        # Pas besoin de json.loads. Fallback string si valeur historique.
        if isinstance(rule_ids_raw, list):
            rule_ids = rule_ids_raw
        elif isinstance(rule_ids_raw, str):
            rule_ids = json.loads(rule_ids_raw) if rule_ids_raw else []
        else:
            rule_ids = []

        # Charge le détail des règles injectées
        rules_detail = []
        if rule_ids:
            c.execute("""
                SELECT id, category, rule, confidence, reinforcements
                FROM aria_rules
                WHERE id = ANY(%s) AND username = %s
                  AND (tenant_id = %s OR tenant_id IS NULL)
            """, (rule_ids, username, tenant_id))
            rules_detail = [
                {"id": r[0], "category": r[1], "rule": r[2],
                 "confidence": r[3], "reinforcements": r[4]}
                for r in c.fetchall()
            ]
        conn.close()

        return {
            "meta_id":        meta_id,
            "aria_memory_id": aria_memory_id,
            "model_tier":     tier,
            "model_name":     model,
            "via_rag":        via_rag,
            "rule_ids":       rule_ids,
            "rules_detail":   rules_detail,
            "feedback_type":  fb_type,
            "feedback_comment": fb_comment,
            "corrective_rule_id": corr_id,
            "created_at":     str(created),
        }
    except Exception as e:
        print(f"[Feedback] get_response_metadata échoué : {e}")
        return None


def process_positive_feedback(
    aria_memory_id: int,
    username: str,
    tenant_id: str,
) -> bool:
    """
    👍 Renforce les règles qui étaient injectées dans ce contexte (+0.05 confiance).
    Retourne True si au moins une règle a été renforcée.
    """
    try:
        conn = get_pg_conn()
        c = conn.cursor()

        # Récupère les rule_ids
        c.execute("""
            SELECT rule_ids_injected FROM aria_response_metadata
            WHERE aria_memory_id = %s AND username = %s
              AND (tenant_id = %s OR tenant_id IS NULL)
            LIMIT 1
        """, (aria_memory_id, username, tenant_id))
        row = c.fetchone()
        if not row:
            conn.close()
            return False

        # psycopg2 deserialize JSONB en list Python automatiquement.
        # Avant ce fix : json.loads sur une list -> TypeError silencieux
        # (avale par le thread daemon) -> 👍 jamais traite, regle jamais
        # renforcee, feedback_type jamais update.
        raw = row[0]
        if isinstance(raw, list):
            rule_ids = raw
        elif isinstance(raw, str):
            rule_ids = json.loads(raw) if raw else []
        else:
            rule_ids = []
        if not rule_ids:
            conn.close()
            return False

        # Renforce chaque règle
        c.execute("""
            UPDATE aria_rules
            SET confidence     = LEAST(1.0, confidence + 0.05),
                reinforcements = reinforcements + 1,
                updated_at     = NOW()
            WHERE id = ANY(%s) AND username = %s
              AND (tenant_id = %s OR tenant_id IS NULL)
        """, (rule_ids, username, tenant_id))

        # Met à jour le feedback dans les métadonnées
        c.execute("""
            UPDATE aria_response_metadata
            SET feedback_type = 'positive'
            WHERE aria_memory_id = %s AND username = %s
              AND (tenant_id = %s OR tenant_id IS NULL)
        """, (aria_memory_id, username, tenant_id))

        conn.commit()
        conn.close()
        print(f"[Feedback] 👍 {len(rule_ids)} règles renforcées pour {username}")
        return True
    except Exception as e:
        print(f"[Feedback] process_positive_feedback échoué : {e}")
        return False


def process_negative_feedback(
    aria_memory_id: int,
    username: str,
    tenant_id: str,
    comment: str = "",
) -> dict:
    """
    👎 Appel Opus pour formuler une règle corrective à partir du feedback négatif.

    Workflow :
      1. Récupère la conversation originale (user_input + aria_response)
      2. Récupère les règles qui étaient injectées
      3. Appel Opus avec le contexte → formule une règle corrective
      4. Stocke la règle corrective dans aria_rules (confidence 0.8)
      5. Met à jour aria_response_metadata avec le feedback et l'id de la règle corrective

    Retourne : {status, rule_id, rule_text, category}
    """
    try:
        conn = get_pg_conn()
        c = conn.cursor()

        # Conversation originale
        c.execute("""
            SELECT user_input, aria_response FROM aria_memory
            WHERE id = %s AND username = %s
              AND (tenant_id = %s OR tenant_id IS NULL)
        """, (aria_memory_id, username, tenant_id))
        conv = c.fetchone()
        if not conv:
            conn.close()
            return {"status": "error", "message": "Conversation introuvable"}
        user_input, aria_response = conv

        # Règles injectées
        c.execute("""
            SELECT rule_ids_injected FROM aria_response_metadata
            WHERE aria_memory_id = %s AND username = %s
              AND (tenant_id = %s OR tenant_id IS NULL)
            LIMIT 1
        """, (aria_memory_id, username, tenant_id))
        meta_row = c.fetchone()
        # Meme bug fix que process_positive_feedback : JSONB -> list deja
        # deserialisee par psycopg2.
        if meta_row and meta_row[0]:
            raw = meta_row[0]
            if isinstance(raw, list):
                rule_ids = raw
            elif isinstance(raw, str):
                rule_ids = json.loads(raw)
            else:
                rule_ids = []
        else:
            rule_ids = []

        rules_context = ""
        if rule_ids:
            c.execute("""
                SELECT category, rule FROM aria_rules
                WHERE id = ANY(%s) AND username = %s
                  AND (tenant_id = %s OR tenant_id IS NULL)
            """, (rule_ids, username, tenant_id))
            rules_rows = c.fetchall()
            if rules_rows:
                rules_context = "\n".join([f"[{r[0]}] {r[1]}" for r in rules_rows])
        conn.close()

        # Prompt Opus pour la règle corrective
        rules_section = f"\nRègles qui étaient actives :\n{rules_context}" if rules_context else ""
        comment_section = f"\nCommentaire de l'utilisateur : {comment}" if comment else ""
        prompt = f"""L'utilisateur a marqué cette réponse de Raya comme incorrecte ou insatisfaisante.

Question de l'utilisateur : {user_input[:300]}
Réponse de Raya : {aria_response[:500]}{rules_section}{comment_section}

Formule UNE règle corrective précise que Raya devrait apprendre pour mieux répondre à ce type de situation.
Format JSON strict (sans backticks) :
{{"category": "catégorie_parmi_comportement_tri_mails_style_reponse_contacts_cles_ou_autre", "rule": "La règle apprise"}}"""

        from app.llm_client import llm_complete, log_llm_usage
        import re
        result = llm_complete(
            messages=[{"role": "user", "content": prompt}],
            model_tier="deep",
            max_tokens=300,
        )
        log_llm_usage(result, username=username, tenant_id=tenant_id,
                      purpose="negative_feedback_correction")

        raw = re.sub(r'^```(?:json)?\s*', '', result["text"].strip(), flags=re.MULTILINE)
        raw = re.sub(r'\s*```$', '', raw, flags=re.MULTILINE).strip()
        parsed = json.loads(raw)

        category = parsed.get("category", "Comportement")
        rule_text = parsed.get("rule", "")
        if not rule_text:
            return {"status": "error", "message": "Opus n'a pas pu formuler de règle"}

        # Stocke la règle corrective (confiance 0.8 — plus haute car correction explicite)
        from app.memory_rules import save_rule
        rule_id = save_rule(
            category=category,
            rule=rule_text,
            source="feedback_negative",
            confidence=0.8,
            username=username,
            tenant_id=tenant_id,
        )

        # Met à jour les métadonnées
        # F.2 (audit isolation user-user, LOT 1.7) : ajout filtre
        # tenant_id pour coherence avec les autres queries du fichier.
        # Protege deja par aria_memory_id (PK unique) + username, mais
        # ajoute la defense en profondeur.
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            UPDATE aria_response_metadata
            SET feedback_type      = 'negative',
                feedback_comment   = %s,
                corrective_rule_id = %s
            WHERE aria_memory_id = %s AND username = %s
              AND (tenant_id = %s OR tenant_id IS NULL)
        """, (comment or None, rule_id, aria_memory_id, username, tenant_id))
        conn.commit()
        conn.close()

        print(f"[Feedback] 👎 Règle corrective créée pour {username}: [{category}] {rule_text[:60]}")
        return {
            "status":    "ok",
            "rule_id":   rule_id,
            "rule_text": rule_text,
            "category":  category,
        }

    except Exception as e:
        print(f"[Feedback] process_negative_feedback échoué : {e}")
        return {"status": "error", "message": str(e)}
