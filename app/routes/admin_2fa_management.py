"""
Endpoints super_admin pour gerer la 2FA et le PIN d autres users.

LOT 6 du chantier 2FA - decision Guillaume 30/04 :
Si Charlotte (ou un futur client) perd son telephone + ses codes recovery,
elle est verrouillee dehors. Le super_admin doit pouvoir reinitialiser
sa 2FA depuis le panel pour la debloquer.

Endpoints :
  GET  /admin/users/{username}/2fa-status  - voir l etat 2FA + PIN
  POST /admin/users/{username}/reset-2fa   - reset complet 2FA d un user
  POST /admin/users/{username}/reset-pin   - reset PIN seul (sans toucher 2FA)
  POST /admin/users/{username}/reset-trusted-devices - vider devices trusted

Securite :
  - require_super_admin (uniquement Guillaume + futurs co-fondateurs)
  - log_admin_action pour traçabilite
  - log_auth_event pour la victime du reset
  - Pas d auto-reset (on ne peut pas reset sa propre 2FA via cet endpoint —
    le super_admin doit utiliser ses codes recovery ou se faire reset par
    un autre super_admin)
"""
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Request

from app.admin_audit import log_admin_action
from app.auth_events import log_auth_event
from app.database import get_pg_conn
from app.logging_config import get_logger
from app.routes.deps import require_super_admin
from app.admin_2fa_stepup import require_recent_stepup

logger = get_logger("raya.admin_2fa_mgmt")

router = APIRouter(tags=["admin", "2fa-management"])


def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
    if fwd:
        return fwd
    return request.client.host if request.client else "unknown"


# ─── GET /admin/users/{username}/2fa-status ─────────────────────────────


