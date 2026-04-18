"""
Introspection Odoo — inventaire complet des modèles accessibles.

Utilise les modèles système d'Odoo (ir.model, ir.model.fields) pour
découvrir automatiquement tous les modèles, leurs champs, et leur volume
de records.

Architecture : run en background thread, résultats stockés en mémoire
via un dict indexé par run_id. Évite les timeouts HTTP (30s) quand on a
~300 modèles à inspecter.
"""

import logging
import threading
import time
import uuid
from typing import Optional

logger = logging.getLogger("raya.odoo_introspect")

# Cache en mémoire : run_id -> dict avec progress + result
_RUNS: dict = {}
_RUNS_LOCK = threading.Lock()

# Modèles système à ignorer (bruit, pas d'intérêt métier)
IGNORED_MODEL_PREFIXES = (
    "ir.",          # infrastructure Odoo
    "base.",        # base système
    "bus.",         # bus de messages
    "web.",         # UI
    "website",      # website builder
    "report.",      # rapports
    "mail.compose", # composeur de mails
    "mail.template","mail.blacklist","mail.alias","mail.render",
    "wizard.",      # wizards (popups)
    "res.config",   # settings
    "res.lang", "res.currency", "res.country",  # référentiels Odoo
    "digest.",      # digest hebdo
    "auth_",        # authentification
)


# Champs systématiques présents sur TOUS les records Odoo (à documenter)
SYSTEMATIC_FIELDS = {
    "create_uid", "write_uid", "create_date", "write_date",
    "id", "display_name", "__last_update",
}


def _should_ignore_model(model_name: str) -> bool:
    """Filtre les modèles système qui n'ont pas d'intérêt métier."""
    if not model_name:
        return True
    for prefix in IGNORED_MODEL_PREFIXES:
        if model_name.startswith(prefix):
            return True
    return False


def _categorize_model(model_name: str) -> str:
    """Classification en catégorie métier (pour affichage UI)."""
    if model_name.startswith("res.partner") or model_name in ("res.users", "res.company"):
        return "A_Partenaires"
    if model_name.startswith("crm."):
        return "B_CRM"
    if model_name.startswith("sale."):
        return "C_Ventes"
    if model_name.startswith("account."):
        return "D_Comptabilite"
    if model_name.startswith(("product.", "uom.")):
        return "E_Produits"
    if model_name.startswith(("mrp.", "stock.")):
        return "F_Stock_Production"
    if model_name.startswith(("calendar.", "project.")):
        return "G_Planning_Projets"
    if model_name.startswith("mail."):
        return "H_Communication"
    if model_name.startswith(("sign.", "approval.")):
        return "J_Signatures"
    if model_name.startswith("x_") or "x_" in model_name:
        return "K_Custom"
    return "Z_Autres"


