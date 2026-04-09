"""
Page de redéfinition forcée du mot de passe.

Déclenchée quand :
  - Un admin génère un lien de reset pour un utilisateur
  - Un nouvel utilisateur se connecte pour la première fois

L'utilisateur ne peut pas accéder au chat sans avoir défini
un nouveau mot de passe fort conforme à la politique.
"""
from fastapi import APIRouter, Request, Form
from fastapi.responses import RedirectResponse, HTMLResponse
from app.security_auth import hash_password, validate_password_strength
from app.security_users import set_must_reset_password
from app.database import get_pg_conn

router = APIRouter(tags=["forced_reset"])


def _render(error: str = "", username: str = "") -> str:
    with open("app/templates/forced_reset.html", "r", encoding="utf-8") as f:
        html = f.read()
    error_block = f'<div class="error">{error}</div>' if error else ""
    user_block = f'<div class="user-hint">Compte : <strong>{username}</strong></div>' if username else ""
    return html.replace("{{error_block}}", error_block).replace("{{user_block}}", user_block)


@router.get("/forced-reset", response_class=HTMLResponse)
def forced_reset_get(request: Request):
    username = request.session.get("user")
    if not username:
        return RedirectResponse("/login-app")
    if not request.session.get("must_reset"):
        return RedirectResponse("/chat")
    return HTMLResponse(_render(username=username))


@router.post("/forced-reset", response_class=HTMLResponse)
async def forced_reset_post(
    request: Request,
    new_password: str = Form(...),
    confirm_password: str = Form(...),
):
    username = request.session.get("user")
    if not username:
        return RedirectResponse("/login-app")

    if new_password != confirm_password:
        return HTMLResponse(_render(
            error="Les mots de passe ne correspondent pas.",
            username=username
        ))

    # Validation force du mot de passe
    ok, msg = validate_password_strength(new_password)
    if not ok:
        return HTMLResponse(_render(error=msg, username=username))

    # Mise à jour en base
    conn = None
    try:
        conn = get_pg_conn(); c = conn.cursor()
        c.execute(
            "UPDATE users SET password_hash=%s, must_reset_password=false WHERE username=%s",
            (hash_password(new_password), username)
        )
        conn.commit()
    except Exception as e:
        return HTMLResponse(_render(
            error=f"Erreur lors de la mise à jour : {str(e)[:80]}",
            username=username
        ))
    finally:
        if conn: conn.close()

    request.session.pop("must_reset", None)
    return RedirectResponse("/chat", status_code=303)
