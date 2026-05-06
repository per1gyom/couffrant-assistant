"""
Connection Token Manager — Connecteurs V2 Phase C.

get_connection_token(username, tool_type) :
  → cherche le token dans tenant_connections (v2) via connection_assignments
  → fallback oauth_tokens (legacy per-user) pour compatibilité ascendante
  → refresh automatique + rechiffrement

get_connection_email(username, tool_type) :
  → retourne l'email de la connexion (connected_email sur la connexion v2
    ou email depuis oauth_tokens/users)
"""
import json
from datetime import datetime, timezone, timedelta
from app.database import get_pg_conn
from app.crypto import encrypt_token, decrypt_token
from app.logging_config import get_logger

logger = get_logger("raya.conn_tokens")


# ─── RÉSOLUTION PUBLIQUE ───────────────────────────────────────────

def get_connection_token(username: str, tool_type: str,
                         tenant_id: str | None = None,
                         email_hint: str | None = None) -> str | None:
    """
    Retourne un access_token valide pour (username, tool_type).
    Ordre : tenant_connections V2 → oauth_tokens legacy.

    Audit isolation 28/04 (I.14) : ajout tenant_id optionnel pour
    proteger contre les homonymes cross-tenant. Si non fourni, on
    resout via users (compat ascendante).

    Audit multi-boites 28/04 : email_hint optionnel pour cibler une
    boite specifique (ex: 'sci.romagui@gmail.com'). Si non fourni,
    retourne le token de la derniere boite connectee (legacy).
    """
    token = _get_v2_token(username, tool_type, tenant_id=tenant_id,
                          email_hint=email_hint)
    if token:
        return token
    # Fallback legacy (uniquement si pas de email_hint - le legacy ne
    # supporte pas le multi-boites)
    if email_hint:
        return None
    if tool_type == "microsoft":
        from app.token_manager import get_valid_microsoft_token
        return get_valid_microsoft_token(username)
    if tool_type in ("gmail", "google"):
        from app.token_manager import get_valid_google_token
        return get_valid_google_token(username)
    return None


def get_connection_email(username: str, tool_type: str,
                         tenant_id: str | None = None,
                         email_hint: str | None = None) -> str:
    """
    Retourne l'email associé à la connexion (boite mail) de l'utilisateur.
    Ordre : tenant_connections V2 → oauth_tokens/users legacy.

    Audit isolation 28/04 (I.14) : tenant_id optionnel.
    Audit multi-boites 28/04 : email_hint optionnel.
    """
    email = _get_v2_email(username, tool_type, tenant_id=tenant_id,
                          email_hint=email_hint)
    if email:
        return email
    # Fallback legacy (uniquement si pas de email_hint)
    if email_hint:
        return ""
    conn = None
    try:
        conn = get_pg_conn(); c = conn.cursor()
        if tool_type == "microsoft":
            c.execute("SELECT email FROM users WHERE username=%s LIMIT 1", (username,))
            row = c.fetchone()
            if row and row[0] and "raya-ia.fr" not in row[0]:
                return row[0]
        if tool_type in ("gmail", "google"):
            c.execute("SELECT email FROM gmail_tokens WHERE username=%s LIMIT 1", (username,))
            row = c.fetchone()
            if row and row[0]:
                return row[0]
    except Exception:
        pass
    finally:
        if conn: conn.close()
    return ""


def _resolve_tenant(username: str) -> str | None:
    """Helper : resout le tenant_id d un username via users.
    Utilise comme fallback quand tenant_id n est pas fourni explicitement."""
    conn = None
    try:
        conn = get_pg_conn(); c = conn.cursor()
        c.execute("SELECT tenant_id FROM users WHERE username=%s LIMIT 1", (username,))
        row = c.fetchone()
        return row[0] if row else None
    except Exception:
        return None
    finally:
        if conn: conn.close()


