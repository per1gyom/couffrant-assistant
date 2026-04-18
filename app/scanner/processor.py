"""
Processor de records — construit le texte composite, embedde, ecrit en DB.

Prend en entree :
- un record brut fetche depuis Odoo
- le manifest du modele (quels champs vectoriser, quelles aretes creer)
- les transversaux associes (messages, trackings, attachments, followers)

Produit en sortie (ecrit en DB) :
- 1 noeud dans semantic_graph_nodes
- N aretes dans semantic_graph_edges (depuis les many2one du manifest)
- 1 chunk dans odoo_semantic_content (si vectorisation activee)
- N chunks additionnels pour chaque mail.message vectorise
- Tracabilite dans semantic_graph_nodes (noeuds message) + aretes AUTHORED_BY

Idempotence garantie par INSERT ON CONFLICT UPDATE partout.
"""

import logging
import re
from typing import Optional

logger = logging.getLogger("raya.scanner.processor")


def build_composite_text(record: dict, manifest: dict,
                         model_name: str) -> str:
    """Construit un texte riche multi-champs pour embedding.

    Exemple pour sale.order :
      "Devis S01545 de [AZEM Societe]. Reference client: PROJ-2026-017.
       Note: 'Attente retour ENEDIS pour augmentation puissance'.
       Commercial: Arlene Desnoues."

    Cette concatenation structuree donne beaucoup plus de contexte a
    l embedding qu un simple nom seul, ce qui ameliore la pertinence
    des recherches semantiques.
    """
    parts = []
    vectorize_fields = manifest.get("vectorize_fields", [])
    name = record.get("display_name") or record.get("name") or f"#{record.get('id')}"
    parts.append(f"{model_name} {name}")
    for field in vectorize_fields:
        val = record.get(field)
        if not val:
            continue
        # Si la valeur est un many2one (tuple [id, "Nom"]), on prend le nom
        if isinstance(val, (list, tuple)) and len(val) == 2:
            val = val[1]
        # Si c est du HTML, on nettoie les balises
        if isinstance(val, str) and ("<" in val and ">" in val):
            val = _strip_html(val)
        val = str(val).strip()
        if val and val.lower() not in ("false", "none", "null"):
            parts.append(f"{field}: {val}")
    return ". ".join(parts)[:8000]


def _strip_html(html: str) -> str:
    """Nettoie le HTML pour n en garder que le texte lisible."""
    if not html:
        return ""
    # Supprime les balises
    text = re.sub(r"<[^>]+>", " ", html)
    # Supprime les entites HTML basiques
    text = (text.replace("&nbsp;", " ").replace("&amp;", "&")
            .replace("&lt;", "<").replace("&gt;", ">")
            .replace("&quot;", '"').replace("&apos;", "'"))
    # Normalise les espaces
    text = re.sub(r"\s+", " ", text).strip()
    return text


def extract_edges(record: dict, manifest: dict) -> list:
    """Extrait les aretes a creer depuis les champs many2one du manifest.

    Retourne une liste de tuples (edge_type, target_model, target_id).

    Exemple pour sale.order.line avec manifest :
      graph_edges: [
        {"field": "order_id", "type": "BELONGS_TO_ORDER"},
        {"field": "product_id", "type": "HAS_PRODUCT"},
      ]
    Et un record avec order_id=[42, "S01545"] et product_id=[99, "Module PV"]
    -> retourne [
         ("BELONGS_TO_ORDER", "sale.order", 42),
         ("HAS_PRODUCT", "product.product", 99),
       ]
    """
    edges = []
    for edge_def in manifest.get("graph_edges", []):
        field = edge_def.get("field")
        edge_type = edge_def.get("type")
        target_model = edge_def.get("target_model")
        val = record.get(field)
        if not val:
            continue
        # many2one : tuple (id, "nom")
        if isinstance(val, (list, tuple)) and len(val) == 2 and isinstance(val[0], int):
            edges.append((edge_type, target_model, val[0]))
        # one2many ou many2many : liste d ids
        elif isinstance(val, list) and all(isinstance(x, int) for x in val):
            for tid in val:
                edges.append((edge_type, target_model, tid))
    return edges


def extract_metadata(record: dict, manifest: dict) -> dict:
    """Extrait les champs metadata (dates, montants, etats) du manifest.

    Ces valeurs sont stockees en JSONB sur le noeud, pas vectorisees.
    Elles servent au filtrage et a l affichage mais pas a la recherche
    semantique.
    """
    meta = {}
    for field in manifest.get("metadata_fields", []):
        val = record.get(field)
        if val is None or val is False:
            continue
        # Normalisation des many2one en label lisible
        if isinstance(val, (list, tuple)) and len(val) == 2:
            meta[field] = val[1]
        elif hasattr(val, "isoformat"):
            meta[field] = val.isoformat()
        else:
            meta[field] = val
    return meta


