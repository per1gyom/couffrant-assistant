from fastapi import APIRouter, Request, Form
from fastapi.responses import RedirectResponse, HTMLResponse
from app.auth import build_msal_app
from app.config import GRAPH_SCOPES, REDIRECT_URI
from app.token_manager import save_microsoft_token, save_google_token
from app.app_security import (
    authenticate, update_last_login, get_user_scope,
    get_tenant_id, LOGIN_PAGE_HTML,
)
from app.security_auth import (
    check_rate_limit, record_failed_attempt, clear_attempts,
    check_user_lockout, record_user_failed, clear_user_attempts,
    is_account_locked_db,
)
from app.security_users import must_reset_password_check
from app.database import get_pg_conn

router = APIRouter(tags=["auth"])


@router.get("/login-app", response_class=HTMLResponse)
def login_app_get(request: Request):
    if request.session.get("user"):
        return RedirectResponse("/chat")
    return HTMLResponse(LOGIN_PAGE_HTML.format(error_block=""))


@router.post("/login-app", response_class=HTMLResponse)
async def login_app_post(
    request: Request, username: str = Form(...), password: str = Form(...)
):
    ip = request.client.host if request.client else "unknown"
    username_clean = username.strip()

    # 1. Rate limit IP (anti-bot)
    allowed, msg_ip = check_rate_limit(ip)
    if not allowed:
        return HTMLResponse(LOGIN_PAGE_HTML.format(
            error_block=f'<div class="error">{msg_ip}</div>'
        ))

    # 2. Compte définitivement bloqué (DB)
    if is_account_locked_db(username_clean):
        return HTMLResponse(LOGIN_PAGE_HTML.format(
            error_block='<div class="error">Ce compte est bloqué. Contactez votre administrateur.</div>'
        ))

    # 3. Verrouillage temporaire en cours (mémoire)
    ok, msg_lock, permanent = check_user_lockout(username_clean)
    if not ok:
        return HTMLResponse(LOGIN_PAGE_HTML.format(
            error_block=f'<div class="error">{msg_lock}</div>'
        ))

    # 4. Authentification
    if authenticate(username_clean, password):
        clear_attempts(ip)
        clear_user_attempts(username_clean)
        update_last_login(username_clean)
        scope = get_user_scope(username_clean)
        tenant_id = get_tenant_id(username_clean)
        request.session["user"] = username_clean
        request.session["scope"] = scope
        request.session["tenant_id"] = tenant_id
        # Redéfinition MDP obligatoire ?
        if must_reset_password_check(username_clean):
            request.session["must_reset"] = True
            return RedirectResponse("/forced-reset", status_code=303)
        return RedirectResponse("/chat", status_code=303)

    # 5. Échec — enregistrer et appliquer le blocage progressif
    record_failed_attempt(ip)
    result = record_user_failed(username_clean, ip)

    if result.get("permanent"):
        error_msg = "Compte bloqué définitivement après trop de tentatives. Contactez votre administrateur."
    elif result.get("blocked"):
        mins = result.get("minutes", 5)
        error_msg = f"Trop d'échecs consécutifs. Compte verrouillé {mins} minute(s)."
    else:
        error_msg = "Identifiant ou mot de passe incorrect."

    return HTMLResponse(
        LOGIN_PAGE_HTML.format(error_block=f'<div class="error">{error_msg}</div>'),
        status_code=401,
    )


@router.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login-app")


@router.get("/chat", response_class=HTMLResponse)
def chat(request: Request):
    if not request.session.get("user"):
        return RedirectResponse("/login-app")
    username = request.session.get("user")
    # Vérification en base (si flag activé pendant la session)
    if must_reset_password_check(username):
        request.session["must_reset"] = True
        return RedirectResponse("/forced-reset")
    with open("app/templates/aria_chat.html", "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())


@router.get("/login")
def login_microsoft(request: Request, next: str = "/chat"):
    msal_app = build_msal_app()
    auth_url = msal_app.get_authorization_request_url(
        scopes=GRAPH_SCOPES, redirect_uri=REDIRECT_URI, state=next
    )
    return RedirectResponse(auth_url)


@router.get("/auth/callback")
def auth_callback(request: Request, code: str | None = None, state: str | None = None):
    if not code:
        return HTMLResponse("Code manquant", status_code=400)
    msal_app = build_msal_app()
    result = msal_app.acquire_token_by_authorization_code(
        code, scopes=GRAPH_SCOPES, redirect_uri=REDIRECT_URI
    )
    if "access_token" not in result:
        return HTMLResponse("Erreur d'authentification", status_code=400)
    request.session["access_token"] = result["access_token"]
    username = request.session.get("user", "guillaume")
    save_microsoft_token(
        username, result["access_token"],
        result.get("refresh_token", ""), result.get("expires_in", 3600),
    )
    return RedirectResponse(state or "/chat")


@router.get("/login/gmail")
def login_gmail():
    from app.connectors.gmail_connector import get_gmail_auth_url
    return RedirectResponse(get_gmail_auth_url())


@router.get("/auth/gmail/callback")
def auth_gmail_callback(request: Request, code: str | None = None):
    if not code:
        return HTMLResponse("Code manquant", status_code=400)
    from app.connectors.gmail_connector import exchange_code_for_tokens
    tokens = exchange_code_for_tokens(code)
    username = request.session.get("user", "guillaume")
    email = tokens.get("email", f"{username}@gmail.com")
    save_google_token(
        username=username,
        access_token=tokens.get("access_token", ""),
        refresh_token=tokens.get("refresh_token", ""),
        email=email,
    )
    return {"status": "ok", "message": f"Google connecté pour {username} ({email}) !"}
