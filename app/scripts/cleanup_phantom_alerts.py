"""
Script one-shot : nettoyage des alertes 'connection_silence' devenues
obsoletes (la connexion est repassee en 'healthy' depuis la creation
de l alerte mais celle-ci est restee acknowledged=FALSE).

Usage :
  python3 -m app.scripts.cleanup_phantom_alerts          # dry-run par defaut
  python3 -m app.scripts.cleanup_phantom_alerts --apply  # vraie execution

Cree le 02/05/2026 suite au feedback Guillaume sur les 5 alertes
Gmail "degraded/down" affichees sur /admin/health/page alors que
les polls etaient OK depuis 22h.

Le bug a ete corrige dans connection_health.py.record_poll_attempt :
chaque poll OK acquitte desormais automatiquement les alertes
connection_silence du meme connection_id. Mais ce script nettoie
l historique deja existant en base.
"""

import argparse
import logging
import sys
from app.database import get_pg_conn

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("cleanup_phantom_alerts")


def find_phantom_alerts():
    """Retourne la liste des alertes connection_silence non acquittees
    pour lesquelles la connexion est aujourd hui en 'healthy' avec un
    poll recent (< 15 min)."""
    conn = get_pg_conn()
    try:
        c = conn.cursor()
        c.execute("""
            SELECT
              sa.id, sa.tenant_id, sa.component, sa.message, sa.created_at,
              ch.connection_id, ch.status, ch.last_successful_poll_at,
              ch.consecutive_failures
            FROM system_alerts sa
            JOIN connection_health ch
              ON ch.connection_id = SUBSTRING(sa.component FROM 'connection_(\d+)')::int
            WHERE sa.acknowledged = FALSE
              AND sa.alert_type = 'connection_silence'
              AND ch.status = 'healthy'
              AND ch.consecutive_failures = 0
              AND ch.last_successful_poll_at > NOW() - INTERVAL '15 minutes'
            ORDER BY sa.created_at DESC
        """)
        return c.fetchall()
    finally:
        conn.close()


def acknowledge_alerts(alert_ids):
    """Acquitte les alertes en lot avec acknowledged_by='auto_cleanup_phantom'."""
    if not alert_ids:
        return 0
    conn = get_pg_conn()
    try:
        c = conn.cursor()
        c.execute("""
            UPDATE system_alerts
            SET acknowledged = TRUE,
                acknowledged_at = NOW(),
                acknowledged_by = 'auto_cleanup_phantom',
                updated_at = NOW()
            WHERE id = ANY(%s)
        """, (alert_ids,))
        conn.commit()
        return c.rowcount
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true",
                        help="Execute vraiment (sinon dry-run)")
    args = parser.parse_args()

    phantoms = find_phantom_alerts()
    if not phantoms:
        logger.info("Aucune alerte fantome a nettoyer.")
        return 0

    logger.info("Trouve %d alerte(s) fantome(s) :", len(phantoms))
    for r in phantoms:
        sa_id, tenant, comp, msg, created, ch_id, status, last_ok, fails = r
        logger.info(
            "  - alert#%s tenant=%s component=%s status=%s last_ok=%s",
            sa_id, tenant, comp, status,
            last_ok.isoformat() if last_ok else None,
        )
        logger.info("    Message : %s", (msg or "")[:140])

    if not args.apply:
        logger.info("\n[DRY-RUN] Ajoute --apply pour executer vraiment.")
        return 0

    alert_ids = [r[0] for r in phantoms]
    n = acknowledge_alerts(alert_ids)
    logger.info("OK %d alerte(s) acquittee(s) avec acknowledged_by='auto_cleanup_phantom'", n)
    return 0


if __name__ == "__main__":
    sys.exit(main())
