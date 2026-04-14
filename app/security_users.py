"""
Gestion des utilisateurs : CRUD, auth, reset MDP, forçage redéfinition MDP.

USER-PHONE  : champ phone en base + get_user_phone(username) centralisé.
LOGIN-EMAIL : authenticate() accepte username OU email.
              resolve_username() retourne le vrai username depuis un login quelconque.
REFACTOR-5/6 : CRUD → user_crud.py, reset MDP → password_reset.py.
"""
import os
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


# ─── CRUD (tenant_id) ───

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


# Réexports depuis user_crud pour rétrocompatibilité
from app.user_crud import (  # noqa
    get_users_in_tenant, resolve_username, authenticate, get_user_scope,
    get_user_phone, create_user, update_user, delete_user, list_users,
)


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

    backup_username = os.getenv("BACKUP_ADMIN_USERNAME", "").strip()
    backup_password = os.getenv("BACKUP_ADMIN_PASSWORD", "").strip()
    if backup_username and backup_password:
        conn = None
        try:
            conn = get_pg_conn(); c = conn.cursor()
            c.execute("SELECT id FROM users WHERE username = %s", (backup_username,))
            if not c.fetchone():
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


# Réexports depuis password_reset pour rétrocompatibilité
from app.password_reset import (  # noqa
    generate_reset_token, validate_reset_token, consume_reset_token,
)
