"""
Donnees de seed du registre d'outils Raya.
Extrait de tools_registry.py -- SPLIT-3.
"""

_TOOLS = [
    # —— MAILS ——
    {"name": "ARCHIVE", "label": "Archiver un mail", "category": "mail",
     "action_code": "ACTION:ARCHIVE:id", "description": "Archive un mail dans Outlook",
     "functional_description": "Ranger un mail traite pour garder une boite propre.",
     "is_sensitive": False, "requires_confirmation": False, "default_enabled": True},
    {"name": "READ", "label": "Marquer lu", "category": "mail",
     "action_code": "ACTION:READ:id", "description": "Marque un mail comme lu",
     "functional_description": "Indiquer qu'un mail a ete lu sans avoir a l'ouvrir manuellement.",
     "is_sensitive": False, "requires_confirmation": False, "default_enabled": True},
    {"name": "READBODY", "label": "Lire le corps d'un mail", "category": "mail",
     "action_code": "ACTION:READBODY:id", "description": "Télécharge et lit le corps complet d'un mail",
     "functional_description": "Acceder au contenu integral d'un mail pour l'analyser en detail.",
     "is_sensitive": False, "requires_confirmation": False, "default_enabled": True},
    {"name": "REPLY", "label": "Répondre à un mail", "category": "mail",
     "action_code": "ACTION:REPLY:id:texte", "description": "Répond à un mail via Outlook",
     "functional_description": "Repondre a un interlocuteur par mail. Raya redige le brouillon.",
     "is_sensitive": True, "requires_confirmation": True, "default_enabled": True},
    {"name": "DELETE", "label": "Supprimer un mail", "category": "mail",
     "action_code": "ACTION:DELETE:id", "description": "Déplace un mail dans la corbeille (récupérable)",
     "functional_description": "Supprimer un mail inutile. Reversible : le mail va en corbeille.",
     "is_sensitive": True, "requires_confirmation": True, "default_enabled": False},

    # —— CALENDRIER ——
    {"name": "CREATEEVENT", "label": "Créer un événement", "category": "calendar",
     "action_code": "ACTION:CREATEEVENT:sujet|debut_iso|fin_iso|participants",
     "description": "Crée un événement dans le calendrier Outlook",
     "functional_description": "Planifier un rendez-vous ou une reunion dans le calendrier.",
     "is_sensitive": True, "requires_confirmation": True, "default_enabled": True},
    {"name": "CREATE_TASK", "label": "Créer une tâche", "category": "calendar",
     "action_code": "ACTION:CREATE_TASK:titre", "description": "Crée une tâche dans Microsoft To Do",
     "functional_description": "Ajouter un element a la liste de taches pour ne rien oublier.",
     "is_sensitive": False, "requires_confirmation": False, "default_enabled": True},

    # —— DRIVE ——
    {"name": "LISTDRIVE", "label": "Lister Drive", "category": "drive",
     "action_code": "ACTION:LISTDRIVE:", "description": "Liste les fichiers et dossiers SharePoint",
     "functional_description": "Explorer l'arborescence SharePoint pour trouver un dossier.",
     "is_sensitive": False, "requires_confirmation": False, "default_enabled": True},
    {"name": "READDRIVE", "label": "Lire un fichier Drive", "category": "drive",
     "action_code": "ACTION:READDRIVE:id", "description": "Lit le contenu d'un fichier SharePoint",
     "functional_description": "Lire le contenu d'un document stocke dans SharePoint.",
     "is_sensitive": False, "requires_confirmation": False, "default_enabled": True},
    {"name": "SEARCHDRIVE", "label": "Chercher dans Drive", "category": "drive",
     "action_code": "ACTION:SEARCHDRIVE:mot", "description": "Recherche dans SharePoint par mot-clé",
     "functional_description": "Retrouver un document quand on connait un mot-cle ou un nom.",
     "is_sensitive": False, "requires_confirmation": False, "default_enabled": True},
    {"name": "MOVEDRIVE", "label": "Déplacer un fichier", "category": "drive",
     "action_code": "ACTION:MOVEDRIVE:item|dest|nom", "description": "Déplace un fichier dans SharePoint",
     "functional_description": "Reorganiser les fichiers en les deplacant vers le bon dossier.",
     "is_sensitive": True, "requires_confirmation": True, "default_enabled": False},
    {"name": "COPYFILE", "label": "Copier un fichier", "category": "drive",
     "action_code": "ACTION:COPYFILE:source|dest|nom", "description": "Copie un fichier dans SharePoint",
     "functional_description": "Dupliquer un document existant pour en creer une nouvelle version.",
     "is_sensitive": True, "requires_confirmation": True, "default_enabled": False},
    {"name": "CREATEFOLDER", "label": "Créer un dossier", "category": "drive",
     "action_code": "ACTION:CREATEFOLDER:parent|nom", "description": "Crée un dossier dans SharePoint",
     "functional_description": "Creer un nouveau repertoire pour organiser les documents.",
     "is_sensitive": False, "requires_confirmation": False, "default_enabled": False},

    # —— TEAMS ——
    {"name": "TEAMS_LIST", "label": "Lister les Teams", "category": "teams",
     "action_code": "ACTION:TEAMS_LIST:", "description": "Liste les équipes Teams accessibles",
     "functional_description": "Voir les equipes et canaux Teams disponibles.",
     "is_sensitive": False, "requires_confirmation": False, "default_enabled": True},
    {"name": "TEAMS_CHATS", "label": "Lister les conversations Teams", "category": "teams",
     "action_code": "ACTION:TEAMS_CHATS:", "description": "Liste les conversations Teams récentes",
     "functional_description": "Consulter les dernieres conversations Teams.",
     "is_sensitive": False, "requires_confirmation": False, "default_enabled": True},
    {"name": "TEAMS_MSG", "label": "Envoyer un message Teams", "category": "teams",
     "action_code": "ACTION:TEAMS_MSG:email|texte", "description": "Envoie un message Teams à un contact",
     "functional_description": "Contacter rapidement un collegue par messagerie instantanee.",
     "is_sensitive": True, "requires_confirmation": True, "default_enabled": True},
    {"name": "TEAMS_REPLYCHAT", "label": "Répondre dans un chat Teams", "category": "teams",
     "action_code": "ACTION:TEAMS_REPLYCHAT:chat_id|texte",
     "description": "Répond dans une conversation Teams existante",
     "functional_description": "Continuer une conversation Teams en cours.",
     "is_sensitive": True, "requires_confirmation": True, "default_enabled": True},
    {"name": "TEAMS_GROUPE", "label": "Créer un groupe Teams", "category": "teams",
     "action_code": "ACTION:TEAMS_GROUPE:email1,email2|sujet|texte",
     "description": "Crée une conversation de groupe Teams",
     "functional_description": "Demarrer une discussion de groupe avec plusieurs personnes.",
     "is_sensitive": True, "requires_confirmation": True, "default_enabled": True},

    # —— MÉMOIRE ——
    {"name": "LEARN", "label": "Apprendre une règle", "category": "memory",
     "action_code": "ACTION:LEARN:catégorie|règle",
     "description": "Sauvegarde une nouvelle règle dans la mémoire de Raya",
     "functional_description": "Memoriser une preference ou une regle metier.",
     "is_sensitive": False, "requires_confirmation": False, "default_enabled": True},
    {"name": "INSIGHT", "label": "Enregistrer une observation", "category": "memory",
     "action_code": "ACTION:INSIGHT:sujet|observation",
     "description": "Enregistre une observation sur l'utilisateur",
     "functional_description": "Sauvegarder une observation pertinente sur les habitudes.",
     "is_sensitive": False, "requires_confirmation": False, "default_enabled": True},
    {"name": "FORGET", "label": "Oublier une règle", "category": "memory",
     "action_code": "ACTION:FORGET:id", "description": "Désactive une règle de la mémoire",
     "functional_description": "Effacer une regle obsolete de la memoire.",
     "is_sensitive": False, "requires_confirmation": False, "default_enabled": True},
    {"name": "SYNTH", "label": "Synthétiser la session", "category": "memory",
     "action_code": "ACTION:SYNTH:",
     "description": "Déclenche la synthèse des conversations récentes par Opus",
     "functional_description": "Lancer la synthese des echanges recents pour consolider la memoire.",
     "is_sensitive": False, "requires_confirmation": False, "default_enabled": True},

    # —— WORKFLOW ——
    {"name": "CONFIRM", "label": "Confirmer une action", "category": "workflow",
     "action_code": "ACTION:CONFIRM:id", "description": "Exécute une action sensible mise en queue",
     "functional_description": "Valider une action en attente de confirmation.",
     "is_sensitive": True, "requires_confirmation": False, "default_enabled": True},
    {"name": "CANCEL", "label": "Annuler une action", "category": "workflow",
     "action_code": "ACTION:CANCEL:id", "description": "Annule une action sensible mise en queue",
     "functional_description": "Annuler une action en attente avant qu'elle soit executee.",
     "is_sensitive": False, "requires_confirmation": False, "default_enabled": True},

    # —— CRÉATION DE FICHIERS (TOOL-CREATE-FILES) ——
    {"name": "CREATE_PDF", "label": "Créer un PDF", "category": "creation",
     "action_code": "ACTION:CREATE_PDF:titre|contenu",
     "description": "Crée un document PDF téléchargeable",
     "functional_description": (
         "Générer un PDF professionnel (récap chantier, rapport, mémo). "
         "L'utilisateur reçoit un lien de téléchargement dans le chat."
     ),
     "is_sensitive": False, "requires_confirmation": False, "default_enabled": True},
    {"name": "CREATE_EXCEL", "label": "Créer un fichier Excel", "category": "creation",
     "action_code": "ACTION:CREATE_EXCEL:titre|headers|lignes",
     "description": "Crée un fichier Excel téléchargeable",
     "functional_description": (
         "Créer un tableau Excel structuré (suivi, planning, inventaire). "
         "L'utilisateur reçoit un lien de téléchargement dans le chat."
     ),
     "is_sensitive": False, "requires_confirmation": False, "default_enabled": True},

    # —— GÉNÉRATION D'IMAGES (TOOL-DALLE) ——
    {"name": "CREATE_IMAGE", "label": "Générer une image", "category": "creation",
     "action_code": "ACTION:CREATE_IMAGE:description",
     "description": "Génère une image avec DALL-E 3",
     "functional_description": "Créer une image sur mesure. L'image s'affiche dans le chat.",
     "is_sensitive": False, "requires_confirmation": False, "default_enabled": True},
]

