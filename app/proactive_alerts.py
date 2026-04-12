"""
CRUD des alertes proactives de Raya.
Permet de creer, lister, marquer vues et nettoyer les alertes.
"""
from app.database import get_pg_conn


def create_alert(
    username: str,
    tenant_id: str,
    alert_type: str,
    priority: str,
    title: str,
    body: str = "",
    source_type: str = None,
    source_id: str = None,
) -> int:
    """
    Insere une alerte proactive.
    Deduplique par (username, title, source_id) sur les 24 dernieres heures.
    Retourne l'id de l'alerte inseree ou 0 si doublon.
    """
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        # Deduplication : meme source_id dans les 24h
        if source_id:
            c.execute("""
                SELECT id FROM proactive_alerts
                WHERE username = %s AND source_id = %s
                  AND created_at > NOW() - INTERVAL '24 hours'
                LIMIT 1
            """, (username, source_id))
            if c.fetchone():
                return 0
        c.execute("""
            INSERT INTO proactive_alerts
              (username, tenant_id, alert_type, priority, title, body, source_type, source_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (username, tenant_id, alert_type, priority, title, body or "",
               source_type, source_id))
        alert_id = c.fetchone()[0]
        conn.commit()
        return alert_id
    except Exception as e:
        print(f"[ProactiveAlerts] Erreur create_alert: {e}")
        return 0
    finally:
        if conn: conn.close()


def get_active_alerts(username: str, limit: int = 10) -> list:
    """
    Retourne les alertes non vues, non dismissed, non expirees,
    triees par priority DESC puis created_at DESC.
    """
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            SELECT id, alert_type, priority, title, body, source_type, source_id, created_at
            FROM proactive_alerts
            WHERE username = %s
              AND seen = false
              AND dismissed = false
              AND expires_at > NOW()
            ORDER BY
                CASE priority
                    WHEN 'critical' THEN 0
                    WHEN 'high'     THEN 1
                    WHEN 'normal'   THEN 2
                    WHEN 'low'      THEN 3
                    ELSE 4
                END ASC,
                created_at DESC
            LIMIT %s
        """, (username, limit))
        cols = ["id", "alert_type", "priority", "title", "body",
                "source_type", "source_id", "created_at"]
        return [dict(zip(cols, row)) for row in c.fetchall()]
    except Exception as e:
        print(f"[ProactiveAlerts] Erreur get_active_alerts: {e}")
        return []
    finally:
        if conn: conn.close()


def mark_seen(alert_ids: list, username: str) -> int:
    """
    Marque les alertes comme vues.
    Retourne le nombre mis a jour.
    """
    if not alert_ids:
        return 0
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            UPDATE proactive_alerts
            SET seen = true
            WHERE id = ANY(%s) AND username = %s
        """, (alert_ids, username))
        updated = c.rowcount
        conn.commit()
        return updated
    except Exception as e:
        print(f"[ProactiveAlerts] Erreur mark_seen: {e}")
        return 0
    finally:
        if conn: conn.close()


def dismiss_alert(alert_id: int, username: str) -> bool:
    """Marque une alerte comme dismissed. Retourne True si succes."""
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            UPDATE proactive_alerts
            SET dismissed = true
            WHERE id = %s AND username = %s
        """, (alert_id, username))
        ok = c.rowcount > 0
        conn.commit()
        return ok
    except Exception as e:
        print(f"[ProactiveAlerts] Erreur dismiss_alert: {e}")
        return False
    finally:
        if conn: conn.close()


def cleanup_expired() -> int:
    """Supprime les alertes expirees depuis plus de 7 jours. Retourne le nombre supprime."""
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            DELETE FROM proactive_alerts
            WHERE expires_at < NOW() - INTERVAL '7 days'
        """)
        deleted = c.rowcount
        conn.commit()
        return deleted
    except Exception as e:
        print(f"[ProactiveAlerts] Erreur cleanup_expired: {e}")
        return 0
    finally:
        if conn: conn.close()
