from app.database import get_pg_conn
from app.auth import refresh_microsoft_token


def get_valid_microsoft_token() -> str | None:
    conn = get_pg_conn()
    c = conn.cursor()
    c.execute("""
        SELECT access_token, refresh_token, expires_at
        FROM oauth_tokens
        WHERE provider = 'microsoft'
        ORDER BY updated_at DESC
        LIMIT 1
    """)
    row = c.fetchone()
    conn.close()

    if not row:
        return None

    access_token, refresh_token, expires_at = row

    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    
    # Si le token expire dans moins de 5 minutes, on le rafraîchit
    if expires_at and expires_at.replace(tzinfo=timezone.utc) > now:
        return access_token

    # Token expiré — on rafraîchit
    if not refresh_token:
        return None

    result = refresh_microsoft_token(refresh_token)
    if not result:
        return None

    new_token = result["access_token"]
    new_refresh = result.get("refresh_token", refresh_token)

    conn = get_pg_conn()
    c = conn.cursor()
    c.execute("""
        UPDATE oauth_tokens
        SET access_token = %s, refresh_token = %s,
            expires_at = NOW() + INTERVAL '1 hour',
            updated_at = NOW()
        WHERE provider = 'microsoft'
    """, (new_token, new_refresh))
    conn.commit()
    conn.close()

    return new_token