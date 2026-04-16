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
    set_user_tool, remove_user_tool,
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


@router.post("/tenant/user-tools/{target}/{tool}")
def tenant_set_tool(
    request: Request,
    target: str,
    tool: str,
    payload: dict = Body(...),
    admin: dict = Depends(require_tenant_admin),
):
    assert_same_tenant(request, target)
    result = set_user_tool(
        target, tool,
        payload.get("access_level", "read_only"),
        payload.get("enabled", True),
        payload.get("config", {}),
    )
    log_admin_action(admin["username"], "update_tools", target, tool)
    return result


@router.delete("/tenant/user-tools/{target}/{tool}")
def tenant_remove_tool(
    request: Request,
    target: str,
    tool: str,
    admin: dict = Depends(require_tenant_admin),
):
    assert_same_tenant(request, target)
    result = remove_user_tool(target, tool)
    log_admin_action(admin["username"], "remove_tool", target, tool)
    return result


# ─── CONNEXIONS V2 ───

@router.get("/tenant/connections")
def tenant_list_connections(request: Request, user: dict = Depends(require_tenant_admin)):
    from app.connections import list_connections
    return list_connections(user["tenant_id"])

@router.post("/tenant/connections")
def tenant_create_connection(request: Request, payload: dict = Body(...), user: dict = Depends(require_tenant_admin)):
    from app.connections import create_connection
    return create_connection(user["tenant_id"], payload.get("tool_type", ""), payload.get("label", ""),
        auth_type=payload.get("auth_type", "manual"), config=payload.get("config", {}),
        created_by=user["username"], status=payload.get("status", "not_configured"))

@router.put("/tenant/connections/{connection_id}")
def tenant_update_connection(request: Request, connection_id: int, payload: dict = Body(...), _: dict = Depends(require_tenant_admin)):
    from app.connections import update_connection
    return update_connection(connection_id, **payload)

@router.delete("/tenant/connections/{connection_id}")
def tenant_delete_connection(request: Request, connection_id: int, _: dict = Depends(require_tenant_admin)):
    from app.connections import delete_connection
    return delete_connection(connection_id)

@router.post("/tenant/connections/{connection_id}/assign")
def tenant_assign_connection(request: Request, connection_id: int, payload: dict = Body(...), _: dict = Depends(require_tenant_admin)):
    from app.connections import assign_connection
    return assign_connection(connection_id, payload.get("username", ""), payload.get("access_level", "read_only"), payload.get("enabled", True))

@router.delete("/tenant/connections/{connection_id}/assign/{username}")
def tenant_unassign_connection(request: Request, connection_id: int, username: str, _: dict = Depends(require_tenant_admin)):
    from app.connections import unassign_connection
    return unassign_connection(connection_id, username)


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


# ─── CONNEXIONS V2 — lecture seule pour tenant admin ───

@router.get("/tenant/connections")
def tenant_list_connections(request: Request, user: dict = Depends(require_tenant_admin)):
    """Retourne les connexions du tenant (sans credentials)."""
    from app.connections import list_connections
    return list_connections(user["tenant_id"])

@router.post("/tenant/connections")
def tenant_create_connection(request: Request, payload: dict = Body(...), user: dict = Depends(require_tenant_admin)):
    from app.connections import create_connection
    return create_connection(user["tenant_id"], payload.get("tool_type",""), payload.get("label",""),
        auth_type=payload.get("auth_type","manual"), config=payload.get("config",{}),
        credentials={}, created_by=user["username"], status="not_configured")

@router.put("/tenant/connections/{connection_id}")
def tenant_update_connection(request: Request, connection_id: int, payload: dict = Body(...), user: dict = Depends(require_tenant_admin)):
    from app.connections import update_connection
    return update_connection(connection_id, **{k:v for k,v in payload.items() if k != "credentials"})

@router.delete("/tenant/connections/{connection_id}")
def tenant_delete_connection(request: Request, connection_id: int, user: dict = Depends(require_tenant_admin)):
    from app.connections import delete_connection
    return delete_connection(connection_id)

@router.post("/tenant/connections/{connection_id}/assign")
def tenant_assign_connection(request: Request, connection_id: int, payload: dict = Body(...), user: dict = Depends(require_tenant_admin)):
    from app.connections import assign_connection
    return assign_connection(connection_id, payload.get("username",""), payload.get("access_level","read_only"), payload.get("enabled",True))

@router.delete("/tenant/connections/{connection_id}/assign/{username}")
def tenant_unassign_connection(request: Request, connection_id: int, username: str, user: dict = Depends(require_tenant_admin)):
    from app.connections import unassign_connection
    return unassign_connection(connection_id, username)
