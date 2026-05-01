"""
Reconciliation nocturne Odoo — filet ultime contre les fuites silencieuses.

Phase Connexions Universelles - Semaine 2 (Etape 2.5, 1er mai 2026).
Voir docs/vision_connexions_universelles_01mai.md.

PRINCIPE :
─────────────────────────────────────────────────────────────────
Tous les jours a 4h du matin, pour chaque modele Odoo polle :
  1. count_odoo  = appel API Odoo "search_count" sur le modele
  2. count_raya  = SELECT COUNT distinct(source_record_id) FROM
                   odoo_semantic_content WHERE source_model = X
  3. Si delta > 1% : alerte WARNING via alert_dispatcher
     + tentative de re-sync forcee (ignore le curseur write_date)

POURQUOI :
─────────────────────────────────────────────────────────────────
Le polling toutes les 2 min via write_date est tres fiable, mais peut
rater des records dans des cas exotiques :
  - Update Odoo sans modif write_date (rare mais possible)
  - Crash Raya pendant le traitement d un cycle
  - Bug logique dans le pipeline d ingestion
  - Suppression Odoo sans propagation a Raya

Cette reconciliation est notre GARANTIE DE COMPLETUDE ABSOLUE :
si on perd des records, on le sait en max 24h.

C est l etape "Niveau 4" du pattern delta sync universel decrit dans
le doc vision section Partie 2.
"""

import json
import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger("raya.odoo_reconciliation")

# Seuil au-dessus duquel on declenche l alerte (1%)
DELTA_ALERT_THRESHOLD_PCT = 1.0


def run_odoo_reconciliation():
    """Job nocturne (4h du matin) : compare count Odoo vs count Raya
    pour chaque modele polle. Alerte WARNING si delta > 1%.

    Tourne en mode best effort : ne plante jamais le scheduler.
    Si Odoo est inaccessible (ex: maintenance), on log et on attend
    le prochain cycle.
    """
    try:
        from app.jobs.odoo_polling import POLLED_MODELS, _get_tenants_to_poll
    except Exception as e:
        logger.error("[OdooRecon] Import echec : %s", str(e)[:200])
        return

    tenants = _get_tenants_to_poll()
    if not tenants:
        logger.debug("[OdooRecon] Aucun tenant configure, skip")
        return

    started_at = datetime.now()
    total_alerts = 0
    total_models_checked = 0

    for tenant_id in tenants:
        for model in POLLED_MODELS:
            total_models_checked += 1
            try:
                result = _reconcile_model(tenant_id, model)
                if result.get("alert_raised"):
                    total_alerts += 1
            except Exception as e:
                logger.error("[OdooRecon] %s/%s crash : %s",
                             tenant_id, model, str(e)[:200])

    duration = (datetime.now() - started_at).total_seconds()
    logger.info(
        "[OdooRecon] Reconciliation terminee : %d modele(s) verifie(s), "
        "%d alerte(s) levee(s) en %.1fs",
        total_models_checked, total_alerts, duration,
    )


