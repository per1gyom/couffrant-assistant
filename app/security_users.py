"""
Gestion des utilisateurs : CRUD, auth, reset MDP.
"""
import os
import secrets
from datetime import datetime, timezone, timedelta
from app.database import get_pg_conn
from app.security_auth import hash_password, verify_password
from app.security_tools import (
    ALL_SCOPES, SCOPE_ADMIN, SCOPE_USER, DEFAULT_TENANT,
    init_default_tools,
)


def get_tenant_id(username: str) -> str:
    conn = None
    try:
        conn = get_pg_conn(); c = conn.cursor()
        c.execute("SELECT tenant_id FROM users WHERE username = %s", (username.strip(),))
        row = c.fetchone()
        return row[0] if row and row[0] else DEFAULT_TENANT
    except Exception:
        return DEFAULT_TENANT
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
    except Exception:
        return []
    finally:
        if conn: conn.close()


def authenticate(username: str, password: str) -> bool:
    conn = None
    try:
        conn = get_pg_conn(); c = conn.cursor()
        c.execute("SELECT password_hash FROM users WHERE username = %s", (username.strip(),))
        row = c.fetchone()
        if not row: return False
        return verify_password(password, row[0])
    except Exception:
        return False
    finally:
        if conn: conn.close()


def get_user_scope(username: str) -> str:
    from app.security_tools import SCOPE_USER
    conn = None
    try:
        conn = get_pg_conn(); c = conn.cursor()
        c.execute("SELECT scope FROM users WHERE username = %s", (username.strip(),))
        row = c.fetchone()
        return row[0] if row else SCOPE_USER
    except Exception:
        return SCOPE_USER
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
    except Exception:
        pass
    init_default_tools(username.strip(), scope)
    if tools:
        from app.security_tools import set_user_tool
        for t in tools:
            if "tool" in t:
                set_user_tool(username.strip(), t["tool"], t.get("access_level", "read_only"),
                              t.get("enabled", True), t.get("config", {}))
    return {"status": "ok", "message": f"Utilisateur '{username}' créé."}


def update_user(username: str, email: str = None, scope: str = None,
                display_name: str = None) -> dict:
    conn = None
    try:
        conn = get_pg_conn(); c = conn.cursor()
        if email is not None:
            c.execute("UPDATE users SET email=%s WHERE username=%s", (email or None, username))
        if scope is not None and scope in ALL_SCOPES:
            c.execute("UPDATE users SET scope=%s WHERE username=%s", (scope, username))
        conn.commit()
        return {"status": "ok"}
    except Exception as e:
        return {"status": "error", "message": str(e)[:100]}
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
        c.execute("DELETE FROM users WHERE username=%s AND username!=%s",
                  (username.strip(), requesting_user.strip()))
        if c.rowcount == 0: return {"status": "error", "message": "Introuvable."}
        for table in ["user_tools", "mail_memory", "aria_memory", "aria_rules", "aria_insights",
                      "aria_hot_summary", "aria_style_examples", "aria_session_digests",
                      "sent_mail_memory", "aria_profile", "oauth_tokens",
                      "reply_learning_memory", "gmail_tokens", "password_reset_tokens"]:
            c.execute(f"DELETE FROM {table} WHERE username=%s", (username.strip(),))
        conn.commit()
        return {"status": "ok", "message": f"'{username}' supprimé."}
    except Exception as e:
        return {"status": "error", "message": str(e)[:100]}
    finally:
        if conn: conn.close()


def list_users() -> list:
    conn = None
    try:
        conn = get_pg_conn(); c = conn.cursor()
        c.execute("SELECT username, email, scope, tenant_id, last_login, created_at FROM users ORDER BY tenant_id, created_at")
        return [{"username": r[0], "email": r[1], "scope": r[2], "tenant_id": r[3],
                 "last_login": str(r[4]) if r[4] else None, "created_at": str(r[5])}
                for r in c.fetchall()]
    except Exception:
        return []
    finally:
        if conn: conn.close()


def update_last_login(username: str):
    conn = None
    try:
        conn = get_pg_conn(); c = conn.cursor()
        c.execute("UPDATE users SET last_login=NOW() WHERE username=%s", (username,))
        conn.commit()
    except Exception:
        pass
    finally:
        if conn: conn.close()


def get_current_user(request):
    return request.session.get("user")


def init_default_user():
    try:
        from app.tenant_manager import ensure_default_tenant
        ensure_default_tenant()
    except Exception as e:
        print(f"[Tenant] {e}")

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
    except Exception as e:
        print(f"[Auth] {e}")
    finally:
        if conn: conn.close()

    init_default_tools(username, SCOPE_ADMIN)
    try:
        from app.memory_manager import seed_default_rules
        seed_default_rules(username)
    except Exception as e:
        print(f"[Seed] {e}")


# ─── RÉINITIALISATION MOT DE PASSE ───

def generate_reset_token(username: str, ttl_hours: int = 24) -> dict:
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(hours=ttl_hours)
    conn = None
    try:
        conn = get_pg_conn(); c = conn.cursor()
        c.execute("UPDATE password_reset_tokens SET used=true WHERE username=%s AND used=false", (username,))
        c.execute("""
            INSERT INTO password_reset_tokens (username, token, expires_at) VALUES (%s, %s, %s)
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

    return {"status": "ok", "token": token, "reset_url": reset_url,
            "email": user_email, "email_sent": email_sent, "expires_in": f"{ttl_hours}h"}


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
            s.starttls(); s.login(smtp_user, smtp_pass)
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
            SELECT username, expires_at FROM password_reset_tokens WHERE token=%s AND used=false
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
    except Exception:
        return None
    finally:
        if conn: conn.close()


def consume_reset_token(token: str, new_password: str) -> dict:
    if len(new_password) < 8:
        return {"status": "error", "message": "Mot de passe trop court (8 caractères min.)."}
    conn = None
    try:
        conn = get_pg_conn(); c = conn.cursor()
        c.execute("""
            SELECT username, expires_at FROM password_reset_tokens WHERE token=%s AND used=false FOR UPDATE
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
    except Exception as e:
        return {"status": "error", "message": str(e)[:100]}
    finally:
        if conn: conn.close()
