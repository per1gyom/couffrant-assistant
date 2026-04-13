"""
Générateur de fichiers PDF et Excel pour Raya.
Utilisé par les actions CREATE_PDF et CREATE_EXCEL.
"""
import os
import uuid
import re
from datetime import datetime
from app.logging_config import get_logger

logger = get_logger("raya.file_creator")


def _slugify(text: str) -> str:
    """Transforme un titre en nom de fichier propre."""
    text = text.lower().strip()
    text = re.sub(r'[àáâãä]', 'a', text)
    text = re.sub(r'[èéêë]', 'e', text)
    text = re.sub(r'[ìíîï]', 'i', text)
    text = re.sub(r'[òóôõö]', 'o', text)
    text = re.sub(r'[ùúûü]', 'u', text)
    text = re.sub(r'[^a-z0-9]+', '_', text)
    return text.strip('_')[:50]


def create_pdf(title: str, content: str, username: str = "") -> dict:
    """
    Crée un PDF avec titre et contenu texte.
    Retourne {"file_id", "filename", "path"}.
    """
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import mm
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
        from reportlab.lib.colors import HexColor
    except ImportError:
        return {"error": "reportlab non installé"}

    file_id = str(uuid.uuid4())
    filename = f"{_slugify(title)}.pdf"
    path = f"/tmp/{file_id}.pdf"

    doc = SimpleDocTemplate(path, pagesize=A4,
                            leftMargin=25*mm, rightMargin=25*mm,
                            topMargin=20*mm, bottomMargin=20*mm)
    styles = getSampleStyleSheet()

    # Style en-tête
    header_style = ParagraphStyle(
        'RayaHeader', parent=styles['Heading1'],
        fontSize=16, textColor=HexColor('#6366f1'),
        spaceAfter=6,
    )
    date_style = ParagraphStyle(
        'RayaDate', parent=styles['Normal'],
        fontSize=9, textColor=HexColor('#6b7280'),
        spaceAfter=16,
    )
    body_style = ParagraphStyle(
        'RayaBody', parent=styles['Normal'],
        fontSize=11, leading=16, spaceAfter=8,
    )

    elements = []
    elements.append(Paragraph(f"⚡ Raya — {title}", header_style))
    elements.append(Paragraph(datetime.now().strftime("%d/%m/%Y %H:%M"), date_style))
    elements.append(Spacer(1, 8))

    for line in content.split('\n'):
        line = line.strip()
        if not line:
            elements.append(Spacer(1, 6))
        else:
            # Échapper les caractères HTML
            safe = line.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            elements.append(Paragraph(safe, body_style))

    doc.build(elements)
    logger.info(f"[FileCreator] PDF créé: {filename} ({path})")
    return {"file_id": file_id, "filename": filename, "path": path}


def create_excel(title: str, data: list, headers: list, username: str = "") -> dict:
    """
    Crée un fichier Excel avec en-têtes et données.
    data = liste de listes (lignes).
    headers = liste de strings (en-têtes).
    Retourne {"file_id", "filename", "path"}.
    """
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill, Alignment
    except ImportError:
        return {"error": "openpyxl non installé"}

    file_id = str(uuid.uuid4())
    filename = f"{_slugify(title)}.xlsx"
    path = f"/tmp/{file_id}.xlsx"

    wb = Workbook()
    ws = wb.active
    ws.title = title[:31]  # max 31 chars pour le nom d'onglet Excel

    # Style en-têtes
    header_font = Font(bold=True, color="FFFFFF", size=11)
    header_fill = PatternFill(start_color="6366F1", end_color="6366F1", fill_type="solid")

    for col_idx, header in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col_idx, value=header)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center")

    # Données
    for row_idx, row_data in enumerate(data, 2):
        for col_idx, value in enumerate(row_data, 1):
            ws.cell(row=row_idx, column=col_idx, value=value)

    # Auto-largeur colonnes
    for col_idx in range(1, len(headers) + 1):
        max_len = len(str(headers[col_idx - 1]))
        for row_idx in range(2, len(data) + 2):
            cell_val = ws.cell(row=row_idx, column=col_idx).value
            if cell_val and len(str(cell_val)) > max_len:
                max_len = len(str(cell_val))
        ws.column_dimensions[chr(64 + col_idx) if col_idx <= 26 else 'A'].width = min(max_len + 4, 40)

    wb.save(path)
    logger.info(f"[FileCreator] Excel créé: {filename} ({path})")
    return {"file_id": file_id, "filename": filename, "path": path}
