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
    Peuple le graphe depuis Odoo : contacts ↔ factures, devis, leads, projets,
    tâches, planning, tickets SAV, paiements + équipe (res.users = collaborateurs
    internes).
    Appelé après discover_odoo ou périodiquement.

    Chaque bloc est dans un try/except indépendant : si un module Odoo n'est
    pas installé (ex: helpdesk, planning) ou qu'un appel échoue, les autres
    blocs continuent. L'erreur est consignée dans stats["errors"].
    """
    from app.connectors.odoo_connector import odoo_call
    stats = {
        "contacts": 0, "invoices": 0, "orders": 0, "team_members": 0,
        "leads": 0, "projects": 0, "tasks": 0,
        "planning_slots": 0, "tickets": 0, "payments": 0,
        "errors": [],
    }

    # 0. Équipe interne (res.users) — les collaborateurs qui apparaissent dans
    # les plannings d'intervention et sont assignés aux événements (user_id).
    # Sans ça, Raya hallucine la composition de l'équipe depuis l'historique chat.
    try:
        users = odoo_call(
            model="res.users", method="search_read",
            kwargs={"domain": [["active", "=", True], ["share", "=", False]],
                    "fields": ["name", "login", "email", "partner_id"],
                    "limit": 50}
        )
        for u in (users or []):
            key = normalize_key(u.get("login") or u.get("email") or u.get("name", ""))
            if not key or len(key) < 3:
                continue
            link_entity(tenant_id, "team_member", key, u.get("name", ""),
                       "team_member", str(u["id"]), "odoo",
                       f"{u.get('name','')} — {u.get('email') or u.get('login','')}",
                       {"login": u.get("login"), "email": u.get("email"),
                        "partner_id": u.get("partner_id")})
            stats["team_members"] += 1
    except Exception as e:
        stats["errors"].append(f"res.users: {str(e)[:100]}")

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

    # 4. CRM Leads (crm.lead) → pipeline commercial, liés au contact partner_id
    try:
        leads = odoo_call(
            model="crm.lead", method="search_read",
            kwargs={"domain": [["active", "=", True]],
                    "fields": ["name", "partner_id", "stage_id",
                               "expected_revenue", "probability", "user_id"],
                    "limit": 300}
        )
        for lead in (leads or []):
            partner = lead.get("partner_id")
            # Les leads peuvent exister sans partner_id (prospect pas encore converti).
            # Dans ce cas, on les lie à un contact "lead-<id>" synthétique pour ne
            # pas les perdre, mais idéalement v2 créera un entity_type="lead".
            if partner and isinstance(partner, list):
                partner_name = partner[1] if len(partner) > 1 else ""
                key = normalize_key(partner_name)
            else:
                partner_name = lead.get("name", "") or f"Lead #{lead['id']}"
                key = normalize_key(partner_name)
            if not key:
                continue
            stage = lead.get("stage_id")
            stage_name = stage[1] if isinstance(stage, list) and len(stage) > 1 else ""
            revenue = lead.get("expected_revenue") or 0
            proba = lead.get("probability") or 0
            label = f"{lead.get('name','')} — {stage_name or '?'} — {revenue:.0f}€ ({proba:.0f}%)"
            link_entity(tenant_id, "contact", key, partner_name,
                       "lead", str(lead["id"]), "odoo", label,
                       {"stage": stage_name, "revenue": revenue,
                        "probability": proba, "user_id": lead.get("user_id")})
            stats["leads"] += 1
    except Exception as e:
        stats["errors"].append(f"leads: {str(e)[:100]}")

    # 5. Projets (project.project) → chantiers, liés au contact partner_id
    try:
        projects = odoo_call(
            model="project.project", method="search_read",
            kwargs={"domain": [["active", "=", True]],
                    "fields": ["name", "partner_id", "stage_id", "user_id",
                               "date_start", "date"],
                    "limit": 300}
        )
        for proj in (projects or []):
            partner = proj.get("partner_id")
            if not partner or not isinstance(partner, list):
                continue
            partner_name = partner[1] if len(partner) > 1 else ""
            key = normalize_key(partner_name)
            if not key:
                continue
            stage = proj.get("stage_id")
            stage_name = stage[1] if isinstance(stage, list) and len(stage) > 1 else ""
            date_range = ""
            if proj.get("date_start") or proj.get("date"):
                date_range = f" ({proj.get('date_start','?')} → {proj.get('date','?')})"
            label = f"{proj.get('name','')} — {stage_name or 'en cours'}{date_range}"
            link_entity(tenant_id, "contact", key, partner_name,
                       "project", str(proj["id"]), "odoo", label,
                       {"stage": stage_name, "user_id": proj.get("user_id"),
                        "date_start": str(proj.get("date_start") or ""),
                        "date_end": str(proj.get("date") or "")})
            stats["projects"] += 1
    except Exception as e:
        stats["errors"].append(f"projets: {str(e)[:100]}")

    # 6. Tâches (project.task) → liées au contact partner_id si présent,
    # sinon liées à l'équipier assigné (team_member). Permet à Raya de répondre
    # à "Qui bosse sur quoi ?" et "Où en est la tâche X pour le client Y ?"
    try:
        tasks = odoo_call(
            model="project.task", method="search_read",
            kwargs={"domain": [["active", "=", True]],
                    "fields": ["name", "partner_id", "project_id", "stage_id",
                               "user_ids", "date_deadline"],
                    "limit": 500}
        )
        for task in (tasks or []):
            partner = task.get("partner_id")
            linked = False
            # Lien principal : contact via partner_id
            if partner and isinstance(partner, list):
                partner_name = partner[1] if len(partner) > 1 else ""
                key = normalize_key(partner_name)
                if key:
                    stage = task.get("stage_id")
                    stage_name = stage[1] if isinstance(stage, list) and len(stage) > 1 else ""
                    project = task.get("project_id")
                    project_name = project[1] if isinstance(project, list) and len(project) > 1 else ""
                    deadline = task.get("date_deadline") or ""
                    label = f"{task.get('name','')} [{project_name}] — {stage_name}"
                    if deadline:
                        label += f" (échéance {deadline})"
                    link_entity(tenant_id, "contact", key, partner_name,
                               "task", str(task["id"]), "odoo", label,
                               {"project": project_name, "stage": stage_name,
                                "deadline": str(deadline),
                                "user_ids": task.get("user_ids")})
                    stats["tasks"] += 1
                    linked = True
            # Lien secondaire : équipiers assignés (team_member). Non-exclusif
            # si la tâche a un partner_id : la tâche apparaît dans les 2 vues.
            user_ids = task.get("user_ids") or []
            if isinstance(user_ids, list) and not linked:
                # Sans partner_id mais avec équipier assigné : on lie à l'équipier
                # pour que "que fait Benoît cette semaine ?" remonte ces tâches.
                # Note : user_ids sont des IDs bruts ici, on ne résout pas (ce
                # serait lourd dans populate_from_odoo — c'est odoo_actions qui
                # le fait côté requête live via odoo_enrich).
                for uid in user_ids:
                    if not isinstance(uid, int):
                        continue
                    stage = task.get("stage_id")
                    stage_name = stage[1] if isinstance(stage, list) and len(stage) > 1 else ""
                    project = task.get("project_id")
                    project_name = project[1] if isinstance(project, list) and len(project) > 1 else ""
                    label = f"{task.get('name','')} [{project_name}] — {stage_name}"
                    # Clé synthétique basée sur user_id — l'équipier sera résolu
                    # par ailleurs via team_roster_block.
                    link_entity(tenant_id, "team_member", f"user-{uid}",
                               f"User #{uid}",
                               "task", str(task["id"]), "odoo", label,
                               {"project": project_name, "stage": stage_name,
                                "user_id": uid})
                stats["tasks"] += 1
    except Exception as e:
        stats["errors"].append(f"tâches: {str(e)[:100]}")

    # 7. Planning slots (planning.slot) → ventilations ressources × dates.
    # Module optionnel d'Odoo (Enterprise). Si non installé, l'appel échoue
    # proprement et on continue.
    try:
        slots = odoo_call(
            model="planning.slot", method="search_read",
            kwargs={"domain": [],  # tous (le module filtre déjà par défaut les actifs)
                    "fields": ["name", "start_datetime", "end_datetime",
                               "resource_id", "role_id", "project_id"],
                    "limit": 300}
        )
        for slot in (slots or []):
            resource = slot.get("resource_id")
            if not resource or not isinstance(resource, list):
                continue
            resource_name = resource[1] if len(resource) > 1 else ""
            key = normalize_key(resource_name)
            if not key:
                continue
            role = slot.get("role_id")
            role_name = role[1] if isinstance(role, list) and len(role) > 1 else ""
            project = slot.get("project_id")
            project_name = project[1] if isinstance(project, list) and len(project) > 1 else ""
            start = slot.get("start_datetime") or ""
            end = slot.get("end_datetime") or ""
            label = f"{role_name or 'créneau'} {start} → {end}"
            if project_name:
                label += f" [{project_name}]"
            link_entity(tenant_id, "team_member", key, resource_name,
                       "planning_slot", str(slot["id"]), "odoo", label,
                       {"role": role_name, "project": project_name,
                        "start": str(start), "end": str(end)})
            stats["planning_slots"] += 1
    except Exception as e:
        stats["errors"].append(f"planning: {str(e)[:100]}")

    # 8. Tickets SAV (helpdesk.ticket) → module Helpdesk d'Odoo, optionnel.
    try:
        tickets = odoo_call(
            model="helpdesk.ticket", method="search_read",
            kwargs={"domain": [["active", "=", True]],
                    "fields": ["name", "partner_id", "stage_id", "priority",
                               "user_id", "create_date"],
                    "limit": 300}
        )
        for tk in (tickets or []):
            partner = tk.get("partner_id")
            if not partner or not isinstance(partner, list):
                continue
            partner_name = partner[1] if len(partner) > 1 else ""
            key = normalize_key(partner_name)
            if not key:
                continue
            stage = tk.get("stage_id")
            stage_name = stage[1] if isinstance(stage, list) and len(stage) > 1 else ""
            prio = tk.get("priority") or "0"
            prio_label = {"0": "normale", "1": "basse", "2": "haute",
                          "3": "urgente"}.get(str(prio), prio)
            label = f"{tk.get('name','')} — {stage_name} (prio {prio_label})"
            link_entity(tenant_id, "contact", key, partner_name,
                       "ticket", str(tk["id"]), "odoo", label,
                       {"stage": stage_name, "priority": prio_label,
                        "user_id": tk.get("user_id"),
                        "created": str(tk.get("create_date") or "")})
            stats["tickets"] += 1
    except Exception as e:
        stats["errors"].append(f"tickets: {str(e)[:100]}")

    # 9. Paiements (account.payment) → encaissements historiques, liés au contact.
    # Complète le bloc factures : permet de voir la chronologie des règlements.
    try:
        payments = odoo_call(
            model="account.payment", method="search_read",
            kwargs={"domain": [["state", "!=", "cancel"]],
                    "fields": ["name", "partner_id", "amount", "state",
                               "date", "payment_type"],
                    "limit": 500}
        )
        for pay in (payments or []):
            partner = pay.get("partner_id")
            if not partner or not isinstance(partner, list):
                continue
            partner_name = partner[1] if len(partner) > 1 else ""
            key = normalize_key(partner_name)
            if not key:
                continue
            state_label = {"draft": "brouillon", "posted": "comptabilisé",
                          "reconciled": "rapproché",
                          "sent": "envoyé"}.get(pay.get("state", ""), pay.get("state", ""))
            ptype_label = {"inbound": "reçu", "outbound": "émis"}.get(
                pay.get("payment_type", ""), pay.get("payment_type", ""))
            date_str = str(pay.get("date") or "")
            label = f"{pay.get('name','')} — {pay.get('amount',0):.0f}€ {ptype_label} {state_label} {date_str}"
            link_entity(tenant_id, "contact", key, partner_name,
                       "payment", str(pay["id"]), "odoo", label,
                       {"amount": pay.get("amount"),
                        "state": pay.get("state"),
                        "payment_type": pay.get("payment_type"),
                        "date": date_str})
            stats["payments"] += 1
    except Exception as e:
        stats["errors"].append(f"paiements: {str(e)[:100]}")

    logger.info(
        "[Graph] Odoo → graphe : %d équipiers, %d contacts, %d factures, %d devis, "
        "%d leads, %d projets, %d tâches, %d planning, %d tickets, %d paiements, %d erreurs",
        stats["team_members"], stats["contacts"], stats["invoices"], stats["orders"],
        stats["leads"], stats["projects"], stats["tasks"], stats["planning_slots"],
        stats["tickets"], stats["payments"], len(stats["errors"]))
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
            WHERE tenant_id = %s
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



# ─── PEUPLEMENT : DRIVE → GRAPHE ────────────────────────────────

def populate_from_drive(tenant_id: str, username: str) -> dict:
    """
    Lie les fichiers/dossiers Drive aux entités déjà connues dans le graphe
    (contacts, sociétés). Heuristique : nom de dossier = nom d'entité.

    Ex : dossier 'SARL DES MOINES' → lié à l'entité contact 'sarl-des-moines'.
    """
    from app.drive_manager import get_user_drives
    stats = {"folders": 0, "files": 0, "matched": 0, "errors": []}

    # 1. Récupérer les entités connues du tenant (pour matcher avec les noms de dossier)
    known_entities = {}
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            SELECT DISTINCT entity_key, entity_name FROM entity_links
            WHERE tenant_id = %s AND entity_name IS NOT NULL
        """, (tenant_id,))
        for key, name in c.fetchall():
            if name:
                known_entities[normalize_key(name)] = (key, name)
    except Exception as e:
        stats["errors"].append(f"load entities: {str(e)[:100]}")
    finally:
        if conn: conn.close()

    drives = get_user_drives(username)
    if not drives:
        stats["errors"].append(f"aucun drive connecté pour {username}")
        return stats

    for drv in drives:
        try:
            root = drv.list("") or []
            for item in root:
                if item.item_type != "folder":
                    continue
                stats["folders"] += 1
                key_norm = normalize_key(item.name)
                # Match direct sur nom d'entité connue
                matched_key = None
                for ek, (entity_key, entity_name) in known_entities.items():
                    if key_norm == ek or key_norm in ek or ek in key_norm:
                        matched_key = (entity_key, entity_name)
                        break
                if matched_key:
                    entity_key, entity_name = matched_key
                    link_entity(
                        tenant_id=tenant_id, entity_type="contact",
                        entity_key=entity_key, entity_name=entity_name,
                        resource_type="folder", resource_id=item.id,
                        resource_source=drv.provider,
                        resource_label=f"Dossier {item.name}",
                        resource_data={"url": item.url, "path": item.path},
                    )
                    stats["matched"] += 1
        except Exception as e:
            stats["errors"].append(f"{drv.provider}: {str(e)[:100]}")

    logger.info("[Graph] Drive → graphe : %d dossiers, %d matchs, %d erreurs",
                stats["folders"], stats["matched"], len(stats["errors"]))
    return stats


