"""
Extraction de texte depuis un PDF en bytes. (TOOL-READ-PDF)

Utilise pdfplumber pour une extraction fiable (tableaux, colonnes, etc.).
Tronque à 15 000 caractères pour rester dans le contexte LLM.
"""
import io


def extract_text_from_pdf(pdf_bytes: bytes, max_pages: int = 20) -> dict:
    """
    Extrait le texte d'un PDF depuis ses bytes.

    Args:
        pdf_bytes : contenu binaire du PDF
        max_pages : nombre max de pages à lire (défaut : 20)

    Returns:
        {"text": str, "pages": int, "truncated": bool}
        ou {"error": str} si le PDF est illisible ou pdfplumber absent.
    """
    try:
        import pdfplumber
    except ImportError:
        return {"error": "pdfplumber non installé. Ajoutez 'pdfplumber' dans requirements.txt."}

    MAX_CHARS = 15_000

    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            total_pages = len(pdf.pages)
            pages_to_read = min(total_pages, max_pages)
            parts = []

            for i, page in enumerate(pdf.pages[:pages_to_read], start=1):
                page_text = page.extract_text() or ""
                parts.append(f"--- Page {i} ---\n{page_text.strip()}")

            full_text = "\n\n".join(parts)
            truncated = False

            if len(full_text) > MAX_CHARS:
                full_text = full_text[:MAX_CHARS]
                remaining = total_pages - pages_to_read
                suffix = f"\n\n[... tronqué, {remaining} pages restantes]" if remaining > 0 else "\n\n[... tronqué]"
                full_text += suffix
                truncated = True

            return {
                "text": full_text,
                "pages": pages_to_read,
                "truncated": truncated,
            }

    except Exception as e:
        return {"error": f"PDF illisible : {str(e)[:120]}"}
