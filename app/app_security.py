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

# ─── PAGE DE CONNEXION ───

LOGIN_PAGE_HTML = """<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Raya — Connexion</title>
<style>
*, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
:root {{
  --bg: #f5f7fa; --surface: #ffffff; --border: #dde2ec;
  --text: #111827; --text-muted: #6b7280;
  --accent: #6366f1; --accent-hover: #5558e8;
  --danger: #ef4444; --danger-light: #fee2e2;
  --shadow: 0 4px 24px rgba(0,0,0,0.08);
}}
html, body {{ height: 100%; background: var(--bg); color: var(--text);
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  font-size: 15px; }}
.page {{ min-height: 100vh; display: flex; align-items: center;
  justify-content: center; padding: 24px; }}
.card {{ background: var(--surface); border: 1px solid var(--border);
  border-radius: 16px; padding: 40px; width: 100%; max-width: 380px;
  box-shadow: var(--shadow); }}
.logo {{ text-align: center; font-size: 28px; font-weight: 800;
  letter-spacing: -0.5px; margin-bottom: 6px; }}
.logo span {{ color: var(--accent); }}
.subtitle {{ text-align: center; font-size: 13px; color: var(--text-muted);
  margin-bottom: 28px; }}
.form-group {{ margin-bottom: 16px; }}
label {{ display: block; font-size: 12px; font-weight: 600;
  color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.5px;
  margin-bottom: 6px; }}
input[type=text], input[type=password] {{
  width: 100%; background: var(--bg); border: 1px solid var(--border);
  border-radius: 8px; color: var(--text); font-size: 14px;
  padding: 10px 12px; outline: none; transition: border-color 0.15s; }}
input:focus {{ border-color: var(--accent);
  box-shadow: 0 0 0 3px rgba(99,102,241,0.1); }}
.submit-btn {{ width: 100%; background: var(--accent); color: #fff;
  border: none; border-radius: 10px; padding: 12px; font-size: 15px;
  font-weight: 600; cursor: pointer; transition: background 0.15s;
  margin-top: 8px; }}
.submit-btn:hover {{ background: var(--accent-hover); }}
.error {{ background: var(--danger-light);
  border: 1px solid rgba(239,68,68,0.3); color: #b91c1c;
  border-radius: 8px; padding: 10px 14px; font-size: 13px;
  margin-bottom: 16px; }}
.forgot-link {{ text-align: center; margin-top: 14px; }}
.forgot-link a {{ color: var(--text-muted); font-size: 13px;
  text-decoration: none; transition: color 0.15s; }}
.forgot-link a:hover {{ color: var(--accent); text-decoration: underline; }}
</style>
</head>
<body>
<div class="page">
  <div class="card">
    <div class="logo">⚡ Ra<span>ya</span></div>
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
        <input type="password" name="password" placeholder="••••••••••••"
               autocomplete="current-password" required>
      </div>
      <button type="submit" class="submit-btn">Se connecter</button>
    </form>
    <p class="forgot-link"><a href="/forgot-password">Mot de passe oublié ?</a></p>
  </div>
</div>
</body>
</html>"""
