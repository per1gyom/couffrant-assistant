"""
app/routes/admin package — réexporte le router combiné.

L'import `from app.routes.admin import router as admin_router` dans main.py
continue à fonctionner sans changement.

Sous-modules :
  profile.py      — GET/PUT /profile, /profile/email, /profile/password
  tenant_admin.py — /tenant/* (tenant_admin)
  super_admin.py  — /admin/* (super_admin)
  health.py       — /admin/health* (Phase Connexions Universelles 1er mai)
  admin_mail.py   — /admin/mail/* (chantier B 04/05 : inventaire, bootstrap, graphe)
"""
from fastapi import APIRouter

from app.routes.admin.profile import router as _profile_router
from app.routes.admin.tenant_admin import router as _tenant_router
from app.routes.admin.super_admin import router as _super_router
from app.routes.admin.health import router as _health_router
from app.routes.admin.admin_mail import router as _admin_mail_router

router = APIRouter(tags=["admin"])
router.include_router(_profile_router)
router.include_router(_tenant_router)
router.include_router(_super_router)
router.include_router(_health_router)
router.include_router(_admin_mail_router)

__all__ = ["router"]
