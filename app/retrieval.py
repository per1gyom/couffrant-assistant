"""
Module de recherche hybrid sémantique + reranking + enrichissement par graphe.

COUCHE 3 du modèle mémoire de Raya (voir docs/raya_memory_architecture.md).
C'est LE module qui transforme les données vectorisées + le graphe typé en
résultats pertinents pour Raya.

Architecture en 3 étages :

1. HYBRID SEARCH (dense + sparse)
   - Dense : pgvector cosine sur odoo_semantic_content.embedding
     (OpenAI text-embedding-3-small, 1536 dims)
   - Sparse : PostgreSQL tsvector français sur content_tsv (BM25)
   - Fusion : Reciprocal Rank Fusion (RRF) avec k=60
   - Retourne top 50 candidats

2. RERANKING (Cohere rerank-3-multilingual)
   - Compare la query au texte complet de chaque candidat
   - Top 50 → top 10 finaux, classés par pertinence sémantique
   - Gain +3-5 points de pertinence vs embeddings seuls

3. ENRICHISSEMENT PAR GRAPHE (traverse multi-hop)
   - Pour chaque résultat du top 10, traverse le semantic_graph
   - Remonte le contexte relationnel : client lié, chantier, mails, etc.
   - Résout les cas complexes type Coullet/Glandier

Dégradation gracieuse : si Cohere n'est pas configuré (pas de clé API),
skip le reranking et retourne directement les top N du RRF. Si les
embeddings ne sont pas calculables (pas de clé OpenAI), fallback sur
sparse uniquement.
"""

import logging
import os
from typing import Optional

from app.database import get_pg_conn

logger = logging.getLogger("raya.retrieval")

# Paramètres de tuning
RRF_K = 60  # Constante Reciprocal Rank Fusion (60 est le standard de la littérature)
HYBRID_TOP_N = 50  # Candidats après fusion, avant reranking
FINAL_TOP_K = 10   # Résultats finaux après reranking
GRAPH_MAX_HOPS = 2  # Profondeur de traversée du graphe pour enrichissement


# ─── RECHERCHE DENSE (pgvector cosine) ────────────────────────

def _dense_search(
    tenant_id: str,
    query_embedding: list,
    limit: int = HYBRID_TOP_N,
    source_models: Optional[list] = None,
) -> list:
    """Recherche vectorielle sur odoo_semantic_content via pgvector cosine.
    Retourne une liste ordonnée (rang 1 = plus similaire) de dicts avec
    id, source_model, source_record_id, content_type, text_content,
    related_partner_id, similarity_score."""
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        vec_str = "[" + ",".join(str(x) for x in query_embedding) + "]"
        filters = ["tenant_id = %s", "embedding IS NOT NULL"]
        params = [tenant_id]
        if source_models:
            filters.append("source_model = ANY(%s)")
            params.append(source_models)
        where = " AND ".join(filters)

        c.execute(f"""
            SELECT id, source_model, source_record_id, content_type,
                   text_content, related_partner_id, metadata,
                   1 - (embedding <=> %s::vector) AS similarity
            FROM odoo_semantic_content
            WHERE {where}
            ORDER BY embedding <=> %s::vector
            LIMIT %s
        """, [vec_str] + params + [vec_str, limit])

        results = []
        for idx, row in enumerate(c.fetchall()):
            results.append({
                "id": row[0], "source_model": row[1],
                "source_record_id": row[2], "content_type": row[3],
                "text_content": row[4], "related_partner_id": row[5],
                "metadata": row[6] or {},
                "similarity": float(row[7]),
                "dense_rank": idx + 1,
            })
        return results
    except Exception as e:
        logger.warning("[Retrieval] dense_search échoué : %s", str(e)[:200])
        return []
    finally:
        if conn: conn.close()


# ─── RECHERCHE SPARSE (tsvector + BM25) ───────────────────────

