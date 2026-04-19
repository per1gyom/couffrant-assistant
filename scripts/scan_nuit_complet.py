"""
Script de scan nuit COMPLET — Couffrant Solar (Option 1 validée le 19/04/2026).

Enchaîne EN SÉQUENCE les 4 étapes qui finalisent la vectorisation P1+P2 :

  ÉTAPE 1 — Complément mail.tracking.value (limite portée à 25000, ~22 850 records)
  ÉTAPE 2 — Complément res.partner (tentative 1226 records)
  ÉTAPE 3 — product.template filtré sur articles UTILES (devis + kits)
            → ~500-2000 templates vectorisés au lieu de 133 112 du catalogue entier
  ÉTAPE 4 — Scan P2 COMPLET (volume réel, sans limite 200) sur les 13 modèles
            P2 qui passent au Test P2. Exclut mail.message (droits Odoo bloqués,
            suspens #3) et of.service.request (2 records seulement, négligeable).

TOUTES les étapes : purge_first=False (non destructif, idempotent via INSERT
ON CONFLICT UPDATE dans le processor).

Durée estimée totale : 2h à 3h selon vitesse Odoo. À LANCER MANUELLEMENT par
Guillaume au moment du coucher. Aucun lancement auto depuis Claude.

Usage :
  cd /Users/per1guillaume/couffrant-assistant
  APP_USERNAME=guillaume APP_PASSWORD=x ANTHROPIC_API_KEY=x \\
    PYTHONPATH=. python3.11 scripts/scan_nuit_complet.py
"""

import os
import sys
import time
import importlib.util
from datetime import datetime

from dotenv import load_dotenv
load_dotenv()

# Import dynamique des helpers + étapes existantes depuis scan_nuit.py
# (scripts/ n'est pas un package Python donc import direct impossible)
_spec = importlib.util.spec_from_file_location(
    "scan_nuit",
    os.path.join(os.path.dirname(__file__), "scan_nuit.py"),
)
_scan_nuit = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_scan_nuit)

# On réutilise tous les helpers et les 3 premières étapes sans les redupliquer
log = _scan_nuit.log
wait_run_completion = _scan_nuit.wait_run_completion
print_summary = _scan_nuit.print_summary
etape1_mail_tracking = _scan_nuit.etape1_mail_tracking
etape2_res_partner = _scan_nuit.etape2_res_partner
etape3_products_utiles = _scan_nuit.etape3_products_utiles
TENANT = _scan_nuit.TENANT
SOURCE = _scan_nuit.SOURCE

from app.scanner.runner import start_scan_p1
from app.database import get_pg_conn


# ─── ETAPE 4 : Scan P2 COMPLET (volume réel sur modèles qui marchent) ─

# Modèles P2 à EXCLURE du scan complet :
# - mail.message : droits Odoo bloquent la lecture (suspens #3), 0 records lus
# - of.service.request : 2 records total, négligeable
P2_MODELS_TO_SKIP = {"mail.message", "of.service.request"}


