"""
Log d'activite utilisateur pour l'intelligence de workflow (7-ACT).
Chaque action faite via Raya est loggee ici.
Le moteur de patterns (5G-4) analysera ces sequences.

action_type valeurs :
  mail_read, mail_reply_queued, mail_archive, mail_delete,
  drive_list, drive_read, drive_search, drive_create,
  teams_read, teams_send, calendar_create,
  learn, insight, search, conversation

8-COLLAB : parametre shared=True publie automatiquement l'activite
comme evenement tenant visible par l'equipe.
"""
from app.database import get_pg_conn
from app.logging_config import get_logger

logger = get_logger("raya.activity")


def log_activity(
    username: str,
    action_type: str,
    action_target: str = None,
    action_detail: str = None,
    tenant_id: str = None,
    source: str = None,
    shared: bool = False,
    shared_title: str = None,
    shared_event_type: str = "task_completed",
) -> None:
    """
    Log une action utilisateur. Non bloquant (silencieux si erreur).

    shared=True (8-COLLAB) : publie automatiquement l'activite comme
    evenement tenant visible par tous les membres du tenant.
    shared_title : titre de l'evenement (defaut: action_target).
    shared_event_type : type d'evenement tenant (defaut: task_completed).
    """
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        if source:
            # activity_log peut avoir une colonne source (8-OBSERVE)
            try:
                c.execute("""
                    INSERT INTO activity_log
                        (username, tenant_id, action_type, action_target, action_detail, source)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (username, tenant_id, action_type,
                      (action_target or "")[:200], (action_detail or "")[:500], source))
            except Exception:
                # Colonne source absente -> fallback sans source
                c.execute("""
                    INSERT INTO activity_log
                        (username, tenant_id, action_type, action_target, action_detail)
                    VALUES (%s, %s, %s, %s, %s)
                """, (username, tenant_id, action_type,
                      (action_target or "")[:200], (action_detail or "")[:500]))
        else:
            c.execute("""
                INSERT INTO activity_log
                    (username, tenant_id, action_type, action_target, action_detail)
                VALUES (%s, %s, %s, %s, %s)
            """, (username, tenant_id, action_type,
                  (action_target or "")[:200], (action_detail or "")[:500]))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"[Activity] Erreur log: {e}")

    # 8-COLLAB : publication automatique si shared=True
    if shared and tenant_id:
        try:
            from app.tenant_events import publish_event
            publish_event(
                tenant_id=tenant_id,
                username=username,
                event_type=shared_event_type,
                title=shared_title or action_target or action_type,
                body=action_detail or None,
            )
        except Exception as e:
            logger.error(f"[Activity] shared publish_event: {e}")


def get_recent_activity(username: str, hours: int = 24, limit: int = 50) -> list:
    """Retourne les dernieres activites d'un utilisateur."""
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            SELECT action_type, action_target, action_detail, tenant_id, created_at
            FROM activity_log
            WHERE username = %s AND created_at > NOW() - (%s || ' hours')::INTERVAL
            ORDER BY created_at DESC LIMIT %s
        """, (username, str(hours), limit))
        cols = [d[0] for d in c.description]
        return [dict(zip(cols, r)) for r in c.fetchall()]
    except Exception:
        return []
    finally:
        if conn: conn.close()


def get_activity_sequences(username: str, days: int = 30, limit: int = 200) -> list:
    """Retourne les activites recentes pour l'analyse de sequences."""
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            SELECT action_type, action_target, action_detail, tenant_id,
                   created_at,
                   created_at - LAG(created_at) OVER (ORDER BY created_at) AS gap
            FROM activity_log
            WHERE username = %s AND created_at > NOW() - (%s || ' days')::INTERVAL
            ORDER BY created_at DESC LIMIT %s
        """, (username, str(days), limit))
        cols = [d[0] for d in c.description]
        return [dict(zip(cols, r)) for r in c.fetchall()]
    except Exception:
        return []
    finally:
        if conn: conn.close()
