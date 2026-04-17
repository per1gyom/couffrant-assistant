"""
Endpoints super_admin — gestion globale (utilisateurs, tenants, outils, mémoire).
  POST   /admin/unlock-user/{target}
  GET    /admin/costs
  GET    /admin/tenants/{tenant_id}/sharepoint
  PUT    /admin/tenants/{tenant_id}/sharepoint
  GET    /admin/tenants-overview
  GET    /admin/tenants
  POST   /admin/tenants
  DELETE /admin/tenants/{tenant_id}
  PUT    /admin/tenants/{tenant_id}
  GET    /admin/panel
  GET    /admin/users
  POST   /admin/create-user
  PUT    /admin/update-user/{target}
  DELETE /admin/delete-user/{target}
  POST   /admin/reset-password/{target}
  POST   /admin/users/{username}/reset-password
  GET    /admin/rules
  GET    /admin/insights
  GET    /admin/memory-status
  GET    /admin/user-tools/{target}
  POST   /admin/user-tools/{target}/{tool}
  DELETE /admin/user-tools/{target}/{tool}
  GET    /admin/diag
  GET    /init-db
  GET    /test-elevenlabs
"""
import os
import requests as http_requests
from fastapi import APIRouter, Request, Body, Depends, HTTPException
from fastapi.responses import RedirectResponse, HTMLResponse

from app.database import get_pg_conn, init_postgres
from app.app_security import (
    create_user, delete_user, update_user, list_users, init_default_user,
    get_user_tools, set_user_tool, remove_user_tool,
    generate_reset_token, hash_password,
    SCOPE_USER, DEFAULT_TENANT,
)
from app.security_auth import unlock_account
from app.routes.deps import require_admin, require_tenant_admin, assert_same_tenant
from app.admin_audit import log_admin_action
from app.dashboard_service import get_costs_dashboard

router = APIRouter()


# ─── DÉBLOCAGE COMPTE ───


@router.get("/admin/users")
def admin_list_users(request: Request, _: dict = Depends(require_admin)):
    return list_users()


@router.post("/admin/create-user")
def admin_create_user(
    request: Request,
    payload: dict = Body(...),
    admin: dict = Depends(require_admin),
):
    new_username = payload.get("username", "").strip()
    result = create_user(
        new_username,
        payload.get("password", ""),
        payload.get("scope", SCOPE_USER),
        payload.get("tools"),
        tenant_id=payload.get("tenant_id", DEFAULT_TENANT),
        email=payload.get("email"),
    )
    log_admin_action(admin["username"], "create_user", new_username)
    return result


@router.put("/admin/update-user/{target}")
def admin_update_user(
    request: Request,
    target: str,
    payload: dict = Body(...),
    admin: dict = Depends(require_admin),
):
    new_scope = payload.get("scope", "")
    result = update_user(target, email=payload.get("email"), scope=new_scope)
    log_admin_action(admin["username"], "update_scope", target, new_scope)
    return result


@router.delete("/admin/delete-user/{target}")
def admin_delete_user(
    request: Request,
    target: str,
    user: dict = Depends(require_admin),
):
    result = delete_user(target, user["username"])
    log_admin_action(user["username"], "delete_user", target)
    return result


@router.post("/admin/reset-password/{target}")
def admin_reset_password(
    request: Request,
    target: str,
    _: dict = Depends(require_tenant_admin),
):
    assert_same_tenant(request, target)
    return generate_reset_token(target)


