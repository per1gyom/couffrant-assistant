import os
import time
import html as _html

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
from app.security_users import must_reset_password_check, resolve_username
from app.database import get_pg_conn
from app.logging_config import get_logger

logger = get_logger("raya.auth")

router = APIRouter(tags=["auth"])


def _save_ms_token_v2(username: str, oauth_result: dict):
    """Upsert le token Microsoft dans tenant_connections (V2)."""
    try:
        from app.connection_token_manager import save_connection_oauth_token
        from app.connections import list_connections
        from app.database import get_pg_conn
        from app.app_security import get_tenant_id
        from app.crypto import encrypt_token
        import json

        tenant_id = get_tenant_id(username)
        if not tenant_id:
            return

        # Récupérer l'email via Graph
        email = ""
        try:
            from app.graph_client import graph_get
            me = graph_get(oauth_result["access_token"], "/me",
                           params={"$select": "mail,userPrincipalName"})
            email = me.get("mail") or me.get("userPrincipalName") or ""
        except Exception:
            pass

        # Trouver ou créer la connexion Microsoft pour ce user
        conn = get_pg_conn(); c = conn.cursor()
        c.execute("""
            SELECT tc.id FROM tenant_connections tc
            JOIN connection_assignments ca ON ca.connection_id = tc.id
            WHERE tc.tenant_id = %s AND tc.tool_type = 'microsoft' AND ca.username = %s
            LIMIT 1
        """, (tenant_id, username))
        row = c.fetchone()
        if row:
            conn_id = row[0]
        else:
            label = email or f"Microsoft ({username})"
            c.execute("""
                INSERT INTO tenant_connections
                    (tenant_id, tool_type, label, auth_type, status, created_by)
                VALUES (%s, 'microsoft', %s, 'oauth', 'connected', 'oauth_callback')
                RETURNING id
            """, (tenant_id, label))
            conn_id = c.fetchone()[0]
            c.execute("""
                INSERT INTO connection_assignments (connection_id, username, access_level, enabled)
                VALUES (%s, %s, 'full', true)
                ON CONFLICT (connection_id, username) DO NOTHING
            """, (conn_id, username))
        conn.commit(); conn.close()

        save_connection_oauth_token(
            connection_id=conn_id,
            access_token=oauth_result["access_token"],
            refresh_token=oauth_result.get("refresh_token", ""),
            email=email,
            expires_in=oauth_result.get("expires_in", 3600),
        )
    except Exception as e:
        logger.warning("[Auth] _save_ms_token_v2 error: %s", e)


def _save_gmail_token_v2(username: str, tokens: dict, email: str):
    """Upsert le token Gmail dans tenant_connections (V2)."""
    try:
        from app.connection_token_manager import save_connection_oauth_token
        from app.database import get_pg_conn
        from app.app_security import get_tenant_id

        tenant_id = get_tenant_id(username)
        if not tenant_id:
            return

        conn = get_pg_conn(); c = conn.cursor()
        c.execute("""
            SELECT tc.id FROM tenant_connections tc
            JOIN connection_assignments ca ON ca.connection_id = tc.id
            WHERE tc.tenant_id = %s AND tc.tool_type = 'gmail' AND ca.username = %s
            LIMIT 1
        """, (tenant_id, username))
        row = c.fetchone()
        if row:
            conn_id = row[0]
        else:
            label = email or f"Gmail ({username})"
            c.execute("""
                INSERT INTO tenant_connections
                    (tenant_id, tool_type, label, auth_type, status, created_by)
                VALUES (%s, 'gmail', %s, 'oauth', 'connected', 'oauth_callback')
                RETURNING id
            """, (tenant_id, label))
            conn_id = c.fetchone()[0]
            c.execute("""
                INSERT INTO connection_assignments (connection_id, username, access_level, enabled)
                VALUES (%s, %s, 'full', true)
                ON CONFLICT (connection_id, username) DO NOTHING
            """, (conn_id, username))
        conn.commit(); conn.close()

        save_connection_oauth_token(
            connection_id=conn_id,
            access_token=tokens.get("access_token", ""),
            refresh_token=tokens.get("refresh_token", ""),
            email=email,
            expires_in=3600,
        )
    except Exception as e:
        logger.warning("[Auth] _save_gmail_token_v2 error: %s", e)


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
    login_input = username.strip()

    real_username = resolve_username(login_input) or login_input

    allowed, msg_ip = check_rate_limit(ip)
    if not allowed:
        return HTMLResponse(LOGIN_PAGE_HTML.format(
            error_block=f'<div class="error">{msg_ip}</div>'
        ))

    if is_account_locked_db(real_username):
        return HTMLResponse(LOGIN_PAGE_HTML.format(
            error_block='<div class="error">Ce compte est bloqué. Contactez votre administrateur.</div>'
        ))

    ok, msg_lock, permanent = check_user_lockout(real_username)
    if not ok:
        return HTMLResponse(LOGIN_PAGE_HTML.format(
            error_block=f'<div class="error">{msg_lock}</div>'
        ))

    if authenticate(login_input, password):
        clear_attempts(ip)
        clear_user_attempts(real_username)
        update_last_login(real_username)
        scope = get_user_scope(real_username)
        tenant_id = get_tenant_id(real_username)
        from app.suspension import check_suspension
        suspended, reason = check_suspension(real_username, tenant_id)
        if suspended:
            return HTMLResponse(LOGIN_PAGE_HTML.format(
                error_block=f'<div class="error">{reason}</div>'
            ))
        request.session["user"] = real_username
        request.session["scope"] = scope
        request.session["tenant_id"] = tenant_id
        request.session["last_activity"] = time.time()
        if must_reset_password_check(real_username):
            request.session["must_reset"] = True
            return RedirectResponse("/forced-reset", status_code=303)
        return RedirectResponse("/chat", status_code=303)

    record_failed_attempt(ip)
    result = record_user_failed(real_username, ip)

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
    tenant_id = request.session.get("tenant_id", "")
    from app.suspension import check_suspension
    suspended, reason = check_suspension(username, tenant_id)
    if suspended:
        request.session.clear()
        return HTMLResponse(
            LOGIN_PAGE_HTML.format(error_block=f'<div class="error">{reason}</div>'),
        )
    if must_reset_password_check(username):
        request.session["must_reset"] = True
        return RedirectResponse("/forced-reset")
    # Récupérer le nom d'affichage depuis la DB (display_name ou username capitalisé)
    display_name = username[0].upper() + username[1:] if username else username
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("SELECT display_name FROM users WHERE username=%s", (username,))
        row = c.fetchone()
        conn.close()
        if row and row[0] and row[0].strip():
            display_name = row[0].strip()
    except Exception:
        pass
    with open("app/templates/raya_chat.html", "r", encoding="utf-8") as f:
        content = f.read()
    safe_name = _html.escape(display_name)
    content = content.replace(
        'id="logoUserName"></span>',
        f'id="logoUserName">{safe_name}</span>'
    )
    return HTMLResponse(content=content)


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
    username = request.session.get("user")
    if not username:
        return HTMLResponse(
            "<h2>Session expirée</h2><p><a href='/login-app'>Se reconnecter</a></p>",
            status_code=401,
        )
    # Écrire dans tenant_connections (V2) + oauth_tokens (legacy fallback)
    _save_ms_token_v2(username, result)
    save_microsoft_token(
        username, result["access_token"],
        result.get("refresh_token", ""), result.get("expires_in", 3600),
    )
    return RedirectResponse(state or "/chat")


