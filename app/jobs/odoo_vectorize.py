"""
Vectorisation initiale Odoo + population du graphe sémantique typé.

Couche 2 (graphe) + Couche 3 (vectorisation) pour la source Odoo. Voir
docs/raya_memory_architecture.md pour la règle universelle.

Ce module fait 3 choses en un passage :

1. Populer le graphe semantic_graph avec les entités Odoo typées :
   Person (res.partner individuel), Company (res.partner is_company=True),
   Deal (sale.order), Invoice (account.move), Payment (account.payment),
   Lead (crm.lead), Event (calendar.event), Product (product.product),
   Ticket (helpdesk.ticket), Task (project.task).

2. Créer les arêtes explicites depuis les relations natives Odoo :
   contact_of (partner → company via parent_id),
   partner_of (deal → partner),
   has_line (deal → product via sale.order.line),
   has_invoice (deal → invoice via invoice_origin),
   assigned_to (event → partner),
   etc.

3. Vectoriser tout le contenu textuel pertinent (notes, descriptions,
   commentaires) dans la table odoo_semantic_content avec :
   - embedding OpenAI text-embedding-3-small (1536 dims)
   - content_tsv tsvector français (BM25)

Performance : traitement en batch, embedding groupés par 50, transactions
par modèle Odoo pour éviter les timeouts PostgreSQL.
"""

import logging
from typing import Any, Optional

logger = logging.getLogger("raya.odoo_vectorize")

DEFAULT_TENANT = "couffrant_solar"


def _count_odoo_records(model: str, domain: Optional[list] = None) -> Optional[int]:
    """Retourne le nombre total de records Odoo pour un modele et un domain,
    via search_count (leger, O(1) cote Odoo). Utilise pour detecter proactivement
    les cas ou la limite de fetch est approchee ou depassee.

    Retourne None en cas d'erreur (pas bloquant, la vectorisation continue)."""
    try:
        from app.connectors.odoo_connector import odoo_call
        count = odoo_call(
            model=model, method="search_count",
            args=[domain or []],
        )
        return int(count) if count is not None else None
    except Exception as e:
        logger.debug("[Vectorize] count %s échoué : %s", model, str(e)[:100])
        return None


# ─── STOCKAGE D'UN CONTENU SÉMANTIQUE ─────────────────────────

