"""
Vue 360° client — agrège en un seul appel toutes les infos qu'un dirigeant
peut vouloir sur un client : contact, chantiers, factures, paiements, leads,
tickets SAV, mails récents, et indicateurs financiers (CA, impayés, balance).

Cas d'usage : quand Guillaume demande "Fais-moi le point sur AZEM", Raya
appelle get_client_360("AZEM") et reçoit un bloc structuré prêt à être
synthétisé — au lieu de faire 6-8 requêtes Odoo séquentielles coûteuses.

Adaptation Couffrant Solar : comme project.project n'est pas utilisé,
les "chantiers" sont matérialisés par les sale.order confirmés (state='sale').
Pour d'autres tenants qui utilisent project.project, on ajoute aussi ces
projets dans la vue (fallback intelligent).

Étape 3 du chantier enrichissement vision Odoo (après résolution IDs
en étape 1 et élargissement entity_graph en étape 2).
"""

import logging
from typing import Any, Optional

from app.connectors.odoo_connector import odoo_call
from app.connectors.odoo_enrich import enrich_records

logger = logging.getLogger("raya.client_360")


# ─── RÉSOLUTION DU PARTNER ─────────────────────────────────────


def _resolve_partner(key_or_id: Any) -> Optional[dict]:
    """Résout un partenaire Odoo depuis un ID (int) ou un nom (string).
    Retourne le dict partner complet ou None si pas trouvé.
    Si plusieurs matches sur le nom, retourne le premier (tri par id DESC
    pour favoriser les partenaires récents, ce qui est un heuristique
    utile quand on a des doublons anciens mal nettoyés)."""
    # Cas 1 : ID numérique direct
    if isinstance(key_or_id, int) or (isinstance(key_or_id, str) and str(key_or_id).isdigit()):
        pid = int(key_or_id)
        try:
            partners = odoo_call(
                model="res.partner", method="search_read",
                kwargs={
                    "domain": [["id", "=", pid]],
                    "fields": ["id", "name", "email", "phone", "mobile",
                               "street", "city", "zip", "country_id", "is_company",
                               "parent_id", "customer_rank", "supplier_rank",
                               "comment", "create_date"],
                },
            )
            return partners[0] if partners else None
        except Exception as e:
            logger.warning("[Client360] resolve_partner by id %s échoué : %s", pid, e)
            return None

    # Cas 2 : recherche par nom (ilike insensible à la casse)
    name = str(key_or_id).strip()
    if not name:
        return None
    try:
        partners = odoo_call(
            model="res.partner", method="search_read",
            kwargs={
                "domain": [["name", "ilike", name]],
                "fields": ["id", "name", "email", "phone", "mobile",
                           "street", "city", "zip", "country_id", "is_company",
                           "parent_id", "customer_rank", "supplier_rank",
                           "comment", "create_date"],
                "limit": 10,
                "order": "id DESC",
            },
        )
        if not partners:
            return None
        # Si une seule occurrence : retour direct
        if len(partners) == 1:
            return partners[0]
        # Plusieurs : on privilégie la correspondance exacte du nom (case-insensitive),
        # sinon le plus récent (déjà trié id DESC).
        name_low = name.lower()
        exact = [p for p in partners if (p.get("name") or "").strip().lower() == name_low]
        return (exact[0] if exact else partners[0])
    except Exception as e:
        logger.warning("[Client360] resolve_partner by name '%s' échoué : %s", name, e)
        return None


# ─── AGRÉGATION 360° ───────────────────────────────────────────

