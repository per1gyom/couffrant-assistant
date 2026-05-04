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
    des nœuds voisins (max_hops=2 par défaut, ~10-20 nœuds max).

    V2.6 (27/04 nuit) : refactor du mapping vers le nouveau format de cles
    'odoo:<source_model>:<id>' utilise par le scanner universel. Ajout des
    modeles of.planning.tour, of.planning.tour.line, of.planning.task,
    sale.order.line, account.move.line (resolus le bug du planning sans
    detail des interventions)."""
    from app.semantic_graph import find_node_id, traverse

    # Mapping source_model Odoo -> (node_type principal, fallback_node_type)
    # Les cles de noeuds utilisent le format 'odoo:<source_model>:<id>' depuis
    # le scanner universel (commit 18/04 soir). L ancien format 'odoo-X-id' est
    # obsolete (cf docs/a_faire.md - migration en cours).
    # Le fallback gere les cas ou un modele a 2 node_types possibles
    # (ex: res.partner peut etre Person OU Company selon is_company).
    MODEL_TO_NODE = {
        # Entites principales (clients, deals, factures...)
        "res.partner":        ("Person",       "Company"),
        "sale.order":         ("Deal",         None),
        "sale.order.line":    ("DealLine",     None),
        "crm.lead":           ("Lead",         None),
        "calendar.event":     ("Event",        None),
        "calendar.attendee":  ("Attendee",     None),
        "account.move":       ("Invoice",      None),
        "account.move.line":  ("InvoiceLine",  None),
        "account.payment":    ("Payment",      None),
        # Produits (template = catalogue, variant = unite vendable)
        "product.template":   ("Product",         None),
        "product.product":    ("ProductVariant",  "Product"),
        # Planning (gros bloc OpenFire - corrige bug du 27/04 sur of.planning.tour)
        "of.planning.tour":            ("Tour",      None),
        "of.planning.tour.line":       ("TourStop",  None),
        "of.planning.task":            ("Task",      None),
        "of.planning.intervention.template": ("InterventionTemplate", None),
        "of.planning.intervention.section":  ("InterventionSection",  None),
        "of.planning.available.slot":  ("Slot",      None),
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

        node_type, fallback_type = mapping
        # Nouveau format de cle : 'odoo:<source_model>:<id>'
        node_key = f"odoo:{r['source_model']}:{r['source_record_id']}"
        node_id = find_node_id(tenant_id, node_type, node_key)

        # Fallback : essayer le node_type alternatif (ex: Company si Person echoue)
        if not node_id and fallback_type:
            node_id = find_node_id(tenant_id, fallback_type, node_key)

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



# ═══════════════════════════════════════════════════════════════
# UNIFIED SEARCH MULTI-SOURCE (étape A, 20/04/2026 nuit)
#
# Recherche unifiée sur TOUTES les mémoires de Raya en parallèle :
#   - odoo_semantic_content (ERP : clients, devis, factures, events...)
#   - drive_semantic_content (SharePoint : fichiers, photos, PDF...)
#   - mail_memory (emails analysés Outlook/Gmail)
#   - aria_memory (historique conversations Raya)
#
# Principe architectural (voir docs/vision_architecture_raya.md) :
#   - 4 requêtes Postgres en parallèle via ThreadPoolExecutor
#   - Chaque table garde ses index optimaux (HNSW + GIN où dispo)
#   - Fusion RRF unifiée, reranking Cohere sur l'union
#   - Chaque résultat tagué avec sa source pour traçabilité
#   - Rétrocompatibilité : hybrid_search(...) continue de fonctionner
#
# Ce bloc ne remplace PAS hybrid_search. Il ajoute unified_search() en
# parallèle. Branché manuellement côté prompt après validation.
# ═══════════════════════════════════════════════════════════════


# ─── DRIVE : DENSE ─────────────────────────────────────────────

def _dense_search_drive(
    tenant_id: str,
    query_embedding: list,
    limit: int = HYBRID_TOP_N,
) -> list:
    """Recherche pgvector cosine sur drive_semantic_content.
    Retourne les nœuds level 1 (méta) et level 2 (chunks détail) ensemble.
    Le reranking gèrera le choix final."""
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        vec_str = "[" + ",".join(str(x) for x in query_embedding) + "]"
        c.execute("""
            SELECT id, file_id, file_name, file_path, web_url, file_ext,
                   level, chunk_index, text_content, metadata, mime_type,
                   1 - (embedding <=> %s::vector) AS similarity
            FROM drive_semantic_content
            WHERE tenant_id = %s
              AND embedding IS NOT NULL
              AND deleted_at IS NULL
            ORDER BY embedding <=> %s::vector
            LIMIT %s
        """, (vec_str, tenant_id, vec_str, limit))
        results = []
        for idx, row in enumerate(c.fetchall()):
            results.append({
                "id": f"drive-{row[0]}",
                "source": "drive",
                "source_key": row[1],
                "display_label": row[2],
                "display_meta": row[3] or "",
                "web_url": row[4],
                "file_ext": row[5],
                "level": row[6],
                "chunk_index": row[7],
                "text_content": row[8],
                "metadata": row[9] or {},
                "mime_type": row[10],
                "similarity": float(row[11]),
                "dense_rank": idx + 1,
            })
        return results
    except Exception as e:
        logger.warning("[UnifiedRetrieval] dense_drive échoué : %s", str(e)[:200])
        return []
    finally:
        if conn: conn.close()


# ─── DRIVE : SPARSE (BM25 via tsvector) ────────────────────────

def _sparse_search_drive(
    tenant_id: str,
    query_text: str,
    limit: int = HYBRID_TOP_N,
) -> list:
    """Recherche BM25 sur drive_semantic_content.content_tsv.
    Capte les noms de fichiers exacts, références produit dans les docs,
    etc. Même logique que _sparse_search Odoo : french + simple fusionnés."""
    if not query_text or not query_text.strip():
        return []
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        q = query_text.strip()
        c.execute("""
            SELECT id, file_id, file_name, file_path, web_url, file_ext,
                   level, chunk_index, text_content, metadata, mime_type,
                   ts_rank_cd(content_tsv,
                              plainto_tsquery('french', %s)
                              || plainto_tsquery('simple', %s)) AS rank_score
            FROM drive_semantic_content
            WHERE tenant_id = %s
              AND deleted_at IS NULL
              AND content_tsv @@ (plainto_tsquery('french', %s)
                                  || plainto_tsquery('simple', %s))
            ORDER BY rank_score DESC
            LIMIT %s
        """, (q, q, tenant_id, q, q, limit))
        results = []
        for idx, row in enumerate(c.fetchall()):
            results.append({
                "id": f"drive-{row[0]}",
                "source": "drive",
                "source_key": row[1],
                "display_label": row[2],
                "display_meta": row[3] or "",
                "web_url": row[4],
                "file_ext": row[5],
                "level": row[6],
                "chunk_index": row[7],
                "text_content": row[8],
                "metadata": row[9] or {},
                "mime_type": row[10],
                "bm25_score": float(row[11]),
                "sparse_rank": idx + 1,
            })
        return results
    except Exception as e:
        logger.warning("[UnifiedRetrieval] sparse_drive échoué : %s", str(e)[:200])
        return []
    finally:
        if conn: conn.close()


# ─── MAIL : DENSE (pas de tsvector, dense uniquement) ──────────

def _dense_search_mail(
    tenant_id: str,
    username: str,
    query_embedding: list,
    limit: int = HYBRID_TOP_N,
    mailbox: Optional[str] = None,
) -> list:
    """Recherche pgvector sur mail_memory.
    Scope : tenant_id + username (mails scopés par utilisateur).
    Si mailbox est fourni (ex: 'guillaume@couffrant-solar.fr'),
    restreint la recherche a cette boite uniquement (filtre
    mailbox_email). Indispensable pour les actions ciblees type
    'tri dans ma boite Couffrant Solar' qui ne doivent pas
    remonter de mails d autres boites mail.
    text_content reconstruit = subject + short_summary + raw_body_preview
    pour que Cohere ait du contexte riche au reranking."""
    if not username:
        return []
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        vec_str = "[" + ",".join(str(x) for x in query_embedding) + "]"
        mbx_clause = ""
        params = [vec_str, tenant_id, username]
        if mailbox:
            mbx_clause = " AND mailbox_email = %s"
            params.append(mailbox)
        params.extend([vec_str, limit])
        c.execute(f"""
            SELECT id, message_id, thread_id, from_email, subject,
                   short_summary, raw_body_preview, received_at,
                   category, mailbox_source, display_title,
                   1 - (embedding <=> %s::vector) AS similarity
            FROM mail_memory
            WHERE tenant_id = %s AND username = %s
              AND embedding IS NOT NULL
              AND deleted_at IS NULL
              {mbx_clause}
            ORDER BY embedding <=> %s::vector
            LIMIT %s
        """, params)
        results = []
        for idx, row in enumerate(c.fetchall()):
            subject = row[4] or ""
            summary = row[5] or ""
            preview = (row[6] or "")[:500]
            text_full = "\n".join([t for t in [subject, summary, preview] if t])
            results.append({
                "id": f"mail-{row[0]}",
                "source": "mail",
                "source_key": row[1],  # message_id
                "display_label": row[10] or subject or "(sans objet)",
                "display_meta": f"de {row[3]} · {row[7] or ''}",
                "text_content": text_full,
                "metadata": {
                    "thread_id": row[2], "from_email": row[3],
                    "category": row[8], "mailbox": row[9],
                },
                "similarity": float(row[11]),
                "dense_rank": idx + 1,
            })
        return results
    except Exception as e:
        logger.warning("[UnifiedRetrieval] dense_mail échoué : %s", str(e)[:200])
        return []
    finally:
        if conn: conn.close()


# ─── CONVERSATION : DENSE (aria_memory) ────────────────────────

def _dense_search_conversation(
    tenant_id: str,
    username: str,
    query_embedding: list,
    limit: int = HYBRID_TOP_N,
) -> list:
    """Recherche pgvector sur aria_memory (historique conversations).
    Scope : tenant_id + username. text_content = user_input + aria_response
    pour capter les deux côtés d'un échange."""
    if not username:
        return []
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        vec_str = "[" + ",".join(str(x) for x in query_embedding) + "]"
        c.execute("""
            SELECT id, user_input, aria_response, created_at,
                   1 - (embedding <=> %s::vector) AS similarity
            FROM aria_memory
            WHERE tenant_id = %s AND username = %s
              AND embedding IS NOT NULL
            ORDER BY embedding <=> %s::vector
            LIMIT %s
        """, (vec_str, tenant_id, username, vec_str, limit))
        results = []
        for idx, row in enumerate(c.fetchall()):
            user_q = (row[1] or "")[:200]
            response = (row[2] or "")[:500]
            text_full = f"Q: {user_q}\nR: {response}"
            # Label court = premiers mots de la question
            label = user_q[:80] + ("..." if len(user_q) > 80 else "")
            results.append({
                "id": f"conv-{row[0]}",
                "source": "conversation",
                "source_key": str(row[0]),
                "display_label": label or "(échange ancien)",
                "display_meta": str(row[3]) if row[3] else "",
                "text_content": text_full,
                "metadata": {"created_at": str(row[3]) if row[3] else None},
                "similarity": float(row[4]),
                "dense_rank": idx + 1,
            })
        return results
    except Exception as e:
        logger.warning("[UnifiedRetrieval] dense_conversation échoué : %s", str(e)[:200])
        return []
    finally:
        if conn: conn.close()


