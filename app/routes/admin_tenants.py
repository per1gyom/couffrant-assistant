"""
Routes admin — profil, tenants-overview, memory-status.
Extrait de admin.py — SPLIT-R2.
"""
from fastapi import APIRouter, Request, Body, Depends
from app.database import get_pg_conn
from app.app_security import authenticate, hash_password, DEFAULT_TENANT
from app.security_auth import validate_password_strength
from app.routes.deps import require_user, require_admin, require_tenant_admin

router = APIRouter(tags=["admin"])


# ─── PROFIL UTILISATEUR CONNECTÉ ───


@router.get("/profile")
def get_profile(request: Request, user: dict = Depends(require_user)):
    username = user["username"]
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute(
            "SELECT username, email, scope, tenant_id FROM users WHERE username=%s",
            (username,),
        )
        row = c.fetchone()
        if not row:
            return {"error": "Utilisateur introuvable."}
        return {
            "username": row[0],
            "email": row[1] or "",
            "scope": row[2],
            "tenant_id": row[3] or "",
        }
    except Exception as e:
        return {"error": str(e)[:100]}
    finally:
        if conn:
            conn.close()


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
        if conn:
            conn.close()


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
            (hash_password(new_password), username),
        )
        conn.commit()
        return {"status": "ok", "message": "Mot de passe mis à jour."}
    except Exception as e:
        return {"status": "error", "message": str(e)[:100]}
    finally:
        if conn:
            conn.close()


# ─── SUPER ADMIN — VUE TOUTES SOCIÉTÉS ───


@router.get("/admin/tenants-overview")
def admin_tenants_overview(request: Request, _: dict = Depends(require_admin)):
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("SELECT id, name, settings FROM tenants ORDER BY name")
        tenants_raw = c.fetchall()
        # HOTFIX 30/04 : ne pas afficher les soft-deletes dans la vue Societes
        c.execute("""
            SELECT u.username, u.email, u.scope, u.tenant_id, u.last_login,
                   u.created_at, COALESCE(u.account_locked, false),
                   COALESCE(u.must_reset_password, false),
                   COALESCE(u.suspended, false), u.settings
            FROM users u
            WHERE u.deleted_at IS NULL
            ORDER BY u.tenant_id, u.created_at
        """)
        users_raw = c.fetchall()
        stats = {}
        for table, key in [
            ("aria_memory", "conv"),
            ("aria_rules", "rules"),
            ("aria_insights", "insights"),
            ("mail_memory", "mails"),
        ]:
            c.execute(f"SELECT username, COUNT(*) FROM {table} GROUP BY username")
            for u, cnt in c.fetchall():
                stats.setdefault(u, {})[key] = cnt
        c.execute("SELECT username FROM oauth_tokens WHERE provider='microsoft'")
        ms_connected = {r[0] for r in c.fetchall()}
    finally:
        if conn:
            conn.close()

    users_by_tenant = {}
    for row in users_raw:
        (username, email, scope, tenant_id, last_login,
         created_at, locked, must_reset, suspended, user_settings) = row
        tid = tenant_id or DEFAULT_TENANT
        da = (user_settings or {}).get("direct_actions") if user_settings else None
        users_by_tenant.setdefault(tid, []).append({
            "username": username, "email": email or "", "scope": scope or "user",
            "last_login": str(last_login) if last_login else None,
            "created_at": str(created_at) if created_at else None,
            "ms_connected": username in ms_connected,
            "account_locked": bool(locked),
            "must_reset_password": bool(must_reset),
            "suspended": bool(suspended),
            "direct_actions_override": da,
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


# ─── TENANT ADMIN — VUE MA SOCIÉTÉ ───


@router.get("/tenant/my-overview")
def tenant_my_overview(request: Request, user: dict = Depends(require_tenant_admin)):
    """Vue société pour le tenant admin — sa propre société uniquement."""
    tenant_id = user["tenant_id"]
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("SELECT id, name, settings FROM tenants WHERE id = %s", (tenant_id,))
        tenant_row = c.fetchone()
        if not tenant_row:
            return []
        t_id, t_name, t_settings = tenant_row
        # HOTFIX 30/04 : ne pas afficher les soft-deletes dans la vue tenant_admin
        c.execute("""
            SELECT u.username, u.email, u.scope, u.tenant_id, u.last_login,
                   u.created_at, COALESCE(u.account_locked, false),
                   COALESCE(u.must_reset_password, false),
                   COALESCE(u.suspended, false), u.settings
            FROM users u WHERE u.tenant_id = %s AND u.deleted_at IS NULL ORDER BY u.created_at
        """, (tenant_id,))
        users_raw = c.fetchall()
        stats = {}
        for table, key in [
            ("aria_memory", "conv"),
            ("aria_rules", "rules"),
            ("aria_insights", "insights"),
            ("mail_memory", "mails"),
        ]:
            c.execute(
                f"SELECT username, COUNT(*) FROM {table} WHERE username IN "
                f"(SELECT username FROM users WHERE tenant_id = %s) GROUP BY username",
                (tenant_id,),
            )
            for u, cnt in c.fetchall():
                stats.setdefault(u, {})[key] = cnt
        c.execute(
            "SELECT username FROM oauth_tokens WHERE provider='microsoft' "
            "AND username IN (SELECT username FROM users WHERE tenant_id = %s)",
            (tenant_id,),
        )
        ms_connected = {r[0] for r in c.fetchall()}
    finally:
        if conn:
            conn.close()

    users = []
    for row in users_raw:
        (username, email, scope, tid, last_login,
         created_at, locked, must_reset, suspended, user_settings) = row
        da = (user_settings or {}).get("direct_actions") if user_settings else None
        users.append({
            "username": username, "email": email or "", "scope": scope or "user",
            "last_login": str(last_login) if last_login else None,
            "created_at": str(created_at) if created_at else None,
            "ms_connected": username in ms_connected,
            "account_locked": bool(locked),
            "must_reset_password": bool(must_reset),
            "suspended": bool(suspended),
            "direct_actions_override": da,
            **{k: stats.get(username, {}).get(k, 0) for k in ["conv", "rules", "insights", "mails"]},
        })

    sp = t_settings or {}
    return [{
        "tenant_id": t_id, "name": t_name or t_id,
        "settings": sp,
        "sharepoint_site": sp.get("sharepoint_site", ""),
        "sharepoint_folder": sp.get("sharepoint_folder", ""),
        "sharepoint_drive": sp.get("sharepoint_drive", "Documents"),
        "user_count": len(users),
        "ms_connected_count": sum(1 for u in users if u["ms_connected"]),
        "total_mails": sum(u["mails"] for u in users),
        "total_conv": sum(u["conv"] for u in users),
        "users": users,
    }]


# ─── MEMORY STATUS — DOUBLON SUPPRIME 30/04 ───
# L endpoint /admin/memory-status existe deja dans super_admin_users.py
# (ligne 296) avec le filtre deleted_at IS NULL applique. Le supprimer ici
# evite le conflit de routing FastAPI (l ordre d enregistrement determinait
# laquelle des deux versions etait active).
