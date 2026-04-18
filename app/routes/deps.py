from fastapi import Request, HTTPException, status, Depends
from app.app_security import (
    SCOPE_ADMIN, SCOPE_TENANT_ADMIN, SCOPE_CS, SCOPE_USER,
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
    db_scope = request.session.get("scope", SCOPE_USER)
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