# ─── ODOO : ADAPTATEURS AU FORMAT UNIFIÉ ───────────────────────

def _odoo_to_unified(raw_results: list) -> list:
    """Convertit les résultats de _dense_search / _sparse_search (format
    historique Odoo) vers le format unifié utilisé par unified_search.
    Évite de dupliquer les fonctions SQL existantes.

    IMPORTANT : extrait le VRAI NOM (personne, devis, event...) depuis
    text_content pour le mettre en display_label. Sinon Opus ne le voit
    qu'en 2e ligne et peut halluciner les prenoms (bug Legroux 21/04)."""
    unified = []
    for r in raw_results:
        # Extraction du nom propre depuis text_content :
        # - Partner : "Arrault Legroux — à Saint-Pryvé..." -> "Arrault Legroux"
        # - Order   : "D2500225 — pour Arrault Legroux..." -> "D2500225 — pour Arrault Legroux"
        # - Event   : "LEGROUX Jean-Bernard 45750... — le 2026-03-23" -> tronqué
        # - Lead    : "2406 - PV pro - LEGROUX — SARL DES MOINES..." -> tronqué
        text = r.get("text_content", "") or ""
        # Couper a la premiere virgule OU au 2e tiret OU 100 caracteres
        first_segment = text.split(" — ", 2)
        if len(first_segment) >= 2:
            # Garder les 2 premiers segments (ex: "D2500225 — pour Arrault Legroux")
            real_label = (first_segment[0] + " — " + first_segment[1])[:140]
        else:
            real_label = text[:140]
        real_label = real_label.strip() or r.get("content_type", "record")

        unified.append({
            "id": f"odoo-{r['id']}",
            "source": "odoo",
            "source_key": f"{r['source_model']}#{r['source_record_id']}",
            "source_model": r["source_model"],
            "source_record_id": r["source_record_id"],
            "display_label": real_label,
            "display_meta": f"{r.get('source_model', '')} #{r.get('source_record_id', '')}",
            "content_type": r.get("content_type", ""),
            "text_content": r.get("text_content", ""),
            "metadata": r.get("metadata") or {},
            "related_partner_id": r.get("related_partner_id"),
            "similarity": r.get("similarity"),
            "bm25_score": r.get("bm25_score"),
            "dense_rank": r.get("dense_rank"),
            "sparse_rank": r.get("sparse_rank"),
        })
    return unified


