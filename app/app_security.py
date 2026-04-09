import hashlib
import hmac
import os
import base64
import time
import json
import secrets
from datetime import datetime, timezone, timedelta
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
# SCOPES
# ─────────────────────────────────────────
SCOPE_ADMIN        = "admin"
SCOPE_TENANT_ADMIN = "tenant_admin"
SCOPE_CS           = "couffrant_solar"  # legacy
SCOPE_USER         = "user"
DEFAULT_TENANT     = "couffrant_solar"
TENANT_ADMIN_SCOPES = (SCOPE_ADMIN, SCOPE_TENANT_ADMIN)
USER_SCOPES         = (SCOPE_CS, SCOPE_USER)
ALL_SCOPES          = (SCOPE_ADMIN, SCOPE_TENANT_ADMIN, SCOPE_CS, SCOPE_USER)


DEFAULT_TOOLS_ADMIN = [
    {"tool": "outlook", "access_level": "full",      "config": {"mailboxes": [], "can_delete_mail": True}},
    {"tool": "odoo",    "access_level": "full",      "config": {}},
    {"tool": "drive",   "access_level": "full",      "config": {"can_delete": True}},
    {"tool": "gmail",   "access_level": "full",      "config": {}},
]
DEFAULT_TOOLS_TENANT_ADMIN = [
    {"tool": "outlook", "access_level": "full",  "config": {"mailboxes": [], "can_delete_mail": True}},
    {"tool": "odoo",    "access_level": "full",  "config": {}},
    {"tool": "drive",   "access_level": "full",  "config": {"can_delete": True}},
]
DEFAULT_TOOLS_USER = [
    {"tool": "outlook", "access_level": "write",     "config": {"mailboxes": [], "can_delete_mail": False}},
    {"tool": "odoo",    "access_level": "read_only", "config": {"shared_user": "sabrina"}},
    {"tool": "drive",   "access_level": "write",     "config": {"can_delete": False}},
]
DEFAULT_TOOLS_CS = DEFAULT_TOOLS_USER

def _tools_for_scope(scope: str) -> list:
    if scope == SCOPE_ADMIN: return DEFAULT_TOOLS_ADMIN
    if scope == SCOPE_TENANT_ADMIN: return DEFAULT_TOOLS_TENANT_ADMIN
    return DEFAULT_TOOLS_USER


def init_default_tools(username: str, scope: str):
    conn = None
    try:
        conn = get_pg_conn(); c = conn.cursor()
        for t in _tools_for_scope(scope):
            c.execute("""
                INSERT INTO user_tools (username, tool, access_level, enabled, config)
                VALUES (%s, %s, %s, true, %s) ON CONFLICT (username, tool) DO NOTHING
            """, (username, t["tool"], t["access_level"], json.dumps(t["config"])))
        conn.commit()
    except Exception as e: print(f"[Tools] Erreur {username}: {e}")
    finally:
        if conn: conn.close()


def get_user_tools(username: str, raw: bool = False):
    conn = None
    try:
        conn = get_pg_conn(); c = conn.cursor()
        c.execute("SELECT tool, access_level, enabled, config FROM user_tools WHERE username = %s ORDER BY tool", (username,))
        rows = c.fetchall()
        if raw: return [{"tool": r[0], "access_level": r[1], "enabled": r[2], "config": r[3] or {}} for r in rows]
        return {r[0]: {"access_level": r[1], "enabled": r[2], "config": r[3] or {}} for r in rows}
    except Exception: return [] if raw else {}
    finally:
        if conn: conn.close()


def get_tool_config(username: str, tool: str) -> dict:
    conn = None
    try:
        conn = get_pg_conn(); c = conn.cursor()
        c.execute("SELECT access_level, enabled, config FROM user_tools WHERE username=%s AND tool=%s", (username, tool))
        row = c.fetchone()
        if not row: return {"access_level": "none", "enabled": False, "config": {}}
        return {"access_level": row[0], "enabled": row[1], "config": row[2] or {}}
    except Exception: return {"access_level": "none", "enabled": False, "config": {}}
    finally:
        if conn: conn.close()


