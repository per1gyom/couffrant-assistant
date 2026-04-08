from fastapi import Request
from app.app_security import SCOPE_ADMIN, SCOPE_CS


def require_user(request: Request):
    """Retourne username si connecté, sinon None."""
    return request.session.get("user")


def require_admin(request: Request) -> bool:
    """Retourne True si l'utilisateur connecté est admin."""
    return request.session.get("scope", SCOPE_CS) == SCOPE_ADMIN
