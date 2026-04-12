"""
Endpoints tenant_admin — gestion des utilisateurs du tenant.
  GET    /tenant/users
  POST   /tenant/create-user
  PUT    /tenant/update-user/{target}
  DELETE /tenant/delete-user/{target}
  POST   /tenant/reset-password/{target}
  GET    /tenant/user-tools/{target}
  GET    /tenant/rules
"""
from fastapi import APIRouter, Request, Body, Depends

from app.database import get_pg_conn
from app.app_security import (
    create_user, delete_user, update_user,
    get_users_in_tenant, generate_reset_token, get_user_tools,
    SCOPE_USER, SCOPE_CS, SCOPE_TENANT_ADMIN, DEFAULT_TENANT,
)
from app.routes.deps import require_tenant_admin, get_session_tenant_id, assert_same_tenant
from app.admin_audit import log_admin_action

router = APIRouter()


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
