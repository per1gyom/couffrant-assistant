from fastapi import APIRouter, Request, Form
from fastapi.responses import RedirectResponse, HTMLResponse
from app.auth import build_msal_app
from app.config import GRAPH_SCOPES, REDIRECT_URI
from app.token_manager import save_microsoft_token
from app.app_security import (
    authenticate, update_last_login, check_rate_limit,
    record_failed_attempt, clear_attempts, get_user_scope,
    LOGIN_PAGE_HTML,
)
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
    allowed, message = check_rate_limit(ip)
    if not allowed:
        return HTMLResponse(LOGIN_PAGE_HTML.format(error_block=f'<div class="error">{message}</div>'))
    if authenticate(username.strip(), password):
        clear_attempts(ip)
        update_last_login(username.strip())
        scope = get_user_scope(username.strip())
        request.session["user"] = username.strip()
        request.session["scope"] = scope
        return RedirectResponse("/chat", status_code=303)
    record_failed_attempt(ip)
    return HTMLResponse(
        LOGIN_PAGE_HTML.format(
            error_block='<div class="error">Identifiant ou mot de passe incorrect.</div>'
        ),
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
        username,
        result["access_token"],
        result.get("refresh_token", ""),
        result.get("expires_in", 3600),
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
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("DELETE FROM gmail_tokens WHERE email=%s", ("per1.guillaume@gmail.com",))
        c.execute(
            "INSERT INTO gmail_tokens (email,access_token,refresh_token) VALUES (%s,%s,%s)",
            ("per1.guillaume@gmail.com", tokens.get("access_token"), tokens.get("refresh_token")),
        )
        conn.commit()
    finally:
        if conn: conn.close()
    return {"status": "ok", "message": "Gmail connecté !"}
