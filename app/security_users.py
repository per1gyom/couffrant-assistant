"""
Gestion des utilisateurs : CRUD, auth, reset MDP, forçage redéfinition MDP.

USER-PHONE  : champ phone en base + get_user_phone(username) centralisé.
LOGIN-EMAIL : authenticate() accepte username OU email.
              resolve_username() retourne le vrai username depuis un login quelconque.
"""
import os
import secrets
from datetime import datetime, timezone, timedelta
from app.database import get_pg_conn
from app.security_auth import hash_password, verify_password, validate_password_strength
from app.security_tools import (
    ALL_SCOPES, SCOPE_ADMIN, SCOPE_USER, DEFAULT_TENANT,
    init_default_tools,
)


# ─── MIGRATIONS ───

def _ensure_security_columns():
    """Migration : ajoute les colonnes de sécurité si absentes."""
    conn = None
    try:
        conn = get_pg_conn(); c = conn.cursor()
        c.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS must_reset_password BOOLEAN DEFAULT FALSE")
        c.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS account_locked BOOLEAN DEFAULT FALSE")
        conn.commit()
    except Exception as e:
        print(f"[Migration] {e}")
    finally:
        if conn: conn.close()


# ─── FLAG MUST_RESET_PASSWORD ───

def must_reset_password_check(username: str) -> bool:
    conn = None
    try:
        conn = get_pg_conn(); c = conn.cursor()
        c.execute("SELECT must_reset_password FROM users WHERE username=%s", (username,))
        row = c.fetchone()
        return bool(row[0]) if row else False
    except Exception:
        return False
    finally:
        if conn: conn.close()


def set_must_reset_password(username: str, value: bool = True):
    conn = None
    try:
        conn = get_pg_conn(); c = conn.cursor()
        c.execute("UPDATE users SET must_reset_password=%s WHERE username=%s", (value, username))
        conn.commit()
    except Exception as e:
        print(f"[Auth] set_must_reset_password: {e}")
    finally:
        if conn: conn.close()


# ─── CRUD ───

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


# ─── LOGIN PAR EMAIL (USER-PHONE / LOGIN-EMAIL) ───

def resolve_username(login: str) -> str | None:
    """
    Retourne le vrai username à partir d'un identifiant qui peut être
    soit le username exact, soit l'adresse email (case-insensitive).
    Utilisé pour le login par email.
    """
    conn = None
    try:
        conn = get_pg_conn(); c = conn.cursor()
        c.execute("""
            SELECT username FROM users
            WHERE username = %s OR lower(email) = lower(%s)
            LIMIT 1
        """, (login.strip(), login.strip()))
        row = c.fetchone()
        return row[0] if row else None
    except Exception:
        return None
    finally:
        if conn: conn.close()


def authenticate(username: str, password: str) -> bool:
    """
    Vérifie le mot de passe. Accepte username OU email comme identifiant.
    Retourne True si les credentials sont valides, False sinon.
    """
    conn = None
    try:
        conn = get_pg_conn(); c = conn.cursor()
        c.execute("""
            SELECT password_hash FROM users
            WHERE username = %s OR lower(email) = lower(%s)
        """, (username.strip(), username.strip()))
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


# ─── TÉLÉPHONE UTILISATEUR (USER-PHONE) ───

def get_user_phone(username: str) -> str:
    """
    Retourne le numéro de téléphone de l'utilisateur.
    Cherche d'abord dans la colonne phone de la table users,
    puis se rabat sur les variables d'environnement (compatibilité).

    Priorité des variables d'env :
      NOTIFICATION_PHONE_{USERNAME}
      NOTIFICATION_PHONE_ADMIN
      NOTIFICATION_PHONE_GUILLAUME
      NOTIFICATION_PHONE_DEFAULT
    """
    # 1. Chercher en base (priorité)
    conn = None
    try:
        conn = get_pg_conn(); c = conn.cursor()
        c.execute("SELECT phone FROM users WHERE username = %s", (username.strip(),))
        row = c.fetchone()
        if row and row[0] and row[0].strip():
            return row[0].strip()
    except Exception:
        pass
    finally:
        if conn: conn.close()

    # 2. Fallback variables d'environnement (compatibilité ascendante)
    phone = os.getenv(f"NOTIFICATION_PHONE_{username.upper()}", "").strip()
    if not phone:
        phone = os.getenv("NOTIFICATION_PHONE_ADMIN", "").strip()
    if not phone:
        phone = os.getenv("NOTIFICATION_PHONE_GUILLAUME", "").strip()
    if not phone:
        phone = os.getenv("NOTIFICATION_PHONE_DEFAULT", "").strip()
    return phone


