from app.database import get_pg_conn
from app.auth import refresh_microsoft_token
from app.crypto import encrypt_token, decrypt_token, is_encrypted
from datetime import datetime, timezone, timedelta


def _make_aware(dt):
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


# ─── MICROSOFT ───

def get_valid_microsoft_token(username: str = 'guillaume') -> str | None:
    """Retourne un token Microsoft valide, avec auto-refresh et déchiffrement."""
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            SELECT access_token, refresh_token, expires_at
            FROM oauth_tokens
            WHERE provider = 'microsoft' AND username = %s
            ORDER BY updated_at DESC LIMIT 1
        """, (username,))
        row = c.fetchone()
    finally:
        if conn: conn.close()

    if not row:
        return None

    access_token_raw, refresh_token_raw, expires_at = row
    # Déchiffrement transparent (passthrough si en clair)
    access_token  = decrypt_token(access_token_raw  or "")
    refresh_token = decrypt_token(refresh_token_raw or "")

    now = datetime.now(timezone.utc)
    expires_at_aware = _make_aware(expires_at)

    # Migration : rechiffrer si le token est encore en clair
    if access_token and not is_encrypted(access_token_raw) and is_encrypted(encrypt_token(access_token)):
        _save_microsoft_token_raw(username, encrypt_token(access_token),
                                   encrypt_token(refresh_token), expires_at_aware)

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

    new_token    = result["access_token"]
    new_refresh  = result.get("refresh_token", refresh_token)
    expires_in   = result.get("expires_in", 3600)
    new_expires  = now + timedelta(seconds=expires_in)

    save_microsoft_token(username, new_token, new_refresh, expires_in)
    print(f"[Token/MS] Refresh OK pour {username}.")
    return new_token


def _save_microsoft_token_raw(username: str, access_enc: str, refresh_enc: str, expires_at):
    """Sauvegarde les tokens déjà chiffrés (usage interne migration)."""
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            UPDATE oauth_tokens
            SET access_token=%s, refresh_token=%s, expires_at=%s, updated_at=NOW()
            WHERE provider='microsoft' AND username=%s
        """, (access_enc, refresh_enc, expires_at, username))
        conn.commit()
    finally:
        if conn: conn.close()


def save_microsoft_token(username: str, access_token: str, refresh_token: str, expires_in: int = 3600):
    """Sauvegarde le token Microsoft en base, chiffré."""
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
    conn = None
    try:
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
        """, (username, encrypt_token(access_token), encrypt_token(refresh_token), expires_at))
        conn.commit()
    finally:
        if conn: conn.close()


# ─── GOOGLE ───

def get_valid_google_token(username: str) -> str | None:
    """
    Retourne un token Google valide, avec auto-refresh et déchiffrement.
    Cherche d'abord dans oauth_tokens (provider='google'),
    puis dans gmail_tokens (compat ascendante).
    """
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            SELECT access_token, refresh_token, expires_at
            FROM oauth_tokens
            WHERE provider = 'google' AND username = %s
            ORDER BY updated_at DESC LIMIT 1
        """, (username,))
        row = c.fetchone()

        if not row:
            c.execute("SELECT access_token, refresh_token FROM gmail_tokens WHERE username = %s LIMIT 1", (username,))
            legacy = c.fetchone()
            if not legacy:
                return None
            # Migration vers oauth_tokens
            save_google_token(username, legacy[0], legacy[1])
            return legacy[0]
    finally:
        if conn: conn.close()

    access_token_raw, refresh_token_raw, expires_at = row
    access_token  = decrypt_token(access_token_raw  or "")
    refresh_token = decrypt_token(refresh_token_raw or "")

    now = datetime.now(timezone.utc)
    expires_at_aware = _make_aware(expires_at)

    if expires_at_aware and expires_at_aware > now + timedelta(minutes=5):
        return access_token

    print(f"[Token/Google] Refresh pour {username}...")
    if not refresh_token:
        return access_token
    try:
        from app.connectors.gmail_connector import refresh_gmail_token
        new_token = refresh_gmail_token(refresh_token)
        new_expires = now + timedelta(seconds=3600)
        conn = None
        try:
            conn = get_pg_conn()
            c = conn.cursor()
            c.execute("""
                UPDATE oauth_tokens
                SET access_token=%s, expires_at=%s, updated_at=NOW()
                WHERE provider='google' AND username=%s
            """, (encrypt_token(new_token), new_expires, username))
            conn.commit()
        finally:
            if conn: conn.close()
        print(f"[Token/Google] Refresh OK pour {username}.")
        return new_token
    except Exception as e:
        print(f"[Token/Google] Erreur refresh {username}: {e}")
        return access_token


def save_google_token(username: str, access_token: str, refresh_token: str,
                      email: str = "", expires_in: int = 3600):
    """Sauvegarde un token Google chiffré dans oauth_tokens."""
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
    conn = None
    try:
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
        """, (username, encrypt_token(access_token), encrypt_token(refresh_token), expires_at))
        # Sync compat gmail_tokens (en clair pour compat legacy)
        c.execute("""
            INSERT INTO gmail_tokens (username, email, access_token, refresh_token)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (username) DO UPDATE SET
                access_token = EXCLUDED.access_token,
                refresh_token = EXCLUDED.refresh_token
        """, (username, email or f"{username}@gmail.com", access_token, refresh_token))
        conn.commit()
    finally:
        if conn: conn.close()


# ─── HELPERS ───

def get_all_users_with_tokens(provider: str = 'microsoft') -> list[str]:
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("SELECT DISTINCT username FROM oauth_tokens WHERE provider = %s", (provider,))
        return [r[0] for r in c.fetchall()]
    finally:
        if conn: conn.close()


def get_connected_providers(username: str) -> list[str]:
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("SELECT provider FROM oauth_tokens WHERE username = %s", (username,))
        return [r[0] for r in c.fetchall()]
    finally:
        if conn: conn.close()
