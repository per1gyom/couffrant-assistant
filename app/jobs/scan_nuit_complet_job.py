"""Scan de nuit COMPLET orchestre cote Railway (Option 1 validee 19/04/2026).

Equivalent de scripts/scan_nuit_complet.py mais execute sur Railway (qui a
toutes les credentials OpenAI/Odoo) plutot que sur le Mac de Guillaume.

Enchaine en thread daemon les 4 etapes :
  1. mail.tracking.value jusqu a 25000 records (~22 850 attendus)
  2. res.partner jusqu a 1226 records (rattrapage des 100 manquants)
  3. product.template filtre sur articles UTILES (devis + kits, ~500-2000)
  4. P2 COMPLET volume reel (13 modeles, exclut mail.message + of.service.request)

Toutes les etapes en purge_first=False (non destructif, idempotent).
Duree totale : 2h a 3h. Le navigateur peut etre ferme, Railway tourne seul.

Le suivi se fait visuellement via le dashboard 📊 Integrite du panel admin.
"""

import logging
import threading
import time
from typing import Optional

logger = logging.getLogger("raya.scan_nuit_complet")

# Modeles P2 a exclure du scan complet (etape 4)
P2_MODELS_TO_SKIP = {"mail.message", "of.service.request"}

# Verrou pour empecher le lancement simultane de plusieurs scans de nuit
_scan_nuit_lock = threading.Lock()
_scan_nuit_running = False


def _wait_run_completion(run_id: str, max_seconds: int = 3600) -> dict:
    """Poll le status toutes les 10s jusqu a fin du run. Meme logique que
    scripts/scan_nuit.py mais adapte thread Railway."""
    from app.scanner import orchestrator
    start = time.time()
    last_log = 0
    while time.time() - start < max_seconds:
        status = orchestrator.get_run_status(run_id)
        if not status:
            logger.warning("[ScanNuit] run %s introuvable", run_id[:8])
            return {}
        st = status.get("status", "")
        if st in ("ok", "error", "stopped"):
            return status
        # Log periodique toutes les 60s (moins verbose qu en terminal)
        if time.time() - last_log > 60:
            prog = status.get("progress") or {}
            stats = status.get("stats") or {}
            logger.info("[ScanNuit] %s | model=%s | chunks=%d err=%d",
                        st, prog.get("current_model", "?"),
                        stats.get("chunks_vectorized", 0),
                        stats.get("errors", 0))
            last_log = time.time()
        time.sleep(10)
    logger.warning("[ScanNuit] TIMEOUT run %s apres %ds", run_id[:8], max_seconds)
    return orchestrator.get_run_status(run_id) or {}


def _etape1_mail_tracking(tenant_id: str, source: str) -> dict:
    """Etape 1 : complete mail.tracking.value jusqu a 25000 records."""
    from app.scanner.runner import start_scan_p1
    from app.database import get_pg_conn

    logger.info("[ScanNuit] ETAPE 1 : mail.tracking.value")
    with get_pg_conn() as conn:
        cur = conn.cursor()
        cur.execute("""SELECT model_name FROM connector_schemas
                       WHERE tenant_id=%s AND source=%s AND enabled=TRUE
                         AND priority=1""", (tenant_id, source))
        all_p1 = [r[0] for r in cur.fetchall()]
    record_limits = {m: 0 for m in all_p1 if m != "mail.tracking.value"}

    run_id = start_scan_p1(
        tenant_id=tenant_id, source=source,
        priority_max=1, purge_first=False,
        run_type="complete", record_limits=record_limits,
    )
    logger.info("[ScanNuit] Etape 1 run_id=%s", run_id[:8])
    return _wait_run_completion(run_id, max_seconds=2400)  # 40 min max


def _etape2_res_partner(tenant_id: str, source: str) -> dict:
    """Etape 2 : rattrapage res.partner (idempotent)."""
    from app.scanner.runner import start_scan_p1
    from app.database import get_pg_conn

    logger.info("[ScanNuit] ETAPE 2 : res.partner")
    with get_pg_conn() as conn:
        cur = conn.cursor()
        cur.execute("""SELECT model_name FROM connector_schemas
                       WHERE tenant_id=%s AND source=%s AND enabled=TRUE
                         AND priority=1""", (tenant_id, source))
        all_p1 = [r[0] for r in cur.fetchall()]
    record_limits = {m: 0 for m in all_p1 if m != "res.partner"}

    run_id = start_scan_p1(
        tenant_id=tenant_id, source=source,
        priority_max=1, purge_first=False,
        run_type="complete", record_limits=record_limits,
    )
    logger.info("[ScanNuit] Etape 2 run_id=%s", run_id[:8])
    return _wait_run_completion(run_id, max_seconds=600)  # 10 min max


