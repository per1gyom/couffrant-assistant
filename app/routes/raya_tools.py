"""
Registre des tools exposes a Claude en mode agent (v2).

Cette liste est la source de verite unique des outils disponibles pour Raya.
Chaque tool est defini au format attendu par l API Anthropic (tool use) :
  - name       : nom du tool appele par Claude
  - description: ce que Claude lit pour savoir quand l utiliser
  - input_schema: JSONSchema des parametres

L execution de chaque tool est mappee dans raya_tool_executors.py.

IMPORTANT : cette liste remplace les 51 tags [ACTION:...] de la v1.
Voir docs/audit_v1_vers_v2.md pour la correspondance.

Principes de redaction des descriptions :
  - Courtes et directes (Claude comprend vite)
  - Pas de "quand utiliser" verbeux (Claude decide)
  - Pas de regles negatives ("ne pas faire X") — confiance Opus
  - Juste : ce que le tool fait + ses parametres
"""
from typing import Any


# ==========================================================================
# OUTILS DE RECHERCHE (lecture seule, sans carte de confirmation)
# ==========================================================================

TOOL_SEARCH_GRAPH = {
    "name": "search_graph",
    "description": (
        "Recherche dans le graphe semantique unifie de l entreprise. "
        "Remonte toutes les entites liees a une requete (clients, devis, "
        "factures, mails, fichiers, conversations passees) avec leurs relations. "
        "C est l outil a utiliser en premier pour toute question sur une entite "
        "(personne, societe, chantier, produit)."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Nom, reference ou concept a rechercher dans le graphe.",
            },
            "max_results": {
                "type": "integer",
                "description": "Nombre max de noeuds a remonter. Par defaut 20.",
                "default": 20,
            },
        },
        "required": ["query"],
    },
}

TOOL_SEARCH_ODOO = {
    "name": "search_odoo",
    "description": (
        "Recherche semantique dans Odoo sur tous les modeles accessibles "
        "(contacts, devis, factures, leads, events, taches). "
        "Remonte le contenu textuel des records correspondant a la requete."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Termes a rechercher.",
            },
            "max_results": {
                "type": "integer",
                "description": "Nombre max de resultats. Par defaut 10.",
                "default": 10,
            },
        },
        "required": ["query"],
    },
}


TOOL_GET_CLIENT_360 = {
    "name": "get_client_360",
    "description": (
        "Vue consolidee 360 degres d un client : partner Odoo, tous ses devis "
        "et commandes, toutes ses factures, ses contacts rattaches, ses events "
        "calendrier. Retourne des donnees structurees (pas du texte vectorise), "
        "donc parfait quand la precision compte (numeros exacts, montants, dates)."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "client_name_or_id": {
                "type": "string",
                "description": "Nom du client ou ID Odoo. Recherche par nom fait du fuzzy matching.",
            },
        },
        "required": ["client_name_or_id"],
    },
}

TOOL_SEARCH_DRIVE = {
    "name": "search_drive",
    "description": (
        "Recherche semantique dans les fichiers SharePoint (photos, PDF, docs "
        "techniques, plans). Remonte les fichiers dont le contenu ou le nom "
        "correspond a la requete."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Termes a rechercher dans les fichiers.",
            },
            "max_results": {
                "type": "integer",
                "default": 10,
            },
        },
        "required": ["query"],
    },
}


TOOL_SEARCH_MAIL = {
    "name": "search_mail",
    "description": (
        "Recherche dans les mails analyses (Outlook et Gmail). Remonte les mails "
        "dont le contenu, l objet ou l expediteur correspond a la requete."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "max_results": {"type": "integer", "default": 10},
        },
        "required": ["query"],
    },
}

TOOL_SEARCH_CONVERSATIONS = {
    "name": "search_conversations",
    "description": (
        "Recherche dans l historique complet des conversations passees entre "
        "Raya et l utilisateur. Utile pour retrouver un fait mentionne dans "
        "une discussion precedente, une preference, une decision prise."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "max_results": {"type": "integer", "default": 5},
        },
        "required": ["query"],
    },
}

TOOL_READ_MAIL = {
    "name": "read_mail",
    "description": (
        "Lit le contenu complet d un mail specifique par son ID. A utiliser "
        "apres un search_mail pour obtenir le texte integral d un mail."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "mail_id": {"type": "string"},
        },
        "required": ["mail_id"],
    },
}


TOOL_READ_DRIVE_FILE = {
    "name": "read_drive_file",
    "description": (
        "Lit le contenu d un fichier SharePoint par son ID. Supporte texte, "
        "PDF, Office (avec extraction auto)."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "file_id": {"type": "string"},
        },
        "required": ["file_id"],
    },
}

TOOL_WEB_SEARCH = {
    "name": "web_search",
    "description": (
        "Recherche sur le web via l API native Anthropic. A utiliser "
        "spontanement quand tu rencontres un terme, une entreprise, une "
        "technologie ou une personne que tu ne maitrises pas, ou pour verifier "
        "une information externe."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
        },
        "required": ["query"],
    },
}

