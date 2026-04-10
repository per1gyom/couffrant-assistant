"""
Job d'expiration des pending_actions — Phase 4.

Planification : toutes les heures (app/scheduler.py)

Marque 'expired' toutes les actions sensibles en attente
dont expires_at < NOW() et status = 'pending'.
Sans LLM, très rapide (<10ms).
"""
from app.database import get_pg_conn


def run() -> int:
    """Expire les pending_actions dépassées. Retourne le nombre d'actions expirées."""
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            UPDATE pending_actions
            SET status = 'expired', cancelled_at = NOW()
            WHERE status = 'pending'
              AND expires_at < NOW()
        """)
        count = c.rowcount
        conn.commit()
        conn.close()
        if count:
            print(f"[Scheduler] pending_expiry : {count} action(s) expirée(s)")
        return count
    except Exception as e:
        print(f"[Scheduler] pending_expiry erreur : {e}")
        return 0
