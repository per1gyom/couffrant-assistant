"""
Registre statique des capacites UI et fonctionnelles de Raya.

Injecte dans chaque prompt systeme pour que Raya ne mente jamais
sur ce qu'elle peut ou ne peut pas faire.

Exemple de mauvaise reponse corrigee par ce module :
  AVANT : "je suis limitee au texte brut" (FAUX)
  APRES : Raya consulte ce registre et repond correctement
"""

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
            "de choix a tout moment dans la conversation, pas seulement pendant l'onboarding."
        ),
    },
    "limitations_reelles": {
        "pas_generation_images": "Je ne genere pas d'images.",
        "pas_acces_web_libre": (
            "Je n'ai pas acces a Internet en dehors de mes outils connectes "
            "(Microsoft 365, Odoo, SharePoint)."
        ),
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
        "IMPORTANT : Ne jamais dire 'je suis limitee au texte brut' — c'est faux.\n"
        "Consulter ce registre avant de repondre a toute question sur mes capacites."
    )


def get_user_capabilities_prompt(username: str, tools: dict) -> str:
    """
    Construit le bloc capacites en fonction des outils reellement connectes de l'utilisateur.

    Args:
        username: nom de l'utilisateur
        tools: dict retourne par load_user_tools(username) dans aria_context.py
               Cles : drive_write, drive_can_delete, mail_can_delete, mail_extra_boxes,
                      odoo_enabled, odoo_access, odoo_shared_user
    """
    # Bloc statique (identique a get_capabilities_prompt)
    static_block = get_capabilities_prompt()

    # Bloc dynamique : outils reellement connectes
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

    tools_block = (
        f"Outils connectes pour {username} :\n"
        f"  - Mails Outlook : actif (lecture + envoi)\n"
        f"  - Drive SharePoint : actif ({drive_level})\n"
        f"  - Teams : actif (lecture + envoi)\n"
        f"  - Calendrier Outlook : actif\n"
        f"  - Odoo : {odoo_status}\n"
        f"  - Boites supplementaires : {boites_supp}\n"
        "\n"
        "IMPORTANT : Ne propose JAMAIS une action sur un outil non connecte.\n"
        "Si l'utilisateur demande quelque chose d'impossible, explique-lui pourquoi "
        "et suggere une alternative."
    )

    return static_block + "\n\n" + tools_block
