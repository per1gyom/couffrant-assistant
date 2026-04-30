"""
Endpoints HTTP du système feature flags.

Phase 1 (30/04/2026) :
  GET /me/features                              (auth user) - features du tenant courant
  GET /admin/features                           (super_admin) - catalogue complet
  GET /admin/tenants/{tenant_id}/features       (super_admin) - état par tenant
  POST /admin/tenants/{tenant_id}/features/{key} (super_admin) - toggle ON/OFF

Phase 2 (demain) : UI dans le panel super_admin (cartes par tenant + toggle).
Phase 3 (demain) : application des décorateurs @require_feature() sur les
endpoints existants (audio_capture, vesta_connector, etc.).
"""
from fastapi import APIRouter, Body, Depends, HTTPException, Request

from app.admin_audit import log_admin_action
from app.feature_flags import (
    get_features_for_tenant,
    invalidate_cache,
    is_feature_enabled,
    list_all_features,
    set_tenant_feature,
)
from app.logging_config import get_logger
from app.routes.deps import require_admin, require_super_admin, require_user
from app.admin_2fa_stepup import require_recent_stepup

logger = get_logger("raya.feature_flags_routes")

router = APIRouter(tags=["feature_flags"])


# ─── ENDPOINTS USER ────────────────────────────────────────────────────


@router.get("/me/features")
def my_features(request: Request, user: dict = Depends(require_user)):
    """Renvoie l état des features pour le tenant courant.

    Format : {feature_key: enabled, ...}
    Inclut TOUTES les features non-deprecated du registry.

    Le front appelle cet endpoint au load de l app et cache 60s.
    Permet de masquer les boutons des features désactivées côté UI.
    """
    tenant_id = user.get("tenant_id")
    if not tenant_id:
        raise HTTPException(401, "tenant_id manquant en session")

    features = get_features_for_tenant(tenant_id)
    return {
        "tenant_id": tenant_id,
        "features": features,
        "count": len(features),
    }


# ─── ENDPOINTS SUPER_ADMIN — Phase 2 préparation ───────────────────────


@router.get("/admin/features")
def admin_list_features(_: dict = Depends(require_super_admin)):
    """Liste le catalogue complet des features (avec metadata).

    Pour la future UI super_admin Phase 2.
    Renvoie : [{feature_key, label, description, category, default_enabled, deprecated}, ...]
    """
    return {
        "features": list_all_features(),
    }


@router.get("/admin/tenants/{tenant_id}/features")
def admin_get_tenant_features(
    tenant_id: str,
    _: dict = Depends(require_super_admin),
):
    """Renvoie l état des features pour un tenant spécifique.

    Pour la future UI super_admin Phase 2 (vue 'gérer les features de X').
    Inclut les features désactivées et les overrides explicites.
    """
    features = get_features_for_tenant(tenant_id)
    return {
        "tenant_id": tenant_id,
        "features": features,
        "count": len(features),
    }


@router.post("/admin/tenants/{tenant_id}/features/{feature_key}")
def admin_set_tenant_feature(
    request: Request,
    tenant_id: str,
    feature_key: str,
    payload: dict = Body(...),
    admin: dict = Depends(require_super_admin),
    _stepup: dict = Depends(require_recent_stepup),
):
    """Active/désactive une feature pour un tenant (super_admin uniquement).

    Body JSON :
      {
        "enabled": true | false,
        "notes": "raison optionnelle"
      }

    Step-up 2FA requis (action structurelle pouvant impacter l usage du tenant).
    Cache invalidé automatiquement.
    """
    enabled = payload.get("enabled")
    if enabled is None or not isinstance(enabled, bool):
        raise HTTPException(400, "Le champ 'enabled' doit etre un booleen (true/false)")

    notes = (payload.get("notes") or "").strip() or None

    success = set_tenant_feature(
        tenant_id=tenant_id,
        feature_key=feature_key,
        enabled=enabled,
        updated_by=admin["username"],
        notes=notes,
    )
    if not success:
        raise HTTPException(500, f"Erreur lors du toggle. Verifier que '{feature_key}' existe dans le registry.")

    # Audit log
    log_admin_action(
        admin["username"],
        "set_tenant_feature",
        tenant_id,
        f"{feature_key}={enabled} notes={notes or '-'}",
    )

    return {
        "success": True,
        "tenant_id": tenant_id,
        "feature_key": feature_key,
        "enabled": enabled,
        "message": f"Feature '{feature_key}' {'activee' if enabled else 'desactivee'} pour {tenant_id}",
    }


@router.post("/admin/features/cache/invalidate")
def admin_invalidate_cache(
    payload: dict = Body(default={}),
    _: dict = Depends(require_super_admin),
):
    """Invalide le cache feature flags.

    Body JSON optionnel :
      {"tenant_id": "couffrant_solar"}  -> invalide juste ce tenant
      {} ou pas de body                 -> invalide tout

    Utile pour debug ou apres une migration manuelle en DB.
    """
    tenant_id = (payload.get("tenant_id") or "").strip() or None
    invalidate_cache(tenant_id)
    return {
        "success": True,
        "scope": tenant_id or "global",
        "message": f"Cache invalide pour {'tenant ' + tenant_id if tenant_id else 'TOUS les tenants'}",
    }