# ─── FUSION RRF MULTI-SOURCE ───────────────────────────────────

def _rrf_multi_source(dense_lists: list, sparse_lists: list,
                     k: int = RRF_K) -> list:
    """RRF étendu pour N listes dense + M listes sparse.
    Chaque liste a son propre classement (rank 1 = top de SA source).
    Le score final est la somme des 1/(k+rank) sur toutes les listes.
    Les résultats qui apparaissent dans plusieurs listes remontent naturellement.
    Déduplication par id unique (préfixé par source : odoo-xxx, drive-xxx...)."""
    scores = {}  # id -> accumulateur
    for lst in dense_lists:
        for res in lst:
            rid = res["id"]
            rank = res.get("dense_rank", len(lst) + 1)
            if rid not in scores:
                scores[rid] = {"score": 0.0, "doc": res,
                               "dense_ranks": [], "sparse_ranks": []}
            scores[rid]["score"] += 1.0 / (k + rank)
            scores[rid]["dense_ranks"].append(rank)
    for lst in sparse_lists:
        for res in lst:
            rid = res["id"]
            rank = res.get("sparse_rank", len(lst) + 1)
            if rid not in scores:
                scores[rid] = {"score": 0.0, "doc": res,
                               "dense_ranks": [], "sparse_ranks": []}
            scores[rid]["score"] += 1.0 / (k + rank)
            scores[rid]["sparse_ranks"].append(rank)
    sorted_items = sorted(scores.values(), key=lambda x: x["score"], reverse=True)
    fused = []
    for item in sorted_items:
        doc = dict(item["doc"])
        doc["rrf_score"] = item["score"]
        doc["dense_ranks"] = item["dense_ranks"]
        doc["sparse_ranks"] = item["sparse_ranks"]
        fused.append(doc)
    return fused