def set_user_tool(username: str, tool: str, access_level: str = "read_only",
                  enabled: bool = True, config: dict = None) -> dict:
    conn = None
    try:
        conn = get_pg_conn(); c = conn.cursor()
        c.execute("""
            INSERT INTO user_tools (username, tool, access_level, enabled, config, updated_at)
            VALUES (%s, %s, %s, %s, %s, NOW())
            ON CONFLICT (username, tool) DO UPDATE SET
                access_level=EXCLUDED.access_level, enabled=EXCLUDED.enabled,
                config=EXCLUDED.config, updated_at=NOW()
        """, (username, tool, access_level, enabled, json.dumps(config or {})))
        conn.commit()
        return {"status": "ok", "message": f"Outil '{tool}' configuré ({access_level})."}
    except Exception as e: return {"status": "error", "message": str(e)[:100]}
    finally:
        if conn: conn.close()


def remove_user_tool(username: str, tool: str) -> dict:
    conn = None
    try:
        conn = get_pg_conn(); c = conn.cursor()
        c.execute("DELETE FROM user_tools WHERE username=%s AND tool=%s", (username, tool))
        if c.rowcount == 0: return {"status": "error", "message": "Outil introuvable."}
        conn.commit()
        return {"status": "ok"}
    except Exception as e: return {"status": "error", "message": str(e)[:100]}
    finally:
        if conn: conn.close()


# ─────────────────────────────────────────
# UTILISATEURS
# ─────────────────────────────────────────

def get_tenant_id(username: str) -> str:
    conn = None
    try:
        conn = get_pg_conn(); c = conn.cursor()
        c.execute("SELECT tenant_id FROM users WHERE username = %s", (username.strip(),))
        row = c.fetchone()
        return row[0] if row and row[0] else DEFAULT_TENANT
    except Exception: return DEFAULT_TENANT
    finally:
        if conn: conn.close()


def get_users_in_tenant(tenant_id: str) -> list:
    conn = None
    try:
        conn = get_pg_conn(); c = conn.cursor()
        c.execute("""
            SELECT username, email, scope, last_login, created_at
            FROM users WHERE tenant_id = %s ORDER BY created_at
        """, (tenant_id,))
        return [{"username": r[0], "email": r[1], "scope": r[2],
                 "last_login": str(r[3]) if r[3] else None, "created_at": str(r[4])}
                for r in c.fetchall()]
    except Exception: return []
    finally:
        if conn: conn.close()


def init_default_user():
    try:
        from app.tenant_manager import ensure_default_tenant
        ensure_default_tenant()
    except Exception as e: print(f"[Tenant] {e}")

    username = os.getenv("APP_USERNAME", "guillaume").strip()
    password = os.getenv("APP_PASSWORD", "couffrant2026").strip()
    email    = os.getenv("APP_ADMIN_EMAIL", "").strip()

    conn = None
    try:
        conn = get_pg_conn(); c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM users")
        if c.fetchone()[0] == 0:
            c.execute("""
                INSERT INTO users (username, password_hash, email, scope, tenant_id)
                VALUES (%s, %s, %s, %s, %s) ON CONFLICT (username) DO NOTHING
            """, (username, hash_password(password), email or None, SCOPE_ADMIN, DEFAULT_TENANT))
            conn.commit()
        else:
            c.execute("""
                UPDATE users SET scope=%s, tenant_id=COALESCE(NULLIF(tenant_id,''),%s)
                WHERE username=%s AND scope='couffrant_solar'
            """, (SCOPE_ADMIN, DEFAULT_TENANT, username))
            conn.commit()
    except Exception as e: print(f"[Auth] {e}")
    finally:
        if conn: conn.close()

    init_default_tools(username, SCOPE_ADMIN)
    try:
        from app.memory_manager import seed_default_rules
        seed_default_rules(username)
    except Exception as e: print(f"[Seed] {e}")


def authenticate(username: str, password: str) -> bool:
    conn = None
    try:
        conn = get_pg_conn(); c = conn.cursor()
        c.execute("SELECT password_hash FROM users WHERE username = %s", (username.strip(),))
        row = c.fetchone()
        if not row: return False
        return verify_password(password, row[0])
    except Exception: return False
    finally:
        if conn: conn.close()


def get_user_scope(username: str) -> str:
    conn = None
    try:
        conn = get_pg_conn(); c = conn.cursor()
        c.execute("SELECT scope FROM users WHERE username = %s", (username.strip(),))
        row = c.fetchone()
        return row[0] if row else SCOPE_USER
    except Exception: return SCOPE_USER
    finally:
        if conn: conn.close()


