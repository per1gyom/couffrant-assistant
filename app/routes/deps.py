from fastapi import Request, HTTPException, status, Depends
from app.app_security import (
    SCOPE_ADMIN, SCOPE_TENANT_ADMIN, SCOPE_CS, SCOPE_USER,
    get_tenant_id,
)


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
    return {
        "username": username,
        "tenant_id": tenant_id,
        "scope": request.session.get("scope", SCOPE_USER),
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


def require_admin(request: Request) -> dict:
    """Super-admin système uniquement. Lève 403 si pas admin."""
    user = require_user(request)
    if user["scope"] != SCOPE_ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Privilèges super-administrateur requis",
        )
    return user


def require_tenant_admin(request: Request) -> dict:
    """Admin du tenant ou super-admin. Lève 403 sinon."""
    user = require_user(request)
    if user["scope"] not in (SCOPE_ADMIN, SCOPE_TENANT_ADMIN):
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
    if user["scope"] == SCOPE_ADMIN:
        return
    target_tenant = get_tenant_id(target_username)
    if user["tenant_id"] != target_tenant:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"L'utilisateur '{target_username}' n'appartient pas à votre tenant",
        )
