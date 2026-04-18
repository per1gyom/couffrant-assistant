"""
Webhook Odoo — reception en temps reel des modifications depuis base_automation.

Architecture : voir docs/raya_memory_architecture.md couche 2+3.

Odoo (base_automation.rule) -> Action serveur Python -> requests.post vers
cet endpoint -> Raya vectorise + met a jour le graphe en async.

SECURITE :
- Authentification par secret partage via header X-Webhook-Token
- Secret configure en variable d env : ODOO_WEBHOOK_SECRET
- Rate limit natif FastAPI (par IP, via middleware global)

IDEMPOTENCE :
- Les fonctions vectorize_* utilisent INSERT ON CONFLICT UPDATE
- Recevoir 2 fois le meme event ne cree pas de doublon, juste un re-update

ASYNC :
- Le endpoint retourne immediatement (202 Accepted) apres avoir declenche
  le traitement en background thread
- Evite de bloquer Odoo avec une response HTTP lente
"""

import os
import logging
import threading
from typing import Optional

from fastapi import APIRouter, Request, Header, HTTPException

logger = logging.getLogger("raya.webhook_odoo")
router = APIRouter()


def _get_expected_secret() -> str:
    """Le secret doit etre configure en variable d env ODOO_WEBHOOK_SECRET.
    Si absent, on desactive le webhook (renvoie None, endpoint refuse tout)."""
    return (os.getenv("ODOO_WEBHOOK_SECRET") or "").strip()


# ─── FONCTIONS DE TRAITEMENT PAR MODELE ───────────────────────

def _process_partner_change(record_id: int, tenant_id: str) -> None:
    """Traite un changement sur res.partner : fetch le record + vectorise +
    met a jour le graphe. Execute en thread background pour ne pas bloquer
    Odoo avec la latence HTTP."""
    try:
        from app.connectors.odoo_connector import odoo_call
        from app.embedding import embed
        from app.semantic_graph import add_node, add_edge_by_keys
        from app.jobs.odoo_vectorize import _store_semantic_content

        partners = odoo_call(
            model="res.partner", method="search_read",
            kwargs={
                "domain": [["id", "=", record_id]],
                "fields": ["id", "name", "comment", "email", "phone",
                           "mobile", "street", "city", "zip", "is_company",
                           "parent_id", "customer_rank", "supplier_rank",
                           "write_date"],
            },
        )
        if not partners:
            logger.info("[Webhook Odoo] partner %d inexistant (probablement supprime)", record_id)
            return
        p = partners[0]
        pid = p["id"]
        is_co = bool(p.get("is_company"))
        node_type = "Company" if is_co else "Person"
        node_key = f"odoo-partner-{pid}"
        node_label = p.get("name", "") or f"Partner #{pid}"
        props = {
            "email": p.get("email"), "phone": p.get("phone") or p.get("mobile"),
            "city": p.get("city"), "zip": p.get("zip"),
            "customer_rank": p.get("customer_rank", 0),
            "supplier_rank": p.get("supplier_rank", 0),
        }
        add_node(tenant_id, node_type, node_key, node_label, props,
                 source="odoo", source_record_id=str(pid))

        # Arete parent_id si present
        parent = p.get("parent_id")
        if parent and isinstance(parent, list):
            for ptype in ("Company", "Person"):
                if add_edge_by_keys(
                    tenant_id, from_type=node_type, from_key=node_key,
                    to_type=ptype, to_key=f"odoo-partner-{parent[0]}",
                    edge_type="contact_of", edge_confidence=1.0,
                    edge_source="explicit_source",
                ): break

        # Vectoriser
        text_bits = [node_label]
        if p.get("comment"): text_bits.append(p["comment"])
        if p.get("city"): text_bits.append(f"à {p['city']}")
        if is_co: text_bits.append("(entreprise)")
        text = " — ".join([b for b in text_bits if b and str(b).strip()])
        if text.strip():
            emb = embed(text[:2000])
            _store_semantic_content(
                tenant_id, "res.partner", str(pid), "partner_summary",
                text, emb, related_partner_id=str(pid),
                odoo_write_date=p.get("write_date"),
            )
        logger.info("[Webhook Odoo] partner %d (%s) mis a jour", pid, node_label[:50])
    except Exception as e:
        logger.error("[Webhook Odoo] _process_partner_change %s : %s",
                     record_id, str(e)[:300])


