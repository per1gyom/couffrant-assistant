from fastapi import Request, HTTPException, status, Depends
from app.app_security import (
    SCOPE_ADMIN, SCOPE_TENANT_ADMIN, SCOPE_TENANT_USER,
    get_tenant_id,
)
# Nouveau scope super_admin + hardcoded
try:
    from app.app_security import SCOPE_SUPER_ADMIN
except ImportError:
    SCOPE_SUPER_ADMIN = "super_admin"
from app.hardcoded_permissions import is_hardcoded_super_admin, get_effective_scope


def require_user(request: Request) -> dict:
    """
    Dépendance FastAPI — retourne {username, tenant_id, scope} si connecté.
    Lève HTTPException 401 sinon.

    Usage :
        @router.post("/endpoint")
        def mon_endpoint(user: dict = Depends(require_user)):
            username = user["username"]
            tenant_id = user["tenant_id"]
    """
    username = request.session.get("user")
    if not username:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentification requise",
        )
    tenant_id = request.session.get("tenant_id")
    if not tenant_id:
        try:
            tenant_id = get_tenant_id(username)
        except Exception:
            tenant_id = None
        if not tenant_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Tenant introuvable pour cet utilisateur",
            )
    # Vérification suspension (API + web)
    _check_suspension_api(username, tenant_id)
    # Scope effectif : si l user est dans HARDCODED_SUPER_ADMINS, on force super_admin
    # quelle que soit la valeur en DB ou en session. Empeche toute retrogradation
    # accidentelle ou malveillante.
    db_scope = request.session.get("scope", SCOPE_TENANT_USER)
    email = request.session.get("email") or ""
    effective_scope = get_effective_scope(email, db_scope)
    return {
        "username": username,
        "tenant_id": tenant_id,
        "scope": effective_scope,
        "email": email,
    }


def _check_suspension_api(username: str, tenant_id: str):
    """Vérifie la suspension pour les appels API. Lève 403 si suspendu."""
    try:
        from app.suspension import check_suspension
        suspended, reason = check_suspension(username, tenant_id)
        if suspended:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=reason,
            )
    except HTTPException:
        raise
    except Exception:
        pass


def require_super_admin(request: Request) -> dict:
    """Super-admin Raya uniquement (hardcode OU scope='super_admin'). Leve 403 sinon.

    Le status de super_admin hardcode est applique via require_user() qui lit
    get_effective_scope(). Donc il suffit de verifier scope == SCOPE_SUPER_ADMIN.
    """
    user = require_user(request)
    if user["scope"] != SCOPE_SUPER_ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Privileges super-administrateur Raya requis",
        )
    return user


def require_admin(request: Request) -> dict:
    """Admin Raya ou super-admin. Leve 403 sinon.

    Accepte SCOPE_ADMIN (collaborateur Raya) OU SCOPE_SUPER_ADMIN (fondateur).
    Le super_admin a tous les droits d un admin, donc les 2 accedent.
    """
    user = require_user(request)
    if user["scope"] not in (SCOPE_SUPER_ADMIN, SCOPE_ADMIN):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Privileges administrateur requis",
        )
    return user


def require_tenant_admin(request: Request) -> dict:
    """Admin du tenant ou super-admin. Lève 403 sinon."""
    user = require_user(request)
    if user["scope"] not in (SCOPE_SUPER_ADMIN, SCOPE_ADMIN, SCOPE_TENANT_ADMIN):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Privilèges administrateur tenant requis",
        )
    return user


def get_session_tenant_id(request: Request) -> str:
    """Retourne le tenant_id de la session. Défaut : 'couffrant_solar'."""
    return request.session.get("tenant_id", "couffrant_solar")


def assert_same_tenant(request: Request, target_username: str) -> None:
    """
    Vérifie qu'un tenant_admin ne manipule que des users de son propre tenant.
    Lève HTTPException 403 si violation. Super-admin passe toujours.
    """
    user = require_user(request)
    # Super_admin ET admin Raya passent toujours (cross-tenant autorise)
    if user["scope"] in (SCOPE_SUPER_ADMIN, SCOPE_ADMIN):
        return
    target_tenant = get_tenant_id(target_username)
    if user["tenant_id"] != target_tenant:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"L'utilisateur '{target_username}' n'appartient pas à votre tenant",
        )



