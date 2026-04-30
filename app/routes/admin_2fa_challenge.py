"""
Endpoints du challenge 2FA pour acces aux panels admin.

Workflow :
1. User authentifie (password OK) clique sur Admin/Super Admin
2. require_admin_with_2fa() detecte que la 2FA admin est expiree (>7j)
3. Sauve l URL d origine dans request.session["pending_admin_path"]
4. Redirige vers GET /admin/2fa-challenge
5. User saisit son code 6 chiffres (ou code recovery si super_admin)
6. POST /admin/2fa-challenge verifie -> mark_admin_2fa_validated()
7. Redirection vers l URL d origine

Si le user n a pas encore active sa 2FA et grace expiree -> redirige vers
/admin/2fa/setup pour qu il l active.
"""
import time
from typing import Optional

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.admin_2fa_session import (
    has_user_activated_2fa,
    is_user_in_grace_period,
    mark_admin_2fa_validated,
    must_setup_2fa_now,
    SCOPES_REQUIRING_2FA,
)
from app.auth_events import log_auth_event
from app.database import get_pg_conn
from app.logging_config import get_logger
from app.routes.deps import require_admin
from app.totp import (
    consume_recovery_code,
    decrypt_totp_secret,
    verify_totp_code,
)

logger = get_logger("raya.admin_2fa_challenge")

router = APIRouter(tags=["auth", "2fa"])


def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
    if fwd:
        return fwd
    return request.client.host if request.client else "unknown"


def _user_agent(request: Request) -> str:
    return (request.headers.get("user-agent") or "")[:512]


def _fetch_user_2fa_data(username: str, tenant_id: str) -> Optional[dict]:
    """Lit le secret chiffre + recovery hashes du user."""
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute(
            """
            SELECT totp_secret_encrypted, recovery_codes_hashes
            FROM users
            WHERE username = %s AND tenant_id = %s AND deleted_at IS NULL
            """,
            (username, tenant_id),
        )
        row = c.fetchone()
        if not row:
            return None
        return {
            "secret_encrypted": row[0],
            "recovery_hashes": row[1] or [],
        }
    except Exception as e:
        logger.error("[2FA Challenge] _fetch_user_2fa_data error: %s", str(e)[:200])
        return None
    finally:
        if conn:
            conn.close()


def _save_remaining_recovery_codes(username: str, tenant_id: str, remaining: list) -> bool:
    """Persiste la liste des hashes recovery restants apres consommation."""
    conn = None
    try:
        import json
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute(
            """
            UPDATE users
            SET recovery_codes_hashes = %s::jsonb,
                recovery_codes_used_count = COALESCE(recovery_codes_used_count, 0) + 1
            WHERE username = %s AND tenant_id = %s
            """,
            (json.dumps(remaining), username, tenant_id),
        )
        conn.commit()
        return c.rowcount == 1
    except Exception as e:
        logger.error("[2FA Challenge] _save_remaining_recovery_codes error: %s", str(e)[:200])
        try:
            if conn:
                conn.rollback()
        except Exception:
            pass
        return False
    finally:
        if conn:
            conn.close()


# ============================================================================
# PAGE HTML — page sobre identique au design login
# ============================================================================

