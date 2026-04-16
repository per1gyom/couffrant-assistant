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
        c.execute(
            "SELECT username, email, scope, tenant_id, display_name FROM users WHERE username=%s",
            (username,)
        )
        row = c.fetchone()
        if not row:
            return {"error": "Utilisateur introuvable."}
        return {
            "username": row[0],
            "email": row[1] or "",
            "scope": row[2],
            "tenant_id": row[3] or "",
            "display_name": row[4] or "",
        }
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