def _sparse_search(
    tenant_id: str,
    query_text: str,
    limit: int = HYBRID_TOP_N,
    source_models: Optional[list] = None,
) -> list:
    """Recherche full-text via PostgreSQL tsvector avec dictionnaire français.
    Utilise ts_rank_cd (variante de BM25) pour scorer la pertinence.

    Cette recherche excelle sur les termes exacts que le modèle vectoriel
    peut rater : 'SE100K', 'FAC/2026/00042', noms propres, acronymes métier."""
    if not query_text or not query_text.strip():
        return []
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        # Recherche BM25 avec dictionnaire COMBINE 'french' + 'simple' pour capter
        # a la fois les requetes en langage naturel et les noms propres/acronymes
        # (SE100K, AZEM, SOLAREDGE, DMEGC, etc.) que 'french' seul filtre.
        filters = ["tenant_id = %s",
                   "content_tsv @@ (plainto_tsquery('french', %s) "
                   "|| plainto_tsquery('simple', %s))"]
        params = [tenant_id, query_text.strip(), query_text.strip()]
        if source_models:
            filters.append("source_model = ANY(%s)")
            params.append(source_models)
        where = " AND ".join(filters)

        c.execute(f"""
            SELECT id, source_model, source_record_id, content_type,
                   text_content, related_partner_id, metadata,
                   ts_rank_cd(content_tsv,
                              plainto_tsquery('french', %s)
                              || plainto_tsquery('simple', %s)) AS rank_score
            FROM odoo_semantic_content
            WHERE {where}
            ORDER BY rank_score DESC
            LIMIT %s
        """, [query_text.strip(), query_text.strip()] + params + [limit])

        results = []
        for idx, row in enumerate(c.fetchall()):
            results.append({
                "id": row[0], "source_model": row[1],
                "source_record_id": row[2], "content_type": row[3],
                "text_content": row[4], "related_partner_id": row[5],
                "metadata": row[6] or {},
                "bm25_score": float(row[7]),
                "sparse_rank": idx + 1,
            })
        return results
    except Exception as e:
        logger.warning("[Retrieval] sparse_search échoué : %s", str(e)[:200])
        return []
    finally:
        if conn: conn.close()


# ─── FUSION RECIPROCAL RANK FUSION ────────────────────────────

def _reciprocal_rank_fusion(
    dense_results: list,
    sparse_results: list,
    k: int = RRF_K,
) -> list:
    """Fusion RRF : pour chaque doc, score = 1/(k + rank_dense) + 1/(k + rank_sparse).
    Les docs présents dans les 2 listes remontent naturellement en haut.

    k=60 est le standard (Cormack et al. 2009). Plus k est grand, moins on
    pénalise les rangs élevés (lissage).

    Retourne une liste fusionnée, dédupliquée par id, triée par score décroissant."""
    scores = {}  # id -> {"score": float, "doc": dict, "dense_rank": int, "sparse_rank": int}

    for res in dense_results:
        rid = res["id"]
        rank = res.get("dense_rank", len(dense_results) + 1)
        scores[rid] = {
            "score": 1.0 / (k + rank),
            "doc": res,
            "dense_rank": rank,
            "sparse_rank": None,
            "similarity": res.get("similarity"),
        }

    for res in sparse_results:
        rid = res["id"]
        rank = res.get("sparse_rank", len(sparse_results) + 1)
        if rid in scores:
            # Doc déjà vu côté dense : on somme les deux contributions RRF
            scores[rid]["score"] += 1.0 / (k + rank)
            scores[rid]["sparse_rank"] = rank
            scores[rid]["bm25_score"] = res.get("bm25_score")
        else:
            scores[rid] = {
                "score": 1.0 / (k + rank),
                "doc": res,
                "dense_rank": None,
                "sparse_rank": rank,
                "bm25_score": res.get("bm25_score"),
            }

    # Tri par score fusion décroissant
    sorted_items = sorted(scores.values(), key=lambda x: x["score"], reverse=True)

    # Construction du résultat final en préservant les métadonnées utiles
    fused = []
    for item in sorted_items:
        doc = dict(item["doc"])  # copie pour ne pas muter les entrées originales
        doc["rrf_score"] = item["score"]
        doc["dense_rank"] = item.get("dense_rank")
        doc["sparse_rank"] = item.get("sparse_rank")
        fused.append(doc)
    return fused


# ─── RERANKING (Cohere rerank-3-multilingual) ─────────────────

def _rerank_with_cohere(
    query: str,
    candidates: list,
    top_k: int = FINAL_TOP_K,
) -> list:
    """Rerank avec Cohere rerank-3-multilingual. Degradation gracieuse si
    pas de clé Cohere : on retourne les top_k candidats tels quels (ordre RRF).

    Le reranker compare la query au text_content complet de chaque candidat
    et attribue un score de pertinence sémantique (0-1). Plus précis que
    les embeddings car il utilise un cross-encoder au lieu de deux vecteurs
    indépendants."""
    if not candidates:
        return []

    api_key = os.getenv("COHERE_API_KEY")
    if not api_key:
        logger.info("[Retrieval] Pas de COHERE_API_KEY, skip rerank (dégradation gracieuse)")
        return candidates[:top_k]

    try:
        import requests
        # Préparer les documents pour Cohere : juste le text_content tronqué
        documents = [c.get("text_content", "")[:3000] for c in candidates]

        response = requests.post(
            "https://api.cohere.com/v2/rerank",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "rerank-v3.5",  # dernière version multilingue Cohere
                "query": query,
                "documents": documents,
                "top_n": top_k,
            },
            timeout=8,
        )
        if response.status_code != 200:
            logger.warning("[Retrieval] Cohere rerank HTTP %d : %s",
                           response.status_code, response.text[:200])
            return candidates[:top_k]

        data = response.json()
        # Cohere retourne [{"index": i, "relevance_score": 0.xyz}]
        reranked = []
        for item in data.get("results", []):
            idx = item["index"]
            if 0 <= idx < len(candidates):
                c = dict(candidates[idx])
                c["rerank_score"] = item.get("relevance_score", 0)
                reranked.append(c)
        return reranked
    except Exception as e:
        logger.warning("[Retrieval] Cohere rerank échoué : %s", str(e)[:200])
        return candidates[:top_k]


