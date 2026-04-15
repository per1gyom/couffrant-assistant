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

@router.get("/admin/panel", response_class=HTMLResponse)
def admin_panel(request: Request):
    try:
        require_admin(request)
    except HTTPException:
        return RedirectResponse("/login-app")
    with open("app/templates/admin_panel.html", "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())


from app.routes.admin.super_admin_users import router as _su
router.include_router(_su)
from app.routes.admin.super_admin_system import router as _ss
router.include_router(_ss)
