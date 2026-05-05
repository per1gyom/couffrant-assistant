"""
Routes OAuth super admin pour connecter un compte Microsoft/Gmail
à une tenant_connection. Accessible uniquement par le super admin.

/admin/connections/{tenant_id}/oauth/{tool_type}/start
  → Lance le flux OAuth, stocke (tenant_id, connection_id) en session
  → Crée la connexion dans tenant_connections si elle n'existe pas
/auth/connection/microsoft/callback  → Callback Microsoft
/auth/connection/gmail/callback      → Callback Gmail
"""
import os
from fastapi import APIRouter, Request, Depends, HTTPException, Body
from fastapi.responses import RedirectResponse, HTMLResponse
from app.routes.deps import require_admin
from app.connections import create_connection, update_connection
from app.connection_token_manager import save_connection_oauth_token
from app.logging_config import get_logger

logger = get_logger("raya.admin_oauth")
router = APIRouter(tags=["admin_oauth"])

_RETURN_URL = os.getenv("APP_BASE_URL", "https://app.raya-ia.fr").rstrip("/")


def _ensure_assignment_for_admin(connection_id: int, request: Request):
    """Cree un assignment dans connection_assignments pour l admin qui
    vient de connecter une boite via OAuth.

    Fix 05/05/2026 : sans cet assignment, get_all_user_connections() ne
    retourne pas la connexion (filtre WHERE ca.enabled=true) et tous les
    jobs V2 par-connexion ne la voient pas. Bug observe sur la
    reconnexion contact@ le 05/05 (conn#14 invisible jusqu a creation
    manuelle de l assignment).

    Idempotent : si un assignment existe deja, ON CONFLICT DO NOTHING.
    Niveau par defaut 'read_only' (le super_admin pourra ensuite l elever
    via le panel de permissions a 'full' ou autre selon besoin).
    """
    try:
        from app.database import get_pg_conn
        admin_session = getattr(request, "session", {})
        username = admin_session.get("username") if admin_session else None
        if not username:
            logger.warning(
                "[AdminOAuth] Pas d username en session, "
                "assignment connexion #%s skipped",
                connection_id,
            )
            return
        # Recupere le tenant_id de la connexion (pour cohérence cross-tenant)
        with get_pg_conn() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT tenant_id FROM tenant_connections WHERE id = %s",
                (connection_id,),
            )
            row = cur.fetchone()
            if not row:
                logger.warning(
                    "[AdminOAuth] Connexion #%s introuvable, "
                    "assignment skipped", connection_id,
                )
                return
            tenant_id = row[0]
            cur.execute(
                """INSERT INTO connection_assignments
                   (connection_id, username, access_level, enabled, tenant_id)
                   VALUES (%s, %s, 'read_only', true, %s)
                   ON CONFLICT (connection_id, username) DO UPDATE
                   SET enabled = true""",
                (connection_id, username, tenant_id),
            )
            conn.commit()
        logger.info(
            "[AdminOAuth] Assignment cree/active : conn#%s -> %s (tenant %s)",
            connection_id, username, tenant_id,
        )
    except Exception as e:
        logger.warning(
            "[AdminOAuth] Echec creation assignment conn#%s : %s",
            connection_id, str(e)[:200],
        )


# ─── DÉMARRAGE DU FLUX OAUTH ────────────────────────────────────────

@router.get("/admin/connections/{tenant_id}/oauth/microsoft/start")
def admin_oauth_microsoft_start(
    request: Request,
    tenant_id: str,
    connection_id: int = None,
    label: str = "Boîte Outlook",
    admin: dict = Depends(require_admin),
):
    """
    Lance le flux OAuth Microsoft pour connecter une boîte Outlook.
    connection_id : connexion existante à mettre à jour (optionnel, sinon crée).
    """
    if not connection_id:
        result = create_connection(
            tenant_id=tenant_id, tool_type="microsoft",
            label=label, auth_type="oauth",
            created_by=admin["username"],
        )
        if result.get("status") != "ok":
            return HTMLResponse(f"<h2>Erreur création connexion</h2><p>{result['message']}</p>", 500)
        connection_id = result["connection_id"]

    # Stocker l'état OAuth en session
    request.session["oauth_conn_tenant"] = tenant_id
    request.session["oauth_conn_id"] = connection_id

    from app.auth import build_msal_app
    from app.config import GRAPH_SCOPES
    redirect_uri = f"{_RETURN_URL}/auth/connection/microsoft/callback"
    msal_app = build_msal_app()
    # prompt="select_account" force l ecran de choix de compte Microsoft.
    # Sans ce parametre, Microsoft reutilise silencieusement la session SSO
    # active dans le navigateur (cookie de l admin) et stocke un token
    # pointant vers la mauvaise boite. Bug constate le 28/04 sur la
    # tentative de connexion contact@couffrant-solar.fr (la boite Guillaume
    # etait deja loggee, le flow a abouti silencieusement avec son token).
    auth_url = msal_app.get_authorization_request_url(
        scopes=GRAPH_SCOPES,
        redirect_uri=redirect_uri,
        state=str(connection_id),
        prompt="select_account",
    )
    return RedirectResponse(auth_url)


