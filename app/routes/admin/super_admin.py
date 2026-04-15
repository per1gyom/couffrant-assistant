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


# ─── COÛTS LLM (5F-1) ───

@router.get("/admin/costs")
def admin_costs(
    request: Request,
    days: int = 30,
    user: dict = Depends(require_admin),
):
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
def _build_tenants_overview(tenant_filter=None):
    """Construit l'overview. tenant_filter=None → tous, sinon filtre un tenant."""
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        if tenant_filter:
            c.execute("SELECT id, name, settings FROM tenants WHERE id = %s", (tenant_filter,))
        else:
            c.execute("SELECT id, name, settings FROM tenants ORDER BY name")
        tenants_raw = c.fetchall()
        q_users = """
            SELECT u.username, u.email, u.scope, u.tenant_id, u.last_login, u.created_at,
                   COALESCE(u.account_locked, false), COALESCE(u.must_reset_password, false),
                   COALESCE(u.suspended, false), u.settings
            FROM users u {} ORDER BY u.tenant_id, u.created_at
        """
        if tenant_filter:
            c.execute(q_users.format("WHERE u.tenant_id = %s"), (tenant_filter,))
        else:
            c.execute(q_users.format(""))
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
        username, email, scope, tenant_id, last_login, created_at, locked, must_reset, suspended, user_settings = row
        tid = tenant_id or DEFAULT_TENANT
        da_override = None
        if user_settings and isinstance(user_settings, dict):
            da_override = user_settings.get("direct_actions")
        users_by_tenant.setdefault(tid, []).append({
            "username": username, "email": email or "", "scope": scope or "user",
            "last_login": str(last_login) if last_login else None,
            "created_at": str(created_at) if created_at else None,
            "ms_connected": username in ms_connected,
            "account_locked": bool(locked),
            "must_reset_password": bool(must_reset),
            "suspended": bool(suspended),
            "direct_actions_override": da_override,
            **{k: stats.get(username, {}).get(k, 0) for k in ["conv", "rules", "insights", "mails"]},
        })

    result = []
    for tenant_id, name, settings in tenants_raw:
        users = users_by_tenant.get(tenant_id, [])
        sp = settings or {}
        result.append({
            "tenant_id": tenant_id, "name": name or tenant_id,
            "settings": sp,
            "sharepoint_site": sp.get("sharepoint_site", ""),
            "sharepoint_folder": sp.get("sharepoint_folder", ""),
            "sharepoint_drive": sp.get("sharepoint_drive", ""),
            "user_count": len(users),
            "ms_connected_count": sum(1 for u in users if u["ms_connected"]),
            "total_mails": sum(u["mails"] for u in users),
            "total_conv": sum(u["conv"] for u in users),
            "users": users,
        })

    if not tenant_filter:
        orphans = users_by_tenant.get(DEFAULT_TENANT, [])
        if orphans and not any(t["tenant_id"] == DEFAULT_TENANT for t in result):
            result.insert(0, {
                "tenant_id": DEFAULT_TENANT, "name": "Couffrant Solar",
                "settings": {}, "sharepoint_site": "",
                "sharepoint_folder": "", "sharepoint_drive": "",
                "user_count": len(orphans),
                "ms_connected_count": sum(1 for u in orphans if u["ms_connected"]),
                "total_mails": sum(u["mails"] for u in orphans),
                "total_conv": sum(u["conv"] for u in orphans),
                "users": orphans,
            })
    return result


@router.get("/admin/tenants-overview")
def admin_tenants_overview(request: Request, _: dict = Depends(require_admin)):
    return _build_tenants_overview()


@router.get("/tenant/my-overview")
def tenant_my_overview(request: Request, user: dict = Depends(require_tenant_admin)):
    """Overview du tenant du user connecté (tenant admin)."""
    return _build_tenants_overview(tenant_filter=user["tenant_id"])


# ─── TENANTS CRUD ───

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
        payload.get("tenant_id", payload.get("id", "")).strip(),
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

import time

ADMIN_AUTH_TIMEOUT = 600  # 10 minutes

ADMIN_LOGIN_PAGE = """<!DOCTYPE html>
<html lang="fr"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Raya — Accès Admin</title>
<link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500&family=IBM+Plex+Sans:wght@400;500;600&display=swap" rel="stylesheet">
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{background:#0e0e12;color:#e0e0e0;font-family:'IBM Plex Sans',sans-serif;display:flex;align-items:center;justify-content:center;min-height:100vh}}
.card{{background:#16161d;border:1px solid #2a2a35;border-radius:16px;padding:36px;max-width:380px;width:90%}}
h2{{font-size:18px;margin-bottom:6px;color:#fff}}
.sub{{font-size:12px;color:#888;margin-bottom:24px;font-family:'JetBrains Mono',monospace}}
label{{display:block;font-size:12px;color:#aaa;margin-bottom:6px}}
input{{width:100%;padding:10px 14px;background:#1e1e28;border:1px solid #2a2a35;border-radius:8px;color:#fff;font-size:14px;margin-bottom:16px}}
input:focus{{outline:none;border-color:#6366f1}}
button{{width:100%;padding:10px;background:#6366f1;color:#fff;border:none;border-radius:8px;font-size:14px;font-weight:600;cursor:pointer}}
button:hover{{background:#4f46e5}}
.err{{color:#ef4444;font-size:12px;margin-bottom:12px;font-family:'JetBrains Mono',monospace}}
.back{{display:block;text-align:center;margin-top:16px;color:#888;font-size:12px;text-decoration:none}}
.back:hover{{color:#fff}}
</style></head><body>
<div class="card">
<h2>🔒 Accès protégé</h2>
<div class="sub">Saisissez votre mot de passe pour accéder au panel d'administration.</div>
{error_block}
<form method="POST" action="/admin/auth">
<label>Mot de passe</label>
<input type="password" name="password" autofocus required placeholder="Votre mot de passe">
<input type="hidden" name="next" value="{next_url}">
<button type="submit">Accéder</button>
</form>
<a class="back" href="/chat">← Retour au chat</a>
</div></body></html>"""