CHALLENGE_PAGE_HTML = """<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="UTF-8">
  <title>Verification 2FA — Raya</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500&family=IBM+Plex+Sans:wght@400;500;600&display=swap" rel="stylesheet">
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body {
      background: #0e0e12; color: #e0e0e0;
      font-family: 'IBM Plex Sans', sans-serif;
      display: flex; align-items: center; justify-content: center;
      min-height: 100vh; padding: 20px;
    }
    .card {
      background: #16161d; border: 1px solid #2a2a35;
      border-radius: 16px; padding: 36px;
      max-width: 420px; width: 100%;
    }
    .logo { font-size: 24px; font-weight: 600; color: #6366f1; margin-bottom: 4px; }
    .sub { font-size: 12px; color: #888; margin-bottom: 24px; font-family: 'JetBrains Mono', monospace; }
    h2 { font-size: 18px; margin-bottom: 8px; color: #fff; }
    .info {
      background: rgba(99, 102, 241, 0.1);
      border-left: 3px solid #6366f1;
      padding: 10px 14px; border-radius: 6px;
      font-size: 13px; color: #c0c0d0; margin-bottom: 20px;
      line-height: 1.5;
    }
    label { display: block; font-size: 12px; color: #aaa; margin-bottom: 6px; }
    input[type=text] {
      width: 100%; padding: 14px;
      background: #1e1e28; border: 1px solid #2a2a35;
      border-radius: 8px; color: #fff;
      font-size: 22px; font-family: 'JetBrains Mono', monospace;
      letter-spacing: 0.3em; text-align: center;
      margin-bottom: 16px;
    }
    input[type=text]:focus { outline: none; border-color: #6366f1; }
    button {
      width: 100%; padding: 12px;
      background: #6366f1; color: #fff; border: none;
      border-radius: 8px; font-size: 14px; font-weight: 600;
      cursor: pointer;
    }
    button:hover { background: #4f46e5; }
    .error {
      color: #ef4444; font-size: 12px; margin-bottom: 12px;
      font-family: 'JetBrains Mono', monospace;
      padding: 10px; background: rgba(239, 68, 68, 0.1);
      border-radius: 6px; border-left: 3px solid #ef4444;
    }
    .hint {
      margin-top: 16px; font-size: 11px;
      color: #888; line-height: 1.6;
    }
    .hint code {
      background: #1e1e28; padding: 2px 6px;
      border-radius: 4px; color: #aaa;
    }
    .links { margin-top: 20px; text-align: center; }
    .links a {
      color: #888; font-size: 12px; text-decoration: none; margin: 0 8px;
    }
    .links a:hover { color: #fff; }
  </style>
</head>
<body>
  <div class="card">
    <div class="logo">⚡ Raya</div>
    <div class="sub">Verification 2FA — acces administrateur</div>

    <div class="info">
      🔐 Pour acceder au panel administration, ouvrez votre application
      d authentification (Microsoft Authenticator, Google Authenticator...)
      et saisissez le code a 6 chiffres affiche.
    </div>

    __ERROR_BLOCK__

    <form method="POST" action="/admin/2fa-challenge">
      <label>Code de verification</label>
      <input type="text" name="code"
             placeholder="000000"
             autofocus required
             autocomplete="one-time-code"
             inputmode="numeric"
             maxlength="13">
      <button type="submit">Valider</button>
    </form>

    __RECOVERY_HINT__

    <div class="links">
      <a href="/chat">&#8592; Retour au chat</a>
      <a href="/logout">Deconnexion</a>
    </div>
  </div>
</body>
</html>"""

RECOVERY_HINT_HTML = """
    <div class="hint">
      💡 Vous avez perdu votre application ?<br>
      Saisissez l un de vos codes de recuperation <code>XXXXX-XXXXX</code>
      a la place du code TOTP.
    </div>"""


# ============================================================================
# GET /admin/2fa-challenge
# ============================================================================

@router.get("/admin/2fa-challenge", response_class=HTMLResponse)
def get_2fa_challenge(request: Request):
    """Affiche la page de saisie du code 2FA.

    Pre-condition : user authentifie + scope admin (sinon redirect login).
    """
    username = request.session.get("user")
    if not username:
        return RedirectResponse("/login-app", status_code=303)
    scope = request.session.get("scope", "")
    if scope not in SCOPES_REQUIRING_2FA:
        return RedirectResponse("/chat", status_code=303)

    # Si l user n a pas active sa 2FA, on le redirige vers le setup
    if not has_user_activated_2fa(username):
        if is_user_in_grace_period(username):
            # Grace active : laisser passer et afficher warning dans la page setup
            return RedirectResponse("/admin/2fa/setup", status_code=303)
        else:
            # Grace expiree : forcer l activation
            return RedirectResponse(
                "/admin/2fa/setup?required=1", status_code=303
            )

    # Le super_admin a acces aux codes recovery, les autres non
    show_recovery_hint = scope == "super_admin"
    recovery_block = RECOVERY_HINT_HTML if show_recovery_hint else ""

    return HTMLResponse(
        CHALLENGE_PAGE_HTML
        .replace("__ERROR_BLOCK__", "")
        .replace("__RECOVERY_HINT__", recovery_block)
    )


