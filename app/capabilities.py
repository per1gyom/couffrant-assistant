"""
Registre des capacites UI et fonctionnelles de Raya.

Injecte dans chaque prompt systeme pour que Raya ne mente jamais
sur ce qu'elle peut ou ne peut pas faire.
"""
import os

CAPABILITIES = {
    "interface_utilisateur": {
        "boutons_interactifs": (
            "Oui — je peux afficher des boutons cliquables via [ACTION:ASK_CHOICE:question|opt1|opt2] "
            "ou les cartes de confirmation d'actions. L'utilisateur n'est pas limite au clavier."
        ),
        "rendu_markdown": (
            "Oui — titres, gras, italique, listes, tableaux, liens cliquables (via marked.js). "
            "Mes reponses s'affichent avec mise en forme complete."
        ),
        "entree_vocale": (
            "Oui — micro integre, transcription vocale francaise (Chrome/Edge). "
            "L'utilisateur peut parler au lieu de taper."
        ),
        "sortie_vocale": (
            "Oui — synthese vocale ElevenLabs sur chaque reponse, lecture automatique ou manuelle."
        ),
        "upload_fichiers": (
            "Oui — images (JPG/PNG/WebP), PDF, texte. Taille max 10 Mo par fichier."
        ),
        "choix_interactifs": (
            "Oui — [ACTION:ASK_CHOICE:ma_question|option1|option2|option3] affiche des boutons "
            "de choix a tout moment dans la conversation."
        ),
        "creation_pdf": (
            "Oui — je peux creer des documents PDF telechargeables. "
            "Syntaxe : [ACTION:CREATE_PDF:titre du document|contenu du document]. "
            "Le contenu peut contenir des retours a la ligne. "
            "L'utilisateur recoit un lien de telechargement dans le chat."
        ),
        "creation_excel": (
            "Oui — je peux creer des fichiers Excel telechargeables. "
            "Syntaxe : [ACTION:CREATE_EXCEL:titre|col1;col2;col3|val1;val2;val3\\nval4;val5;val6]. "
            "Les en-tetes sont separes par ; et les lignes par \\n. "
            "L'utilisateur recoit un lien de telechargement dans le chat."
        ),
        "creation_images": (
            "Oui — je peux generer des images via DALL-E 3. "
            "Syntaxe : [ACTION:CREATE_IMAGE:description detaillee de l'image]. "
            "L'utilisateur recoit un lien vers l'image dans le chat."
        ),
        "lecture_pdf": (
            "Oui — quand l'utilisateur uploade un PDF, j'extrais le texte automatiquement (pdfplumber) "
            "et je peux l'analyser, le resumer, repondre a des questions dessus."
        ),
    },
    "limitations_reelles": {
        "pas_streaming": "Je reponds en un bloc complet, pas mot par mot.",
    },
}


def get_capabilities_prompt() -> str:
    """Retourne le bloc de capacites a injecter dans le prompt systeme."""
    ui_lines = "\n".join(
        f"  \u2022 {k} : {v}" for k, v in CAPABILITIES["interface_utilisateur"].items()
    )
    lim_lines = "\n".join(
        f"  \u2022 {v}" for v in CAPABILITIES["limitations_reelles"].values()
    )
    return (
        "=== MES CAPACITES REELLES ===\n"
        "Interface utilisateur :\n"
        f"{ui_lines}\n"
        "Limitations reelles :\n"
        f"{lim_lines}\n"
        "IMPORTANT : Ne jamais dire 'je ne peux pas creer de PDF' ou 'je ne peux pas creer d'Excel' — c'est FAUX.\n"
        "Utiliser [ACTION:CREATE_PDF:...] et [ACTION:CREATE_EXCEL:...] quand l'utilisateur demande un document.\n"
        "Utiliser [ACTION:CREATE_IMAGE:...] quand l'utilisateur demande une image ou illustration.\n"
        "Consulter ce registre avant de repondre a toute question sur mes capacites."
    )


def get_user_capabilities_prompt(username: str, tools: dict) -> str:
    """
    Construit le bloc capacites en fonction des outils reellement connectes.
    """
    static_block = get_capabilities_prompt()

    drive_level = "lecture + ecriture" if tools.get("drive_write") else "lecture seule"

    if tools.get("odoo_enabled"):
        odoo_access = tools.get("odoo_access", "read_only")
        if odoo_access == "full":
            odoo_status = "actif (complet)"
        else:
            shared = tools.get("odoo_shared_user")
            odoo_status = f"actif (lecture seule{f' via {shared}' if shared else ''})"
    else:
        odoo_status = "non connecte"

    extra_boxes = tools.get("mail_extra_boxes", [])
    boites_supp = ", ".join(extra_boxes) if extra_boxes else "aucune"

    # WhatsApp
    whatsapp_status = "non configure (pas de numero de telephone)"
    try:
        from app.security_users import get_user_phone
        phone = get_user_phone(username)
        if phone:
            whatsapp_status = (
                f"actif ({phone}) — notifications + reponses bidirectionnelles"
            )
    except Exception:
        pass

    # Recherche web
    web_search_enabled = os.getenv("RAYA_WEB_SEARCH_ENABLED", "true").strip().lower()
    web_search_line = ""
    if web_search_enabled not in ("false", "0", "no", "off"):
        web_search_line = "  - Recherche web : active (je peux chercher sur Internet en temps reel)\n"

    # ElevenLabs
    elevenlabs_key = os.getenv("ELEVENLABS_API_KEY", "").strip()
    elevenlabs_status = "active (ElevenLabs)" if elevenlabs_key else "non configuree"

    tools_block = (
        f"Outils connectes pour {username} :\n"
        f"  - Mails Outlook : actif (lecture + envoi)\n"
        f"  - Drive SharePoint : actif ({drive_level})\n"
        f"  - Teams : actif (lecture + envoi)\n"
        f"  - Calendrier Outlook : actif\n"
        f"  - Odoo : {odoo_status}\n"
        f"  - Boites supplementaires : {boites_supp}\n"
        f"  - WhatsApp : {whatsapp_status}\n"
        f"{web_search_line}"
        f"  - Lecture vocale : {elevenlabs_status}\n"
        f"  - Creation PDF : actif — [ACTION:CREATE_PDF:titre|contenu]\n"
        f"  - Creation Excel : actif — [ACTION:CREATE_EXCEL:titre|en-tetes;sep;par;point-virgule|ligne1\\nligne2]\n"
        f"  - Generation images DALL-E : actif — [ACTION:CREATE_IMAGE:description detaillee]\n"
        "\n"
        "IMPORTANT : Ne propose JAMAIS une action sur un outil non connecte.\n"
        "Pour creer un PDF ou Excel, utiliser TOUJOURS les [ACTION:CREATE_PDF:...] ou [ACTION:CREATE_EXCEL:...].\n"
        "Pour generer une image, utiliser [ACTION:CREATE_IMAGE:description].\n"
        "Ne JAMAIS dire 'je ne peux pas creer de fichier' — c'est FAUX."
    )

    return static_block + "\n\n" + tools_block