def get_user_tool_connections(username: str,
                              tenant_id: str | None = None) -> dict:
    """
    Retourne un dict {tool_type: {token, email, connection_id, label}}
    pour toutes les connexions actives de l'utilisateur (v2 uniquement).

    ATTENTION : si l user a plusieurs connexions du meme tool_type
    (ex: 6 Gmail), seule la derniere est retournee (le dict ecrase).
    Pour le multi-boites, utiliser get_all_user_connections() qui
    retourne une liste complete.

    Audit isolation 28/04 (I.14) : tenant_id optionnel.
    """
    if not tenant_id:
        tenant_id = _resolve_tenant(username)
        if not tenant_id:
            return {}
    conn = None
    try:
        conn = get_pg_conn(); c = conn.cursor()
        c.execute("""
            SELECT tc.id, tc.tool_type, tc.label, tc.credentials, tc.connected_email, tc.status
            FROM connection_assignments ca
            JOIN tenant_connections tc ON tc.id = ca.connection_id
            WHERE ca.username = %s AND ca.enabled = true
              AND tc.status = 'connected' AND tc.tenant_id = %s
            ORDER BY tc.tool_type
        """, (username, tenant_id))
        result = {}
        for row in c.fetchall():
            cid, tool_type, label, creds_raw, email, status = row
            creds = creds_raw if isinstance(creds_raw, dict) else (json.loads(creds_raw) if creds_raw else {})
            token = decrypt_token(creds.get("access_token", "")) if creds.get("access_token") else ""
            result[tool_type] = {
                "connection_id": cid,
                "label": label,
                "token": token,
                "email": email or "",
                "status": status,
            }
        return result
    except Exception as e:
        logger.warning("[ConnTokens] get_user_tool_connections error: %s", e)
        return {}
    finally:
        if conn: conn.close()


def get_all_user_connections(username: str,
                             tenant_id: str | None = None) -> list:
    """
    Retourne TOUTES les connexions actives de l user, en LISTE de dicts.
    Indispensable pour le multi-boites (ex: 6 Gmail differents).

    Chaque dict contient : tool_type, connection_id, label, token, email, status.

    Difference avec get_user_tool_connections (qui retourne dict[tool_type]) :
    cette fonction n ecrase pas si plusieurs connexions du meme tool_type.

    Audit multi-boites 28/04 : creee pour supporter N gmail/outlook par user.
    """
    if not tenant_id:
        tenant_id = _resolve_tenant(username)
        if not tenant_id:
            return []
    conn = None
    try:
        conn = get_pg_conn(); c = conn.cursor()
        c.execute("""
            SELECT tc.id, tc.tool_type, tc.label, tc.credentials,
                   tc.connected_email, tc.status, tc.updated_at
            FROM connection_assignments ca
            JOIN tenant_connections tc ON tc.id = ca.connection_id
            WHERE ca.username = %s AND ca.enabled = true
              AND tc.status = 'connected' AND tc.tenant_id = %s
            ORDER BY tc.tool_type, tc.id
        """, (username, tenant_id))
        result = []
        for row in c.fetchall():
            cid, tool_type, label, creds_raw, email, status, _ = row
            creds = creds_raw if isinstance(creds_raw, dict) else (json.loads(creds_raw) if creds_raw else {})
            token = decrypt_token(creds.get("access_token", "")) if creds.get("access_token") else ""
            result.append({
                "connection_id": cid,
                "tool_type": tool_type,
                "label": label,
                "token": token,
                "email": email or "",
                "status": status,
            })
        return result
    except Exception as e:
        logger.warning("[ConnTokens] get_all_user_connections error: %s", e)
        return []
    finally:
        if conn: conn.close()


# ─── STOCKAGE OAUTH (appelé depuis auth.py) ────────────────────────

def save_connection_oauth_token(
    connection_id: int,
    access_token: str,
    refresh_token: str,
    email: str = "",
    expires_in: int = 3600,
) -> bool:
    """Sauvegarde un token OAuth dans tenant_connections.credentials."""
    expires_at = (datetime.now(timezone.utc) + timedelta(seconds=expires_in)).isoformat()
    creds = {
        "access_token": encrypt_token(access_token),
        "refresh_token": encrypt_token(refresh_token),
        "expires_at": expires_at,
    }
    conn = None
    try:
        conn = get_pg_conn(); c = conn.cursor()
        c.execute("""
            UPDATE tenant_connections
            SET credentials = %s,
                connected_email = %s,
                status = 'connected',
                updated_at = NOW()
            WHERE id = %s
        """, (json.dumps(creds), email or None, connection_id))
        conn.commit()
        logger.info("[ConnTokens] Saved OAuth token for connection #%s (%s)", connection_id, email)
        return True
    except Exception as e:
        logger.error("[ConnTokens] Save error for #%s: %s", connection_id, e)
        return False
    finally:
        if conn: conn.close()


