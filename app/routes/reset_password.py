from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from app.app_security import validate_reset_token, consume_reset_token
from app.config import SUPPORT_EMAIL

router = APIRouter(tags=["reset"])

RESET_HTML = """
<!DOCTYPE html><html lang="fr"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Raya — Réinitialisation</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:#0a0a0a;color:#fff;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Arial,sans-serif;display:flex;align-items:center;justify-content:center;min-height:100vh}}
.card{{background:#111;border:1px solid #1e1e1e;border-radius:16px;padding:40px;width:100%;max-width:400px}}
.logo{{font-size:28px;margin-bottom:12px}}
h1{{font-size:22px;color:#e8e8e8;margin-bottom:6px;font-weight:700}}
.sub{{font-size:13px;color:#555;margin-bottom:28px}}
label{{font-size:11px;color:#666;text-transform:uppercase;letter-spacing:0.8px;display:block}}
input[type=password]{{width:100%;padding:13px 16px;background:#161616;border:1px solid #2a2a2a;border-radius:10px;color:#e8e8e8;font-size:15px;margin:8px 0 22px;outline:none}}
input:focus{{border-color:#1565c0}}
button{{width:100%;padding:14px;background:#1565c0;color:white;border:none;border-radius:10px;font-size:15px;font-weight:600;cursor:pointer}}
.msg{{padding:12px 16px;border-radius:8px;font-size:13px;margin-bottom:20px;text-align:center}}
.ok{{background:rgba(0,200,100,0.1);border:1px solid rgba(0,200,100,0.3);color:#4ade80}}
.err{{background:rgba(220,50,50,0.1);border:1px solid rgba(220,50,50,0.3);color:#ff7070}}
</style></head>
<body><div class="card">
<div class="logo">⚡</div>
<h1>Nouveau mot de passe</h1>
<div class="sub">{sub}</div>
{msg_block}
{form_block}
</div></body></html>
"""

FORGOT_HTML = """<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Raya — Mot de passe oublié</title>
<style>
*, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
:root {{
  --bg: #f5f7fa; --surface: #ffffff; --border: #dde2ec;
  --text: #111827; --text-muted: #6b7280;
  --accent: #6366f1; --accent-hover: #5558e8;
  --shadow: 0 4px 24px rgba(0,0,0,0.08);
}}
html, body {{ height: 100%; background: var(--bg); color: var(--text);
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  font-size: 15px; }}
.page {{ min-height: 100vh; display: flex; align-items: center;
  justify-content: center; padding: 24px; }}
.card {{ background: var(--surface); border: 1px solid var(--border);
  border-radius: 16px; padding: 40px; width: 100%; max-width: 400px;
  box-shadow: var(--shadow); text-align: center; }}
.logo {{ font-size: 28px; font-weight: 800; letter-spacing: -0.5px;
  margin-bottom: 6px; }}
.logo span {{ color: var(--accent); }}
.subtitle {{ font-size: 13px; color: var(--text-muted); margin-bottom: 32px; }}
.icon {{ font-size: 40px; margin-bottom: 16px; }}
h2 {{ font-size: 20px; font-weight: 700; margin-bottom: 12px; }}
.message {{ font-size: 14px; color: var(--text-muted); line-height: 1.6;
  margin-bottom: 8px; }}
.email-link {{ color: var(--accent); font-weight: 600; text-decoration: none; }}
.email-link:hover {{ text-decoration: underline; }}
.back-btn {{ display: inline-block; margin-top: 28px; background: var(--accent);
  color: #fff; border: none; border-radius: 10px; padding: 12px 24px;
  font-size: 14px; font-weight: 600; text-decoration: none;
  transition: background 0.15s; cursor: pointer; }}
.back-btn:hover {{ background: var(--accent-hover); }}
</style>
</head>
<body>
<div class="page">
  <div class="card">
    <div class="logo">⚡ Ra<span>ya</span></div>
    <p class="subtitle">Couffrant Solar — Assistant IA</p>
    <div class="icon">🔑</div>
    <h2>Mot de passe oublié ?</h2>
    <p class="message">
      Pour réinitialiser votre mot de passe, contactez votre administrateur :
    </p>
    <p class="message" style="margin-top: 10px;">
      <a href="mailto:{support_email}" class="email-link">{support_email}</a>
    </p>
    <p class="message" style="margin-top: 16px; font-size: 13px;">
      Il vous générera un nouveau mot de passe temporaire.
    </p>
    <a href="/login-app" class="back-btn">Retour au login</a>
  </div>
</div>
</body>
</html>"""


@router.get("/forgot-password", response_class=HTMLResponse)
def forgot_password_page():
    return HTMLResponse(FORGOT_HTML.format(support_email=SUPPORT_EMAIL))


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
            msg_block='<div class="msg err">Lien invalide, expiré ou déjà utilisé. Demandez un nouveau lien à votre administrateur.</div>',
            form_block=""))
    form = f"""
    <p style="font-size:13px;color:#888;margin-bottom:20px">Compte : <strong style="color:#ccc">{info['username']}</strong></p>
    <form method="post" action="/reset-password">
      <input type="hidden" name="token" value="{token}">
      <label>Nouveau mot de passe</label>
      <input type="password" name="password" placeholder="8 caractères minimum" required>
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
