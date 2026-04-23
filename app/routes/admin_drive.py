"""
Routes super admin pour lister/selectionner les dossiers Google Drive
accessibles avec le token Gmail/Google existant du tenant.

GET  /admin/drive/folders/{tenant_id}
  -> liste les dossiers Drive racine (ou dossier parent)
POST /admin/drive/select
  -> enregistre le dossier choisi dans tenant_connections (tool_type='drive')

Pas besoin d'un nouvel OAuth : le scope drive est deja dans les GMAIL_SCOPES
de gmail_auth.py. On reutilise le token Google du super-admin.
"""
from fastapi import APIRouter, Request, Depends, Body
from fastapi.responses import JSONResponse
from app.routes.deps import require_admin
from app.connection_token_manager import get_connection_token
from app.connections import create_connection
from app.logging_config import get_logger

logger = get_logger("raya.admin_drive")
router = APIRouter(tags=["admin_drive"])


# ---- LISTER LES DOSSIERS DRIVE ACCESSIBLES ----------------------------

@router.get("/admin/drive/folders/{tenant_id}")
def admin_list_drive_folders(
    request: Request,
    tenant_id: str,
    parent_id: str = "root",
    admin: dict = Depends(require_admin),
):
    """
    Liste les dossiers Drive du parent donne (racine par defaut).
    parent_id = 'root' pour la racine, sinon un folder_id.
    Retourne : [{id, name, webViewLink, modifiedTime}]
    """
    import requests
    token = get_connection_token(admin["username"], "gmail")
    if not token:
        return JSONResponse({
            "status": "error",
            "message": "Aucun token Google disponible. Connecte d'abord ta boite Gmail.",
        }, status_code=400)

    try:
        q = f"'{parent_id}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false"
        url = "https://www.googleapis.com/drive/v3/files"
        params = {
            "q": q,
            "fields": "files(id,name,webViewLink,modifiedTime)",
            "orderBy": "name",
            "pageSize": 100,
        }
        headers = {"Authorization": f"Bearer {token}"}
        r = requests.get(url, headers=headers, params=params, timeout=15)
        if r.status_code != 200:
            logger.error("[Drive] folders list error: %s %s", r.status_code, r.text[:300])
            return JSONResponse({
                "status": "error",
                "message": f"Erreur Drive API : {r.status_code}",
                "detail": r.text[:400],
            }, status_code=500)
        data = r.json()
        folders = []
        for f in data.get("files", []):
            folders.append({
                "id": f.get("id", ""),
                "name": f.get("name", ""),
                "webViewLink": f.get("webViewLink", ""),
                "modifiedTime": f.get("modifiedTime", ""),
            })
        return {"status": "ok", "folders": folders, "count": len(folders), "parent_id": parent_id}
    except Exception as e:
        logger.exception("[Drive] list exception")
        return JSONResponse({"status": "error", "message": str(e)[:200]}, status_code=500)


# ---- ENREGISTRER LE DOSSIER CHOISI ------------------------------------

@router.post("/admin/drive/select")
def admin_select_drive_folder(
    request: Request,
    payload: dict = Body(...),
    admin: dict = Depends(require_admin),
):
    """
    Enregistre le dossier Drive choisi dans tenant_connections.
    payload : {
      "tenant_id": "couffrant_solar",
      "folder_id": "1aBcDe...",
      "folder_name": "Devis clients",
      "folder_url": "https://drive.google.com/drive/folders/...",
      "label": "Drive - Devis clients" (optionnel)
    }
    Cree une nouvelle tenant_connections (tool_type='drive').
    """
    tenant_id = (payload.get("tenant_id") or "").strip()
    folder_id = (payload.get("folder_id") or "").strip()
    folder_name = (payload.get("folder_name") or "").strip()
    folder_url = (payload.get("folder_url") or "").strip()
    label = (payload.get("label") or f"Drive - {folder_name}").strip()

    if not tenant_id or not folder_id:
        return JSONResponse({
            "status": "error",
            "message": "tenant_id et folder_id obligatoires",
        }, status_code=400)

    result = create_connection(
        tenant_id=tenant_id,
        tool_type="drive",
        label=label,
        auth_type="shared_google",
        config={
            "folder_id": folder_id,
            "folder_name": folder_name,
            "folder_url": folder_url,
        },
        credentials={},
        created_by=admin["username"],
        status="connected",
    )
    if result.get("status") != "ok":
        return JSONResponse(result, status_code=500)
    logger.info("[Drive] dossier %s lie au tenant %s par %s",
                folder_name, tenant_id, admin["username"])
    return {"status": "ok", "connection": result.get("connection")}
