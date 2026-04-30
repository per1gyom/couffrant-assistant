"""
Endpoints du PIN admin (LOT 5 du chantier 2FA).

Endpoints :
  GET  /admin/pin/status             (require_admin) - etat du PIN
  POST /admin/pin/setup              (require_admin) - configurer / changer PIN
  GET  /admin/pin-challenge          (auth) - page saisie PIN avant entree panel
  POST /admin/pin-challenge          (auth) - valider PIN
  POST /admin/pin/unlock-via-2fa     (auth) - debloquer apres 3 echecs en validant 2FA

Workflow :
1. User entre dans /admin/panel
2. require_admin_with_pin() detecte que le PIN n est pas valide en session
3. Redirect vers /admin/pin-challenge (PIN demande)
4. User saisit PIN -> valide -> mark_pin_validated() -> redirect panel
5. Apres 3 echecs : PIN bloque -> page propose de valider 2FA pour debloquer
"""
import time
from typing import Optional

from fastapi import APIRouter, Body, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from app.admin_pin import (
    clear_pin_lockout,
    clear_pin_session,
    fetch_pin_state,
    has_pin_set,
    is_pin_locked,
    is_pin_validated_in_session,
    mark_pin_validated,
    set_pin,
    validate_pin_format,
    verify_pin,
    PIN_MAX_ATTEMPTS,
    PIN_MIN_LENGTH,
    PIN_MAX_LENGTH,
)
from app.admin_2fa_session import (
    SCOPES_REQUIRING_2FA,
    has_user_activated_2fa,
)
from app.auth_events import log_auth_event
from app.logging_config import get_logger
from app.routes.deps import require_admin
from app.totp import decrypt_totp_secret, verify_totp_code

logger = get_logger("raya.admin_pin_routes")

router = APIRouter(tags=["auth", "pin"])


def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
    if fwd:
        return fwd
    return request.client.host if request.client else "unknown"


def _user_agent(request: Request) -> str:
    return (request.headers.get("user-agent") or "")[:512]


# ─── PIN STATUS ────────────────────────────────────────────────────────


@router.get("/admin/pin/status")
def get_pin_status(
    request: Request,
    user: dict = Depends(require_admin),
):
    """Renvoie l etat du PIN admin du user courant."""
    state = fetch_pin_state(user["username"])
    if not state:
        raise HTTPException(404, "Utilisateur introuvable")
    locked, seconds = is_pin_locked(user["username"])
    return {
        "configured": bool(state["pin_hash"]),
        "set_at": state["set_at"].isoformat() if state["set_at"] else None,
        "attempts": state["attempts"],
        "max_attempts": PIN_MAX_ATTEMPTS,
        "locked": locked,
        "lockout_seconds_remaining": seconds,
        "validated_in_session": is_pin_validated_in_session(request),
    }


# ─── PIN SETUP ─────────────────────────────────────────────────────────


@router.post("/admin/pin/setup")
def setup_pin(
    request: Request,
    payload: dict = Body(...),
    user: dict = Depends(require_admin),
):
    """Configure ou change le PIN admin.

    Pre-condition : la 2FA Authenticator doit etre activee au prealable.
    Body JSON : {pin: '123456'}
    """
    if not has_user_activated_2fa(user["username"]):
        raise HTTPException(
            400,
            "Activez d abord votre 2FA Authenticator avant de configurer un PIN.",
        )

    pin = (payload.get("pin") or "").strip()
    valid, err = validate_pin_format(pin)
    if not valid:
        raise HTTPException(400, err)

    success, error_msg = set_pin(user["username"], pin)
    if not success:
        raise HTTPException(500, error_msg)

    log_auth_event(
        username=user["username"],
        tenant_id=user["tenant_id"],
        event_type="pin_configured",
        ip=_client_ip(request),
        user_agent=_user_agent(request),
    )
    # Marquer PIN valide pour la session courante (l user vient de le poser)
    mark_pin_validated(request)
    return {
        "success": True,
        "message": "PIN configure. Il sera demande a chaque entree dans le panel admin.",
    }


