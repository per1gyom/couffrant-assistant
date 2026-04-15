"""
Construction du contenu utilisateur pour Raya.
Extrait de raya_helpers.py -- SPLIT-F9.
"""
from app.routes.raya_helpers import RayaQuery


def _build_user_content(payload: RayaQuery):
    if not payload.file_data or not payload.file_type:
        return payload.query
    file_name_info = f" ({payload.file_name})" if payload.file_name else ""
    parts = []
    if payload.file_type.startswith("image/"):
        parts.append({"type": "image",
                      "source": {"type": "base64", "media_type": payload.file_type,
                                 "data": payload.file_data}})
        parts.append({"type": "text",
                      "text": f"[Image jointe{file_name_info}]\n{payload.query}"
                      if payload.query else f"[Image jointe{file_name_info}] Analyse ce document."})
    elif payload.file_type == "application/pdf":
        enriched = payload.query or ""
        try:
            import base64 as _b64
            from app.connectors.pdf_reader import extract_text_from_pdf
            pdf_bytes = _b64.b64decode(payload.file_data)
            r = extract_text_from_pdf(pdf_bytes)
            if "error" in r:
                enriched += f"\n\n[Erreur PDF: {r['error']}]"
            else:
                enriched += f"\n\n--- PDF '{payload.file_name or 'doc.pdf'}' ({r['pages']}p) ---\n{r['text']}"
        except Exception as e:
            logger.warning("[Raya] PDF error: %s", e)
        parts.append({"type": "document",
                      "source": {"type": "base64", "media_type": "application/pdf",
                                 "data": payload.file_data}})
        parts.append({"type": "text",
                      "text": f"[PDF joint{file_name_info}]\n{enriched}"
                      if enriched else f"[PDF joint{file_name_info}] Analyse ce document."})
    else:
        parts.append({"type": "text",
                      "text": f"[Fichier joint{file_name_info}]\n{payload.query}"})
    return parts


