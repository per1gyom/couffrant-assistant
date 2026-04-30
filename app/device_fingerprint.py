"""
Device fingerprinting persistant pour skipper la 2FA sur appareil connu.

Implemente le LOT 4 du chantier 2FA (decision Guillaume 30/04) :
- Une fois la 2FA validee sur un navigateur, on s en souvient 30 jours
- Survit aux deconnexions/reconnexions (cookie persistant signe)
- IP nouvelle dans le meme pays : tolere, on ajoute a known_ips
- Pays different : 2FA redemandee
- Cookie absent (mode prive, autre navigateur) : 2FA redemandee

Stockage :
- Cookie navigateur `raya_device_id` signe (itsdangerous), valide 30j
- Table user_devices (deja creee au LOT 0) :
    device_fingerprint = UUID du cookie
    last_2fa_validated_at = timestamp
    known_ips = JSONB array d objets {ip, country, first_seen, last_seen}
    expires_at = NOW + 30j (re-bumpe a chaque utilisation reussie)

Securite :
- Cookie HttpOnly + Secure + SameSite=Lax (anti-XSS, anti-CSRF)
- Signature itsdangerous : impossible de forger un cookie sans SESSION_SECRET
- Verification couplee : cookie valide + DB existe + non expire
- Tout echec -> 2FA redemandee (fail-safe)
"""
import json
import os
import time
import uuid
from datetime import datetime, timedelta
from typing import Optional, Tuple

from itsdangerous import BadSignature, URLSafeSerializer

from app.database import get_pg_conn
from app.geoip_lookup import lookup_country
from app.logging_config import get_logger

logger = get_logger("raya.device_fp")


# ─── CONSTANTES ────────────────────────────────────────────────────────

# Validite d un device "trusted" = 30 jours (decision Guillaume Q2=A)
DEVICE_TRUSTED_DAYS = 30

# Cookie navigateur
DEVICE_COOKIE_NAME = "raya_device_id"
DEVICE_COOKIE_MAX_AGE = DEVICE_TRUSTED_DAYS * 24 * 3600  # secondes

# Combien d IP on memorise par device avant rotation
MAX_KNOWN_IPS_PER_DEVICE = 20

# Salt pour signature cookie (different de la session pour isolation)
COOKIE_SALT = "raya-device-fingerprint-v1"


# ─── HELPERS ───────────────────────────────────────────────────────────


def _get_serializer() -> URLSafeSerializer:
    """Serializer itsdangerous pour signer le cookie device.

    Utilise SESSION_SECRET (deja en prod pour la session starlette).
    """
    secret = os.getenv("SESSION_SECRET", "")
    if not secret:
        raise RuntimeError("SESSION_SECRET absent — impossible de signer le cookie device")
    return URLSafeSerializer(secret, salt=COOKIE_SALT)


def _encode_device_id(device_uuid: str) -> str:
    """Signe un UUID pour stockage dans le cookie."""
    return _get_serializer().dumps({"id": device_uuid, "v": 1})


def _decode_device_id(signed_token: Optional[str]) -> Optional[str]:
    """Decode un cookie signe et retourne l UUID, ou None si invalide."""
    if not signed_token:
        return None
    try:
        payload = _get_serializer().loads(signed_token)
        if not isinstance(payload, dict) or "id" not in payload:
            return None
        return payload["id"]
    except BadSignature:
        logger.warning("[Device FP] Cookie avec signature invalide — possible tentative forgery")
        return None
    except Exception as e:
        logger.error("[Device FP] _decode_device_id error: %s", str(e)[:200])
        return None


def _normalize_ip(ip: Optional[str]) -> str:
    """Normalise une IP (strip, lowercase) pour comparaison stable."""
    return (ip or "").strip().lower()


# ─── DB OPERATIONS ─────────────────────────────────────────────────────


def _fetch_device(device_uuid: str, username: str, tenant_id: str) -> Optional[dict]:
    """Lit un device en DB. Returns None si introuvable ou expire."""
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute(
            """
            SELECT id, last_2fa_validated_at, expires_at, known_ips, country, device_label
            FROM user_devices
            WHERE device_fingerprint = %s
              AND username = %s
              AND tenant_id = %s
              AND expires_at > NOW()
            """,
            (device_uuid, username, tenant_id),
        )
        row = c.fetchone()
        if not row:
            return None
        return {
            "id": row[0],
            "last_2fa_validated_at": row[1],
            "expires_at": row[2],
            "known_ips": row[3] or [],
            "country": row[4],
            "device_label": row[5],
        }
    except Exception as e:
        logger.error("[Device FP] _fetch_device error: %s", str(e)[:200])
        return None
    finally:
        if conn:
            conn.close()