# ─── GMAIL OAuth2 ───

@router.get("/login/gmail")
def login_gmail(request: Request):
    gmail_redirect = os.getenv("GMAIL_REDIRECT_URI", "").strip()
    if not gmail_redirect:
        return HTMLResponse(
            "<h2>Erreur configuration Gmail</h2>"
            "<p>La variable <code>GMAIL_REDIRECT_URI</code> n'est pas configurée sur Railway.</p>"
            "<p><a href='/chat'>\u2190 Retour au chat</a></p>",
            status_code=500,
        )
    from app.connectors.gmail_connector import get_gmail_auth_url, is_configured
    if not is_configured():
        return HTMLResponse(
            "<h2>Erreur configuration Gmail</h2>"
            "<p>GMAIL_CLIENT_ID / GMAIL_CLIENT_SECRET manquants dans Railway.</p>"
            "<p><a href='/chat'>\u2190 Retour au chat</a></p>",
            status_code=500,
        )
    try:
        auth_url = get_gmail_auth_url()
        return RedirectResponse(auth_url)
    except Exception as e:
        return HTMLResponse(
            f"<h2>Erreur Gmail</h2><p>{e}</p><p><a href='/chat'>\u2190 Retour</a></p>",
            status_code=500,
        )


@router.get("/auth/gmail/callback")
def auth_gmail_callback(request: Request, code: str | None = None, error: str | None = None):
    if error:
        conn_id = request.session.get("oauth_conn_id")
        if conn_id:
            return RedirectResponse(f"/admin/panel?oauth_err=gmail:{error}&view=companies")
        return RedirectResponse(f"/chat?gmail_error={error}")
    if not code:
        return HTMLResponse("Code OAuth manquant", status_code=400)
    from app.connectors.gmail_connector import exchange_code_for_tokens
    username = request.session.get("user")
    if not username:
        return HTMLResponse(
            "<h2>Session expirée</h2><p><a href='/login-app'>Se reconnecter</a></p>",
            status_code=401,
        )
    try:
        tokens = exchange_code_for_tokens(code)
    except Exception as e:
        return HTMLResponse(
            f"<h2>Erreur connexion Gmail</h2><p>{e}</p><p><a href='/chat'>\u2190 Retour</a></p>",
            status_code=500,
        )
    email = tokens.get("email", "")

    # Flux admin : sauvegarder dans tenant_connections
    conn_id = request.session.pop("oauth_conn_id", None)
    tenant_id = request.session.pop("oauth_conn_tenant", None)
    if conn_id:
        from app.connection_token_manager import save_connection_oauth_token
        save_connection_oauth_token(
            connection_id=conn_id,
            access_token=tokens.get("access_token", ""),
            refresh_token=tokens.get("refresh_token", ""),
            email=email,
            expires_in=3600,
        )
        logger.info(f"[Gmail/Admin] Connexion #{conn_id} sauvegardée pour {email} (tenant={tenant_id})")
        return RedirectResponse(f"/admin/panel?oauth_ok=1&email={email}&view=companies")

    # Flux per-user : sauvegarder en V2 (tenant_connections) + legacy (oauth_tokens)
    _save_gmail_token_v2(username, tokens, email)
    try:
        save_google_token(
            username=username,
            access_token=tokens.get("access_token", ""),
            refresh_token=tokens.get("refresh_token", ""),
            email=email or f"{username}@gmail.com",
        )
    except Exception as e:
        logger.error(f"[Gmail] Erreur sauvegarde legacy {username}: {e}")
    return RedirectResponse("/chat?gmail_connected=1")