def introspect_odoo(
    include_empty: bool = False,
    include_system: bool = False,
    fetch_fields_for_top: int = 30,
) -> dict:
    """Scanne l'Odoo connecté et retourne un inventaire complet.

    Args:
        include_empty: inclure les modèles sans aucun record
        include_system: inclure les modèles système (ir.*, base.*, etc.)
        fetch_fields_for_top: pour les N modèles avec le plus de records,
            fetch aussi la liste complète des champs (plus lent mais complet)

    Retourne :
      {
        "models": [{
          "model": "sale.order",
          "name": "Bon de commande",
          "category": "C_Ventes",
          "records_count": 310,
          "transient": false,
          "fields_count": 87,
          "fields_sample": [{"name": "partner_id", "type": "many2one",
                              "label": "Client", "relation": "res.partner"}, ...],
        }, ...],
        "stats": {
          "total_models": 245,
          "non_empty_models": 78,
          "business_models": 45,
          "custom_models": 3,
          "total_records_business": 140123,
        },
        "by_category": {"A_Partenaires": 12, "C_Ventes": 8, ...},
      }
    """
    from app.connectors.odoo_connector import odoo_call

    # 1. Lister tous les modèles Odoo via ir.model
    try:
        all_models = odoo_call(
            model="ir.model", method="search_read",
            kwargs={
                "domain": [],
                "fields": ["model", "name", "transient"],
                "limit": 1000,  # largement suffisant (~300 modèles typiques)
            },
        )
    except Exception as e:
        logger.error("[Introspect] Fetch ir.model échoué : %s", str(e)[:200])
        return {"error": f"Impossible de lister les modèles Odoo : {e}"}

    logger.info("[Introspect] %d modèles découverts via ir.model", len(all_models))


    # 2. Filtrer les modèles système sauf si explicitement demandés
    filtered_models = []
    for m in all_models:
        model_name = m.get("model", "")
        if not include_system and _should_ignore_model(model_name):
            continue
        filtered_models.append(m)

    # 3. Pour chaque modèle, compter les records (search_count est léger O(1))
    enriched = []
    for m in filtered_models:
        model_name = m["model"]
        category = _categorize_model(model_name)
        count = 0
        access_error = None
        try:
            count = odoo_call(model=model_name, method="search_count",
                              args=[[]]) or 0
        except Exception as e:
            # Certains modèles ne sont pas requêtables (abstract, manager, etc.)
            # ou on n'a pas les droits. On les skip silencieusement.
            access_error = str(e)[:100]

        if count == 0 and not include_empty:
            continue

        enriched.append({
            "model": model_name,
            "name": m.get("name", ""),
            "category": category,
            "records_count": count,
            "transient": bool(m.get("transient", False)),
            "access_error": access_error,
        })

    # Trier par nombre de records décroissant pour mettre en tête ce qui compte
    enriched.sort(key=lambda x: x["records_count"], reverse=True)

    logger.info("[Introspect] %d modèles non-vides apres filtrage",
                len(enriched))


    # 4. Pour les top N modèles, fetch aussi les champs complets
    for m in enriched[:fetch_fields_for_top]:
        try:
            fields = odoo_call(
                model="ir.model.fields", method="search_read",
                kwargs={
                    "domain": [["model", "=", m["model"]]],
                    "fields": ["name", "field_description", "ttype",
                               "relation", "required", "readonly",
                               "store", "translate"],
                    "limit": 200,
                },
            )
            m["fields_count"] = len(fields or [])
            # Sample : on garde les 20 premiers pour l'aperçu UI, le reste
            # est accessible via /admin/odoo/fields/{model} si besoin
            m["fields_sample"] = [{
                "name": f.get("name"),
                "type": f.get("ttype"),
                "label": f.get("field_description"),
                "relation": f.get("relation"),
                "required": f.get("required"),
                "stored": f.get("store"),
                "translatable": f.get("translate"),
            } for f in (fields or [])[:20]]
            # Compteurs par type pour vue synthèse
            types_count = {}
            for f in (fields or []):
                t = f.get("ttype", "unknown")
                types_count[t] = types_count.get(t, 0) + 1
            m["fields_by_type"] = types_count
        except Exception as e:
            m["fields_count"] = None
            m["fields_error"] = str(e)[:150]

    # 5. Stats agrégées
    by_category = {}
    for m in enriched:
        by_category[m["category"]] = by_category.get(m["category"], 0) + 1

    stats = {
        "total_models_discovered": len(all_models),
        "total_models_filtered": len(enriched),
        "models_with_fields": sum(1 for m in enriched if m.get("fields_count")),
        "total_records_all": sum(m["records_count"] for m in enriched),
        "custom_models": sum(1 for m in enriched if m["category"] == "K_Custom"),
    }

    return {
        "status": "ok",
        "stats": stats,
        "by_category": by_category,
        "models": enriched,
    }


# ─── API ASYNC : run en background + polling ──────────────────

def start_introspect_run(
    include_empty: bool = False,
    include_system: bool = False,
    fetch_fields_for_top: int = 30,
) -> str:
    """Lance une introspection en background. Retourne un run_id a utiliser
    pour poller le resultat via get_run_status(run_id).

    Ne bloque pas : l'appelant recupere immediatement le run_id et peut
    interroger l'avancement sans timeout HTTP."""
    run_id = str(uuid.uuid4())[:12]
    with _RUNS_LOCK:
        _RUNS[run_id] = {
            "run_id": run_id,
            "status": "running",
            "started_at": time.time(),
            "progress": {"step": "init", "current": 0, "total": 0},
            "result": None,
            "error": None,
        }

    def worker():
        try:
            _run_introspect_internal(run_id, include_empty, include_system,
                                      fetch_fields_for_top)
        except Exception as e:
            logger.exception("[Introspect] worker crash")
            with _RUNS_LOCK:
                _RUNS[run_id]["status"] = "error"
                _RUNS[run_id]["error"] = str(e)[:500]

    threading.Thread(target=worker, daemon=True).start()
    return run_id


