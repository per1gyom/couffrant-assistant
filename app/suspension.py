"""
Suspension de comptes — utilisateurs et tenants.
Super admin peut suspendre un utilisateur ou un tenant entier.
"""
from app.database import get_pg_conn
from app.logging_config import get_logger

logger = get_logger("raya.suspension")


def check_suspension(username: str, tenant_id: str) -> tuple:
    """
    Vérifie si l'utilisateur ou son tenant est suspendu.
    Retourne (True, message) si suspendu, (False, "") sinon.
    """
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        # Vérifier suspension utilisateur
        c.execute(
            "SELECT suspended, suspended_reason FROM users WHERE username = %s",
            (username,)
        )
        row = c.fetchone()
        if row and row[0]:
            reason = row[1] or ""
            return (True,
                "Votre compte est suspendu. "
                "Contactez l'administrateur de votre organisation."
                + (f" Motif : {reason}" if reason else ""))

        # Vérifier suspension tenant
        c.execute(
            "SELECT settings FROM tenants WHERE id = %s",
            (tenant_id,)
        )
        t_row = c.fetchone()
        if t_row and t_row[0]:
            settings = t_row[0] if isinstance(t_row[0], dict) else {}
            if settings.get("suspended"):
                reason = settings.get("suspended_reason", "")
                return (True,
                    "Votre organisation est suspendue. "
                    "Contactez contact@raya-ia.fr pour plus d'informations."
                    + (f" Motif : {reason}" if reason else ""))
        return (False, "")
    except Exception as e:
        logger.warning("[Suspension] Erreur check: %s", e)
        return (False, "")
    finally:
        if conn:
            conn.close()


def suspend_user(username: str, reason: str = "") -> dict:
    """Suspend un utilisateur."""
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute(
            "UPDATE users SET suspended = true, suspended_reason = %s WHERE username = %s",
            (reason or None, username)
        )
        if c.rowcount == 0:
            return {"status": "error", "message": "Utilisateur introuvable."}
        conn.commit()
        logger.warning("[Suspension] User %s suspendu. Raison: %s", username, reason)
        return {"status": "ok", "message": f"Compte '{username}' suspendu."}
    except Exception as e:
        return {"status": "error", "message": str(e)[:200]}
    finally:
        if conn:
            conn.close()


def unsuspend_user(username: str) -> dict:
    """Réactive un utilisateur suspendu."""
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute(
            "UPDATE users SET suspended = false, suspended_reason = NULL WHERE username = %s",
            (username,)
        )
        conn.commit()
        logger.info("[Suspension] User %s réactivé", username)
        return {"status": "ok", "message": f"Compte '{username}' réactivé."}
    except Exception as e:
        return {"status": "error", "message": str(e)[:200]}
    finally:
        if conn:
            conn.close()


def suspend_tenant(tenant_id: str, reason: str = "") -> dict:
    """Suspend un tenant entier."""
    import json
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        updates = json.dumps({"suspended": True, "suspended_reason": reason or ""})
        c.execute(
            "UPDATE tenants SET settings = COALESCE(settings, '{}')::jsonb || %s::jsonb WHERE id = %s",
            (updates, tenant_id)
        )
        if c.rowcount == 0:
            return {"status": "error", "message": "Tenant introuvable."}
        conn.commit()
        logger.warning("[Suspension] Tenant %s suspendu. Raison: %s", tenant_id, reason)
        return {"status": "ok", "message": f"Société '{tenant_id}' suspendue."}
    except Exception as e:
        return {"status": "error", "message": str(e)[:200]}
    finally:
        if conn:
            conn.close()


def unsuspend_tenant(tenant_id: str) -> dict:
    """Réactive un tenant suspendu."""
    import json
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        updates = json.dumps({"suspended": False, "suspended_reason": ""})
        c.execute(
            "UPDATE tenants SET settings = COALESCE(settings, '{}')::jsonb || %s::jsonb WHERE id = %s",
            (updates, tenant_id)
        )
        conn.commit()
        logger.info("[Suspension] Tenant %s réactivé", tenant_id)
        return {"status": "ok", "message": f"Société '{tenant_id}' réactivée."}
    except Exception as e:
        return {"status": "error", "message": str(e)[:200]}
    finally:
        if conn:
            conn.close()
