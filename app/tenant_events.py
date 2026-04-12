"""
Événements partagés au sein d'un tenant — collaboration inter-Raya (8-COLLAB).

Permet aux Rayas d'un même tenant de partager des événements métier sans
exposer les données personnelles de chaque utilisateur.

Table : tenant_events (créée automatiquement au premier appel).

Types d'événements :
  task_completed, document_modified, mail_important,
  meeting_scheduled, milestone_reached, alert_shared
"""
import json
from app.database import get_pg_conn
from app.logging_config import get_logger

logger = get_logger("raya.tenant_events")

VALID_EVENT_TYPES = {
    "task_completed", "document_modified", "mail_important",
    "meeting_scheduled", "milestone_reached", "alert_shared",
}


def _ensure_table():
    """Crée la table tenant_events + index si absents."""
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS tenant_events (
                id              SERIAL PRIMARY KEY,
                tenant_id       TEXT NOT NULL,
                source_username TEXT NOT NULL,
                event_type      TEXT NOT NULL,
                title           TEXT NOT NULL,
                body            TEXT,
                entity_key      TEXT,
                visibility      TEXT DEFAULT 'tenant',
                seen_by         JSONB DEFAULT '[]',
                created_at      TIMESTAMP DEFAULT NOW()
            )
        """)
        c.execute("""
            CREATE INDEX IF NOT EXISTS idx_tenant_events_tenant_date
            ON tenant_events (tenant_id, created_at DESC)
        """)
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"[TenantEvents] _ensure_table: {e}")


def publish_event(
    tenant_id: str,
    username: str,
    event_type: str,
    title: str,
    body: str = None,
    entity_key: str = None,
    visibility: str = "tenant",
) -> dict:
    """
    Publie un événement visible par les utilisateurs du tenant.
    L'auteur est automatiquement ajouté à seen_by (il n'a pas besoin de le voir).
    """
    if event_type not in VALID_EVENT_TYPES:
        event_type = "alert_shared"
    _ensure_table()
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            INSERT INTO tenant_events
                (tenant_id, source_username, event_type, title, body,
                 entity_key, visibility, seen_by)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb)
            RETURNING id
        """, (
            tenant_id, username, event_type,
            title[:200], (body or "")[:1000],
            entity_key, visibility,
            json.dumps([username]),   # auteur = déjà vu
        ))
        event_id = c.fetchone()[0]
        conn.commit()
        conn.close()
        logger.info(f"[TenantEvents] {username}@{tenant_id} → {event_type}: {title[:60]}")
        return {"status": "ok", "event_id": event_id}
    except Exception as e:
        logger.error(f"[TenantEvents] publish_event: {e}")
        return {"status": "error", "message": str(e)[:100]}


def get_unseen_events(username: str, tenant_id: str, limit: int = 10) -> list:
    """
    Retourne les événements du tenant non encore vus par cet utilisateur.
    Exclut les événements publiés par l'utilisateur lui-même.
    """
    _ensure_table()
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            SELECT id, source_username, event_type, title, body, entity_key, created_at
            FROM tenant_events
            WHERE tenant_id = %s
              AND source_username != %s
              AND visibility = 'tenant'
              AND NOT (seen_by @> %s::jsonb)
            ORDER BY created_at DESC
            LIMIT %s
        """, (tenant_id, username, json.dumps([username]), limit))
        rows = c.fetchall()
        conn.close()
        return [
            {
                "id": r[0],
                "source_username": r[1],
                "event_type": r[2],
                "title": r[3],
                "body": r[4] or "",
                "entity_key": r[5],
                "created_at": r[6],
            }
            for r in rows
        ]
    except Exception as e:
        logger.error(f"[TenantEvents] get_unseen_events: {e}")
        return []


def mark_seen(event_id: int, username: str) -> None:
    """Ajoute username dans seen_by de l'événement (idempotent)."""
    _ensure_table()
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            UPDATE tenant_events
            SET seen_by = CASE
                WHEN seen_by @> %s::jsonb THEN seen_by
                ELSE seen_by || %s::jsonb
            END
            WHERE id = %s
        """, (json.dumps([username]), json.dumps([username]), event_id))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"[TenantEvents] mark_seen: {e}")


def mark_seen_batch(event_ids: list, username: str) -> None:
    """Marque plusieurs événements comme vus en un seul appel."""
    if not event_ids:
        return
    _ensure_table()
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        placeholders = ",".join(["%s"] * len(event_ids))
        c.execute(f"""
            UPDATE tenant_events
            SET seen_by = CASE
                WHEN seen_by @> %s::jsonb THEN seen_by
                ELSE seen_by || %s::jsonb
            END
            WHERE id IN ({placeholders})
        """, [json.dumps([username]), json.dumps([username])] + event_ids)
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"[TenantEvents] mark_seen_batch: {e}")


def get_recent_events(tenant_id: str, limit: int = 20) -> list:
    """Retourne tous les événements récents du tenant (pour admin/debug)."""
    _ensure_table()
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            SELECT id, source_username, event_type, title, body,
                   entity_key, visibility, seen_by, created_at
            FROM tenant_events
            WHERE tenant_id = %s
            ORDER BY created_at DESC
            LIMIT %s
        """, (tenant_id, limit))
        rows = c.fetchall()
        conn.close()
        return [
            {
                "id": r[0],
                "source_username": r[1],
                "event_type": r[2],
                "title": r[3],
                "body": r[4] or "",
                "entity_key": r[5],
                "visibility": r[6],
                "seen_by": r[7] or [],
                "created_at": str(r[8]),
            }
            for r in rows
        ]
    except Exception as e:
        logger.error(f"[TenantEvents] get_recent_events: {e}")
        return []