def get_client_360(key_or_id: Any, include_mails: bool = True,
                   mail_username: Optional[str] = None) -> dict:
    """Agrège en un dict structuré toutes les infos client pertinentes.

    Args:
        key_or_id: ID numérique du partner ou nom (str) à rechercher.
        include_mails: si True, inclut les mails récents depuis mail_memory.
        mail_username: username du tenant pour filtrer mail_memory
            (nécessaire si include_mails=True).

    Returns:
        dict avec clés : partner, orders, invoices, payments, leads,
        projects, tasks, tickets, mails, indicators, errors.
        Si partner non résolu, retourne {"error": "...", "partner": None}.
    """
    result: dict = {
        "partner": None,
        "orders": [], "invoices": [], "payments": [],
        "leads": [], "projects": [], "tasks": [], "tickets": [],
        "mails": [],
        "indicators": {},
        "errors": [],
    }

    partner = _resolve_partner(key_or_id)
    if not partner:
        result["error"] = f"Partner '{key_or_id}' introuvable dans Odoo"
        return result
    result["partner"] = partner
    pid = partner["id"]

    # ─── 1. Devis & Chantiers (sale.order) ────────────────────
    # Dans le cas Couffrant Solar, les "chantiers" sont des sale.order
    # confirmés (state='sale'). On récupère TOUS les devis+chantiers
    # du client, la distinction se fait via le champ state :
    #   - draft, sent : devis en cours
    #   - sale : chantier confirmé
    #   - done : chantier terminé
    #   - cancel : annulé
    try:
        orders = odoo_call(
            model="sale.order", method="search_read",
            kwargs={
                "domain": [["partner_id", "=", pid]],
                "fields": ["id", "name", "state", "amount_total",
                           "amount_untaxed", "date_order", "validity_date",
                           "user_id", "team_id", "invoice_status",
                           "commitment_date", "note"],
                "order": "date_order DESC",
                "limit": 50,
            },
        )
        if orders:
            orders = enrich_records("sale.order", orders) or orders
        result["orders"] = orders or []
    except Exception as e:
        result["errors"].append(f"sale.order: {str(e)[:100]}")

    # ─── 2. Factures (account.move type out_invoice + out_refund) ────
    try:
        invoices = odoo_call(
            model="account.move", method="search_read",
            kwargs={
                "domain": [
                    ["partner_id", "=", pid],
                    ["move_type", "in", ["out_invoice", "out_refund"]],
                ],
                "fields": ["id", "name", "state", "move_type",
                           "amount_total", "amount_residual",
                           "invoice_date", "invoice_date_due",
                           "payment_state", "ref", "invoice_origin"],
                "order": "invoice_date DESC",
                "limit": 100,
            },
        )
        result["invoices"] = invoices or []
    except Exception as e:
        result["errors"].append(f"account.move: {str(e)[:100]}")

    # ─── 3. Paiements (account.payment) ───────────────────────
    try:
        payments = odoo_call(
            model="account.payment", method="search_read",
            kwargs={
                "domain": [
                    ["partner_id", "=", pid],
                    ["state", "!=", "cancel"],
                ],
                "fields": ["id", "name", "amount", "state", "date",
                           "payment_type", "ref", "journal_id"],
                "order": "date DESC",
                "limit": 50,
            },
        )
        if payments:
            payments = enrich_records("account.payment", payments) or payments
        result["payments"] = payments or []
    except Exception as e:
        result["errors"].append(f"account.payment: {str(e)[:100]}")

    # ─── 4. Leads CRM (crm.lead) ──────────────────────────────
    try:
        leads = odoo_call(
            model="crm.lead", method="search_read",
            kwargs={
                "domain": [["partner_id", "=", pid], ["active", "=", True]],
                "fields": ["id", "name", "stage_id", "expected_revenue",
                           "probability", "user_id", "create_date",
                           "date_deadline"],
                "order": "create_date DESC",
                "limit": 20,
            },
        )
        if leads:
            leads = enrich_records("crm.lead", leads) or leads
        result["leads"] = leads or []
    except Exception as e:
        result["errors"].append(f"crm.lead: {str(e)[:100]}")

    # ─── 5. Projets (project.project) ─────────────────────────
    # Module optionnel — peut échouer si non installé.
    # Pour Couffrant Solar, ce bloc retournera typiquement 0 projets car
    # Guillaume utilise sale.order comme "chantier". Les autres tenants
    # qui ont project.project auront les projets listés.
    try:
        projects = odoo_call(
            model="project.project", method="search_read",
            kwargs={
                "domain": [["partner_id", "=", pid]],
                "fields": ["id", "name", "stage_id", "user_id",
                           "date_start", "date", "task_count"],
                "limit": 20,
            },
        )
        if projects:
            projects = enrich_records("project.project", projects) or projects
        result["projects"] = projects or []
    except Exception as e:
        result["errors"].append(f"project.project: {str(e)[:80]}")

    # ─── 6. Tickets SAV (helpdesk.ticket) — optionnel ─────────
    try:
        tickets = odoo_call(
            model="helpdesk.ticket", method="search_read",
            kwargs={
                "domain": [["partner_id", "=", pid], ["active", "=", True]],
                "fields": ["id", "name", "stage_id", "priority", "user_id",
                           "create_date", "team_id"],
                "order": "create_date DESC",
                "limit": 20,
            },
        )
        if tickets:
            tickets = enrich_records("helpdesk.ticket", tickets) or tickets
        result["tickets"] = tickets or []
    except Exception as e:
        result["errors"].append(f"helpdesk.ticket: {str(e)[:80]}")

    # ─── 7. Mails récents (mail_memory) ───────────────────────
    # Recherche tous les mails dont l'email expéditeur correspond à
    # partner.email OU dont le sujet/corps mentionne partner.name.
    # Filtrage par tenant via username (qui reçoit les mails).
    if include_mails and mail_username:
        try:
            result["mails"] = _fetch_client_mails(partner, mail_username, limit=10)
        except Exception as e:
            result["errors"].append(f"mails: {str(e)[:80]}")

    # ─── 8. Calcul des indicateurs financiers ─────────────────
    result["indicators"] = _compute_indicators(result)

    return result