# ─── INTERNES ──────────────────────────────────────────────────────

def _get_v2_token(username: str, tool_type: str,
                  tenant_id: str | None = None,
                  email_hint: str | None = None) -> str | None:
    """Cherche et rafraîchit le token V2 pour (username, tool_type).

    Audit isolation 28/04 (I.14) : ajout filtre tenant_id sur le JOIN.
    Audit multi-boites 28/04 : email_hint optionnel pour cibler une
    boite specifique quand l user a plusieurs connexions du meme
    tool_type (ex: 6 Gmail). Si non fourni, retourne la derniere
    connectee (ORDER BY updated_at DESC LIMIT 1) - comportement legacy.
    """
    if not tenant_id:
        tenant_id = _resolve_tenant(username)
        if not tenant_id:
            return None
    conn = None
    try:
        conn = get_pg_conn(); c = conn.cursor()
        if email_hint:
            c.execute("""
                SELECT tc.id, tc.credentials, tc.tool_type
                FROM connection_assignments ca
                JOIN tenant_connections tc ON tc.id = ca.connection_id
                WHERE ca.username = %s AND ca.enabled = true
                  AND tc.tool_type = %s AND tc.status = 'connected'
                  AND tc.tenant_id = %s
                  AND LOWER(tc.connected_email) = LOWER(%s)
                LIMIT 1
            """, (username, tool_type, tenant_id, email_hint))
        else:
            c.execute("""
                SELECT tc.id, tc.credentials, tc.tool_type
                FROM connection_assignments ca
                JOIN tenant_connections tc ON tc.id = ca.connection_id
                WHERE ca.username = %s AND ca.enabled = true
                  AND tc.tool_type = %s AND tc.status = 'connected'
                  AND tc.tenant_id = %s
                ORDER BY tc.updated_at DESC LIMIT 1
            """, (username, tool_type, tenant_id))
        row = c.fetchone()
        if not row:
            return None
        cid, creds_raw, _ = row
        creds = creds_raw if isinstance(creds_raw, dict) else (json.loads(creds_raw) if creds_raw else {})
        if not creds:
            return None
        access_enc = creds.get("access_token", "")
        refresh_enc = creds.get("refresh_token", "")
        expires_at_str = creds.get("expires_at", "")
        access_token = decrypt_token(access_enc) if access_enc else ""
        refresh_token = decrypt_token(refresh_enc) if refresh_enc else ""
        # Vérifier expiry
        now = datetime.now(timezone.utc)
        if expires_at_str:
            try:
                expires_at = datetime.fromisoformat(expires_at_str)
                if expires_at.tzinfo is None:
                    expires_at = expires_at.replace(tzinfo=timezone.utc)
                if expires_at > now + timedelta(minutes=5):
                    return access_token  # Encore valide
            except Exception:
                pass
        # Refresh nécessaire
        if not refresh_token:
            return access_token
        new_token = _refresh_v2_token(cid, tool_type, refresh_token, creds)
        return new_token or access_token
    except Exception as e:
        logger.warning("[ConnTokens] _get_v2_token error (%s/%s): %s", username, tool_type, e)
        return None
    finally:
        if conn: conn.close()