def process_record(
    tenant_id: str,
    source: str,
    model_name: str,
    record: dict,
    manifest: dict,
    transversals: Optional[dict] = None,
) -> dict:
    """Traite UN record : texte composite + embedding + noeud + aretes + chunk.

    Fonction principale, appelee par l orchestrateur pour chaque record d un
    batch. Idempotente grace aux INSERT ON CONFLICT des sous-fonctions.

    Returns : {"node_id": int, "chunk_id": int | None, "edges_count": int}
    """
    from app.semantic_graph import add_node, add_edge

    record_id = record.get("id")
    if not record_id:
        return {"error": "record without id"}

    name = record.get("display_name") or record.get("name") or f"#{record_id}"
    metadata = extract_metadata(record, manifest)

    # 1. Upsert du noeud principal via add_node (idempotent ON CONFLICT)
    node_id = add_node(
        tenant_id=tenant_id,
        node_type=_model_to_node_type(model_name),
        node_key=f"{source}:{model_name}:{record_id}",
        node_label=str(name)[:500],
        node_properties=metadata,
        source=source,
        source_record_id=str(record_id),
    )

    # 2. Aretes depuis les many2one du manifest
    edges_count = 0
    for edge_type, target_model, target_id in extract_edges(record, manifest):
        if not target_model or not target_id:
            continue
        # Upsert d un noeud cible stub (sera enrichi quand son modele sera traite)
        target_node_id = add_node(
            tenant_id=tenant_id,
            node_type=_model_to_node_type(target_model),
            node_key=f"{source}:{target_model}:{target_id}",
            node_label=f"{target_model}#{target_id}",
            node_properties={},
            source=source,
            source_record_id=str(target_id),
        )
        if node_id and target_node_id:
            add_edge(tenant_id, node_id, target_node_id, edge_type)
            edges_count += 1

    # 3. Vectorisation (si au moins 1 champ dans vectorize_fields)
    chunk_id = None
    if manifest.get("vectorize_fields"):
        composite_text = build_composite_text(record, manifest, model_name)
        if composite_text.strip():
            chunk_id = _write_semantic_chunk(
                tenant_id, source, model_name, record_id,
                composite_text, metadata,
            )

    return {
        "node_id": node_id,
        "chunk_id": chunk_id,
        "edges_count": edges_count,
    }


# Mapping model Odoo -> node_type du graphe semantique
_MODEL_TO_NODE_TYPE = {
    "res.partner": "Person",
    "res.users": "Person",
    "crm.lead": "Lead",
    "sale.order": "Deal",
    "sale.order.line": "DealLine",
    "sale.order.template": "DealTemplate",
    "sale.order.template.line": "DealTemplateLine",
    "account.move": "Invoice",
    "account.move.line": "InvoiceLine",
    "account.payment": "Payment",
    "product.template": "Product",
    "product.product": "ProductVariant",
    "of.product.pack.lines": "KitComponent",
    "calendar.event": "Event",
    "of.planning.tour": "Tour",
    "of.planning.tour.line": "TourStop",
    "of.survey.answers": "SurveyAnswer",
    "mail.message": "Message",
    "ir.attachment": "Document",
    "hr.employee": "Employee",
    "of.image": "Image",
}


def _model_to_node_type(model_name: str) -> str:
    """Convertit un nom de modele Odoo en node_type du graphe semantique."""
    if model_name in _MODEL_TO_NODE_TYPE:
        return _MODEL_TO_NODE_TYPE[model_name]
    # Default : prend la partie apres le dernier point, capitalise
    return model_name.split(".")[-1].title().replace("_", "")


def _write_semantic_chunk(
    tenant_id: str, source: str, model_name: str,
    record_id: int, content: str, metadata: dict,
) -> Optional[int]:
    """Ecrit un chunk dans odoo_semantic_content avec embedding.

    Reutilise la logique existante du bloc 2 d hier (INSERT ON CONFLICT
    sur la cle composite). L embedding est fait par app.embedding.embed_text.
    """
    try:
        from app.database import get_pg_conn
        from app.embedding import embed
        import json
        embedding = embed(content)
        if embedding is None:
            logger.warning("[Processor] embedding None pour %s:%s — skip chunk",
                           model_name, record_id)
            return None
        # pgvector attend un format texte "[x,y,z]" et non une liste Python
        vec_str = "[" + ",".join(str(x) for x in embedding) + "]"
        with get_pg_conn() as conn:
            cur = conn.cursor()
            cur.execute(
                """INSERT INTO odoo_semantic_content
                   (tenant_id, source_model, source_record_id, content_type,
                    text_content, embedding, metadata, odoo_write_date,
                    updated_at)
                   VALUES (%s, %s, %s, 'record_summary', %s, %s::vector, %s, NOW(), NOW())
                   ON CONFLICT (tenant_id, source_model, source_record_id, content_type)
                   DO UPDATE SET text_content=EXCLUDED.text_content,
                                 embedding=EXCLUDED.embedding,
                                 metadata=EXCLUDED.metadata,
                                 odoo_write_date=EXCLUDED.odoo_write_date,
                                 updated_at=NOW(),
                                 deleted_at=NULL
                   RETURNING id""",
                (tenant_id, model_name, str(record_id),
                 content, vec_str, json.dumps(metadata)),
            )
            row = cur.fetchone()
            conn.commit()
            return row[0] if row else None
    except Exception as e:
        logger.error("[Processor] write_semantic_chunk %s:%s: %s",
                     model_name, record_id, str(e)[:200])
        return None