# ──────────────────────────────────────────────────────────────────────────
# require_admin_2fa_validated — guard specifique pages HTML /admin
# ──────────────────────────────────────────────────────────────────────────
# Decision Guillaume 30/04 (LOT 3 du chantier 2FA) :
#  - 2FA Authenticator demandee 1x par semaine pour acces /admin
#  - Ne touche pas le login chat (Niveau 1 = password seul)
#  - Filet de secours : env var DISABLE_2FA_ENFORCEMENT=true
#
# Different de require_admin() (utilise pour les endpoints API qui
# repondent JSON) car ce guard RENVOIE des HTMLResponse (redirection vers
# /admin/2fa-challenge ou /admin/2fa/setup).
# ──────────────────────────────────────────────────────────────────────────

def require_admin_2fa_validated(request: Request):
    """Verifie que le user est admin ET que sa 2FA admin est validee < 7j.

    Utilise sur les routes HTML qui servent un panel admin (ex: /admin/panel,
    /admin/connexions). PAS sur les endpoints API qui doivent repondre 401/403.

    Comportement :
    1. Si pas authentifie -> redirige /login-app (HTMLResponse RedirectResponse)
    2. Si pas admin -> 403
    3. Si DISABLE_2FA_ENFORCEMENT=true -> on passe (filet d urgence)
    4. Si user n a pas active sa 2FA :
       - Si encore en grace 7j -> on laisse passer (warning sera affiche par UI)
       - Si grace expiree -> redirige vers /admin/2fa/setup?required=1
    5. Si user a active sa 2FA :
       - Si validation < 7j -> on laisse passer
       - Si validation > 7j ou jamais -> redirige vers /admin/2fa-challenge

    Returns le dict user{} si tout OK. Sinon leve HTTPException avec une
    RedirectResponse en detail (capture par un exception_handler dans main).

    NB: Comme FastAPI ne supporte pas nativement le retour d une RedirectResponse
    depuis une dependance, on utilise un trick : on raise une HTTPException avec
    un header Location, et un middleware ou exception_handler la transforme en 303.
    """
    from fastapi.responses import RedirectResponse
    from fastapi import HTTPException, status as _status
    from app.admin_2fa_session import (
        is_2fa_enforcement_disabled,
        has_user_activated_2fa,
        is_user_in_grace_period,
        needs_admin_2fa,
        SCOPES_REQUIRING_2FA,
    )

    # 1. Authentification (lance HTTPException 401 si pas connecte)
    user = require_user(request)

    # 2. Scope admin requis
    if user["scope"] not in SCOPES_REQUIRING_2FA:
        raise HTTPException(
            status_code=_status.HTTP_403_FORBIDDEN,
            detail="Privileges administrateur requis",
        )

    # 3. Bypass urgence
    if is_2fa_enforcement_disabled():
        return user

    username = user["username"]

    # 4. User n a pas encore active sa 2FA
    if not has_user_activated_2fa(username):
        if is_user_in_grace_period(username):
            # Grace : laisser passer, warning visible dans le panel
            return user
        else:
            # Grace expiree : forcer setup
            raise HTTPException(
                status_code=_status.HTTP_303_SEE_OTHER,
                detail="2FA setup required",
                headers={"Location": "/admin/2fa/setup?required=1"},
            )

    # 5. 2FA active : verifier la validite
    if needs_admin_2fa(request, user):
        # Sauve l URL d origine pour la restorer apres validation
        request.session["pending_admin_path"] = str(request.url.path)
        raise HTTPException(
            status_code=_status.HTTP_303_SEE_OTHER,
            detail="2FA challenge required",
            headers={"Location": "/admin/2fa-challenge"},
        )

    return user
