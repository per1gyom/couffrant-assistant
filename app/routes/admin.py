import os
import threading
import requests as http_requests
from fastapi import APIRouter, Request, Body
from fastapi.responses import RedirectResponse, HTMLResponse
from app.database import get_pg_conn, init_postgres
from app.app_security import (
    create_user, delete_user, update_user, list_users, init_default_user,
    get_user_tools, set_user_tool, remove_user_tool,
    get_users_in_tenant, get_tenant_id, generate_reset_token,
    authenticate, hash_password,
    SCOPE_CS, SCOPE_USER, SCOPE_TENANT_ADMIN, DEFAULT_TENANT,
)
from app.token_manager import get_valid_microsoft_token
from app.routes.deps import require_admin, require_tenant_admin, require_user, get_session_tenant_id, assert_same_tenant

router = APIRouter(tags=["admin"])


# ─── PROFIL UTILISATEUR CONNECTÉ ───

@router.get("/profile")
def get_profile(request: Request):
    """Retourne email + username de l'utilisateur connecté."""
    if not require_user(request): return {"error": "Non connecté."}
    username = request.session.get("user", "")
    conn = None
    try:
        conn = get_pg_conn(); c = conn.cursor()
        c.execute("SELECT username, email, scope FROM users WHERE username=%s", (username,))
        row = c.fetchone()
        if not row: return {"error": "Utilisateur introuvable."}
        return {"username": row[0], "email": row[1] or "", "scope": row[2]}
    except Exception as e: return {"error": str(e)[:100]}
    finally:
        if conn: conn.close()


@router.put("/profile/email")
def update_profile_email(request: Request, payload: dict = Body(...)):
    """Met à jour l'email de l'utilisateur connecté."""
    if not require_user(request): return {"error": "Non connecté."}
    username = request.session.get("user", "")
    email = payload.get("email", "").strip()
    conn = None
    try:
        conn = get_pg_conn(); c = conn.cursor()
        c.execute("UPDATE users SET email=%s WHERE username=%s", (email or None, username))
        conn.commit()
        return {"status": "ok", "message": "Email mis à jour."}
    except Exception as e: return {"status": "error", "message": str(e)[:100]}
    finally:
        if conn: conn.close()


@router.put("/profile/password")
def update_profile_password(request: Request, payload: dict = Body(...)):
    """
    Change le mot de passe de l'utilisateur connecté.
    Nécessite le mot de passe actuel pour sécuriser l'opération.
    """
    if not require_user(request): return {"error": "Non connecté."}
    username = request.session.get("user", "")
    current_password = payload.get("current_password", "")
    new_password = payload.get("new_password", "")
    if not current_password or not new_password:
        return {"status": "error", "message": "Mot de passe actuel et nouveau requis."}
    if len(new_password) < 8:
        return {"status": "error", "message": "Nouveau mot de passe trop court (8 caractères min.)."}
    if not authenticate(username, current_password):
        return {"status": "error", "message": "Mot de passe actuel incorrect."}
    conn = None
    try:
        conn = get_pg_conn(); c = conn.cursor()
        c.execute("UPDATE users SET password_hash=%s WHERE username=%s", (hash_password(new_password), username))
        conn.commit()
        return {"status": "ok", "message": "Mot de passe mis à jour."}
    except Exception as e: return {"status": "error", "message": str(e)[:100]}
    finally:
        if conn: conn.close()


# ─── TENANTS (super-admin) ───

@router.get("/admin/tenants")
def list_tenants_endpoint(request: Request):
    if not require_admin(request): return {"error": "Accès refusé."}
    from app.tenant_manager import list_tenants
    return list_tenants()

@router.post("/admin/tenants")
def create_tenant_endpoint(request: Request, payload: dict = Body(...)):
    if not require_admin(request): return {"error": "Accès refusé."}
    from app.tenant_manager import create_tenant
    return create_tenant(payload.get("tenant_id","").strip(), payload.get("name","").strip(), payload.get("settings",{}))

