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
from app.routes.admin_tenants import router as _at
router.include_router(_at)
from app.routes.admin_endpoints import router as _ep
router.include_router(_ep)


# ─── SUSPENSION ───

@router.post("/admin/suspend-user/{target}")
def admin_suspend_user(
    request: Request,
    target: str,
    payload: dict = Body(default={}),
    _: dict = Depends(require_admin),
):
    from app.suspension import suspend_user
    reason = payload.get("reason", "")
    return suspend_user(target, reason)


@router.post("/admin/unsuspend-user/{target}")
def admin_unsuspend_user(
    request: Request,
    target: str,
    _: dict = Depends(require_admin),
):
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
    _: dict = Depends(require_admin),
):
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
    """Admin tenant ou super admin peut toggler les actions directes d'un user."""
    from app.direct_actions import set_user_direct_actions
    enabled = payload.get("enabled")  # null = hériter du tenant
    return set_user_direct_actions(username, enabled)


# ─── SEEDING PROFIL ───

@router.post("/admin/seed-user")
def seed_user_endpoint(
    request: Request,
    payload: dict = Body(...),
    _: dict = Depends(require_admin),
):
    """Seed un utilisateur avec un profil metier. Idempotent."""
    username = payload.get("username", "").strip()
    profile = payload.get("profile", "generic").strip()
    if not username:
        return {"status": "error", "message": "Username requis."}
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
