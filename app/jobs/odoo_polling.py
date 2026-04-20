"""Polling Odoo cote Raya — palliatif temps-reel en attendant le module
OpenFire custom (voir docs/demande_openfire_webhooks_temps_reel.md).

Odoo 16 Community bloque les imports dans les actions base_automation,
ce qui empeche d implementer les vrais webhooks. On contourne en faisant
un polling cote Raya :

  Toutes les 2 min, pour chaque modele webhooke :
    1. Lire les records Odoo ou write_date > last_seen
    2. Les enqueuer dans vectorization_queue (comme un webhook aurait fait)
    3. Mettre a jour last_seen

Tout le reste de l infrastructure webhook (queue, worker, dedup, anti-rejeu,
dashboard, ronde de nuit 5h) reste valable et s applique a ces jobs enqueues.

Le jour ou OpenFire livre le module custom, on desactive ce polling et les
vrais webhooks prennent le relais sans autre modification.
"""

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

logger = logging.getLogger("raya.odoo_polling")

# Liste identique aux modeles que le module OpenFire couvrira plus tard
# (voir webhook_night_patrol.WEBHOOKED_MODELS pour coherence)
# NOTE 20/04 : of.survey.answers et of.survey.user_input.line sont
# temporairement desactives car leur manifest reference le champ 'name'
# qui n existe pas sur ces modeles chez Couffrant (boucle d erreur
# "Invalid field 'name' on model of.survey.answers"). A re-activer
# apres purge/regeneration de leurs manifests.
POLLED_MODELS = [
    "sale.order", "sale.order.line", "crm.lead",
    "mail.activity", "calendar.event", "res.partner",
    "account.move", "account.payment",
    "of.planning.tour", "of.planning.task",
    "of.planning.intervention.template",
    # "of.survey.answers",           # DESACTIVE - manifest champ name invalide
    # "of.survey.user_input.line",   # DESACTIVE - manifest champ name invalide
    "of.custom.document",
]

# Limite de safety : max records a enqueue par tick (evite explosion si le
# systeme n a pas tourne longtemps)
MAX_RECORDS_PER_TICK = 500


def _get_last_seen(tenant_id: str, model: str) -> Optional[datetime]:
    """Lit la derniere write_date vue pour ce (tenant, modele).
    Stocke dans system_alerts (reutilise la table existante, alert_type
    = 'odoo_polling_cursor', component = model).
    """
    from app.database import get_pg_conn
    with get_pg_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """SELECT details->>'last_seen_iso' FROM system_alerts
               WHERE tenant_id=%s AND alert_type='odoo_polling_cursor'
                 AND component=%s""",
            (tenant_id, model),
        )
        row = cur.fetchone()
    if not row or not row[0]:
        return None
    try:
        return datetime.fromisoformat(row[0])
    except ValueError:
        return None


