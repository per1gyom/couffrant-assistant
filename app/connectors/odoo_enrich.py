"""
Enrichissement des résultats Odoo : résolution automatique des IDs en noms.

Quand Odoo retourne un champ many2many (ex: user_ids=[14, 13, 15]) ou un
many2one en mode "liste d'IDs", les LLMs comme Raya doivent deviner qui est
qui. Ce module résout ces IDs en noms lisibles avant que le résultat soit
présenté au LLM.

Utilisation :
    from app.connectors.odoo_enrich import enrich_records
    results = odoo_call(model="calendar.event", method="search_read", kwargs={...})
    enriched = enrich_records("calendar.event", results)
    # Maintenant results[0]["user_ids"] = [{"id": 14, "name": "Aurélien Le Maistre"}]

Design :
- Cache in-memory TTL 60s pour éviter de requêter Odoo à chaque appel
- Mapping hardcodé des relations les plus courantes (95% des cas)
- Fallback : si un champ n'est pas connu et contient des IDs, on ne l'enrichit
  pas (on ne casse rien — le LLM verra les IDs bruts comme avant)
"""
from __future__ import annotations

import time
from typing import Optional

from app.logging_config import get_logger

logger = get_logger("raya.odoo_enrich")


# Cache in-memory : clé = (model, id), valeur = (name, timestamp_expiry)
_NAME_CACHE: dict[tuple[str, int], tuple[str, float]] = {}
_CACHE_TTL_SECONDS = 60.0


# Mapping des champs Odoo vers leur modèle relation.
# Couvre les 95% des cas courants sur calendar.event, planning.slot,
# project.task, crm.lead, sale.order, account.move, etc.
FIELD_TO_MODEL: dict[str, str] = {
    # Utilisateurs / contacts
    "user_id": "res.users",
    "user_ids": "res.users",
    "create_uid": "res.users",
    "write_uid": "res.users",
    "partner_id": "res.partner",
    "partner_ids": "res.partner",
    "attendee_ids": "res.partner",
    "responsible_id": "res.users",
    "assigned_to": "res.users",
    # Projets / tâches / planning
    "project_id": "project.project",
    "task_id": "project.task",
    "stage_id": "project.task.type",
    "resource_id": "resource.resource",
    "slot_id": "planning.slot",
    "role_id": "planning.role",
    # CRM
    "team_id": "crm.team",
    "lead_id": "crm.lead",
    "opportunity_id": "crm.lead",
    "source_id": "utm.source",
    "medium_id": "utm.medium",
    "campaign_id": "utm.campaign",
    # Ventes / achats / facturation
    "order_id": "sale.order",
    "sale_order_id": "sale.order",
    "purchase_id": "purchase.order",
    "invoice_id": "account.move",
    "move_id": "account.move",
    "journal_id": "account.journal",
    "account_id": "account.account",
    "product_id": "product.product",
    "product_tmpl_id": "product.template",
    "pricelist_id": "product.pricelist",
    "currency_id": "res.currency",
    "analytic_account_id": "account.analytic.account",
    # HR
    "employee_id": "hr.employee",
    "employee_ids": "hr.employee",
    "department_id": "hr.department",
    "leave_type_id": "hr.leave.type",
    "holiday_id": "hr.leave",
    # Helpdesk
    "ticket_id": "helpdesk.ticket",
    # Référentiel
    "company_id": "res.company",
    "country_id": "res.country",
    "state_id": "res.country.state",
    "title": "res.partner.title",
    "industry_id": "res.partner.industry",
    "lang_id": "res.lang",
    "uom_id": "uom.uom",
    # Stock
    "picking_id": "stock.picking",
    "warehouse_id": "stock.warehouse",
    "location_id": "stock.location",
    "location_dest_id": "stock.location",
    # Tags / catégories génériques (ambigus : on laissera tomber si le modèle
    # ne correspond pas — ce mapping prend le cas le plus fréquent)
    "tag_ids": "res.partner.category",
    "category_ids": "res.partner.category",
    "category_id": "res.partner.category",
}


def _cache_get(model: str, rec_id: int) -> Optional[str]:
    """Retourne le nom en cache si présent et non expiré, sinon None."""
    entry = _NAME_CACHE.get((model, rec_id))
    if not entry:
        return None
    name, expiry = entry
    if time.monotonic() > expiry:
        # Expiré : on le laisse se faire écraser plutôt que le supprimer
        return None
    return name


def _cache_set(model: str, rec_id: int, name: str) -> None:
    """Stocke le nom avec expiration à now+TTL."""
    _NAME_CACHE[(model, rec_id)] = (name, time.monotonic() + _CACHE_TTL_SECONDS)


