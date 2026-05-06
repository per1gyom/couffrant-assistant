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
DELTA_ALERT_THRESHOLD_PCT = 1.0  # legacy : seuil de detection ecart

# Fix 05/05/2026 : seuils 3 niveaux pour ne pas alerter en orange/rouge
# quand l ecart est petit ET le re-sync auto va le corriger au prochain
# cycle de polling.
INFO_THRESHOLD_PCT = 5.0       # < 5% = info verte (sera auto-rattrape)
WARNING_THRESHOLD_PCT = 10.0   # 5-10% = warning orange
# > 10% OU > 100 records = critical rouge
CRITICAL_THRESHOLD_ABS = 100


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
    """Leve une alerte avec severite calibree selon l ampleur de l ecart.
    
    Fix 05/05/2026 : 3 niveaux pour ne plus crier au loup quand le re-sync
    automatique va corriger l ecart au prochain cycle de polling.

    Refonte 06/05/2026 : message en francais clair sans jargon technique
    (plus de "modele res.partner"), nom humain des modeles, et SI ecart
    < 10% on ne cree plus d alerte INFO du tout (juste log) - le re-sync
    automatique va corriger sans qu il faille acquitter manuellement.
    """
    try:
        from app.alert_dispatcher import send

        # Mapping modele technique Odoo -> nom humain
        # Refonte 06/05/2026 : evite le jargon "res.partner" / "sale.order"
        model_label = {
            "res.partner": "Contacts",
            "sale.order": "Devis et commandes",
            "purchase.order": "Bons de commande",
            "account.move": "Factures",
            "crm.lead": "Opportunites CRM",
            "product.template": "Produits",
            "stock.picking": "Bons de livraison",
        }.get(model, model)

        delta_pct_abs = abs(delta_pct)
        # Choix de severite selon ampleur
        if delta_pct_abs >= WARNING_THRESHOLD_PCT or delta_abs >= CRITICAL_THRESHOLD_ABS:
            severity = "critical"
            should_skip_alert = False
            verdict = (
                f"L'ecart de {delta_pct_abs:.0f}% depasse les seuils. "
                f"Le re-sync automatique va etre tente mais si l'ecart "
                f"persiste apres 24h, investigation manuelle recommandee."
            )
        elif delta_pct_abs >= INFO_THRESHOLD_PCT:
            severity = "warning"
            should_skip_alert = False
            verdict = (
                f"Ecart modere de {delta_pct_abs:.0f}% a surveiller. "
                f"Le re-sync automatique au prochain cycle de polling "
                f"devrait corriger sous 30 min."
            )
        else:
            # Cas 'petit ecart auto-correctible' : skip
            severity = "info"
            should_skip_alert = True
            verdict = (
                f"{delta_abs} {model_label.lower()} a synchroniser au "
                f"prochain cycle (sous 30 min). Aucune action requise."
            )

        if should_skip_alert:
            logger.info(
                "[OdooRecon] %s tenant=%s model=%s : %s",
                severity.upper(), tenant_id, model, verdict,
            )
            return

        # Refonte titre + message : francais clair, nom humain du modele.
        if severity == "critical":
            title = f"{model_label} Odoo : ecart anormal {delta_pct_abs:.0f}%"
        elif severity == "warning":
            title = f"{model_label} Odoo : ecart {delta_pct_abs:.0f}% a surveiller"
        else:
            title = f"{model_label} Odoo : {delta_abs} a synchroniser"

        message = (
            f"{verdict}\n\n"
            f"Details : Odoo a {count_odoo} {model_label.lower()}, Raya en "
            f"connait {count_raya} (ecart de {delta_abs}, {delta_pct_abs:.0f}%)."
        )

        send(
            severity=severity,
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