def _create_or_update_device(
    device_uuid: str,
    username: str,
    tenant_id: str,
    ip: str,
    country: Optional[str],
    user_agent_label: Optional[str] = None,
) -> bool:
    """Cree un device trusted ou met a jour s il existe deja.

    Cas usage :
    - Apres validation 2FA reussie (POST /admin/2fa-challenge OK)
    - Pose / re-pose le timestamp last_2fa_validated_at + expires_at = NOW + 30j
    - Met a jour known_ips avec l IP courante
    """
    conn = None
    try:
        ip_clean = _normalize_ip(ip)
        new_known_ip = {
            "ip": ip_clean,
            "country": country,
            "first_seen": datetime.utcnow().isoformat(),
            "last_seen": datetime.utcnow().isoformat(),
        }

        conn = get_pg_conn()
        c = conn.cursor()

        # Existe deja ? -> UPDATE, sinon INSERT
        c.execute(
            """
            SELECT id, known_ips FROM user_devices
            WHERE device_fingerprint = %s AND username = %s AND tenant_id = %s
            """,
            (device_uuid, username, tenant_id),
        )
        existing = c.fetchone()

        if existing:
            # Update : refresh + ajouter IP si nouvelle
            existing_ips = existing[1] or []
            ip_already_known = any(_normalize_ip(k.get("ip")) == ip_clean for k in existing_ips)

            if ip_already_known:
                # Refresh last_seen de l IP existante
                updated_ips = []
                for k in existing_ips:
                    if _normalize_ip(k.get("ip")) == ip_clean:
                        k["last_seen"] = datetime.utcnow().isoformat()
                    updated_ips.append(k)
            else:
                # Ajouter la nouvelle IP, conserver les MAX_KNOWN_IPS_PER_DEVICE plus recentes
                updated_ips = (existing_ips + [new_known_ip])[-MAX_KNOWN_IPS_PER_DEVICE:]

            c.execute(
                """
                UPDATE user_devices
                SET last_2fa_validated_at = NOW(),
                    expires_at = NOW() + INTERVAL '%s days',
                    ip_last_seen = %s,
                    country = COALESCE(%s, country),
                    known_ips = %s::jsonb,
                    updated_at = NOW()
                WHERE id = %s
                """,
                (DEVICE_TRUSTED_DAYS, ip_clean, country, json.dumps(updated_ips), existing[0]),
            )
        else:
            # Insert : nouveau device
            c.execute(
                """
                INSERT INTO user_devices (
                    username, tenant_id, device_fingerprint, device_label,
                    ip_first_seen, ip_last_seen, country, known_ips,
                    last_2fa_validated_at, expires_at
                ) VALUES (
                    %s, %s, %s, %s,
                    %s, %s, %s, %s::jsonb,
                    NOW(), NOW() + INTERVAL '%s days'
                )
                """,
                (
                    username, tenant_id, device_uuid, user_agent_label,
                    ip_clean, ip_clean, country, json.dumps([new_known_ip]),
                    DEVICE_TRUSTED_DAYS,
                ),
            )

        conn.commit()
        return True
    except Exception as e:
        logger.error("[Device FP] _create_or_update_device error: %s", str(e)[:200])
        try:
            if conn:
                conn.rollback()
        except Exception:
            pass
        return False
    finally:
        if conn:
            conn.close()


def _add_ip_to_device(device_id: int, ip: str, country: Optional[str]) -> bool:
    """Ajoute une IP nouvelle a un device existant (apres validation pays OK).

    Different de _create_or_update_device : ne touche PAS last_2fa_validated_at
    ni expires_at. Sert quand on tolere une nouvelle IP dans le meme pays
    sans redemander la 2FA.
    """
    conn = None
    try:
        ip_clean = _normalize_ip(ip)
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("SELECT known_ips FROM user_devices WHERE id = %s", (device_id,))
        row = c.fetchone()
        if not row:
            return False
        existing_ips = row[0] or []
        new_known_ip = {
            "ip": ip_clean,
            "country": country,
            "first_seen": datetime.utcnow().isoformat(),
            "last_seen": datetime.utcnow().isoformat(),
        }
        updated_ips = (existing_ips + [new_known_ip])[-MAX_KNOWN_IPS_PER_DEVICE:]
        c.execute(
            """
            UPDATE user_devices
            SET known_ips = %s::jsonb, ip_last_seen = %s, updated_at = NOW()
            WHERE id = %s
            """,
            (json.dumps(updated_ips), ip_clean, device_id),
        )
        conn.commit()
        return True
    except Exception as e:
        logger.error("[Device FP] _add_ip_to_device error: %s", str(e)[:200])
        try:
            if conn:
                conn.rollback()
        except Exception:
            pass
        return False
    finally:
        if conn:
            conn.close()