# ─── MAILS ─────────────────────────────────────────────────────

def _fetch_client_mails(partner: dict, username: str, limit: int = 10) -> list:
    """Récupère les mails récents liés à ce partner depuis mail_memory.
    Matche sur l'email (exact) ET sur le nom (ilike dans subject/sender)."""
    from app.database import get_pg_conn
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        email = (partner.get("email") or "").strip().lower()
        name = (partner.get("name") or "").strip()
        # Construction dynamique du WHERE selon ce qu'on a
        conditions = ["username = %s"]
        params: list = [username]
        if email:
            conditions.append("LOWER(from_email) = %s")
            params.append(email)
            # On utilise OR ici : l'email matche OU le nom matche
            where = "username = %s AND (LOWER(from_email) = %s"
            sub_params = [username, email]
            if name and len(name) >= 3:
                where += " OR subject ILIKE %s OR from_email ILIKE %s"
                sub_params.extend([f"%{name}%", f"%{name.split()[0]}%"])
            where += ")"
            params = sub_params
        else:
            if not name or len(name) < 3:
                return []
            where = "username = %s AND (subject ILIKE %s OR from_email ILIKE %s)"
            params = [username, f"%{name}%", f"%{name.split()[0]}%"]

        c.execute(
            f"""
            SELECT id, from_email, subject, short_summary, received_at,
                   category, priority
            FROM mail_memory
            WHERE {where}
              AND deleted_at IS NULL
            ORDER BY received_at DESC NULLS LAST
            LIMIT %s
            """,
            (*params, limit),
        )
        cols = [d[0] for d in c.description]
        return [dict(zip(cols, row)) for row in c.fetchall()]
    except Exception as e:
        logger.warning("[Client360] _fetch_client_mails: %s", e)
        return []
    finally:
        if conn: conn.close()


# ─── CALCUL D'INDICATEURS ──────────────────────────────────────

