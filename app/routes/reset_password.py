"""
Routes de réinitialisation de mot de passe.
  GET  /forgot-password  → formulaire self-service (ou info si SMTP absent)
  POST /forgot-password  → traitement avec rate-limit
  GET  /reset-password   → formulaire nouveau mot de passe (via token)
  POST /reset-password   → application du nouveau mot de passe

FORGOT-PASSWORD : self-service avec protection :
  - Rate limit 3 tentatives / IP / heure (in-memory)
  - Réponse identique qu'un compte existe ou non (anti-énumération)
  - Log de chaque tentative (IP + identifiant tenté)
  - Délai constant en cas d'absence pour éviter le timing attack
  - Désactivé si SMTP non configuré
"""
import os
import time
import asyncio
from collections import defaultdict
from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from app.app_security import validate_reset_token, consume_reset_token
from app.config import SUPPORT_EMAIL

router = APIRouter(tags=["reset"])

# ─── Rate limiter léger (in-memory, oublié au redémarrage) ───
# Structure : {ip: [timestamp, timestamp, ...]} — on garde les 3h récentes max.
_FORGOT_ATTEMPTS: dict = defaultdict(list)
_FORGOT_MAX_ATTEMPTS = 3     # par IP
_FORGOT_WINDOW_SEC  = 3600   # 1 heure