@router.delete("/admin/tenants/{tenant_id}")
def delete_tenant_endpoint(request: Request, tenant_id: str):
    if not require_admin(request): return {"error": "Accès refusé."}
    from app.tenant_manager import delete_tenant
    return delete_tenant(tenant_id)

@router.post("/admin/tenants/{tenant_id}/tools")
def add_tenant_tool(request: Request, tenant_id: str, payload: dict = Body(...)):
    if not require_admin(request): return {"error": "Accès refusé."}
    from app.tenant_manager import add_custom_tool
    return add_custom_tool(tenant_id, payload.get("tool_id","").strip(),
                           payload.get("label","").strip(), payload.get("description",""),
                           payload.get("config_fields"))

@router.delete("/admin/tenants/{tenant_id}/tools/{tool_id}")
def remove_tenant_tool(request: Request, tenant_id: str, tool_id: str):
    if not require_admin(request): return {"error": "Accès refusé."}
    from app.tenant_manager import remove_custom_tool
    return remove_custom_tool(tenant_id, tool_id)

@router.put("/admin/tenants/{tenant_id}")
def update_tenant_endpoint(request: Request, tenant_id: str, payload: dict = Body(...)):
    if not require_admin(request): return {"error": "Accès refusé."}
    from app.tenant_manager import update_tenant_settings
    return update_tenant_settings(tenant_id, payload)


# ─── PANEL & USERS (super-admin) ───