def _process_sale_order_change(record_id: int, tenant_id: str) -> None:
    """Traite un changement sur sale.order : fetch + lignes + vectorise +
    graphe (Deal + partner_of + has_line vers Products)."""
    try:
        from app.connectors.odoo_connector import odoo_call
        from app.embedding import embed
        from app.semantic_graph import add_node, add_edge_by_keys
        from app.jobs.odoo_vectorize import _store_semantic_content

        orders = odoo_call(
            model="sale.order", method="search_read",
            kwargs={
                "domain": [["id", "=", record_id]],
                "fields": ["id", "name", "state", "amount_total", "partner_id",
                           "date_order", "note", "order_line", "write_date"],
            },
        )
        if not orders:
            logger.info("[Webhook Odoo] sale.order %d inexistant", record_id)
            return
        o = orders[0]
        oid = o["id"]
        node_key = f"odoo-order-{oid}"
        node_label = o.get("name", "") or f"Order #{oid}"
        partner = o.get("partner_id")
        partner_id = partner[0] if isinstance(partner, list) and partner else None
        partner_name = partner[1] if isinstance(partner, list) and len(partner) > 1 else ""
        state = o.get("state", "")

        add_node(tenant_id, "Deal", node_key, node_label,
                 {"state": state, "amount_total": o.get("amount_total", 0),
                  "date_order": str(o.get("date_order") or "")[:10],
                  "partner_name": partner_name},
                 source="odoo", source_record_id=str(oid))

        if partner_id:
            for ptype in ("Company", "Person"):
                if add_edge_by_keys(
                    tenant_id, from_type="Deal", from_key=node_key,
                    to_type=ptype, to_key=f"odoo-partner-{partner_id}",
                    edge_type="partner_of", edge_confidence=1.0,
                    edge_source="explicit_source",
                ): break

        # Fetch lignes + has_line
        lines_text = []
        if o.get("order_line"):
            try:
                lines = odoo_call(
                    model="sale.order.line", method="search_read",
                    kwargs={"domain": [["id", "in", o["order_line"]]],
                            "fields": ["id", "name", "product_id",
                                       "product_uom_qty", "price_subtotal"]},
                )
                for ln in (lines or []):
                    prod = ln.get("product_id")
                    prod_id = prod[0] if isinstance(prod, list) and prod else None
                    prod_name = prod[1] if isinstance(prod, list) and len(prod) > 1 else ""
                    qty = ln.get("product_uom_qty", 0)
                    subtotal = ln.get("price_subtotal", 0)
                    lines_text.append(f"{qty} × {prod_name or ln.get('name', '')} ({subtotal:.0f}€)")
                    if prod_id:
                        prod_key = f"odoo-product-{prod_id}"
                        add_node(tenant_id, "Product", prod_key,
                                 prod_name or ln.get("name", ""),
                                 {"product_ref": ln.get("name", "")},
                                 source="odoo", source_record_id=str(prod_id))
                        add_edge_by_keys(
                            tenant_id, from_type="Deal", from_key=node_key,
                            to_type="Product", to_key=prod_key,
                            edge_type="has_line", edge_confidence=1.0,
                            edge_source="explicit_source",
                            edge_metadata={"qty": qty, "subtotal": subtotal,
                                           "line_desc": ln.get("name", "")[:200]},
                        )
            except Exception as e:
                logger.debug("[Webhook Odoo] lignes order %s : %s", oid, str(e)[:100])

        # Texte semantique
        text_bits = [node_label]
        if partner_name: text_bits.append(f"pour {partner_name}")
        if o.get("note"): text_bits.append(o["note"])
        if lines_text: text_bits.append("Contenu : " + " ; ".join(lines_text[:20]))
        text_bits.append(f"(état : {state})")
        text = " — ".join([b for b in text_bits if b and str(b).strip()])
        if text.strip():
            emb = embed(text[:4000])
            _store_semantic_content(
                tenant_id, "sale.order", str(oid), "order_full",
                text, emb,
                related_partner_id=str(partner_id) if partner_id else None,
                odoo_write_date=o.get("write_date"),
            )
        logger.info("[Webhook Odoo] sale.order %d (%s) mis a jour", oid, node_label[:50])
    except Exception as e:
        logger.error("[Webhook Odoo] _process_sale_order_change %s : %s",
                     record_id, str(e)[:300])


