import os
import http.client
import requests as http_requests
from fastapi import APIRouter, Request, Body, Depends, HTTPException
from fastapi.responses import RedirectResponse, HTMLResponse
from app.database import get_pg_conn, init_postgres
from app.app_security import (
    create_user, delete_user, update_user, list_users, init_default_user,
    get_user_tools, set_user_tool, remove_user_tool,
    get_users_in_tenant, get_tenant_id, generate_reset_token,
    authenticate, hash_password,
    SCOPE_CS, SCOPE_USER, SCOPE_TENANT_ADMIN, SCOPE_ADMIN, DEFAULT_TENANT,
)
from app.security_auth import validate_password_strength, unlock_account
from app.token_manager import get_valid_microsoft_token
from app.routes.deps import (
    require_user, require_admin, require_tenant_admin,
    get_session_tenant_id, assert_same_tenant,
)
from app.admin_audit import log_admin_action
from app.dashboard_service import get_costs_dashboard

router = APIRouter(tags=["admin"])


# ─── PROFIL UTILISATEUR CONNECTÉ ───

@router.get("/profile")
def get_profile(request: Request, user: dict = Depends(require_user)):
    username = user["username"]
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("SELECT username, email, scope FROM users WHERE username=%s", (username,))
        row = c.fetchone()
        if not row:
            return {"error": "Utilisateur introuvable."}
        return {"username": row[0], "email": row[1] or "", "scope": row[2]}
    except Exception as e:
        return {"error": str(e)[:100]}
    finally:
        if conn: conn.close()


@router.put("/profile/email")
def update_profile_email(
    request: Request,
    payload: dict = Body(...),
    user: dict = Depends(require_user),
):
    username = user["username"]
    email = payload.get("email", "").strip()
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("UPDATE users SET email=%s WHERE username=%s", (email or None, username))
        conn.commit()
        return {"status": "ok", "message": "Email mis à jour."}
    except Exception as e:
        return {"status": "error", "message": str(e)[:100]}
    finally:
        if conn: conn.close()


@router.put("/profile/password")
def update_profile_password(
    request: Request,
    payload: dict = Body(...),
    user: dict = Depends(require_user),
):
    username = user["username"]
    current_password = payload.get("current_password", "")
    new_password = payload.get("new_password", "")
    if not current_password or not new_password:
        return {"status": "error", "message": "Mot de passe actuel et nouveau requis."}
    ok, msg = validate_password_strength(new_password)
    if not ok:
        return {"status": "error", "message": msg}
    if not authenticate(username, current_password):
        return {"status": "error", "message": "Mot de passe actuel incorrect."}
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute(
            "UPDATE users SET password_hash=%s WHERE username=%s",
            (hash_password(new_password), username)
        )
        conn.commit()
        return {"status": "ok", "message": "Mot de passe mis à jour."}
    except Exception as e:
        return {"status": "error", "message": str(e)[:100]}
    finally:
        if conn: conn.close()


# ─── DÉBLOCAGE COMPTE ───

@router.post("/admin/unlock-user/{target}")
def admin_unlock_user(
    request: Request,
    target: str,
    admin: dict = Depends(require_admin),
):
    result = unlock_account(target)
    log_admin_action(admin["username"], "unlock_user", target)
    return result


# ─── COUTS LLM (5F-1) ───

@router.get("/admin/costs")
def admin_costs(
    request: Request,
    days: int = 30,
    user: dict = Depends(require_admin),
):
    """
    Dashboard des couts LLM.
    super_admin : toutes les donnees (pas de filtre tenant).
    admin : filtre sur son propre tenant.
    """
    tenant_filter = None if user.get("scope") == "super_admin" else user.get("tenant_id")
    return get_costs_dashboard(tenant_id=tenant_filter, days=days)


# ─── CONFIG SHAREPOINT ───

@router.get("/admin/tenants/{tenant_id}/sharepoint")
def get_sharepoint_config(
    request: Request,
    tenant_id: str,
    _: dict = Depends(require_admin),
):
    from app.connectors.drive_connector import get_drive_config
    config = get_drive_config(tenant_id)
    return {
        "tenant_id": tenant_id,
        "sharepoint_site": config["site_name"],
        "sharepoint_folder": config["folder_name"],
        "sharepoint_drive": config["drive_name"],
    }


@router.put("/admin/tenants/{tenant_id}/sharepoint")
def update_sharepoint_config(
    request: Request,
    tenant_id: str,
    payload: dict = Body(...),
    _: dict = Depends(require_admin),
):
    site = payload.get("sharepoint_site", "").strip()
    folder = payload.get("sharepoint_folder", "").strip()
    drive = payload.get("sharepoint_drive", "Documents").strip()
    if not site or not folder:
        return {"status": "error", "message": "Site et dossier requis."}
    from app.connectors.drive_connector import save_drive_config
    return save_drive_config(tenant_id, site, folder, drive)