# ─── PAGE HTML CHALLENGE ───────────────────────────────────────────────

CHALLENGE_PIN_HTML = """<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="UTF-8">
  <title>Code PIN — Raya</title>
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
    .info {
      background: rgba(99, 102, 241, 0.1);
      border-left: 3px solid #6366f1;
      padding: 10px 14px; border-radius: 6px;
      font-size: 13px; color: #c0c0d0; margin-bottom: 20px;
      line-height: 1.5;
    }
    label { display: block; font-size: 12px; color: #aaa; margin-bottom: 6px; }
    input[type=password] {
      width: 100%; padding: 14px;
      background: #1e1e28; border: 1px solid #2a2a35;
      border-radius: 8px; color: #fff;
      font-size: 28px; font-family: 'JetBrains Mono', monospace;
      letter-spacing: 0.5em; text-align: center;
      margin-bottom: 16px;
    }
    input[type=password]:focus { outline: none; border-color: #6366f1; }
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
    .links { margin-top: 20px; text-align: center; }
    .links a {
      color: #888; font-size: 12px; text-decoration: none; margin: 0 8px;
    }
    .links a:hover { color: #fff; }
    .locked-block {
      background: rgba(239, 68, 68, 0.1);
      border: 1px solid rgba(239, 68, 68, 0.3);
      padding: 14px; border-radius: 8px; margin-bottom: 16px;
    }
  </style>
</head>
<body>
  <div class="card">
    <div class="logo">⚡ Raya</div>
    <div class="sub">Acces panel admin — saisie PIN</div>

    <div class="info">
      🔒 Pour acceder au panel, saisissez votre PIN a __PIN_LENGTH__ chiffres.
      __EXTRA_INFO__
    </div>

    __ERROR_BLOCK__

    <form method="POST" action="/admin/pin-challenge">
      <label>Code PIN</label>
      <input type="password" name="pin"
             placeholder="••••"
             autofocus required
             autocomplete="off"
             inputmode="numeric"
             pattern="\\d*"
             minlength="__MIN_LEN__"
             maxlength="__MAX_LEN__">
      <button type="submit">Valider</button>
    </form>

    <div class="links">
      <a href="/chat">&#8592; Retour au chat</a>
      <a href="/logout">Deconnexion</a>
    </div>
  </div>
</body>
</html>"""


