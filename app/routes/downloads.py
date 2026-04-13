"""
Endpoint de téléchargement de fichiers générés par Raya.
GET /download/{file_id} → sert le fichier depuis /tmp/
"""
import os
import glob
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import FileResponse
from app.logging_config import get_logger

logger = get_logger("raya.downloads")

router = APIRouter(tags=["downloads"])

# Content-types par extension
_CONTENT_TYPES = {
    ".pdf": "application/pdf",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".csv": "text/csv",
}


@router.get("/download/{file_id}")
def download_file(request: Request, file_id: str):
    """Sert un fichier généré depuis /tmp/{file_id}.*"""
    user = request.session.get("user")
    if not user:
        raise HTTPException(status_code=401, detail="Authentification requise")

    # Sécurité : file_id ne doit contenir que des caractères UUID
    if not all(c in "0123456789abcdef-" for c in file_id):
        raise HTTPException(status_code=400, detail="ID invalide")

    # Chercher le fichier par son UUID
    matches = glob.glob(f"/tmp/{file_id}.*")
    if not matches:
        raise HTTPException(status_code=404, detail="Fichier expiré ou introuvable")

    filepath = matches[0]
    ext = os.path.splitext(filepath)[1].lower()
    content_type = _CONTENT_TYPES.get(ext, "application/octet-stream")

    logger.info(f"[Download] {user} télécharge {os.path.basename(filepath)}")

    return FileResponse(
        path=filepath,
        media_type=content_type,
        filename=os.path.basename(filepath),
    )
