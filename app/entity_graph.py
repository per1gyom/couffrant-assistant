"""
Graphe de relations cross-source.

Relie les entités (contacts, sociétés) aux ressources (factures, mails,
fichiers, messages Teams) à travers TOUTES les sources connectées.

Quand un mail arrive de "SARL DES MOINES", un seul lookup retourne :
  - facture impayée 81k€ (Odoo)
  - dernier échange Teams avec Arlène (Teams)
  - devis signé dans /Clients 2026/ (Drive)
  - 3 mails échangés cette semaine (Gmail)

Usage :
  link_entity(tenant, "contact", "sarl-des-moines", "SARL DES MOINES",
              "invoice", "FAC/2026/00063", "odoo", "81 000€ impayée",
              {"amount": 81000, "state": "not_paid"})
  ctx = get_entity_context("sarl-des-moines", tenant)
"""
import re
import json
from datetime import datetime
from app.database import get_pg_conn
from app.logging_config import get_logger

logger = get_logger("raya.graph")


# ─── NORMALISATION DES CLÉS ─────────────────────────────────────

def normalize_key(raw: str) -> str:
    """Normalise un nom ou email en clé d'entité stable."""
    if not raw:
        return ""
    key = raw.strip().lower()
    # Si c'est un email, garder tel quel
    if "@" in key:
        return key
    # Sinon, normaliser : retirer accents, ponctuation, espaces multiples
    key = re.sub(r'[^\w\s-]', '', key)
    key = re.sub(r'\s+', '-', key).strip('-')
    return key


def _extract_entity_keys(text: str) -> list[str]:
    """Extrait les clés d'entité possibles d'un texte (nom, email)."""
    keys = set()
    # Emails
    for email in re.findall(r'[\w.+-]+@[\w.-]+\.\w+', text):
        keys.add(normalize_key(email))
    # Mots capitalisés (noms propres, sociétés)
    for word in re.findall(r'[A-ZÀ-Ü][a-zà-ü]+(?:\s+[A-ZÀ-Ü][a-zà-ü]+)*', text):
        if len(word) > 2:
            keys.add(normalize_key(word))
    return list(keys)


# ─── ÉCRITURE : LIER UNE ENTITÉ À UNE RESSOURCE ────────────────

def link_entity(
    tenant_id: str,
    entity_type: str,    # 'contact', 'company', 'project'
    entity_key: str,     # clé normalisée
    entity_name: str,    # nom d'affichage
    resource_type: str,  # 'invoice', 'mail', 'file', 'teams_msg', 'calendar_event', 'order'
    resource_id: str,    # id dans le système source
    resource_source: str,# 'odoo', 'gmail', 'outlook', 'sharepoint', 'teams'
    resource_label: str, # description courte
    resource_data: dict = None,
) -> bool:
    """Ajoute ou met à jour un lien entité ↔ ressource."""
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            INSERT INTO entity_links
                (tenant_id, entity_type, entity_key, entity_name,
                 resource_type, resource_id, resource_source, resource_label,
                 resource_data, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, NOW())
            ON CONFLICT (tenant_id, entity_key, resource_source, resource_type, resource_id)
            DO UPDATE SET
                entity_name = EXCLUDED.entity_name,
                resource_label = EXCLUDED.resource_label,
                resource_data = EXCLUDED.resource_data,
                updated_at = NOW()
        """, (
            tenant_id, entity_type, normalize_key(entity_key), entity_name,
            resource_type, str(resource_id), resource_source, resource_label,
            json.dumps(resource_data or {}, ensure_ascii=False),
        ))
        conn.commit()
        return True
    except Exception as e:
        logger.warning("[Graph] link_entity échoué: %s", e)
        return False
    finally:
        if conn: conn.close()


# ─── LECTURE : CONTEXTE COMPLET D'UNE ENTITÉ ────────────────────

def get_entity_context(entity_key: str, tenant_id: str) -> dict:
    """
    Retourne tout le contexte cross-source d'une entité.
    Utilisé quand un mail arrive, quand l'utilisateur mentionne un contact, etc.

    Retourne :
    {
        "entity_key": "sarl-des-moines",
        "entity_name": "SARL DES MOINES",
        "links": [
            {"type": "invoice", "source": "odoo", "label": "FAC/2026/00063 — 81 000€ impayée", "data": {...}},
            {"type": "mail", "source": "gmail", "label": "Re: Retard livraison — 15/04", "data": {...}},
            ...
        ]
    }
    """
    key = normalize_key(entity_key)
    if not key:
        return {"entity_key": "", "entity_name": "", "links": []}
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            SELECT entity_name, resource_type, resource_id, resource_source,
                   resource_label, resource_data, updated_at
            FROM entity_links
            WHERE tenant_id = %s AND entity_key = %s
            ORDER BY updated_at DESC
            LIMIT 50
        """, (tenant_id, key))
        rows = c.fetchall()
        if not rows:
            return {"entity_key": key, "entity_name": "", "links": []}
        name = rows[0][0] or key
        links = []
        for r in rows:
            links.append({
                "type": r[1], "source": r[3], "id": r[2],
                "label": r[4] or "", "data": r[5] or {},
                "updated": str(r[6]) if r[6] else "",
            })
        return {"entity_key": key, "entity_name": name, "links": links}
    except Exception as e:
        logger.warning("[Graph] get_entity_context échoué: %s", e)
        return {"entity_key": key, "entity_name": "", "links": []}
    finally:
        if conn: conn.close()


