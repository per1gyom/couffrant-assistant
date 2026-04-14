"""
Backup de la base de données PostgreSQL — B4.

GET /admin/backup (require_admin) :
  - Essaie pg_dump si disponible (dump SQL complet, timeout 120s)
  - Fallback Python : COPY table TO STDOUT CSV HEADER sur toutes les tables publiques
  - Retourne un StreamingResponse en pièce jointe (.sql ou .csv selon le mode)

Usage : ouvrir /admin/backup dans le navigateur → téléchargement immédiat.
"""
import io
import os
import subprocess
from datetime import datetime

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.routes.deps import require_admin
from app.logging_config import get_logger

logger = get_logger("raya.backup")
router = APIRouter(tags=["backup"])

DATABASE_URL = os.getenv("DATABASE_URL", "")


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M")


def _pg_dump_stream():
    """Tente un pg_dump complet. Retourne les bytes ou None si indisponible."""
    try:
        result = subprocess.run(
            ["pg_dump", "--no-password", DATABASE_URL],
            capture_output=True,
            timeout=120,
        )
        if result.returncode == 0 and result.stdout:
            return result.stdout
        logger.warning("[Backup] pg_dump exit %d : %s", result.returncode, result.stderr[:200])
    except FileNotFoundError:
        logger.info("[Backup] pg_dump non disponible — fallback Python CSV")
    except subprocess.TimeoutExpired:
        logger.warning("[Backup] pg_dump timeout (120s)")
    except Exception as e:
        logger.warning("[Backup] pg_dump erreur : %s", e)
    return None


def _python_csv_dump() -> bytes:
    """
    Fallback : exporte toutes les tables publiques en CSV via COPY TO STDOUT.
    Retourne un seul fichier avec les tables séparées par des en-têtes.
    """
    from app.database import get_pg_conn
    conn = None
    buf = io.StringIO()
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        # Liste toutes les tables publiques
        c.execute("""
            SELECT tablename FROM pg_tables
            WHERE schemaname = 'public'
            ORDER BY tablename
        """)
        tables = [r[0] for r in c.fetchall()]
        buf.write(f"-- Raya CSV Backup {_timestamp()}\n")
        buf.write(f"-- Tables : {', '.join(tables)}\n\n")
        for table in tables:
            buf.write(f"-- TABLE: {table}\n")
            try:
                copy_buf = io.StringIO()
                c.copy_expert(f'COPY "{table}" TO STDOUT WITH CSV HEADER', copy_buf)
                copy_buf.seek(0)
                buf.write(copy_buf.read())
            except Exception as e:
                buf.write(f"-- ERREUR: {e}\n")
            buf.write("\n\n")
    finally:
        if conn:
            conn.close()
    return buf.getvalue().encode("utf-8")


@router.get("/admin/backup")
def download_backup(user: dict = Depends(require_admin)):
    """
    Télécharge un backup complet de la base de données.
    Utilise pg_dump si disponible, sinon fallback CSV Python.
    """
    ts = _timestamp()

    # Tentative pg_dump (dump SQL natif)
    sql_bytes = _pg_dump_stream()
    if sql_bytes:
        filename = f"raya_backup_{ts}.sql"
        logger.info("[Backup] pg_dump OK — %d bytes — %s", len(sql_bytes), filename)
        return StreamingResponse(
            io.BytesIO(sql_bytes),
            media_type="application/octet-stream",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    # Fallback CSV Python
    logger.info("[Backup] Fallback CSV Python")
    try:
        csv_bytes = _python_csv_dump()
        filename = f"raya_backup_{ts}.csv"
        logger.info("[Backup] CSV dump OK — %d bytes — %s", len(csv_bytes), filename)
        return StreamingResponse(
            io.BytesIO(csv_bytes),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except Exception as e:
        logger.error("[Backup] Echec backup complet : %s", e)
        return {"ok": False, "error": str(e)[:200]}