@router.get("/admin/connections/{tenant_id}/oauth/gmail/start")
def admin_oauth_gmail_start(
    request: Request,
    tenant_id: str,
    connection_id: int = None,
    label: str = "Boîte Gmail",
    admin: dict = Depends(require_admin),
):
    """Lance le flux OAuth Gmail pour connecter une boîte Gmail à un tenant."""
    from app.connectors.gmail_auth import is_configured, GMAIL_CLIENT_ID, GMAIL_SCOPES
    import urllib.parse
    if not is_configured():
        return HTMLResponse(
            "<h2>Gmail non configuré</h2>"
            "<p>GMAIL_CLIENT_ID / GMAIL_CLIENT_SECRET manquants dans Railway.</p>", 500
        )
    if not connection_id:
        result = create_connection(
            tenant_id=tenant_id, tool_type="gmail",
            label=label, auth_type="oauth",
            created_by=admin["username"],
        )
        if result.get("status") != "ok":
            return HTMLResponse(f"<h2>Erreur création connexion</h2><p>{result['message']}</p>", 500)
        connection_id = result["connection_id"]

    # Stocker le flag admin en session — le callback /auth/gmail/callback le détectera
    request.session["oauth_conn_tenant"] = tenant_id
    request.session["oauth_conn_id"] = connection_id

    # Utiliser le MÊME redirect_uri que le flux per-user (déjà enregistré dans Google Cloud Console)
    gmail_redirect = os.getenv("GMAIL_REDIRECT_URI", "").strip()
    if not gmail_redirect:
        return HTMLResponse("<h2>GMAIL_REDIRECT_URI manquant dans Railway</h2>", 500)

    params = {
        "client_id": GMAIL_CLIENT_ID,
        "redirect_uri": gmail_redirect,
        "response_type": "code",
        "scope": " ".join(GMAIL_SCOPES),
        "access_type": "offline",
        "prompt": "consent",
        "state": str(connection_id),
    }
    auth_url = "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode(params)
    return RedirectResponse(auth_url)


# ─── CALLBACKS OAUTH ────────────────────────────────────────────────

@router.get("/auth/connection/microsoft/callback")
def auth_connection_ms_callback(
    request: Request,
    code: str = None,
    state: str = None,
    error: str = None,
):
    """Callback Microsoft pour une connexion tenant."""
    if error:
        return HTMLResponse(f"<h2>Erreur OAuth Microsoft</h2><p>{error}</p>"
                            "<p><a href='/admin/panel?view=companies'>← Retour panel</a></p>", 400)
    if not code:
        return HTMLResponse("<h2>Code OAuth manquant</h2>", 400)

    conn_id = request.session.pop("oauth_conn_id", None)
    tenant_id = request.session.pop("oauth_conn_tenant", None)
    if not conn_id:
        return HTMLResponse("<h2>Session expirée</h2><p>Relancez la connexion.</p>", 401)

    from app.auth import build_msal_app
    from app.config import GRAPH_SCOPES
    redirect_uri = f"{_RETURN_URL}/auth/connection/microsoft/callback"
    msal_app = build_msal_app()
    result = msal_app.acquire_token_by_authorization_code(
        code, scopes=GRAPH_SCOPES, redirect_uri=redirect_uri
    )
    if "access_token" not in result:
        return HTMLResponse(f"<h2>Erreur token Microsoft</h2><p>{result}</p>", 400)

    # Récupérer l'email depuis Graph /me
    email = ""
    try:
        from app.graph_client import graph_get
        me = graph_get(result["access_token"], "/me", params={"$select": "mail,userPrincipalName"})
        email = me.get("mail") or me.get("userPrincipalName") or ""
    except Exception as e:
        logger.warning("[AdminOAuth] Graph /me error: %s", e)

    save_connection_oauth_token(
        connection_id=conn_id,
        access_token=result["access_token"],
        refresh_token=result.get("refresh_token", ""),
        email=email,
        expires_in=result.get("expires_in", 3600),
    )
    # Fix 05/05/2026 : auto-assigner la nouvelle connexion a l admin
    # qui vient de la connecter. Sans cet assignment, get_all_user_connections
    # ne retourne pas la connexion (filtre WHERE ca.enabled=true) et donc
    # tous les jobs V2 par-connexion (bootstrap, delta-sync, inventaire,
    # reconciliation) ne la voient pas. Bug observe le 05/05 sur la
    # reconnexion contact@ : conn#14 creee mais sans assignment, inventaire
    # plantait silencieusement.
    _ensure_assignment_for_admin(conn_id, request)
    logger.info("[AdminOAuth] Microsoft connected: conn#%s email=%s tenant=%s", conn_id, email, tenant_id)
    return RedirectResponse(f"/admin/panel?oauth_ok=1&email={email}&view=companies")


@router.get("/auth/connection/gmail/callback")
def auth_connection_gmail_callback(
    request: Request,
    code: str = None,
    state: str = None,
    error: str = None,
):
    """Callback Gmail pour une connexion tenant."""
    if error:
        return RedirectResponse(f"/admin/panel?oauth_err=gmail:{error}&view=companies")
    if not code:
        return HTMLResponse("<h2>Code OAuth manquant</h2>", 400)

    conn_id = request.session.pop("oauth_conn_id", None)
    tenant_id = request.session.pop("oauth_conn_tenant", None)
    if not conn_id:
        return HTMLResponse("<h2>Session expirée</h2><p>Relancez la connexion.</p>", 401)

    from app.connectors.gmail_auth import exchange_code_for_tokens
    try:
        tokens = exchange_code_for_tokens(code)
    except Exception as e:
        return HTMLResponse(f"<h2>Erreur Gmail</h2><p>{e}</p>", 500)

    save_connection_oauth_token(
        connection_id=conn_id,
        access_token=tokens.get("access_token", ""),
        refresh_token=tokens.get("refresh_token", ""),
        email=tokens.get("email", ""),
        expires_in=3600,
    )
    # Fix 05/05/2026 : meme auto-assignment que pour Microsoft callback.
    _ensure_assignment_for_admin(conn_id, request)
    email = tokens.get("email", "")
    logger.info("[AdminOAuth] Gmail connected: conn#%s email=%s tenant=%s", conn_id, email, tenant_id)
    return RedirectResponse(f"/admin/panel?oauth_ok=1&email={email}&view=companies")
