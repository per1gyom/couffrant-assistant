"""
Endpoints profil de l'utilisateur connecté.
  GET  /profile
  PUT  /profile/email
  PUT  /profile/password
  PUT  /profile/display-name
"""
from fastapi import APIRouter, Request, Body, Depends

from app.database import get_pg_conn
from app.app_security import authenticate, hash_password
from app.security_auth import validate_password_strength
from app.routes.deps import require_user

router = APIRouter()


@router.get("/profile")
def get_profile(request: Request, user: dict = Depends(require_user)):
    username = user["username"]
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        # Essai avec tous les champs (enrichi en Phase 2 pour /settings)
        try:
            c.execute(
                """
                SELECT u.username, u.email, u.scope, u.tenant_id, u.display_name,
                       u.deletion_requested_at, u.phone, u.last_login, u.created_at,
                       u.settings, t.name AS tenant_name
                FROM users u
                LEFT JOIN tenants t ON t.id = u.tenant_id
                WHERE u.username = %s
                """,
                (username,)
            )
            row = c.fetchone()
            if not row:
                return {"error": "Utilisateur introuvable."}
            scope = row[2] or ""
            # Rôles cumulatifs (cohérent avec docs/architecture_roles_cumulatifs.md)
            is_tenant_admin = scope in ("tenant_admin", "admin", "super_admin")
            is_super_admin = scope in ("admin", "super_admin")
            return {
                "username": row[0],
                "email": row[1] or "",
                "scope": scope,
                "tenant_id": row[3] or "",
                "display_name": row[4] or "",
                "deletion_requested_at": str(row[5]) if row[5] else None,
                "phone": row[6] or "",
                "last_login": row[7].isoformat() if row[7] else None,
                "created_at": row[8].isoformat() if row[8] else None,
                "settings": row[9] or {},
                "tenant_name": row[10] or row[3] or "",
                "is_user": True,
                "is_tenant_admin": is_tenant_admin,
                "is_super_admin": is_super_admin,
            }
        except Exception:
            # Fallback sans colonnes optionnelles (rétrocompatibilité)
            c.execute("SELECT username, email, scope, tenant_id FROM users WHERE username=%s", (username,))
            row = c.fetchone()
            if not row:
                return {"error": "Utilisateur introuvable."}
            return {"username": row[0], "email": row[1] or "", "scope": row[2] or "", "tenant_id": row[3] or ""}
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


@router.put("/profile/display-name")
def update_profile_display_name(
    request: Request,
    payload: dict = Body(...),
    user: dict = Depends(require_user),
):
    """Permet à l'utilisateur de définir son nom d'affichage personnalisé."""
    username = user["username"]
    display_name = payload.get("display_name", "").strip()
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute(
            "UPDATE users SET display_name=%s WHERE username=%s",
            (display_name or None, username)
        )
        conn.commit()
        return {"status": "ok", "message": "Nom d'affichage mis à jour.", "display_name": display_name or ""}
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


@router.put("/profile/phone")
def update_profile_phone(
    request: Request,
    payload: dict = Body(...),
    user: dict = Depends(require_user),
):
    """Phase 2 /settings — numero de telephone (optionnel, alertes urgentes)."""
    username = user["username"]
    phone = (payload.get("phone") or "").strip()
    # Validation simple : on laisse l'utilisateur libre sur le format
    # mais on limite la longueur pour eviter les abus
    if len(phone) > 30:
        return {"status": "error", "message": "Numero trop long (max 30 caracteres)."}
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute(
            "UPDATE users SET phone=%s WHERE username=%s",
            (phone or None, username)
        )
        conn.commit()
        return {"status": "ok", "message": "Telephone mis a jour.", "phone": phone or ""}
    except Exception as e:
        return {"status": "error", "message": str(e)[:100]}
    finally:
        if conn: conn.close()


@router.put("/profile/settings")
def update_profile_settings(
    request: Request,
    payload: dict = Body(...),
    user: dict = Depends(require_user),
):
    """Phase 2 /settings — preferences d'affichage (toggles).

    Attendu : {settings: {email_notifications: bool, show_response_time: bool, compact_mode: bool}}
    Stocke en JSONB dans users.settings pour extensibilite future.
    """
    username = user["username"]
    new_settings = payload.get("settings", {})
    if not isinstance(new_settings, dict):
        return {"status": "error", "message": "Format invalide."}
    # Whitelist des cles autorisees (securite)
    allowed_keys = {
        "email_notifications",
        "show_response_time",
        "compact_mode",
        "auto_speak",
    }
    filtered = {k: v for k, v in new_settings.items() if k in allowed_keys}
    import json
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        # Merge avec les settings existants (on ne remplace pas tout)
        c.execute("SELECT settings FROM users WHERE username=%s", (username,))
        row = c.fetchone()
        current = (row[0] if row else {}) or {}
        merged = {**current, **filtered}
        c.execute(
            "UPDATE users SET settings=%s WHERE username=%s",
            (json.dumps(merged), username)
        )
        conn.commit()
        return {"status": "ok", "message": "Preferences mises a jour.", "settings": merged}
    except Exception as e:
        return {"status": "error", "message": str(e)[:100]}
    finally:
        if conn: conn.close()
