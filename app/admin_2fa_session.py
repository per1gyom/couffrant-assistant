"""
Helpers session 2FA pour l acces aux panels /admin et /super_admin.

Implemente le modele Niveau 2 valide par Guillaume le 30/04/2026 :
- 2FA Authenticator demandee UNE FOIS PAR SEMAINE max sur /admin
- Pas de 2FA pour /chat (Niveau 1 = password seul)
- Validation gardee pendant 7 jours (par appareil via cookie session)

Variables session utilisees :
    request.session["admin_2fa_validated_at"] : timestamp Unix de la derniere
        validation 2FA reussie pour l acces admin. Quand est-ce qu on
        redemande la 2FA :
        - Si absente OU > ADMIN_2FA_VALIDITY_SECONDS (7j)
        - SAUF si user n a pas encore active sa 2FA (grace period 7j)

    request.session["pending_admin_path"] : URL d origine sauvegardee
        avant la redirection vers /admin/2fa-challenge pour la restorer
        apres validation.

Env vars :
    DISABLE_2FA_ENFORCEMENT=true : court-circuite TOUS les checks 2FA admin.
        Filet de securite a activer en cas de bug. A retirer une fois LOT 3
        stabilise.
"""
import os
import time
from typing import Optional

from app.app_security import SCOPE_ADMIN, SCOPE_SUPER_ADMIN, SCOPE_TENANT_ADMIN
from app.database import get_pg_conn
from app.logging_config import get_logger

logger = get_logger("raya.admin_2fa")

# 2FA validee = 7 jours (1 semaine, decision Guillaume 30/04)
ADMIN_2FA_VALIDITY_SECONDS = 7 * 24 * 3600

# Periode de grace pour activer sa 2FA apres premiere connexion admin
GRACE_PERIOD_DAYS = 7

# Scopes qui doivent passer la 2FA pour /admin
SCOPES_REQUIRING_2FA = (SCOPE_SUPER_ADMIN, SCOPE_ADMIN, SCOPE_TENANT_ADMIN)


def is_2fa_enforcement_disabled() -> bool:
    """Renvoie True si l env var DISABLE_2FA_ENFORCEMENT est true.

    Permet de bypass tous les checks 2FA en cas d urgence (bug bloquant).
    Lue dynamiquement a chaque appel (pas besoin de restart Railway).
    """
    return os.getenv("DISABLE_2FA_ENFORCEMENT", "").strip().lower() in (
        "true", "1", "yes", "on"
    )


def has_user_activated_2fa(username: str) -> bool:
    """Renvoie True si l user a totp_enabled_at IS NOT NULL en DB."""
    if not username:
        return False
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute(
            "SELECT totp_enabled_at FROM users WHERE username = %s AND deleted_at IS NULL",
            (username,),
        )
        row = c.fetchone()
        return bool(row and row[0] is not None)
    except Exception as e:
        logger.error("[2FA] has_user_activated_2fa error: %s", str(e)[:200])
        return False
    finally:
        if conn:
            conn.close()


def is_user_in_grace_period(username: str) -> bool:
    """Renvoie True si l user est dans sa periode de grace 2FA (7j depuis created_at).

    Pendant la grace, on laisse passer meme sans 2FA active, mais on affiche
    un warning a chaque visite admin pour rappeler d activer sa 2FA.
    """
    if not username:
        return False
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute(
            "SELECT created_at, scope FROM users WHERE username = %s AND deleted_at IS NULL",
            (username,),
        )
        row = c.fetchone()
        if not row or not row[0]:
            return False
        created_at, scope = row
        # Pas de grace pour scopes qui ne sont pas concernes
        if scope not in SCOPES_REQUIRING_2FA:
            return False
        from datetime import datetime, timedelta
        grace_ends = created_at + timedelta(days=GRACE_PERIOD_DAYS)
        return datetime.utcnow() < grace_ends
    except Exception as e:
        logger.error("[2FA] is_user_in_grace_period error: %s", str(e)[:200])
        return False
    finally:
        if conn:
            conn.close()


def needs_admin_2fa(request, user: dict) -> bool:
    """Decide si on doit demander la 2FA a ce user pour acceder a /admin.

    Logique :
    1. Si DISABLE_2FA_ENFORCEMENT=true -> jamais de 2FA (bypass urgence)
    2. Si scope pas concerne (ex: tenant_user) -> pas de 2FA
       (ce cas ne devrait pas arriver via require_admin mais ceinture-bretelles)
    3. Si user n a pas active sa 2FA -> pas de 2FA tant qu il est en grace
    4. Si user est dans grace 7j -> on laisse passer, warning affiche
    5. Si grace expiree ET 2FA pas activee -> on bloque (gere ailleurs)
    6. Si user a active sa 2FA :
        - Si validation < 7j -> pas de 2FA, on laisse passer
        - Si validation > 7j ou absente -> redemande 2FA

    Returns True si on doit demander la 2FA, False sinon.
    """
    # 1. Bypass urgence
    if is_2fa_enforcement_disabled():
        return False

    # 2. Scope pas concerne (ne devrait pas arriver)
    if user.get("scope") not in SCOPES_REQUIRING_2FA:
        return False

    username = user.get("username", "")
    if not username:
        return False

    # 3 & 4 & 5. User n a pas encore active sa 2FA
    if not has_user_activated_2fa(username):
        # Si en grace -> laisser passer (le warning sera affiche par l UI)
        # Si grace expiree -> renvoyer False ici pour permettre l acces, mais
        # un autre check (must_setup_2fa) bloquera dans la page admin.
        # On gere le hard-block dans require_admin_with_2fa() au-dessus.
        return False

    # 6. User a active sa 2FA -> verifier validite
    last_validated = request.session.get("admin_2fa_validated_at", 0)
    age = time.time() - last_validated
    return age > ADMIN_2FA_VALIDITY_SECONDS


def must_setup_2fa_now(username: str) -> bool:
    """Renvoie True si l user doit OBLIGATOIREMENT activer sa 2FA maintenant.

    Cas : scope qui requiert la 2FA + pas active + grace expiree.
    Dans ce cas on doit le rediriger vers /admin/2fa/setup avec un message
    bloquant.
    """
    if not username:
        return False
    if is_2fa_enforcement_disabled():
        return False
    if has_user_activated_2fa(username):
        return False
    return not is_user_in_grace_period(username)


def mark_admin_2fa_validated(request) -> None:
    """Pose le timestamp de validation 2FA dans la session.

    Doit etre appele apres une verification reussie d un code TOTP ou recovery.
    """
    request.session["admin_2fa_validated_at"] = time.time()


def get_admin_2fa_remaining_days(request) -> Optional[int]:
    """Renvoie le nombre de jours restants avant expiration de la 2FA admin.

    Returns None si jamais validee, sinon int >= 0.
    """
    last = request.session.get("admin_2fa_validated_at", 0)
    if not last:
        return None
    elapsed = time.time() - last
    remaining = ADMIN_2FA_VALIDITY_SECONDS - elapsed
    if remaining <= 0:
        return 0
    return int(remaining / 86400)
