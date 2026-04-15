"""
Endpoints admin gestion utilisateurs/regles/insights.
Extrait de admin.py -- SPLIT-R2.
"""
import os
import requests as http_requests
from fastapi import APIRouter, Request, Body, Depends, HTTPException
from fastapi.responses import JSONResponse
from app.routes.deps import require_admin, require_tenant_admin, get_session_tenant_id, assert_same_tenant
from app.security_tools import ALL_SCOPES, SCOPE_USER, SCOPE_CS, SCOPE_ADMIN, SCOPE_TENANT_ADMIN, DEFAULT_TENANT
from app.app_security import (
    create_user, delete_user, update_user, list_users,
    get_user_tools, set_user_tool, remove_user_tool,
    get_users_in_tenant, get_tenant_id, generate_reset_token,
    hash_password, init_default_user,
)
from app.database import get_pg_conn, init_postgres
from app.admin_audit import log_admin_action
from app.logging_config import get_logger
logger = get_logger("raya.admin")
router = APIRouter(tags=["admin"])


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
            "message": f"Mot de passe temporaire genere. L'utilisateur devra en choisir un nouveau a la connexion.",
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn:
            conn.close()


# ─── TENANT ADMIN ───



@router.get("/tenant/users")
def tenant_list_users(request: Request, _: dict = Depends(require_tenant_admin)):
    return get_users_in_tenant(get_session_tenant_id(request))




@router.post("/tenant/create-user")
def tenant_create_user(
    request: Request,
    payload: dict = Body(...),
    user: dict = Depends(require_tenant_admin),
):
    tenant_id = user["tenant_id"]
    scope = payload.get("scope", SCOPE_USER)
    if user["scope"] == SCOPE_TENANT_ADMIN and scope not in (SCOPE_USER, SCOPE_CS):
        scope = SCOPE_USER
    new_username = payload.get("username", "").strip()
    result = create_user(
        new_username,
        payload.get("password", ""),
        scope,
        payload.get("tools"),
        tenant_id=tenant_id,
        email=payload.get("email"),
    )
    log_admin_action(user["username"], "create_user", new_username)
    return result




@router.put("/tenant/update-user/{target}")
def tenant_update_user(
    request: Request,
    target: str,
    payload: dict = Body(...),
    admin: dict = Depends(require_tenant_admin),
):
    assert_same_tenant(request, target)
    new_scope = payload.get("scope", "")
    result = update_user(target, email=payload.get("email"), scope=new_scope)
    log_admin_action(admin["username"], "update_scope", target, new_scope)
    return result




@router.delete("/tenant/delete-user/{target}")
def tenant_delete_user(
    request: Request,
    target: str,
    user: dict = Depends(require_tenant_admin),
):
    assert_same_tenant(request, target)
    result = delete_user(target, user["username"], user["tenant_id"])
    log_admin_action(user["username"], "delete_user", target)
    return result




@router.post("/tenant/reset-password/{target}")
def tenant_reset_password(
    request: Request,
    target: str,
    _: dict = Depends(require_tenant_admin),
):
    assert_same_tenant(request, target)
    return generate_reset_token(target)




@router.get("/tenant/user-tools/{target}")
def tenant_get_tools(
    request: Request,
    target: str,
    _: dict = Depends(require_tenant_admin),
):
    assert_same_tenant(request, target)
    return get_user_tools(target, raw=True)




@router.get("/tenant/rules")
def tenant_rules(request: Request, user: dict = Depends(require_tenant_admin)):
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            SELECT ar.id, ar.username, ar.category, ar.rule,
                   ar.confidence, ar.reinforcements, ar.active
            FROM aria_rules ar
            JOIN users u ON u.username = ar.username
            WHERE u.tenant_id = %s
            ORDER BY ar.username, ar.active DESC, ar.confidence DESC
        """, (user["tenant_id"],))
        cols = [d[0] for d in c.description]
        return [dict(zip(cols, row)) for row in c.fetchall()]
    finally:
        if conn: conn.close()


# ─── ADMIN GLOBAL ───



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

