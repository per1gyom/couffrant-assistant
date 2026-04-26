"""
CRUD utilisateurs : création, lecture, mise à jour, suppression.
Extrait de security_users.py — REFACTOR-6.
"""
from app.database import get_pg_conn
from app.security_auth import hash_password, verify_password
from app.security_tools import (
    ALL_SCOPES, SCOPE_ADMIN, SCOPE_USER, DEFAULT_TENANT,
    init_default_tools,
)


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


def resolve_username(login: str) -> str | None:
    """
    Retourne le vrai username à partir d'un identifiant qui peut être
    soit le username exact, soit l'adresse email (case-insensitive).
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
    """Verifie le mot de passe. Accepte username OU email comme identifiant.

    HOTFIX 26/04 (etape B.1a-1) : refuse les users soft-delete
    (deleted_at IS NOT NULL) meme si le password est valide. Utiliser
    is_user_deleted() pour differencier 401 (mauvais mdp) de 403
    (compte desactive) cote route login.
    """
    conn = None
    try:
        conn = get_pg_conn(); c = conn.cursor()
        c.execute("""
            SELECT password_hash, deleted_at FROM users
            WHERE username = %s OR lower(email) = lower(%s)
        """, (username.strip(), username.strip()))
        row = c.fetchone()
        if not row: return False
        if row[1] is not None: return False  # User soft-delete : refus
        return verify_password(password, row[0])
    except Exception:
        return False
    finally:
        if conn: conn.close()


def is_user_deleted(username: str) -> bool:
    """Retourne True si le user est soft-delete (deleted_at IS NOT NULL).
    Permet a la route login d'afficher 403 explicite au lieu d'un 401
    generique (decision Guillaume 26/04 : meilleure UX = le user sait
    qu'il doit contacter son admin)."""
    conn = None
    try:
        conn = get_pg_conn(); c = conn.cursor()
        c.execute(
            "SELECT deleted_at FROM users "
            "WHERE username = %s OR lower(email) = lower(%s)",
            (username.strip(), username.strip()),
        )
        row = c.fetchone()
        return bool(row and row[0] is not None)
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


def get_user_phone(username: str) -> str:
    """Retourne le numéro de téléphone de l'utilisateur (base puis env)."""
    import os
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
    """Crée un utilisateur. force_reset=True : MDP à changer à la 1ère connexion."""
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

    try:
        uta_role = "admin" if "admin" in scope else "user"
        uta_conn = get_pg_conn(); uta_c = uta_conn.cursor()
        uta_c.execute("""
            INSERT INTO user_tenant_access (username, tenant_id, role)
            VALUES (%s, %s, %s) ON CONFLICT (username, tenant_id) DO NOTHING
        """, (username.strip(), effective_tenant, uta_role))
        uta_conn.commit(); uta_conn.close()
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
    """Met à jour email, scope, display_name et/ou phone d'un utilisateur."""
    conn = None
    try:
        conn = get_pg_conn(); c = conn.cursor()
        if email is not None:
            c.execute("UPDATE users SET email=%s WHERE username=%s", (email or None, username))
        if scope is not None and scope in ALL_SCOPES:
            c.execute("UPDATE users SET scope=%s WHERE username=%s", (scope, username))
        if phone is not None:
            c.execute("UPDATE users SET phone=%s WHERE username=%s", (phone or None, username))
        if display_name is not None:
            c.execute("UPDATE users SET display_name=%s WHERE username=%s", (display_name or None, username))
        conn.commit()
        return {"status": "ok"}
    except Exception as e:
        return {"status": "error", "message": str(e)[:100]}
    finally:
        if conn: conn.close()


def delete_user(username: str, requesting_user: str, requesting_tenant: str = None) -> dict:
    """Soft-delete un utilisateur (refactor 26/04 etape B.1a-1).

    Pose deleted_at + deleted_by, conserve toutes les donnees du user
    intactes (rules, conversations, mails). Permet a un nouveau user
    (ex: Marc reprend le poste de Marie) de recuperer ces donnees plus
    tard via reassignation.

    La suppression DEFINITIVE des donnees passe par
    permanent_delete_user() (workflow 2 etapes : tenant_admin demande,
    super_admin valide).

    Idempotent : si le user est deja soft-delete, ne fait rien.
    """
    from app.security_users import get_tenant_id
    if username.strip() == requesting_user.strip():
        return {"status": "error", "message": "Impossible de supprimer son propre compte."}
    if requesting_tenant:
        if get_tenant_id(username.strip()) != requesting_tenant:
            return {"status": "error", "message": "Utilisateur hors de votre tenant."}
    conn = None
    try:
        conn = get_pg_conn(); c = conn.cursor()
        # Verifier que le user existe et n'est pas deja soft-delete
        c.execute(
            "SELECT deleted_at FROM users WHERE username=%s",
            (username.strip(),),
        )
        row = c.fetchone()
        if not row:
            return {"status": "error", "message": "Introuvable."}
        if row[0] is not None:
            return {"status": "ok", "message": f"'{username}' deja desactive."}

        # Soft-delete : marque le user, ne touche pas aux donnees
        c.execute(
            "UPDATE users SET deleted_at = NOW(), deleted_by = %s WHERE username = %s",
            (requesting_user.strip(), username.strip()),
        )
        conn.commit()
        return {
            "status": "ok",
            "message": f"'{username}' desactive. Donnees conservees, "
                       f"recuperables ulterieurement (reassignation possible "
                       f"a un nouveau user, ou purge definitive via super_admin).",
        }
    except Exception as e:
        return {"status": "error", "message": str(e)[:200]}
    finally:
        if conn: conn.close()


def permanent_delete_user(username: str, requesting_user: str) -> dict:
    """Purge DEFINITIVE des donnees d'un user (etape B.1a-1, super_admin
    only). Equivaut a l'ancien delete_user() : DELETE FROM users + DELETE
    en cascade + anonymisation des donnees collectives.

    A appeler uniquement apres validation explicite du super_admin
    (workflow request -> confirm). Operation irreversible.
    """
    if username.strip() == requesting_user.strip():
        return {"status": "error", "message": "Impossible de purger son propre compte."}
    conn = None
    try:
        conn = get_pg_conn(); c = conn.cursor()
        c.execute(
            "DELETE FROM users WHERE username=%s AND username!=%s",
            (username.strip(), requesting_user.strip()),
        )
        if c.rowcount == 0:
            return {"status": "error", "message": "Introuvable."}

        personal_tables = [
            "user_tools", "oauth_tokens", "gmail_tokens", "password_reset_tokens",
            "aria_memory", "aria_hot_summary", "aria_style_examples",
            "aria_session_digests", "aria_profile", "reply_learning_memory",
            "sent_mail_memory", "user_tenant_access", "proactive_alerts", "daily_reports",
            "email_signatures", "bug_reports", "user_topics",
        ]
        for table in personal_tables:
            try:
                c.execute(f"DELETE FROM {table} WHERE username=%s", (username.strip(),))
            except Exception:
                pass

        # Anonymisation des donnees collectives (gardees pour le tenant)
        anon = f"ancien_{username.strip()}"
        for table in ["aria_rules", "aria_insights", "aria_patterns",
                      "dossier_narratives", "mail_memory", "activity_log"]:
            try:
                c.execute(
                    f"UPDATE {table} SET username=%s WHERE username=%s",
                    (anon, username.strip()),
                )
            except Exception:
                pass

        conn.commit()
        return {
            "status": "ok",
            "message": f"'{username}' purge definitivement. "
                       f"Donnees collectives conservees sous '{anon}'.",
        }
    except Exception as e:
        return {"status": "error", "message": str(e)[:200]}
    finally:
        if conn: conn.close()


def list_users(include_deleted: bool = False) -> list:
    """Liste les users.

    HOTFIX 26/04 (etape B.1a-1) : ajout du parametre include_deleted
    (defaut False = exclut les users soft-delete). Le super_admin peut
    passer include_deleted=True pour avoir une vue complete (audit,
    restauration, purge definitive).
    """
    conn = None
    try:
        conn = get_pg_conn(); c = conn.cursor()
        where_clause = "" if include_deleted else "WHERE deleted_at IS NULL"
        c.execute(f"""
            SELECT username, email, scope, tenant_id, last_login, created_at,
                   COALESCE(account_locked, false), COALESCE(must_reset_password, false), phone,
                   COALESCE(suspended, false), suspended_reason, display_name,
                   deletion_requested_at, deleted_at, deleted_by
            FROM users {where_clause}
            ORDER BY tenant_id, created_at
        """)
        return [{
            "username": r[0], "email": r[1], "scope": r[2], "tenant_id": r[3],
            "last_login": str(r[4]) if r[4] else None, "created_at": str(r[5]),
            "account_locked": bool(r[6]), "must_reset_password": bool(r[7]),
            "phone": r[8] or "",
            "suspended": bool(r[9]), "suspended_reason": r[10] or "",
            "display_name": r[11] or "",
            "deletion_requested_at": str(r[12]) if r[12] else None,
            "deleted_at": str(r[13]) if r[13] else None,
            "deleted_by": r[14] or None,
        } for r in c.fetchall()]
    except Exception:
        return []
    finally:
        if conn: conn.close()