CHALLENGE_LOCKED_HTML = """<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="UTF-8">
  <title>PIN bloque — Raya</title>
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
      background: #16161d; border: 1px solid #ef4444;
      border-radius: 16px; padding: 36px;
      max-width: 420px; width: 100%;
    }
    .logo { font-size: 24px; font-weight: 600; color: #ef4444; margin-bottom: 4px; }
    .sub { font-size: 12px; color: #888; margin-bottom: 24px; font-family: 'JetBrains Mono', monospace; }
    .info {
      background: rgba(239, 68, 68, 0.1);
      border-left: 3px solid #ef4444;
      padding: 12px 14px; border-radius: 6px;
      font-size: 13px; color: #ffd0d0; margin-bottom: 20px;
      line-height: 1.5;
    }
    label { display: block; font-size: 12px; color: #aaa; margin-bottom: 6px; margin-top: 12px; }
    input[type=text], input[type=password] {
      width: 100%; padding: 14px;
      background: #1e1e28; border: 1px solid #2a2a35;
      border-radius: 8px; color: #fff;
      font-size: 22px; font-family: 'JetBrains Mono', monospace;
      letter-spacing: 0.3em; text-align: center;
      margin-bottom: 8px;
    }
    button {
      width: 100%; padding: 12px;
      background: #6366f1; color: #fff; border: none;
      border-radius: 8px; font-size: 14px; font-weight: 600;
      cursor: pointer; margin-top: 12px;
    }
    button:hover { background: #4f46e5; }
    .error {
      color: #ef4444; font-size: 12px; margin-bottom: 12px;
      font-family: 'JetBrains Mono', monospace;
      padding: 10px; background: rgba(239, 68, 68, 0.1);
      border-radius: 6px; border-left: 3px solid #ef4444;
    }
    .links { margin-top: 20px; text-align: center; }
    .links a { color: #888; font-size: 12px; text-decoration: none; margin: 0 8px; }
  </style>
</head>
<body>
  <div class="card">
    <div class="logo">🔐 PIN bloque</div>
    <div class="sub">Trop d essais incorrects</div>

    <div class="info">
      Apres __MAX_ATTEMPTS__ essais incorrects, le PIN est bloque.
      Pour debloquer immediatement, validez votre code 2FA Authenticator
      a 6 chiffres ci-dessous.
    </div>

    __ERROR_BLOCK__

    <form method="POST" action="/admin/pin/unlock-via-2fa">
      <label>Code 2FA Authenticator (6 chiffres)</label>
      <input type="text" name="totp_code"
             placeholder="000000"
             autofocus required
             autocomplete="one-time-code"
             inputmode="numeric"
             pattern="\\d*"
             maxlength="6">
      <label>Nouveau PIN admin</label>
      <input type="password" name="new_pin"
             placeholder="••••"
             required
             autocomplete="off"
             inputmode="numeric"
             pattern="\\d*"
             minlength="4"
             maxlength="6">
      <button type="submit">Debloquer + redefinir PIN</button>
    </form>

    <div class="links">
      <a href="/chat">&#8592; Retour au chat</a>
      <a href="/logout">Deconnexion</a>
    </div>
  </div>
</body>
</html>"""


# ─── GET /admin/pin-challenge ──────────────────────────────────────────


@router.get("/admin/pin-challenge", response_class=HTMLResponse)
def get_pin_challenge(request: Request):
    """Affiche la page de saisie du PIN."""
    username = request.session.get("user")
    if not username:
        return RedirectResponse("/login-app", status_code=303)
    scope = request.session.get("scope", "")
    if scope not in SCOPES_REQUIRING_2FA:
        return RedirectResponse("/chat", status_code=303)

    # Pas de PIN configure -> redirect setup 2FA
    if not has_pin_set(username):
        return RedirectResponse("/admin/2fa/setup?need_pin=1", status_code=303)

    # PIN bloque -> page de deblocage
    locked, seconds = is_pin_locked(username)
    if locked:
        return _render_locked_page("")

    # Page normale
    return _render_pin_page("", min_len=PIN_MIN_LENGTH, max_len=PIN_MAX_LENGTH)


def _render_pin_page(error_block: str, min_len: int = 4, max_len: int = 6) -> HTMLResponse:
    extra = f"({min_len}-{max_len} chiffres)" if min_len != max_len else f"({min_len} chiffres)"
    page_length = "4 a 6" if min_len != max_len else str(min_len)
    html = (
        CHALLENGE_PIN_HTML
        .replace("__ERROR_BLOCK__", error_block)
        .replace("__PIN_LENGTH__", page_length)
        .replace("__EXTRA_INFO__", extra)
        .replace("__MIN_LEN__", str(min_len))
        .replace("__MAX_LEN__", str(max_len))
    )
    return HTMLResponse(html)


def _render_locked_page(error_block: str) -> HTMLResponse:
    html = (
        CHALLENGE_LOCKED_HTML
        .replace("__ERROR_BLOCK__", error_block)
        .replace("__MAX_ATTEMPTS__", str(PIN_MAX_ATTEMPTS))
    )
    return HTMLResponse(html, status_code=423)  # 423 Locked


# ─── POST /admin/pin-challenge ─────────────────────────────────────────