# ─── API PUBLIQUE ──────────────────────────────────────────────────────


def check_device_trusted(
    request,
    username: str,
    tenant_id: str,
) -> Tuple[bool, str]:
    """Verifie si l appareil courant est trusted (skippe la 2FA).

    Returns (trusted: bool, reason: str)

    reason possible :
    - "no_cookie"       : pas de cookie raya_device_id
    - "invalid_cookie"  : cookie present mais signature invalide
    - "device_unknown"  : device pas en DB pour ce user
    - "device_expired"  : device en DB mais expires_at < NOW
    - "country_changed" : nouveau pays detecte vs known_ips
    - "trusted_match"   : IP connue + meme pays -> on laisse passer
    - "trusted_new_ip"  : IP nouvelle mais meme pays -> ajout known_ips, on laisse passer

    Cas trusted=False -> le caller redemande la 2FA.
    """
    # 1. Lire le cookie
    signed_token = request.cookies.get(DEVICE_COOKIE_NAME)
    if not signed_token:
        return False, "no_cookie"

    device_uuid = _decode_device_id(signed_token)
    if not device_uuid:
        return False, "invalid_cookie"

    # 2. Lire le device en DB
    device = _fetch_device(device_uuid, username, tenant_id)
    if not device:
        return False, "device_unknown"

    # 3. Verifier l IP courante
    ip = _client_ip_from_request(request)
    ip_clean = _normalize_ip(ip)
    current_country = lookup_country(ip)

    # 4. Comparer pays vs pays connu du device
    device_country = device.get("country")
    known_ips = device.get("known_ips", [])

    # IP deja connue ?
    ip_already_known = any(_normalize_ip(k.get("ip")) == ip_clean for k in known_ips)
    if ip_already_known:
        return True, "trusted_match"

    # IP nouvelle - verifier le pays
    if current_country and device_country and current_country != device_country:
        # Pays different -> 2FA obligatoire
        logger.info(
            "[Device FP] Pays different : device=%s now=%s pour %s",
            device_country, current_country, username,
        )
        return False, "country_changed"

    # IP nouvelle mais meme pays (ou pays inconnu cote GeoIP) -> tolere
    # On l ajoute a known_ips silencieusement
    _add_ip_to_device(device["id"], ip, current_country)
    return True, "trusted_new_ip"


def _client_ip_from_request(request) -> str:
    """Extrait l IP client depuis la request FastAPI."""
    fwd = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
    if fwd:
        return fwd
    return request.client.host if request.client else "unknown"


def issue_device_cookie(response, username: str, tenant_id: str, request, user_agent_label: Optional[str] = None) -> str:
    """Pose un cookie device sur la response et cree le device en DB.

    A appeler apres une validation 2FA reussie (POST /admin/2fa-challenge OK).
    Retourne l UUID du device.
    """
    # Recuperer ou creer un UUID
    existing_token = request.cookies.get(DEVICE_COOKIE_NAME)
    existing_uuid = _decode_device_id(existing_token) if existing_token else None
    device_uuid = existing_uuid or str(uuid.uuid4())

    ip = _client_ip_from_request(request)
    country = lookup_country(ip)

    # Persister en DB
    _create_or_update_device(
        device_uuid=device_uuid,
        username=username,
        tenant_id=tenant_id,
        ip=ip,
        country=country,
        user_agent_label=user_agent_label,
    )

    # Poser le cookie signe
    signed = _encode_device_id(device_uuid)
    response.set_cookie(
        key=DEVICE_COOKIE_NAME,
        value=signed,
        max_age=DEVICE_COOKIE_MAX_AGE,
        httponly=True,
        secure=True,    # HTTPS seulement (Railway = HTTPS)
        samesite="lax",
        path="/",
    )
    return device_uuid