def create_user(username: str, password: str, scope: str = SCOPE_USER,
                tools: list = None, tenant_id: str = DEFAULT_TENANT,
                email: str = None, phone: str = None,
                force_reset: bool = True) -> dict:
    """
    Crée un utilisateur.
    force_reset=True (défaut) : l'utilisateur devra changer son mot de passe à la première connexion.
    Après création, insère dans user_tenant_access (BUG 1).
    phone : numéro de téléphone pour les notifications WhatsApp/SMS (optionnel).
    """
    if not username or not password:
        return {"status": "error", "message": "Identifiant et mot de passe requis."}
    if len(password) < 8:
        return {"status": "error", "message": "Mot de passe temporaire trop court (8 caractères min.)."}
    if scope not in ALL_SCOPES:
        scope = SCOPE_USER
    effective_tenant = (tenant_id or DEFAULT_TENANT).strip()
    conn = None
    try:
        conn = get_pg_conn(); c = conn.cursor()
        c.execute("""
            INSERT INTO users (username, password_hash, email, phone, scope, tenant_id, must_reset_password)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (username.strip(), hash_password(password), email or None,
               phone or None, scope, effective_tenant, force_reset))
        conn.commit()
    except Exception as e:
        if "unique" in str(e).lower():
            return {"status": "error", "message": f"'{username}' existe déjà."}
        return {"status": "error", "message": str(e)[:100]}
    finally:
        if conn: conn.close()

    # BUG 1 : Enregistrer dans user_tenant_access
    try:
        uta_role = "admin" if "admin" in scope else "user"
        uta_conn = get_pg_conn()
        uta_c = uta_conn.cursor()
        uta_c.execute("""
            INSERT INTO user_tenant_access (username, tenant_id, role)
            VALUES (%s, %s, %s)
            ON CONFLICT (username, tenant_id) DO NOTHING
        """, (username.strip(), effective_tenant, uta_role))
        uta_conn.commit()
        uta_conn.close()
    except Exception as e:
        print(f"[create_user] user_tenant_access non mis à jour: {e}")

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
                display_name: str = None, phone: str = None) -> dict:
    """Met à jour email, scope et/ou phone d'un utilisateur."""
    conn = None
    try:
        conn = get_pg_conn(); c = conn.cursor()
        if email is not None:
            c.execute("UPDATE users SET email=%s WHERE username=%s", (email or None, username))
        if scope is not None and scope in ALL_SCOPES:
            c.execute("UPDATE users SET scope=%s WHERE username=%s", (scope, username))
        if phone is not None:
            c.execute("UPDATE users SET phone=%s WHERE username=%s", (phone or None, username))
        conn.commit()
        return {"status": "ok"}
    except Exception as e:
        return {"status": "error", "message": str(e)[:100]}
    finally:
        if conn: conn.close()


def delete_user(username: str, requesting_user: str, requesting_tenant: str = None) -> dict:
    """
    Supprime un utilisateur.

    DONNÉES SUPPRIMÉES (privées / personnelles) :
      user_tools, oauth_tokens, gmail_tokens, password_reset_tokens,
      aria_memory, aria_hot_summary, aria_style_examples, aria_session_digests,
      aria_profile, reply_learning_memory, sent_mail_memory,
      user_tenant_access, proactive_alerts, daily_reports

    DONNÉES CONSERVÉES (intelligence collective) — anonymisées sous 'ancien_<username>' :
      aria_rules, aria_insights, aria_patterns, dossier_narratives,
      mail_memory, activity_log
    (BUG 3 — FIX-BUGS-AUDIT)
    """
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
        if c.rowcount == 0:
            return {"status": "error", "message": "Introuvable."}

        # ─ Données personnelles/privées — suppression complète
        personal_tables = [
            "user_tools", "oauth_tokens", "gmail_tokens", "password_reset_tokens",
            "aria_memory", "aria_hot_summary", "aria_style_examples",
            "aria_session_digests", "aria_profile", "reply_learning_memory",
            "sent_mail_memory", "user_tenant_access", "proactive_alerts", "daily_reports",
        ]
        for table in personal_tables:
            try:
                c.execute(f"DELETE FROM {table} WHERE username=%s", (username.strip(),))
            except Exception:
                pass  # Table absente → on ignore silencieusement

        # ─ Intelligence collective — anonymisation (l'expérience profite au collectif)
        anon = f"ancien_{username.strip()}"
        collective_tables = [
            "aria_rules", "aria_insights", "aria_patterns",
            "dossier_narratives", "mail_memory", "activity_log",
        ]
        for table in collective_tables:
            try:
                c.execute(f"UPDATE {table} SET username=%s WHERE username=%s",
                          (anon, username.strip()))
            except Exception:
                pass  # Table absente → on ignore silencieusement

        conn.commit()
        return {
            "status": "ok",
            "message": (
                f"'{username}' supprimé. Les règles, insights et narratives "
                f"sont conservés sous '" + anon + "' pour l'intelligence collective."
            ),
        }
    except Exception as e:
        return {"status": "error", "message": str(e)[:100]}
    finally:
        if conn: conn.close()


def list_users() -> list:
    conn = None
    try:
        conn = get_pg_conn(); c = conn.cursor()
        c.execute("""
            SELECT username, email, scope, tenant_id, last_login, created_at,
                   COALESCE(account_locked, false), COALESCE(must_reset_password, false),
                   phone
            FROM users ORDER BY tenant_id, created_at
        """)
        return [{
            "username": r[0], "email": r[1], "scope": r[2], "tenant_id": r[3],
            "last_login": str(r[4]) if r[4] else None, "created_at": str(r[5]),
            "account_locked": bool(r[6]), "must_reset_password": bool(r[7]),
            "phone": r[8] or "",
        } for r in c.fetchall()]
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
    _ensure_security_columns()

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
                INSERT INTO users (username, password_hash, email, scope, tenant_id, must_reset_password)
                VALUES (%s, %s, %s, %s, %s, false) ON CONFLICT (username) DO NOTHING
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

    # Compte admin de secours
    backup_username = os.getenv("BACKUP_ADMIN_USERNAME", "").strip()
    backup_password = os.getenv("BACKUP_ADMIN_PASSWORD", "").strip()
    if backup_username and backup_password:
        conn = None
        try:
            conn = get_pg_conn(); c = conn.cursor()
            c.execute("SELECT id FROM users WHERE username = %s", (backup_username,))
            if not c.fetchone():
                from app.security_auth import hash_password
                c.execute(
                    "INSERT INTO users (username, password_hash, scope, tenant_id) VALUES (%s, %s, %s, %s)",
                    (backup_username, hash_password(backup_password), "super_admin", "couffrant_solar")
                )
                conn.commit()
                print(f"[Security] Compte admin de secours '{backup_username}' créé")
        except Exception as e:
            print(f"[Security] Erreur création admin secours: {e}")
        finally:
            if conn: conn.close()


# ─── RÉINITIALISATION MOT DE PASSE ───

def generate_reset_token(username: str, ttl_hours: int = 24) -> dict:
    """
    Génère un lien de réinitialisation.
    Active aussi must_reset_password pour forcer la redéfinition à la prochaine connexion.
    """
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
        c.execute("UPDATE users SET must_reset_password=true WHERE username=%s", (username,))
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
    smtp_from = os.getenv("SMTP_FROM", smtp_user or "noreply@raya-ia.fr")
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
    """Consomme un token de reset. Valide la force du MDP avant de l'enregistrer."""
    ok, msg = validate_password_strength(new_password)
    if not ok:
        return {"status": "error", "message": msg}
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
        c.execute("""
            UPDATE users SET password_hash=%s, must_reset_password=false WHERE username=%s
        """, (hash_password(new_password), username))
        c.execute("UPDATE password_reset_tokens SET used=true WHERE token=%s", (token,))
        conn.commit()
        return {"status": "ok", "message": "Mot de passe mis à jour."}
    except Exception as e:
        return {"status": "error", "message": str(e)[:100]}
    finally:
        if conn: conn.close()
