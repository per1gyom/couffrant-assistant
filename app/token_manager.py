from app.database import get_pg_conn
from app.auth import refresh_microsoft_token
from datetime import datetime, timezone, timedelta


def _make_aware(dt):
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


# ─────────────────────────────────────────
# MICROSOFT
# ─────────────────────────────────────────

def get_valid_microsoft_token(username: str = 'guillaume') -> str | None:
    """Retourne un token Microsoft valide pour l'utilisateur, avec auto-refresh."""
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

    print(f"[Token/MS] Refresh pour {username}...")
    if not refresh_token:
        return access_token

    try:
        result = refresh_microsoft_token(refresh_token)
    except Exception as e:
        print(f"[Token/MS] Erreur refresh {username}: {e}")
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
    print(f"[Token/MS] Refresh OK pour {username}.")
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


# ─────────────────────────────────────────
# GOOGLE
# Les tokens Google sont stockés dans oauth_tokens (provider='google').
# La table gmail_tokens est conservée pour compatibilité ascendante.
# ─────────────────────────────────────────

def get_valid_google_token(username: str) -> str | None:
    """
    Retourne un token Google valide, avec auto-refresh.
    Cherche d'abord dans oauth_tokens (provider='google'),
    puis dans gmail_tokens (compat ascendante).
    """
    conn = get_pg_conn()
    c = conn.cursor()

    # Source principale : oauth_tokens
    c.execute("""
        SELECT access_token, refresh_token, expires_at
        FROM oauth_tokens
        WHERE provider = 'google' AND username = %s
        ORDER BY updated_at DESC LIMIT 1
    """, (username,))
    row = c.fetchone()

    # Fallback : gmail_tokens (ancienne table)
    if not row:
        c.execute("SELECT access_token, refresh_token FROM gmail_tokens WHERE username = %s LIMIT 1", (username,))
        legacy = c.fetchone()
        conn.close()
        if not legacy:
            return None
        # Migration automatique vers oauth_tokens
        save_google_token(username, legacy[0], legacy[1])
        return legacy[0]

    conn.close()
    access_token, refresh_token, expires_at = row
    now = datetime.now(timezone.utc)
    expires_at_aware = _make_aware(expires_at)

    # Token encore valide
    if expires_at_aware and expires_at_aware > now + timedelta(minutes=5):
        return access_token

    # Refresh nécessaire
    print(f"[Token/Google] Refresh pour {username}...")
    if not refresh_token:
        return access_token
    try:
        from app.connectors.gmail_connector import refresh_gmail_token
        new_token = refresh_gmail_token(refresh_token)
        new_expires_at = now + timedelta(seconds=3600)
        conn2 = get_pg_conn()
        c2 = conn2.cursor()
        c2.execute("""
            UPDATE oauth_tokens
            SET access_token = %s, expires_at = %s, updated_at = NOW()
            WHERE provider = 'google' AND username = %s
        """, (new_token, new_expires_at, username))
        conn2.commit()
        conn2.close()
        print(f"[Token/Google] Refresh OK pour {username}.")
        return new_token
    except Exception as e:
        print(f"[Token/Google] Erreur refresh {username}: {e}")
        return access_token


def save_google_token(username: str, access_token: str, refresh_token: str,
                      email: str = "", expires_in: int = 3600):
    """Sauvegarde un token Google dans oauth_tokens (provider='google')."""
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
    conn = get_pg_conn()
    c = conn.cursor()
    c.execute("""
        INSERT INTO oauth_tokens (provider, username, access_token, refresh_token, expires_at)
        VALUES ('google', %s, %s, %s, %s)
        ON CONFLICT (provider, username) DO UPDATE SET
            access_token = EXCLUDED.access_token,
            refresh_token = EXCLUDED.refresh_token,
            expires_at = EXCLUDED.expires_at,
            updated_at = NOW()
    """, (username, access_token, refresh_token, expires_at))
    # Synchronise aussi gmail_tokens pour compat
    c.execute("""
        INSERT INTO gmail_tokens (username, email, access_token, refresh_token)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (username) DO UPDATE SET
            access_token = EXCLUDED.access_token,
            refresh_token = EXCLUDED.refresh_token
    """, (username, email or f"{username}@gmail.com", access_token, refresh_token))
    conn.commit()
    conn.close()


# ─────────────────────────────────────────
# HELPERS MULTI-PROVIDER
# ─────────────────────────────────────────

def get_all_users_with_tokens(provider: str = 'microsoft') -> list[str]:
    """Retourne les usernames ayant un token valide pour un provider donné."""
    conn = get_pg_conn()
    c = conn.cursor()
    c.execute("SELECT DISTINCT username FROM oauth_tokens WHERE provider = %s", (provider,))
    users = [r[0] for r in c.fetchall()]
    conn.close()
    return users


def get_connected_providers(username: str) -> list[str]:
    """Retourne les providers connectés pour un utilisateur."""
    conn = get_pg_conn()
    c = conn.cursor()
    c.execute("SELECT provider FROM oauth_tokens WHERE username = %s", (username,))
    providers = [r[0] for r in c.fetchall()]
    conn.close()
    return providers
