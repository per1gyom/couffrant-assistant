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


def _resolve_tenant_strict(username: str, conn) -> str | None:
    """Resout le tenant_id d'un user de maniere stricte. Retourne None
    si user inconnu ou sans tenant_id (PAS de fallback DEFAULT_TENANT
    silencieux : ce serait un risque de fuite cross-tenant en cas
    d'homonyme, qui est precisement le scenario qu'on veut bloquer).

    Reutilise la connexion existante pour eviter de gaspiller le pool.
    Ajoute le 26/04 (etape A.1 audit isolation, fix isolation tokens
    OAuth)."""
    c = conn.cursor()
    c.execute("SELECT tenant_id FROM users WHERE username = %s", (username,))
    row = c.fetchone()
    return row[0] if row and row[0] else None


# ─── MICROSOFT ───

def get_valid_microsoft_token(username: str) -> str | None:
    """Retourne un token Microsoft valide, avec auto-refresh et dechiffrement.

    HOTFIX 26/04 (etape A.1 audit isolation) :
    - Default 'guillaume' retire (anti-pattern multi-tenant)
    - Resolution stricte du tenant_id depuis username (return None si inconnu)
    - Filtre AND tenant_id = %s ajoute dans le SELECT pour empecher la fuite
      en cas d'homonyme cross-tenant (Pierre/microsoft existant dans 2 tenants)."""
    conn = None
    try:
        conn = get_pg_conn()
        tenant_id = _resolve_tenant_strict(username, conn)
        if not tenant_id:
            return None  # User inconnu : pas de token, pas de fallback
        c = conn.cursor()
        c.execute("""
            SELECT access_token, refresh_token, expires_at
            FROM oauth_tokens
            WHERE provider = 'microsoft' AND username = %s AND tenant_id = %s
            ORDER BY updated_at DESC LIMIT 1
        """, (username, tenant_id))
        row = c.fetchone()
    finally:
        if conn: conn.close()

    if not row:
        return None

    access_token_raw, refresh_token_raw, expires_at = row
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

    new_token   = result["access_token"]
    new_refresh = result.get("refresh_token", refresh_token)
    expires_in  = result.get("expires_in", 3600)

    save_microsoft_token(username, new_token, new_refresh, expires_in)
    print(f"[Token/MS] Refresh OK pour {username}.")
    return new_token


def _save_microsoft_token_raw(username: str, access_enc: str, refresh_enc: str, expires_at):
    """Sauvegarde les tokens deja chiffres (usage interne migration).
    HOTFIX 26/04 : ajout filtre tenant_id pour ne pas ecraser le token
    d'un homonyme cross-tenant."""
    conn = None
    try:
        conn = get_pg_conn()
        tenant_id = _resolve_tenant_strict(username, conn)
        if not tenant_id:
            return  # User inconnu : on ne sauvegarde rien
        c = conn.cursor()
        c.execute("""
            UPDATE oauth_tokens
            SET access_token=%s, refresh_token=%s, expires_at=%s, updated_at=NOW()
            WHERE provider='microsoft' AND username=%s AND tenant_id=%s
        """, (access_enc, refresh_enc, expires_at, username, tenant_id))
        conn.commit()
    finally:
        if conn: conn.close()


def save_microsoft_token(username: str, access_token: str, refresh_token: str, expires_in: int = 3600):
    """Sauvegarde le token Microsoft en base, chiffre.
    HOTFIX 26/04 : ajout du tenant_id (colonne + ON CONFLICT) pour
    permettre des homonymes cross-tenant. Si user inconnu, on raise
    plutot que de sauvegarder dans le mauvais tenant."""
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
    conn = None
    try:
        conn = get_pg_conn()
        tenant_id = _resolve_tenant_strict(username, conn)
        if not tenant_id:
            raise ValueError(f"save_microsoft_token: user '{username}' inconnu, refus de sauvegarde")
        c = conn.cursor()
        c.execute("""
            INSERT INTO oauth_tokens (provider, username, tenant_id, access_token, refresh_token, expires_at)
            VALUES ('microsoft', %s, %s, %s, %s, %s)
            ON CONFLICT (provider, username, tenant_id) DO UPDATE SET
                access_token = EXCLUDED.access_token,
                refresh_token = EXCLUDED.refresh_token,
                expires_at = EXCLUDED.expires_at,
                updated_at = NOW()
        """, (username, tenant_id, encrypt_token(access_token), encrypt_token(refresh_token), expires_at))
        conn.commit()
    finally:
        if conn: conn.close()


# ─── GOOGLE ───