def _compute_indicators(data: dict) -> dict:
    """Calcule les indicateurs financiers et métier à partir des
    données brutes récupérées. Détecte aussi les anomalies simples
    (factures annulées, impayés significatifs, dormance)."""
    ind: dict = {
        "ca_facture": 0.0,
        "ca_encaisse": 0.0,
        "impayes": 0.0,
        "balance": 0.0,
        "chantiers_confirmes": 0,
        "chantiers_termines": 0,
        "devis_en_cours": 0,
        "factures_count": 0,
        "impayes_count": 0,
        "paiements_count": 0,
        "derniere_activite": None,
        "anomalies": [],
    }

    # Ventilation des devis/chantiers par état
    for o in data.get("orders", []):
        state = o.get("state", "")
        if state == "sale":
            ind["chantiers_confirmes"] += 1
        elif state == "done":
            ind["chantiers_termines"] += 1
        elif state in ("draft", "sent"):
            ind["devis_en_cours"] += 1

    # Agrégats factures
    cancelled_refunded = []  # pour détection anomalie facture annulée le même jour qu'un impayé
    for inv in data.get("invoices", []):
        ind["factures_count"] += 1
        move_type = inv.get("move_type", "")
        state = inv.get("state", "")
        pay_state = inv.get("payment_state", "")
        total = inv.get("amount_total", 0) or 0
        residual = inv.get("amount_residual", 0) or 0
        if state == "cancel":
            cancelled_refunded.append(inv)
            continue
        # Factures posted : on compte le CA
        if move_type == "out_invoice" and state == "posted":
            ind["ca_facture"] += total
            if pay_state in ("not_paid", "partial") and residual > 0:
                ind["impayes"] += residual
                ind["impayes_count"] += 1
        elif move_type == "out_refund" and state == "posted":
            # Avoir : soustrait du CA facturé
            ind["ca_facture"] -= total

    # Agrégats paiements
    for p in data.get("payments", []):
        if p.get("state") in ("posted", "reconciled"):
            amount = p.get("amount", 0) or 0
            ptype = p.get("payment_type", "")
            if ptype == "inbound":
                ind["ca_encaisse"] += amount
            # outbound = remboursement au client, non déduit du CA ici
            ind["paiements_count"] += 1

    # Balance : positive = client débiteur (nous doit de l'argent)
    ind["balance"] = round(ind["ca_facture"] - ind["ca_encaisse"], 2)
    ind["ca_facture"] = round(ind["ca_facture"], 2)
    ind["ca_encaisse"] = round(ind["ca_encaisse"], 2)
    ind["impayes"] = round(ind["impayes"], 2)

    # Dernière activité : max des dates (order, invoice, payment, mail)
    dates = []
    for o in data.get("orders", []):
        if o.get("date_order"): dates.append(str(o["date_order"])[:10])
    for i in data.get("invoices", []):
        if i.get("invoice_date"): dates.append(str(i["invoice_date"])[:10])
    for p in data.get("payments", []):
        if p.get("date"): dates.append(str(p["date"])[:10])
    for m in data.get("mails", []):
        if m.get("received_at"): dates.append(str(m["received_at"])[:10])
    if dates:
        ind["derniere_activite"] = max(dates)

    # ─── Détection d'anomalies ────────────────────────────────
    # Comme ce que Raya a identifié en live sur AZEM : facture annulée
    # le même jour qu'un impayé est un signal fort de situation complexe.
    for ci in cancelled_refunded:
        ci_date = str(ci.get("invoice_date", ""))[:10]
        if not ci_date:
            continue
        for inv in data.get("invoices", []):
            if inv.get("id") == ci.get("id"): continue
            inv_date = str(inv.get("invoice_date", ""))[:10]
            if inv_date == ci_date and inv.get("state") == "posted":
                pay_state = inv.get("payment_state", "")
                if pay_state in ("not_paid", "partial"):
                    ind["anomalies"].append({
                        "type": "cancel_impaye_meme_jour",
                        "label": (f"Facture {ci.get('name','?')} annulée "
                                  f"le {ci_date}, même jour qu'impayé "
                                  f"{inv.get('name','?')} de "
                                  f"{inv.get('amount_residual',0):.0f}€"),
                    })

    # Impayé significatif (> 5k€)
    if ind["impayes"] >= 5000:
        ind["anomalies"].append({
            "type": "impaye_significatif",
            "label": f"Impayé total de {ind['impayes']:.0f}€ "
                     f"sur {ind['impayes_count']} facture(s)",
        })

    # Dormance : pas d'activité depuis 180 jours alors que le client
    # a déjà eu des commandes (utile pour relance commerciale).
    if ind["derniere_activite"] and ind["factures_count"] > 0:
        from datetime import date as _date
        try:
            y, m, d = ind["derniere_activite"].split("-")
            last = _date(int(y), int(m), int(d))
            days_since = (_date.today() - last).days
            if days_since > 180:
                ind["anomalies"].append({
                    "type": "dormance",
                    "label": f"Dernière activité il y a {days_since} jours "
                             f"({ind['derniere_activite']})",
                })
        except Exception:
            pass

    return ind


# ─── FORMATAGE POUR RAYA ───────────────────────────────────────


