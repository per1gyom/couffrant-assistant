"""
Script de scan nuit — complement vectorisation pour Couffrant Solar.

Lance EN SEQUENCE :
  1. Complement mail.tracking.value (10000 -> 22850, apres update limite a 25000)
  2. Complement res.partner (1126 -> 1226)
  3. Scan product.template filtre sur articles utilises dans devis + kits

IMPORTANT :
  - purge_first=False partout (non destructif)
  - Script lance MANUELLEMENT par Guillaume avant de se coucher
  - Chaque etape peut echouer independamment sans bloquer les suivantes

Utilisation :
  cd /Users/per1guillaume/couffrant-assistant
  APP_USERNAME=guillaume APP_PASSWORD=x ANTHROPIC_API_KEY=x \\
    PYTHONPATH=. python3.11 scripts/scan_nuit.py
"""

import os
import sys
import time
from datetime import datetime

# Charge .env AVANT import modules app/
from dotenv import load_dotenv
load_dotenv()

from app.scanner.runner import start_scan_p1
from app.scanner import orchestrator
from app.database import get_pg_conn


TENANT = "couffrant"
SOURCE = "odoo"

def log(msg: str):
    """Log avec timestamp Paris (UTC+2 en ete)."""
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def wait_run_completion(run_id: str, max_seconds: int = 3600) -> dict:
    """Poll le status toutes les 10s jusqu a fin du run. Retourne le dict
    de stats final. Max 1h par default."""
    start = time.time()
    last_log = 0
    while time.time() - start < max_seconds:
        status = orchestrator.get_run_status(run_id)
        if not status:
            log(f"  [WARN] run {run_id[:8]} introuvable")
            return {}
        st = status["status"]
        if st in ("ok", "error", "stopped"):
            return status
        # Log periodique toutes les 30s
        if time.time() - last_log > 30:
            prog = status.get("progress") or {}
            stats = status.get("stats") or {}
            log(f"  ... {st} | {prog.get('current_model','?')} | "
                f"{stats.get('chunks_vectorized',0)} chunks, "
                f"{stats.get('errors',0)} erreurs")
            last_log = time.time()
        time.sleep(10)
    log(f"  [TIMEOUT] run {run_id[:8]} toujours pas termine apres {max_seconds}s")
    return orchestrator.get_run_status(run_id) or {}


def print_summary(title: str, status: dict):
    """Affiche un recap lisible d un run termine."""
    stats = status.get("stats") or {}
    log(f"  === {title} ===")
    log(f"     status : {status.get('status')}")
    log(f"     chunks : {stats.get('chunks_vectorized', 0)}")
    log(f"     erreurs: {stats.get('errors', 0)}")
    aborted = stats.get("models_aborted") or []
    if aborted:
        log(f"     ABANDONNES ({len(aborted)}):")
        for a in aborted:
            log(f"       - {a.get('model')} : {(a.get('reason') or '')[:120]}")


# ─── ETAPE 1 : Complement mail.tracking.value (22850) ─────────────

def etape1_mail_tracking():
    """Complete mail.tracking.value. Limite app deja passee a 25000 dans
    MODEL_RECORD_LIMITS, donc on laisse le runner aller jusqu a 25k (ou
    jusqu a epuisement si moins dispo cote Odoo)."""
    log("=" * 70)
    log("ETAPE 1 : mail.tracking.value (target 22850 records)")
    log("=" * 70)
    # record_limits : on skip TOUS les autres modeles en les mettant a 0
    # sauf mail.tracking.value qu on laisse avec la limite MODEL_RECORD_LIMITS
    # (donc on ne le passe PAS dans record_limits pour qu il prenne 25000)
    with get_pg_conn() as conn:
        cur = conn.cursor()
        cur.execute("""SELECT model_name FROM connector_schemas
                       WHERE tenant_id=%s AND source=%s AND enabled=TRUE
                         AND priority=1""", (TENANT, SOURCE))
        all_p1 = [r[0] for r in cur.fetchall()]
    # Skip tout sauf mail.tracking.value
    record_limits = {m: 0 for m in all_p1 if m != "mail.tracking.value"}
    log(f"  Skip {len(record_limits)} modeles, scan uniquement mail.tracking.value")
    run_id = start_scan_p1(
        tenant_id=TENANT, source=SOURCE,
        priority_max=1, purge_first=False,
        run_type="complete",
        record_limits=record_limits,
    )
    log(f"  run_id={run_id[:8]}")
    status = wait_run_completion(run_id, max_seconds=2400)  # 40 min max
    print_summary("ETAPE 1 terminee", status)
    return status


