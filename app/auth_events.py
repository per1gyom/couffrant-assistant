"""
Helper centralise pour logger les events d authentification.

Toutes les operations sensibles (login, 2FA setup/success/failure,
recovery codes, reset par admin) appellent log_auth_event() qui ecrit
dans la table auth_events (creee au LOT 0).

Utilise par :
  - LOT 2 : endpoints setup 2FA (this LOT)
  - LOT 3 : login flow modifie (a venir)
  - LOT 5 : step-up auth (a venir)
  - LOT 6 : reset 2FA par super_admin (a venir)

Conventions d event_type :
  - login_success, login_failure
  - 2fa_setup_started, 2fa_setup_completed, 2fa_setup_failed
  - 2fa_success, 2fa_failure
  - recovery_code_used, recovery_codes_regenerated
  - 2fa_reset_by_admin, 2fa_disabled
  - device_trusted, device_revoked
"""
import json
from typing import Optional

from app.database import get_pg_conn
from app.logging_config import get_logger

logger = get_logger("raya.auth_events")


def log_auth_event(
    username: str,
    event_type: str,
    tenant_id: Optional[str] = None,
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
    country: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> bool:
    """
    Logue un event d authentification dans auth_events.

    Returns True si insertion OK, False sinon.
    Ne leve JAMAIS d exception : un echec de logging ne doit pas casser
    le flow auth principal. Logue juste un warning interne.
    """
    if not username or not event_type:
        return False
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute(
            """
            INSERT INTO auth_events
                (username, tenant_id, event_type, ip, user_agent, country, metadata)
            VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb)
            """,
            (
                username,
                tenant_id,
                event_type,
                (ip or "")[:64] or None,
                (user_agent or "")[:512] or None,
                (country or "")[:8] or None,
                json.dumps(metadata or {}),
            ),
        )
        conn.commit()
        return True
    except Exception as e:
        logger.warning(
            "[AuthEvents] Echec log %s pour %s: %s",
            event_type, username, str(e)[:200],
        )
        try:
            if conn:
                conn.rollback()
        except Exception:
            pass
        return False
    finally:
        try:
            if conn:
                conn.close()
        except Exception:
            pass


def get_recent_events(
    username: str,
    tenant_id: Optional[str] = None,
    limit: int = 50,
    event_types: Optional[list] = None,
) -> list:
    """
    Retourne les N derniers events d auth pour un user.
    event_types : optionnel, filtre sur la liste donnee.
    """
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        if event_types:
            c.execute(
                """
                SELECT event_type, ip, user_agent, country, metadata, created_at
                FROM auth_events
                WHERE username = %s
                  AND (%s::text IS NULL OR tenant_id = %s)
                  AND event_type = ANY(%s)
                ORDER BY created_at DESC LIMIT %s
                """,
                (username, tenant_id, tenant_id, event_types, limit),
            )
        else:
            c.execute(
                """
                SELECT event_type, ip, user_agent, country, metadata, created_at
                FROM auth_events
                WHERE username = %s
                  AND (%s::text IS NULL OR tenant_id = %s)
                ORDER BY created_at DESC LIMIT %s
                """,
                (username, tenant_id, tenant_id, limit),
            )
        rows = c.fetchall()
        return [
            {
                "event_type": r[0],
                "ip": r[1],
                "user_agent": r[2],
                "country": r[3],
                "metadata": r[4] or {},
                "created_at": str(r[5]),
            }
            for r in rows
        ]
    except Exception as e:
        logger.warning("[AuthEvents] Echec get_recent_events: %s", str(e)[:200])
        return []
    finally:
        try:
            if conn:
                conn.close()
        except Exception:
            pass