@router.get("/admin/users/{username}/2fa-status")
def get_user_2fa_status(
    request: Request,
    username: str,
    admin: dict = Depends(require_super_admin),
):
    """Renvoie l etat 2FA + PIN + devices trusted d un user.

    Pour le panel super_admin : voir si Charlotte a configure sa 2FA,
    combien de codes recovery il lui reste, si son PIN est bloque, etc.
    """
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute(
            """
            SELECT
                username, scope, tenant_id,
                totp_enabled_at,
                COALESCE(jsonb_array_length(recovery_codes_hashes), 0),
                COALESCE(recovery_codes_used_count, 0),
                pin_hash IS NOT NULL,
                pin_set_at,
                pin_attempts_count,
                pin_locked_until
            FROM users
            WHERE username = %s AND deleted_at IS NULL
            """,
            (username,),
        )
        row = c.fetchone()
        if not row:
            raise HTTPException(404, f"Utilisateur '{username}' introuvable")

        # Compter les devices trusted actifs
        c.execute(
            """
            SELECT COUNT(*) FROM user_devices
            WHERE username = %s AND expires_at > NOW()
            """,
            (username,),
        )
        devices_count = (c.fetchone() or [0])[0]

        return {
            "username": row[0],
            "scope": row[1],
            "tenant_id": row[2],
            "totp_enabled": row[3] is not None,
            "totp_enabled_at": row[3].isoformat() if row[3] else None,
            "recovery_codes_remaining": row[4],
            "recovery_codes_used": row[5],
            "pin_configured": bool(row[6]),
            "pin_set_at": row[7].isoformat() if row[7] else None,
            "pin_attempts": row[8] or 0,
            "pin_locked": bool(row[9]),
            "trusted_devices_count": devices_count,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("[2FA Mgmt] get_user_2fa_status error: %s", str(e)[:200])
        raise HTTPException(500, "Erreur serveur")
    finally:
        if conn:
            conn.close()


# ─── POST /admin/users/{username}/reset-2fa ─────────────────────────────


@router.post("/admin/users/{username}/reset-2fa")
def reset_user_2fa(
    request: Request,
    username: str,
    payload: dict = Body(...),
    admin: dict = Depends(require_super_admin),
    _stepup: dict = Depends(require_recent_stepup),
):
    """Reset complet de la 2FA d un user.

    Apres reset :
    - totp_secret_encrypted = NULL
    - totp_enabled_at = NULL
    - recovery_codes_hashes = []
    - recovery_codes_used_count = 0
    - pin_hash = NULL (le PIN tombe aussi car il est lie a la 2FA)
    - pin_attempts/locked = reset
    - Tous les devices trusted sont supprimes

    L user devra reactiver sa 2FA depuis zero (re-scan QR, nouveaux codes
    recovery) au prochain login admin.

    Body JSON :
    - reason (str, REQUIS) : motivation pour traçabilite (10 chars min)

    Garde-fous :
    - Pas d auto-reset (admin ne peut pas reset sa propre 2FA)
    - Reason obligatoire (min 10 caracteres)
    """
    if username == admin["username"]:
        raise HTTPException(
            400,
            "Vous ne pouvez pas reinitialiser votre propre 2FA via cet endpoint. "
            "Utilisez vos codes de recuperation, ou demandez a un autre super_admin.",
        )

    reason = (payload.get("reason") or "").strip()
    if len(reason) < 10:
        raise HTTPException(
            400,
            "Motivation requise (10 caracteres min). Ex: 'telephone perdu', 'reset suite a demande user'.",
        )

    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()

        # Verifier que l user existe et qu il avait bien une 2FA active
        c.execute(
            "SELECT tenant_id, totp_enabled_at IS NOT NULL FROM users WHERE username = %s AND deleted_at IS NULL",
            (username,),
        )
        row = c.fetchone()
        if not row:
            raise HTTPException(404, f"Utilisateur '{username}' introuvable")
        target_tenant = row[0]
        had_2fa = row[1]

        # Reset complet 2FA + PIN
        c.execute(
            """
            UPDATE users
            SET totp_secret_encrypted = NULL,
                totp_enabled_at = NULL,
                recovery_codes_hashes = '[]'::jsonb,
                recovery_codes_used_count = 0,
                pin_hash = NULL,
                pin_set_at = NULL,
                pin_attempts_count = 0,
                pin_locked_until = NULL
            WHERE username = %s AND deleted_at IS NULL
            """,
            (username,),
        )
        rows_affected = c.rowcount

        # Supprimer tous les devices trusted
        c.execute(
            "DELETE FROM user_devices WHERE username = %s",
            (username,),
        )
        devices_removed = c.rowcount

        conn.commit()

        # Audit log
        log_admin_action(
            admin["username"],
            "reset_2fa",
            username,
            f"reason={reason} devices_removed={devices_removed} had_2fa={had_2fa}",
        )

        # Auth event pour la victime
        log_auth_event(
            username=username,
            tenant_id=target_tenant,
            event_type="2fa_reset_by_admin",
            ip=_client_ip(request),
            user_agent=(request.headers.get("user-agent") or "")[:512],
            metadata={
                "reset_by": admin["username"],
                "reason": reason[:200],
                "devices_removed": devices_removed,
            },
        )

        logger.info(
            "[2FA Mgmt] %s a reset la 2FA de %s (raison: %s, %d devices supprimes)",
            admin["username"], username, reason[:80], devices_removed,
        )

        return {
            "success": True,
            "message": f"2FA de {username} reinitialisee. {devices_removed} appareil(s) trusted supprime(s).",
            "user_must_reactivate": True,
            "devices_removed": devices_removed,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("[2FA Mgmt] reset_user_2fa error: %s", str(e)[:200])
        try:
            if conn:
                conn.rollback()
        except Exception:
            pass
        raise HTTPException(500, f"Erreur lors du reset 2FA : {str(e)[:200]}")
    finally:
        if conn:
            conn.close()


# ─── POST /admin/users/{username}/reset-pin ─────────────────────────────


@router.post("/admin/users/{username}/reset-pin")
def reset_user_pin(
    request: Request,
    username: str,
    payload: dict = Body(...),
    admin: dict = Depends(require_super_admin),
    _stepup: dict = Depends(require_recent_stepup),
):
    """Reset SEUL le PIN d un user (sans toucher a la 2FA Authenticator).

    Cas d usage : l user a oublie son PIN mais a toujours son telephone.
    Apres reset, l user devra configurer un nouveau PIN au prochain acces
    admin (redirect /admin/2fa/setup?need_pin=1).

    Body JSON :
    - reason (str, REQUIS) : motivation
    """
    if username == admin["username"]:
        raise HTTPException(400, "Utilisez le bouton 'Changer mon PIN' sur votre compte.")

    reason = (payload.get("reason") or "").strip()
    if len(reason) < 10:
        raise HTTPException(400, "Motivation requise (10 caracteres min).")

    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute(
            "SELECT tenant_id FROM users WHERE username = %s AND deleted_at IS NULL",
            (username,),
        )
        row = c.fetchone()
        if not row:
            raise HTTPException(404, f"Utilisateur '{username}' introuvable")
        target_tenant = row[0]

        c.execute(
            """
            UPDATE users
            SET pin_hash = NULL,
                pin_set_at = NULL,
                pin_attempts_count = 0,
                pin_locked_until = NULL
            WHERE username = %s AND deleted_at IS NULL
            """,
            (username,),
        )
        conn.commit()

        log_admin_action(admin["username"], "reset_pin", username, f"reason={reason}")
        log_auth_event(
            username=username,
            tenant_id=target_tenant,
            event_type="pin_reset_by_admin",
            ip=_client_ip(request),
            user_agent=(request.headers.get("user-agent") or "")[:512],
            metadata={"reset_by": admin["username"], "reason": reason[:200]},
        )

        return {
            "success": True,
            "message": f"PIN de {username} reinitialise. Il devra en configurer un nouveau au prochain acces admin.",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("[2FA Mgmt] reset_user_pin error: %s", str(e)[:200])
        try:
            if conn:
                conn.rollback()
        except Exception:
            pass
        raise HTTPException(500, f"Erreur reset PIN : {str(e)[:200]}")
    finally:
        if conn:
            conn.close()


# ─── POST /admin/users/{username}/reset-trusted-devices ─────────────────


@router.post("/admin/users/{username}/reset-trusted-devices")
def reset_user_devices(
    request: Request,
    username: str,
    payload: dict = Body(...),
    admin: dict = Depends(require_super_admin),
    _stepup: dict = Depends(require_recent_stepup),
):
    """Vide les devices trusted d un user (sans toucher 2FA ni PIN).

    Cas d usage :
    - L user a perdu son ordinateur (suspicion vol)
    - Demande RGPD de nettoyage devices
    - Audit / nettoyage periodique

    Apres : l user devra retaper sa 2FA au prochain acces admin
    (le PIN reste inchange).

    Body JSON :
    - reason (str, REQUIS)
    """
    reason = (payload.get("reason") or "").strip()
    if len(reason) < 10:
        raise HTTPException(400, "Motivation requise (10 caracteres min).")

    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute(
            "SELECT tenant_id FROM users WHERE username = %s AND deleted_at IS NULL",
            (username,),
        )
        row = c.fetchone()
        if not row:
            raise HTTPException(404, f"Utilisateur '{username}' introuvable")
        target_tenant = row[0]

        c.execute("DELETE FROM user_devices WHERE username = %s", (username,))
        devices_removed = c.rowcount
        conn.commit()

        log_admin_action(
            admin["username"], "reset_trusted_devices", username,
            f"reason={reason} count={devices_removed}",
        )
        log_auth_event(
            username=username,
            tenant_id=target_tenant,
            event_type="trusted_devices_reset_by_admin",
            ip=_client_ip(request),
            metadata={"reset_by": admin["username"], "count": devices_removed, "reason": reason[:200]},
        )

        return {
            "success": True,
            "message": f"{devices_removed} appareil(s) trusted supprime(s) pour {username}.",
            "devices_removed": devices_removed,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("[2FA Mgmt] reset_user_devices error: %s", str(e)[:200])
        try:
            if conn:
                conn.rollback()
        except Exception:
            pass
        raise HTTPException(500, "Erreur reset devices")
    finally:
        if conn:
            conn.close()
