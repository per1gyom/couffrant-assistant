from app.database import get_pg_conn
from app.auth import refresh_microsoft_token
from datetime import datetime, timezone, timedelta


def _make_aware(dt):
    """Rend un datetime timezone-aware en UTC si nécessaire."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


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
        print("[Token] Aucun token Microsoft en base.")
        return None

    access_token, refresh_token, expires_at = row
    now = datetime.now(timezone.utc)
    expires_at_aware = _make_aware(expires_at)

    # Token valide avec plus de 5 minutes restantes → on le retourne directement
    if expires_at_aware and expires_at_aware > now + timedelta(minutes=5):
        return access_token

    # Token expiré ou expire bientôt → on rafraîchit
    print(f"[Token] Token expiré ou expire bientôt ({expires_at_aware}), rafraîchissement...")

    if not refresh_token:
        print("[Token] Pas de refresh_token disponible.")
        return None

    try:
        result = refresh_microsoft_token(refresh_token)
    except Exception as e:
        print(f"[Token] Erreur lors du rafraîchissement: {e}")
        return access_token  # Retourne l'ancien token en fallback

    if not result or "access_token" not in result:
        print("[Token] Rafraîchissement échoué, retour ancien token.")
        return access_token  # Fallback sur l'ancien token

    new_token = result["access_token"]
    new_refresh = result.get("refresh_token", refresh_token)
    expires_in = result.get("expires_in", 3600)

    conn = get_pg_conn()
    c = conn.cursor()
    c.execute("""
        UPDATE oauth_tokens
        SET access_token = %s,
            refresh_token = %s,
            expires_at = NOW() + INTERVAL '%s seconds',
            updated_at = NOW()
        WHERE provider = 'microsoft'
    """, (new_token, new_refresh, expires_in))
    conn.commit()
    conn.close()

    print(f"[Token] Token Microsoft rafraîchi, expire dans {expires_in}s.")
    return new_token


def save_microsoft_token(access_token: str, refresh_token: str, expires_in: int = 3600):
    """Sauvegarde ou met à jour le token Microsoft en base."""
    conn = get_pg_conn()
    c = conn.cursor()
    c.execute("""
        INSERT INTO oauth_tokens (provider, access_token, refresh_token, expires_at)
        VALUES ('microsoft', %s, %s, NOW() + INTERVAL '%s seconds')
        ON CONFLICT (provider) DO UPDATE SET
            access_token = EXCLUDED.access_token,
            refresh_token = EXCLUDED.refresh_token,
            expires_at = EXCLUDED.expires_at,
            updated_at = NOW()
    """, (access_token, refresh_token, expires_in))
    conn.commit()
    conn.close()
    print(f"[Token] Token Microsoft sauvegardé, expire dans {expires_in}s.")
