"""
Actions liées au rapport quotidien (7-6D).
Raya peut livrer le rapport via différents canaux (outils du tools_registry).
Le rapport est préparé en arrière-plan dans daily_reports.
L'utilisateur décide comment le recevoir.
"""
from app.database import get_pg_conn
from app.logging_config import get_logger

logger = get_logger("raya.report")


def get_today_report(username: str) -> dict | None:
    """Retourne le rapport du jour s'il existe."""
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            SELECT id, content, sections, delivered, delivered_via, created_at
            FROM daily_reports
            WHERE username = %s AND report_date = CURRENT_DATE
            LIMIT 1
        """, (username,))
        row = c.fetchone()
        if not row:
            return None
        return {
            "id": row[0], "content": row[1], "sections": row[2] or [],
            "delivered": row[3], "delivered_via": row[4],
            "created_at": str(row[5]),
        }
    except Exception:
        return None
    finally:
        if conn: conn.close()


def mark_report_delivered(report_id: int, channel: str) -> None:
    """Marque le rapport comme livré via un canal spécifique."""
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            UPDATE daily_reports SET delivered = true, delivered_via = %s,
                   delivered_at = NOW() WHERE id = %s
        """, (channel, report_id))
        conn.commit()
        conn.close()
    except Exception:
        pass


def get_report_section(username: str, section_type: str) -> str | None:
    """Retourne une section spécifique du rapport du jour."""
    report = get_today_report(username)
    if not report:
        return None
    for s in report.get("sections", []):
        if s.get("type") == section_type:
            return s.get("content")
    return None
