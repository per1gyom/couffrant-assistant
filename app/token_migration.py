"""
Migration des tokens OAuth vers tenant_connections.

Toutes les connexions OAuth sont migrées depuis :
  - oauth_tokens  (provider='microsoft'|'google', per user)
  - gmail_tokens  (per user, legacy)

vers :
  - tenant_connections + connection_assignments

La migration est IDEMPOTENTE — sans danger à appeler plusieurs fois.
Elle s'exécute au démarrage de l'app via startup_event().
"""
import json
from datetime import datetime, timezone, timedelta
from app.database import get_pg_conn
from app.logging_config import get_logger

logger = get_logger("raya.token_migration")


def migrate_tokens_to_v2():
    """
    Migre tous les tokens OAuth legacy vers tenant_connections.
    Idempotent : ne crée pas de doublons.
    """
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()

        # Récupérer le tenant_id de chaque user
        c.execute("SELECT username, tenant_id FROM users")
        user_tenants = {row[0]: row[1] for row in c.fetchall()}

        migrated = 0

        # 1. Migrer oauth_tokens (Microsoft + Google)
        c.execute("""
            SELECT provider, username, access_token, refresh_token, expires_at
            FROM oauth_tokens
            WHERE provider IN ('microsoft', 'google')
        """)
        rows = c.fetchall()

        for provider, username, access_token, refresh_token, expires_at in rows:
            tool_type = "microsoft" if provider == "microsoft" else "gmail"
            tenant_id = user_tenants.get(username)
            if not tenant_id:
                continue

            # Vérifier si une connexion V2 existe déjà pour cet utilisateur
            c.execute("""
                SELECT tc.id FROM tenant_connections tc
                JOIN connection_assignments ca ON ca.connection_id = tc.id
                WHERE tc.tenant_id = %s AND tc.tool_type = %s AND ca.username = %s
                LIMIT 1
            """, (tenant_id, tool_type, username))
            if c.fetchone():
                continue  # Déjà migré

            # Créer la connexion V2
            expires_str = expires_at.isoformat() if expires_at else (
                datetime.now(timezone.utc) + timedelta(hours=1)
            ).isoformat()
            credentials = json.dumps({
                "access_token": access_token or "",
                "refresh_token": refresh_token or "",
                "expires_at": expires_str,
            })

            # Récupérer l'email du compte
            email = _get_user_email_for_provider(c, username, tool_type)
            label = email or f"{tool_type.title()} ({username})"

            c.execute("""
                INSERT INTO tenant_connections
                    (tenant_id, tool_type, label, auth_type, credentials,
                     connected_email, status, created_by)
                VALUES (%s, %s, %s, 'oauth', %s, %s, 'connected', 'auto_migration')
                RETURNING id
            """, (tenant_id, tool_type, label, credentials, email or None))
            conn_id = c.fetchone()[0]

            # Créer l'assignation
            c.execute("""
                INSERT INTO connection_assignments (connection_id, username, access_level, enabled)
                VALUES (%s, %s, 'full', true)
                ON CONFLICT (connection_id, username) DO NOTHING
            """, (conn_id, username))

            migrated += 1
            logger.info("[Migration] %s → tenant_connections #%d (%s, %s)", 
                        tool_type, conn_id, username, email)

        # 2. Migrer gmail_tokens (si pas déjà couvert par oauth_tokens)
        c.execute("SELECT username, email, access_token, refresh_token FROM gmail_tokens")
        gmail_rows = c.fetchall()

        for username, email, access_token, refresh_token in gmail_rows:
            tenant_id = user_tenants.get(username)
            if not tenant_id:
                continue

            c.execute("""
                SELECT tc.id FROM tenant_connections tc
                JOIN connection_assignments ca ON ca.connection_id = tc.id
                WHERE tc.tenant_id = %s AND tc.tool_type = 'gmail' AND ca.username = %s
                LIMIT 1
            """, (tenant_id, username))
            if c.fetchone():
                continue

            credentials = json.dumps({
                "access_token": access_token or "",
                "refresh_token": refresh_token or "",
                "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
            })
            label = email or f"Gmail ({username})"

            c.execute("""
                INSERT INTO tenant_connections
                    (tenant_id, tool_type, label, auth_type, credentials,
                     connected_email, status, created_by)
                VALUES (%s, 'gmail', %s, 'oauth', %s, %s, 'connected', 'auto_migration')
                RETURNING id
            """, (tenant_id, label, credentials, email or None))
            conn_id = c.fetchone()[0]

            c.execute("""
                INSERT INTO connection_assignments (connection_id, username, access_level, enabled)
                VALUES (%s, %s, 'full', true)
                ON CONFLICT (connection_id, username) DO NOTHING
            """, (conn_id, username))

            migrated += 1
            logger.info("[Migration] gmail_tokens → tenant_connections #%d (%s, %s)",
                        conn_id, username, email)

        conn.commit()
        if migrated:
            logger.info("[Migration] %d connexion(s) migrée(s) vers tenant_connections.", migrated)
        else:
            logger.debug("[Migration] Rien à migrer (déjà à jour).")

    except Exception as e:
        logger.error("[Migration] Erreur : %s", e)
        if conn:
            try:
                conn.rollback()
            except Exception:
                pass
    finally:
        if conn:
            conn.close()


def _get_user_email_for_provider(cursor, username: str, tool_type: str) -> str:
    """Récupère l'email connu pour un user+provider."""
    try:
        if tool_type in ("gmail", "google"):
            cursor.execute(
                "SELECT email FROM gmail_tokens WHERE username=%s LIMIT 1", (username,)
            )
            row = cursor.fetchone()
            if row and row[0]:
                return row[0]
        cursor.execute(
            "SELECT email FROM users WHERE username=%s LIMIT 1", (username,)
        )
        row = cursor.fetchone()
        if row and row[0] and "raya-ia.fr" not in (row[0] or ""):
            return row[0]
    except Exception:
        pass
    return ""