# ─── ETAPE 2 : Complement res.partner (100 manquants) ─────────────

def etape2_res_partner():
    """Complete res.partner. Actuellement 1126/1226. Les 100 manquants
    peuvent etre des records sans display_name. On relance un scan complet
    (INSERT ON CONFLICT UPDATE, idempotent sur les 1126 deja la)."""
    log("=" * 70)
    log("ETAPE 2 : res.partner (target 1226 records)")
    log("=" * 70)
    with get_pg_conn() as conn:
        cur = conn.cursor()
        cur.execute("""SELECT model_name FROM connector_schemas
                       WHERE tenant_id=%s AND source=%s AND enabled=TRUE
                         AND priority=1""", (TENANT, SOURCE))
        all_p1 = [r[0] for r in cur.fetchall()]
    record_limits = {m: 0 for m in all_p1 if m != "res.partner"}
    log(f"  Skip {len(record_limits)} modeles, scan uniquement res.partner")
    run_id = start_scan_p1(
        tenant_id=TENANT, source=SOURCE,
        priority_max=1, purge_first=False,
        run_type="complete",
        record_limits=record_limits,
    )
    log(f"  run_id={run_id[:8]}")
    status = wait_run_completion(run_id, max_seconds=600)  # 10 min max
    print_summary("ETAPE 2 terminee", status)
    return status


# ─── ETAPE 3 : product.template filtre sur articles utiles ────────

def etape3_products_utiles():
    """Scan product.template UNIQUEMENT sur les articles qui sont :
    - soit dans au moins un sale.order.line (utilises en devis)
    - soit dans au moins un of.product.pack.lines (composants de kits)

    Permet de vectoriser ~500-2000 articles pertinents au lieu des 133k
    entiers (massacre pour la DB et pas utile metier).
    """
    log("=" * 70)
    log("ETAPE 3 : product.template filtre (devis + kits)")
    log("=" * 70)
    from app.connectors.odoo_connector import odoo_call

    # 3.1 : Recupere les product_id de sale.order.line
    log("  [3.1] Fetch product_id distincts de sale.order.line...")
    try:
        sol_records = odoo_call(
            model="sale.order.line", method="search_read",
            kwargs={"domain": [], "fields": ["product_id"],
                    "limit": 10000, "order": "id asc"},
        )
        sol_product_ids = set()
        for r in sol_records or []:
            pid = r.get("product_id")
            if isinstance(pid, (list, tuple)) and len(pid) >= 1:
                sol_product_ids.add(pid[0])
        log(f"     {len(sol_records or [])} lignes, {len(sol_product_ids)} products distincts")
    except Exception as e:
        log(f"  [ERREUR 3.1] {str(e)[:200]}")
        return {"status": "error", "error": f"sale.order.line fetch: {str(e)[:200]}"}


    # 3.2 : Recupere les product_id de of.product.pack.lines (kits)
    log("  [3.2] Fetch product_id distincts de of.product.pack.lines...")
    try:
        kit_records = odoo_call(
            model="of.product.pack.lines", method="search_read",
            kwargs={"domain": [], "fields": ["product_id"],
                    "limit": 10000, "order": "id asc"},
        )
        kit_product_ids = set()
        for r in kit_records or []:
            pid = r.get("product_id")
            if isinstance(pid, (list, tuple)) and len(pid) >= 1:
                kit_product_ids.add(pid[0])
        log(f"     {len(kit_records or [])} lignes kits, {len(kit_product_ids)} products distincts")
    except Exception as e:
        log(f"  [ERREUR 3.2] {str(e)[:200]}")
        return {"status": "error", "error": f"of.product.pack.lines fetch: {str(e)[:200]}"}

    # 3.3 : Remonte vers product.template via product.product
    product_product_ids = sol_product_ids | kit_product_ids
    log(f"  [3.3] Union : {len(product_product_ids)} product.product uniques")
    if not product_product_ids:
        log("     [WARN] aucun product.product trouve, abandon etape 3")
        return {"status": "skipped", "reason": "no products found"}
    # Remontee vers product.template via product_tmpl_id
    try:
        pp_records = odoo_call(
            model="product.product", method="search_read",
            kwargs={"domain": [["id", "in", list(product_product_ids)]],
                    "fields": ["product_tmpl_id"], "limit": len(product_product_ids) + 100},
        )
        template_ids = set()
        for r in pp_records or []:
            tid = r.get("product_tmpl_id")
            if isinstance(tid, (list, tuple)) and len(tid) >= 1:
                template_ids.add(tid[0])
        log(f"     {len(pp_records or [])} variants -> {len(template_ids)} templates distincts")
    except Exception as e:
        log(f"  [ERREUR 3.3] {str(e)[:200]}")
        return {"status": "error", "error": f"product.product fetch: {str(e)[:200]}"}


    # 3.4 : Lance le scan product.template avec domain filter
    if not template_ids:
        log("     [WARN] aucun template trouve, abandon etape 3")
        return {"status": "skipped"}
    log(f"  [3.4] Lance scan product.template domain=[id in {len(template_ids)} ids]")
    # On skip tous les autres modeles P1
    with get_pg_conn() as conn:
        cur = conn.cursor()
        cur.execute("""SELECT model_name FROM connector_schemas
                       WHERE tenant_id=%s AND source=%s AND enabled=TRUE
                         AND priority=1""", (TENANT, SOURCE))
        all_p1 = [r[0] for r in cur.fetchall()]
    record_limits = {m: 0 for m in all_p1 if m != "product.template"}
    # Surcharge la limite product.template : on met la taille exacte (pas
    # de 5000 arbitraire, on veut TOUS les templates utiles)
    record_limits["product.template"] = len(template_ids) + 100
    model_domains = {
        "product.template": [["id", "in", sorted(template_ids)]],
    }
    run_id = start_scan_p1(
        tenant_id=TENANT, source=SOURCE,
        priority_max=1, purge_first=False,
        run_type="complete",
        record_limits=record_limits,
        model_domains=model_domains,
    )
    log(f"     run_id={run_id[:8]}")
    status = wait_run_completion(run_id, max_seconds=1800)  # 30 min max
    print_summary("ETAPE 3 terminee", status)
    return status