def create_user(username: str, password: str, scope: str = SCOPE_USER,
                tools: list = None, tenant_id: str = DEFAULT_TENANT,
                email: str = None) -> dict:
    if not username or not password:
        return {"status": "error", "message": "Identifiant et mot de passe requis."}
    if len(password) < 8:
        return {"status": "error", "message": "Mot de passe trop court (8 caractères min.)."}
    if scope not in ALL_SCOPES:
        scope = SCOPE_USER
    conn = None
    try:
        conn = get_pg_conn(); c = conn.cursor()
        c.execute("""
            INSERT INTO users (username, password_hash, email, scope, tenant_id)
            VALUES (%s, %s, %s, %s, %s)
        """, (username.strip(), hash_password(password), email or None, scope, tenant_id or DEFAULT_TENANT))
        conn.commit()
    except Exception as e:
        if "unique" in str(e).lower():
            return {"status": "error", "message": f"'{username}' existe déjà."}
        return {"status": "error", "message": str(e)[:100]}
    finally:
        if conn: conn.close()
    try:
        from app.memory_manager import seed_default_rules
        seed_default_rules(username.strip())
    except Exception: pass
    init_default_tools(username.strip(), scope)
    if tools:
        for t in tools:
            if "tool" in t:
                set_user_tool(username.strip(), t["tool"], t.get("access_level","read_only"), t.get("enabled",True), t.get("config",{}))
    return {"status": "ok", "message": f"Utilisateur '{username}' créé."}


def update_user(username: str, email: str = None, scope: str = None,
               display_name: str = None) -> dict:
    """Met à jour email et/ou scope d'un utilisateur."""
    conn = None
    try:
        conn = get_pg_conn(); c = conn.cursor()
        if email is not None:
            c.execute("UPDATE users SET email=%s WHERE username=%s", (email or None, username))
        if scope is not None and scope in ALL_SCOPES:
            c.execute("UPDATE users SET scope=%s WHERE username=%s", (scope, username))
        conn.commit()
        return {"status": "ok"}
    except Exception as e: return {"status": "error", "message": str(e)[:100]}
    finally:
        if conn: conn.close()


def delete_user(username: str, requesting_user: str, requesting_tenant: str = None) -> dict:
    if username.strip() == requesting_user.strip():
        return {"status": "error", "message": "Impossible de supprimer son propre compte."}
    if requesting_tenant:
        if get_tenant_id(username.strip()) != requesting_tenant:
            return {"status": "error", "message": "Utilisateur hors de votre tenant."}
    conn = None
    try:
        conn = get_pg_conn(); c = conn.cursor()
        c.execute("DELETE FROM users WHERE username=%s AND username!=%s", (username.strip(), requesting_user.strip()))
        if c.rowcount == 0: return {"status": "error", "message": "Introuvable."}
        for table in ["user_tools","mail_memory","aria_memory","aria_rules","aria_insights",
                      "aria_hot_summary","aria_style_examples","aria_session_digests",
                      "sent_mail_memory","aria_profile","oauth_tokens",
                      "reply_learning_memory","gmail_tokens","password_reset_tokens"]:
            c.execute(f"DELETE FROM {table} WHERE username=%s", (username.strip(),))
        conn.commit()
        return {"status": "ok", "message": f"'{username}' supprimé."}
    except Exception as e: return {"status": "error", "message": str(e)[:100]}
    finally:
        if conn: conn.close()


def list_users() -> list:
    conn = None
    try:
        conn = get_pg_conn(); c = conn.cursor()
        c.execute("SELECT username, email, scope, tenant_id, last_login, created_at FROM users ORDER BY tenant_id, created_at")
        return [{"username":r[0],"email":r[1],"scope":r[2],"tenant_id":r[3],
                 "last_login":str(r[4]) if r[4] else None,"created_at":str(r[5])} for r in c.fetchall()]
    except Exception: return []
    finally:
        if conn: conn.close()


def update_last_login(username: str):
    conn = None
    try:
        conn = get_pg_conn(); c = conn.cursor()
        c.execute("UPDATE users SET last_login=NOW() WHERE username=%s", (username,))
        conn.commit()
    except Exception: pass
    finally:
        if conn: conn.close()


def get_current_user(request) -> str | None:
    return request.session.get("user")


# ─────────────────────────────────────────
# RÉINITIALISATION MOT DE PASSE
# ─────────────────────────────────────────