# ─── FONCTION PRINCIPALE UNIFIED SEARCH ────────────────────────

UNIFIED_FINAL_TOP_K = 15  # Plus large que FINAL_TOP_K=10 car union de 4 sources


def unified_search(
    query: str,
    tenant_id: str,
    username: Optional[str] = None,
    sources: Optional[list] = None,
    top_n_fusion: int = HYBRID_TOP_N,
    top_k_final: int = UNIFIED_FINAL_TOP_K,
    use_rerank: bool = True,
    enrich_graph: bool = True,
    mailbox: Optional[str] = None,
) -> dict:
    """Recherche multi-source parallèle sur toutes les mémoires de Raya.

    Args:
      query: question utilisateur en langage naturel
      tenant_id: tenant scope (isolation multi-tenant)
      username: requis pour inclure mail_memory et aria_memory
      sources: liste de sources à inclure (défaut : toutes selon contexte)
          Valeurs possibles : ['odoo', 'drive', 'mail', 'conversation']
      top_n_fusion: candidats par source avant RRF
      top_k_final: résultats finaux après rerank
      use_rerank: activer le reranking Cohere
      enrich_graph: ajouter les nœuds voisins du graphe aux résultats Odoo

    Retourne un dict avec results (liste unifiée) + stats par source.
    """
    from app.embedding import embed, is_available as embed_available
    from concurrent.futures import ThreadPoolExecutor

    # Sources effectives : toutes par défaut, mail/conversation skip si pas de username
    if sources is None:
        sources = ["odoo", "drive"]
        if username:
            sources.extend(["mail", "conversation"])
    sources = set(sources)

    stats = {
        "sources_queried": sorted(sources),
        "per_source_dense": {}, "per_source_sparse": {},
        "fused_count": 0, "final_count": 0,
        "embedding_available": embed_available(),
        "rerank_used": False,
    }

    if not query or not query.strip():
        return {"query": query, "tenant_id": tenant_id, "results": [], "stats": stats}

    # 1 seul embedding de la question, réutilisé sur toutes les sources
    query_vec = embed(query) if stats["embedding_available"] else None

    # ─ Étage 1 : exécution parallèle de toutes les recherches ─
    dense_lists = []
    sparse_lists = []

    with ThreadPoolExecutor(max_workers=6) as executor:
        futures = {}
        if "odoo" in sources:
            # Sparse Odoo (toujours possible, pas besoin d'embedding)
            futures["sp_odoo"] = executor.submit(
                _sparse_search, tenant_id, query, top_n_fusion, None)
            if query_vec:
                futures["dn_odoo"] = executor.submit(
                    _dense_search, tenant_id, query_vec, top_n_fusion, None)
        if "drive" in sources:
            futures["sp_drive"] = executor.submit(
                _sparse_search_drive, tenant_id, query, top_n_fusion)
            if query_vec:
                futures["dn_drive"] = executor.submit(
                    _dense_search_drive, tenant_id, query_vec, top_n_fusion)
        if "mail" in sources and query_vec and username:
            futures["dn_mail"] = executor.submit(
                _dense_search_mail, tenant_id, username, query_vec, top_n_fusion, mailbox)
        if "conversation" in sources and query_vec and username:
            futures["dn_conv"] = executor.submit(
                _dense_search_conversation, tenant_id, username, query_vec, top_n_fusion)

        # Récupération résultats (wait up to 8s par source)
        results_by_key = {}
        for key, fut in futures.items():
            try:
                results_by_key[key] = fut.result(timeout=8)
            except Exception as e:
                logger.warning("[UnifiedRetrieval] %s timeout/erreur : %s",
                               key, str(e)[:150])
                results_by_key[key] = []

    # Normaliser Odoo au format unifié + alimenter dense/sparse lists
    if "dn_odoo" in results_by_key:
        raw = results_by_key["dn_odoo"]
        stats["per_source_dense"]["odoo"] = len(raw)
        dense_lists.append(_odoo_to_unified(raw))
    if "sp_odoo" in results_by_key:
        raw = results_by_key["sp_odoo"]
        stats["per_source_sparse"]["odoo"] = len(raw)
        sparse_lists.append(_odoo_to_unified(raw))
    if "dn_drive" in results_by_key:
        stats["per_source_dense"]["drive"] = len(results_by_key["dn_drive"])
        dense_lists.append(results_by_key["dn_drive"])
    if "sp_drive" in results_by_key:
        stats["per_source_sparse"]["drive"] = len(results_by_key["sp_drive"])
        sparse_lists.append(results_by_key["sp_drive"])
    if "dn_mail" in results_by_key:
        stats["per_source_dense"]["mail"] = len(results_by_key["dn_mail"])
        dense_lists.append(results_by_key["dn_mail"])
    if "dn_conv" in results_by_key:
        stats["per_source_dense"]["conversation"] = len(results_by_key["dn_conv"])
        dense_lists.append(results_by_key["dn_conv"])


    # ─ Étage 2 : fusion RRF multi-source ─
    fused = _rrf_multi_source(dense_lists, sparse_lists, k=RRF_K)
    stats["fused_count"] = len(fused)

    # Tronquer à top_n_fusion pour limiter l'envoi à Cohere
    candidates = fused[:top_n_fusion]

    # ─ Étage 3 : reranking Cohere sur l'union ─
    if use_rerank and candidates:
        reranked = _rerank_with_cohere(query, candidates, top_k=top_k_final)
        stats["rerank_used"] = any("rerank_score" in r for r in reranked)
        results = reranked
    else:
        results = candidates[:top_k_final]
    stats["final_count"] = len(results)

    # ─ Étage 4 : enrichissement graphe (Odoo pour l'instant, drive en commit 2) ─
    if enrich_graph and results:
        # On ne peut enrich que les résultats Odoo tant que drive/mail/conv
        # ne sont pas dans le graphe (commits 2 et 5 à venir). On sépare pour
        # ne pas polluer les résultats non-Odoo avec des related_nodes vides.
        odoo_results = [r for r in results if r.get("source") == "odoo"]
        other_results = [r for r in results if r.get("source") != "odoo"]
        if odoo_results:
            # Adapter au format attendu par _enrich_with_graph (avec source_model
            # + source_record_id exposés à la racine, ce qu'_odoo_to_unified fait)
            enriched = _enrich_with_graph(tenant_id, odoo_results,
                                          max_hops=GRAPH_MAX_HOPS)
            # Re-fusionner en conservant l'ordre du rerank
            enriched_by_id = {r["id"]: r for r in enriched}
            results = [enriched_by_id.get(r["id"], r) for r in results]

    return {
        "query": query,
        "tenant_id": tenant_id,
        "username": username,
        "results": results,
        "stats": stats,
    }