def etape4_p2_complet():
    """Lance un scan complet (sans limite 200) sur les 13 modèles P2 qui ont
    passé le Test P2 du 19/04. purge_first=False : non destructif, complète
    les 150-200 records existants jusqu'au volume réel de chaque modèle.

    Pour mettre les modèles P1 de côté (déjà scannés dans etapes 1-3) :
    record_limits P1 = 0 (skip).
    Pour mail.message / of.service.request : record_limits = 0 (skip).
    Pour les autres P2 : record_limits absent = pas de limite (volume réel).
    """
    log("=" * 70)
    log("ETAPE 4 : Scan P2 COMPLET (13 modeles, volume reel sans limite 200)")
    log("=" * 70)

    # Récupère la liste complète P1 + P2 depuis la DB
    with get_pg_conn() as conn:
        cur = conn.cursor()
        cur.execute("""SELECT model_name, priority FROM connector_schemas
                       WHERE tenant_id=%s AND source=%s AND enabled=TRUE
                         AND priority<=2""", (TENANT, SOURCE))
        all_models = cur.fetchall()

    p1_models = [m for m, p in all_models if p == 1]
    p2_models = [m for m, p in all_models if p == 2]
    log(f"  {len(p1_models)} modeles P1 (skip)")
    log(f"  {len(p2_models)} modeles P2 detectes")

    # Build record_limits :
    # - 0 pour TOUS les P1 (deja traites en etapes 1-3)
    # - 0 pour les P2 a skipper
    # - NON DEFINI pour les P2 a scanner (= volume reel, pas de plafond)
    record_limits = {m: 0 for m in p1_models}
    p2_to_skip = []
    p2_to_scan = []
    for m in p2_models:
        if m in P2_MODELS_TO_SKIP:
            record_limits[m] = 0
            p2_to_skip.append(m)
        else:
            # Pas de cle dans record_limits = pas de limite (volume reel)
            p2_to_scan.append(m)

    log(f"  P2 a SCANNER ({len(p2_to_scan)}) :")
    for m in p2_to_scan:
        log(f"     - {m}")
    if p2_to_skip:
        log(f"  P2 a SKIPPER ({len(p2_to_skip)}) : {', '.join(p2_to_skip)}")
    log("")

    run_id = start_scan_p1(
        tenant_id=TENANT, source=SOURCE,
        priority_max=2, purge_first=False,
        run_type="complete",
        record_limits=record_limits,
    )
    log(f"  run_id={run_id[:8]} lance, polling toutes les 30s...")
    status = wait_run_completion(run_id, max_seconds=10800)  # 3h max
    print_summary("ETAPE 4 terminee (P2 complet)", status)
    return status


# ─── MAIN ─────────────────────────────────────────────────────────

def main():
    log("=" * 70)
    log("SCAN NUIT COMPLET - Finalisation vectorisation P1+P2 Couffrant Solar")
    log(f"Tenant : {TENANT}  |  Source : {SOURCE}")
    log("Duree estimee totale : 2h a 3h")
    log("=" * 70)

    # Etat DB avant (pour comparer apres)
    with get_pg_conn() as conn:
        cur = conn.cursor()
        cur.execute("""SELECT COUNT(*) FROM odoo_semantic_content
                       WHERE tenant_id=%s AND deleted_at IS NULL""", (TENANT,))
        chunks_before = cur.fetchone()[0]
    log(f"Chunks en DB AVANT : {chunks_before}")
    log("")

    # Execute les 4 etapes en sequence. Chaque etape dans un try/except
    # pour ne pas bloquer les suivantes si une plante.
    results = {}
    for name, fn in [
        ("etape1_mail_tracking", etape1_mail_tracking),
        ("etape2_res_partner", etape2_res_partner),
        ("etape3_products_utiles", etape3_products_utiles),
        ("etape4_p2_complet", etape4_p2_complet),
    ]:
        try:
            results[name] = fn()
        except Exception as e:
            log(f"[CRASH {name}] {type(e).__name__}: {e}")
            results[name] = {"status": "crash", "error": str(e)}
        log("")

    # Recap final : etat DB apres + resume des 4 etapes
    with get_pg_conn() as conn:
        cur = conn.cursor()
        cur.execute("""SELECT COUNT(*) FROM odoo_semantic_content
                       WHERE tenant_id=%s AND deleted_at IS NULL""", (TENANT,))
        chunks_after = cur.fetchone()[0]

    log("=" * 70)
    log("RECAP FINAL - SCAN NUIT COMPLET")
    log("=" * 70)
    log(f"Chunks AVANT : {chunks_before}")
    log(f"Chunks APRES : {chunks_after}")
    log(f"Delta        : +{chunks_after - chunks_before}")
    log("")
    log("Statut de chaque etape :")
    for etape, st in results.items():
        status = st.get("status", "unknown") if isinstance(st, dict) else "unknown"
        log(f"  - {etape:30s} : {status}")
    log("")
    log("Fin scan nuit complet. Tu peux fermer le terminal.")
    log("Verifie le dashboard Integrite dans le panel admin pour voir le detail.")


if __name__ == "__main__":
    main()
