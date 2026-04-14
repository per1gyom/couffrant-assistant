"""
Templates HTML reset_password.
Extrait de reset_password.py -- SPLIT-R4.
"""
import os
SUPPORT_EMAIL=os.getenv("SUPPORT_EMAIL","support@couffrant-solar.fr")

# ─── HTML ───────────────────────────────────────────────────────────────────

_BASE_STYLE = """
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
:root {
  --bg: #f5f7fa; --surface: #ffffff; --border: #dde2ec;
  --text: #111827; --text-muted: #6b7280;
  --accent: #6366f1; --accent-hover: #5558e8;
  --red: #ef4444; --green: #22c55e;
  --shadow: 0 4px 24px rgba(0,0,0,0.08);
}
html, body { height: 100%; background: var(--bg); color: var(--text);
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  font-size: 15px; }
.page { min-height: 100vh; display: flex; align-items: center;
  justify-content: center; padding: 24px; }
.card { background: var(--surface); border: 1px solid var(--border);
  border-radius: 16px; padding: 40px; width: 100%; max-width: 420px;
  box-shadow: var(--shadow); }
.logo { font-size: 28px; font-weight: 800; letter-spacing: -0.5px;
  margin-bottom: 4px; text-align: center; }
.logo span { color: var(--accent); }
.subtitle { font-size: 13px; color: var(--text-muted); margin-bottom: 32px;
  text-align: center; }
h2 { font-size: 20px; font-weight: 700; margin-bottom: 8px; }
.desc { font-size: 13px; color: var(--text-muted); line-height: 1.6;
  margin-bottom: 24px; }
label { display: block; font-size: 11px; color: var(--text-muted);
  text-transform: uppercase; letter-spacing: 0.8px; margin-bottom: 6px; }
input[type=text], input[type=email] {
  width: 100%; padding: 13px 16px;
  background: #f9fafb; border: 1px solid var(--border);
  border-radius: 10px; color: var(--text); font-size: 15px;
  margin-bottom: 22px; outline: none; transition: border-color 0.15s; }
input:focus { border-color: var(--accent); background: #fff; }
button[type=submit] { width: 100%; padding: 14px;
  background: var(--accent); color: #fff; border: none;
  border-radius: 10px; font-size: 15px; font-weight: 600; cursor: pointer;
  transition: background 0.15s; }
button[type=submit]:hover { background: var(--accent-hover); }
button[type=submit]:disabled { opacity: 0.6; cursor: not-allowed; }
.msg { padding: 12px 16px; border-radius: 8px; font-size: 13px;
  margin-bottom: 20px; line-height: 1.5; }
.msg.ok  { background: rgba(34,197,94,0.08); border: 1px solid rgba(34,197,94,0.25);
  color: #16a34a; }
.msg.err { background: rgba(239,68,68,0.08); border: 1px solid rgba(239,68,68,0.25);
  color: var(--red); }
.msg.info { background: rgba(99,102,241,0.07); border: 1px solid rgba(99,102,241,0.2);
  color: #4338ca; }
.back { display: block; text-align: center; margin-top: 24px;
  font-size: 13px; color: var(--text-muted); text-decoration: none; }
.back:hover { color: var(--accent); }
"""

# Page quand SMTP n'est pas configuré
_PAGE_SMTP_MISSING = f"""<!DOCTYPE html>
<html lang="fr"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Raya — Mot de passe oublié</title>
<style>{_BASE_STYLE}</style></head>
<body><div class="page"><div class="card">
  <div class="logo">⚡ Ra<span>ya</span></div>
  <p class="subtitle">Couffrant Solar — Assistant IA</p>
  <h2>Mot de passe oublié ?</h2>
  <div class="msg info">
    La réinitialisation par email n'est pas encore activée.<br>
    Contactez votre administrateur :
    <strong><a href="mailto:{{support_email}}" style="color:#4338ca">{{support_email}}</a></strong>
  </div>
  <a href="/login-app" class="back">← Retour au login</a>
</div></div></body></html>"""

# Formulaire self-service
_PAGE_FORM = f"""<!DOCTYPE html>
<html lang="fr"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Raya — Mot de passe oublié</title>
<style>{_BASE_STYLE}</style></head>
<body><div class="page"><div class="card">
  <div class="logo">⚡ Ra<span>ya</span></div>
  <p class="subtitle">Couffrant Solar — Assistant IA</p>
  <h2>Mot de passe oublié ?</h2>
  <p class="desc">
    Entrez votre identifiant ou adresse email. Si un compte correspondant
    est trouvé, vous recevrez un lien de réinitialisation valable 24 h.
  </p>
  {{msg_block}}
  <form method="post" action="/forgot-password">
    <label>Identifiant ou adresse email</label>
    <input type="text" name="login" placeholder="ex : guillaume ou mon@email.fr"
           autocomplete="username" required autofocus value="{{prefill}}">
    <button type="submit">Envoyer le lien de réinitialisation</button>
  </form>
  <a href="/login-app" class="back">← Retour au login</a>
</div></div></body></html>"""

# Réponse identique quelle que soit la situation (anti-énumération)
_PAGE_SENT = f"""<!DOCTYPE html>
<html lang="fr"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Raya — Lien envoyé</title>
<style>{_BASE_STYLE}</style></head>
<body><div class="page"><div class="card">
  <div class="logo">⚡ Ra<span>ya</span></div>
  <p class="subtitle">Couffrant Solar — Assistant IA</p>
  <h2>Vérifiez votre boîte mail</h2>
  <div class="msg ok">
    Si un compte existe avec ces informations, un email de réinitialisation
    vient d'être envoyé. Le lien est valable 24 heures.<br><br>
    Pensez à vérifier vos spams.
  </div>
  <a href="/login-app" class="back">← Retour au login</a>
</div></div></body></html>"""

# ─── Page de réinitialisation du mot de passe (token) ───────────────────────

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

# ─── Routes ─────────────────────────────────────────────────────────────────