def get_entity_context_text(entity_key: str, tenant_id: str) -> str:
    """Version texte du contexte, injectable dans le prompt."""
    ctx = get_entity_context(entity_key, tenant_id)
    if not ctx["links"]:
        return ""
    lines = [f"=== Contexte de {ctx['entity_name']} ==="]
    by_source = {}
    for lk in ctx["links"]:
        by_source.setdefault(lk["source"], []).append(lk)
    for source, items in by_source.items():
        lines.append(f"  [{source}]")
        for item in items[:10]:
            lines.append(f"    {item['type']}: {item['label']}")
    return "\n".join(lines)


# ─── PEUPLEMENT : ODOO → GRAPHE ────────────────────────────────

def populate_from_odoo(tenant_id: str) -> dict:
    """
    Peuple le graphe depuis Odoo : contacts ↔ factures, devis, projets.
    Appelé après discover_odoo ou périodiquement.
    """
    from app.connectors.odoo_connector import odoo_call
    stats = {"contacts": 0, "invoices": 0, "orders": 0, "errors": []}

    # 1. Contacts (res.partner) — l'entité de base
    try:
        partners = odoo_call(
            model="res.partner", method="search_read",
            kwargs={"domain": [], "fields": ["name", "email", "phone", "company_name"],
                    "limit": 500}
        )
        for p in (partners or []):
            key = normalize_key(p.get("email") or p.get("name", ""))
            if not key or len(key) < 3:
                continue
            link_entity(tenant_id, "contact", key, p.get("name", ""),
                       "contact", str(p["id"]), "odoo",
                       f"{p.get('name','')} — {p.get('email','')}",
                       {"phone": p.get("phone"), "company": p.get("company_name")})
            stats["contacts"] += 1
    except Exception as e:
        stats["errors"].append(f"contacts: {str(e)[:100]}")

    # 2. Factures (account.move) → liées au contact partner_id
    try:
        invoices = odoo_call(
            model="account.move", method="search_read",
            kwargs={"domain": [["move_type", "in", ["out_invoice", "out_refund"]]],
                    "fields": ["name", "partner_id", "amount_total", "payment_state", "invoice_date"],
                    "limit": 500}
        )
        for inv in (invoices or []):
            partner = inv.get("partner_id")
            if not partner or not isinstance(partner, list):
                continue
            partner_name = partner[1] if len(partner) > 1 else ""
            key = normalize_key(partner_name)
            if not key:
                continue
            state_label = {"paid": "payée", "not_paid": "impayée",
                          "partial": "partiel", "reversed": "annulée"
                          }.get(inv.get("payment_state", ""), inv.get("payment_state", ""))
            label = f"{inv.get('name','')} — {inv.get('amount_total',0):.0f}€ {state_label}"
            link_entity(tenant_id, "contact", key, partner_name,
                       "invoice", str(inv["id"]), "odoo", label,
                       {"amount": inv.get("amount_total"), "state": inv.get("payment_state"),
                        "date": str(inv.get("invoice_date", ""))})
            stats["invoices"] += 1
    except Exception as e:
        stats["errors"].append(f"factures: {str(e)[:100]}")

    # 3. Devis/Commandes (sale.order) → liées au contact partner_id
    try:
        orders = odoo_call(
            model="sale.order", method="search_read",
            kwargs={"domain": [], "fields": ["name", "partner_id", "amount_total", "state"],
                    "limit": 500}
        )
        for order in (orders or []):
            partner = order.get("partner_id")
            if not partner or not isinstance(partner, list):
                continue
            partner_name = partner[1] if len(partner) > 1 else ""
            key = normalize_key(partner_name)
            if not key:
                continue
            state_label = {"draft": "brouillon", "sent": "envoyé", "sale": "confirmé",
                          "cancel": "annulé"}.get(order.get("state", ""), order.get("state", ""))
            label = f"{order.get('name','')} — {order.get('amount_total',0):.0f}€ {state_label}"
            link_entity(tenant_id, "contact", key, partner_name,
                       "order", str(order["id"]), "odoo", label,
                       {"amount": order.get("amount_total"), "state": order.get("state")})
            stats["orders"] += 1
    except Exception as e:
        stats["errors"].append(f"devis: {str(e)[:100]}")

    logger.info("[Graph] Odoo → graphe : %d contacts, %d factures, %d devis, %d erreurs",
                stats["contacts"], stats["invoices"], stats["orders"], len(stats["errors"]))
    return stats


# ─── PEUPLEMENT : MAILS → GRAPHE ───────────────────────────────

def link_mail_to_graph(tenant_id: str, sender: str, sender_name: str,
                       subject: str, mail_id: str, source: str = "outlook"):
    """Lie un mail entrant au graphe. Appelé par le webhook mail."""
    key = normalize_key(sender)
    if not key or len(key) < 3:
        return
    link_entity(tenant_id, "contact", key, sender_name or sender,
               "mail", mail_id, source, subject[:100],
               {"sender": sender, "date": datetime.now().isoformat()})


def populate_from_mail_memory(tenant_id: str) -> int:
    """Peuple le graphe depuis les mails existants en base."""
    conn = None
    count = 0
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            SELECT DISTINCT sender, subject, id
            FROM mail_memory
            WHERE username IN (SELECT username FROM users WHERE tenant_id = %s)
            ORDER BY received_at DESC LIMIT 500
        """, (tenant_id,))
        for sender, subject, mid in c.fetchall():
            key = normalize_key(sender or "")
            if key and len(key) > 3:
                link_entity(tenant_id, "contact", key, sender or "",
                           "mail", str(mid), "outlook", (subject or "")[:100],
                           {"sender": sender})
                count += 1
    except Exception as e:
        logger.warning("[Graph] populate_from_mail_memory: %s", e)
    finally:
        if conn: conn.close()
    logger.info("[Graph] Mails → graphe : %d liens", count)
    return count