# ============================================================================
# POST /admin/2fa-challenge
# ============================================================================

@router.post("/admin/2fa-challenge", response_class=HTMLResponse)
def post_2fa_challenge(request: Request, code: str = Form(...)):
    """Verifie le code TOTP ou recovery saisi par l user.

    En cas de succes : pose request.session["admin_2fa_validated_at"] et
    redirige vers l URL sauvegardee dans pending_admin_path (ou /admin/panel).
    En cas d echec : reaffiche la page avec un message d erreur.
    """
    username = request.session.get("user")
    if not username:
        return RedirectResponse("/login-app", status_code=303)

    scope = request.session.get("scope", "")
    tenant_id = request.session.get("tenant_id", "")
    show_recovery_hint = scope == "super_admin"
    recovery_block = RECOVERY_HINT_HTML if show_recovery_hint else ""

    if scope not in SCOPES_REQUIRING_2FA:
        return RedirectResponse("/chat", status_code=303)

    code_clean = (code or "").strip()
    if not code_clean:
        return HTMLResponse(
            CHALLENGE_PAGE_HTML
            .replace("__ERROR_BLOCK__", '<div class="error">Code requis.</div>')
            .replace("__RECOVERY_HINT__", recovery_block)
        )

    # Charger les donnees 2FA du user
    data = _fetch_user_2fa_data(username, tenant_id)
    if not data or not data["secret_encrypted"]:
        # 2FA pas encore activee, on le redirige vers le setup
        return RedirectResponse("/admin/2fa/setup?required=1", status_code=303)

    # Detection auto : code TOTP (6 chiffres) ou code recovery (XXXXX-XXXXX)
    is_recovery = "-" in code_clean or len(code_clean.replace(" ", "")) > 6
    is_totp = code_clean.replace(" ", "").isdigit() and len(code_clean.replace(" ", "")) == 6

    success = False
    method_used = None

    if is_totp:
        # Verification code TOTP
        try:
            secret = decrypt_totp_secret(data["secret_encrypted"])
            if verify_totp_code(secret, code_clean):
                success = True
                method_used = "totp"
        except RuntimeError as e:
            logger.error("[2FA Challenge] Echec dechiffrement: %s", e)
            return HTMLResponse(
                CHALLENGE_PAGE_HTML
                .replace("__ERROR_BLOCK__", '<div class="error">Erreur de configuration serveur. Contactez le support.</div>')
                .replace("__RECOVERY_HINT__", recovery_block),
                status_code=500,
            )
        except Exception as e:
            logger.error("[2FA Challenge] verify_totp_code error: %s", str(e)[:200])

    elif is_recovery and scope == "super_admin":
        # Verification code de recuperation (super_admin uniquement)
        recovery_hashes = data["recovery_hashes"]
        matched, remaining = consume_recovery_code(code_clean, recovery_hashes)
        if matched:
            saved = _save_remaining_recovery_codes(username, tenant_id, remaining)
            if saved:
                success = True
                method_used = "recovery"
                logger.info(
                    "[2FA Challenge] Recovery code consomme par %s. Restants: %d",
                    username, len(remaining),
                )

    # Logging + retour
    if success:
        mark_admin_2fa_validated(request)
        log_auth_event(
            username=username,
            tenant_id=tenant_id,
            event_type="2fa_success" if method_used == "totp" else "recovery_code_used",
            ip=_client_ip(request),
            user_agent=_user_agent(request),
            metadata={"context": "admin_access", "method": method_used},
        )
        # Restaure l URL d origine sauvegardee, ou /admin/panel par defaut
        next_url = request.session.pop("pending_admin_path", None) or "/admin/panel"
        return RedirectResponse(next_url, status_code=303)

    # Echec
    log_auth_event(
        username=username,
        tenant_id=tenant_id,
        event_type="2fa_failure",
        ip=_client_ip(request),
        user_agent=_user_agent(request),
        metadata={"context": "admin_access"},
    )
    return HTMLResponse(
        CHALLENGE_PAGE_HTML
        .replace("__ERROR_BLOCK__", '<div class="error">Code invalide. Reessayez.</div>')
        .replace("__RECOVERY_HINT__", recovery_block),
        status_code=401,
    )