@router.get("/admin/panel", response_class=HTMLResponse)
def admin_panel(request: Request):
    if not require_admin(request): return RedirectResponse("/login-app")
    with open("app/templates/admin_panel.html", "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())

@router.get("/admin/users")
def admin_list_users(request: Request):
    if not require_admin(request): return {"error": "Accès refusé."}
    return list_users()

@router.post("/admin/create-user")
def admin_create_user(request: Request, payload: dict = Body(...)):
    if not require_admin(request): return {"error": "Accès refusé."}
    return create_user(
        payload.get("username","").strip(), payload.get("password",""),
        payload.get("scope", SCOPE_USER), payload.get("tools"),
        tenant_id=payload.get("tenant_id", DEFAULT_TENANT),
        email=payload.get("email"),
    )

@router.put("/admin/update-user/{target}")
def admin_update_user(request: Request, target: str, payload: dict = Body(...)):
    if not require_admin(request): return {"error": "Accès refusé."}
    return update_user(target, email=payload.get("email"), scope=payload.get("scope"))

@router.delete("/admin/delete-user/{target}")
def admin_delete_user(request: Request, target: str):
    if not require_admin(request): return {"error": "Accès refusé."}
    return delete_user(target, request.session.get("user",""))

@router.post("/admin/reset-password/{target}")
def admin_reset_password(request: Request, target: str):
    if not require_tenant_admin(request): return {"error": "Accès refusé."}
    ok, err = assert_same_tenant(request, target)
    if not ok: return {"error": err}
    return generate_reset_token(target)


# ─── TENANT ADMIN (admin société) ───

@router.get("/tenant/users")
def tenant_list_users(request: Request):
    if not require_tenant_admin(request): return {"error": "Accès refusé."}
    return get_users_in_tenant(get_session_tenant_id(request))

@router.post("/tenant/create-user")
def tenant_create_user(request: Request, payload: dict = Body(...)):
    if not require_tenant_admin(request): return {"error": "Accès refusé."}
    tenant_id = get_session_tenant_id(request)
    scope = payload.get("scope", SCOPE_USER)
    if request.session.get("scope") == SCOPE_TENANT_ADMIN and scope not in (SCOPE_USER, SCOPE_CS):
        scope = SCOPE_USER
    return create_user(payload.get("username","").strip(), payload.get("password",""),
                       scope, payload.get("tools"), tenant_id=tenant_id,
                       email=payload.get("email"))

@router.put("/tenant/update-user/{target}")
def tenant_update_user(request: Request, target: str, payload: dict = Body(...)):
    if not require_tenant_admin(request): return {"error": "Accès refusé."}
    ok, err = assert_same_tenant(request, target)
    if not ok: return {"error": err}
    return update_user(target, email=payload.get("email"), scope=payload.get("scope"))

@router.delete("/tenant/delete-user/{target}")
def tenant_delete_user(request: Request, target: str):
    if not require_tenant_admin(request): return {"error": "Accès refusé."}
    ok, err = assert_same_tenant(request, target)
    if not ok: return {"error": err}
    return delete_user(target, request.session.get("user",""), get_session_tenant_id(request))

@router.post("/tenant/reset-password/{target}")
def tenant_reset_password(request: Request, target: str):
    if not require_tenant_admin(request): return {"error": "Accès refusé."}
    ok, err = assert_same_tenant(request, target)
    if not ok: return {"error": err}
    return generate_reset_token(target)

@router.get("/tenant/user-tools/{target}")
def tenant_get_tools(request: Request, target: str):
    if not require_tenant_admin(request): return {"error": "Accès refusé."}
    ok, err = assert_same_tenant(request, target)
    if not ok: return {"error": err}
    return get_user_tools(target, raw=True)

@router.post("/tenant/user-tools/{target}/{tool}")
def tenant_set_tool(request: Request, target: str, tool: str, payload: dict = Body(...)):
    if not require_tenant_admin(request): return {"error": "Accès refusé."}
    ok, err = assert_same_tenant(request, target)
    if not ok: return {"error": err}
    return set_user_tool(target, tool, payload.get("access_level","read_only"), payload.get("enabled",True), payload.get("config",{}))

@router.get("/tenant/rules")
def tenant_rules(request: Request):
    if not require_tenant_admin(request): return {"error": "Accès refusé."}
    conn = None
    try:
        conn = get_pg_conn(); c = conn.cursor()
        c.execute("""
            SELECT ar.id, ar.username, ar.category, ar.rule, ar.confidence, ar.reinforcements, ar.active
            FROM aria_rules ar JOIN users u ON u.username=ar.username
            WHERE u.tenant_id=%s ORDER BY ar.username, ar.active DESC, ar.confidence DESC
        """, (get_session_tenant_id(request),))
        cols=[d[0] for d in c.description]; return [dict(zip(cols,row)) for row in c.fetchall()]
    finally:
        if conn: conn.close()

@router.get("/tenant/memory-status")
def tenant_memory_status(request: Request):
    if not require_tenant_admin(request): return {"error": "Accès refusé."}
    tid = get_session_tenant_id(request)
    conn = None
    try:
        conn = get_pg_conn(); c = conn.cursor()
        c.execute("SELECT username, scope FROM users WHERE tenant_id=%s", (tid,))
        users = c.fetchall(); results = []
        for uname, scope in users:
            row = {"username":uname,"scope":scope}
            for table, key in [("aria_memory","conv"),("aria_rules","regles"),("aria_insights","insights"),("mail_memory","mails")]:
                c.execute(f"SELECT COUNT(*) FROM {table} WHERE username=%s",(uname,)); row[key]=c.fetchone()[0]
            results.append(row)
        return results
    finally:
        if conn: conn.close()


# ─── ADMIN GLOBAL ───

@router.get("/admin/rules")
def admin_rules(request: Request, user: str = ""):
    if not require_admin(request): return {"error": "Accès refusé."}
    conn = None
    try:
        conn = get_pg_conn(); c = conn.cursor()
        if user: c.execute("SELECT id,username,category,rule,confidence,reinforcements,active FROM aria_rules WHERE username=%s ORDER BY active DESC,confidence DESC",(user,))
        else: c.execute("SELECT id,username,category,rule,confidence,reinforcements,active FROM aria_rules ORDER BY username,active DESC,confidence DESC")
        cols=[d[0] for d in c.description]; return [dict(zip(cols,row)) for row in c.fetchall()]
    finally:
        if conn: conn.close()

@router.get("/admin/insights")
def admin_insights(request: Request, user: str = ""):
    if not require_admin(request): return {"error": "Accès refusé."}
    conn = None
    try:
        conn = get_pg_conn(); c = conn.cursor()
        if user: c.execute("SELECT id,username,topic,insight,reinforcements FROM aria_insights WHERE username=%s ORDER BY reinforcements DESC",(user,))
        else: c.execute("SELECT id,username,topic,insight,reinforcements FROM aria_insights ORDER BY username,reinforcements DESC")
        cols=[d[0] for d in c.description]; return [dict(zip(cols,row)) for row in c.fetchall()]
    finally:
        if conn: conn.close()

@router.get("/admin/memory-status")
def admin_memory_status(request: Request):
    if not require_admin(request): return {"error": "Accès refusé."}
    conn = None
    try:
        conn = get_pg_conn(); c = conn.cursor()
        c.execute("SELECT username,email,scope,tenant_id FROM users")
        meta = {r[0]:{"email":r[1],"scope":r[2],"tenant_id":r[3]} for r in c.fetchall()}
        agg = {}
        for table, key in [("aria_memory","conv"),("aria_rules","rules"),("aria_insights","insights"),("mail_memory","mails")]:
            c.execute(f"SELECT username, COUNT(*) FROM {table} GROUP BY username")
            for u,cnt in c.fetchall(): agg.setdefault(u,{})[key]=cnt
        return [{"username":u,**meta.get(u,{}),**agg.get(u,{"conv":0,"rules":0,"insights":0,"mails":0})} for u in sorted(set(list(meta)+list(agg)))]
    finally:
        if conn: conn.close()

@router.get("/admin/user-tools/{target}")
def admin_get_tools(request: Request, target: str):
    if not require_admin(request): return {"error": "Accès refusé."}
    return get_user_tools(target, raw=True)

@router.post("/admin/user-tools/{target}/{tool}")
def admin_set_tool(request: Request, target: str, tool: str, payload: dict = Body(...)):
    if not require_admin(request): return {"error": "Accès refusé."}
    return set_user_tool(target, tool, payload.get("access_level","read_only"), payload.get("enabled",True), payload.get("config",{}))

@router.delete("/admin/user-tools/{target}/{tool}")
def admin_remove_tool(request: Request, target: str, tool: str):
    if not require_admin(request): return {"error": "Accès refusé."}
    return remove_user_tool(target, tool)

@router.get("/init-db")
def init_db_now(request: Request):
    if not require_admin(request): return {"error": "Accès refusé."}
    init_postgres()
    try: init_default_user()
    except Exception: pass
    return {"status": "tables créées"}

@router.get("/test-elevenlabs")
def test_elevenlabs(request: Request):
    if not require_admin(request): return {"error": "Accès refusé."}
    api_key=os.environ.get("ELEVENLABS_API_KEY",""); voice_id=os.environ.get("ELEVENLABS_VOICE_ID","")
    resp=http_requests.post(f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
        headers={"xi-api-key":api_key,"Content-Type":"application/json"},
        json={"text":"Bonjour.","model_id":"eleven_flash_v2_5","voice_settings":{"stability":0.5,"similarity_boost":0.8}},timeout=30)
    return {"status_code":resp.status_code,"api_key_length":len(api_key),"voice_id":voice_id}

@router.get("/test-odoo")
def test_odoo(request: Request):
    if not require_admin(request): return {"error": "Accès refusé."}
    from app.connectors.odoo_connector import perform_odoo_action
    return perform_odoo_action(action="get_partner_by_email",params={"email":"guillaume@couffrant-solar.fr"})
