"""
Routes super admin pour lister/selectionner les sites SharePoint
accessibles avec le token Microsoft existant du tenant.

GET  /admin/sharepoint/sites/{tenant_id}
  -> liste les sites SharePoint accessibles avec le token MS du tenant
POST /admin/sharepoint/select
  -> enregistre le site choisi dans tenant_connections (tool_type='sharepoint')

Pas besoin d'un nouvel OAuth : Sites.Read.All est deja dans GRAPH_SCOPES
(cf config.py). On reutilise le token Microsoft du super-admin.
"""
from fastapi import APIRouter, Request, Depends, Body
from fastapi.responses import JSONResponse
from app.routes.deps import require_admin
from app.connection_token_manager import get_connection_token
from app.connections import create_connection
from app.logging_config import get_logger

logger = get_logger("raya.admin_sharepoint")
router = APIRouter(tags=["admin_sharepoint"])


# ---- LISTER LES SITES SHAREPOINT ACCESSIBLES --------------------------

@router.get("/admin/sharepoint/sites/{tenant_id}")
def admin_list_sharepoint_sites(
    request: Request,
    tenant_id: str,
    admin: dict = Depends(require_admin),
):
    """
    Liste les sites SharePoint accessibles par le compte Microsoft
    du super-admin connecte (qui gere les connexions du tenant).
    Retourne : [{id, name, webUrl, description}]
    """
    import requests
    # Utilise le token Microsoft du super-admin qui cree la connexion
    token = get_connection_token(admin["username"], "microsoft")
    if not token:
        return JSONResponse({
            "status": "error",
            "message": "Aucun token Microsoft disponible pour le super-admin. "
                       "Connecte d'abord ta boite Outlook avant de choisir un site SharePoint.",
        }, status_code=400)

    try:
        # Recherche globale de sites (search=* renvoie tous les sites accessibles)
        url = "https://graph.microsoft.com/v1.0/sites?search=*"
        headers = {"Authorization": f"Bearer {token}"}
        r = requests.get(url, headers=headers, timeout=15)
        if r.status_code != 200:
            logger.error("[SharePoint] sites list error: %s %s", r.status_code, r.text[:300])
            return JSONResponse({
                "status": "error",
                "message": f"Erreur Graph API : {r.status_code}",
                "detail": r.text[:400],
            }, status_code=500)
        data = r.json()
        sites = []
        for s in data.get("value", []):
            sites.append({
                "id": s.get("id", ""),
                "name": s.get("displayName") or s.get("name") or "",
                "webUrl": s.get("webUrl", ""),
                "description": s.get("description", ""),
            })
        return {"status": "ok", "sites": sites, "count": len(sites)}
    except Exception as e:
        logger.exception("[SharePoint] list exception")
        return JSONResponse({"status": "error", "message": str(e)[:200]}, status_code=500)


# ---- ENREGISTRER LE SITE CHOISI ---------------------------------------

@router.post("/admin/sharepoint/select")
def admin_select_sharepoint_site(
    request: Request,
    payload: dict = Body(...),
    admin: dict = Depends(require_admin),
):
    """
    Enregistre le site SharePoint choisi dans tenant_connections.
    payload : {
      "tenant_id": "couffrant_solar",
      "site_id": "couffrantsolar.sharepoint.com,abc-123,def-456",
      "site_name": "Commun",
      "site_url": "https://couffrantsolar.sharepoint.com/sites/Commun",
      "label": "SharePoint - Commun" (optionnel)
    }
    Cree une nouvelle tenant_connections (tool_type='sharepoint')
    et la marque connected.
    """
    tenant_id = (payload.get("tenant_id") or "").strip()
    site_id = (payload.get("site_id") or "").strip()
    site_name = (payload.get("site_name") or "").strip()
    site_url = (payload.get("site_url") or "").strip()
    label = (payload.get("label") or f"SharePoint - {site_name}").strip()

    if not tenant_id or not site_id:
        return JSONResponse({
            "status": "error",
            "message": "tenant_id et site_id obligatoires",
        }, status_code=400)

    # La connexion SharePoint reutilise le token MS du tenant, donc on
    # stocke juste le site_id et site_url en config. auth_type='shared_ms'
    # pour indiquer qu elle depend de la connexion Microsoft existante.
    result = create_connection(
        tenant_id=tenant_id,
        tool_type="sharepoint",
        label=label,
        auth_type="shared_ms",
        config={
            "site_id": site_id,
            "site_name": site_name,
            "site_url": site_url,
        },
        credentials={},
        created_by=admin["username"],
        status="connected",
    )
    if result.get("status") != "ok":
        return JSONResponse(result, status_code=500)
    logger.info("[SharePoint] site %s lie au tenant %s par %s",
                site_name, tenant_id, admin["username"])
    return {"status": "ok", "connection": result.get("connection")}
