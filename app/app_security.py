import hashlib
import hmac
import os
import base64
import time
import json
from app.database import get_pg_conn

_login_attempts: dict = {}
MAX_ATTEMPTS = 5
LOCKOUT_SECONDS = 15 * 60


def check_rate_limit(ip: str) -> tuple[bool, str]:
    now = time.time()
    data = _login_attempts.get(ip, {})
    locked_until = data.get("locked_until", 0)
    if locked_until > now:
        remaining = int((locked_until - now) / 60) + 1
        return False, f"Trop de tentatives. Réessaie dans {remaining} minute(s)."
    return True, ""


def record_failed_attempt(ip: str):
    now = time.time()
    data = _login_attempts.setdefault(ip, {"count": 0})
    data["count"] = data.get("count", 0) + 1
    if data["count"] >= MAX_ATTEMPTS:
        data["locked_until"] = now + LOCKOUT_SECONDS
        data["count"] = 0


def clear_attempts(ip: str):
    _login_attempts.pop(ip, None)


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 100_000)
    return base64.b64encode(salt + dk).decode('utf-8')


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        raw = base64.b64decode(stored_hash.encode('utf-8'))
        salt, stored_dk = raw[:16], raw[16:]
        dk = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 100_000)
        return hmac.compare_digest(dk, stored_dk)
    except Exception:
        return False


# ─────────────────────────────────────────
# SCOPES — hiérarchie des rôles
# ─────────────────────────────────────────
# SCOPE_ADMIN        → super-admin système (Guillaume / Anthropic)
#                      Accès total : tous les tenants, toutes les données
# SCOPE_TENANT_ADMIN → admin société cliente
#                      Gère les utilisateurs de son tenant uniquement
#                      Ne voit pas les autres sociétés
# SCOPE_CS / SCOPE_USER → employé standard
#                      Utilise Aria, accès aux outils de son scope
# ---------------------------------------------------------
SCOPE_ADMIN        = "admin"
SCOPE_TENANT_ADMIN = "tenant_admin"
SCOPE_CS           = "couffrant_solar"  # legacy — traité comme SCOPE_USER
SCOPE_USER         = "user"
DEFAULT_TENANT     = "couffrant_solar"

# Scopes qui ont accès à la gestion d'un tenant
TENANT_ADMIN_SCOPES = (SCOPE_ADMIN, SCOPE_TENANT_ADMIN)
# Scopes employés standard
USER_SCOPES = (SCOPE_CS, SCOPE_USER)
# Tous les scopes valides
ALL_SCOPES = (SCOPE_ADMIN, SCOPE_TENANT_ADMIN, SCOPE_CS, SCOPE_USER)


DEFAULT_TOOLS_ADMIN = [
    {"tool": "outlook", "access_level": "full",      "config": {"mailboxes": [], "can_delete_mail": True}},
    {"tool": "odoo",    "access_level": "full",      "config": {}},
    {"tool": "drive",   "access_level": "full",      "config": {"can_delete": True}},
    {"tool": "gmail",   "access_level": "full",      "config": {}},
]

# Outils par défaut pour tenant_admin : accès complet dans son tenant
DEFAULT_TOOLS_TENANT_ADMIN = [
    {"tool": "outlook", "access_level": "full",  "config": {"mailboxes": [], "can_delete_mail": True}},
    {"tool": "odoo",    "access_level": "full",  "config": {}},
    {"tool": "drive",   "access_level": "full",  "config": {"can_delete": True}},
]

# Outils par défaut pour employé standard
DEFAULT_TOOLS_USER = [
    {"tool": "outlook", "access_level": "write",     "config": {"mailboxes": [], "can_delete_mail": False}},
    {"tool": "odoo",    "access_level": "read_only", "config": {"shared_user": "sabrina"}},
    {"tool": "drive",   "access_level": "write",     "config": {"can_delete": False}},
]
DEFAULT_TOOLS_CS = DEFAULT_TOOLS_USER  # alias legacy


def _tools_for_scope(scope: str) -> list:
    if scope == SCOPE_ADMIN:
        return DEFAULT_TOOLS_ADMIN
    if scope == SCOPE_TENANT_ADMIN:
        return DEFAULT_TOOLS_TENANT_ADMIN
    return DEFAULT_TOOLS_USER  # SCOPE_CS, SCOPE_USER, autres