TOOL_GET_WEATHER = {
    "name": "get_weather",
    "description": (
        "Meteo d une localisation (utile pour planifier des chantiers exterieurs)."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "location": {
                "type": "string",
                "description": "Ville ou code postal. Par defaut Romorantin-Lanthenay.",
            },
        },
    },
}


# ==========================================================================
# OUTILS D ACTION MAIL (avec carte de confirmation)
# ==========================================================================

TOOL_SEND_MAIL = {
    "name": "send_mail",
    "description": (
        "Prepare l envoi d un mail (Outlook par defaut, Gmail si specifie). "
        "Le mail n est pas envoye directement : une carte de confirmation "
        "s affiche pour validation manuelle par l utilisateur. "
        "IMPORTANT : ne termine pas le corps du mail par une signature "
        "(pas de 'Cordialement, Guillaume' ni bloc de contact). La signature "
        "de l utilisateur est ajoutee automatiquement par le systeme. "
        "Termine juste ton texte et c est bon."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "to": {"type": "string", "description": "Email du destinataire."},
            "subject": {"type": "string"},
            "body": {
                "type": "string",
                "description": (
                    "Corps du mail SANS signature finale (ajoutee auto "
                    "par le systeme)."
                ),
            },
            "provider": {
                "type": "string",
                "enum": ["outlook", "gmail"],
                "default": "outlook",
            },
            "cc": {"type": "string", "description": "Optionnel."},
        },
        "required": ["to", "subject", "body"],
    },
}

TOOL_REPLY_TO_MAIL = {
    "name": "reply_to_mail",
    "description": (
        "Prepare une reponse a un mail existant. Carte de confirmation avant envoi. "
        "IMPORTANT : ne termine pas le corps par une signature (ajoutee auto)."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "mail_id": {"type": "string"},
            "body": {
                "type": "string",
                "description": "Corps SANS signature finale (ajoutee auto).",
            },
        },
        "required": ["mail_id", "body"],
    },
}


TOOL_ARCHIVE_MAIL = {
    "name": "archive_mail",
    "description": "Archive un mail. Carte de confirmation avant execution.",
    "input_schema": {
        "type": "object",
        "properties": {
            "mail_id": {"type": "string"},
        },
        "required": ["mail_id"],
    },
}

TOOL_DELETE_MAIL = {
    "name": "delete_mail",
    "description": "Met un mail a la corbeille. Carte de confirmation avant execution.",
    "input_schema": {
        "type": "object",
        "properties": {
            "mail_id": {"type": "string"},
        },
        "required": ["mail_id"],
    },
}

# ==========================================================================
# OUTILS CALENDAR / TEAMS (avec carte de confirmation)
# ==========================================================================

TOOL_CREATE_CALENDAR_EVENT = {
    "name": "create_calendar_event",
    "description": (
        "Prepare la creation d un RDV dans le calendrier Outlook. "
        "Carte de confirmation avant creation."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "start_time": {"type": "string", "description": "ISO format."},
            "end_time": {"type": "string", "description": "ISO format."},
            "attendees": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Liste d emails optionnels.",
            },
            "location": {"type": "string"},
            "description": {"type": "string"},
        },
        "required": ["title", "start_time", "end_time"],
    },
}


TOOL_SEND_TEAMS_MESSAGE = {
    "name": "send_teams_message",
    "description": (
        "Prepare l envoi d un message Teams (chat prive ou canal). "
        "Carte de confirmation avant envoi."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "recipient": {
                "type": "string",
                "description": "Nom ou email du destinataire, ou ID du canal.",
            },
            "message": {"type": "string"},
            "is_channel": {
                "type": "boolean",
                "default": False,
                "description": "True si le destinataire est un canal.",
            },
        },
        "required": ["recipient", "message"],
    },
}

# ==========================================================================
# OUTILS DE CREATION DE CONTENU (sans carte de confirmation)
# ==========================================================================

TOOL_CREATE_FILE = {
    "name": "create_file",
    "description": (
        "Cree un fichier telechargeable (markdown, texte, CSV). "
        "Retourne un lien de telechargement."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "filename": {"type": "string"},
            "content": {"type": "string"},
            "format": {
                "type": "string",
                "enum": ["md", "txt", "csv"],
                "default": "md",
            },
        },
        "required": ["filename", "content"],
    },
}

TOOL_CREATE_PDF = {
    "name": "create_pdf",
    "description": "Cree un PDF structure a partir de markdown.",
    "input_schema": {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "markdown_content": {"type": "string"},
        },
        "required": ["title", "markdown_content"],
    },
}


TOOL_CREATE_EXCEL = {
    "name": "create_excel",
    "description": "Cree un fichier Excel avec donnees tabulaires.",
    "input_schema": {
        "type": "object",
        "properties": {
            "filename": {"type": "string"},
            "sheets": {
                "type": "object",
                "description": (
                    "Dict {nom_feuille: [[ligne1], [ligne2]]}. "
                    "Premiere ligne = en-tetes."
                ),
            },
        },
        "required": ["filename", "sheets"],
    },
}