# ─── PEUPLEMENT : CALENDRIER → GRAPHE ───────────────────────────

def populate_from_calendar(tenant_id: str, username: str) -> dict:
    """
    Lie les événements calendrier aux entités (participants).
    Chaque participant (email) devient une clé d'entité, et l'événement y est rattaché.
    """
    from app.mailbox_manager import load_agenda_all
    stats = {"events": 0, "links": 0, "errors": []}

    try:
        events = load_agenda_all(username, days=30) or []
    except Exception as e:
        return {"events": 0, "links": 0, "errors": [f"load_agenda_all: {str(e)[:200]}"]}

    for ev in events[:100]:
        try:
            stats["events"] += 1
            subject = ev.get("subject") or ev.get("summary") or "(sans sujet)"
            ev_id = str(ev.get("id", ""))
            if not ev_id:
                continue
            source = ev.get("source", "calendar")
            start = ev.get("start") or ev.get("start_time") or ""
            attendees = ev.get("attendees") or []

            for a in attendees:
                email = a.get("email") if isinstance(a, dict) else str(a)
                if not email or "@" not in email:
                    continue
                name = ""
                if isinstance(a, dict):
                    name = a.get("name") or a.get("emailAddress", {}).get("name", "") or email
                link_entity(
                    tenant_id=tenant_id, entity_type="contact",
                    entity_key=email, entity_name=name or email,
                    resource_type="calendar_event", resource_id=ev_id,
                    resource_source=source,
                    resource_label=f"{subject} — {start}",
                    resource_data={"start": start, "subject": subject},
                )
                stats["links"] += 1
        except Exception as e:
            stats["errors"].append(f"event: {str(e)[:80]}")

    logger.info("[Graph] Calendar → graphe : %d événements, %d liens",
                stats["events"], stats["links"])
    return stats


