"""
Script de test P2 — scan 200 records par modele sur les 16 modeles P2.

Objectif : identifier rapidement quels modeles P2 peuvent etre scannes
avec succes (comme on a fait pour P1) AVANT de les integrer a un scan
complet. Pattern valide sur P1 le 19/04 : diagnostic des champs casses,
correction des manifests, puis scan complet.

Ce script :
  - Detecte les 16 modeles P2 via priority=2
  - Lance un scan sur 200 records par modele (limite stricte)
  - purge_first=False (aucun impact sur les chunks P1 existants)
  - Affiche un recap par modele : OK / ERREUR / ABANDONNE (circuit breaker)

Utilisation :
  cd /Users/per1guillaume/couffrant-assistant
  APP_USERNAME=guillaume APP_PASSWORD=x ANTHROPIC_API_KEY=x \\
    PYTHONPATH=. python3.11 scripts/test_p2_200.py

Duree estimee : 5 a 15 min selon combien de modeles plantent.
"""

import time
from datetime import datetime

from dotenv import load_dotenv
load_dotenv()

from app.scanner.runner import start_scan_p1
from app.scanner import orchestrator
from app.database import get_pg_conn


TENANT = "couffrant"
SOURCE = "odoo"
SAMPLE_SIZE = 200  # records par modele pour le test


def log(msg: str):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def main():
    log("=" * 70)
    log("TEST P2 - Scan 200 records par modele sur les 16 modeles P2")
    log("=" * 70)

    # Recupere la liste des modeles P1 (a skip) et P2 (a scanner)
    with get_pg_conn() as conn:
        cur = conn.cursor()
        cur.execute("""SELECT model_name, priority, records_count_odoo
                       FROM connector_schemas
                       WHERE tenant_id=%s AND source=%s AND enabled=TRUE
                         AND priority<=2
                       ORDER BY priority ASC, records_count_odoo DESC NULLS LAST""",
                    (TENANT, SOURCE))
        rows = cur.fetchall()

    p1_models = [r[0] for r in rows if r[1] == 1]
    p2_models = [r for r in rows if r[1] == 2]
    log(f"  {len(p1_models)} modeles P1 (skip)")
    log(f"  {len(p2_models)} modeles P2 (test 200 records chacun) :")
    for r in p2_models:
        log(f"    - {r[0]:40s} ({r[2] or 0} records Odoo)")
    log("")


    # Construit record_limits : 0 pour P1 (skip), SAMPLE_SIZE pour P2
    record_limits = {m: 0 for m in p1_models}
    for r in p2_models:
        record_limits[r[0]] = SAMPLE_SIZE

    log(f"  Lancement scan test (priority_max=2, purge=False, 200/modele)...")
    run_id = start_scan_p1(
        tenant_id=TENANT, source=SOURCE,
        priority_max=2, purge_first=False,
        run_type="test",
        record_limits=record_limits,
    )
    log(f"  run_id={run_id[:8]}")
    log("")

    # Polling
    start = time.time()
    last_log = 0
    max_seconds = 1800  # 30 min max
    while time.time() - start < max_seconds:
        status = orchestrator.get_run_status(run_id)
        if not status:
            log(f"  [WARN] run introuvable")
            return
        st = status["status"]
        if st in ("ok", "error", "stopped"):
            break
        if time.time() - last_log > 30:
            prog = status.get("progress") or {}
            stats = status.get("stats") or {}
            log(f"  ... {st} | {prog.get('current_model','?')} | "
                f"{stats.get('chunks_vectorized',0)} chunks, "
                f"{stats.get('errors',0)} erreurs, "
                f"{len(stats.get('models_aborted') or [])} abandonnes")
            last_log = time.time()
        time.sleep(10)


    # Recap final
    final = orchestrator.get_run_status(run_id) or {}
    stats = final.get("stats") or {}
    prog = final.get("progress") or {}
    aborted = stats.get("models_aborted") or []
    aborted_set = set(a.get("model") for a in aborted)

    log("")
    log("=" * 70)
    log(f"RESULTAT TEST P2 (status={final.get('status')})")
    log("=" * 70)
    log(f"  Duree : {int(time.time() - start)}s")
    log(f"  Chunks crees : {stats.get('chunks_vectorized', 0)}")
    log(f"  Erreurs : {stats.get('errors', 0)}")
    log(f"  Modeles abandonnes : {len(aborted)}")
    log("")

    # Detail par modele P2
    log("DETAIL PAR MODELE :")
    models_prog = prog.get("models") or {}
    for r in p2_models:
        model_name = r[0]
        p = models_prog.get(model_name) or {}
        done = p.get("done", 0)
        total = p.get("total", r[2] or 0)
        if model_name in aborted_set:
            abort_info = next((a for a in aborted if a.get("model") == model_name), {})
            reason = (abort_info.get("reason") or "")[:200]
            log(f"  ❌ {model_name:40s} ABANDONNE apres {done} records")
            log(f"     raison: {reason}")
        elif done >= total * 0.95 or done >= SAMPLE_SIZE:
            log(f"  ✅ {model_name:40s} OK ({done}/{total})")
        elif done > 0:
            log(f"  ⚠️  {model_name:40s} PARTIEL ({done}/{total})")
        else:
            log(f"  ⚪ {model_name:40s} vide (0/{total})")

    log("")
    log("Prochaine etape : pour chaque modele ABANDONNE, identifier le")
    log("champ computed casse (comme pour P1) et le retirer du manifest.")
    log("Pour les PARTIEL : meme demarche si ca arrive, mais probablement OK.")
    log("Pour les VIDES : droits Odoo a verifier (comme mail.message en P1).")


if __name__ == "__main__":
    main()