def get_run_status(run_id: str) -> Optional[dict]:
    """Recupere le status d'un run en cours ou termine."""
    with _RUNS_LOCK:
        return _RUNS.get(run_id)


def _update_progress(run_id: str, step: str, current: int, total: int):
    """Helper pour mettre a jour l'avancement depuis le worker."""
    with _RUNS_LOCK:
        if run_id in _RUNS:
            _RUNS[run_id]["progress"] = {
                "step": step, "current": current, "total": total,
                "pct": round(100 * current / total, 1) if total else 0,
            }


def _run_introspect_internal(
    run_id: str,
    include_empty: bool,
    include_system: bool,
    fetch_fields_for_top: int,
):
    """Worker qui fait le boulot, met a jour la progression, stocke le resultat."""
    from app.connectors.odoo_connector import odoo_call

    # Etape 1 : liste des modeles
    _update_progress(run_id, "list_models", 0, 1)
    try:
        all_models = odoo_call(
            model="ir.model", method="search_read",
            kwargs={
                "domain": [],
                "fields": ["model", "name", "transient"],
                "limit": 1000,
            },
        )
    except Exception as e:
        with _RUNS_LOCK:
            _RUNS[run_id]["status"] = "error"
            _RUNS[run_id]["error"] = f"Fetch ir.model: {e}"
        return

    logger.info("[Introspect run=%s] %d modeles decouverts", run_id, len(all_models))

    # Etape 2 : filtrer
    filtered = [m for m in all_models
                if include_system or not _should_ignore_model(m.get("model", ""))]

    # Etape 3 : counter chaque modele (c'est ce qui etait long)
    enriched = []
    total = len(filtered)
    for i, m in enumerate(filtered):
        _update_progress(run_id, "counting", i, total)
        model_name = m["model"]
        count = 0
        access_error = None
        try:
            count = odoo_call(model=model_name, method="search_count",
                              args=[[]]) or 0
        except Exception as e:
            access_error = str(e)[:100]
        if count == 0 and not include_empty:
            continue
        enriched.append({
            "model": model_name,
            "name": m.get("name", ""),
            "category": _categorize_model(model_name),
            "records_count": count,
            "transient": bool(m.get("transient", False)),
            "access_error": access_error,
        })

    # Tri par volume decroissant
    enriched.sort(key=lambda x: x["records_count"], reverse=True)


    # Etape 4 : fetch fields pour le top N
    top = enriched[:fetch_fields_for_top]
    for i, m in enumerate(top):
        _update_progress(run_id, "fetch_fields", i, len(top))
        try:
            fields = odoo_call(
                model="ir.model.fields", method="search_read",
                kwargs={
                    "domain": [["model", "=", m["model"]]],
                    "fields": ["name", "field_description", "ttype",
                               "relation", "required", "readonly",
                               "store", "translate"],
                    "limit": 200,
                },
            )
            m["fields_count"] = len(fields or [])
            m["fields_sample"] = [{
                "name": f.get("name"),
                "type": f.get("ttype"),
                "label": f.get("field_description"),
                "relation": f.get("relation"),
                "stored": f.get("store"),
            } for f in (fields or [])[:20]]
            types_count = {}
            for f in (fields or []):
                t = f.get("ttype", "unknown")
                types_count[t] = types_count.get(t, 0) + 1
            m["fields_by_type"] = types_count
        except Exception as e:
            m["fields_error"] = str(e)[:150]

    by_category = {}
    for m in enriched:
        by_category[m["category"]] = by_category.get(m["category"], 0) + 1

    stats = {
        "total_models_discovered": len(all_models),
        "total_models_filtered": len(enriched),
        "models_with_fields": sum(1 for m in enriched if m.get("fields_count")),
        "total_records_all": sum(m["records_count"] for m in enriched),
        "custom_models": sum(1 for m in enriched if m["category"] == "K_Custom"),
    }

    duration = time.time() - _RUNS[run_id]["started_at"]
    with _RUNS_LOCK:
        _RUNS[run_id]["status"] = "ok"
        _RUNS[run_id]["duration_sec"] = round(duration, 1)
        _RUNS[run_id]["result"] = {
            "stats": stats,
            "by_category": by_category,
            "models": enriched,
        }
    logger.info("[Introspect run=%s] Termine en %.1fs, %d modeles",
                run_id, duration, len(enriched))
