"""Ronde de nuit webhook — Phase A.2 roadmap v4, annexe Q7.

Objectif : filet de securite pour les webhooks Odoo. Si une regle
base_automation plante silencieusement, les webhooks cessent d arriver et
Raya a une memoire qui vieillit sans s en rendre compte. La ronde de nuit :

  1. A 5h du matin (run_night_patrol) :
     - Interroge Odoo pour lister tous les records modifies dans les
       dernieres 24h (via write_date)
     - Compare avec les webhooks effectivement recus et traites
     - Pour chaque ecart : enqueue le record manquant (rattrapage)
     - Stocke un rapport dans system_alerts

  2. A 7h du matin (send_patrol_alert_if_needed) :
     - Lit le dernier rapport de ronde
     - Si ecart > seuil : envoie une alerte WhatsApp a Guillaume

Pas de canari temps reel (trop de faux positifs chez Couffrant).
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

logger = logging.getLogger("raya.night_patrol")

# Modeles webhookes en temps reel (voir annexe Q2 raya_planning_v4.md)
# Ceux-la doivent normalement arriver via webhook. Si on detecte un ecart
# significatif avec Odoo, c est signe que la regle base_automation a plante.
WEBHOOKED_MODELS = [
    # Socle business
    "sale.order", "sale.order.line", "crm.lead",
    "mail.activity", "calendar.event", "res.partner",
    "account.move", "account.payment",
    # Intervention
    "of.planning.tour", "of.planning.task",
    "of.planning.intervention.template",
    "of.survey.answers", "of.survey.user_input.line",
    "of.custom.document",
]

ALERT_THRESHOLD = 5  # si plus de 5 records manquants, on alerte (legacy)

# Fix 05/05/2026 : seuils refines pour ne plus alerter en orange/rouge
# quand le filet de securite fait son boulot normalement.
# Logique : si rattrapages == missing (= tout a ete enqueue avec succes
# dans la queue), c est un signal POSITIF que le systeme s autorepare.
# Severite info verte sauf si on detecte un vrai probleme.
INFO_THRESHOLD_RATTRAPES_OK = 50    # jusqu a 50 rattrapages reussis = info verte
WARNING_THRESHOLD_MISSING = 100      # >100 missing = warning
CRITICAL_THRESHOLD_MISSING = 500     # >500 missing = critical
CRITICAL_THRESHOLD_FAILED_RATIO = 0.2  # >20% des rattrapages en echec = critical


def _list_odoo_modified_last_24h(model: str) -> set:
    """Retourne l ensemble des record_ids modifies dans Odoo depuis 24h."""
    from app.connectors.odoo_connector import odoo_call
    yesterday = (datetime.now(timezone.utc) - timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")
    try:
        records = odoo_call(
            model=model, method="search_read",
            kwargs={
                "domain": [["write_date", ">=", yesterday]],
                "fields": ["id"],
                "limit": 10000,
                "order": "id asc",
            },
        )
        return set(r["id"] for r in (records or []))
    except Exception as e:
        logger.warning("[NightPatrol] %s fetch Odoo echoue : %s", model, str(e)[:200])
        return set()


def _list_webhook_processed_last_24h(tenant_id: str, model: str) -> set:
    """Retourne l ensemble des record_ids traites via webhook depuis 24h."""
    from app.database import get_pg_conn
    with get_pg_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """SELECT DISTINCT record_id FROM vectorization_queue
               WHERE tenant_id=%s AND source='odoo' AND model_name=%s
                 AND completed_at > NOW() - INTERVAL '24 hours'
                 AND last_error IS NULL""",
            (tenant_id, model),
        )
        return set(r[0] for r in cur.fetchall())


def _enqueue_missing(tenant_id: str, model: str, missing_ids: set) -> int:
    """Rattrape les records manquants en les enqueuant pour vectorisation.
    Retourne le nombre de jobs effectivement crees (hors dedup/replay)."""
    from app.webhook_queue import enqueue
    created = 0
    for rid in sorted(missing_ids)[:500]:  # max 500 rattrapages / tenant / modele
        try:
            result = enqueue(
                tenant_id=tenant_id, source="odoo",
                model_name=model, record_id=rid,
                action="upsert", priority=7,  # priorite basse
                source_info={"via": "night_patrol",
                             "reason": "missing_from_webhooks"},
            )
            if result == "enqueued":
                created += 1
        except Exception as e:
            logger.error("[NightPatrol] enqueue failed %s #%d : %s",
                         model, rid, str(e)[:150])
    return created


def _get_tenants_with_webhook_configured() -> list:
    """Retourne la liste des tenants ayant au moins 1 secret webhook
    configure (donc pour lesquels la ronde de nuit a du sens)."""
    import os
    prefix = "ODOO_WEBHOOK_SECRET_"
    tenants = set()
    for key in os.environ:
        if key.startswith(prefix):
            tenant = key[len(prefix):].lower().strip()
            if tenant:
                tenants.add(tenant)
    return sorted(tenants)


def run_night_patrol():
    """Execute la ronde de nuit : compare Odoo vs webhooks traites, rattrape
    les manquants, stocke un rapport dans system_alerts."""
    import json
    from app.database import get_pg_conn

    tenants = _get_tenants_with_webhook_configured()
    if not tenants:
        logger.info("[NightPatrol] Aucun tenant avec webhook configure, skip")
        return

    logger.info("[NightPatrol] Demarrage ronde - tenants=%s", tenants)
    report = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "tenants": {},
        "total_missing": 0,
        "total_rattrapes": 0,
    }

    for tenant_id in tenants:
        tenant_report = {"models": {}, "missing": 0, "rattrapes": 0}
        for model in WEBHOOKED_MODELS:
            odoo_ids = _list_odoo_modified_last_24h(model)
            webhook_ids = _list_webhook_processed_last_24h(tenant_id, model)
            missing = odoo_ids - webhook_ids
            created = 0
            if missing:
                created = _enqueue_missing(tenant_id, model, missing)
            tenant_report["models"][model] = {
                "odoo_modified_24h": len(odoo_ids),
                "webhook_processed_24h": len(webhook_ids),
                "missing": len(missing),
                "rattrapes_enqueued": created,
            }
            tenant_report["missing"] += len(missing)
            tenant_report["rattrapes"] += created
        report["tenants"][tenant_id] = tenant_report
        report["total_missing"] += tenant_report["missing"]
        report["total_rattrapes"] += tenant_report["rattrapes"]
        logger.info("[NightPatrol] tenant=%s missing=%d rattrapes=%d",
                    tenant_id, tenant_report["missing"], tenant_report["rattrapes"])


    # 3. Stockage du rapport dans system_alerts (1 entree par tenant, upsert)
    report["finished_at"] = datetime.now(timezone.utc).isoformat()
    with get_pg_conn() as conn:
        cur = conn.cursor()
        for tenant_id, tenant_report in report["tenants"].items():
            # Fix 05/05/2026 : refonte severite a 3 niveaux clairs.
            # info verte : filet fait son boulot normalement
            # warning orange : volume anormal a surveiller
            # critical rouge : echecs significatifs ou volume critique
            missing = tenant_report["missing"]
            rattrapes = tenant_report["rattrapes"]
            failed = max(0, missing - rattrapes)
            failed_ratio = (failed / missing) if missing > 0 else 0

            # Refonte 06/05/2026 : messages en francais clair + on
            # n'affiche PAS l'alerte INFO si tout s est bien passe (evite
            # le bruit dans le panel admin pour des operations normales).
            should_skip_alert = False  # par defaut : on cree l alerte

            if missing == 0:
                # Cas 'tout va bien' : pas d alerte du tout, juste log
                should_skip_alert = True
                severity = "info"
                msg = "Aucun mail rattrapage cette nuit (tout est arrive en temps reel)."
            elif (missing <= INFO_THRESHOLD_RATTRAPES_OK and
                  failed_ratio < CRITICAL_THRESHOLD_FAILED_RATIO):
                # Cas 'autoreparation normale' : on log mais on n affiche
                # PAS dans le panel - aucune action requise de l admin
                should_skip_alert = True
                severity = "info"
                msg = (f"{rattrapes} mails rattrapes cette nuit "
                       f"(arrivees sans webhook, recuperees automatiquement).")
            elif (missing >= CRITICAL_THRESHOLD_MISSING or
                  failed_ratio >= CRITICAL_THRESHOLD_FAILED_RATIO):
                # Vraie alerte critique : echecs trop nombreux
                severity = "critical"
                msg = (f"Probleme grave de rattrapage cette nuit : "
                       f"{missing} mails arrivés sans webhook, dont {failed} "
                       f"({failed_ratio:.0%}) n'ont pas pu etre recuperes. "
                       f"Verifie les logs du job webhook_night_patrol.")
            elif missing > WARNING_THRESHOLD_MISSING:
                # Volume anormal : a surveiller
                severity = "warning"
                msg = (f"Volume inhabituel cette nuit : {missing} mails "
                       f"manquants detectes, {rattrapes} rattrapes. "
                       f"Verifier si une boite mail a un probleme.")
            else:
                # Entre INFO_THRESHOLD et WARNING_THRESHOLD : info attentive,
                # on garde dans le panel (volume non negligeable)
                severity = "info"
                msg = (f"{missing} mails manquants cette nuit, "
                       f"{rattrapes} ont ete rattrapes automatiquement.")

            # Si should_skip_alert : on log sans creer d'alerte panel
            if should_skip_alert:
                logger.info("[NightPatrol] %s tenant=%s : %s",
                            severity.upper(), tenant_id, msg)
                continue
            cur.execute(
                """INSERT INTO system_alerts
                   (tenant_id, alert_type, severity, component, message, details, updated_at)
                   VALUES (%s, %s, %s, %s, %s, %s, NOW())
                   ON CONFLICT (tenant_id, alert_type, component) DO UPDATE
                   SET severity=EXCLUDED.severity, message=EXCLUDED.message,
                       details=EXCLUDED.details, acknowledged=FALSE,
                       acknowledged_by=NULL, acknowledged_at=NULL,
                       updated_at=NOW()""",
                (tenant_id, "webhook_night_patrol", severity,
                 "webhook_queue", msg, json.dumps({**tenant_report,
                                                   "report_started_at": report["started_at"],
                                                   "report_finished_at": report["finished_at"]})),
            )
        conn.commit()

    logger.info("[NightPatrol] Ronde terminee - total_missing=%d total_rattrapes=%d",
                report["total_missing"], report["total_rattrapes"])
    return report


def send_patrol_alert_if_needed():
    """A 7h du matin : lit les rapports de ronde de la nuit et envoie une
    alerte WhatsApp a Guillaume si un tenant a des ecarts significatifs.

    Exclut volontairement les rapports 'info' (tout va bien) pour ne pas
    spammer. Seule la severite 'warning' ou plus declenche une alerte."""
    import os
    from app.database import get_pg_conn

    try:
        with get_pg_conn() as conn:
            cur = conn.cursor()
            cur.execute(
                """SELECT tenant_id, message, details
                   FROM system_alerts
                   WHERE alert_type='webhook_night_patrol'
                     AND component='webhook_queue'
                     AND severity IN ('warning', 'critical')
                     AND acknowledged = FALSE
                     AND updated_at > NOW() - INTERVAL '6 hours'""",
            )
            alerts = cur.fetchall()

        if not alerts:
            logger.info("[NightPatrol] Aucune alerte a envoyer")
            return

        # Construction du message consolide (si plusieurs tenants en alerte)
        lines = ["\u26a0\ufe0f Raya - Alerte ronde de nuit webhooks"]
        for tenant_id, msg, details in alerts:
            lines.append(f"\n[{tenant_id}] {msg}")
        body = "\n".join(lines) + "\n\nVerifier les regles base_automation cote OpenFire."


        # Envoi WhatsApp (suivant le pattern heartbeat.py)
        username = os.getenv("APP_USERNAME", "guillaume").strip()
        phone = ""
        try:
            from app.security_users import get_user_phone
            phone = get_user_phone(username) or ""
        except Exception:
            pass
        if not phone:
            phone = (os.getenv(f"NOTIFICATION_PHONE_{username.upper()}", "")
                     or os.getenv("NOTIFICATION_PHONE_DEFAULT", "")).strip()
        if not phone:
            logger.warning("[NightPatrol] Aucun telephone configure, alerte non envoyee")
            return

        try:
            from app.connectors.twilio_connector import send_whatsapp
            send_whatsapp(phone, body)
            logger.info("[NightPatrol] Alerte envoyee a %s (%d tenants concernes)",
                        username, len(alerts))
        except Exception as e:
            logger.error("[NightPatrol] Echec envoi alerte : %s", str(e)[:200])
    except Exception as e:
        logger.error("[NightPatrol] Erreur dans send_patrol_alert_if_needed : %s",
                     str(e)[:300])