# ─── MAIN ─────────────────────────────────────────────────────────

def main():
    log("=" * 70)
    log("SCAN NUIT - Complement vectorisation Couffrant Solar")
    log(f"Tenant : {TENANT}  |  Source : {SOURCE}")
    log("=" * 70)

    # Etat DB avant
    with get_pg_conn() as conn:
        cur = conn.cursor()
        cur.execute("""SELECT COUNT(*) FROM odoo_semantic_content
                       WHERE tenant_id=%s AND deleted_at IS NULL""", (TENANT,))
        chunks_before = cur.fetchone()[0]
    log(f"Chunks en DB AVANT : {chunks_before}")
    log("")

    # Execute les 3 etapes en sequence. Chaque etape peut echouer sans
    # bloquer les suivantes.
    results = {}
    try:
        results["etape1_mail_tracking"] = etape1_mail_tracking()
    except Exception as e:
        log(f"[CRASH ETAPE 1] {type(e).__name__}: {e}")
        results["etape1_mail_tracking"] = {"status": "crash", "error": str(e)}
    log("")
    try:
        results["etape2_res_partner"] = etape2_res_partner()
    except Exception as e:
        log(f"[CRASH ETAPE 2] {type(e).__name__}: {e}")
        results["etape2_res_partner"] = {"status": "crash", "error": str(e)}
    log("")
    try:
        results["etape3_products_utiles"] = etape3_products_utiles()
    except Exception as e:
        log(f"[CRASH ETAPE 3] {type(e).__name__}: {e}")
        results["etape3_products_utiles"] = {"status": "crash", "error": str(e)}
    log("")

    # Recap final
    with get_pg_conn() as conn:
        cur = conn.cursor()
        cur.execute("""SELECT COUNT(*) FROM odoo_semantic_content
                       WHERE tenant_id=%s AND deleted_at IS NULL""", (TENANT,))
        chunks_after = cur.fetchone()[0]
    log("=" * 70)
    log("RECAP FINAL")
    log("=" * 70)
    log(f"  Chunks AVANT : {chunks_before}")
    log(f"  Chunks APRES : {chunks_after}")
    log(f"  Delta        : +{chunks_after - chunks_before}")
    for etape, st in results.items():
        log(f"  {etape:30s} : {st.get('status', 'unknown')}")
    log("")
    log("Fin du scan nuit. Tu peux fermer le terminal.")


if __name__ == "__main__":
    main()
