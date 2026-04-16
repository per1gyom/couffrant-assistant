"""
Raccourcis rapides — SHORTCUTS v2.
Boutons sidebar avec titre, prompt personnalise et couleur.
Stockage DB par user (remplace localStorage).
"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import Optional
from app.database import get_pg_conn
from app.routes.deps import require_user
from app.logging_config import get_logger

logger = get_logger("raya.shortcuts")
router = APIRouter(tags=["shortcuts"])

DEFAULT_SHORTCUTS = [
    {"label": "Mails urgents",  "prompt": "Quels sont mes mails urgents ?",                    "color": "#4f46e5", "position": 0},
    {"label": "Planning",       "prompt": "Quel est mon planning aujourd'hui ?",               "color": "#059669", "position": 1},
    {"label": "Chantiers",      "prompt": "Donne-moi un point sur mes chantiers en cours",     "color": "#d97706", "position": 2},
    {"label": "Point semaine",  "prompt": "Fais-moi un point de la semaine",                   "color": "#dc2626", "position": 3},
    {"label": "Relances",       "prompt": "Quelles sont mes relances en attente ?",             "color": "#7c3aed", "position": 4},
]


class ShortcutCreate(BaseModel):
    label: str
    prompt: str
    color: Optional[str] = "#059669"


class ShortcutUpdate(BaseModel):
    label: Optional[str] = None
    prompt: Optional[str] = None
    color: Optional[str] = None
    position: Optional[int] = None


def _seed_defaults(username: str, tenant_id: str, conn):
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM user_shortcuts WHERE username = %s", (username,))
    if c.fetchone()[0] == 0:
        for s in DEFAULT_SHORTCUTS:
            c.execute(
                "INSERT INTO user_shortcuts (username, tenant_id, label, prompt, color, position) "
                "VALUES (%s, %s, %s, %s, %s, %s)",
                (username, tenant_id, s["label"], s["prompt"], s["color"], s["position"])
            )
        conn.commit()


@router.get("/shortcuts")
def list_shortcuts(user: dict = Depends(require_user)):
    username = user["username"]
    tenant_id = user["tenant_id"]
    conn = None
    try:
        conn = get_pg_conn()
        _seed_defaults(username, tenant_id, conn)
        c = conn.cursor()
        c.execute("""
            SELECT id, label, prompt, color, position
            FROM user_shortcuts WHERE username = %s
            ORDER BY position, id
        """, (username,))
        return [{"id": r[0], "label": r[1], "prompt": r[2], "color": r[3], "position": r[4]}
                for r in c.fetchall()]
    except Exception as e:
        logger.warning("[Shortcuts] list error: %s", e)
        return []
    finally:
        if conn: conn.close()


@router.post("/shortcuts")
def create_shortcut(payload: ShortcutCreate, user: dict = Depends(require_user)):
    username = user["username"]
    tenant_id = user["tenant_id"]
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("SELECT COALESCE(MAX(position)+1, 0) FROM user_shortcuts WHERE username = %s", (username,))
        pos = c.fetchone()[0]
        c.execute(
            "INSERT INTO user_shortcuts (username, tenant_id, label, prompt, color, position) "
            "VALUES (%s, %s, %s, %s, %s, %s) RETURNING id, label, prompt, color, position",
            (username, tenant_id, payload.label.strip()[:100],
             payload.prompt.strip()[:2000], payload.color or "#059669", pos)
        )
        r = c.fetchone()
        conn.commit()
        return {"id": r[0], "label": r[1], "prompt": r[2], "color": r[3], "position": r[4]}
    except Exception as e:
        if conn: conn.rollback()
        return {"error": str(e)[:200]}
    finally:
        if conn: conn.close()


@router.patch("/shortcuts/{shortcut_id}")
def update_shortcut(shortcut_id: int, payload: ShortcutUpdate, user: dict = Depends(require_user)):
    username = user["username"]
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("SELECT id FROM user_shortcuts WHERE id = %s AND username = %s", (shortcut_id, username))
        if not c.fetchone():
            return {"error": "Raccourci introuvable"}
        updates, params = [], []
        if payload.label is not None:
            updates.append("label = %s"); params.append(payload.label.strip()[:100])
        if payload.prompt is not None:
            updates.append("prompt = %s"); params.append(payload.prompt.strip()[:2000])
        if payload.color is not None:
            updates.append("color = %s"); params.append(payload.color[:20])
        if payload.position is not None:
            updates.append("position = %s"); params.append(payload.position)
        if not updates:
            return {"error": "Rien a modifier"}
        updates.append("updated_at = NOW()")
        params.extend([shortcut_id, username])
        c.execute(
            f"UPDATE user_shortcuts SET {', '.join(updates)} "
            "WHERE id = %s AND username = %s RETURNING id, label, prompt, color, position",
            params
        )
        r = c.fetchone()
        conn.commit()
        return {"id": r[0], "label": r[1], "prompt": r[2], "color": r[3], "position": r[4]}
    except Exception as e:
        if conn: conn.rollback()
        return {"error": str(e)[:200]}
    finally:
        if conn: conn.close()


@router.delete("/shortcuts/{shortcut_id}")
def delete_shortcut(shortcut_id: int, user: dict = Depends(require_user)):
    username = user["username"]
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("DELETE FROM user_shortcuts WHERE id = %s AND username = %s", (shortcut_id, username))
        if c.rowcount == 0:
            return {"ok": False, "error": "Raccourci introuvable"}
        conn.commit()
        return {"ok": True}
    except Exception as e:
        if conn: conn.rollback()
        return {"ok": False, "error": str(e)[:200]}
    finally:
        if conn: conn.close()