def get_valid_google_token(username: str) -> str | None:
    """
    Retourne un token Google valide, avec auto-refresh et dechiffrement.
    Cherche d'abord dans oauth_tokens (provider='google'),
    puis dans gmail_tokens (fallback lecture seule - table depreciee).

    HOTFIX 26/04 (etape A.1) : ajout filtre tenant_id sur SELECT et
    UPDATE refresh pour empecher fuite cross-tenant. Si user inconnu,
    return None.
    """
    conn = None
    tenant_id = None
    try:
        conn = get_pg_conn()
        tenant_id = _resolve_tenant_strict(username, conn)
        if not tenant_id:
            return None
        c = conn.cursor()
        c.execute("""
            SELECT access_token, refresh_token, expires_at
            FROM oauth_tokens
            WHERE provider = 'google' AND username = %s AND tenant_id = %s
            ORDER BY updated_at DESC LIMIT 1
        """, (username, tenant_id))
        row = c.fetchone()

        if not row:
            # Fallback lecture seule : migration depuis gmail_tokens (table legacy)
            # F.9 (audit isolation user-user, LOT 1.5) : ajout filtre tenant_id
            # pour coherence multi-tenant. La table gmail_tokens a bien
            # tenant_id (verifie 28/04). Sans ce filtre, en cas d homonyme
            # futur cross-tenant, le fallback recuperait un token du mauvais
            # tenant.
            c.execute(
                "SELECT access_token, refresh_token FROM gmail_tokens "
                "WHERE username = %s AND tenant_id = %s LIMIT 1",
                (username, tenant_id),
            )
            legacy = c.fetchone()
            if not legacy:
                return None
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
            # tenant_id deja resolu en debut de fonction, on le reutilise
            c = conn.cursor()
            c.execute("""
                UPDATE oauth_tokens
                SET access_token=%s, expires_at=%s, updated_at=NOW()
                WHERE provider='google' AND username=%s AND tenant_id=%s
            """, (encrypt_token(new_token), new_expires, username, tenant_id))
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
    """
    Sauvegarde un token Google chiffre dans oauth_tokens.
    Met aussi a jour gmail_tokens.email pour que le bandeau affiche l'adresse.

    HOTFIX 26/04 (etape A.1) : ajout du tenant_id (colonne + ON CONFLICT)
    pour permettre des homonymes cross-tenant. Si user inconnu, on raise.
    """
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
    conn = None
    try:
        conn = get_pg_conn()
        tenant_id = _resolve_tenant_strict(username, conn)
        if not tenant_id:
            raise ValueError(f"save_google_token: user '{username}' inconnu, refus de sauvegarde")
        c = conn.cursor()
        c.execute("""
            INSERT INTO oauth_tokens (provider, username, tenant_id, access_token, refresh_token, expires_at)
            VALUES ('google', %s, %s, %s, %s, %s)
            ON CONFLICT (provider, username, tenant_id) DO UPDATE SET
                access_token = EXCLUDED.access_token,
                refresh_token = EXCLUDED.refresh_token,
                expires_at = EXCLUDED.expires_at,
                updated_at = NOW()
        """, (username, tenant_id, encrypt_token(access_token), encrypt_token(refresh_token), expires_at))
        # Sauvegarder aussi l'email dans gmail_tokens pour affichage dans le bandeau
        if email:
            c.execute("""
                INSERT INTO gmail_tokens (username, access_token, refresh_token, email)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (username) DO UPDATE SET
                    access_token = EXCLUDED.access_token,
                    refresh_token = EXCLUDED.refresh_token,
                    email = EXCLUDED.email
            """, (username, encrypt_token(access_token), encrypt_token(refresh_token), email))
        conn.commit()
    finally:
        if conn: conn.close()


# ─── HELPERS ───

def get_all_users_with_tokens(provider: str = 'microsoft') -> list[str]:
    """Retourne la liste des usernames (tous tenants confondus) ayant un
    token pour ce provider.

    NOTE 26/04 (etape A.1) : cette fonction est volontairement
    CROSS-TENANT (utilisee par les jobs cron type token_refresh qui
    iterent sur tous les users de tous les tenants). Les callers DOIVENT
    re-resoudre le tenant_id avant tout traitement specifique au user
    (typiquement via _resolve_tenant_strict). Le risque d'homonymes
    cross-tenant est gere au niveau ligne par ligne par chaque caller."""
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("SELECT DISTINCT username FROM oauth_tokens WHERE provider = %s", (provider,))
        return [r[0] for r in c.fetchall()]
    finally:
        if conn: conn.close()


def get_connected_providers(username: str) -> list[str]:
    """Retourne la liste des providers connectes pour ce user dans son
    tenant. HOTFIX 26/04 (etape A.1) : ajout du filtre tenant_id pour
    eviter de retourner les providers d'un homonyme cross-tenant."""
    conn = None
    try:
        conn = get_pg_conn()
        tenant_id = _resolve_tenant_strict(username, conn)
        if not tenant_id:
            return []  # User inconnu : aucun provider
        c = conn.cursor()
        c.execute(
            "SELECT provider FROM oauth_tokens WHERE username = %s AND tenant_id = %s",
            (username, tenant_id),
        )
        return [r[0] for r in c.fetchall()]
    finally:
        if conn: conn.close()