def _check_forgot_rate_limit(ip: str) -> tuple[bool, str]:
    """Retourne (allowed, message). Expurge les entrées périmées."""
    now = time.time()
    recent = [t for t in _FORGOT_ATTEMPTS[ip] if now - t < _FORGOT_WINDOW_SEC]
    _FORGOT_ATTEMPTS[ip] = recent
    if len(recent) >= _FORGOT_MAX_ATTEMPTS:
        remaining = int(_FORGOT_WINDOW_SEC - (now - recent[0]))
        mins = max(1, remaining // 60)
        return False, (
            f"Trop de tentatives. Réessayez dans {mins} minute(s) "
            f"ou contactez <a href='mailto:{SUPPORT_EMAIL}'>{SUPPORT_EMAIL}</a>."
        )
    _FORGOT_ATTEMPTS[ip].append(now)
    return True, ""


def _smtp_configured() -> bool:
    """Retourne True si SMTP est configuré dans les variables d'environnement."""
    return bool(
        os.getenv("SMTP_HOST", "").strip()
        and os.getenv("SMTP_USER", "").strip()
        and os.getenv("SMTP_PASS", "").strip()
    )


def _find_user_by_login_or_email(login: str) -> dict | None:
    """
    Cherche un utilisateur par identifiant (exact) OU par email (case-insensitive).
    Retourne {"username": str, "email": str|None} ou None.
    """
    from app.database import get_pg_conn
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        login_clean = login.strip()
        c.execute("""
            SELECT username, email
            FROM users
            WHERE username = %s
               OR (email IS NOT NULL AND lower(email) = lower(%s))
            LIMIT 1
        """, (login_clean, login_clean))
        row = c.fetchone()
        if not row:
            return None
        return {"username": row[0], "email": row[1]}
    except Exception as e:
        print(f"[ForgotPassword] Erreur lookup: {e}")
        return None
    finally:
        if conn: conn.close()


from app.routes.reset_password_templates import (  # noqa
    _PAGE_SMTP_MISSING,_PAGE_FORM,_PAGE_SENT,RESET_HTML,SUPPORT_EMAIL,
)

@router.get("/forgot-password", response_class=HTMLResponse)
def forgot_password_page():
    if not _smtp_configured():
        return HTMLResponse(
            _PAGE_SMTP_MISSING.replace("{support_email}", SUPPORT_EMAIL)
                              .replace("{support_email}", SUPPORT_EMAIL)
        )
    return HTMLResponse(
        _PAGE_FORM.format(msg_block="", prefill="")
    )


@router.post("/forgot-password", response_class=HTMLResponse)
async def forgot_password_submit(
    request: Request,
    login: str = Form(...),
):
    ip = request.client.host if request.client else "unknown"
    login_clean = login.strip()

    # 0. SMTP toujours requis
    if not _smtp_configured():
        return HTMLResponse(
            _PAGE_SMTP_MISSING.replace("{support_email}", SUPPORT_EMAIL)
                              .replace("{support_email}", SUPPORT_EMAIL)
        )

    # 1. Rate limit (3 tentatives / IP / heure)
    allowed, rl_msg = _check_forgot_rate_limit(ip)
    if not allowed:
        print(f"[ForgotPassword] Rate limit dépassé — IP:{ip} login:{login_clean!r}")
        return HTMLResponse(
            _PAGE_FORM.format(
                msg_block=f'<div class="msg err">{rl_msg}</div>',
                prefill=login_clean,
            )
        )

    print(f"[ForgotPassword] Tentative — IP:{ip} login:{login_clean!r}")

    # 2. Chercher l'utilisateur (nom OU email)
    user = _find_user_by_login_or_email(login_clean)

    # 3. Toujours attendre le même temps (anti-timing attack)
    #    On fait la vraie opération si possible, sinon on simule le délai.
    if user and user.get("email"):
        # Cas nominal : envoyer le mail
        try:
            from app.security_users import generate_reset_token
            generate_reset_token(user["username"])
            print(
                f"[ForgotPassword] Lien envoyé → {user['username']} "
                f"({user['email']}) depuis IP:{ip}"
            )
        except Exception as e:
            print(f"[ForgotPassword] Erreur generate_reset_token: {e}")
        # Pas de délai supplémentaire nécessaire (appel réseau a déjà pris du temps)
    else:
        # Cas : user absent ou sans email → on simule le temps de traitement
        # pour éviter de révéler par timing si le compte existe.
        await asyncio.sleep(0.4)
        if user:
            # User trouvé mais sans email : on log seulement en interne
            print(
                f"[ForgotPassword] Compte sans email → {user['username']} "
                f"(impossible d'envoyer le lien) IP:{ip}"
            )
        else:
            print(f"[ForgotPassword] Compte introuvable → login:{login_clean!r} IP:{ip}")

    # 4. Réponse TOUJOURS identique (anti-énumération)
    return HTMLResponse(_PAGE_SENT)


@router.get("/reset-password", response_class=HTMLResponse)
def reset_password_page(token: str = ""):
    if not token:
        return HTMLResponse(RESET_HTML.format(
            sub="Lien invalide.",
            msg_block='<div class="msg err">Lien manquant ou mal formé.</div>',
            form_block=""))
    info = validate_reset_token(token)
    if not info:
        return HTMLResponse(RESET_HTML.format(
            sub="Ce lien est expiré ou déjà utilisé.",
            msg_block='<div class="msg err">Lien invalide, expiré ou déjà utilisé. Demandez un nouveau lien.</div>',
            form_block=""))
    form = f"""
    <p style="font-size:13px;color:#888;margin-bottom:20px">Compte : <strong style="color:#ccc">{info['username']}</strong></p>
    <form method="post" action="/reset-password">
      <input type="hidden" name="token" value="{token}">
      <label>Nouveau mot de passe</label>
      <input type="password" name="password" placeholder="12 caractères min, maj, chiffre, spécial" required>
      <label>Confirmer</label>
      <input type="password" name="confirm" placeholder="Répéter" required>
      <button type="submit">Mettre à jour →</button>
    </form>"""
    return HTMLResponse(RESET_HTML.format(
        sub="Choisissez un nouveau mot de passe sécurisé.",
        msg_block="", form_block=form))


@router.post("/reset-password", response_class=HTMLResponse)
async def reset_password_submit(
    request: Request,
    token: str = Form(...),
    password: str = Form(...),
    confirm: str = Form(...),
):
    if password != confirm:
        return HTMLResponse(RESET_HTML.format(
            sub="Les mots de passe ne correspondent pas.",
            msg_block='<div class="msg err">Les deux mots de passe doivent être identiques.</div>',
            form_block=f"""
            <form method="post" action="/reset-password">
              <input type="hidden" name="token" value="{token}">
              <label>Nouveau mot de passe</label><input type="password" name="password" required>
              <label>Confirmer</label><input type="password" name="confirm" required>
              <button type="submit">Mettre à jour →</button>
            </form>"""))
    result = consume_reset_token(token, password)
    if result["status"] != "ok":
        return HTMLResponse(RESET_HTML.format(
            sub="Échec de la réinitialisation.",
            msg_block=f'<div class="msg err">{result["message"]}</div>',
            form_block=""))
    return HTMLResponse(RESET_HTML.format(
        sub="Mot de passe mis à jour avec succès.",
        msg_block='<div class="msg ok">✓ Mot de passe mis à jour. Vous pouvez vous connecter.</div>',
        form_block='<p style="text-align:center"><a href="/login-app" style="color:#1565c0;font-size:14px">→ Se connecter</a></p>'))
