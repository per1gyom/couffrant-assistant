"""
Contrôle des actions directes — par tenant et par utilisateur.
Par défaut, les actions dangereuses sur les fichiers passent par la queue.
L'admin du tenant peut débloquer l'action directe globalement ou par user.
"""
import json
from app.database import get_pg_conn
from app.logging_config import get_logger

logger = get_logger("raya.direct_actions")


def can_do_direct_actions(username: str, tenant_id: str) -> bool:
    """
    Vérifie si l'utilisateur peut exécuter des actions directes sur les fichiers.
    Priorité : user override > tenant setting > default (False).
    """
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        # 1. Vérifier override utilisateur
        c.execute("SELECT settings FROM users WHERE username = %s", (username,))
        row = c.fetchone()
        if row and row[0]:
            user_settings = row[0] if isinstance(row[0], dict) else json.loads(row[0])
            user_override = user_settings.get("direct_actions")
            if user_override is not None:
                return bool(user_override)

        # 2. Vérifier setting tenant
        c.execute("SELECT settings FROM tenants WHERE id = %s", (tenant_id,))
        t_row = c.fetchone()
        if t_row and t_row[0]:
            tenant_settings = t_row[0] if isinstance(t_row[0], dict) else json.loads(t_row[0])
            return bool(tenant_settings.get("direct_actions", False))
        # 3. Défaut : pas d'actions directes
        return False
    except Exception as e:
        logger.warning("[DirectActions] check error: %s", e)
        return False
    finally:
        if conn:
            conn.close()


def set_tenant_direct_actions(tenant_id: str, enabled: bool) -> dict:
    """Active/désactive les actions directes pour tout le tenant."""
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        updates = json.dumps({"direct_actions": enabled})
        c.execute(
            "UPDATE tenants SET settings = COALESCE(settings, '{}')::jsonb || %s::jsonb WHERE id = %s",
            (updates, tenant_id)
        )
        conn.commit()
        state = "activées" if enabled else "désactivées"
        return {"status": "ok", "message": f"Actions directes {state} pour '{tenant_id}'."}
    except Exception as e:
        return {"status": "error", "message": str(e)[:200]}
    finally:
        if conn:
            conn.close()


def set_user_direct_actions(username: str, enabled) -> dict:
    """
    Active/désactive les actions directes pour un utilisateur.
    enabled=None → hérite du tenant.
    """
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        updates = json.dumps({"direct_actions": enabled})
        c.execute(
            "UPDATE users SET settings = COALESCE(settings, '{}')::jsonb || %s::jsonb WHERE username = %s",
            (updates, username)
        )
        conn.commit()
        if enabled is None:
            state = "hérité du tenant"
        elif enabled:
            state = "activées"
        else:
            state = "désactivées"
        return {"status": "ok", "message": f"Actions directes {state} pour '{username}'."}
    except Exception as e:
        return {"status": "error", "message": str(e)[:200]}
    finally:
        if conn:
            conn.close()
