"""
Gestion des outils par utilisateur.
"""
import json
from app.database import get_pg_conn

# Scopes
SCOPE_SUPER_ADMIN  = "super_admin"           # NEW : super admin Raya (hardcode via email)
SCOPE_ADMIN        = "admin"                 # admin Raya (collaborateur)
SCOPE_TENANT_ADMIN = "tenant_admin"
SCOPE_CS           = "couffrant_solar"  # legacy
SCOPE_USER         = "user"
DEFAULT_TENANT     = "couffrant_solar"
SUPER_ADMIN_SCOPES  = (SCOPE_SUPER_ADMIN,)
TENANT_ADMIN_SCOPES = (SCOPE_SUPER_ADMIN, SCOPE_ADMIN, SCOPE_TENANT_ADMIN)
USER_SCOPES         = (SCOPE_CS, SCOPE_USER)
ALL_SCOPES          = (SCOPE_SUPER_ADMIN, SCOPE_ADMIN, SCOPE_TENANT_ADMIN, SCOPE_CS, SCOPE_USER)

DEFAULT_TOOLS_ADMIN = [
    {"tool": "outlook", "access_level": "full", "config": {"mailboxes": [], "can_delete_mail": True}},
    {"tool": "odoo",    "access_level": "full", "config": {}},
    {"tool": "drive",   "access_level": "full", "config": {"can_delete": True}},
    {"tool": "gmail",   "access_level": "full", "config": {}},
]
DEFAULT_TOOLS_TENANT_ADMIN = [
    {"tool": "outlook", "access_level": "full", "config": {"mailboxes": [], "can_delete_mail": True}},
    {"tool": "odoo",    "access_level": "full", "config": {}},
    {"tool": "drive",   "access_level": "full", "config": {"can_delete": True}},
]
DEFAULT_TOOLS_USER = [
    {"tool": "outlook", "access_level": "write",     "config": {"mailboxes": [], "can_delete_mail": False}},
    {"tool": "odoo",    "access_level": "read_only", "config": {"shared_user": "sabrina"}},
    {"tool": "drive",   "access_level": "write",     "config": {"can_delete": False}},
]
DEFAULT_TOOLS_CS = DEFAULT_TOOLS_USER


def _tools_for_scope(scope: str) -> list:
    if scope == SCOPE_ADMIN: return DEFAULT_TOOLS_ADMIN
    if scope == SCOPE_TENANT_ADMIN: return DEFAULT_TOOLS_TENANT_ADMIN
    return DEFAULT_TOOLS_USER


def init_default_tools(username: str, scope: str):
    conn = None
    try:
        conn = get_pg_conn(); c = conn.cursor()
        for t in _tools_for_scope(scope):
            c.execute("""
                INSERT INTO user_tools (username, tool, access_level, enabled, config)
                VALUES (%s, %s, %s, true, %s) ON CONFLICT (username, tool) DO NOTHING
            """, (username, t["tool"], t["access_level"], json.dumps(t["config"])))
        conn.commit()
    except Exception as e:
        print(f"[Tools] Erreur {username}: {e}")
    finally:
        if conn: conn.close()


def get_user_tools(username: str, raw: bool = False):
    conn = None
    try:
        conn = get_pg_conn(); c = conn.cursor()
        c.execute("SELECT tool, access_level, enabled, config FROM user_tools WHERE username = %s ORDER BY tool",
                  (username,))
        rows = c.fetchall()
        if raw: return [{"tool": r[0], "access_level": r[1], "enabled": r[2], "config": r[3] or {}} for r in rows]
        return {r[0]: {"access_level": r[1], "enabled": r[2], "config": r[3] or {}} for r in rows}
    except Exception:
        return [] if raw else {}
    finally:
        if conn: conn.close()


def get_tool_config(username: str, tool: str) -> dict:
    conn = None
    try:
        conn = get_pg_conn(); c = conn.cursor()
        c.execute("SELECT access_level, enabled, config FROM user_tools WHERE username=%s AND tool=%s",
                  (username, tool))
        row = c.fetchone()
        if not row: return {"access_level": "none", "enabled": False, "config": {}}
        return {"access_level": row[0], "enabled": row[1], "config": row[2] or {}}
    except Exception:
        return {"access_level": "none", "enabled": False, "config": {}}
    finally:
        if conn: conn.close()


def set_user_tool(username: str, tool: str, access_level: str = "read_only",
                  enabled: bool = True, config: dict = None) -> dict:
    conn = None
    try:
        conn = get_pg_conn(); c = conn.cursor()
        c.execute("""
            INSERT INTO user_tools (username, tool, access_level, enabled, config, updated_at)
            VALUES (%s, %s, %s, %s, %s, NOW())
            ON CONFLICT (username, tool) DO UPDATE SET
                access_level=EXCLUDED.access_level, enabled=EXCLUDED.enabled,
                config=EXCLUDED.config, updated_at=NOW()
        """, (username, tool, access_level, enabled, json.dumps(config or {})))
        conn.commit()
        return {"status": "ok", "message": f"Outil '{tool}' configuré ({access_level})."}
    except Exception as e:
        return {"status": "error", "message": str(e)[:100]}
    finally:
        if conn: conn.close()


def remove_user_tool(username: str, tool: str) -> dict:
    conn = None
    try:
        conn = get_pg_conn(); c = conn.cursor()
        c.execute("DELETE FROM user_tools WHERE username=%s AND tool=%s", (username, tool))
        if c.rowcount == 0: return {"status": "error", "message": "Outil introuvable."}
        conn.commit()
        return {"status": "ok"}
    except Exception as e:
        return {"status": "error", "message": str(e)[:100]}
    finally:
        if conn: conn.close()