TOOL_CREATE_IMAGE = {
    "name": "create_image",
    "description": (
        "Genere une image via DALL-E a partir d une description. "
        "Retourne l URL de l image."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "prompt": {"type": "string"},
            "size": {
                "type": "string",
                "enum": ["1024x1024", "1792x1024", "1024x1792"],
                "default": "1024x1024",
            },
        },
        "required": ["prompt"],
    },
}

# ==========================================================================
# OUTILS DRIVE (mouvement de fichiers, avec carte de confirmation)
# ==========================================================================

TOOL_MOVE_DRIVE_FILE = {
    "name": "move_drive_file",
    "description": "Deplace un fichier SharePoint. Carte de confirmation.",
    "input_schema": {
        "type": "object",
        "properties": {
            "file_id": {"type": "string"},
            "destination_folder_id": {"type": "string"},
        },
        "required": ["file_id", "destination_folder_id"],
    },
}


TOOL_CREATE_DRIVE_FOLDER = {
    "name": "create_drive_folder",
    "description": "Cree un dossier SharePoint.",
    "input_schema": {
        "type": "object",
        "properties": {
            "folder_name": {"type": "string"},
            "parent_folder_id": {"type": "string"},
        },
        "required": ["folder_name"],
    },
}

# ==========================================================================
# OUTILS MEMOIRE (preferences durables)
# ==========================================================================

TOOL_REMEMBER_PREFERENCE = {
    "name": "remember_preference",
    "description": (
        "Enregistre une preference durable ou une regle metier de l utilisateur "
        "(ex: 'boite pro = Outlook', 'reponses courtes', 'comptable = Sophie'). "
        "Ces preferences sont rappelees a chaque conversation. "
        "A utiliser uniquement pour des regles generales, PAS pour des faits "
        "ponctuels (ceux-ci sont automatiquement memorises via le graphe)."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "category": {
                "type": "string",
                "description": "Categorie (ex: 'communication', 'equipe', 'workflow').",
            },
            "preference": {
                "type": "string",
                "description": "La regle en une phrase claire.",
            },
        },
        "required": ["category", "preference"],
    },
}

TOOL_FORGET_PREFERENCE = {
    "name": "forget_preference",
    "description": "Supprime une preference apprise precedemment.",
    "input_schema": {
        "type": "object",
        "properties": {
            "preference_id": {"type": "string"},
        },
        "required": ["preference_id"],
    },
}


# ==========================================================================
# REGISTRE CENTRAL DES TOOLS v2
# ==========================================================================
# Cette liste est ce qu on passe a l API Anthropic via le parametre `tools=`.
# L ordre n a pas d importance pour Claude.

RAYA_TOOLS: list[dict[str, Any]] = [
    # Recherche / lecture
    TOOL_SEARCH_GRAPH,
    TOOL_SEARCH_ODOO,
    TOOL_GET_CLIENT_360,
    TOOL_SEARCH_DRIVE,
    TOOL_SEARCH_MAIL,
    TOOL_SEARCH_CONVERSATIONS,
    TOOL_READ_MAIL,
    TOOL_READ_DRIVE_FILE,
    TOOL_WEB_SEARCH,
    # TOOL_GET_WEATHER desactive en v2 initiale (pas de connecteur meteo)
    # Action mail
    TOOL_SEND_MAIL,
    TOOL_REPLY_TO_MAIL,
    TOOL_ARCHIVE_MAIL,
    TOOL_DELETE_MAIL,
    # Action calendar / Teams
    TOOL_CREATE_CALENDAR_EVENT,
    TOOL_SEND_TEAMS_MESSAGE,
    # Creation contenu
    TOOL_CREATE_FILE,
    TOOL_CREATE_PDF,
    TOOL_CREATE_EXCEL,
    TOOL_CREATE_IMAGE,
    # Drive
    TOOL_MOVE_DRIVE_FILE,
    TOOL_CREATE_DRIVE_FOLDER,
    # Memoire preferences durables
    TOOL_REMEMBER_PREFERENCE,
    TOOL_FORGET_PREFERENCE,
]


def get_tools_for_user(username: str, tenant_id: str) -> list[dict]:
    """
    Retourne la liste des tools exposes pour un utilisateur donne.

    Cette fonction est le point d entree appele par raya_helpers.py avant
    chaque appel agent. Elle peut filtrer les tools selon les permissions
    de l utilisateur ou les connecteurs actifs.

    Pour la v2 initiale, elle retourne simplement RAYA_TOOLS. Le filtrage
    par permissions viendra dans une sous-etape ulterieure.
    """
    # TODO v2.1 : filtrer selon app.permissions et connexions actives
    return RAYA_TOOLS


# Set des tools qui necessitent une carte de confirmation cote front.
# Utilise par raya_tool_executors.py pour savoir s il faut creer un
# pending_action plutot que d executer directement.
TOOLS_REQUIRING_CONFIRMATION = {
    "send_mail",
    "reply_to_mail",
    "archive_mail",
    "delete_mail",
    "create_calendar_event",
    "send_teams_message",
    "move_drive_file",
}