@router.post("/admin/users/{username}/reset-password")
def admin_users_reset_password(
    request: Request,
    username: str,
    admin: dict = Depends(require_admin),
):
    import secrets
    import string
    alphabet = string.ascii_letters + string.digits
    temp_password = "".join(secrets.choice(alphabet) for _ in range(12))
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("SELECT username FROM users WHERE username = %s", (username,))
        if not c.fetchone():
            raise HTTPException(status_code=404, detail=f"Utilisateur '{username}' introuvable")
        c.execute(
            "UPDATE users SET password_hash = %s, must_reset_password = true WHERE username = %s",
            (hash_password(temp_password), username),
        )
        conn.commit()
        log_admin_action(admin["username"], "reset_password", username)
        return {
            "status": "ok",
            "username": username,
            "temp_password": temp_password,
            "message": "Mot de passe temporaire genere. L'utilisateur devra en choisir un nouveau a la connexion.",
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn: conn.close()


# ─── MÉMOIRE & RÈGLES ───

@router.get("/admin/rules")
def admin_rules(request: Request, user: str = "", _: dict = Depends(require_admin)):
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        if user:
            c.execute(
                "SELECT id,username,category,rule,confidence,reinforcements,active "
                "FROM aria_rules WHERE username=%s ORDER BY active DESC,confidence DESC",
                (user,)
            )
        else:
            c.execute(
                "SELECT id,username,category,rule,confidence,reinforcements,active "
                "FROM aria_rules ORDER BY username,active DESC,confidence DESC"
            )
        cols = [d[0] for d in c.description]
        return [dict(zip(cols, row)) for row in c.fetchall()]
    finally:
        if conn: conn.close()


@router.get("/admin/insights")
def admin_insights(request: Request, user: str = "", _: dict = Depends(require_admin)):
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        if user:
            c.execute(
                "SELECT id,username,topic,insight,reinforcements "
                "FROM aria_insights WHERE username=%s ORDER BY reinforcements DESC",
                (user,)
            )
        else:
            c.execute(
                "SELECT id,username,topic,insight,reinforcements "
                "FROM aria_insights ORDER BY username,reinforcements DESC"
            )
        cols = [d[0] for d in c.description]
        return [dict(zip(cols, row)) for row in c.fetchall()]
    finally:
        if conn: conn.close()


@router.get("/admin/memory-status")
def admin_memory_status(request: Request, _: dict = Depends(require_admin)):
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("SELECT username,email,scope,tenant_id FROM users")
        meta = {r[0]: {"email": r[1], "scope": r[2], "tenant_id": r[3]} for r in c.fetchall()}
        agg = {}
        for table, key in [
            ("aria_memory", "conv"), ("aria_rules", "rules"),
            ("aria_insights", "insights"), ("mail_memory", "mails"),
        ]:
            c.execute(f"SELECT username, COUNT(*) FROM {table} GROUP BY username")
            for u, cnt in c.fetchall():
                agg.setdefault(u, {})[key] = cnt
        return [
            {
                "username": u,
                **meta.get(u, {}),
                **agg.get(u, {"conv": 0, "rules": 0, "insights": 0, "mails": 0}),
            }
            for u in sorted(set(list(meta) + list(agg)))
        ]
    finally:
        if conn: conn.close()


# ─── OUTILS ───

@router.get("/admin/user-tools/{target}")
def admin_get_tools(
    request: Request,
    target: str,
    _: dict = Depends(require_admin),
):
    return get_user_tools(target, raw=True)


@router.post("/admin/user-tools/{target}/{tool}")
def admin_set_tool(
    request: Request,
    target: str,
    tool: str,
    payload: dict = Body(...),
    admin: dict = Depends(require_admin),
):
    result = set_user_tool(
        target, tool,
        payload.get("access_level", "read_only"),
        payload.get("enabled", True),
        payload.get("config", {}),
    )
    log_admin_action(admin["username"], "update_tools", target, tool)
    return result


@router.delete("/admin/user-tools/{target}/{tool}")
def admin_remove_tool(
    request: Request,
    target: str,
    tool: str,
    admin: dict = Depends(require_admin),
):
    result = remove_user_tool(target, tool)
    log_admin_action(admin["username"], "update_tools", target, f"remove:{tool}")
    return result


# ─── MAINTENANCE ───

@router.get("/init-db")
def init_db_now(request: Request, _: dict = Depends(require_admin)):
    init_postgres()
    try:
        init_default_user()
    except Exception:
        pass
    return {"status": "tables créées"}


@router.get("/test-elevenlabs")
def test_elevenlabs(request: Request, _: dict = Depends(require_admin)):
    api_key = os.environ.get("ELEVENLABS_API_KEY", "")
    voice_id = os.environ.get("ELEVENLABS_VOICE_ID", "")
    resp = http_requests.post(
        f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
        headers={"xi-api-key": api_key, "Content-Type": "application/json"},
        json={"text": "Bonjour.", "model_id": "eleven_flash_v2_5",
              "voice_settings": {"stability": 0.5, "similarity_boost": 0.8}},
        timeout=30,
    )
    return {"status_code": resp.status_code, "api_key_length": len(api_key), "voice_id": voice_id}



# ─── SUPPRESSION COMPTE — VALIDATION ADMIN ───

@router.post("/admin/users/{username}/confirm-delete")
def admin_confirm_delete(
    request: Request,
    username: str,
    admin: dict = Depends(require_tenant_admin),
):
    """
    L'admin confirme la suppression d'un compte dont deletion_requested_at est renseigné.
    Exécute la vraie suppression RGPD.
    """
    from app.database import get_pg_conn
    from app.security_users import delete_user as _delete_user
    from app.admin_audit import log_admin_action

    # Vérifier qu'une demande existe bien
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute(
            "SELECT username, deletion_requested_at FROM users WHERE username = %s",
            (username,)
        )
        row = c.fetchone()
        if not row:
            return {"status": "error", "message": "Utilisateur introuvable."}
        if not row[1]:
            return {"status": "error", "message": "Aucune demande de suppression en cours pour cet utilisateur."}
    except Exception as e:
        return {"status": "error", "message": str(e)[:100]}
    finally:
        if conn:
            conn.close()

    # Exécuter la suppression RGPD
    result = _delete_user(username, requesting_user=admin["username"])
    if result.get("status") == "ok":
        log_admin_action(admin["username"], "confirm_delete_account", username)
    return result


@router.post("/admin/users/{username}/reject-delete")
def admin_reject_delete(
    request: Request,
    username: str,
    admin: dict = Depends(require_tenant_admin),
):
    """
    L'admin refuse la demande de suppression. Remet deletion_requested_at à NULL.
    """
    from app.database import get_pg_conn
    from app.admin_audit import log_admin_action
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("UPDATE users SET deletion_requested_at = NULL WHERE username = %s", (username,))
        conn.commit()
        log_admin_action(admin["username"], "reject_delete_account", username)
        return {"status": "ok", "message": f"Demande de suppression de '{username}' rejetée."}
    except Exception as e:
        return {"status": "error", "message": str(e)[:100]}
    finally:
        if conn:
            conn.close()



@router.api_route("/admin/reset-history/{target}", methods=["GET", "POST"])
def admin_reset_history(
    request: Request,
    target: str,
    _: dict = Depends(require_admin),
):
    """Archive l'historique de conversation d'un utilisateur (reset sans suppression)."""
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("UPDATE aria_memory SET archived = true WHERE username = %s AND archived = false", (target,))
        count = c.rowcount
        conn.commit()
        return {"status": "ok", "archived": count, "message": f"{count} message(s) archivé(s) pour {target}"}
    except Exception as e:
        return {"status": "error", "message": str(e)[:200]}
    finally:
        if conn: conn.close()