def format_client_360(data: dict, max_items_per_section: int = 8) -> str:
    """Formate le dict retourné par get_client_360 en texte structuré
    prêt à être injecté dans la réponse de Raya. Version riche mais
    concise : les sections vides sont omises."""
    if data.get("error"):
        return f"❌ {data['error']}"

    partner = data.get("partner") or {}
    ind = data.get("indicators") or {}
    lines: list = []

    # En-tête : identité du client
    name = partner.get("name") or "?"
    is_company = partner.get("is_company")
    kind = "entreprise" if is_company else "particulier"
    lines.append(f"📇 Vue 360° — {name} ({kind}, #{partner.get('id')})")

    contact_bits = []
    if partner.get("email"): contact_bits.append(f"✉ {partner['email']}")
    if partner.get("phone"): contact_bits.append(f"📞 {partner['phone']}")
    elif partner.get("mobile"): contact_bits.append(f"📱 {partner['mobile']}")
    city_bits = [str(partner.get(f) or "").strip() for f in ("zip", "city")]
    city_str = " ".join([b for b in city_bits if b])
    if city_str: contact_bits.append(f"📍 {city_str}")
    if contact_bits: lines.append("  " + " · ".join(contact_bits))

    # Synthèse financière
    if ind.get("factures_count") or ind.get("paiements_count"):
        lines.append("")
        lines.append("=== Synthèse financière ===")
        lines.append(f"CA facturé : {ind.get('ca_facture', 0):,.0f}€ "
                     f"sur {ind.get('factures_count', 0)} facture(s)")
        lines.append(f"Encaissé : {ind.get('ca_encaisse', 0):,.0f}€ "
                     f"sur {ind.get('paiements_count', 0)} paiement(s)")
        if ind.get("impayes", 0) > 0:
            lines.append(f"🔴 Impayés : {ind['impayes']:,.0f}€ "
                         f"({ind.get('impayes_count', 0)} facture(s))")
        balance = ind.get("balance", 0)
        if balance > 100:
            lines.append(f"Balance : {balance:,.0f}€ (client débiteur)")
        elif balance < -100:
            lines.append(f"Balance : {balance:,.0f}€ (client créditeur)")
        else:
            lines.append(f"Balance : équilibrée")

    # Anomalies détectées (signal fort pour Raya)
    if ind.get("anomalies"):
        lines.append("")
        lines.append("⚠️ Anomalies détectées :")
        for a in ind["anomalies"]:
            lines.append(f"  • {a['label']}")

    # Chantiers (sale.order state='sale' ou 'done') — priorité haute
    chantiers = [o for o in data.get("orders", []) if o.get("state") in ("sale", "done")]
    if chantiers:
        lines.append("")
        label = "Chantiers" if ind.get("chantiers_termines", 0) == 0 else "Chantiers/terminés"
        lines.append(f"=== {label} ({len(chantiers)}) ===")
        for o in chantiers[:max_items_per_section]:
            state_label = {"sale": "confirmé", "done": "terminé"}.get(o.get("state"), "?")
            date = str(o.get("date_order") or "")[:10]
            user = o.get("user_id")
            user_name = user[1] if isinstance(user, list) and len(user) > 1 else ""
            lines.append(f"  • {o.get('name','?')} — {o.get('amount_total',0):,.0f}€ "
                         f"{state_label} ({date}) {('· '+user_name) if user_name else ''}")

    # Devis en cours
    devis = [o for o in data.get("orders", []) if o.get("state") in ("draft", "sent")]
    if devis:
        lines.append("")
        lines.append(f"=== Devis en cours ({len(devis)}) ===")
        for o in devis[:max_items_per_section]:
            state_label = {"draft": "brouillon", "sent": "envoyé"}.get(o.get("state"), "?")
            date = str(o.get("date_order") or "")[:10]
            lines.append(f"  • {o.get('name','?')} — {o.get('amount_total',0):,.0f}€ "
                         f"{state_label} ({date})")


    # Factures récentes (max 6 : 3 impayées + 3 récentes par défaut)
    invoices = data.get("invoices", [])
    if invoices:
        impayees = [i for i in invoices
                    if i.get("state") == "posted"
                    and i.get("payment_state") in ("not_paid", "partial")
                    and (i.get("amount_residual") or 0) > 0]
        recentes = [i for i in invoices if i not in impayees
                    and i.get("state") == "posted"][:3]
        shown = impayees[:4] + recentes
        if shown:
            lines.append("")
            lines.append(f"=== Factures ({len(shown)}/{len(invoices)}) ===")
            for inv in shown:
                date = str(inv.get("invoice_date") or "")[:10]
                total = inv.get("amount_total", 0) or 0
                residual = inv.get("amount_residual", 0) or 0
                pay_state = inv.get("payment_state", "")
                is_refund = inv.get("move_type") == "out_refund"
                prefix = "↩ AVOIR" if is_refund else ""
                if inv in impayees:
                    lines.append(f"  🔴 {inv.get('name','?')} — {total:,.0f}€ "
                                 f"(reste {residual:,.0f}€ {pay_state}) {date}")
                else:
                    state_lbl = pay_state if pay_state else inv.get("state", "")
                    lines.append(f"  • {prefix} {inv.get('name','?')} — "
                                 f"{total:,.0f}€ {state_lbl} {date}")

    # Paiements récents (top 5)
    payments = data.get("payments", [])
    if payments:
        lines.append("")
        lines.append(f"=== Paiements récents ({min(5, len(payments))}/{len(payments)}) ===")
        for p in payments[:5]:
            date = str(p.get("date") or "")[:10]
            amount = p.get("amount", 0) or 0
            ptype = {"inbound": "reçu", "outbound": "émis"}.get(p.get("payment_type", ""), "?")
            state = {"posted": "comptabilisé", "reconciled": "rapproché",
                     "draft": "brouillon"}.get(p.get("state", ""), p.get("state", ""))
            lines.append(f"  • {p.get('name','?')} — {amount:,.0f}€ {ptype} {state} ({date})")

    # Leads CRM actifs
    leads = data.get("leads", [])
    if leads:
        lines.append("")
        lines.append(f"=== Pipeline CRM ({len(leads)}) ===")
        for l in leads[:max_items_per_section]:
            stage = l.get("stage_id")
            stage_name = stage[1] if isinstance(stage, list) and len(stage) > 1 else "?"
            revenue = l.get("expected_revenue", 0) or 0
            proba = l.get("probability", 0) or 0
            lines.append(f"  • {l.get('name','?')} — {stage_name} — "
                         f"{revenue:,.0f}€ ({proba:.0f}%)")

    # Projets (rare chez Couffrant Solar, utile pour autres tenants)
    projects = data.get("projects", [])
    if projects:
        lines.append("")
        lines.append(f"=== Projets ({len(projects)}) ===")
        for proj in projects[:max_items_per_section]:
            stage = proj.get("stage_id")
            stage_name = stage[1] if isinstance(stage, list) and len(stage) > 1 else "?"
            date_end = str(proj.get("date") or "")[:10]
            tasks_n = proj.get("task_count", 0) or 0
            lines.append(f"  • {proj.get('name','?')} — {stage_name} "
                         f"({tasks_n} tâche(s)) {('→ '+date_end) if date_end else ''}")

    # Tickets SAV actifs
    tickets = data.get("tickets", [])
    if tickets:
        lines.append("")
        lines.append(f"=== Tickets SAV ({len(tickets)}) ===")
        for tk in tickets[:max_items_per_section]:
            stage = tk.get("stage_id")
            stage_name = stage[1] if isinstance(stage, list) and len(stage) > 1 else "?"
            prio = str(tk.get("priority", "0"))
            prio_lbl = {"0": "normale", "1": "basse", "2": "haute",
                        "3": "urgente"}.get(prio, prio)
            date = str(tk.get("create_date") or "")[:10]
            lines.append(f"  • {tk.get('name','?')} — {stage_name} "
                         f"(prio {prio_lbl}, ouvert le {date})")

    # Mails récents liés au client (extrait mail_memory)
    mails = data.get("mails", [])
    if mails:
        lines.append("")
        lines.append(f"=== Mails récents ({min(5, len(mails))}/{len(mails)}) ===")
        for m in mails[:5]:
            date = str(m.get("received_at") or "")[:10]
            sender = m.get("from_email", "?")
            subj = (m.get("subject") or "")[:70]
            prio_lbl = ""
            prio = m.get("priority")
            if prio == "high" or prio == "urgent":
                prio_lbl = " 🔴"
            lines.append(f"  • {date} · {sender}{prio_lbl} — {subj}")

    # Pied de page : dernière activité + erreurs techniques silencieuses
    if ind.get("derniere_activite"):
        lines.append("")
        lines.append(f"Dernière activité : {ind['derniere_activite']}")

    # Erreurs techniques (modèles non installés) : affichées en fin en
    # discret pour que Raya sache quelles sources n'étaient pas disponibles
    # sans polluer la vue principale.
    errors = data.get("errors", [])
    if errors:
        lines.append("")
        lines.append("(Sources indisponibles : " + ", ".join(
            e.split(":")[0] for e in errors) + ")")

    return "\n".join(lines)
