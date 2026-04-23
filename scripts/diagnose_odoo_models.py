"""Script de diagnostic pour identifier les champs Odoo qui plantent le fetch.

Utilise le même connecteur que le scanner (odoo_call) pour tester progressivement :
1. Appel minimal (id + display_name) sur chaque modèle problématique
2. Ajout des champs vectorize_fields, puis metadata_fields, puis graph_edges
3. Si ça plante, on binary-search dans le groupe qui a cassé pour isoler le champ

Ne modifie RIEN. Ne purge RIEN. Juste de la lecture.
"""
import os
import sys
from dotenv import load_dotenv
load_dotenv()

from app.connectors.odoo_connector import odoo_call
from app.database import get_pg_conn


MODELS_TO_DIAGNOSE = [
    "of.planning.tour",
    "sale.order.line",
    "calendar.event",
    "mail.message",
]


def get_manifest(model_name: str, tenant_id: str = "couffrant", source: str = "odoo"):
    with get_pg_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """SELECT manifest FROM connector_schemas
               WHERE tenant_id=%s AND source=%s AND model_name=%s""",
            (tenant_id, source, model_name),
        )
        r = cur.fetchone()
        return r[0] if r else None


def test_fetch(model_name: str, fields: list, label: str = "") -> tuple[bool, str]:
    """Renvoie (succès, message). Teste avec offset=0, limit=5."""
    try:
        r = odoo_call(
            model=model_name, method="search_read",
            kwargs={"domain": [], "fields": fields, "offset": 0, "limit": 5,
                    "order": "id asc"},
        )
        return True, f"OK {len(r or [])} records"
    except Exception as e:
        msg = str(e)
        # Raccourcir la pile Odoo (on veut juste le type d'erreur)
        if "debug" in msg:
            # Extraire juste le message d'erreur principal
            import re
            m = re.search(r'"message"\s*:\s*"([^"]+)"', msg)
            core = m.group(1) if m else msg[:200]
            return False, f"FAIL: {core[:200]}"
        return False, f"FAIL: {type(e).__name__}: {msg[:200]}"


def binary_search_bad_field(model_name: str, base_fields: list, test_fields: list) -> list:
    """Isole le(s) champ(s) qui fait planter. base_fields = toujours OK.
    Retourne la liste des champs 'tueurs'."""
    if not test_fields:
        return []
    # Test avec tous les test_fields
    ok, msg = test_fetch(model_name, base_fields + test_fields)
    if ok:
        return []  # Aucun ne casse
    if len(test_fields) == 1:
        return test_fields  # Le seul est le tueur
    # Binary split
    mid = len(test_fields) // 2
    left = test_fields[:mid]
    right = test_fields[mid:]
    bad_left = binary_search_bad_field(model_name, base_fields, left)
    bad_right = binary_search_bad_field(model_name, base_fields + left, right)
    return bad_left + bad_right


def diagnose_model(model_name: str):
    print(f"\n{'='*70}")
    print(f"MODELE : {model_name}")
    print(f"{'='*70}")

    manifest = get_manifest(model_name)
    if not manifest:
        print("  [ERREUR] Pas de manifest trouvé en DB")
        return

    vectorize_fields = manifest.get("vectorize_fields", []) or []
    metadata_fields = manifest.get("metadata_fields", []) or []
    graph_fields = [e.get("field") for e in manifest.get("graph_edges", []) if e.get("field")]

    print(f"  vectorize: {len(vectorize_fields)} champs")
    print(f"  metadata : {len(metadata_fields)} champs")
    print(f"  graph    : {len(graph_fields)} champs")
    print(f"  TOTAL    : {len(vectorize_fields) + len(metadata_fields) + len(graph_fields)} champs")

    # Test 1 : minimal
    base = ["id", "display_name"]
    ok, msg = test_fetch(model_name, base)
    print(f"\n  [1/5] Minimal (id, display_name) → {msg}")
    if not ok:
        print("  >>> Le modèle lui-même plante. Pas la peine d'aller plus loin.")
        return

    # Test 2 : + vectorize
    ok, msg = test_fetch(model_name, base + vectorize_fields)
    print(f"  [2/5] + vectorize_fields ({len(vectorize_fields)}) → {msg}")
    bad_vectorize = []
    if not ok and vectorize_fields:
        print(f"      >>> Recherche du champ tueur dans vectorize_fields...")
        bad_vectorize = binary_search_bad_field(model_name, base, vectorize_fields)
        print(f"      >>> CHAMPS TUEURS (vectorize): {bad_vectorize}")

    # Test 3 : + metadata (sans les vectorize tueurs)
    safe_vectorize = [f for f in vectorize_fields if f not in bad_vectorize]
    base3 = base + safe_vectorize
    ok, msg = test_fetch(model_name, base3 + metadata_fields)
    print(f"  [3/5] + metadata_fields ({len(metadata_fields)}) → {msg}")
    bad_metadata = []
    if not ok and metadata_fields:
        print(f"      >>> Recherche du champ tueur dans metadata_fields...")
        bad_metadata = binary_search_bad_field(model_name, base3, metadata_fields)
        print(f"      >>> CHAMPS TUEURS (metadata): {bad_metadata}")

    # Test 4 : + graph (sans les tueurs précédents)
    safe_metadata = [f for f in metadata_fields if f not in bad_metadata]
    base4 = base3 + safe_metadata
    ok, msg = test_fetch(model_name, base4 + graph_fields)
    print(f"  [4/5] + graph_fields ({len(graph_fields)}) → {msg}")
    bad_graph = []
    if not ok and graph_fields:
        print(f"      >>> Recherche du champ tueur dans graph_fields...")
        bad_graph = binary_search_bad_field(model_name, base4, graph_fields)
        print(f"      >>> CHAMPS TUEURS (graph): {bad_graph}")

    # Test 5 : final avec tous les champs safe
    safe_graph = [f for f in graph_fields if f not in bad_graph]
    final_fields = base + safe_vectorize + safe_metadata + safe_graph
    ok, msg = test_fetch(model_name, final_fields)
    print(f"  [5/5] Final safe ({len(final_fields)} champs) → {msg}")

    # Résumé
    all_bad = bad_vectorize + bad_metadata + bad_graph
    print(f"\n  ══ RESUME {model_name} ══")
    print(f"    Champs tueurs total : {len(all_bad)}")
    if all_bad:
        for f in all_bad:
            origin = "vectorize" if f in bad_vectorize else ("metadata" if f in bad_metadata else "graph")
            print(f"      - {f} [{origin}]")
    safe_count = len(safe_vectorize) + len(safe_metadata) + len(safe_graph)
    print(f"    Champs sains        : {safe_count} / {len(vectorize_fields) + len(metadata_fields) + len(graph_fields)}")


if __name__ == "__main__":
    print(f"=== Diagnostic Odoo — {len(MODELS_TO_DIAGNOSE)} modèles ===")
    for model in MODELS_TO_DIAGNOSE:
        try:
            diagnose_model(model)
        except Exception as e:
            print(f"\n[CRASH SCRIPT sur {model}] {type(e).__name__}: {e}")
    print("\n=== Fin du diagnostic ===")