@router.get("/admin/panel", response_class=HTMLResponse)
def admin_panel(request: Request):
    try:
        require_tenant_admin(request)
    except HTTPException:
        return RedirectResponse("/login-app")
    # Vérifier re-auth admin (10 min)
    admin_auth_at = request.session.get("admin_auth_at", 0)
    if time.time() - admin_auth_at > ADMIN_AUTH_TIMEOUT:
        return HTMLResponse(ADMIN_LOGIN_PAGE.format(error_block="", next_url="/admin/panel"))
    with open("app/templates/admin_panel.html", "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())


@router.post("/admin/auth")
async def admin_auth(request: Request):
    """Re-authentification admin — protège l'accès au panel."""
    from app.app_security import authenticate
    form = await request.form()
    password = form.get("password", "")
    next_url = form.get("next", "/admin/panel")
    username = request.session.get("user")
    if not username:
        return RedirectResponse("/login-app", status_code=303)
    if authenticate(username, password):
        request.session["admin_auth_at"] = time.time()
        return RedirectResponse(next_url, status_code=303)
    return HTMLResponse(
        ADMIN_LOGIN_PAGE.format(
            error_block='<div class="err">Mot de passe incorrect.</div>',
            next_url=next_url,
        )
    )
    with open("app/templates/admin_panel.html", "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())


# ─── SUSPENSION ───

@router.post("/admin/suspend-user/{target}")
def admin_suspend_user(
    request: Request,
    target: str,
    payload: dict = Body(default={}),
    user: dict = Depends(require_tenant_admin),
):
    if user["scope"] != "admin":
        assert_same_tenant(request, target)
    from app.suspension import suspend_user
    reason = payload.get("reason", "")
    return suspend_user(target, reason)


@router.post("/admin/unsuspend-user/{target}")
def admin_unsuspend_user(
    request: Request,
    target: str,
    user: dict = Depends(require_tenant_admin),
):
    if user["scope"] != "admin":
        assert_same_tenant(request, target)
    from app.suspension import unsuspend_user
    return unsuspend_user(target)


@router.post("/admin/suspend-tenant/{tenant_id}")
def admin_suspend_tenant(
    request: Request,
    tenant_id: str,
    payload: dict = Body(default={}),
    _: dict = Depends(require_admin),
):
    from app.suspension import suspend_tenant
    reason = payload.get("reason", "")
    return suspend_tenant(tenant_id, reason)


@router.post("/admin/unsuspend-tenant/{tenant_id}")
def admin_unsuspend_tenant(
    request: Request,
    tenant_id: str,
    _: dict = Depends(require_admin),
):
    from app.suspension import unsuspend_tenant
    return unsuspend_tenant(tenant_id)


# ─── ACTIONS DIRECTES ───

@router.post("/admin/direct-actions/tenant/{tenant_id}")
def admin_toggle_tenant_direct_actions(
    request: Request,
    tenant_id: str,
    payload: dict = Body(default={}),
    user: dict = Depends(require_tenant_admin),
):
    if user["scope"] != "admin" and user["tenant_id"] != tenant_id:
        raise HTTPException(status_code=403, detail="Pas autorisé pour ce tenant.")
    from app.direct_actions import set_tenant_direct_actions
    enabled = bool(payload.get("enabled", False))
    return set_tenant_direct_actions(tenant_id, enabled)


@router.post("/admin/direct-actions/user/{username}")
def admin_toggle_user_direct_actions(
    request: Request,
    username: str,
    payload: dict = Body(default={}),
    user: dict = Depends(require_tenant_admin),
):
    if user["scope"] != "admin":
        assert_same_tenant(request, username)
    from app.direct_actions import set_user_direct_actions
    enabled = payload.get("enabled")
    return set_user_direct_actions(username, enabled)


# ─── SEEDING PROFIL ───

@router.post("/admin/seed-user")
def seed_user_endpoint(
    request: Request,
    payload: dict = Body(...),
    _: dict = Depends(require_admin),
):
    username = payload.get("username", "").strip()
    profile = payload.get("profile", "generic").strip()
    if not username:
        return {"status": "error", "message": "Username requis."}
    from app.app_security import get_tenant_id
    tenant_id = get_tenant_id(username)
    if not tenant_id:
        return {"status": "error", "message": f"Utilisateur '{username}' introuvable."}
    try:
        from app.seeding import seed_tenant, PROFILES
        if profile not in PROFILES:
            return {"status": "error", "message": f"Profil inconnu. Disponibles : {list(PROFILES.keys())}"}
        counts = seed_tenant(tenant_id, username, profile=profile)
        total = sum(counts.values())
        return {"status": "ok", "message": f"{total} regles seedees (profil '{profile}').", "counts": counts}
    except Exception as e:
        return {"status": "error", "message": str(e)[:200]}


from app.routes.admin.super_admin_users import router as _su
router.include_router(_su)
from app.routes.admin.super_admin_system import router as _ss
router.include_router(_ss)
