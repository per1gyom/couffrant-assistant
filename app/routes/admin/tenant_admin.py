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
from fastapi import APIRouter, Request, Body, Depends, HTTPException
from fastapi.responses import HTMLResponse

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
    # Recuperer l etat actuel du target pour can_modify_user / can_change_scope
    with get_pg_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT username, email, scope, tenant_id FROM users WHERE username=%s", (target,))
        row = cur.fetchone()
    if not row:
        return {"status": "error", "message": "Utilisateur introuvable."}
    target_user = {"username": row[0], "email": row[1] or "", "scope": row[2], "tenant_id": row[3]}
    # Garde-fous : modification du scope interdite si hardcoded / auto-modif / sous-privilege
    from app.hardcoded_permissions import can_modify_user, can_change_scope, is_hardcoded_super_admin
    allowed, reason = can_modify_user(admin, target_user)
    if not allowed:
        return {"status": "error", "message": reason}
    # Si changement de scope demande, garde-fou dedie
    new_scope = payload.get("scope")
    if new_scope and new_scope != target_user["scope"]:
        ok_scope, reason_scope = can_change_scope(admin, target_user, new_scope)
        if not ok_scope:
            return {"status": "error", "message": reason_scope}
    else:
        # Pas de changement de scope demande : on ne le modifie pas meme si present
        new_scope = None
    # Garde-fou email : si target est hardcoded super_admin, on ne laisse PAS toucher a l email
    new_email = payload.get("email")
    if new_email is not None and is_hardcoded_super_admin(target_user["email"]):
        if new_email.strip().lower() != target_user["email"].strip().lower():
            return {"status": "error", "message": "L email d un super-admin protege ne peut etre change via UI."}
    # display_name et phone : pas de garde-fou specifique, c est cosmetique
    result = update_user(
        target,
        email=new_email,
        scope=new_scope,
        display_name=payload.get("display_name"),
        phone=payload.get("phone"),
    )
    log_admin_action(admin["username"], "update_user", target,
                     f"scope={new_scope or 'unchanged'} display_name={payload.get('display_name') or 'unchanged'}")
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
        credentials={}, created_by=user["username"], status="not_configured")

@router.put("/tenant/connections/{connection_id}")
def tenant_update_connection(request: Request, connection_id: int, payload: dict = Body(...), user: dict = Depends(require_tenant_admin)):
    from app.connections import assert_connection_tenant
    if not assert_connection_tenant(connection_id, user["tenant_id"]):
        raise HTTPException(status_code=403, detail="Connexion hors de votre tenant.")
    from app.connections import update_connection
    safe = {k: v for k, v in payload.items() if k not in ("credentials", "tenant_id")}
    return update_connection(connection_id, **safe)

@router.delete("/tenant/connections/{connection_id}")
def tenant_delete_connection(request: Request, connection_id: int, user: dict = Depends(require_tenant_admin)):
    from app.connections import assert_connection_tenant, delete_connection
    if not assert_connection_tenant(connection_id, user["tenant_id"]):
        raise HTTPException(status_code=403, detail="Connexion hors de votre tenant.")
    return delete_connection(connection_id)

@router.post("/tenant/connections/{connection_id}/assign")
def tenant_assign_connection(request: Request, connection_id: int, payload: dict = Body(...), user: dict = Depends(require_tenant_admin)):
    from app.connections import assert_connection_tenant, assign_connection
    if not assert_connection_tenant(connection_id, user["tenant_id"]):
        raise HTTPException(status_code=403, detail="Connexion hors de votre tenant.")
    target = payload.get("username", "")
    assert_same_tenant(request, target)
    return assign_connection(connection_id, target, payload.get("access_level", "read_only"), payload.get("enabled", True))

@router.delete("/tenant/connections/{connection_id}/assign/{username}")
def tenant_unassign_connection(request: Request, connection_id: int, username: str, user: dict = Depends(require_tenant_admin)):
    from app.connections import assert_connection_tenant, unassign_connection
    if not assert_connection_tenant(connection_id, user["tenant_id"]):
        raise HTTPException(status_code=403, detail="Connexion hors de votre tenant.")
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