def _get_v2_email(username: str, tool_type: str,
                  tenant_id: str | None = None,
                  email_hint: str | None = None) -> str:
    """Audit isolation 28/04 (I.14) : ajout filtre tenant_id sur le JOIN.
    Audit multi-boites 28/04 : email_hint optionnel.
    """
    if not tenant_id:
        tenant_id = _resolve_tenant(username)
        if not tenant_id:
            return ""
    conn = None
    try:
        conn = get_pg_conn(); c = conn.cursor()
        if email_hint:
            c.execute("""
                SELECT tc.connected_email
                FROM connection_assignments ca
                JOIN tenant_connections tc ON tc.id = ca.connection_id
                WHERE ca.username = %s AND ca.enabled = true
                  AND tc.tool_type = %s AND tc.status = 'connected'
                  AND tc.tenant_id = %s
                  AND LOWER(tc.connected_email) = LOWER(%s)
                LIMIT 1
            """, (username, tool_type, tenant_id, email_hint))
        else:
            c.execute("""
                SELECT tc.connected_email
                FROM connection_assignments ca
                JOIN tenant_connections tc ON tc.id = ca.connection_id
                WHERE ca.username = %s AND ca.enabled = true
                  AND tc.tool_type = %s AND tc.status = 'connected'
                  AND tc.tenant_id = %s
                ORDER BY tc.updated_at DESC LIMIT 1
            """, (username, tool_type, tenant_id))
        row = c.fetchone()
        return row[0] if row and row[0] else ""
    except Exception:
        return ""
    finally:
        if conn: conn.close()


def _refresh_v2_token(connection_id: int, tool_type: str, refresh_token: str, creds: dict) -> str | None:
    """Rafraîchit le token et met à jour tenant_connections.credentials."""
    try:
        if tool_type in ("microsoft", "outlook"):
            # Fix 06/05/2026 : 'outlook' utilise la meme API Microsoft Graph
            # que 'microsoft', donc meme mecanisme de refresh. Avant ce fix,
            # tool_type='outlook' tombait dans le else final et retournait
            # None -> les tokens des boites Outlook (ex: contact@) ne se
            # refreshaient JAMAIS, empechant la creation de subscriptions
            # Microsoft Graph (401 InvalidAuthenticationToken).
            from app.auth import refresh_microsoft_token
            result = refresh_microsoft_token(refresh_token)
            if not result or "access_token" not in result:
                return None
            new_access = result["access_token"]
            new_refresh = result.get("refresh_token", refresh_token)
            expires_in = result.get("expires_in", 3600)
        elif tool_type in ("gmail", "google"):
            from app.connectors.gmail_connector import refresh_gmail_token
            new_access = refresh_gmail_token(refresh_token)
            new_refresh = refresh_token
            expires_in = 3600
        else:
            return None

        expires_at = (datetime.now(timezone.utc) + timedelta(seconds=expires_in)).isoformat()
        new_creds = {**creds,
                     "access_token": encrypt_token(new_access),
                     "refresh_token": encrypt_token(new_refresh),
                     "expires_at": expires_at}
        conn = None
        try:
            conn = get_pg_conn(); c = conn.cursor()
            c.execute(
                "UPDATE tenant_connections SET credentials=%s, updated_at=NOW() WHERE id=%s",
                (json.dumps(new_creds), connection_id)
            )
            conn.commit()
        finally:
            if conn: conn.close()
        logger.info("[ConnTokens] Refreshed token for connection #%s", connection_id)
        return new_access
    except Exception as e:
        logger.error("[ConnTokens] Refresh error for #%s: %s", connection_id, e)
        return None


def get_all_users_with_tool_connections(tool_type: str) -> list[str]:
    """
    Retourne tous les usernames ayant une connexion V2 active pour un tool_type donné.
    Remplace l'ancienne get_all_users_with_tokens() du token_manager legacy.
    """
    try:
        conn = get_pg_conn(); c = conn.cursor()
        c.execute("""
            SELECT DISTINCT ca.username
            FROM connection_assignments ca
            JOIN tenant_connections tc ON tc.id = ca.connection_id
            WHERE tc.tool_type = %s
              AND tc.status = 'connected'
              AND ca.enabled = true
        """, (tool_type,))
        return [row[0] for row in c.fetchall()]
    except Exception as e:
        logger.error("[ConnTokens] get_all_users_with_tool_connections error: %s", e)
        return []
    finally:
        try:
            conn.close()
        except Exception:
            pass