def _etape3_products_utiles(tenant_id: str, source: str) -> dict:
    """Etape 3 : product.template FILTRE sur articles utilises en devis + kits.
    Evite de vectoriser les 133 112 articles du catalogue complet."""
    from app.scanner.runner import start_scan_p1
    from app.connectors.odoo_connector import odoo_call
    from app.database import get_pg_conn

    logger.info("[ScanNuit] ETAPE 3 : product.template filtre (devis + kits)")

    # 3.1 : product_ids de sale.order.line (articles en devis)
    try:
        lines = odoo_call(
            model="sale.order.line", method="search_read",
            kwargs={"domain": [], "fields": ["product_id"], "limit": 100000},
        )
        devis_product_ids = {l["product_id"][0] for l in (lines or [])
                             if l.get("product_id") and isinstance(l["product_id"], list)}
        logger.info("[ScanNuit] 3.1 - %d product_ids distincts en devis", len(devis_product_ids))
    except Exception as e:
        logger.error("[ScanNuit] 3.1 crash : %s", str(e)[:200])
        return {"status": "error", "error": f"sale.order.line fetch: {str(e)[:200]}"}

    # 3.2 : product_ids de of.product.pack.lines (composants de kits)
    try:
        pack_lines = odoo_call(
            model="of.product.pack.lines", method="search_read",
            kwargs={"domain": [], "fields": ["product_id"], "limit": 100000},
        )
        kits_product_ids = {l["product_id"][0] for l in (pack_lines or [])
                            if l.get("product_id") and isinstance(l["product_id"], list)}
        logger.info("[ScanNuit] 3.2 - %d product_ids distincts dans kits", len(kits_product_ids))
    except Exception as e:
        logger.warning("[ScanNuit] 3.2 of.product.pack.lines indispo : %s", str(e)[:200])
        kits_product_ids = set()

    # 3.3 : Remontee vers product.template via product_tmpl_id
    product_product_ids = devis_product_ids | kits_product_ids
    if not product_product_ids:
        logger.info("[ScanNuit] 3.3 - aucun produit utilise detecte, etape skipee")
        return {"status": "ok", "skipped": True, "reason": "no_useful_products"}
    try:
        products = odoo_call(
            model="product.product", method="search_read",
            kwargs={"domain": [["id", "in", sorted(product_product_ids)]],
                    "fields": ["product_tmpl_id"],
                    "limit": len(product_product_ids) + 100},
        )
        template_ids = sorted({p["product_tmpl_id"][0] for p in (products or [])
                               if p.get("product_tmpl_id") and isinstance(p["product_tmpl_id"], list)})
        logger.info("[ScanNuit] 3.3 - %d product.template uniques a vectoriser", len(template_ids))
    except Exception as e:
        logger.error("[ScanNuit] 3.3 crash : %s", str(e)[:200])
        return {"status": "error", "error": f"product.product fetch: {str(e)[:200]}"}

    # 3.4 : Scan cible avec model_domains
    from app.database import get_pg_conn
    with get_pg_conn() as conn:
        cur = conn.cursor()
        cur.execute("""SELECT model_name FROM connector_schemas
                       WHERE tenant_id=%s AND source=%s AND enabled=TRUE
                         AND priority=1""", (tenant_id, source))
        all_p1 = [r[0] for r in cur.fetchall()]
    record_limits = {m: 0 for m in all_p1 if m != "product.template"}
    model_domains = {"product.template": [["id", "in", template_ids]]}

    run_id = start_scan_p1(
        tenant_id=tenant_id, source=source,
        priority_max=1, purge_first=False,
        run_type="complete",
        record_limits=record_limits,
        model_domains=model_domains,
    )
    logger.info("[ScanNuit] Etape 3 run_id=%s (scan cible sur %d templates)",
                run_id[:8], len(template_ids))
    return _wait_run_completion(run_id, max_seconds=3600)  # 1h max


def _etape4_p2_complet(tenant_id: str, source: str) -> dict:
    """Etape 4 : scan P2 complet au volume reel sur les 13 modeles qui marchent.
    Exclut mail.message (droits Odoo bloques) et of.service.request (2 records)."""
    from app.scanner.runner import start_scan_p1
    from app.database import get_pg_conn

    logger.info("[ScanNuit] ETAPE 4 : P2 complet volume reel")
    with get_pg_conn() as conn:
        cur = conn.cursor()
        cur.execute("""SELECT model_name, priority FROM connector_schemas
                       WHERE tenant_id=%s AND source=%s AND enabled=TRUE
                         AND priority<=2""", (tenant_id, source))
        all_models = cur.fetchall()
    p1_models = [m for m, p in all_models if p == 1]
    p2_models = [m for m, p in all_models if p == 2]

    # record_limits : 0 pour tous les P1 (deja scannes en etapes 1-3)
    # 0 pour les P2 a skipper
    # Pas de cle pour les P2 a scanner = volume reel
    record_limits = {m: 0 for m in p1_models}
    for m in p2_models:
        if m in P2_MODELS_TO_SKIP:
            record_limits[m] = 0
    logger.info("[ScanNuit] Etape 4 : %d P1 skipped, %d/%d P2 a scanner",
                len(p1_models),
                len(p2_models) - len(P2_MODELS_TO_SKIP & set(p2_models)),
                len(p2_models))

    run_id = start_scan_p1(
        tenant_id=tenant_id, source=source,
        priority_max=2, purge_first=False,
        run_type="complete", record_limits=record_limits,
    )
    logger.info("[ScanNuit] Etape 4 run_id=%s", run_id[:8])
    return _wait_run_completion(run_id, max_seconds=10800)  # 3h max


