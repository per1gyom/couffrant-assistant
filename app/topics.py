"""
Sujets utilisateur — TOPICS.
Carnet de signets pour organiser les echanges avec Raya.
Specs : docs/raya_flutter_ux_specs.md
"""
import json
from datetime import datetime
from fastapi import APIRouter, Request, Depends
from pydantic import BaseModel
from typing import Optional
from app.database import get_pg_conn
from app.routes.deps import require_user
from app.logging_config import get_logger

logger = get_logger("raya.topics")
router = APIRouter(tags=["topics"])


class TopicCreate(BaseModel):
    title: str


class TopicUpdate(BaseModel):
    title: Optional[str] = None
    status: Optional[str] = None


class SectionTitleUpdate(BaseModel):
    section_title: str


@router.get("/topics")
def list_topics(user: dict = Depends(require_user)):
    username = user["username"]
    tenant_id = user["tenant_id"]
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        # Section title from users.settings
        c.execute(
            "SELECT settings FROM users WHERE username = %s "
            "AND (tenant_id = %s OR tenant_id IS NULL)",
            (username, tenant_id)
        )
        row = c.fetchone()
        settings = {}
        if row and row[0]:
            settings = row[0] if isinstance(row[0], dict) else json.loads(row[0])
        section_title = settings.get("topics_section_title", "Mes sujets")
        # Topics
        c.execute("""
            SELECT id, title, status, created_at, updated_at
            FROM user_topics
            WHERE username = %s
              AND (tenant_id = %s OR tenant_id IS NULL)
            ORDER BY
                CASE status WHEN 'active' THEN 0 WHEN 'paused' THEN 1 ELSE 2 END,
                updated_at DESC
        """, (username, tenant_id))
        topics = []
        for r in c.fetchall():
            topics.append({
                "id": r[0], "title": r[1], "status": r[2],
                "created_at": r[3].isoformat() if r[3] else None,
                "updated_at": r[4].isoformat() if r[4] else None,
            })
        return {"section_title": section_title, "topics": topics}
    except Exception as e:
        logger.warning("[Topics] list error: %s", e)
        return {"section_title": "Mes sujets", "topics": []}
    finally:
        if conn:
            conn.close()


@router.post("/topics")
def create_topic(payload: TopicCreate, user: dict = Depends(require_user)):
    username = user["username"]
    tenant_id = user["tenant_id"]
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            INSERT INTO user_topics (username, tenant_id, title)
            VALUES (%s, %s, %s)
            RETURNING id, title, status, created_at
        """, (username, tenant_id, payload.title.strip()[:255]))
        r = c.fetchone()
        conn.commit()
        logger.info("[Topics] %s created topic '%s'", username, payload.title[:50])
        return {
            "id": r[0], "title": r[1], "status": r[2],
            "created_at": r[3].isoformat() if r[3] else None,
        }
    except Exception as e:
        if conn:
            conn.rollback()
        return {"error": str(e)[:200]}
    finally:
        if conn:
            conn.close()


@router.patch("/topics/{topic_id}")
def update_topic(topic_id: int, payload: TopicUpdate, user: dict = Depends(require_user)):
    username = user["username"]
    tenant_id = user["tenant_id"]
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        # Verify ownership
        c.execute(
            "SELECT id FROM user_topics WHERE id = %s AND username = %s "
            "AND (tenant_id = %s OR tenant_id IS NULL)",
            (topic_id, username, tenant_id)
        )
        if not c.fetchone():
            return {"error": "Sujet introuvable"}
        updates = []
        params = []
        if payload.title is not None:
            updates.append("title = %s")
            params.append(payload.title.strip()[:255])
        if payload.status is not None:
            if payload.status not in ("active", "paused", "archived"):
                return {"error": "Statut invalide"}
            updates.append("status = %s")
            params.append(payload.status)
        if not updates:
            return {"error": "Rien a modifier"}
        updates.append("updated_at = NOW()")
        params.extend([topic_id, username, tenant_id])
        c.execute(
            f"UPDATE user_topics SET {', '.join(updates)} WHERE id = %s AND username = %s "
            "AND (tenant_id = %s OR tenant_id IS NULL) "
            "RETURNING id, title, status, updated_at",
            params
        )
        r = c.fetchone()
        conn.commit()
        return {
            "id": r[0], "title": r[1], "status": r[2],
            "updated_at": r[3].isoformat() if r[3] else None,
        }
    except Exception as e:
        if conn:
            conn.rollback()
        return {"error": str(e)[:200]}
    finally:
        if conn:
            conn.close()


@router.delete("/topics/{topic_id}")
def delete_topic(topic_id: int, user: dict = Depends(require_user)):
    username = user["username"]
    tenant_id = user["tenant_id"]
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute(
            "DELETE FROM user_topics WHERE id = %s AND username = %s "
            "AND (tenant_id = %s OR tenant_id IS NULL)",
            (topic_id, username, tenant_id)
        )
        if c.rowcount == 0:
            return {"ok": False, "error": "Sujet introuvable"}
        conn.commit()
        return {"ok": True}
    except Exception as e:
        if conn:
            conn.rollback()
        return {"ok": False, "error": str(e)[:200]}
    finally:
        if conn:
            conn.close()


@router.patch("/topics/settings")
def update_section_title(payload: SectionTitleUpdate, user: dict = Depends(require_user)):
    username = user["username"]
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        new_settings = json.dumps({"topics_section_title": payload.section_title.strip()[:100]})
        c.execute(
            "UPDATE users SET settings = COALESCE(settings, '{}')::jsonb || %s::jsonb WHERE username = %s",
            (new_settings, username)
        )
        conn.commit()
        return {"section_title": payload.section_title.strip()[:100]}
    except Exception as e:
        if conn:
            conn.rollback()
        return {"error": str(e)[:200]}
    finally:
        if conn:
            conn.close()
