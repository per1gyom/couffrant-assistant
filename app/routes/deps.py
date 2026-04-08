from fastapi import Request
from app.app_security import SCOPE_ADMIN, SCOPE_TENANT_ADMIN, SCOPE_CS, SCOPE_USER


def require_user(request: Request) -> str | None:
    """Retourne username si connecté, sinon None."""
    return request.session.get("user")


def require_admin(request: Request) -> bool:
    """Super-admin système uniquement."""
    return request.session.get("scope") == SCOPE_ADMIN


def require_tenant_admin(request: Request) -> bool:
    """
    Vrai si l'utilisateur peut administrer son tenant.
    Inclut le super-admin et le tenant_admin.
    """
    return request.session.get("scope") in (SCOPE_ADMIN, SCOPE_TENANT_ADMIN)


def get_session_tenant_id(request: Request) -> str:
    """Retourne le tenant_id de la session. Défaut : 'couffrant_solar'."""
    return request.session.get("tenant_id", "couffrant_solar")


def assert_same_tenant(request: Request, target_username: str) -> tuple[bool, str]:
    """
    Vérifie qu'un tenant_admin ne manipule que des users de son propre tenant.
    Retourne (ok, error_message).
    Super-admin passe toujours.
    """
    scope = request.session.get("scope")
    if scope == SCOPE_ADMIN:
        return True, ""
    from app.app_security import get_tenant_id
    session_tenant = get_session_tenant_id(request)
    target_tenant = get_tenant_id(target_username)
    if session_tenant != target_tenant:
        return False, f"L'utilisateur '{target_username}' n'appartient pas à votre tenant."
    return True, ""
