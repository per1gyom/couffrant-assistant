"""
app_security.py — module de compatibilité.
Réexporte tout depuis les sous-modules spécialisés.
Aucun autre fichier n'a besoin d'être modifié.
"""

from app.security_auth import (
    check_rate_limit, record_failed_attempt, clear_attempts,
    hash_password, verify_password,
)

from app.security_tools import (
    SCOPE_ADMIN, SCOPE_TENANT_ADMIN, SCOPE_CS, SCOPE_USER,
    DEFAULT_TENANT, TENANT_ADMIN_SCOPES, USER_SCOPES, ALL_SCOPES,
    DEFAULT_TOOLS_ADMIN, DEFAULT_TOOLS_TENANT_ADMIN, DEFAULT_TOOLS_USER, DEFAULT_TOOLS_CS,
    init_default_tools, get_user_tools, get_tool_config,
    set_user_tool, remove_user_tool,
)

from app.security_users import (
    get_tenant_id, get_users_in_tenant,
    authenticate, get_user_scope,
    create_user, update_user, delete_user, list_users,
    update_last_login, get_current_user, init_default_user,
    generate_reset_token, validate_reset_token, consume_reset_token,
)

LOGIN_PAGE_HTML = """
<!DOCTYPE html><html lang="fr"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Raya — Connexion</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:#0a0a0a;color:#fff;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Arial,sans-serif;display:flex;align-items:center;justify-content:center;min-height:100vh}}
.card{{background:#111;border:1px solid #1e1e1e;border-radius:16px;padding:40px;width:100%;max-width:380px;box-shadow:0 8px 32px rgba(0,0,0,0.5)}}
.logo{{font-size:32px;margin-bottom:12px}}
h1{{font-size:24px;color:#e8e8e8;margin-bottom:4px;font-weight:700}}
.subtitle{{font-size:13px;color:#555;margin-bottom:36px}}
label{{font-size:11px;color:#666;text-transform:uppercase;letter-spacing:0.8px;display:block}}
input[type=text],input[type=password]{{width:100%;padding:13px 16px;background:#161616;border:1px solid #2a2a2a;border-radius:10px;color:#e8e8e8;font-size:15px;margin:8px 0 22px;outline:none;transition:border-color 0.2s}}
input:focus{{border-color:#1565c0;background:#1a1a1a}}
button{{width:100%;padding:14px;background:#1565c0;color:white;border:none;border-radius:10px;font-size:15px;font-weight:600;cursor:pointer;transition:background 0.15s}}
button:hover{{background:#1976d2}}
.error{{background:rgba(220,50,50,0.1);border:1px solid rgba(220,50,50,0.3);color:#ff7070;padding:12px 16px;border-radius:8px;font-size:13px;margin-bottom:24px;text-align:center}}
</style></head><body>
<div class="card">
  <div class="logo">⚡</div><h1>Raya</h1><div class="subtitle">Accès privé</div>
  {{error_block}}
  <form method="post" action="/login-app">
    <label>Identifiant</label><input type="text" name="username" autocomplete="username" required>
    <label>Mot de passe</label><input type="password" name="password" autocomplete="current-password" required>
    <button type="submit">Se connecter →</button>
  </form>
  <p style="text-align:center;margin-top:16px"><a href="/forgot-password" style="font-size:12px;color:#555">Mot de passe oublié ?</a></p>
</div></body></html>
"""

__all__ = [
    # auth
    'check_rate_limit', 'record_failed_attempt', 'clear_attempts',
    'hash_password', 'verify_password',
    # scopes & tools
    'SCOPE_ADMIN', 'SCOPE_TENANT_ADMIN', 'SCOPE_CS', 'SCOPE_USER',
    'DEFAULT_TENANT', 'TENANT_ADMIN_SCOPES', 'USER_SCOPES', 'ALL_SCOPES',
    'init_default_tools', 'get_user_tools', 'get_tool_config',
    'set_user_tool', 'remove_user_tool',
    # users
    'get_tenant_id', 'get_users_in_tenant',
    'authenticate', 'get_user_scope',
    'create_user', 'update_user', 'delete_user', 'list_users',
    'update_last_login', 'get_current_user', 'init_default_user',
    'generate_reset_token', 'validate_reset_token', 'consume_reset_token',
    # html
    'LOGIN_PAGE_HTML',
]
