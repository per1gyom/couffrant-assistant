"""
Registre d'outils Raya — Phase 3c (décision Opus étape 3c).

Centralise la déclaration de tous les outils disponibles :
  - nom, label, description, catégorie
  - code ACTION: correspondant
  - sensibilité (nécessite confirmation)
  - activé par défaut ou non

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
    {"name": "ARCHIVE",      "label": "Archiver un mail",            "category": "mail",
     "action_code": "ACTION:ARCHIVE:id",
     "description": "Archive un mail dans Outlook",
     "is_sensitive": False, "requires_confirmation": False, "default_enabled": True},
    {"name": "READ",         "label": "Marquer lu",                  "category": "mail",
     "action_code": "ACTION:READ:id",
     "description": "Marque un mail comme lu",
     "is_sensitive": False, "requires_confirmation": False, "default_enabled": True},
    {"name": "READBODY",     "label": "Lire le corps d'un mail",     "category": "mail",
     "action_code": "ACTION:READBODY:id",
     "description": "Télécharge et lit le corps complet d'un mail",
     "is_sensitive": False, "requires_confirmation": False, "default_enabled": True},
    {"name": "REPLY",        "label": "Répondre à un mail",          "category": "mail",
     "action_code": "ACTION:REPLY:id:texte",
     "description": "Répond à un mail via Outlook",
     "is_sensitive": True,  "requires_confirmation": True,  "default_enabled": True},
    {"name": "DELETE",       "label": "Supprimer un mail",           "category": "mail",
     "action_code": "ACTION:DELETE:id",
     "description": "Déplace un mail dans la corbeille (récupérable)",
     "is_sensitive": True,  "requires_confirmation": True,  "default_enabled": False},
    # —— CALENDRIER ——
    {"name": "CREATEEVENT",  "label": "Créer un événement",         "category": "calendar",
     "action_code": "ACTION:CREATEEVENT:sujet|debut|fin|participants",
     "description": "Crée un événement dans le calendrier Outlook",
     "is_sensitive": True,  "requires_confirmation": True,  "default_enabled": True},
    {"name": "CREATE_TASK",  "label": "Créer une tâche",            "category": "calendar",
     "action_code": "ACTION:CREATE_TASK:titre",
     "description": "Crée une tâche dans Microsoft To Do",
     "is_sensitive": False, "requires_confirmation": False, "default_enabled": True},
    # —— DRIVE ——
    {"name": "LISTDRIVE",    "label": "Lister Drive",                "category": "drive",
     "action_code": "ACTION:LISTDRIVE:",
     "description": "Liste les fichiers et dossiers SharePoint",
     "is_sensitive": False, "requires_confirmation": False, "default_enabled": True},
    {"name": "READDRIVE",    "label": "Lire un fichier Drive",       "category": "drive",
     "action_code": "ACTION:READDRIVE:id",
     "description": "Lit le contenu d'un fichier SharePoint",
     "is_sensitive": False, "requires_confirmation": False, "default_enabled": True},
    {"name": "SEARCHDRIVE",  "label": "Chercher dans Drive",        "category": "drive",
     "action_code": "ACTION:SEARCHDRIVE:mot",
     "description": "Recherche dans SharePoint par mot-clé",
     "is_sensitive": False, "requires_confirmation": False, "default_enabled": True},
    {"name": "MOVEDRIVE",    "label": "Déplacer un fichier",        "category": "drive",
     "action_code": "ACTION:MOVEDRIVE:item|dest|nom",
     "description": "Déplace un fichier dans SharePoint",
     "is_sensitive": True,  "requires_confirmation": True,  "default_enabled": False},
    {"name": "COPYFILE",     "label": "Copier un fichier",          "category": "drive",
     "action_code": "ACTION:COPYFILE:source|dest|nom",
     "description": "Copie un fichier dans SharePoint",
     "is_sensitive": True,  "requires_confirmation": True,  "default_enabled": False},
    {"name": "CREATEFOLDER", "label": "Créer un dossier",          "category": "drive",
     "action_code": "ACTION:CREATEFOLDER:parent|nom",
     "description": "Crée un dossier dans SharePoint",
     "is_sensitive": False, "requires_confirmation": False, "default_enabled": False},
    # —— TEAMS ——
    {"name": "TEAMS_LIST",   "label": "Lister les Teams",           "category": "teams",
     "action_code": "ACTION:TEAMS_LIST:",
     "description": "Liste les équipes Teams accessibles",
     "is_sensitive": False, "requires_confirmation": False, "default_enabled": True},
    {"name": "TEAMS_CHATS",  "label": "Lister les conversations Teams", "category": "teams",
     "action_code": "ACTION:TEAMS_CHATS:",
     "description": "Liste les conversations Teams récentes",
     "is_sensitive": False, "requires_confirmation": False, "default_enabled": True},
    {"name": "TEAMS_MSG",    "label": "Envoyer un message Teams",   "category": "teams",
     "action_code": "ACTION:TEAMS_MSG:email|texte",
     "description": "Envoie un message Teams à un contact",
     "is_sensitive": True,  "requires_confirmation": True,  "default_enabled": True},
    {"name": "TEAMS_REPLYCHAT", "label": "Répondre dans un chat Teams", "category": "teams",
     "action_code": "ACTION:TEAMS_REPLYCHAT:chat_id|texte",
     "description": "Répond dans une conversation Teams existante",
     "is_sensitive": True,  "requires_confirmation": True,  "default_enabled": True},
    {"name": "TEAMS_GROUPE", "label": "Créer un groupe Teams",      "category": "teams",
     "action_code": "ACTION:TEAMS_GROUPE:email1,email2|sujet|texte",
     "description": "Crée une conversation de groupe Teams",
     "is_sensitive": True,  "requires_confirmation": True,  "default_enabled": True},
    # —— MÉMOIRE ——
    {"name": "LEARN",        "label": "Apprendre une règle",        "category": "memory",
     "action_code": "ACTION:LEARN:catégorie|règle",
     "description": "Sauvegarde une nouvelle règle dans la mémoire de Raya",
     "is_sensitive": False, "requires_confirmation": False, "default_enabled": True},
    {"name": "INSIGHT",      "label": "Enregistrer une observation", "category": "memory",
     "action_code": "ACTION:INSIGHT:sujet|observation",
     "description": "Enregistre une observation sur l'utilisateur",
     "is_sensitive": False, "requires_confirmation": False, "default_enabled": True},
    {"name": "FORGET",       "label": "Oublier une règle",          "category": "memory",
     "action_code": "ACTION:FORGET:id",
     "description": "Désactive une règle de la mémoire",
     "is_sensitive": False, "requires_confirmation": False, "default_enabled": True},
    {"name": "SYNTH",        "label": "Synthétiser la session",     "category": "memory",
     "action_code": "ACTION:SYNTH:",
     "description": "Déclenche la synthèse des conversations récentes par Opus",
     "is_sensitive": False, "requires_confirmation": False, "default_enabled": True},
    {"name": "CONFIRM",      "label": "Confirmer une action",       "category": "workflow",
     "action_code": "ACTION:CONFIRM:id",
     "description": "Exécute une action sensible mise en queue",
     "is_sensitive": True,  "requires_confirmation": False, "default_enabled": True},
    {"name": "CANCEL",       "label": "Annuler une action",         "category": "workflow",
     "action_code": "ACTION:CANCEL:id",
     "description": "Annule une action sensible mise en queue",
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
        for tool in _TOOLS:
            c.execute("""
                INSERT INTO tools_registry
                  (name, label, description, category, action_code, schema_json,
                   is_sensitive, requires_confirmation, default_enabled)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (name) DO NOTHING
            """, (
                tool["name"], tool["label"], tool.get("description", ""),
                tool.get("category", "general"), tool["action_code"],
                json.dumps(tool.get("schema_json", {})),
                tool.get("is_sensitive", False),
                tool.get("requires_confirmation", False),
                tool.get("default_enabled", True),
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
        return _TOOLS  # fallback si table pas encore populer


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
