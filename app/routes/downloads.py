"""
Endpoint de téléchargement de fichiers générés par Raya. (TOOL-CREATE-FILES)

GET /download/{file_id}
  - Vérifie que l'utilisateur est connecté (session["user"])
  - Cherche /tmp/{file_id}.* (glob)
  - Retourne le fichier avec le bon Content-Type et Content-Disposition
  - 404 si fichier introuvable ou expiré
"""
import glob
import os

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, JSONResponse

router = APIRouter(tags=["downloads"])

_CONTENT_TYPES = {
    ".pdf":  "application/pdf",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".xls":  "application/vnd.ms-excel",
    ".csv":  "text/csv",
    ".txt":  "text/plain",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


@router.get("/download/{file_id}")
def download_file(file_id: str, request: Request):
    """
    Sert un fichier généré par Raya (PDF, Excel, …).

    Sécurité :
      - L'utilisateur doit être connecté (session["user"]).
      - Le file_id ne peut contenir que des caractères UUID valides
        (protection contre les path traversal).
      - Les fichiers sont dans /tmp/ — éphémères, supprimés au redémarrage.
    """
    # 1. Authentification obligatoire
    if not request.session.get("user"):
        return JSONResponse(
            {"error": "Non authentifié. Connectez-vous pour télécharger ce fichier."},
            status_code=401,
        )

    # 2. Validation du file_id (UUID uniquement — anti path traversal)
    import re
    if not re.match(r'^[0-9a-f\-]{32,36}$', file_id):
        return JSONResponse({"error": "Identifiant de fichier invalide."}, status_code=400)

    # 3. Recherche du fichier dans /tmp/
    pattern = f"/tmp/{file_id}.*"
    matches = glob.glob(pattern)

    if not matches:
        return JSONResponse(
            {"error": "Fichier expiré ou introuvable. Demandez à Raya de le régénérer."},
            status_code=404,
        )

    filepath = matches[0]
    ext = os.path.splitext(filepath)[1].lower()
    content_type = _CONTENT_TYPES.get(ext, "application/octet-stream")
    filename = os.path.basename(filepath)

    return FileResponse(
        path=filepath,
        media_type=content_type,
        filename=filename,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )
