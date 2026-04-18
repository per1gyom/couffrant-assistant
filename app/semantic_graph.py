"""
Graphe sémantique typé — Couche 2 du modèle mémoire de Raya.

Voir docs/raya_memory_architecture.md pour le contexte architectural.

Stocke les entités (nœuds) et leurs relations (arêtes) avec typage explicite
et score de confiance. Permet la traversée multi-hop pour résoudre des cas
complexes type "Francine → conjoint → Jacques → contact_de → Les Amis du
Glandier → a_devis → S00456".

Types de nœuds supportés :
  Person, Company, Project, Product, Deal, Invoice, Payment,
  Event, Document, Mail, Ticket, Task, Lead

Types d'arêtes courantes :
  Explicites (source) : parent_of, child_of, contact_of, partner_of,
    has_line, has_invoice, has_payment, assigned_to, mentioned_in,
    part_of_deal, scheduled_for, delivered_to
  Implicites (LLM) : spouse_of, colleague_of, works_on, installed_on,
    replaces, follows_up, similar_to

Source des arêtes :
  'explicit_source' : arête directe depuis la source (parent_id Odoo, etc.)
  'llm_inferred'    : déduite par Claude après analyse croisée
  'manual'          : ajoutée manuellement par l'utilisateur

Confidence :
  1.0  : certitude absolue (arête explicite de la source)
  0.9+ : forte confiance (inférence LLM validée)
  0.7-0.9 : confiance modérée (inférence LLM à valider)
  < 0.7 : faible confiance (hypothèse, à confirmer)
"""

import logging
from typing import Any, Optional

from app.database import get_pg_conn

logger = logging.getLogger("raya.semantic_graph")


# ─── TYPES DE NŒUDS ET ARÊTES ─────────────────────────────────

NODE_TYPES = {
    "Person", "Company", "Project", "Product", "Deal", "Invoice",
    "Payment", "Event", "Document", "Mail", "Ticket", "Task", "Lead",
}

EDGE_TYPES_EXPLICIT = {
    "parent_of", "child_of", "contact_of", "partner_of",
    "has_line", "has_invoice", "has_payment", "has_task",
    "has_lead", "has_ticket",
    "assigned_to", "mentioned_in", "part_of_deal", "part_of_project",
    "scheduled_for", "delivered_to", "sent_by", "sent_to",
}

EDGE_TYPES_IMPLICIT = {
    "spouse_of", "colleague_of", "works_on", "installed_on",
    "replaces", "follows_up", "similar_to", "referred_by",
}

EDGE_TYPES = EDGE_TYPES_EXPLICIT | EDGE_TYPES_IMPLICIT

EDGE_SOURCES = {"explicit_source", "llm_inferred", "manual"}


def _validate_node_type(node_type: str) -> None:
    """Lève une erreur si le type de nœud n'est pas connu.
    Permet d'éviter les typos silencieuses."""
    if node_type not in NODE_TYPES:
        logger.warning("[Graph] Type de nœud inconnu : %s (types valides : %s)",
                       node_type, sorted(NODE_TYPES))


def _validate_edge_type(edge_type: str) -> None:
    """Lève un warning si le type d'arête n'est pas connu."""
    if edge_type not in EDGE_TYPES:
        logger.warning("[Graph] Type d'arête inconnu : %s", edge_type)


# ─── ÉCRITURE : NŒUDS ─────────────────────────────────────────

def add_node(
    tenant_id: str,
    node_type: str,
    node_key: str,
    node_label: Optional[str] = None,
    node_properties: Optional[dict] = None,
    source: str = "odoo",
    source_record_id: Optional[str] = None,
) -> Optional[int]:
    """Ajoute ou met à jour un nœud dans le graphe.
    Retourne l'ID du nœud (int) ou None en cas d'échec.

    node_key doit être unique dans le scope (tenant_id, node_type).
    Ex : pour Odoo partner #2501 → node_key = "odoo-partner-2501"
    """
    _validate_node_type(node_type)
    if not node_key:
        logger.warning("[Graph] add_node sans node_key (type=%s)", node_type)
        return None

    import json
    props_json = json.dumps(node_properties or {}, ensure_ascii=False,
                            default=str)
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            INSERT INTO semantic_graph_nodes
              (tenant_id, node_type, node_key, node_label, node_properties,
               source, source_record_id, updated_at)
            VALUES (%s, %s, %s, %s, %s::jsonb, %s, %s, NOW())
            ON CONFLICT (tenant_id, node_type, node_key) DO UPDATE SET
              node_label = EXCLUDED.node_label,
              node_properties = EXCLUDED.node_properties,
              source_record_id = EXCLUDED.source_record_id,
              updated_at = NOW()
            RETURNING id
        """, (tenant_id, node_type, node_key, node_label, props_json,
              source, source_record_id))
        node_id = c.fetchone()[0]
        conn.commit()
        return node_id
    except Exception as e:
        logger.warning("[Graph] add_node %s/%s échoué : %s",
                       node_type, node_key, str(e)[:200])
        return None
    finally:
        if conn: conn.close()


# ─── ÉCRITURE : ARÊTES ────────────────────────────────────────

def add_edge(
    tenant_id: str,
    edge_from: int,
    edge_to: int,
    edge_type: str,
    edge_confidence: float = 1.0,
    edge_source: str = "explicit_source",
    edge_metadata: Optional[dict] = None,
) -> Optional[int]:
    """Ajoute ou met à jour une arête typée entre deux nœuds.
    Retourne l'ID de l'arête ou None si échec.

    edge_from et edge_to sont les IDs internes des nœuds (résultat d'add_node).
    Si tu as les node_keys mais pas les IDs, utilise add_edge_by_keys().
    """
    _validate_edge_type(edge_type)
    if edge_source not in EDGE_SOURCES:
        logger.warning("[Graph] edge_source inconnu : %s", edge_source)
    if edge_from == edge_to:
        return None  # pas d'auto-arête

    import json
    meta_json = json.dumps(edge_metadata or {}, ensure_ascii=False,
                           default=str)
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            INSERT INTO semantic_graph_edges
              (tenant_id, edge_from, edge_to, edge_type,
               edge_confidence, edge_source, edge_metadata, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, NOW())
            ON CONFLICT (tenant_id, edge_from, edge_to, edge_type) DO UPDATE SET
              edge_confidence = GREATEST(semantic_graph_edges.edge_confidence,
                                         EXCLUDED.edge_confidence),
              edge_metadata = EXCLUDED.edge_metadata,
              updated_at = NOW()
            RETURNING id
        """, (tenant_id, edge_from, edge_to, edge_type,
              edge_confidence, edge_source, meta_json))
        edge_id = c.fetchone()[0]
        conn.commit()
        return edge_id
    except Exception as e:
        logger.warning("[Graph] add_edge %s->%s (%s) échoué : %s",
                       edge_from, edge_to, edge_type, str(e)[:200])
        return None
    finally:
        if conn: conn.close()


def add_edge_by_keys(
    tenant_id: str,
    from_type: str, from_key: str,
    to_type: str, to_key: str,
    edge_type: str,
    edge_confidence: float = 1.0,
    edge_source: str = "explicit_source",
    edge_metadata: Optional[dict] = None,
) -> Optional[int]:
    """Version ergonomique d'add_edge quand on a les (type, key) des nœuds
    mais pas leurs IDs. Résout les IDs en interne."""
    from_id = find_node_id(tenant_id, from_type, from_key)
    to_id = find_node_id(tenant_id, to_type, to_key)
    if not from_id or not to_id:
        logger.debug("[Graph] add_edge_by_keys: nœud(s) manquant(s) "
                     "%s/%s ou %s/%s", from_type, from_key, to_type, to_key)
        return None
    return add_edge(tenant_id, from_id, to_id, edge_type,
                    edge_confidence, edge_source, edge_metadata)


# ─── LECTURE : RÉSOLUTION ─────────────────────────────────────

def find_node_id(tenant_id: str, node_type: str, node_key: str) -> Optional[int]:
    """Retourne l'ID interne d'un nœud depuis son (type, key). None si absent."""
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            SELECT id FROM semantic_graph_nodes
            WHERE tenant_id = %s AND node_type = %s AND node_key = %s
        """, (tenant_id, node_type, node_key))
        row = c.fetchone()
        return row[0] if row else None
    except Exception as e:
        logger.warning("[Graph] find_node_id échoué : %s", str(e)[:100])
        return None
    finally:
        if conn: conn.close()


def get_node(tenant_id: str, node_id: int) -> Optional[dict]:
    """Retourne le dict complet d'un nœud depuis son ID interne."""
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            SELECT id, node_type, node_key, node_label, node_properties,
                   source, source_record_id, created_at, updated_at
            FROM semantic_graph_nodes
            WHERE tenant_id = %s AND id = %s
        """, (tenant_id, node_id))
        row = c.fetchone()
        if not row:
            return None
        return {
            "id": row[0], "node_type": row[1], "node_key": row[2],
            "node_label": row[3], "node_properties": row[4] or {},
            "source": row[5], "source_record_id": row[6],
            "created_at": str(row[7]), "updated_at": str(row[8]),
        }
    except Exception as e:
        logger.warning("[Graph] get_node échoué : %s", str(e)[:100])
        return None
    finally:
        if conn: conn.close()


def find_nodes_by_label(
    tenant_id: str,
    label_query: str,
    node_type: Optional[str] = None,
    limit: int = 10,
) -> list:
    """Recherche de nœuds par label (ilike). Utile pour résoudre
    'Francine Coullet' en un node_id avant traversée.

    Si node_type est fourni, filtre par type (ex: 'Person'). Sinon tous types.
    """
    if not label_query or not label_query.strip():
        return []
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        if node_type:
            c.execute("""
                SELECT id, node_type, node_key, node_label, source_record_id
                FROM semantic_graph_nodes
                WHERE tenant_id = %s AND node_type = %s
                  AND node_label ILIKE %s
                ORDER BY LENGTH(node_label) ASC
                LIMIT %s
            """, (tenant_id, node_type, f"%{label_query.strip()}%", limit))
        else:
            c.execute("""
                SELECT id, node_type, node_key, node_label, source_record_id
                FROM semantic_graph_nodes
                WHERE tenant_id = %s AND node_label ILIKE %s
                ORDER BY LENGTH(node_label) ASC
                LIMIT %s
            """, (tenant_id, f"%{label_query.strip()}%", limit))
        return [
            {"id": r[0], "node_type": r[1], "node_key": r[2],
             "node_label": r[3], "source_record_id": r[4]}
            for r in c.fetchall()
        ]
    except Exception as e:
        logger.warning("[Graph] find_nodes_by_label échoué : %s", str(e)[:100])
        return []
    finally:
        if conn: conn.close()


# ─── LECTURE : NAVIGATION DANS LE GRAPHE ──────────────────────

def get_neighbors(
    tenant_id: str,
    node_id: int,
    edge_types: Optional[list] = None,
    min_confidence: float = 0.5,
    direction: str = "both",
) -> list:
    """Retourne les nœuds voisins directs d'un nœud donné.

    Args:
        tenant_id: tenant
        node_id: nœud de départ
        edge_types: filtre par types d'arêtes (None = toutes)
        min_confidence: seuil de confiance minimum (exclut les liens faibles)
        direction: 'out' (arêtes sortantes), 'in' (entrantes), 'both'

    Retourne une liste de dicts :
      {neighbor_id, neighbor_type, neighbor_key, neighbor_label,
       edge_type, edge_direction ('out'/'in'), edge_confidence, edge_source}
    """
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        results = []

        # Filtre optionnel par types d'arêtes
        type_filter_sql = ""
        params_base = [tenant_id, node_id, min_confidence]
        if edge_types:
            type_filter_sql = " AND e.edge_type = ANY(%s)"
            params_base.append(edge_types)

        # Arêtes sortantes (node_id → neighbor)
        if direction in ("out", "both"):
            c.execute(f"""
                SELECT n.id, n.node_type, n.node_key, n.node_label,
                       e.edge_type, e.edge_confidence, e.edge_source,
                       e.edge_metadata
                FROM semantic_graph_edges e
                JOIN semantic_graph_nodes n ON n.id = e.edge_to
                WHERE e.tenant_id = %s AND e.edge_from = %s
                  AND e.edge_confidence >= %s {type_filter_sql}
                ORDER BY e.edge_confidence DESC
            """, params_base)
            for r in c.fetchall():
                results.append({
                    "neighbor_id": r[0], "neighbor_type": r[1],
                    "neighbor_key": r[2], "neighbor_label": r[3],
                    "edge_type": r[4], "edge_direction": "out",
                    "edge_confidence": r[5], "edge_source": r[6],
                    "edge_metadata": r[7] or {},
                })

        # Arêtes entrantes (neighbor → node_id)
        if direction in ("in", "both"):
            c.execute(f"""
                SELECT n.id, n.node_type, n.node_key, n.node_label,
                       e.edge_type, e.edge_confidence, e.edge_source,
                       e.edge_metadata
                FROM semantic_graph_edges e
                JOIN semantic_graph_nodes n ON n.id = e.edge_from
                WHERE e.tenant_id = %s AND e.edge_to = %s
                  AND e.edge_confidence >= %s {type_filter_sql}
                ORDER BY e.edge_confidence DESC
            """, params_base)
            for r in c.fetchall():
                results.append({
                    "neighbor_id": r[0], "neighbor_type": r[1],
                    "neighbor_key": r[2], "neighbor_label": r[3],
                    "edge_type": r[4], "edge_direction": "in",
                    "edge_confidence": r[5], "edge_source": r[6],
                    "edge_metadata": r[7] or {},
                })
        return results
    except Exception as e:
        logger.warning("[Graph] get_neighbors échoué : %s", str(e)[:150])
        return []
    finally:
        if conn: conn.close()


# ─── TRAVERSÉE MULTI-HOP ──────────────────────────────────────

def traverse(
    tenant_id: str,
    start_node_id: int,
    max_hops: int = 3,
    edge_types: Optional[list] = None,
    node_types: Optional[list] = None,
    min_confidence: float = 0.5,
    max_results: int = 100,
) -> dict:
    """Parcours BFS du graphe depuis un nœud de départ jusqu'à max_hops sauts.

    C'est LA fonction qui résout les cas complexes type :
    'Francine Coullet' → spouse_of → 'Jacques Coullet' → contact_of →
    'Les Amis du Glandier' → has_deals → [S00123, S00124]

    Args:
        tenant_id: tenant
        start_node_id: nœud de départ
        max_hops: profondeur max (1 = voisins directs, 2 = voisins de voisins...)
        edge_types: filtre types d'arêtes (None = toutes)
        node_types: ne retient que les nœuds de ces types (None = tous)
        min_confidence: seuil confiance
        max_results: garde-fou contre explosion combinatoire

    Retourne :
      {
        "start_node": {dict du nœud de départ},
        "visited": [list de {node_id, node_type, node_label, hops_distance,
                             path: [liste des arêtes empruntées pour y arriver]}],
        "truncated": bool (True si max_results atteint),
      }
    """
    start_node = get_node(tenant_id, start_node_id)
    if not start_node:
        return {"start_node": None, "visited": [], "truncated": False,
                "error": "start_node_id introuvable"}

    # BFS : file (node_id, distance, path)
    visited_ids = {start_node_id}
    queue = [(start_node_id, 0, [])]
    results = []
    truncated = False

    while queue:
        if len(results) >= max_results:
            truncated = True
            break
        current_id, distance, path = queue.pop(0)

        # Si c'est pas le nœud de départ et qu'il passe le filtre de type,
        # on l'ajoute aux résultats
        if current_id != start_node_id:
            node_info = get_node(tenant_id, current_id)
            if node_info and (
                not node_types or node_info["node_type"] in node_types
            ):
                results.append({
                    "node_id": current_id,
                    "node_type": node_info["node_type"],
                    "node_key": node_info["node_key"],
                    "node_label": node_info["node_label"],
                    "node_properties": node_info["node_properties"],
                    "source": node_info["source"],
                    "source_record_id": node_info["source_record_id"],
                    "hops_distance": distance,
                    "path": path,
                })

        # Continuer BFS si on n'a pas atteint max_hops
        if distance >= max_hops:
            continue

        neighbors = get_neighbors(
            tenant_id, current_id,
            edge_types=edge_types,
            min_confidence=min_confidence,
            direction="both",
        )
        for n in neighbors:
            nid = n["neighbor_id"]
            if nid in visited_ids:
                continue
            visited_ids.add(nid)
            step = {
                "from_id": current_id,
                "to_id": nid,
                "to_label": n["neighbor_label"],
                "edge_type": n["edge_type"],
                "edge_direction": n["edge_direction"],
                "edge_confidence": n["edge_confidence"],
            }
            queue.append((nid, distance + 1, path + [step]))

    return {
        "start_node": start_node,
        "visited": results,
        "truncated": truncated,
        "visited_count": len(results),
    }


# ─── HELPERS HAUT NIVEAU ──────────────────────────────────────

def get_context_around(
    tenant_id: str,
    label_query: str,
    node_type: Optional[str] = None,
    max_hops: int = 2,
    edge_types: Optional[list] = None,
    node_types: Optional[list] = None,
    min_confidence: float = 0.5,
) -> dict:
    """Point d'entrée idéal depuis Raya : 'donne-moi le contexte autour de X'.

    Combine find_nodes_by_label + traverse en une seule opération. Si plusieurs
    nœuds matchent le label (ex : 'Coullet' matche Francine + Jacques), on fait
    un traverse depuis chaque, puis on fusionne les résultats en dédupliquant.

    Retourne :
      {
        "matched_nodes": [list des nœuds trouvés par label],
        "context_nodes": [nœuds connectés dans le voisinage, dédupliqués],
        "total_unique_nodes": int,
      }
    """
    matched = find_nodes_by_label(tenant_id, label_query, node_type, limit=5)
    if not matched:
        return {"matched_nodes": [], "context_nodes": [],
                "total_unique_nodes": 0}

    seen_ids = {m["id"] for m in matched}
    context = []
    for m in matched:
        result = traverse(
            tenant_id, m["id"], max_hops=max_hops,
            edge_types=edge_types, node_types=node_types,
            min_confidence=min_confidence,
        )
        for node in result["visited"]:
            if node["node_id"] not in seen_ids:
                seen_ids.add(node["node_id"])
                context.append(node)
    # Tri : distance croissante, puis par type et label
    context.sort(key=lambda n: (n["hops_distance"], n["node_type"],
                                n["node_label"] or ""))
    return {
        "matched_nodes": matched,
        "context_nodes": context,
        "total_unique_nodes": len(matched) + len(context),
    }


# ─── MAINTENANCE ──────────────────────────────────────────────

def count_graph(tenant_id: str) -> dict:
    """Stats du graphe pour un tenant. Utile pour dashboard admin."""
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM semantic_graph_nodes WHERE tenant_id=%s",
                  (tenant_id,))
        n_nodes = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM semantic_graph_edges WHERE tenant_id=%s",
                  (tenant_id,))
        n_edges = c.fetchone()[0]
        c.execute("""
            SELECT node_type, COUNT(*) FROM semantic_graph_nodes
            WHERE tenant_id=%s GROUP BY node_type ORDER BY COUNT(*) DESC
        """, (tenant_id,))
        by_type = {r[0]: r[1] for r in c.fetchall()}
        c.execute("""
            SELECT edge_type, COUNT(*) FROM semantic_graph_edges
            WHERE tenant_id=%s GROUP BY edge_type ORDER BY COUNT(*) DESC
        """, (tenant_id,))
        by_edge_type = {r[0]: r[1] for r in c.fetchall()}
        return {
            "nodes_total": n_nodes,
            "edges_total": n_edges,
            "nodes_by_type": by_type,
            "edges_by_type": by_edge_type,
        }
    except Exception as e:
        logger.warning("[Graph] count_graph échoué : %s", str(e)[:100])
        return {"nodes_total": 0, "edges_total": 0,
                "nodes_by_type": {}, "edges_by_type": {}}
    finally:
        if conn: conn.close()