# ─── PANEL TENANT ───

@router.get("/tenant/panel", response_class=HTMLResponse)
def tenant_panel(request: Request):
    try:
        require_tenant_admin(request)
    except HTTPException:
        from fastapi.responses import RedirectResponse
        return RedirectResponse("/login-app")
    with open("app/templates/tenant_panel.html", "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())



# ─── PERMISSIONS (v1 : par connexion + par user) ───
# Plan : docs/raya_permissions_plan.md etapes 4 + 7

@router.get("/tenant/permissions")
def tenant_get_permissions(request: Request, _: dict = Depends(require_tenant_admin)):
    """Liste toutes les connexions du tenant avec leurs niveaux de permission.

    Format :
    [{"connection_id": 1, "tool_type": "odoo", "super_admin_level": "read_write",
      "tenant_admin_level": "read", "previous_level": null}, ...]
    """
    tenant_id = get_session_tenant_id(request)
    try:
        with get_pg_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT id, tool_type, name, status,
                       super_admin_permission_level,
                       tenant_admin_permission_level,
                       previous_permission_level
                FROM tenant_connections
                WHERE tenant_id = %s
                ORDER BY tool_type, id
            """, (tenant_id,))
            rows = cur.fetchall()
            return [{
                "connection_id": r[0],
                "tool_type": r[1],
                "name": r[2] or r[1],
                "status": r[3],
                "super_admin_level": r[4] or "read",
                "tenant_admin_level": r[5] or "read",
                "previous_level": r[6],
            } for r in rows]
    except Exception as e:
        return {"status": "error", "message": str(e)[:300]}

@router.post("/tenant/permissions/update")
async def tenant_update_permission(
    request: Request,
    _: dict = Depends(require_tenant_admin),
):
    """Met a jour la permission d une connexion (tenant admin only).

    Body JSON : {"connection_id": 1, "new_level": "read_write"}

    Le new_level est automatiquement cappe au plafond super_admin_permission_level.
    """
    tenant_id = get_session_tenant_id(request)
    try:
        body = await request.json()
        connection_id = int(body.get("connection_id"))
        new_level = body.get("new_level")
        if new_level not in ("read", "read_write", "read_write_delete"):
            return {"status": "error", "message": "Niveau invalide"}
        from app.permissions import update_permission
        ok, msg = update_permission(
            tenant_id=tenant_id,
            connection_id=connection_id,
            new_level=new_level,
            actor_role="tenant_admin",
        )
        if not ok:
            return {"status": "error", "message": msg}
        log_admin_action(
            tenant_id=tenant_id,
            admin_user="tenant_admin",
            action="permission_update",
            target=str(connection_id),
            details=f"level={new_level}",
        )
        return {"status": "ok", "connection_id": connection_id, "new_level": new_level}
    except Exception as e:
        return {"status": "error", "message": str(e)[:300]}

@router.post("/tenant/permissions/toggle-read-only")
def tenant_toggle_read_only(request: Request, _: dict = Depends(require_tenant_admin)):
    """Bouton 'Tout en lecture seule' : bascule toutes les connexions du tenant
    en 'read' ou restaure depuis previous_permission_level.

    Toggle :
    - Si majorite actuellement en 'read' avec previous NOT NULL -> restaure
    - Sinon -> sauve previous_permission_level et passe tout en 'read'
    """
    tenant_id = get_session_tenant_id(request)
    try:
        from app.permissions import toggle_all_read_only
        result = toggle_all_read_only(tenant_id=tenant_id, actor_role="tenant_admin")
        log_admin_action(
            tenant_id=tenant_id,
            admin_user="tenant_admin",
            action="permission_toggle_read_only",
            target=tenant_id,
            details=f"action={result.get('action')} affected={result.get('affected')}",
        )
        return {"status": "ok", **result}
    except Exception as e:
        return {"status": "error", "message": str(e)[:300]}
