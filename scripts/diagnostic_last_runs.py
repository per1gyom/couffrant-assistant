"""Diagnostic rapide : liste les 10 derniers runs du Scanner avec leurs stats.
Lance-moi via :
  PYTHONPATH=. python3.11 scripts/diagnostic_last_runs.py
"""
import os
import sys
from dotenv import load_dotenv
load_dotenv()

from app.database import get_pg_conn

print("=" * 80)
print("DIAGNOSTIC : 10 derniers runs Scanner")
print("=" * 80)

with get_pg_conn() as conn:
    cur = conn.cursor()
    cur.execute("""
        SELECT id, tenant_id, source, run_type, status,
               started_at, completed_at,
               EXTRACT(EPOCH FROM (completed_at - started_at))::int AS duree_sec,
               stats, progress, error_message
        FROM scanner_runs
        ORDER BY started_at DESC
        LIMIT 10
    """)
    rows = cur.fetchall()

if not rows:
    print("Aucun run trouve en DB.")
    sys.exit(0)

for r in rows:
    rid, tenant, source, rtype, status, start, end, duree, stats, progress, err = r
    print(f"\n--- Run {rid[:8]} ({rtype}) ---")
    print(f"  Status        : {status}")
    print(f"  Started       : {start}")
    print(f"  Completed     : {end}")
    print(f"  Duree         : {duree}s" if duree else "  Duree         : (pas termine)")
    print(f"  Stats         : {stats}")
    if progress:
        print(f"  Progress      : {progress}")
    if err:
        print(f"  Error message : {err[:500]}")

# Verif Odoo credentials presentes dans l env
print("\n" + "=" * 80)
print("VERIFICATION credentials Odoo dans l env local")
print("=" * 80)
for var in ["ODOO_URL", "ODOO_DB", "ODOO_LOGIN", "ODOO_API_KEY", "ODOO_PASSWORD", "DATABASE_URL", "OPENAI_API_KEY"]:
    val = os.getenv(var, "")
    if val:
        masked = val[:8] + "***" + val[-4:] if len(val) > 16 else "***"
        print(f"  {var:20s} : OK ({masked})")
    else:
        print(f"  {var:20s} : MANQUANT !")
