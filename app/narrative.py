"""
Mémoire narrative des dossiers — Phase 7 (7-NAR).

Construit et maintient l'histoire vivante de chaque entité
(contact, projet, entreprise, sujet) au fil des interactions.

Types d'entités :
  contact  : une personne  ("dupont", "marie_dupont")
  project  : un chantier   ("chantier_martin", "raccordement_lyon")
  company  : une entreprise ("couffrant_solar", "juillet")
  topic    : un sujet      ("facturation", "raccordement_enedis")

entity_key : identifiant normalisé (minuscule, underscores)
narrative  : texte libre résumant l'historique
key_facts  : faits clés datés :
  [{"date": "2026-01-15", "fact": "Premier contact, demande de devis"},
   {"date": "2026-03-10", "fact": "Retard livraison, client mécontent"}]
"""
from app.database import get_pg_conn
from app.logging_config import get_logger

logger = get_logger("raya.narrative")


def get_narrative(username: str, entity_type: str, entity_key: str,
                  tenant_id: str = None) -> dict | None:
    """Retourne la narrative d'une entité, ou None si inexistante."""
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            SELECT narrative, key_facts, last_event_date, updated_at
            FROM dossier_narratives
            WHERE username = %s AND entity_type = %s AND entity_key = %s
              AND (tenant_id = %s OR tenant_id IS NULL)
            LIMIT 1
        """, (username, entity_type, entity_key, tenant_id))
        row = c.fetchone()
        if not row:
            return None
        return {
            "narrative": row[0],
            "key_facts": row[1] or [],
            "last_event_date": str(row[2]) if row[2] else None,
            "updated_at": str(row[3]),
        }
    except Exception:
        return None
    finally:
        if conn: conn.close()


def upsert_narrative(username: str, entity_type: str, entity_key: str,
                     narrative: str, key_facts: list = None,
                     tenant_id: str = None) -> int:
    """
    Crée ou met à jour la narrative d'une entité.
    Vectorise automatiquement pour injection RAG.
    Retourne l'id de la ligne, ou 0 si erreur.
    """
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        import json

        # Vectorisation
        vec_str = None
        try:
            from app.embedding import embed
            vec = embed(f"[{entity_type}:{entity_key}] {narrative[:500]}")
            if vec:
                vec_str = "[" + ",".join(str(x) for x in vec) + "]"
        except Exception:
            pass

        facts_json = json.dumps(key_facts or [], ensure_ascii=False)

        if vec_str:
            c.execute("""
                INSERT INTO dossier_narratives
                    (username, tenant_id, entity_type, entity_key, narrative, key_facts,
                     last_event_date, embedding, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s::jsonb, NOW(), %s::vector, NOW())
                ON CONFLICT (username, tenant_id, entity_type, entity_key)
                DO UPDATE SET narrative = EXCLUDED.narrative,
                              key_facts = EXCLUDED.key_facts,
                              last_event_date = NOW(),
                              embedding = EXCLUDED.embedding,
                              updated_at = NOW()
                RETURNING id
            """, (username, tenant_id, entity_type, entity_key, narrative, facts_json, vec_str))
        else:
            c.execute("""
                INSERT INTO dossier_narratives
                    (username, tenant_id, entity_type, entity_key, narrative, key_facts,
                     last_event_date, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s::jsonb, NOW(), NOW())
                ON CONFLICT (username, tenant_id, entity_type, entity_key)
                DO UPDATE SET narrative = EXCLUDED.narrative,
                              key_facts = EXCLUDED.key_facts,
                              last_event_date = NOW(),
                              updated_at = NOW()
                RETURNING id
            """, (username, tenant_id, entity_type, entity_key, narrative, facts_json))

        row_id = c.fetchone()[0]
        conn.commit()
        return row_id
    except Exception as e:
        logger.error(f"[Narrative] Erreur upsert: {e}")
        return 0
    finally:
        if conn: conn.close()


def search_narratives(query: str, username: str, tenant_id: str = None,
                      tenant_ids: list = None, limit: int = 3) -> list:
    """
    Recherche sémantique dans les narratives.
    Utilisé pour l'injection RAG dans build_system_prompt.
    Fallback sur recherche texte si embeddings indisponibles.
    """
    # Tentative RAG via embeddings
    try:
        from app.embedding import search_similar
        rows = search_similar(
            table="dossier_narratives",
            username=username,
            query_text=query,
            limit=limit,
            tenant_id=tenant_id,
            tenant_ids=tenant_ids,
        )
        if rows:
            return [
                {
                    "entity_type": r.get("entity_type"),
                    "entity_key": r.get("entity_key"),
                    "narrative": r.get("narrative", ""),
                    "key_facts": r.get("key_facts", []),
                }
                for r in rows
            ]
    except Exception:
        pass

    # Fallback : recherche texte sur les 10 narratives les plus récentes
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            SELECT entity_type, entity_key, narrative, key_facts
            FROM dossier_narratives
            WHERE username = %s
              AND (tenant_id = %s OR tenant_id IS NULL OR %s IS NULL)
            ORDER BY updated_at DESC LIMIT %s
        """, (username, tenant_id, tenant_id, limit))
        rows = c.fetchall()
        return [
            {"entity_type": r[0], "entity_key": r[1],
             "narrative": r[2], "key_facts": r[3] or []}
            for r in rows
        ]
    except Exception:
        return []
    finally:
        if conn: conn.close()


def list_narratives(username: str, entity_type: str = None,
                    tenant_id: str = None, limit: int = 20) -> list:
    """Liste les narratives d'un utilisateur, optionnellement filtrées par type."""
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        if entity_type:
            c.execute("""
                SELECT entity_type, entity_key, narrative, key_facts, updated_at
                FROM dossier_narratives
                WHERE username = %s AND entity_type = %s
                  AND (tenant_id = %s OR tenant_id IS NULL)
                ORDER BY updated_at DESC LIMIT %s
            """, (username, entity_type, tenant_id, limit))
        else:
            c.execute("""
                SELECT entity_type, entity_key, narrative, key_facts, updated_at
                FROM dossier_narratives
                WHERE username = %s
                  AND (tenant_id = %s OR tenant_id IS NULL)
                ORDER BY updated_at DESC LIMIT %s
            """, (username, tenant_id, limit))
        rows = c.fetchall()
        return [
            {"entity_type": r[0], "entity_key": r[1],
             "narrative": r[2], "key_facts": r[3] or [],
             "updated_at": str(r[4])}
            for r in rows
        ]
    except Exception:
        return []
    finally:
        if conn: conn.close()