def _run_complete_overnight_scan(tenant_id: str = "couffrant_solar", source: str = "odoo"):
    """Fonction principale exécutée en thread daemon.
    Enchaine les 4 étapes. Chacune dans un try/except pour ne pas bloquer
    les suivantes si l'une plante."""
    global _scan_nuit_running
    from app.database import get_pg_conn

    try:
        # Chunks AVANT
        with get_pg_conn() as conn:
            cur = conn.cursor()
            cur.execute("""SELECT COUNT(*) FROM odoo_semantic_content
                           WHERE tenant_id=%s AND deleted_at IS NULL""", (tenant_id,))
            chunks_before = cur.fetchone()[0]

        logger.info("[ScanNuit] ===== DEMARRAGE SCAN NUIT COMPLET =====")
        logger.info("[ScanNuit] Tenant=%s Source=%s", tenant_id, source)
        logger.info("[ScanNuit] Chunks AVANT : %d", chunks_before)

        results = {}
        for name, fn in [
            ("etape1_mail_tracking", _etape1_mail_tracking),
            ("etape2_res_partner", _etape2_res_partner),
            ("etape3_products_utiles", _etape3_products_utiles),
            ("etape4_p2_complet", _etape4_p2_complet),
        ]:
            try:
                logger.info("[ScanNuit] >>> Demarrage %s", name)
                results[name] = fn(tenant_id, source)
                logger.info("[ScanNuit] <<< %s termine : %s",
                            name, results[name].get("status", "?"))
            except Exception as e:
                logger.error("[ScanNuit] CRASH %s : %s", name, str(e)[:300])
                results[name] = {"status": "crash", "error": str(e)[:300]}


        # Chunks APRES + stockage du recap dans system_alerts
        import json
        with get_pg_conn() as conn:
            cur = conn.cursor()
            cur.execute("""SELECT COUNT(*) FROM odoo_semantic_content
                           WHERE tenant_id=%s AND deleted_at IS NULL""", (tenant_id,))
            chunks_after = cur.fetchone()[0]
            delta = chunks_after - chunks_before
            summary = {name: r.get("status", "?") for name, r in results.items()}
            msg = f"Scan nuit complet termine. Chunks {chunks_before} -> {chunks_after} (+{delta})"
            logger.info("[ScanNuit] %s", msg)
            logger.info("[ScanNuit] Recap etapes : %s", summary)
            # Stocke dans system_alerts pour que le dashboard puisse l afficher
            severity = "info" if delta > 0 else "warning"
            cur.execute(
                """INSERT INTO system_alerts
                   (tenant_id, alert_type, severity, component, message, details, updated_at)
                   VALUES (%s, %s, %s, %s, %s, %s, NOW())
                   ON CONFLICT (tenant_id, alert_type, component) DO UPDATE
                   SET severity=EXCLUDED.severity, message=EXCLUDED.message,
                       details=EXCLUDED.details, acknowledged=FALSE,
                       acknowledged_by=NULL, acknowledged_at=NULL,
                       updated_at=NOW()""",
                (tenant_id, "scan_nuit_complet", severity, "scanner", msg,
                 json.dumps({"chunks_before": chunks_before,
                             "chunks_after": chunks_after,
                             "delta": delta, "etapes": summary})),
            )
            conn.commit()
    finally:
        with _scan_nuit_lock:
            _scan_nuit_running = False


def launch_async(tenant_id: str = "couffrant_solar", source: str = "odoo") -> dict:
    """Lance le scan de nuit en thread daemon. Appele par l endpoint admin.
    Retourne immediatement. Si deja en cours, refuse (verrou global).

    Returns :
      {"status": "started", "tenant_id": "..."} si OK
      {"status": "already_running"} si un scan est deja en cours
    """
    global _scan_nuit_running
    with _scan_nuit_lock:
        if _scan_nuit_running:
            logger.warning("[ScanNuit] refuse : un scan est deja en cours")
            return {"status": "already_running",
                    "message": "Un scan de nuit est deja en cours. Attendez qu il se termine."}
        _scan_nuit_running = True

    t = threading.Thread(
        target=_run_complete_overnight_scan,
        args=(tenant_id, source),
        name="scan-nuit-complet",
        daemon=True,
    )
    t.start()
    logger.info("[ScanNuit] Thread lance (tenant=%s source=%s)", tenant_id, source)
    return {
        "status": "started",
        "tenant_id": tenant_id,
        "source": source,
        "message": "Scan de nuit complet lance en arriere-plan. Suivi via 📊 Integrite.",
        "estimated_duration": "2h a 3h",
    }


def is_running() -> bool:
    """Retourne True si un scan de nuit est en cours."""
    with _scan_nuit_lock:
        return _scan_nuit_running
