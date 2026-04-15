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

@router.get("/admin/users")@router.post("/admin/create-user")@router.put("/admin/update-user/{target}")@router.delete("/admin/delete-user/{target}")@router.post("/admin/reset-password/{target}")@router.post("/admin/users/{username}/reset-password")@router.get("/tenant/users")@router.post("/tenant/create-user")@router.put("/tenant/update-user/{target}")@router.delete("/tenant/delete-user/{target}")@router.post("/tenant/reset-password/{target}")@router.get("/tenant/user-tools/{target}")@router.get("/tenant/rules")@router.get("/admin/rules")@router.get("/admin/insights")@router.get("/admin/memory-status")
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


def init_db_now(request: Request, _: dict = Depends(require_admin)):
    init_postgres()
    try:
        init_default_user()
    except Exception:
        pass
    return {"status": "tables créées"}


