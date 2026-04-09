"""
Module d'embedding sémantique pour Raya.

Utilise OpenAI text-embedding-3-small (1536 dimensions).
Dégradation gracieuse si OPENAI_API_KEY absent : retourne None,
les insertions fonctionnent normalement sans vecteur.

Pour activer :
  Ajouter OPENAI_API_KEY dans les variables Railway.
"""
import os
from typing import Optional

_client = None
_MODEL = "text-embedding-3-small"
_DIMS = 1536


def _get_client():
    global _client
    if _client is not None:
        return _client
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None
    try:
        from openai import OpenAI
        _client = OpenAI(api_key=api_key)
        return _client
    except ImportError:
        print("[Embedding] openai non installé — pip install openai")
        return None
    except Exception as e:
        print(f"[Embedding] Erreur init client: {e}")
        return None


def embed(text: str) -> Optional[list]:
    """
    Génère un vecteur sémantique pour un texte.
    Retourne None si OPENAI_API_KEY absent ou erreur.
    Le texte est tronqué à 8000 caractères pour éviter les dépassements.
    """
    client = _get_client()
    if not client or not text or not text.strip():
        return None
    try:
        text_clean = text.strip()[:8000]
        response = client.embeddings.create(
            model=_MODEL,
            input=text_clean,
            dimensions=_DIMS,
        )
        return response.data[0].embedding
    except Exception as e:
        print(f"[Embedding] Erreur embed: {e}")
        return None


def embed_batch(texts: list) -> list:
    """
    Génère des vecteurs pour une liste de textes.
    Retourne une liste de même taille avec None pour les échecs.
    """
    client = _get_client()
    if not client:
        return [None] * len(texts)
    try:
        clean = [t.strip()[:8000] if t else "" for t in texts]
        response = client.embeddings.create(model=_MODEL, input=clean, dimensions=_DIMS)
        return [item.embedding for item in sorted(response.data, key=lambda x: x.index)]
    except Exception as e:
        print(f"[Embedding] Erreur embed_batch: {e}")
        return [None] * len(texts)


def search_similar(
    table: str,
    username: str,
    query_text: str,
    limit: int = 5,
    tenant_id: str = None,
    extra_filter: str = "",
) -> list:
    """
    Recherche sémantique dans une table par similarité cosinus.
    Retourne les lignes les plus proches du texte de requête.

    Si pas de vecteur disponible (clé manquante), retourne [].
    L'appelant doit gérer le fallback vers une recherche textuelle.
    """
    query_vec = embed(query_text)
    if query_vec is None:
        return []

    from app.database import get_pg_conn
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()

        # Filtre de base
        filters = ["embedding IS NOT NULL"]
        params = []

        if username:
            filters.append("username = %s")
            params.append(username)
        if tenant_id:
            filters.append("tenant_id = %s")
            params.append(tenant_id)
        if extra_filter:
            filters.append(extra_filter)

        where = " AND ".join(filters)
        vec_str = "[" + ",".join(str(x) for x in query_vec) + "]"

        c.execute(f"""
            SELECT *, 1 - (embedding <=> %s::vector) AS similarity
            FROM {table}
            WHERE {where}
            ORDER BY embedding <=> %s::vector
            LIMIT %s
        """, [vec_str] + params + [vec_str, limit])

        cols = [desc[0] for desc in c.description]
        return [dict(zip(cols, row)) for row in c.fetchall()]
    except Exception as e:
        print(f"[Embedding] Erreur search_similar {table}: {e}")
        return []
    finally:
        if conn: conn.close()


def is_available() -> bool:
    """Retourne True si l'embedding est opérationnel."""
    return _get_client() is not None
