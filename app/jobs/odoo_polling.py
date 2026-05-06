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

INSTRUMENTATION CONNEXIONS UNIVERSELLES (1er mai 2026, Semaine 2) :
─────────────────────────────────────────────────────────────────────
A chaque tick, on log dans connection_health_events pour le liveness check
universel. Voir docs/vision_connexions_universelles_01mai.md.

Le polling Odoo est ainsi visible dans /admin/health/page comme toutes les
autres connexions Raya, et beneficie du meme filet d alerte (silence
detecte > 6 min = alerte automatique).
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
# NOTE 26/04 : mail.activity desactive pour le meme motif (boucle
# "Invalid field 'name' on model 'mail.activity'" qui polluait les logs
# en boucle a chaque webhook). Un fix propre est planifie : regenerer
# le manifest de mail.activity en utilisant display_name ou summary
# au lieu de name (cf. roadmap connexion Odoo durable).
POLLED_MODELS = [
    "sale.order", "sale.order.line", "crm.lead",
    "calendar.event", "res.partner",
    "account.move", "account.payment",
    "of.planning.tour", "of.planning.task",
    "of.planning.intervention.template",
    # "of.survey.answers",           # DESACTIVE - manifest champ name invalide
    # "of.survey.user_input.line",   # DESACTIVE - manifest champ name invalide
    # "mail.activity",               # DESACTIVE 26/04 - meme symptome
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
    last_seen. Retourne un dict avec les stats.

    RESILIENCE (Semaine 2 - Etape 2.4) : l appel XML-RPC est wrappe par
    @protected pour gerer automatiquement les micro-coupures (retry
    immediat) et le rate limiting. Le circuit breaker n est pas active
    sur _poll_model car la granularite est par modele : on prefere que
    record_poll_attempt() agrege les erreurs au niveau du tenant et que
    le seuil consecutive_failures de connection_health declenche le
    circuit breaker au bon niveau.
    """
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

    # Wrap l appel XML-RPC avec resilience (retry immediat + classification)
    connection_id = _get_odoo_connection_id(tenant_id)
    try:
        if connection_id:
            from app.connection_resilience import protected
            # On cree une fonction locale decoree juste pour cet appel.
            # record_in_health=False car on ecrit nous-memes l event au niveau
            # du cycle complet (pas par modele).
            @protected(
                connection_id=connection_id,
                max_immediate_retries=2,   # 2 retries au lieu de 3 (par modele)
                max_backoff_retries=0,      # pas de backoff (le scheduler retentera dans 2 min)
                record_in_health=False,
            )
            def _do_search_read():
                return odoo_call(
                    model=model, method="search_read",
                    kwargs={
                        "domain": [["write_date", ">", since]],
                        "fields": ["id", "write_date"],
                        "limit": MAX_RECORDS_PER_TICK,
                        "order": "write_date asc",
                    },
                )
            records = _do_search_read()
        else:
            # Fallback sans resilience si pas de connection_id (ne devrait pas arriver)
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


def _get_odoo_connection_id(tenant_id: str) -> Optional[int]:
    """Retourne l id de la connexion Odoo dans tenant_connections pour ce tenant.
    Cherche tool_type='odoo'. Retourne None si pas trouve (ne devrait pas
    arriver car la connexion Odoo est creee a la connexion initiale du tenant).
    """
    from app.database import get_pg_conn
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            SELECT id FROM tenant_connections
            WHERE tenant_id = %s AND tool_type = 'odoo'
            ORDER BY id LIMIT 1
        """, (tenant_id,))
        row = c.fetchone()
        return row[0] if row else None
    except Exception as e:
        logger.debug("[OdooPolling] _get_odoo_connection_id echec : %s", str(e)[:200])
        return None
    finally:
        if conn: conn.close()


def _ensure_health_registered(tenant_id: str, connection_id: int) -> None:
    """Inscrit la connexion Odoo dans connection_health (idempotent).
    Appele au demarrage de chaque cycle. Si deja inscrit, ne fait rien
    grace a UPSERT.
    """
    try:
        from app.connection_health import register_connection
        # Polling toutes les 2 min, seuil alerte = 3x = 6 min
        register_connection(
            connection_id=connection_id,
            tenant_id=tenant_id,
            username="system",  # le polling est cross-user, pas attache a un user
            connection_type="odoo",
            expected_poll_interval_seconds=120,
            alert_threshold_seconds=360,
        )
    except Exception as e:
        logger.debug("[OdooPolling] register_connection echec : %s", str(e)[:200])


def run_odoo_polling():
    """Fonction principale declenchee par APScheduler toutes les 2 min.
    Parcourt les modeles webhookes pour chaque tenant et enqueue les
    changements depuis le dernier poll.

    INSTRUMENTATION CONNEXIONS UNIVERSELLES :
    A chaque tick, on log un event dans connection_health_events.
    - Si tout marche : status='ok' (meme si 0 records, c est OK)
    - Si fetch_error sur >50% des modeles : status='internal_error'
    """
    from datetime import datetime as _dt
    poll_started = _dt.now()

    tenants = _get_tenants_to_poll()
    if not tenants:
        logger.debug("[OdooPolling] Aucun tenant configure, skip")
        return

    for tenant_id in tenants:
        # Inscription dans connection_health (idempotent)
        connection_id = _get_odoo_connection_id(tenant_id)
        if connection_id:
            _ensure_health_registered(tenant_id, connection_id)

            # Etape 5 (06/05/2026) : polling adaptatif jour/nuit. Skip
            # si hors heures ouvrees Paris ET dernier poll < 30 min.
            try:
                from app.polling_schedule import should_skip_poll_now
                if should_skip_poll_now(connection_id):
                    logger.debug(
                        "[OdooPolling] skip tenant=%s (hors heures ouvrees + dernier poll < 30 min)",
                        tenant_id,
                    )
                    continue
            except Exception as _e_sk:
                logger.warning("[OdooPolling] should_skip check echoue : %s", str(_e_sk)[:120])

        total_new = 0
        total_enq = 0
        errors = 0
        models_polled = 0
        for model in POLLED_MODELS:
            models_polled += 1
            try:
                result = _poll_model(tenant_id, model)
                total_new += result.get("new_records", 0)
                total_enq += result.get("enqueued", 0)
                if result.get("status") == "fetch_error":
                    errors += 1
            except Exception as e:
                errors += 1
                logger.error("[OdooPolling] %s/%s crash : %s",
                             tenant_id, model, str(e)[:200])
        if total_new > 0:
            logger.info("[OdooPolling] tenant=%s : %d records vus, %d enqueues (14 modeles)",
                        tenant_id, total_new, total_enq)

        # LIVENESS CHECK : log de la tentative dans connection_health_events
        if connection_id:
            try:
                from app.connection_health import record_poll_attempt
                duration_ms = int((_dt.now() - poll_started).total_seconds() * 1000)
                # Status global : ok si <50% des modeles ont echoue, sinon internal_error
                if errors >= models_polled / 2:
                    status = "internal_error"
                    error_detail = f"{errors}/{models_polled} modeles en erreur"
                else:
                    status = "ok"
                    error_detail = None if errors == 0 else f"{errors} modele(s) en erreur (non bloquant)"

                record_poll_attempt(
                    connection_id=connection_id,
                    status=status,
                    items_seen=total_new,
                    items_new=total_enq,
                    duration_ms=duration_ms,
                    error_detail=error_detail,
                    poll_started_at=poll_started,
                )
            except Exception as e:
                logger.debug("[OdooPolling] record_poll_attempt echec : %s", str(e)[:200])