# ─── SOCIÉTÉS ───

@router.get("/admin/tenants-overview")
def admin_tenants_overview(request: Request, _: dict = Depends(require_admin)):
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("SELECT id, name, settings FROM tenants ORDER BY name")
        tenants_raw = c.fetchall()
        c.execute("""
            SELECT u.username, u.email, u.scope, u.tenant_id, u.last_login, u.created_at,
                   COALESCE(u.account_locked, false), COALESCE(u.must_reset_password, false)
            FROM users u ORDER BY u.tenant_id, u.created_at
        """)
        users_raw = c.fetchall()
        stats = {}
        for table, key in [
            ("aria_memory", "conv"), ("aria_rules", "rules"),
            ("aria_insights", "insights"), ("mail_memory", "mails"),
        ]:
            c.execute(f"SELECT username, COUNT(*) FROM {table} GROUP BY username")
            for u, cnt in c.fetchall():
                stats.setdefault(u, {})[key] = cnt
        c.execute("SELECT username FROM oauth_tokens WHERE provider='microsoft'")
        ms_connected = {r[0] for r in c.fetchall()}
    finally:
        if conn: conn.close()

    users_by_tenant = {}
    for row in users_raw:
        username, email, scope, tenant_id, last_login, created_at, locked, must_reset = row
        tid = tenant_id or DEFAULT_TENANT
        users_by_tenant.setdefault(tid, []).append({
            "username": username, "email": email or "", "scope": scope or "user",
            "last_login": str(last_login) if last_login else None,
            "created_at": str(created_at) if created_at else None,
            "ms_connected": username in ms_connected,
            "account_locked": bool(locked),
            "must_reset_password": bool(must_reset),
            **{k: stats.get(username, {}).get(k, 0) for k in ["conv", "rules", "insights", "mails"]},
        })

    result = []
    for tenant_id, name, settings in tenants_raw:
        users = users_by_tenant.get(tenant_id, [])
        sp = settings or {}
        result.append({
            "tenant_id": tenant_id, "name": name or tenant_id,
            "settings": sp,
            "sharepoint_site": sp.get("sharepoint_site", "Commun"),
            "sharepoint_folder": sp.get("sharepoint_folder", "1_Photovoltaïque"),
            "sharepoint_drive": sp.get("sharepoint_drive", "Documents"),
            "user_count": len(users),
            "ms_connected_count": sum(1 for u in users if u["ms_connected"]),
            "total_mails": sum(u["mails"] for u in users),
            "total_conv": sum(u["conv"] for u in users),
            "users": users,
        })

    orphans = users_by_tenant.get(DEFAULT_TENANT, [])
    if orphans and not any(t["tenant_id"] == DEFAULT_TENANT for t in result):
        result.insert(0, {
            "tenant_id": DEFAULT_TENANT, "name": "Couffrant Solar",
            "settings": {}, "sharepoint_site": "Commun",
            "sharepoint_folder": "1_Photovoltaïque", "sharepoint_drive": "Documents",
            "user_count": len(orphans),
            "ms_connected_count": sum(1 for u in orphans if u["ms_connected"]),
            "total_mails": sum(u["mails"] for u in orphans),
            "total_conv": sum(u["conv"] for u in orphans),
            "users": orphans,
        })
    return result


# ─── TENANTS ───

@router.get("/admin/tenants")
def list_tenants_endpoint(request: Request, _: dict = Depends(require_admin)):
    from app.tenant_manager import list_tenants
    return list_tenants()


@router.post("/admin/tenants")
def create_tenant_endpoint(
    request: Request,
    payload: dict = Body(...),
    _: dict = Depends(require_admin),
):
    from app.tenant_manager import create_tenant
    return create_tenant(
        payload.get("tenant_id", "").strip(),
        payload.get("name", "").strip(),
        payload.get("settings", {}),
    )


@router.delete("/admin/tenants/{tenant_id}")
def delete_tenant_endpoint(
    request: Request,
    tenant_id: str,
    _: dict = Depends(require_admin),
):
    from app.tenant_manager import delete_tenant
    return delete_tenant(tenant_id)


@router.put("/admin/tenants/{tenant_id}")
def update_tenant_endpoint(
    request: Request,
    tenant_id: str,
    payload: dict = Body(...),
    _: dict = Depends(require_admin),
):
    from app.tenant_manager import update_tenant_settings
    return update_tenant_settings(tenant_id, payload)


# ─── PANEL & USERS ───

@router.get("/admin/panel", response_class=HTMLResponse)
def admin_panel(request: Request):
    try:
        require_admin(request)
    except HTTPException:
        return RedirectResponse("/login-app")
    with open("app/templates/admin_panel.html", "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())


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