def init_default_tools(username: str, scope: str):
    tools = _tools_for_scope(scope)
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        for t in tools:
            c.execute("""
                INSERT INTO user_tools (username, tool, access_level, enabled, config)
                VALUES (%s, %s, %s, true, %s)
                ON CONFLICT (username, tool) DO NOTHING
            """, (username, t["tool"], t["access_level"], json.dumps(t["config"])))
        conn.commit()
    except Exception as e:
        print(f"[Tools] Erreur init_default_tools pour {username}: {e}")
    finally:
        if conn: conn.close()


def get_user_tools(username: str, raw: bool = False):
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            SELECT tool, access_level, enabled, config
            FROM user_tools WHERE username = %s ORDER BY tool
        """, (username,))
        rows = c.fetchall()
        if raw:
            return [{"tool": r[0], "access_level": r[1], "enabled": r[2], "config": r[3] or {}} for r in rows]
        return {r[0]: {"access_level": r[1], "enabled": r[2], "config": r[3] or {}} for r in rows}
    except Exception:
        return [] if raw else {}
    finally:
        if conn: conn.close()


def get_tool_config(username: str, tool: str) -> dict:
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute(
            "SELECT access_level, enabled, config FROM user_tools WHERE username=%s AND tool=%s",
            (username, tool)
        )
        row = c.fetchone()
        if not row:
            return {"access_level": "none", "enabled": False, "config": {}}
        return {"access_level": row[0], "enabled": row[1], "config": row[2] or {}}
    except Exception:
        return {"access_level": "none", "enabled": False, "config": {}}
    finally:
        if conn: conn.close()


def set_user_tool(username: str, tool: str, access_level: str = "read_only",
                  enabled: bool = True, config: dict = None) -> dict:
    if config is None:
        config = {}
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            INSERT INTO user_tools (username, tool, access_level, enabled, config, updated_at)
            VALUES (%s, %s, %s, %s, %s, NOW())
            ON CONFLICT (username, tool) DO UPDATE SET
                access_level = EXCLUDED.access_level,
                enabled = EXCLUDED.enabled,
                config = EXCLUDED.config,
                updated_at = NOW()
        """, (username, tool, access_level, enabled, json.dumps(config)))
        conn.commit()
        return {"status": "ok", "message": f"Outil '{tool}' configuré pour {username} ({access_level})."}
    except Exception as e:
        return {"status": "error", "message": str(e)[:100]}
    finally:
        if conn: conn.close()


def remove_user_tool(username: str, tool: str) -> dict:
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("DELETE FROM user_tools WHERE username=%s AND tool=%s", (username, tool))
        if c.rowcount == 0:
            conn.rollback()
            return {"status": "error", "message": "Outil introuvable."}
        conn.commit()
        return {"status": "ok", "message": f"Outil '{tool}' supprimé pour {username}."}
    except Exception as e:
        return {"status": "error", "message": str(e)[:100]}
    finally:
        if conn: conn.close()


# ─────────────────────────────────────────
# GESTION TENANTS ET UTILISATEURS
# ─────────────────────────────────────────

def get_tenant_id(username: str) -> str:
    """Retourne le tenant_id de l'utilisateur. Défaut : 'couffrant_solar'."""
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("SELECT tenant_id FROM users WHERE username = %s", (username.strip(),))
        row = c.fetchone()
        return row[0] if row and row[0] else DEFAULT_TENANT
    except Exception:
        return DEFAULT_TENANT
    finally:
        if conn: conn.close()


