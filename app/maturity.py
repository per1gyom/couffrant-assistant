"""
Score de maturite relationnelle Raya/utilisateur.

Trois phases :
  - DISCOVERY      : Raya decouvre, confirme, explore (score 0-39)
  - CONSOLIDATION  : Raya est a l'aise, confirme moins (score 40-74)
  - MATURITY       : Raya est autonome, propose des automatisations (score 75+)

Recalcule a chaque appel (leger, 1 requete SQL agregee).
"""
from app.database import get_pg_conn

PHASE_DISCOVERY     = "discovery"
PHASE_CONSOLIDATION = "consolidation"
PHASE_MATURITY      = "maturity"

ADAPTIVE_PARAMS = {
    "discovery": {
        "synth_every_n":     8,
        "decay_per_week":    0.08,
        "mask_threshold":    0.30,
        "confirm_frequency": "frequent",
        "proactivity_level": "observe",
    },
    "consolidation": {
        "synth_every_n":     15,
        "decay_per_week":    0.05,
        "mask_threshold":    0.30,
        "confirm_frequency": "occasional",
        "proactivity_level": "suggest",
    },
    "maturity": {
        "synth_every_n":     30,
        "decay_per_week":    0.02,
        "mask_threshold":    0.20,
        "confirm_frequency": "rare",
        "proactivity_level": "automate",
    },
}


def compute_maturity_score(username: str) -> dict:
    """
    Calcule le score de maturite (0-100) et la phase.

    Criteres ponderes :
      - Nombre de regles actives       (max 20 pts) : 1 pt par regle, cap 20
      - Total renforcements            (max 20 pts) : 1 pt par 5 renforcements, cap 20
      - Nombre de conversations        (max 20 pts) : 1 pt par 10 conversations, cap 20
      - Anciennete du compte en jours  (max 20 pts) : 1 pt par 3 jours, cap 20
      - Taux feedback positif          (max 20 pts) : ratio positif/(positif+negatif) * 20

    Retourne : {
        "score": int (0-100),
        "phase": str (discovery/consolidation/maturity),
        "details": {
            "rules_active": int,
            "total_reinforcements": int,
            "conversation_count": int,
            "account_age_days": int,
            "feedback_positive_ratio": float,
        }
    }
    """
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()

        # Tout en une seule requete agregee pour la performance
        c.execute("""
            SELECT
                (SELECT COUNT(*) FROM aria_rules
                 WHERE username = %s AND active = true) AS rules_active,
                (SELECT COALESCE(SUM(reinforcements), 0) FROM aria_rules
                 WHERE username = %s AND active = true) AS total_reinforcements,
                (SELECT COUNT(*) FROM aria_memory
                 WHERE username = %s) AS conversation_count,
                (SELECT EXTRACT(DAY FROM NOW() - MIN(created_at))
                 FROM users WHERE username = %s) AS account_age_days,
                (SELECT COUNT(*) FROM aria_response_metadata
                 WHERE username = %s AND feedback_type = 'positive') AS fb_positive,
                (SELECT COUNT(*) FROM aria_response_metadata
                 WHERE username = %s AND feedback_type = 'negative') AS fb_negative
        """, (username, username, username, username, username, username))

        row = c.fetchone()
        rules         = row[0] or 0
        reinforcements = row[1] or 0
        conversations  = row[2] or 0
        age_days       = int(row[3] or 0)
        fb_pos         = row[4] or 0
        fb_neg         = row[5] or 0

        # Calcul des points
        pts_rules          = min(20, rules)
        pts_reinforcements = min(20, reinforcements // 5)
        pts_conversations  = min(20, conversations // 10)
        pts_age            = min(20, age_days // 3)
        fb_total           = fb_pos + fb_neg
        fb_ratio           = fb_pos / fb_total if fb_total > 0 else 0.5
        pts_feedback       = int(fb_ratio * 20)

        score = pts_rules + pts_reinforcements + pts_conversations + pts_age + pts_feedback

        if score >= 75:
            phase = PHASE_MATURITY
        elif score >= 40:
            phase = PHASE_CONSOLIDATION
        else:
            phase = PHASE_DISCOVERY

        return {
            "score": min(100, score),
            "phase": phase,
            "details": {
                "rules_active":             rules,
                "total_reinforcements":     reinforcements,
                "conversation_count":       conversations,
                "account_age_days":         age_days,
                "feedback_positive_ratio":  round(fb_ratio, 2),
            },
        }
    except Exception:
        return {"score": 0, "phase": PHASE_DISCOVERY, "details": {}}
    finally:
        if conn:
            conn.close()


def get_adaptive_params(username: str) -> dict:
    """
    Retourne les parametres adaptatifs pour l'utilisateur,
    bases sur sa phase de maturite actuelle.
    Inclut aussi le score et la phase dans le retour.
    """
    maturity = compute_maturity_score(username)
    phase = maturity["phase"]
    params = ADAPTIVE_PARAMS.get(phase, ADAPTIVE_PARAMS["discovery"]).copy()
    params["phase"] = phase
    params["score"] = maturity["score"]
    return params