# ─── PEUPLEMENT : CONTACTS FRÉQUENTS → GRAPHE ───────────────────

def populate_from_contacts(tenant_id: str, username: str) -> dict:
    """
    Crée/renforce des entités dans le graphe à partir des contacts fréquents
    (agrégation mail_memory). Ajoute une ressource 'contact_profile' par contact
    avec compteur d'échanges, permettant à Raya de distinguer un contact ponctuel
    d'un interlocuteur régulier.
    """
    stats = {"contacts": 0, "errors": []}
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            SELECT from_email, MAX(from_name) AS name,
                   COUNT(*) AS mail_count, MAX(received_at) AS last_seen
            FROM mail_memory
            WHERE username = %s
              AND (tenant_id = %s OR tenant_id IS NULL)
              AND from_email IS NOT NULL AND from_email != ''
            GROUP BY from_email
            HAVING COUNT(*) >= 2
            ORDER BY MAX(received_at) DESC
            LIMIT 200
        """, (username, tenant_id))
        rows = c.fetchall()
    except Exception as e:
        return {"contacts": 0, "errors": [f"query mail_memory: {str(e)[:200]}"]}
    finally:
        if conn: conn.close()

    for from_email, name, mail_count, last_seen in rows:
        try:
            display = name or from_email
            link_entity(
                tenant_id=tenant_id, entity_type="contact",
                entity_key=from_email, entity_name=display,
                resource_type="contact_profile", resource_id=from_email,
                resource_source="mail_memory",
                resource_label=f"{display} — {mail_count} échanges",
                resource_data={"email": from_email, "mail_count": mail_count,
                               "last_seen": str(last_seen) if last_seen else ""},
            )
            stats["contacts"] += 1
        except Exception as e:
            stats["errors"].append(f"{from_email}: {str(e)[:80]}")

    logger.info("[Graph] Contacts → graphe : %d contacts", stats["contacts"])
    return stats


# ─── LECTURE : BLOC ÉQUIPE POUR INJECTION DANS LE PROMPT ────────

def build_team_roster_block(tenant_id: str) -> str:
    """
    Retourne un bloc texte listant le ROSTER d'équipe (team_member) du tenant
    pour injection dans le prompt système de Raya.
    Source : entity_links peuplée par populate_from_odoo depuis res.users.
    Format court : 1 ligne par personne, prénom + email.
    Retourne une chaîne vide si aucun team_member en base.

    ⚠ Nom explicite 'roster' pour éviter conflit avec
    app.routes.prompt_blocks_extra.build_team_block() qui gère lui les
    événements d'activité de l'équipe (sujet différent).
    """
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            SELECT entity_name, resource_data
            FROM entity_links
            WHERE tenant_id = %s AND entity_type = 'team_member'
              AND resource_type = 'team_member'
            ORDER BY entity_name ASC
            LIMIT 50
        """, (tenant_id,))
        rows = c.fetchall()
        if not rows:
            return ""
        lines = ["ÉQUIPE INTERNE (source Odoo res.users, mise à jour à chaque Découvrir) :"]
        for name, data in rows:
            email = ""
            if isinstance(data, dict):
                email = data.get("email") or data.get("login") or ""
            line = f"  - {name}"
            if email:
                line += f" <{email}>"
            lines.append(line)
        lines.append(
            "Quand l'utilisateur te demande qui compose son équipe, "
            "utilise cette liste (source de vérité). Ne l'enrichis pas avec "
            "des souvenirs conversationnels qui pourraient être incomplets."
        )
        return "\n".join(lines)
    except Exception as e:
        logger.warning("[Graph] build_team_block échoué : %s", e)
        return ""
    finally:
        if conn: conn.close()