def generate_reset_token(username: str, ttl_hours: int = 24) -> dict:
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(hours=ttl_hours)
    conn = None
    try:
        conn = get_pg_conn(); c = conn.cursor()
        c.execute("UPDATE password_reset_tokens SET used=true WHERE username=%s AND used=false", (username,))
        c.execute("""
            INSERT INTO password_reset_tokens (username, token, expires_at)
            VALUES (%s, %s, %s)
        """, (username, token, expires_at))
        c.execute("SELECT email FROM users WHERE username=%s", (username,))
        row = c.fetchone()
        user_email = row[0] if row else None
        conn.commit()
    finally:
        if conn: conn.close()

    base_url = os.getenv("APP_BASE_URL", "https://couffrant-assistant-production.up.railway.app")
    reset_url = f"{base_url}/reset-password?token={token}"

    email_sent = False
    if user_email:
        email_sent = _send_reset_email(user_email, username, reset_url)

    return {
        "status": "ok",
        "token": token,
        "reset_url": reset_url,
        "email": user_email,
        "email_sent": email_sent,
        "expires_in": f"{ttl_hours}h",
    }


def _send_reset_email(to_email: str, username: str, reset_url: str) -> bool:
    smtp_host = os.getenv("SMTP_HOST")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER")
    smtp_pass = os.getenv("SMTP_PASS")
    smtp_from = os.getenv("SMTP_FROM", smtp_user or "noreply@raya-app.fr")
    if not smtp_host or not smtp_user or not smtp_pass:
        return False
    try:
        import smtplib
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart
        msg = MIMEMultipart("alternative")
        msg["Subject"] = "Réinitialisation de votre mot de passe Raya"
        msg["From"] = smtp_from
        msg["To"] = to_email
        html = f"""<p>Bonjour {username},</p>
<p>Voici votre lien de réinitialisation de mot de passe. Il est valable 24h.</p>
<p><a href="{reset_url}">Réinitialiser mon mot de passe</a></p>
<p>Si vous n'avez pas demandé cette réinitialisation, ignorez cet email.</p>"""
        msg.attach(MIMEText(html, "html"))
        with smtplib.SMTP(smtp_host, smtp_port) as s:
            s.starttls()
            s.login(smtp_user, smtp_pass)
            s.sendmail(smtp_from, to_email, msg.as_string())
        return True
    except Exception as e:
        print(f"[SMTP] Erreur envoi email: {e}")
        return False


def validate_reset_token(token: str) -> dict | None:
    conn = None
    try:
        conn = get_pg_conn(); c = conn.cursor()
        c.execute("""
            SELECT username, expires_at FROM password_reset_tokens
            WHERE token=%s AND used=false
        """, (token,))
        row = c.fetchone()
        if not row: return None
        username, expires_at = row
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at < datetime.now(timezone.utc): return None
        c.execute("SELECT email FROM users WHERE username=%s", (username,))
        urow = c.fetchone()
        return {"username": username, "email": urow[0] if urow else None}
    except Exception: return None
    finally:
        if conn: conn.close()


def consume_reset_token(token: str, new_password: str) -> dict:
    if len(new_password) < 8:
        return {"status": "error", "message": "Mot de passe trop court (8 caractères min.)."}
    conn = None
    try:
        conn = get_pg_conn(); c = conn.cursor()
        c.execute("""
            SELECT username, expires_at FROM password_reset_tokens
            WHERE token=%s AND used=false FOR UPDATE
        """, (token,))
        row = c.fetchone()
        if not row: return {"status": "error", "message": "Lien invalide ou déjà utilisé."}
        username, expires_at = row
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at < datetime.now(timezone.utc):
            return {"status": "error", "message": "Lien expiré. Demandez-en un nouveau."}
        c.execute("UPDATE users SET password_hash=%s WHERE username=%s", (hash_password(new_password), username))
        c.execute("UPDATE password_reset_tokens SET used=true WHERE token=%s", (token,))
        conn.commit()
        return {"status": "ok", "message": "Mot de passe mis à jour."}
    except Exception as e: return {"status": "error", "message": str(e)[:100]}
    finally:
        if conn: conn.close()


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
  {error_block}
  <form method="post" action="/login-app">
    <label>Identifiant</label><input type="text" name="username" autocomplete="username" required>
    <label>Mot de passe</label><input type="password" name="password" autocomplete="current-password" required>
    <button type="submit">Se connecter →</button>
  </form>
  <p style="text-align:center;margin-top:16px"><a href="/forgot-password" style="font-size:12px;color:#555">Mot de passe oublié ?</a></p>
</div></body></html>
"""