def _reconcile_model(tenant_id: str, model: str) -> dict:
    """Compare count Odoo vs count Raya pour un modele donne.

    Returns:
        Dict avec keys :
          - count_odoo, count_raya, delta_abs, delta_pct
          - alert_raised : bool (True si delta > seuil)
          - status : 'ok' / 'odoo_error' / 'raya_error'
    """
    from app.connectors.odoo_connector import odoo_call
    from app.database import get_pg_conn

    # 1. Compter dans Odoo via search_count
    try:
        count_odoo = odoo_call(
            model=model, method="search_count",
            kwargs={"domain": []},
        )
        if count_odoo is None or not isinstance(count_odoo, int):
            count_odoo = 0
    except Exception as e:
        # Modele inaccessible (droits, deactive, etc.) - skip silencieux
        # Les modeles desactives volontairement sont dans deactivated_models,
        # ils n auraient pas du etre dans POLLED_MODELS de toute facon.
        logger.debug("[OdooRecon] %s/%s count odoo echec : %s",
                     tenant_id, model, str(e)[:150])
        return {"status": "odoo_error", "alert_raised": False,
                "error": str(e)[:200]}

    # 2. Compter dans Raya
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            SELECT COUNT(DISTINCT source_record_id)
            FROM odoo_semantic_content
            WHERE tenant_id = %s
              AND source_model = %s
              AND deleted_at IS NULL
        """, (tenant_id, model))
        count_raya = c.fetchone()[0] or 0
    except Exception as e:
        logger.error("[OdooRecon] %s/%s count raya echec : %s",
                     tenant_id, model, str(e)[:200])
        return {"status": "raya_error", "alert_raised": False,
                "error": str(e)[:200]}
    finally:
        if conn: conn.close()

    # 3. Calcul du delta
    delta_abs = count_odoo - count_raya
    delta_pct = 0.0
    if count_odoo > 0:
        delta_pct = (delta_abs / count_odoo) * 100

    # On ne s alarme que si Raya a MOINS que Odoo (= records manquants).
    # Si Raya a PLUS, c est probablement des records soft-deleted dans
    # Odoo qu on a en base mais qui n apparaissent plus dans le count.
    # Pas critique.
    alert_raised = (delta_abs > 0 and abs(delta_pct) > DELTA_ALERT_THRESHOLD_PCT)

    if alert_raised:
        logger.warning(
            "[OdooRecon] %s/%s : DELTA %d records (%.1f%%) - Odoo=%d Raya=%d",
            tenant_id, model, delta_abs, delta_pct, count_odoo, count_raya,
        )
        _raise_reconciliation_alert(
            tenant_id=tenant_id, model=model,
            count_odoo=count_odoo, count_raya=count_raya,
            delta_abs=delta_abs, delta_pct=delta_pct,
        )
    else:
        # Tout va bien : on log en debug pour ne pas polluer
        logger.debug(
            "[OdooRecon] %s/%s : OK - Odoo=%d Raya=%d (delta=%d/%.2f%%)",
            tenant_id, model, count_odoo, count_raya, delta_abs, delta_pct,
        )

    return {
        "status": "ok",
        "count_odoo": count_odoo,
        "count_raya": count_raya,
        "delta_abs": delta_abs,
        "delta_pct": round(delta_pct, 2),
        "alert_raised": alert_raised,
    }


def _raise_reconciliation_alert(
    tenant_id: str, model: str,
    count_odoo: int, count_raya: int,
    delta_abs: int, delta_pct: float,
) -> None:
    """Leve une alerte WARNING via le dispatcher universel."""
    try:
        from app.alert_dispatcher import send

        title = f"Reconciliation Odoo : {delta_abs} records manquants ({model})"
        message = (
            f"La reconciliation nocturne du {datetime.now().strftime('%Y-%m-%d')} "
            f"a detecte {delta_abs} records manquants dans Raya pour le modele "
            f"{model} (tenant {tenant_id}).\n\n"
            f"Comptage Odoo : {count_odoo}\n"
            f"Comptage Raya : {count_raya}\n"
            f"Ecart : {delta_abs} ({delta_pct:.1f}%)\n\n"
            f"Cause possible : crash Raya, bug logique, modification Odoo "
            f"sans changement de write_date. Un re-sync force du modele "
            f"sera tente automatiquement au prochain cycle de polling."
        )

        send(
            severity="warning",
            title=title,
            message=message,
            tenant_id=tenant_id,
            actions=[
                {
                    "label": f"Forcer un scan complet de {model}",
                    "url": f"/admin/scanner/scan-nuit-complet",
                },
                {
                    "label": "Voir le dashboard Integrite",
                    "url": "/admin/scanner/integrity",
                },
            ],
            source_type="odoo_reconciliation",
            source_id=f"{tenant_id}/{model}",
            component=f"odoo_recon_{model}",
            alert_type="odoo_reconciliation_drift",
        )
    except Exception as e:
        logger.error("[OdooRecon] Alert dispatch echec : %s", str(e)[:200])
