"""
Actions de creation de fichiers declenchees par Raya.
Extrait de router.py -- SPLIT-4.
"""
import os

def execute_create_action(action_str: str, username: str, tenant_id: str) -> str:
    """
    Traite les actions de création de fichiers générés par Raya.

    Formats supportés :
      ACTION:CREATE_PDF:titre|contenu
        → Génère un PDF et retourne un lien Markdown de téléchargement.
        → contenu peut contenir \\n et des lignes "col1|col2" pour des tableaux.

      ACTION:CREATE_EXCEL:titre|headers|lignes
        → Génère un Excel et retourne un lien Markdown de téléchargement.
        → headers : colonnes séparées par ;
        → lignes  : lignes séparées par \\n, colonnes par ;

    Retourne un lien Markdown cliquable ou un message d'erreur.
    """
    base_url = os.getenv("APP_BASE_URL", "https://app.raya-ia.fr").rstrip("/")

    # Parsing du format ACTION:TYPE:params
    parts = action_str.split(":", 2)
    if len(parts) < 3:
        return "❌ Action de création malformée."

    action_type = parts[1].upper()   # CREATE_PDF ou CREATE_EXCEL
    params_raw  = parts[2]           # tout ce qui suit le 2e ":"

    # ── CREATE_PDF ──
    if action_type == "CREATE_PDF":
        sep = params_raw.find("|")
        if sep == -1:
            title   = params_raw.strip()
            content = ""
        else:
            title   = params_raw[:sep].strip()
            content = params_raw[sep + 1:].strip()

        if not title:
            return "❌ Titre manquant pour la création du PDF."

        try:
            from app.connectors.file_creator import create_pdf
            result = create_pdf(title=title, content=content, username=username)
            file_id  = result["file_id"]
            filename = result["filename"]
            url = f"{base_url}/download/{file_id}"
            return f"[📄 Télécharger {filename}]({url})"
        except Exception as e:
            return f"❌ Erreur création PDF : {str(e)[:120]}"

    # ── CREATE_EXCEL ──
    if action_type == "CREATE_EXCEL":
        sub_parts = params_raw.split("|", 2)
        title        = sub_parts[0].strip() if len(sub_parts) > 0 else ""
        headers_raw  = sub_parts[1].strip() if len(sub_parts) > 1 else ""
        rows_raw     = sub_parts[2].strip() if len(sub_parts) > 2 else ""

        if not title:
            return "❌ Titre manquant pour la création de l'Excel."

        headers = [h.strip() for h in headers_raw.split(";") if h.strip()]
        data: list = []
        if rows_raw:
            for line in rows_raw.split("\n"):
                line = line.strip()
                if line:
                    data.append([c.strip() for c in line.split(";")])

        try:
            from app.connectors.file_creator import create_excel
            result = create_excel(
                title=title,
                data=data,
                headers=headers,
                username=username,
            )
            file_id  = result["file_id"]
            filename = result["filename"]
            url = f"{base_url}/download/{file_id}"
            return f"[📊 Télécharger {filename}]({url})"
        except Exception as e:
            return f"❌ Erreur création Excel : {str(e)[:120]}"

    return f"❌ Type de création inconnu : {action_type}"