def get_users_in_tenant(tenant_id: str) -> list:
    """Retourne tous les utilisateurs d'un tenant."""
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            SELECT username, scope, last_login, created_at
            FROM users WHERE tenant_id = %s ORDER BY created_at
        """, (tenant_id,))
        return [{"username": r[0], "scope": r[1],
                 "last_login": str(r[2]) if r[2] else None, "created_at": str(r[3])}
                for r in c.fetchall()]
    except Exception:
        return []
    finally:
        if conn: conn.close()


def init_default_user():
    """Crée l'admin système et s'assure que le tenant par défaut existe."""
    try:
        from app.tenant_manager import ensure_default_tenant
        ensure_default_tenant()
    except Exception as e:
        print(f"[Tenant] Erreur ensure_default_tenant: {e}")

    username = os.getenv("APP_USERNAME", "guillaume").strip()
    password = os.getenv("APP_PASSWORD", "couffrant2026").strip()

    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM users")
        if c.fetchone()[0] == 0:
            password_hash = hash_password(password)
            c.execute("""
                INSERT INTO users (username, password_hash, scope, tenant_id)
                VALUES (%s, %s, %s, %s) ON CONFLICT (username) DO NOTHING
            """, (username, password_hash, SCOPE_ADMIN, DEFAULT_TENANT))
            conn.commit()
            print(f"[Auth] Admin créé : {username}")
        else:
            c.execute("""
                UPDATE users SET scope = %s, tenant_id = COALESCE(NULLIF(tenant_id,''), %s)
                WHERE username = %s AND scope = 'couffrant_solar'
            """, (SCOPE_ADMIN, DEFAULT_TENANT, username))
            conn.commit()
    except Exception as e:
        print(f"[Auth] Erreur init_default_user: {e}")
    finally:
        if conn: conn.close()

    init_default_tools(username, SCOPE_ADMIN)

    try:
        from app.memory_manager import seed_default_rules
        seed_default_rules(username)
    except Exception as e:
        print(f"[Seed] Erreur seed_default_rules pour {username}: {e}")


def authenticate(username: str, password: str) -> bool:
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("SELECT password_hash FROM users WHERE username = %s", (username.strip(),))
        row = c.fetchone()
        if not row: return False
        return verify_password(password, row[0])
    except Exception:
        return False
    finally:
        if conn: conn.close()


def get_user_scope(username: str) -> str:
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("SELECT scope FROM users WHERE username = %s", (username.strip(),))
        row = c.fetchone()
        return row[0] if row else SCOPE_USER
    except Exception:
        return SCOPE_USER
    finally:
        if conn: conn.close()


def create_user(username: str, password: str, scope: str = SCOPE_USER,
                tools: list = None, tenant_id: str = DEFAULT_TENANT) -> dict:
    """
    Crée un utilisateur dans un tenant.
    scope : admin | tenant_admin | user | couffrant_solar (legacy)
    """
    if not username or not password:
        return {"status": "error", "message": "Identifiant et mot de passe requis."}
    if len(password) < 8:
        return {"status": "error", "message": "Mot de passe trop court (8 caractères minimum)."}
    if scope not in ALL_SCOPES:
        scope = SCOPE_USER

    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        password_hash = hash_password(password)
        c.execute("""
            INSERT INTO users (username, password_hash, scope, tenant_id)
            VALUES (%s, %s, %s, %s)
        """, (username.strip(), password_hash, scope, tenant_id or DEFAULT_TENANT))
        conn.commit()
        print(f"[Auth] Création : {username} (scope: {scope}, tenant: {tenant_id})")
    except Exception as e:
        if "unique" in str(e).lower():
            return {"status": "error", "message": f"L'identifiant '{username}' existe déjà."}
        return {"status": "error", "message": str(e)[:100]}
    finally:
        if conn: conn.close()

    try:
        from app.memory_manager import seed_default_rules
        seed_default_rules(username.strip())
    except Exception as e:
        print(f"[Seed] Erreur seed_default_rules pour {username}: {e}")

    init_default_tools(username.strip(), scope)

    if tools:
        for t in tools:
            if "tool" in t:
                set_user_tool(
                    username.strip(), t["tool"],
                    t.get("access_level", "read_only"),
                    t.get("enabled", True),
                    t.get("config", {}),
                )

    return {"status": "ok", "message": f"Utilisateur '{username}' créé (scope: {scope}, tenant: {tenant_id})."}


def delete_user(username: str, requesting_user: str, requesting_tenant: str = None) -> dict:
    """
    Supprime un utilisateur et TOUTES ses données.
    Si requesting_tenant est fourni, vérifie que l'utilisateur cible appartient au même tenant.
    """
    if username.strip() == requesting_user.strip():
        return {"status": "error", "message": "Impossible de supprimer son propre compte."}

    # Vérification d'appartenance au tenant (pour tenant_admin)
    if requesting_tenant:
        target_tenant = get_tenant_id(username.strip())
        if target_tenant != requesting_tenant:
            return {"status": "error", "message": "Utilisateur hors de votre tenant."}

    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("DELETE FROM users WHERE username = %s AND username != %s",
                  (username.strip(), requesting_user.strip()))
        if c.rowcount == 0:
            conn.rollback()
            return {"status": "error", "message": "Utilisateur introuvable."}
        for table in [
            "user_tools", "mail_memory", "aria_memory", "aria_rules",
            "aria_insights", "aria_hot_summary", "aria_style_examples",
            "aria_session_digests", "sent_mail_memory", "aria_profile",
            "oauth_tokens", "reply_learning_memory", "gmail_tokens"
        ]:
            c.execute(f"DELETE FROM {table} WHERE username = %s", (username.strip(),))
        conn.commit()
        return {"status": "ok", "message": f"Utilisateur '{username}' et toutes ses données supprimés."}
    except Exception as e:
        return {"status": "error", "message": str(e)[:100]}
    finally:
        if conn: conn.close()


def list_users() -> list:
    """Liste tous les utilisateurs (super-admin uniquement)."""
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("SELECT username, scope, tenant_id, last_login, created_at FROM users ORDER BY tenant_id, created_at")
        return [
            {"username": r[0], "scope": r[1], "tenant_id": r[2],
             "last_login": str(r[3]) if r[3] else None, "created_at": str(r[4])}
            for r in c.fetchall()
        ]
    except Exception:
        return []
    finally:
        if conn: conn.close()


def update_last_login(username: str):
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("UPDATE users SET last_login = NOW() WHERE username = %s", (username,))
        conn.commit()
    except Exception:
        pass
    finally:
        if conn: conn.close()


def get_current_user(request) -> str | None:
    return request.session.get("user")


LOGIN_PAGE_HTML = """
<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Aria — Connexion</title>
<style>
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{
    background: #0a0a0a; color: #fff;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif;
    display: flex; align-items: center; justify-content: center; min-height: 100vh;
}}
.card {{
    background: #111; border: 1px solid #1e1e1e; border-radius: 16px;
    padding: 40px; width: 100%; max-width: 380px; box-shadow: 0 8px 32px rgba(0,0,0,0.5);
}}
.logo {{ font-size: 32px; margin-bottom: 12px; }}
h1 {{ font-size: 24px; color: #e8e8e8; margin-bottom: 4px; font-weight: 700; }}
.subtitle {{ font-size: 13px; color: #555; margin-bottom: 36px; }}
label {{ font-size: 11px; color: #666; text-transform: uppercase; letter-spacing: 0.8px; display: block; }}
input[type=text], input[type=password] {{
    width: 100%; padding: 13px 16px; background: #161616; border: 1px solid #2a2a2a;
    border-radius: 10px; color: #e8e8e8; font-size: 15px; margin: 8px 0 22px;
    outline: none; transition: border-color 0.2s;
}}
input:focus {{ border-color: #1565c0; background: #1a1a1a; }}
button {{
    width: 100%; padding: 14px; background: #1565c0; color: white; border: none;
    border-radius: 10px; font-size: 15px; font-weight: 600; cursor: pointer;
    transition: background 0.15s; letter-spacing: 0.3px;
}}
button:hover {{ background: #1976d2; }}
.error {{
    background: rgba(220,50,50,0.1); border: 1px solid rgba(220,50,50,0.3);
    color: #ff7070; padding: 12px 16px; border-radius: 8px; font-size: 13px;
    margin-bottom: 24px; text-align: center;
}}
</style>
</head>
<body>
<div class="card">
    <div class="logo">⚡</div>
    <h1>Aria</h1>
    <div class="subtitle">Accès privé</div>
    {error_block}
    <form method="post" action="/login-app">
        <label>Identifiant</label>
        <input type="text" name="username" autocomplete="username" placeholder="Identifiant" required>
        <label>Mot de passe</label>
        <input type="password" name="password" autocomplete="current-password" placeholder="Mot de passe" required>
        <button type="submit">Se connecter →</button>
    </form>
</div>
</body>
</html>
"""