# ─── ENRICHISSEMENT PAR LE GRAPHE SÉMANTIQUE ──────────────────

def _enrich_with_graph(
    tenant_id: str,
    results: list,
    max_hops: int = GRAPH_MAX_HOPS,
) -> list:
    """Pour chaque résultat, traverse le semantic_graph depuis le nœud
    correspondant pour remonter le contexte relationnel.

    Exemple : un résultat sur sale.order #123 va aussi remonter le partner
    associé (partner_of), les produits installés (has_line) et les events
    planifiés (scheduled_for). Permet à Raya de voir le contexte sans
    refaire 5 requêtes séquentielles.

    Chaque résultat se voit enrichi d'un champ 'related_nodes' : liste
    des nœuds voisins (max_hops=2 par défaut, ~10-20 nœuds max)."""
    from app.semantic_graph import find_node_id, traverse

    # Mapping source_model -> (node_type, key_prefix)
    MODEL_TO_NODE = {
        "res.partner": ("Person", "odoo-partner-"),  # fallback Company si pas trouvé
        "sale.order": ("Deal", "odoo-order-"),
        "crm.lead": ("Lead", "odoo-lead-"),
        "calendar.event": ("Event", "odoo-event-"),
        "product.product": ("Product", "odoo-product-"),
        "account.move": ("Invoice", "odoo-invoice-"),
        "account.payment": ("Payment", "odoo-payment-"),
    }

    enriched = []
    for r in results:
        r_copy = dict(r)
        r_copy["related_nodes"] = []
        r_copy["graph_context"] = None

        mapping = MODEL_TO_NODE.get(r["source_model"])
        if not mapping:
            enriched.append(r_copy)
            continue

        node_type, prefix = mapping
        node_key = f"{prefix}{r['source_record_id']}"
        node_id = find_node_id(tenant_id, node_type, node_key)

        # Fallback : pour res.partner, tenter aussi Company
        if not node_id and node_type == "Person":
            node_id = find_node_id(tenant_id, "Company", node_key)

        if not node_id:
            enriched.append(r_copy)
            continue

        trav = traverse(
            tenant_id=tenant_id,
            start_node_id=node_id,
            max_hops=max_hops,
            min_confidence=0.5,
            max_results=20,
        )
        # On garde juste les infos essentielles pour ne pas saturer
        related = []
        for node in trav.get("visited", []):
            related.append({
                "type": node["node_type"],
                "label": node["node_label"],
                "key": node["node_key"],
                "hops": node["hops_distance"],
            })
        r_copy["related_nodes"] = related
        r_copy["graph_context"] = {
            "start_node": node_key,
            "neighbors_count": len(related),
        }
        enriched.append(r_copy)

    return enriched


# ─── FONCTION PRINCIPALE ──────────────────────────────────────

