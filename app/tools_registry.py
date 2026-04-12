"""
Registre d'outils Raya — Phase 3c (décision Opus étape 3c).

Centralise la déclaration de tous les outils disponibles :
  - nom, label, description, catégorie
  - code ACTION: correspondant
  - sensibilité (nécessite confirmation)
  - activé par défaut ou non
  - functional_description : utilité fonctionnelle pour le raisonnement de Raya

Objectif Phase 4+ : migration des [ACTION:...] vers tool use natif Anthropic.
Pour l'instant : source de vérité pour le dashboard admin et les permissions.

Tous les nouveaux outils/skills doivent être déclarés ici, pas hardcodés dans le prompt.
"""
from app.database import get_pg_conn

# ─── MIGRATION AUTO ───

def _ensure_table():
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS tools_registry (
                id                   SERIAL PRIMARY KEY,
                name                 TEXT NOT NULL UNIQUE,
                label                TEXT NOT NULL,
                description          TEXT,
                category             TEXT DEFAULT 'general',
                action_code          TEXT NOT NULL,
                schema_json          JSONB DEFAULT '{}',
                is_sensitive         BOOLEAN DEFAULT false,
                requires_confirmation BOOLEAN DEFAULT false,
                default_enabled      BOOLEAN DEFAULT true,
                created_at           TIMESTAMP DEFAULT NOW()
            )
        """)
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[ToolsRegistry] Migration table: {e}")

_ensure_table()


# ─── DÉFINITION DES OUTILS ───
# Source de vérité de tous les [ACTION:...] existants.

_TOOLS = [
    # —— MAILS ——
    {"name": "ARCHIVE",
     "label": "Archiver un mail",
     "category": "mail",
     "action_code": "ACTION:ARCHIVE:id",
     "description": "Archive un mail dans Outlook",
     "functional_description": "Ranger un mail traite pour garder une boite propre. Utile apres avoir lu et agi sur un message.",
     "is_sensitive": False, "requires_confirmation": False, "default_enabled": True},

    {"name": "READ",
     "label": "Marquer lu",
     "category": "mail",
     "action_code": "ACTION:READ:id",
     "description": "Marque un mail comme lu",
     "functional_description": "Indiquer qu'un mail a ete lu sans avoir a l'ouvrir manuellement. Utile pour nettoyer les notifications.",
     "is_sensitive": False, "requires_confirmation": False, "default_enabled": True},

    {"name": "READBODY",
     "label": "Lire le corps d'un mail",
     "category": "mail",
     "action_code": "ACTION:READBODY:id",
     "description": "Télécharge et lit le corps complet d'un mail",
     "functional_description": "Acceder au contenu integral d'un mail pour l'analyser en detail, quand l'apercu ne suffit pas.",
     "is_sensitive": False, "requires_confirmation": False, "default_enabled": True},

    {"name": "REPLY",
     "label": "Répondre à un mail",
     "category": "mail",
     "action_code": "ACTION:REPLY:id:texte",
     "description": "Répond à un mail via Outlook",
     "functional_description": "Repondre a un interlocuteur par mail. Raya redige le brouillon, l'utilisateur confirme avant envoi.",
     "is_sensitive": True, "requires_confirmation": True, "default_enabled": True},

    {"name": "DELETE",
     "label": "Supprimer un mail",
     "category": "mail",
     "action_code": "ACTION:DELETE:id",
     "description": "Déplace un mail dans la corbeille (récupérable)",
     "functional_description": "Supprimer un mail inutile ou indesiable. Reversible : le mail va en corbeille, pas definitivement efface.",
     "is_sensitive": True, "requires_confirmation": True, "default_enabled": False},

    # —— CALENDRIER ——
    {"name": "CREATEEVENT",
     "label": "Créer un événement",
     "category": "calendar",
     "action_code": "ACTION:CREATEEVENT:sujet|debut_iso|fin_iso|participants",
     "description": "Crée un événement dans le calendrier Outlook",
     "functional_description": "Planifier un rendez-vous, une reunion ou un rappel dans le calendrier. Invite automatiquement les participants si precise.",
     "is_sensitive": True, "requires_confirmation": True, "default_enabled": True},

    {"name": "CREATE_TASK",
     "label": "Créer une tâche",
     "category": "calendar",
     "action_code": "ACTION:CREATE_TASK:titre",
     "description": "Crée une tâche dans Microsoft To Do",
     "functional_description": "Ajouter un element a la liste de taches pour ne rien oublier. Ideal pour les actions a faire plus tard.",
     "is_sensitive": False, "requires_confirmation": False, "default_enabled": True},

    # —— DRIVE ——
    {"name": "LISTDRIVE",
     "label": "Lister Drive",
     "category": "drive",
     "action_code": "ACTION:LISTDRIVE:",
     "description": "Liste les fichiers et dossiers SharePoint",
     "functional_description": "Explorer l'arborescence SharePoint pour trouver un dossier ou voir ce qu'il contient.",
     "is_sensitive": False, "requires_confirmation": False, "default_enabled": True},

    {"name": "READDRIVE",
     "label": "Lire un fichier Drive",
     "category": "drive",
     "action_code": "ACTION:READDRIVE:id",
     "description": "Lit le contenu d'un fichier SharePoint",
     "functional_description": "Lire le contenu d'un document (PDF, texte, tableau) stocke dans SharePoint pour en extraire des informations.",
     "is_sensitive": False, "requires_confirmation": False, "default_enabled": True},

    {"name": "SEARCHDRIVE",
     "label": "Chercher dans Drive",
     "category": "drive",
     "action_code": "ACTION:SEARCHDRIVE:mot",
     "description": "Recherche dans SharePoint par mot-clé",
     "functional_description": "Retrouver un document (devis, facture, plan, dossier chantier) quand on connait un mot-cle ou un nom.",
     "is_sensitive": False, "requires_confirmation": False, "default_enabled": True},

    {"name": "MOVEDRIVE",
     "label": "Déplacer un fichier",
     "category": "drive",
     "action_code": "ACTION:MOVEDRIVE:item|dest|nom",
     "description": "Déplace un fichier dans SharePoint",
     "functional_description": "Reorganiser les fichiers en les deplacant vers le bon dossier. Action irreversible sans corbeille.",
     "is_sensitive": True, "requires_confirmation": True, "default_enabled": False},

    {"name": "COPYFILE",
     "label": "Copier un fichier",
     "category": "drive",
     "action_code": "ACTION:COPYFILE:source|dest|nom",
     "description": "Copie un fichier dans SharePoint",
     "functional_description": "Dupliquer un document existant (modele, template) pour en creer une nouvelle version sans toucher a l'original.",
     "is_sensitive": True, "requires_confirmation": True, "default_enabled": False},

    {"name": "CREATEFOLDER",
     "label": "Créer un dossier",
     "category": "drive",
     "action_code": "ACTION:CREATEFOLDER:parent|nom",
     "description": "Crée un dossier dans SharePoint",
     "functional_description": "Creer un nouveau repertoire pour organiser les documents d'un projet ou d'un client.",
     "is_sensitive": False, "requires_confirmation": False, "default_enabled": False},

    # —— TEAMS ——
    {"name": "TEAMS_LIST",
     "label": "Lister les Teams",
     "category": "teams",
     "action_code": "ACTION:TEAMS_LIST:",
     "description": "Liste les équipes Teams accessibles",
     "functional_description": "Voir les equipes et canaux Teams disponibles pour savoir ou envoyer un message ou chercher une conversation.",
     "is_sensitive": False, "requires_confirmation": False, "default_enabled": True},

    {"name": "TEAMS_CHATS",
     "label": "Lister les conversations Teams",
     "category": "teams",
     "action_code": "ACTION:TEAMS_CHATS:",
     "description": "Liste les conversations Teams récentes",
     "functional_description": "Consulter les dernieres conversations Teams pour retrouver un echange ou verifier les messages recents.",
     "is_sensitive": False, "requires_confirmation": False, "default_enabled": True},

    {"name": "TEAMS_MSG",
     "label": "Envoyer un message Teams",
     "category": "teams",
     "action_code": "ACTION:TEAMS_MSG:email|texte",
     "description": "Envoie un message Teams à un contact",
     "functional_description": "Contacter rapidement un collegue ou partenaire par messagerie instantanee. Plus rapide qu'un mail pour une question courte.",
     "is_sensitive": True, "requires_confirmation": True, "default_enabled": True},

    {"name": "TEAMS_REPLYCHAT",
     "label": "Répondre dans un chat Teams",
     "category": "teams",
     "action_code": "ACTION:TEAMS_REPLYCHAT:chat_id|texte",
     "description": "Répond dans une conversation Teams existante",
     "functional_description": "Continuer une conversation Teams en cours sans en creer une nouvelle. Garde le contexte de l'echange.",
     "is_sensitive": True, "requires_confirmation": True, "default_enabled": True},

    {"name": "TEAMS_GROUPE",
     "label": "Créer un groupe Teams",
     "category": "teams",
     "action_code": "ACTION:TEAMS_GROUPE:email1,email2|sujet|texte",
     "description": "Crée une conversation de groupe Teams",
     "functional_description": "Demarrer une discussion de groupe avec plusieurs personnes simultanement. Pratique pour coordonner une equipe projet.",
     "is_sensitive": True, "requires_confirmation": True, "default_enabled": True},

    # —— MÉMOIRE ——
    {"name": "LEARN",
     "label": "Apprendre une règle",
     "category": "memory",
     "action_code": "ACTION:LEARN:catégorie|règle",
     "description": "Sauvegarde une nouvelle règle dans la mémoire de Raya",
     "functional_description": "Memoriser une preference, une habitude ou une regle metier pour que Raya s'ameliore avec le temps.",
     "is_sensitive": False, "requires_confirmation": False, "default_enabled": True},

    {"name": "INSIGHT",
     "label": "Enregistrer une observation",
     "category": "memory",
     "action_code": "ACTION:INSIGHT:sujet|observation",
     "description": "Enregistre une observation sur l'utilisateur",
     "functional_description": "Sauvegarder une observation pertinente sur les habitudes ou preferences de l'utilisateur pour personnaliser les futures interactions.",
     "is_sensitive": False, "requires_confirmation": False, "default_enabled": True},

    {"name": "FORGET",
     "label": "Oublier une règle",
     "category": "memory",
     "action_code": "ACTION:FORGET:id",
     "description": "Désactive une règle de la mémoire",
     "functional_description": "Effacer une regle ou information obsolete de la memoire. A utiliser uniquement sur demande explicite de l'utilisateur.",
     "is_sensitive": False, "requires_confirmation": False, "default_enabled": True},

    {"name": "SYNTH",
     "label": "Synthétiser la session",
     "category": "memory",
     "action_code": "ACTION:SYNTH:",
     "description": "Déclenche la synthèse des conversations récentes par Opus",
     "functional_description": "Lancer manuellement la synthese des echanges recents pour consolider la memoire et extraire de nouvelles regles.",
     "is_sensitive": False, "requires_confirmation": False, "default_enabled": True},

    {"name": "CONFIRM",
     "label": "Confirmer une action",
     "category": "workflow",
     "action_code": "ACTION:CONFIRM:id",
     "description": "Exécute une action sensible mise en queue",
     "functional_description": "Valider une action en attente de confirmation (envoi mail, message Teams, etc.) apres que l'utilisateur a donne son accord.",
     "is_sensitive": True, "requires_confirmation": False, "default_enabled": True},

    {"name": "CANCEL",
     "label": "Annuler une action",
     "category": "workflow",
     "action_code": "ACTION:CANCEL:id",
     "description": "Annule une action sensible mise en queue",
     "functional_description": "Annuler une action en attente avant qu'elle soit executee. L'utilisateur a change d'avis ou a detecte une erreur.",
     "is_sensitive": False, "requires_confirmation": False, "default_enabled": True},
]


def seed_tools_registry() -> int:
    """
    Remplit le registre avec les outils définis dans _TOOLS.
    Idempotent : utilise ON CONFLICT DO NOTHING.
    Retourne le nombre d'outils insérés.
    """
    inserted = 0
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        import json
        # Migration : ajouter la colonne functional_description si absente
        c.execute("ALTER TABLE tools_registry ADD COLUMN IF NOT EXISTS functional_description TEXT DEFAULT ''")
        conn.commit()
        for tool in _TOOLS:
            c.execute("""
                INSERT INTO tools_registry
                  (name, label, description, category, action_code, schema_json,
                   is_sensitive, requires_confirmation, default_enabled, functional_description)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (name) DO NOTHING
            """, (
                tool["name"], tool["label"], tool.get("description", ""),
                tool.get("category", "general"), tool["action_code"],
                json.dumps(tool.get("schema_json", {})),
                tool.get("is_sensitive", False),
                tool.get("requires_confirmation", False),
                tool.get("default_enabled", True),
                tool.get("functional_description", ""),
            ))
            if c.rowcount:
                inserted += 1
        conn.commit()
        conn.close()
        if inserted:
            print(f"[ToolsRegistry] {inserted} outils enregistrés")
    except Exception as e:
        print(f"[ToolsRegistry] seed: {e}")
    return inserted


def get_all_tools() -> list:
    """Retourne tous les outils du registre."""
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            SELECT name, label, description, category, action_code,
                   is_sensitive, requires_confirmation, default_enabled
            FROM tools_registry ORDER BY category, name
        """)
        cols = [d[0] for d in c.description]
        rows = [dict(zip(cols, r)) for r in c.fetchall()]
        conn.close()
        return rows
    except Exception:
        return _TOOLS  # fallback si table pas encore populee


def is_sensitive_action(action_code: str) -> bool:
    """
    Retourne True si l'action nécessite confirmation.
    Lit depuis le registre, fallback local si non trouvé.
    """
    name = action_code.split(":")[1] if ":" in action_code else action_code
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute(
            "SELECT requires_confirmation FROM tools_registry WHERE name = %s",
            (name,)
        )
        row = c.fetchone()
        conn.close()
        if row is not None:
            return bool(row[0])
    except Exception:
        pass
    # Fallback si tools_registry pas encore populé
    _FALLBACK_SENSITIVE = {
        "REPLY", "TEAMS_MSG", "TEAMS_REPLYCHAT", "TEAMS_SENDCHANNEL",
        "TEAMS_GROUPE", "DELETE_PERMANENT", "MOVEDRIVE", "COPYFILE", "CREATEEVENT",
    }
    return name in _FALLBACK_SENSITIVE
