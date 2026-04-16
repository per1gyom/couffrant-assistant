"""
Couche de compatibilité sécurité.
Re-exporte les fonctions des modules spécialisés.
LOGIN_PAGE_HTML est défini ici car utilisé dans routes/auth.py.
"""
from app.security_auth import (  # noqa
    hash_password, verify_password,
    check_rate_limit, record_failed_attempt, clear_attempts,
    validate_password_strength, unlock_account,
)
from app.security_tools import (  # noqa
    get_user_tools, set_user_tool, remove_user_tool, init_default_tools,
    ALL_SCOPES, SCOPE_ADMIN, SCOPE_TENANT_ADMIN, SCOPE_CS, SCOPE_USER, DEFAULT_TENANT,
)
from app.security_users import (  # noqa
    authenticate, create_user, update_user, delete_user, list_users,
    get_user_scope, get_tenant_id, get_users_in_tenant, update_last_login,
    init_default_user, generate_reset_token, validate_reset_token,
    consume_reset_token, must_reset_password_check, set_must_reset_password,
    resolve_username, get_user_phone,
)

# ─── PAGE DE CONNEXION — palette Bleu Roi Saturé ───

LOGIN_PAGE_HTML = """<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Raya — Connexion</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
*, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
:root {{
  --bg: #f5f9ff; --surface: #ffffff; --border: #bdd6ff;
  --text: #1a1d23; --text-muted: #6e7687;
  --accent: #0057b8; --accent-hover: #004499; --accent-light: #d8eaff;
  --danger: #ef4444; --danger-light: #fee2e2;
  --success: #059669;
}}
html, body {{
  height: 100%; background: var(--bg); color: var(--text);
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  font-size: 15px;
}}
.page {{
  min-height: 100vh; display: flex; align-items: center;
  justify-content: center; padding: 24px;
}}
.card {{
  background: var(--surface); border: 1px solid var(--border);
  border-radius: 24px; padding: 44px 40px; width: 100%; max-width: 400px;
  box-shadow: 0 8px 32px rgba(0,87,184,0.12), 0 2px 8px rgba(0,87,184,0.06);
}}
.logo-area {{
  text-align: center; margin-bottom: 8px;
  display: flex; align-items: center; justify-content: center; gap: 10px;
}}
.logo-dot {{
  width: 10px; height: 10px; background: var(--success);
  border-radius: 50%; animation: pulse 2.5s ease-in-out infinite;
}}
@keyframes pulse {{ 0%,100%{{opacity:1}}50%{{opacity:.4}} }}
.logo-text {{ font-size: 26px; font-weight: 800; letter-spacing: -0.5px; color: var(--text); }}
.subtitle {{
  text-align: center; font-size: 13px; color: var(--text-muted);
  margin-bottom: 32px;
}}
.form-group {{ margin-bottom: 18px; }}
label {{
  display: block; font-size: 11px; font-weight: 700;
  color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.06em;
  margin-bottom: 6px;
}}
input[type=text], input[type=password] {{
  width: 100%; background: #f0f7ff; border: 1.5px solid var(--border);
  border-radius: 10px; color: var(--text); font-size: 14px; font-family: inherit;
  padding: 11px 14px; outline: none;
  transition: border-color 0.15s, box-shadow 0.15s, background 0.15s;
}}
input:focus {{
  border-color: var(--accent);
  box-shadow: 0 0 0 3px rgba(0,87,184,0.10);
  background: #fff;
}}
.submit-btn {{
  width: 100%; background: var(--accent); color: #fff;
  border: none; border-radius: 12px; padding: 13px; font-size: 15px;
  font-weight: 600; cursor: pointer; font-family: inherit;
  transition: background 0.15s, transform 0.1s;
  margin-top: 8px;
  box-shadow: 0 4px 14px rgba(0,87,184,0.25);
}}
.submit-btn:hover {{ background: var(--accent-hover); transform: translateY(-1px); }}
.submit-btn:active {{ transform: translateY(0); }}
.error {{
  background: var(--danger-light);
  border: 1px solid rgba(239,68,68,0.3); color: #b91c1c;
  border-radius: 8px; padding: 10px 14px; font-size: 13px;
  margin-bottom: 18px;
}}
.forgot-link {{ text-align: center; margin-top: 16px; }}
.forgot-link a {{
  color: var(--accent); font-size: 13px; font-weight: 500;
  text-decoration: none; transition: color 0.15s;
}}
.forgot-link a:hover {{ color: var(--accent-hover); text-decoration: underline; }}
.legal-link {{ text-align: center; margin-top: 10px; }}
.legal-link a {{
  color: var(--text-muted); font-size: 12px;
  text-decoration: none; opacity: 0.7; transition: opacity 0.15s;
}}
.legal-link a:hover {{ opacity: 1; text-decoration: underline; }}
</style>
</head>
<body>
<div class="page">
  <div class="card">
    <div class="logo-area">
      <div class="logo-dot"></div>
      <span class="logo-text">Raya</span>
    </div>
    <p class="subtitle">Couffrant Solar — Assistant IA</p>
    {error_block}
    <form method="post" action="/login-app">
      <div class="form-group">
        <label>Email ou identifiant</label>
        <input type="text" name="username" placeholder="email ou identifiant"
               autocomplete="username" autofocus required>
      </div>
      <div class="form-group">
        <label>Mot de passe</label>
        <input type="password" name="password" placeholder="&bull;&bull;&bull;&bull;&bull;&bull;&bull;&bull;&bull;&bull;&bull;&bull;"
               autocomplete="current-password" required>
      </div>
      <button type="submit" class="submit-btn">Se connecter</button>
    </form>
    <p class="forgot-link"><a href="/forgot-password">Mot de passe oublié ?</a></p>
    <p class="legal-link"><a href="/legal" target="_blank">Mentions légales &amp; Confidentialité</a></p>
  </div>
</div>
</body>
</html>"""