def _store_semantic_content(
    tenant_id: str,
    source_model: str,
    source_record_id: str,
    content_type: str,
    text_content: str,
    embedding: Optional[list],
    related_partner_id: Optional[str] = None,
    metadata: Optional[dict] = None,
    odoo_write_date: Optional[str] = None,
) -> bool:
    """Insère ou met à jour une entrée dans odoo_semantic_content.
    Calcule aussi le tsvector français pour recherche sparse.

    Retourne True si succès, False sinon."""
    from app.database import get_pg_conn
    import json

    if not text_content or not text_content.strip():
        return False

    meta_json = json.dumps(metadata or {}, ensure_ascii=False, default=str)
    vec_str = None
    if embedding is not None:
        vec_str = "[" + ",".join(str(x) for x in embedding) + "]"

    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            INSERT INTO odoo_semantic_content
              (tenant_id, source_model, source_record_id, content_type,
               text_content, embedding, content_tsv,
               related_partner_id, metadata, odoo_write_date, updated_at)
            VALUES (%s, %s, %s, %s, %s,
                    %s::vector, to_tsvector('french', %s),
                    %s, %s::jsonb, %s, NOW())
            ON CONFLICT (tenant_id, source_model, source_record_id, content_type)
            DO UPDATE SET
              text_content = EXCLUDED.text_content,
              embedding = EXCLUDED.embedding,
              content_tsv = EXCLUDED.content_tsv,
              related_partner_id = EXCLUDED.related_partner_id,
              metadata = EXCLUDED.metadata,
              odoo_write_date = EXCLUDED.odoo_write_date,
              updated_at = NOW()
        """, (tenant_id, source_model, str(source_record_id), content_type,
              text_content[:8000],
              vec_str, text_content[:8000],
              str(related_partner_id) if related_partner_id else None,
              meta_json, odoo_write_date))
        conn.commit()
        return True
    except Exception as e:
        logger.warning("[Vectorize] _store %s/%s/%s échoué : %s",
                       source_model, source_record_id, content_type, str(e)[:150])
        return False
    finally:
        if conn: conn.close()


# ─── VECTORISATION PAR MODÈLE ODOO ────────────────────────────

def vectorize_partners(tenant_id: str = DEFAULT_TENANT, limit: int = 5000) -> dict:
    """Vectorise res.partner : nom + commentaire + adresse comme texte
    sémantique. Crée les nœuds Person/Company dans le graphe.
    Arête contact_of créée entre enfant et parent_id.
    """
    from app.connectors.odoo_connector import odoo_call
    from app.embedding import embed_batch
    from app.semantic_graph import add_node, add_edge_by_keys

    stats = {"fetched": 0, "graph_nodes": 0, "graph_edges": 0,
             "vectorized": 0, "errors": 0}

    try:
        partners = odoo_call(
            model="res.partner", method="search_read",
            kwargs={
                "domain": [["active", "=", True]],
                "fields": ["id", "name", "comment", "email", "phone",
                           "mobile", "street", "city", "zip", "is_company",
                           "parent_id", "customer_rank", "supplier_rank",
                           "write_date"],
                "limit": limit,
            },
        )
    except Exception as e:
        stats["errors"] += 1
        logger.warning("[Vectorize] Fetch res.partner échoué : %s", str(e)[:150])
        return stats

    stats["fetched"] = len(partners or [])

    # Surveillance proactive : compte total + check limite
    total_in_odoo = _count_odoo_records("res.partner", [["active", "=", True]])
    stats["total_in_source"] = total_in_odoo
    from app.system_alerts import check_fetch_limit
    check_fetch_limit(
        tenant_id=tenant_id, component="vectorize_partners",
        fetched_count=stats["fetched"], limit_configured=limit,
        total_in_source=total_in_odoo,
    )

    # 1. Créer les nœuds dans le graphe (pas besoin d'embedding pour ça)
    texts_to_embed = []
    entries_to_embed = []
    for p in (partners or []):
        pid = p["id"]
        is_co = bool(p.get("is_company"))
        node_type = "Company" if is_co else "Person"
        node_key = f"odoo-partner-{pid}"
        node_label = p.get("name", "") or f"Partner #{pid}"
        props = {
            "email": p.get("email"),
            "phone": p.get("phone") or p.get("mobile"),
            "city": p.get("city"),
            "zip": p.get("zip"),
            "customer_rank": p.get("customer_rank", 0),
            "supplier_rank": p.get("supplier_rank", 0),
        }
        if add_node(tenant_id, node_type, node_key, node_label, props,
                    source="odoo", source_record_id=str(pid)):
            stats["graph_nodes"] += 1

        # Arête contact_of si parent_id existe (contact d'une entreprise)
        parent = p.get("parent_id")
        if parent and isinstance(parent, list) and len(parent) >= 1:
            parent_pid = parent[0]
            # Le parent peut être soit Company soit Person ; on essaie
            # Company en premier (plus courant), puis Person en fallback.
            for parent_type in ("Company", "Person"):
                edge_id = add_edge_by_keys(
                    tenant_id,
                    from_type=node_type, from_key=node_key,
                    to_type=parent_type, to_key=f"odoo-partner-{parent_pid}",
                    edge_type="contact_of",
                    edge_confidence=1.0,
                    edge_source="explicit_source",
                    edge_metadata={"via": "parent_id"},
                )
                if edge_id:
                    stats["graph_edges"] += 1
                    break

        # Préparer le texte à vectoriser (concaténation sémantique utile)
        text_bits = [node_label]
        if p.get("comment"): text_bits.append(p["comment"])
        if p.get("city"): text_bits.append(f"à {p['city']}")
        if is_co: text_bits.append("(entreprise)")
        text = " — ".join([b for b in text_bits if b and str(b).strip()])

        if text.strip():
            texts_to_embed.append(text[:2000])
            entries_to_embed.append({
                "source_record_id": str(pid), "text": text,
                "write_date": p.get("write_date"),
                "related_partner_id": str(pid),
            })

    # 2. Batch embedding (50 par 50 pour ne pas saturer l'API)
    for i in range(0, len(texts_to_embed), 50):
        batch_texts = texts_to_embed[i:i + 50]
        batch_entries = entries_to_embed[i:i + 50]
        embeddings = embed_batch(batch_texts)
        for entry, emb in zip(batch_entries, embeddings):
            if _store_semantic_content(
                tenant_id, "res.partner", entry["source_record_id"],
                "partner_summary", entry["text"], emb,
                related_partner_id=entry["related_partner_id"],
                odoo_write_date=entry.get("write_date"),
            ):
                stats["vectorized"] += 1

    logger.info("[Vectorize] res.partner : %d fetched, %d nodes, %d edges, %d vectorized",
                stats["fetched"], stats["graph_nodes"], stats["graph_edges"],
                stats["vectorized"])
    return stats


def vectorize_sale_orders(tenant_id: str = DEFAULT_TENANT, limit: int = 2000) -> dict:
    """Vectorise sale.order : note + lignes de produits. Crée les nœuds Deal
    et les arêtes partner_of (deal → partner) + has_line (deal → product).
    Permet de retrouver 'devis avec onduleur SE100K' même si le nom du
    client ne le mentionne pas."""
    from app.connectors.odoo_connector import odoo_call
    from app.embedding import embed_batch
    from app.semantic_graph import add_node, add_edge_by_keys

    stats = {"fetched": 0, "graph_nodes": 0, "graph_edges": 0,
             "vectorized": 0, "product_nodes": 0, "errors": 0}

    try:
        orders = odoo_call(
            model="sale.order", method="search_read",
            kwargs={
                "domain": [],
                "fields": ["id", "name", "state", "amount_total", "partner_id",
                           "date_order", "note", "order_line", "write_date"],
                "limit": limit,
            },
        )
    except Exception as e:
        stats["errors"] += 1
        logger.warning("[Vectorize] Fetch sale.order échoué : %s", str(e)[:150])
        return stats

    stats["fetched"] = len(orders or [])
    # Surveillance limite
    total_in_odoo = _count_odoo_records("sale.order", [])
    stats["total_in_source"] = total_in_odoo
    from app.system_alerts import check_fetch_limit
    check_fetch_limit(
        tenant_id=tenant_id, component="vectorize_sale_orders",
        fetched_count=stats["fetched"], limit_configured=limit,
        total_in_source=total_in_odoo,
    )
    texts_to_embed = []
    entries_to_embed = []

    for o in (orders or []):
        oid = o["id"]
        node_key = f"odoo-order-{oid}"
        node_label = o.get("name", "") or f"Order #{oid}"
        state = o.get("state", "")
        partner = o.get("partner_id")
        partner_id = partner[0] if isinstance(partner, list) and partner else None
        partner_name = partner[1] if isinstance(partner, list) and len(partner) > 1 else ""

        props = {
            "state": state, "amount_total": o.get("amount_total", 0),
            "date_order": str(o.get("date_order") or "")[:10],
            "partner_name": partner_name,
        }
        if add_node(tenant_id, "Deal", node_key, node_label, props,
                    source="odoo", source_record_id=str(oid)):
            stats["graph_nodes"] += 1

        # Arête Deal → Partner (partner_of)
        if partner_id:
            for ptype in ("Company", "Person"):
                if add_edge_by_keys(
                    tenant_id,
                    from_type="Deal", from_key=node_key,
                    to_type=ptype, to_key=f"odoo-partner-{partner_id}",
                    edge_type="partner_of",
                    edge_confidence=1.0,
                    edge_source="explicit_source",
                    edge_metadata={"partner_name": partner_name},
                ):
                    stats["graph_edges"] += 1
                    break


        # Récupérer les lignes de commande et créer les arêtes has_line
        # vers les produits (ET vectoriser les noms de produits pour recherche).
        line_ids = o.get("order_line") or []
        lines_text_parts = []
        if line_ids:
            try:
                lines = odoo_call(
                    model="sale.order.line", method="search_read",
                    kwargs={
                        "domain": [["id", "in", line_ids]],
                        "fields": ["id", "name", "product_id", "product_uom_qty",
                                   "price_subtotal"],
                    },
                )
                for ln in (lines or []):
                    prod = ln.get("product_id")
                    prod_id = prod[0] if isinstance(prod, list) and prod else None
                    prod_name = prod[1] if isinstance(prod, list) and len(prod) > 1 else ""
                    line_name = ln.get("name", "")
                    qty = ln.get("product_uom_qty", 0)
                    subtotal = ln.get("price_subtotal", 0)
                    lines_text_parts.append(
                        f"{qty} × {prod_name or line_name} ({subtotal:.0f}€)"
                    )
                    # Créer un nœud Product si absent
                    if prod_id:
                        prod_key = f"odoo-product-{prod_id}"
                        if add_node(tenant_id, "Product", prod_key, prod_name or line_name,
                                    {"product_ref": line_name}, source="odoo",
                                    source_record_id=str(prod_id)):
                            stats["product_nodes"] += 1
                        # Arête Deal → Product (has_line)
                        if add_edge_by_keys(
                            tenant_id,
                            from_type="Deal", from_key=node_key,
                            to_type="Product", to_key=prod_key,
                            edge_type="has_line",
                            edge_confidence=1.0,
                            edge_source="explicit_source",
                            edge_metadata={"qty": qty, "subtotal": subtotal,
                                           "line_desc": line_name[:200]},
                        ):
                            stats["graph_edges"] += 1
            except Exception as e:
                logger.debug("[Vectorize] Lignes order %s : %s", oid, str(e)[:100])

        # Construire le texte sémantique global du devis
        text_bits = [node_label]
        if partner_name: text_bits.append(f"pour {partner_name}")
        if o.get("note"): text_bits.append(o["note"])
        if lines_text_parts:
            text_bits.append("Contenu : " + " ; ".join(lines_text_parts[:20]))
        text_bits.append(f"(état : {state})")
        text = " — ".join([b for b in text_bits if b and str(b).strip()])

        if text.strip():
            texts_to_embed.append(text[:4000])
            entries_to_embed.append({
                "source_record_id": str(oid), "text": text,
                "write_date": o.get("write_date"),
                "related_partner_id": str(partner_id) if partner_id else None,
            })


    # Batch embeddings
    for i in range(0, len(texts_to_embed), 50):
        batch_texts = texts_to_embed[i:i + 50]
        batch_entries = entries_to_embed[i:i + 50]
        embeddings = embed_batch(batch_texts)
        for entry, emb in zip(batch_entries, embeddings):
            if _store_semantic_content(
                tenant_id, "sale.order", entry["source_record_id"],
                "order_full", entry["text"], emb,
                related_partner_id=entry.get("related_partner_id"),
                odoo_write_date=entry.get("write_date"),
            ):
                stats["vectorized"] += 1

    logger.info("[Vectorize] sale.order : %d fetched, %d deals, %d products, %d edges, %d vectorized",
                stats["fetched"], stats["graph_nodes"], stats["product_nodes"],
                stats["graph_edges"], stats["vectorized"])
    return stats


def vectorize_leads(tenant_id: str = DEFAULT_TENANT, limit: int = 1000) -> dict:
    """Vectorise crm.lead : nom + description. Crée les nœuds Lead et arête
    partner_of vers le contact associé."""
    from app.connectors.odoo_connector import odoo_call
    from app.embedding import embed_batch
    from app.semantic_graph import add_node, add_edge_by_keys

    stats = {"fetched": 0, "graph_nodes": 0, "graph_edges": 0,
             "vectorized": 0, "errors": 0}

    try:
        leads = odoo_call(
            model="crm.lead", method="search_read",
            kwargs={
                "domain": [["active", "=", True]],
                "fields": ["id", "name", "description", "partner_id",
                           "stage_id", "expected_revenue", "probability",
                           "user_id", "write_date"],
                "limit": limit,
            },
        )
    except Exception as e:
        stats["errors"] += 1
        logger.warning("[Vectorize] Fetch crm.lead échoué : %s", str(e)[:150])
        return stats

    stats["fetched"] = len(leads or [])
    # Surveillance limite
    total_in_odoo = _count_odoo_records("crm.lead", [["active", "=", True]])
    stats["total_in_source"] = total_in_odoo
    from app.system_alerts import check_fetch_limit
    check_fetch_limit(
        tenant_id=tenant_id, component="vectorize_leads",
        fetched_count=stats["fetched"], limit_configured=limit,
        total_in_source=total_in_odoo,
    )
    texts = []
    entries = []

    for lead in (leads or []):
        lid = lead["id"]
        node_key = f"odoo-lead-{lid}"
        node_label = lead.get("name", "") or f"Lead #{lid}"
        partner = lead.get("partner_id")
        partner_id = partner[0] if isinstance(partner, list) and partner else None
        partner_name = partner[1] if isinstance(partner, list) and len(partner) > 1 else ""
        stage = lead.get("stage_id")
        stage_name = stage[1] if isinstance(stage, list) and len(stage) > 1 else ""
        props = {
            "stage": stage_name, "revenue": lead.get("expected_revenue", 0),
            "probability": lead.get("probability", 0),
            "partner_name": partner_name,
        }
        if add_node(tenant_id, "Lead", node_key, node_label, props,
                    source="odoo", source_record_id=str(lid)):
            stats["graph_nodes"] += 1
        if partner_id:
            for ptype in ("Company", "Person"):
                if add_edge_by_keys(
                    tenant_id, from_type="Lead", from_key=node_key,
                    to_type=ptype, to_key=f"odoo-partner-{partner_id}",
                    edge_type="partner_of", edge_confidence=1.0,
                    edge_source="explicit_source",
                ):
                    stats["graph_edges"] += 1
                    break

        text_bits = [node_label]
        if partner_name: text_bits.append(f"— {partner_name}")
        if lead.get("description"): text_bits.append(lead["description"][:2000])
        if stage_name: text_bits.append(f"(stade : {stage_name})")
        text = " ".join([b for b in text_bits if b and str(b).strip()])

        if text.strip():
            texts.append(text[:3000])
            entries.append({"source_record_id": str(lid), "text": text,
                            "write_date": lead.get("write_date"),
                            "related_partner_id": str(partner_id) if partner_id else None})

    # Embeddings batch
    for i in range(0, len(texts), 50):
        batch_texts = texts[i:i + 50]
        batch_entries = entries[i:i + 50]
        embeddings = embed_batch(batch_texts)
        for entry, emb in zip(batch_entries, embeddings):
            if _store_semantic_content(
                tenant_id, "crm.lead", entry["source_record_id"],
                "lead_full", entry["text"], emb,
                related_partner_id=entry.get("related_partner_id"),
                odoo_write_date=entry.get("write_date"),
            ):
                stats["vectorized"] += 1

    logger.info("[Vectorize] crm.lead : %d fetched, %d nodes, %d edges, %d vectorized",
                stats["fetched"], stats["graph_nodes"], stats["graph_edges"], stats["vectorized"])
    return stats


def vectorize_events(tenant_id: str = DEFAULT_TENANT, limit: int = 1000) -> dict:
    """Vectorise calendar.event : nom + description (commentaires RDV).
    Crée nœuds Event et arêtes scheduled_for vers les partners/attendees.

    CRITIQUE pour le cas d usage Guillaume : les commentaires de RDV
    contiennent souvent des actions à faire. Vectoriser ça permet à Raya
    de retrouver 'le RDV où on avait parlé du kit de fixation renforcé'."""
    from app.connectors.odoo_connector import odoo_call
    from app.embedding import embed_batch
    from app.semantic_graph import add_node, add_edge_by_keys

    stats = {"fetched": 0, "graph_nodes": 0, "graph_edges": 0,
             "vectorized": 0, "errors": 0}

    try:
        events = odoo_call(
            model="calendar.event", method="search_read",
            kwargs={
                "domain": [],
                "fields": ["id", "name", "description", "start", "stop",
                           "partner_ids", "user_id", "write_date"],
                "limit": limit, "order": "start DESC",
            },
        )
    except Exception as e:
        stats["errors"] += 1
        logger.warning("[Vectorize] Fetch calendar.event échoué : %s", str(e)[:150])
        return stats

    stats["fetched"] = len(events or [])
    # Surveillance limite
    total_in_odoo = _count_odoo_records("calendar.event", [])
    stats["total_in_source"] = total_in_odoo
    from app.system_alerts import check_fetch_limit
    check_fetch_limit(
        tenant_id=tenant_id, component="vectorize_events",
        fetched_count=stats["fetched"], limit_configured=limit,
        total_in_source=total_in_odoo,
    )
    texts = []
    entries = []

    for ev in (events or []):
        eid = ev["id"]
        node_key = f"odoo-event-{eid}"
        node_label = ev.get("name", "") or f"Event #{eid}"
        start = str(ev.get("start") or "")
        stop = str(ev.get("stop") or "")
        props = {"start": start, "stop": stop,
                 "user": (ev.get("user_id") or [None, None])[1] if isinstance(ev.get("user_id"), list) else None}
        if add_node(tenant_id, "Event", node_key, node_label, props,
                    source="odoo", source_record_id=str(eid)):
            stats["graph_nodes"] += 1

        # Arêtes scheduled_for vers chaque participant
        partner_ids = ev.get("partner_ids") or []
        primary_partner = None
        for pid in partner_ids:
            if not isinstance(pid, int): continue
            for ptype in ("Person", "Company"):
                if add_edge_by_keys(
                    tenant_id, from_type="Event", from_key=node_key,
                    to_type=ptype, to_key=f"odoo-partner-{pid}",
                    edge_type="scheduled_for", edge_confidence=1.0,
                    edge_source="explicit_source",
                ):
                    stats["graph_edges"] += 1
                    if primary_partner is None:
                        primary_partner = pid
                    break

        # Texte sémantique (le + important : description avec commentaires)
        text_bits = [node_label]
        if start: text_bits.append(f"le {start[:16]}")
        if ev.get("description"):
            # Nettoyer le HTML basique
            desc = ev["description"]
            import re
            desc_clean = re.sub(r"<[^>]+>", " ", desc)
            desc_clean = re.sub(r"\s+", " ", desc_clean).strip()
            if desc_clean:
                text_bits.append(desc_clean[:2000])
        text = " — ".join([b for b in text_bits if b and str(b).strip()])

        if text.strip():
            texts.append(text[:3000])
            entries.append({
                "source_record_id": str(eid), "text": text,
                "write_date": ev.get("write_date"),
                "related_partner_id": str(primary_partner) if primary_partner else None,
            })

    for i in range(0, len(texts), 50):
        embeddings = embed_batch(texts[i:i + 50])
        for entry, emb in zip(entries[i:i + 50], embeddings):
            if _store_semantic_content(
                tenant_id, "calendar.event", entry["source_record_id"],
                "event_full", entry["text"], emb,
                related_partner_id=entry.get("related_partner_id"),
                odoo_write_date=entry.get("write_date"),
            ):
                stats["vectorized"] += 1

    logger.info("[Vectorize] calendar.event : %d fetched, %d nodes, %d edges, %d vectorized",
                stats["fetched"], stats["graph_nodes"], stats["graph_edges"], stats["vectorized"])
    return stats


# ─── ORCHESTRATEUR ────────────────────────────────────────────

def vectorize_all(tenant_id: str = DEFAULT_TENANT) -> dict:
    """Lance la vectorisation complète Odoo : partners + orders + leads + events.

    C est le point d entree pour l initialisation (bouton admin 'Vectoriser Odoo')
    et pour le job de sync incremental nocturne (avec un filtre write_date que
    chaque fonction peut gerer plus tard).

    Retourne un dict agregeant les stats de chaque modele pour affichage admin.
    """
    from app.embedding import is_available

    results = {"tenant_id": tenant_id, "total_duration_sec": 0}

    if not is_available():
        logger.warning("[Vectorize] OPENAI_API_KEY absent — vectorisation "
                       "désactivée. Graphe uniquement.")
        results["warning"] = "Embeddings désactivés (OPENAI_API_KEY manquant)"

    import time
    t0 = time.time()

    logger.info("[Vectorize] === Démarrage vectorisation complète Odoo (tenant=%s) ===",
                tenant_id)

    # Ordre important : partners d abord (necessaires comme cible d aretes
    # pour les autres), puis orders, leads, events.
    results["partners"] = vectorize_partners(tenant_id)
    results["sale_orders"] = vectorize_sale_orders(tenant_id)
    results["leads"] = vectorize_leads(tenant_id)
    results["events"] = vectorize_events(tenant_id)

    # Stats finales graphe
    from app.semantic_graph import count_graph
    results["graph_stats"] = count_graph(tenant_id)

    results["total_duration_sec"] = round(time.time() - t0, 1)
    logger.info("[Vectorize] === Terminé en %.1fs === graphe: %d noeuds, %d aretes",
                results["total_duration_sec"],
                results["graph_stats"]["nodes_total"],
                results["graph_stats"]["edges_total"])
    return results
