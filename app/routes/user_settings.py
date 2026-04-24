"""
Endpoints Paramètres utilisateur (Settings).

Page publique (tout utilisateur connecte) accessible via le menu
3 points du chat > Parametres.

  GET /settings  -> sert la page user_settings.html (HTML statique)

Les endpoints d'API pour cette page sont deja implementes ailleurs :
  - GET /profile, PUT /profile/*       (app/routes/admin/profile.py)
  - GET /memory/rules                  (app/routes/memory.py)
  - GET /account/export, POST /account/delete/request (app/rgpd.py)

Cette route ne fait que servir le shell HTML + CSS + JS.
Le branchement des endpoints se fera en Phase 2-6.
"""
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.routes.deps import require_user
from app.logging_config import get_logger

logger = get_logger("raya.user_settings")
router = APIRouter(tags=["user_settings"])


@router.get("/settings", response_class=HTMLResponse)
def user_settings_page(request: Request):
    """Sert la page Paramètres utilisateur.

    Si l'utilisateur n'est pas authentifie, redirige vers /login-app.
    """
    try:
        require_user(request)
    except Exception:
        return RedirectResponse("/login-app")
    try:
        with open("app/templates/user_settings.html", "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    except FileNotFoundError:
        logger.error("Template user_settings.html introuvable.")
        return HTMLResponse(
            content="<h1>Erreur 500</h1><p>Template introuvable.</p>",
            status_code=500,
        )
