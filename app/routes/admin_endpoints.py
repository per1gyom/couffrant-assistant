"""
Endpoints admin gestion utilisateurs/regles/insights.
Extrait de admin.py -- SPLIT-R2.
"""
from fastapi import APIRouter,Request,Body
from fastapi.responses import JSONResponse
from app.routes.deps import require_admin,require_tenant_admin
from app.security_tools import ALL_SCOPES,SCOPE_USER,SCOPE_ADMIN,SCOPE_TENANT_ADMIN
from app.logging_config import get_logger
logger=get_logger("raya.admin")
router=APIRouter(tags=["admin"])


def admin_list_users(request: Request, _: dict = Depends(require_admin)):
    return list_users()




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




def admin_delete_user(
    request: Request,
    target: str,
    user: dict = Depends(require_admin),
):
    result = delete_user(target, user["username"])
    log_admin_action(user["username"], "delete_user", target)
    return result




def admin_reset_password(
    request: Request,
    target: str,
    _: dict = Depends(require_tenant_admin),
):
    assert_same_tenant(request, target)
    return generate_reset_token(target)




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



def tenant_list_users(request: Request, _: dict = Depends(require_tenant_admin)):
    return get_users_in_tenant(get_session_tenant_id(request))




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




def tenant_delete_user(
    request: Request,
    target: str,
    user: dict = Depends(require_tenant_admin),
):
    assert_same_tenant(request, target)
    result = delete_user(target, user["username"], user["tenant_id"])
    log_admin_action(user["username"], "delete_user", target)
    return result




def tenant_reset_password(
    request: Request,
    target: str,
    _: dict = Depends(require_tenant_admin),
):
    assert_same_tenant(request, target)
    return generate_reset_token(target)




def tenant_get_tools(
    request: Request,
    target: str,
    _: dict = Depends(require_tenant_admin),
):
    assert_same_tenant(request, target)
    return get_user_tools(target, raw=True)




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



