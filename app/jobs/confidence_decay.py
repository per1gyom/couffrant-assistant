"""
Job de décroissance temporelle de confiance (décision Opus B6) — Phase 4.

Planification : 1x/mois, 1er du mois à 3h (app/scheduler.py)

Logique :
  - Règles actives non renforcées depuis > 30 jours → confidence -= 0.05
  - Minimum absolu : 0.10 (jamais à zéro, conservation totale)
  - Sous 0.30 → exclues du RAG (filtrées dans rag.py via WHERE confidence >= 0.3)
  - Règles protégées (non dégradées) :
      source IN ('seed', 'feedback_negative', 'onboarding')
      confidence >= 0.9 (règles très confiantes)

Pas de suppression — les règles sous 0.3 restent en base,
masquées du RAG mais visibles dans le panel admin.

Migration auto : colonne last_reinforced_at si absente.
"""
from app.database import get_pg_conn
from app.logging_config import get_logger

logger = get_logger("raya.scheduler")


def _ensure_column():
    """Ajoute last_reinforced_at sur aria_rules si elle n'existe pas encore."""
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            ALTER TABLE aria_rules
            ADD COLUMN IF NOT EXISTS last_reinforced_at TIMESTAMP DEFAULT NOW()
        """)
        c.execute("""
            UPDATE aria_rules
            SET last_reinforced_at = updated_at
            WHERE last_reinforced_at IS NULL
        """)
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[ConfidenceDecay] Migration colonne : {e}")


_ensure_column()


def run(dry_run: bool = False) -> dict:
    """
    Applique la décroissance de confiance sur toutes les règles éligibles.

    Args:
        dry_run : si True, calcule sans écrire (pour diagnostic)

    Retourne : {degraded, below_threshold, dry_run}
    """
    try:
        conn = get_pg_conn()
        c = conn.cursor()

        c.execute("""
            SELECT COUNT(*) FROM aria_rules
            WHERE active = true
              AND source NOT IN ('seed', 'feedback_negative', 'onboarding')
              AND confidence < 0.9
              AND COALESCE(last_reinforced_at, updated_at, created_at)
                  < NOW() - INTERVAL '30 days'
        """)
        eligible = c.fetchone()[0]

        if not dry_run and eligible > 0:
            c.execute("""
                UPDATE aria_rules
                SET confidence = GREATEST(0.10, confidence - 0.05),
                    updated_at = NOW()
                WHERE active = true
                  AND source NOT IN ('seed', 'feedback_negative', 'onboarding')
                  AND confidence < 0.9
                  AND COALESCE(last_reinforced_at, updated_at, created_at)
                      < NOW() - INTERVAL '30 days'
            """)
            degraded = c.rowcount
            conn.commit()
        else:
            degraded = eligible if dry_run else 0

        c.execute("SELECT COUNT(*) FROM aria_rules WHERE active = true AND confidence < 0.30")
        below_threshold = c.fetchone()[0]
        conn.close()

        print(f"[Scheduler] confidence_decay : {degraded} règles dégradées, "
              f"{below_threshold} sous seuil RAG (0.30)")
        return {"degraded": degraded, "below_threshold": below_threshold, "dry_run": dry_run}

    except Exception as e:
        print(f"[Scheduler] confidence_decay erreur : {e}")
        return {"degraded": 0, "below_threshold": 0, "error": str(e)}


def _job_confidence_decay():
    """Wrapper APScheduler — hebdo (lundi 02h00). Applique la décroissance de confiance."""
    try:
        result = run(dry_run=False)
        logger.info(
            "[Scheduler] confidence_decay : %d règles dégradées, %d sous seuil RAG (0.30)",
            result.get("degraded", 0), result.get("below_threshold", 0)
        )
    except Exception as e:
        logger.error("[Scheduler] confidence_decay erreur : %s", e)