def _is_id_list(value) -> bool:
    """Détecte si value est une liste d'IDs bruts (pas [id, name])."""
    if not isinstance(value, list) or not value:
        return False
    # [id, "Nom"] arrive d'Odoo pour many2one : 2 éléments, int + str
    if len(value) == 2 and isinstance(value[0], int) and isinstance(value[1], str):
        return False
    # Sinon, si tous les éléments sont des int, c'est une liste d'IDs bruts
    return all(isinstance(x, int) for x in value)


def resolve_ids(model: str, ids: list[int]) -> dict[int, str]:
    """
    Résout une liste d'IDs en dict {id: name} pour un modèle donné.
    Utilise le cache, ne requête Odoo que pour les IDs manquants.

    Robust aux erreurs : si Odoo rejette l'appel (modèle inconnu, droits
    insuffisants, etc.), on retourne les IDs connus en cache + string
    vide pour le reste. L'appelant verra donc au pire les IDs bruts,
    comme avant le fix.
    """
    if not ids:
        return {}
    # 1. Récupérer ce qui est en cache
    result: dict[int, str] = {}
    missing: list[int] = []
    for rec_id in ids:
        cached = _cache_get(model, rec_id)
        if cached is not None:
            result[rec_id] = cached
        else:
            missing.append(rec_id)
    # 2. Requêter Odoo pour les IDs manquants
    if missing:
        try:
            from app.connectors.odoo_connector import odoo_call
            records = odoo_call(
                model=model,
                method="read",
                args=[missing, ["name"]],
            ) or []
            for rec in records:
                rid = rec.get("id")
                name = rec.get("name") or ""
                if rid is not None:
                    result[rid] = name
                    _cache_set(model, rid, name)
        except Exception as e:
            logger.warning("[odoo_enrich] Résolution %s échouée pour %s: %s",
                          model, missing, str(e)[:150])
            # On ne lève pas : l'appelant verra les IDs non résolus
            # comme valeur manquante dans le dict.
    return result


def enrich_record(model: str, record: dict) -> dict:
    """
    Enrichit un record Odoo en place : remplace les listes d'IDs bruts
    par des listes de {id, name}. Retourne le record modifié.

    Ne touche pas aux champs déjà au format [id, name] (many2one standard).
    Ne touche pas aux champs dont le modèle relation est inconnu.
    """
    if not isinstance(record, dict):
        return record
    # Collecter les champs à résoudre, groupés par modèle relation
    # pour batcher les appels Odoo (1 appel par modèle, pas 1 par champ).
    to_resolve: dict[str, set[int]] = {}
    field_model: dict[str, str] = {}
    for field, value in record.items():
        if not _is_id_list(value):
            continue
        relation = FIELD_TO_MODEL.get(field)
        if not relation:
            continue
        field_model[field] = relation
        to_resolve.setdefault(relation, set()).update(value)
    # Résoudre par batch
    name_maps: dict[str, dict[int, str]] = {}
    for relation, ids in to_resolve.items():
        name_maps[relation] = resolve_ids(relation, sorted(ids))
    # Injecter les résultats
    for field, relation in field_model.items():
        ids = record[field]
        names = name_maps.get(relation, {})
        record[field] = [
            {"id": rid, "name": names.get(rid, f"#{rid}")}
            for rid in ids
        ]
    return record


def enrich_records(model: str, records: list[dict]) -> list[dict]:
    """
    Version batch d'enrich_record : groupe toutes les résolutions de tous
    les records en un minimum d'appels Odoo (1 par modèle relation, tous
    records confondus).
    """
    if not records:
        return records
    # Collecter TOUS les IDs à résoudre à travers TOUS les records
    to_resolve: dict[str, set[int]] = {}
    for rec in records:
        if not isinstance(rec, dict):
            continue
        for field, value in rec.items():
            if not _is_id_list(value):
                continue
            relation = FIELD_TO_MODEL.get(field)
            if not relation:
                continue
            to_resolve.setdefault(relation, set()).update(value)
    # Résoudre tous les modèles en batch
    name_maps: dict[str, dict[int, str]] = {}
    for relation, ids in to_resolve.items():
        name_maps[relation] = resolve_ids(relation, sorted(ids))
    # Injecter dans chaque record
    for rec in records:
        if not isinstance(rec, dict):
            continue
        for field, value in list(rec.items()):
            if not _is_id_list(value):
                continue
            relation = FIELD_TO_MODEL.get(field)
            if not relation:
                continue
            names = name_maps.get(relation, {})
            rec[field] = [
                {"id": rid, "name": names.get(rid, f"#{rid}")}
                for rid in value
            ]
    return records


def clear_cache() -> None:
    """Vide le cache — utile pour tests ou si l'admin a modifié des users."""
    _NAME_CACHE.clear()
