"""
Audit log des actions admin.
Chaque action sensible (création/suppression user, déblocage, modification permissions)
est loguée avec username admin, action, cible, timestamp.
"""
from app.database import get_pg_conn


def _ensure_table():
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS admin_audit_log (
                id SERIAL PRIMARY KEY,
                admin_username TEXT NOT NULL,
                action TEXT NOT NULL,
                target TEXT,
                details TEXT,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_admin_audit_date ON admin_audit_log (created_at DESC)")
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[AdminAudit] Migration table: {e}")

_ensure_table()


def log_admin_action(admin_username: str, action: str, target: str = "", details: str = ""):
    """
    Logue une action admin. Non-bloquant : si l'écriture échoue, on continue.
    """
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute(
            "INSERT INTO admin_audit_log (admin_username, action, target, details) VALUES (%s, %s, %s, %s)",
            (admin_username, action, target or "", details or ""),
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[AdminAudit] Erreur log (non bloquant): {e}")