def _process_event_change(record_id: int, tenant_id: str) -> None:
    """Traite un changement sur calendar.event : fetch + vectorise (critique
    pour les commentaires de RDV) + graphe (Event + scheduled_for)."""
    try:
        from app.connectors.odoo_connector import odoo_call
        from app.embedding import embed
        from app.semantic_graph import add_node, add_edge_by_keys
        from app.jobs.odoo_vectorize import _store_semantic_content
        import re

        events = odoo_call(
            model="calendar.event", method="search_read",
            kwargs={
                "domain": [["id", "=", record_id]],
                "fields": ["id", "name", "description", "start", "stop",
                           "partner_ids", "user_id", "write_date"],
            },
        )
        if not events:
            logger.info("[Webhook Odoo] event %d inexistant", record_id)
            return
        ev = events[0]
        eid = ev["id"]
        node_key = f"odoo-event-{eid}"
        node_label = ev.get("name", "") or f"Event #{eid}"
        start = str(ev.get("start") or "")
        props = {"start": start, "stop": str(ev.get("stop") or "")}
        add_node(tenant_id, "Event", node_key, node_label, props,
                 source="odoo", source_record_id=str(eid))

        primary_partner = None
        for pid in (ev.get("partner_ids") or []):
            if not isinstance(pid, int): continue
            for ptype in ("Person", "Company"):
                if add_edge_by_keys(
                    tenant_id, from_type="Event", from_key=node_key,
                    to_type=ptype, to_key=f"odoo-partner-{pid}",
                    edge_type="scheduled_for", edge_confidence=1.0,
                    edge_source="explicit_source",
                ):
                    if primary_partner is None: primary_partner = pid
                    break

        text_bits = [node_label]
        if start: text_bits.append(f"le {start[:16]}")
        if ev.get("description"):
            desc = re.sub(r"<[^>]+>", " ", ev["description"])
            desc = re.sub(r"\s+", " ", desc).strip()
            if desc: text_bits.append(desc[:2000])
        text = " — ".join([b for b in text_bits if b and str(b).strip()])
        if text.strip():
            emb = embed(text[:3000])
            _store_semantic_content(
                tenant_id, "calendar.event", str(eid), "event_full",
                text, emb,
                related_partner_id=str(primary_partner) if primary_partner else None,
                odoo_write_date=ev.get("write_date"),
            )
        logger.info("[Webhook Odoo] event %d (%s) mis a jour", eid, node_label[:50])
    except Exception as e:
        logger.error("[Webhook Odoo] _process_event_change %s : %s",
                     record_id, str(e)[:300])


def _process_lead_change(record_id: int, tenant_id: str) -> None:
    """Traite un changement sur crm.lead."""
    try:
        from app.connectors.odoo_connector import odoo_call
        from app.embedding import embed
        from app.semantic_graph import add_node, add_edge_by_keys
        from app.jobs.odoo_vectorize import _store_semantic_content

        leads = odoo_call(
            model="crm.lead", method="search_read",
            kwargs={"domain": [["id", "=", record_id]],
                    "fields": ["id", "name", "description", "partner_id",
                               "stage_id", "expected_revenue", "probability",
                               "user_id", "write_date"]},
        )
        if not leads:
            logger.info("[Webhook Odoo] lead %d inexistant", record_id)
            return
        lead = leads[0]
        lid = lead["id"]
        node_key = f"odoo-lead-{lid}"
        node_label = lead.get("name", "") or f"Lead #{lid}"
        partner = lead.get("partner_id")
        partner_id = partner[0] if isinstance(partner, list) and partner else None
        partner_name = partner[1] if isinstance(partner, list) and len(partner) > 1 else ""
        stage = lead.get("stage_id")
        stage_name = stage[1] if isinstance(stage, list) and len(stage) > 1 else ""

        add_node(tenant_id, "Lead", node_key, node_label,
                 {"stage": stage_name,
                  "revenue": lead.get("expected_revenue", 0),
                  "probability": lead.get("probability", 0),
                  "partner_name": partner_name},
                 source="odoo", source_record_id=str(lid))
        if partner_id:
            for ptype in ("Company", "Person"):
                if add_edge_by_keys(
                    tenant_id, from_type="Lead", from_key=node_key,
                    to_type=ptype, to_key=f"odoo-partner-{partner_id}",
                    edge_type="partner_of", edge_confidence=1.0,
                    edge_source="explicit_source",
                ): break

        text_bits = [node_label]
        if partner_name: text_bits.append(f"— {partner_name}")
        if lead.get("description"): text_bits.append(lead["description"][:2000])
        if stage_name: text_bits.append(f"(stade : {stage_name})")
        text = " ".join([b for b in text_bits if b and str(b).strip()])
        if text.strip():
            emb = embed(text[:3000])
            _store_semantic_content(
                tenant_id, "crm.lead", str(lid), "lead_full",
                text, emb,
                related_partner_id=str(partner_id) if partner_id else None,
                odoo_write_date=lead.get("write_date"),
            )
        logger.info("[Webhook Odoo] lead %d mis a jour", lid)
    except Exception as e:
        logger.error("[Webhook Odoo] _process_lead_change %s : %s",
                     record_id, str(e)[:300])


