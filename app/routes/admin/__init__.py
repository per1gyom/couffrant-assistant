"""
app/routes/admin package — réexporte le router combiné.

L'import `from app.routes.admin import router as admin_router` dans main.py
continue à fonctionner sans changement.

Sous-modules :
  profile.py      — GET/PUT /profile, /profile/email, /profile/password
  tenant_admin.py — /tenant/* (tenant_admin)
  super_admin.py  — /admin/* (super_admin)
"""
from fastapi import APIRouter

from app.routes.admin.profile import router as _profile_router
from app.routes.admin.tenant_admin import router as _tenant_router
from app.routes.admin.super_admin import router as _super_router

router = APIRouter(tags=["admin"])
router.include_router(_profile_router)
router.include_router(_tenant_router)
router.include_router(_super_router)

__all__ = ["router"]