def hybrid_search(
    query: str,
    tenant_id: str,
    source_models: Optional[list] = None,
    top_n_fusion: int = HYBRID_TOP_N,
    top_k_final: int = FINAL_TOP_K,
    enrich_graph: bool = True,
    use_rerank: bool = True,
) -> dict:
    """Point d'entrée principal du Bloc 4 : recherche hybrid + rerank + graph.

    Args:
        query: requête utilisateur en langage naturel
        tenant_id: tenant (pour isolation multi-tenant)
        source_models: filtrer sur certains modèles Odoo
          (ex: ['sale.order', 'crm.lead'] pour limiter au commercial)
        top_n_fusion: nombre de candidats à récupérer en dense + sparse avant RRF
        top_k_final: nombre de résultats finaux après reranking
        enrich_graph: si True, ajoute les nœuds voisins via traverse()
        use_rerank: si True, utilise Cohere (sinon skip reranking)

    Retourne :
      {
        "query": str,
        "tenant_id": str,
        "results": [list de résultats enrichis],
        "stats": {
          "dense_count": int, "sparse_count": int,
          "fused_count": int, "final_count": int,
          "embedding_available": bool,
          "rerank_used": bool,
        },
      }
    """
    from app.embedding import embed, is_available as embed_available

    stats = {
        "dense_count": 0, "sparse_count": 0,
        "fused_count": 0, "final_count": 0,
        "embedding_available": embed_available(),
        "rerank_used": False,
    }

    if not query or not query.strip():
        return {"query": query, "tenant_id": tenant_id, "results": [], "stats": stats}

    # Étage 1 : dense + sparse en parallèle (ou séquentiel si embedding indispo)
    dense = []
    sparse = _sparse_search(tenant_id, query, limit=top_n_fusion,
                            source_models=source_models)
    stats["sparse_count"] = len(sparse)

    if stats["embedding_available"]:
        query_vec = embed(query)
        if query_vec:
            dense = _dense_search(tenant_id, query_vec, limit=top_n_fusion,
                                  source_models=source_models)
            stats["dense_count"] = len(dense)

    # Étage 2 : fusion RRF
    fused = _reciprocal_rank_fusion(dense, sparse, k=RRF_K)
    stats["fused_count"] = len(fused)

    # On tronque à top_n_fusion pour ne pas envoyer 500 docs à Cohere
    candidates = fused[:top_n_fusion]

    # Étage 3 : reranking Cohere
    if use_rerank and candidates:
        reranked = _rerank_with_cohere(query, candidates, top_k=top_k_final)
        stats["rerank_used"] = any("rerank_score" in r for r in reranked)
        results = reranked
    else:
        results = candidates[:top_k_final]

    stats["final_count"] = len(results)

    # Étage 4 : enrichissement par traverse du graphe
    if enrich_graph and results:
        results = _enrich_with_graph(tenant_id, results, max_hops=GRAPH_MAX_HOPS)

    return {
        "query": query,
        "tenant_id": tenant_id,
        "results": results,
        "stats": stats,
    }


# ─── HELPER DE FORMATAGE POUR RAYA ────────────────────────────

def format_search_results(data: dict, max_items: int = 10) -> str:
    """Formate le résultat de hybrid_search en texte structuré pour Raya.
    Chaque entrée inclut le texte source + le contexte relationnel du graphe."""
    if not data or not data.get("results"):
        stats = data.get("stats") if data else {}
        if stats and not stats.get("embedding_available"):
            return "⚠️ Recherche sémantique indisponible (OPENAI_API_KEY manquant côté Raya)."
        return "🔍 Aucun résultat trouvé pour cette requête dans les données Odoo."

    results = data["results"][:max_items]
    stats = data.get("stats", {})
    query = data.get("query", "")

    lines = [f"🔍 Recherche sémantique : '{query}'"]
    lines.append(f"({stats.get('final_count', 0)} résultat(s) · dense={stats.get('dense_count',0)}"
                 f" · sparse={stats.get('sparse_count',0)}"
                 f"{' · reranké' if stats.get('rerank_used') else ''})")
    lines.append("")

    for idx, r in enumerate(results, 1):
        source_model = r.get("source_model", "?")
        record_id = r.get("source_record_id", "?")
        text = (r.get("text_content") or "").strip()
        # Tronquer le texte pour ne pas exploser le prompt
        if len(text) > 350:
            text = text[:347] + "..."

        # Préfixe visuel par type de modèle
        icon = {
            "sale.order": "📋", "crm.lead": "🎯",
            "calendar.event": "📅", "res.partner": "👤",
            "account.move": "🧾", "account.payment": "💰",
        }.get(source_model, "•")

        lines.append(f"{idx}. {icon} [{source_model}#{record_id}] {text}")

        # Scores pour diagnostic (optionnel, utile en debug)
        score_bits = []
        if r.get("rerank_score") is not None:
            score_bits.append(f"rerank={r['rerank_score']:.3f}")
        elif r.get("rrf_score") is not None:
            score_bits.append(f"rrf={r['rrf_score']:.4f}")
        if score_bits:
            lines.append(f"   ({' · '.join(score_bits)})")

        # Contexte relationnel depuis le graphe
        related = r.get("related_nodes") or []
        if related:
            # Grouper par type pour lisibilité
            by_type = {}
            for n in related:
                by_type.setdefault(n["type"], []).append(n["label"] or "?")
            ctx_parts = []
            for t, labels in by_type.items():
                shown = ", ".join(labels[:3])
                if len(labels) > 3:
                    shown += f" +{len(labels)-3}"
                ctx_parts.append(f"{t}: {shown}")
            lines.append(f"   🔗 {' · '.join(ctx_parts)}")
        lines.append("")

    return "\n".join(lines)