# ─── ROUTING PAR MODELE ───────────────────────────────────────

MODEL_HANDLERS = {
    "res.partner": _process_partner_change,
    "sale.order": _process_sale_order_change,
    "calendar.event": _process_event_change,
    "crm.lead": _process_lead_change,
}


def _handle_in_background(model: str, record_id: int, tenant_id: str,
                          event: str) -> None:
    """Dispatch vers la bonne fonction de traitement, en thread background."""
    handler = MODEL_HANDLERS.get(model)
    if not handler:
        logger.warning("[Webhook Odoo] modele non gere : %s", model)
        return
    if event == "unlink":
        # Record supprime : on pourrait supprimer le noeud du graphe, mais
        # on garde pour traçabilite historique. Juste log pour l instant.
        logger.info("[Webhook Odoo] %s %d supprime (noeud garde en historique)",
                    model, record_id)
        return
    try:
        handler(record_id, tenant_id)
    except Exception as e:
        logger.error("[Webhook Odoo] handler %s echoue : %s", model, str(e)[:300])


# ─── ENDPOINT ─────────────────────────────────────────────────

@router.post("/webhooks/odoo/record-changed")
async def webhook_odoo_record_changed(
    request: Request,
    x_webhook_token: Optional[str] = Header(None),
):
    """Recoit une notification de changement Odoo depuis base_automation.

    Payload attendu (JSON) :
      {
        "model": "res.partner",     # modele Odoo
        "record_id": 2501,          # ID du record
        "event": "create|write|unlink",  # type d evenement
        "tenant_id": "couffrant_solar"   # optionnel, defaut
      }

    Header X-Webhook-Token requis et doit egaler ODOO_WEBHOOK_SECRET.

    Repond 202 Accepted immediatement, traitement en background thread.
    """
    expected = _get_expected_secret()
    if not expected:
        raise HTTPException(status_code=503,
                            detail="Webhook desactive (ODOO_WEBHOOK_SECRET non configure)")
    if not x_webhook_token or x_webhook_token != expected:
        logger.warning("[Webhook Odoo] appel refuse : token invalide ou absent")
        raise HTTPException(status_code=401, detail="Invalid webhook token")

    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Payload JSON invalide")

    model = payload.get("model", "").strip()
    record_id = payload.get("record_id")
    event = payload.get("event", "write").strip()
    tenant_id = (payload.get("tenant_id") or "couffrant_solar").strip()

    if not model or not isinstance(record_id, int):
        raise HTTPException(status_code=400,
                            detail="'model' et 'record_id' (int) requis")

    logger.info("[Webhook Odoo] recu %s/%s on %s (tenant=%s)",
                event, model, record_id, tenant_id)

    # Traitement async pour ne pas bloquer Odoo
    threading.Thread(
        target=_handle_in_background,
        args=(model, record_id, tenant_id, event),
        daemon=True,
    ).start()

    return {"status": "accepted", "model": model, "record_id": record_id,
            "event": event}


@router.get("/webhooks/odoo/health")
async def webhook_odoo_health():
    """Health check public pour que Odoo puisse verifier la dispo de Raya
    avant de tenter un POST. Pas d auth."""
    expected = _get_expected_secret()
    return {
        "status": "ok",
        "webhook_enabled": bool(expected),
        "supported_models": list(MODEL_HANDLERS.keys()),
    }
