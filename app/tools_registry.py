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

from app.tools_seed_data import _TOOLS  # noqa


def seed_tools_registry() -> int:
    """Remplit le registre. Idempotent (ON CONFLICT DO NOTHING)."""
    inserted = 0
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        import json
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
        return _TOOLS


def is_sensitive_action(action_code: str) -> bool:
    """Retourne True si l'action nécessite confirmation."""
    name = action_code.split(":")[1] if ":" in action_code else action_code
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("SELECT requires_confirmation FROM tools_registry WHERE name = %s", (name,))
        row = c.fetchone()
        conn.close()
        if row is not None:
            return bool(row[0])
    except Exception:
        pass
    _FALLBACK_SENSITIVE = {
        "REPLY", "TEAMS_MSG", "TEAMS_REPLYCHAT", "TEAMS_SENDCHANNEL",
        "TEAMS_GROUPE", "DELETE_PERMANENT", "MOVEDRIVE", "COPYFILE", "CREATEEVENT",
    }
    return name in _FALLBACK_SENSITIVE