@router.post("/admin/pin-challenge", response_class=HTMLResponse)
def post_pin_challenge(request: Request, pin: str = Form(...)):
    """Verifie le PIN saisi."""
    username = request.session.get("user")
    if not username:
        return RedirectResponse("/login-app", status_code=303)

    tenant_id = request.session.get("tenant_id", "")
    pin_clean = (pin or "").strip()

    success, error_msg, state = verify_pin(username, pin_clean)

    if success:
        mark_pin_validated(request)
        log_auth_event(
            username=username,
            tenant_id=tenant_id,
            event_type="pin_success",
            ip=_client_ip(request),
            user_agent=_user_agent(request),
        )
        next_url = request.session.pop("pending_admin_path", None) or "/admin/panel"
        return RedirectResponse(next_url, status_code=303)

    # Echec
    log_auth_event(
        username=username,
        tenant_id=tenant_id,
        event_type="pin_failure",
        ip=_client_ip(request),
        user_agent=_user_agent(request),
        metadata={"attempts": state.get("attempts", 0)},
    )

    if state.get("max_reached") or state.get("locked_seconds"):
        # Bloque -> page deblocage 2FA
        return _render_locked_page(f'<div class="error">{error_msg}</div>')

    return _render_pin_page(
        f'<div class="error">{error_msg}</div>',
        min_len=PIN_MIN_LENGTH,
        max_len=PIN_MAX_LENGTH,
    )


# ─── POST /admin/pin/unlock-via-2fa ────────────────────────────────────


@router.post("/admin/pin/unlock-via-2fa", response_class=HTMLResponse)
def unlock_pin_via_2fa(
    request: Request,
    totp_code: str = Form(...),
    new_pin: str = Form(...),
):
    """Debloque le PIN apres 3 echecs en validant la 2FA + redefinit un nouveau PIN."""
    username = request.session.get("user")
    if not username:
        return RedirectResponse("/login-app", status_code=303)
    tenant_id = request.session.get("tenant_id", "")

    # Verifier le code TOTP
    from app.database import get_pg_conn
    secret_encrypted = None
    try:
        with get_pg_conn() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT totp_secret_encrypted FROM users WHERE username = %s AND deleted_at IS NULL",
                (username,),
            )
            row = cur.fetchone()
            secret_encrypted = row[0] if row else None
    except Exception as e:
        logger.error("[Admin PIN] unlock fetch secret error: %s", str(e)[:200])

    if not secret_encrypted:
        return _render_locked_page('<div class="error">Erreur configuration 2FA. Contactez le support.</div>')

    try:
        secret = decrypt_totp_secret(secret_encrypted)
        if not verify_totp_code(secret, totp_code):
            log_auth_event(
                username=username, tenant_id=tenant_id,
                event_type="pin_unlock_failed_2fa_invalid",
                ip=_client_ip(request), user_agent=_user_agent(request),
            )
            return _render_locked_page('<div class="error">Code 2FA invalide. Reessayez.</div>')
    except Exception as e:
        logger.error("[Admin PIN] unlock totp verify error: %s", str(e)[:200])
        return _render_locked_page('<div class="error">Erreur validation 2FA. Reessayez.</div>')

    # 2FA OK : valider le format du nouveau PIN
    valid, err = validate_pin_format(new_pin)
    if not valid:
        return _render_locked_page(f'<div class="error">Nouveau PIN invalide : {err}</div>')

    # Set le nouveau PIN (qui reset aussi les compteurs)
    success, error_msg = set_pin(username, new_pin)
    if not success:
        return _render_locked_page(f'<div class="error">{error_msg}</div>')

    log_auth_event(
        username=username, tenant_id=tenant_id,
        event_type="pin_unlocked_via_2fa",
        ip=_client_ip(request), user_agent=_user_agent(request),
    )

    mark_pin_validated(request)
    next_url = request.session.pop("pending_admin_path", None) or "/admin/panel"
    return RedirectResponse(next_url, status_code=303)