def _set_last_seen(tenant_id: str, model: str, last_seen: datetime, count: int):
    """Memorise la nouvelle derniere write_date vue. Upsert dans system_alerts."""
    import json
    from app.database import get_pg_conn
    with get_pg_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO system_alerts
               (tenant_id, alert_type, severity, component, message, details, updated_at)
               VALUES (%s, 'odoo_polling_cursor', 'info', %s, %s, %s, NOW())
               ON CONFLICT (tenant_id, alert_type, component) DO UPDATE
               SET message=EXCLUDED.message, details=EXCLUDED.details, updated_at=NOW()""",
            (tenant_id, model,
             f"Dernier poll : {count} records enqueues",
             json.dumps({"last_seen_iso": last_seen.isoformat(),
                         "last_count": count})),
        )
        conn.commit()


def _poll_model(tenant_id: str, model: str) -> dict:
    """Interroge Odoo pour ce modele, enqueue les records modifies depuis
    last_seen. Retourne un dict avec les stats."""
    from app.connectors.odoo_connector import odoo_call
    from app.webhook_queue import enqueue
    import secrets

    last_seen = _get_last_seen(tenant_id, model)
    if last_seen is None:
        # Premier passage : on prend les 10 dernieres minutes pour ne pas
        # tout re-enqueuer (les chunks existants vont etre UPDATE toutes ces
        # minutes ; ca commence a creer de la charge sans vraie plus-value).
        # Le scan complet a deja tout couvert.
        last_seen = datetime.now(timezone.utc) - timedelta(minutes=10)

    since = last_seen.strftime("%Y-%m-%d %H:%M:%S")
    try:
        records = odoo_call(
            model=model, method="search_read",
            kwargs={
                "domain": [["write_date", ">", since]],
                "fields": ["id", "write_date"],
                "limit": MAX_RECORDS_PER_TICK,
                "order": "write_date asc",
            },
        )
    except Exception as e:
        logger.warning("[OdooPolling] %s fetch failed : %s", model, str(e)[:200])
        return {"model": model, "status": "fetch_error", "error": str(e)[:200]}

    records = records or []
    if not records:
        return {"model": model, "status": "ok", "new_records": 0}

    # Enqueue chaque record via la queue webhook (meme chemin que l aurait
    # fait un webhook Odoo : dedup 5s + anti-rejeu + worker async).
    enqueued = 0
    deduped = 0
    max_write_date = last_seen
    for rec in records:
        # Nonce unique par record+poll (anti-rejeu dans vectorization_queue)
        nonce = f"poll-{model}-{rec['id']}-{int(datetime.now(timezone.utc).timestamp())}-{secrets.token_hex(6)}"
        try:
            result = enqueue(
                tenant_id=tenant_id, source="odoo",
                model_name=model, record_id=rec["id"],
                action="upsert", nonce=nonce, priority=5,
                source_info={"via": "polling", "write_date": str(rec.get("write_date"))},
            )
            if result == "enqueued":
                enqueued += 1
            elif result == "deduped":
                deduped += 1
        except Exception as e:
            logger.error("[OdooPolling] enqueue failed %s #%d : %s",
                         model, rec["id"], str(e)[:150])
            continue

        # Memorise la write_date max pour curseur
        wd_str = rec.get("write_date")
        if wd_str:
            try:
                # Odoo retourne "YYYY-MM-DD HH:MM:SS" en UTC
                wd = datetime.strptime(wd_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
                if wd > max_write_date:
                    max_write_date = wd
            except (ValueError, TypeError):
                pass

    # Avance le curseur
    _set_last_seen(tenant_id, model, max_write_date, enqueued)
    logger.info("[OdooPolling] %s : %d nouveaux, %d enqueues, %d dedupes",
                model, len(records), enqueued, deduped)
    return {"model": model, "status": "ok", "new_records": len(records),
            "enqueued": enqueued, "deduped": deduped}


def _get_tenants_to_poll() -> list:
    """Memes tenants que la ronde de nuit : ceux qui ont un secret webhook
    configure. Permet de controler le polling via Railway simplement en
    ajoutant/retirant la variable ODOO_WEBHOOK_SECRET_<TENANT>."""
    prefix = "ODOO_WEBHOOK_SECRET_"
    tenants = set()
    for key in os.environ:
        if key.startswith(prefix) and os.environ[key]:
            tenant = key[len(prefix):].lower().strip()
            if tenant:
                tenants.add(tenant)
    return sorted(tenants)


def run_odoo_polling():
    """Fonction principale declenchee par APScheduler toutes les 2 min.
    Parcourt les modeles webhookes pour chaque tenant et enqueue les
    changements depuis le dernier poll."""
    tenants = _get_tenants_to_poll()
    if not tenants:
        logger.debug("[OdooPolling] Aucun tenant configure, skip")
        return

    for tenant_id in tenants:
        total_new = 0
        total_enq = 0
        for model in POLLED_MODELS:
            try:
                result = _poll_model(tenant_id, model)
                total_new += result.get("new_records", 0)
                total_enq += result.get("enqueued", 0)
            except Exception as e:
                logger.error("[OdooPolling] %s/%s crash : %s",
                             tenant_id, model, str(e)[:200])
        if total_new > 0:
            logger.info("[OdooPolling] tenant=%s : %d records vus, %d enqueues (14 modeles)",
                        tenant_id, total_new, total_enq)