# ─── FORMATAGE DES RÉSULTATS UNIFIÉS ───────────────────────────

def format_unified_results(data: dict, max_items: int = 15) -> str:
    """Formate les résultats unified_search en texte pour Raya.
    Chaque entrée porte un icône par source + son display_label + meta."""
    if not data or not data.get("results"):
        stats = data.get("stats") if data else {}
        if stats and not stats.get("embedding_available"):
            return "⚠️ Recherche sémantique indisponible (OPENAI_API_KEY manquant)."
        return "🔍 Aucun résultat trouvé pour cette requête."

    results = data["results"][:max_items]
    stats = data.get("stats", {})
    query = data.get("query", "")

    src_stats = []
    for src in stats.get("sources_queried", []):
        dense = stats.get("per_source_dense", {}).get(src, 0)
        sparse = stats.get("per_source_sparse", {}).get(src, 0)
        parts = []
        if dense: parts.append(f"d={dense}")
        if sparse: parts.append(f"s={sparse}")
        if parts: src_stats.append(f"{src}:{'/'.join(parts)}")

    lines = [f"🔍 Recherche multi-source : '{query}'"]
    lines.append(f"({stats.get('final_count', 0)} résultats · "
                 f"{', '.join(src_stats) if src_stats else 'aucune source'}"
                 f"{' · reranké' if stats.get('rerank_used') else ''})")
    lines.append("")

    icon_by_source = {
        "odoo": "📋", "drive": "📁", "mail": "📧", "conversation": "💬"
    }

    for idx, r in enumerate(results, 1):
        src = r.get("source", "?")
        icon = icon_by_source.get(src, "•")
        label = r.get("display_label") or "(sans titre)"
        meta = r.get("display_meta") or ""
        text = (r.get("text_content") or "").strip()
        if len(text) > 300:
            text = text[:297] + "..."

        # Header EVIDENT avec le vrai nom : aide Opus a ne pas halluciner
        # les noms propres (bug Legroux 21/04 : 'Christiane' inventee).
        header = f"{idx}. {icon} {label}"
        if meta:
            header += f"  [{meta}]"
        lines.append(header)
        # Afficher text_content seulement si different du label (sinon redondant)
        if text and text[:100] != label[:100]:
            lines.append(f"   {text}")

        # Scores pour diagnostic (debug)
        score_bits = []
        if r.get("rerank_score") is not None:
            score_bits.append(f"rerank={r['rerank_score']:.3f}")
        elif r.get("rrf_score") is not None:
            score_bits.append(f"rrf={r['rrf_score']:.4f}")
        if score_bits:
            lines.append(f"   ({' · '.join(score_bits)})")

        # Contexte graphe (uniquement pour Odoo aujourd'hui)
        related = r.get("related_nodes") or []
        if related:
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

        # Lien direct si Drive
        if src == "drive" and r.get("web_url"):
            lines.append(f"   🔗 {r['web_url']}")

        lines.append("")

    return "\n".join(lines)
