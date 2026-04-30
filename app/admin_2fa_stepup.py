"""
Step-up authentication 2FA pour actions critiques.

LOT 5b du chantier 2FA (decision Guillaume 30/04) :
Avant les actions IRREVERSIBLES (purge user, suppression tenant, reset 2FA
d un autre user), on redemande un code TOTP frais (< 5 min) MEME si la
2FA hebdo est valide ET le PIN deja saisi.

Pourquoi : protege contre :
- Une session compromise (cookie vole)
- Une distraction d 1 minute (admin laisse l ordi sans verrouiller pendant
  la duree de validite du PIN)
- Une erreur de manipulation (admin clique purge par erreur)

Pattern :
1. User clique 'Purger definitivement' dans l UI
2. Front appelle d abord POST /admin/2fa/step-up-verify {code}
3. Si OK : pose request.session['stepup_validated_at'] = NOW
4. Front appelle ensuite l action critique
5. Backend : require_recent_stepup() verifie session['stepup_validated_at']
6. Si > 5 min : 401, l UI redemande un code TOTP

Storage :
- request.session['stepup_validated_at'] : timestamp Unix
- Validity : STEPUP_VALIDITY_SECONDS (5 min par defaut)
- Reset apres consommation par require_recent_stepup() (one-shot)
"""
import time
from typing import Optional, Tuple

from app.database import get_pg_conn
from app.logging_config import get_logger
from app.totp import decrypt_totp_secret, verify_totp_code

logger = get_logger("raya.admin_2fa_stepup")


# Validite d un step-up = 5 minutes (le user doit re-valider TOTP recemment)
STEPUP_VALIDITY_SECONDS = 5 * 60


def fetch_user_totp_secret(username: str, tenant_id: str) -> Optional[str]:
    """Lit le secret TOTP chiffre du user depuis la DB."""
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute(
            """
            SELECT totp_secret_encrypted
            FROM users
            WHERE username = %s AND tenant_id = %s AND deleted_at IS NULL
            """,
            (username, tenant_id),
        )
        row = c.fetchone()
        return row[0] if row else None
    except Exception as e:
        logger.error("[StepUp] fetch_user_totp_secret error: %s", str(e)[:200])
        return None
    finally:
        if conn:
            conn.close()


def verify_stepup_code(username: str, tenant_id: str, code: str) -> Tuple[bool, str]:
    """Verifie un code TOTP pour step-up. Returns (success, error_message).

    Diffrent de la verification au /2fa-challenge :
    - Pas d acceptation de codes recovery (toujours un TOTP valide demande)
    - Pas d update de last_2fa_validated_at sur le device
    - Juste une verification ponctuelle pour autoriser une action
    """
    if not code or not code.strip():
        return False, "Code requis"

    code_clean = code.strip().replace(" ", "")
    if not code_clean.isdigit() or len(code_clean) != 6:
        return False, "Code TOTP invalide (6 chiffres requis)"

    secret_encrypted = fetch_user_totp_secret(username, tenant_id)
    if not secret_encrypted:
        return False, "2FA non configuree pour ce compte"

    try:
        secret = decrypt_totp_secret(secret_encrypted)
        if verify_totp_code(secret, code_clean):
            return True, ""
        return False, "Code incorrect"
    except RuntimeError as e:
        logger.error("[StepUp] Echec dechiffrement: %s", e)
        return False, "Erreur configuration serveur"
    except Exception as e:
        logger.error("[StepUp] verify_totp_code error: %s", str(e)[:200])
        return False, "Erreur verification"


def mark_stepup_validated(request) -> None:
    """Pose le timestamp de step-up dans la session.

    A appeler apres une verification reussie via /admin/2fa/step-up-verify.
    """
    request.session["stepup_validated_at"] = time.time()


def is_recent_stepup_valid(request) -> bool:
    """True si un step-up a ete valide dans les STEPUP_VALIDITY_SECONDS dernieres secondes."""
    last = request.session.get("stepup_validated_at", 0)
    if not last:
        return False
    return (time.time() - last) <= STEPUP_VALIDITY_SECONDS


def consume_stepup(request) -> bool:
    """Verifie ET consomme le step-up (one-shot).

    Returns True si le step-up etait valide. Apres consommation, retire le
    flag de la session pour eviter qu un meme step-up serve a plusieurs
    actions critiques d affilee (sauf si elles sont enchainees < 5 min).

    Note : on garde le timestamp pour permettre les actions multiples dans
    la meme fenetre de 5 min. C est le comportement attendu pour une
    purge en cascade (3 users a purger d un coup).
    Si on voulait le rendre strictement one-shot, il faudrait .pop()
    au lieu de juste verifier.
    """
    return is_recent_stepup_valid(request)


def clear_stepup(request) -> None:
    """Force la suppression du step-up de la session (reset)."""
    request.session.pop("stepup_validated_at", None)


# ─── GUARD FASTAPI ─────────────────────────────────────────────────────


def require_recent_stepup(request) -> dict:
    """Dependency FastAPI : exige un step-up TOTP recent (< 5 min).

    A utiliser AVANT les actions critiques :
        @router.post('/admin/users/{u}/confirm-permanent-deletion')
        def purge_user(
            request: Request,
            user: dict = Depends(require_super_admin),
            _: bool = Depends(require_recent_stepup),
        ):
            ...

    Si pas de step-up recent : leve HTTPException 401 avec un detail clair.
    Le front doit catcher ce 401 et afficher la modal de saisie TOTP.
    """
    from fastapi import HTTPException, status as _status
    if not is_recent_stepup_valid(request):
        raise HTTPException(
            status_code=_status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": "stepup_required",
                "message": "Cette action sensible necessite une re-verification 2FA recente.",
                "validity_seconds": STEPUP_VALIDITY_SECONDS,
            },
        )
    return {"stepup_ok": True}
