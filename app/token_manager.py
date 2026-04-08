from app.database import get_pg_conn
from app.auth import refresh_microsoft_token
from datetime import datetime, timezone, timedelta


def _make_aware(dt):
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def get_valid_microsoft_token(username: str = 'guillaume') -> str | None:
    """Retourne un token Microsoft valide pour l'utilisateur donné."""
    conn = get_pg_conn()
    c = conn.cursor()
    c.execute("""
        SELECT access_token, refresh_token, expires_at
        FROM oauth_tokens
        WHERE provider = 'microsoft' AND username = %s
        ORDER BY updated_at DESC LIMIT 1
    """, (username,))
    row = c.fetchone()
    conn.close()

    if not row:
        return None

    access_token, refresh_token, expires_at = row
    now = datetime.now(timezone.utc)
    expires_at_aware = _make_aware(expires_at)

    if expires_at_aware and expires_at_aware > now + timedelta(minutes=5):
        return access_token

    print(f"[Token] Refresh pour {username}...")
    if not refresh_token:
        return None

    try:
        result = refresh_microsoft_token(refresh_token)
    except Exception as e:
        print(f"[Token] Erreur refresh {username}: {e}")
        return access_token

    if not result or "access_token" not in result:
        return access_token

    new_token = result["access_token"]
    new_refresh = result.get("refresh_token", refresh_token)
    expires_in = result.get("expires_in", 3600)
    new_expires_at = now + timedelta(seconds=expires_in)

    conn = get_pg_conn()
    c = conn.cursor()
    c.execute("""
        UPDATE oauth_tokens
        SET access_token = %s, refresh_token = %s, expires_at = %s, updated_at = NOW()
        WHERE provider = 'microsoft' AND username = %s
    """, (new_token, new_refresh, new_expires_at, username))
    conn.commit()
    conn.close()
    print(f"[Token] Refresh OK pour {username}.")
    return new_token


def save_microsoft_token(username: str, access_token: str, refresh_token: str, expires_in: int = 3600):
    """Sauvegarde ou met à jour le token Microsoft pour un utilisateur."""
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
    conn = get_pg_conn()
    c = conn.cursor()
    c.execute("""
        INSERT INTO oauth_tokens (provider, username, access_token, refresh_token, expires_at)
        VALUES ('microsoft', %s, %s, %s, %s)
        ON CONFLICT (provider, username) DO UPDATE SET
            access_token = EXCLUDED.access_token,
            refresh_token = EXCLUDED.refresh_token,
            expires_at = EXCLUDED.expires_at,
            updated_at = NOW()
    """, (username, access_token, refresh_token, expires_at))
    conn.commit()
    conn.close()
    print(f"[Token] Token Microsoft sauvegardé pour {username}.")


def get_all_users_with_tokens() -> list[str]:
    """Retourne la liste de tous les usernames ayant un token Microsoft."""
    conn = get_pg_conn()
    c = conn.cursor()
    c.execute("SELECT DISTINCT username FROM oauth_tokens WHERE provider = 'microsoft'")
    users = [r[0] for r in c.fetchall()]
    conn.close()
    return users
