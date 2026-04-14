"""
Bug Reports / SAV provisoire — Phase 1A.
Outil de développement : collecte les bugs et suggestions pendant la beta.
Sera retiré quand Raya sera stable en production.

Activé pour : Guillaume + Charlotte (beta testeurs).
Distinct du feedback 👍👎 qui sert à l'apprentissage de Raya.
"""
import json
from datetime import datetime
from fastapi import APIRouter, Request, Depends
from pydantic import BaseModel
from typing import Optional
from app.database import get_pg_conn
from app.routes.deps import require_user, require_admin

router = APIRouter(tags=["bug-reports"])


class BugReportPayload(BaseModel):
    report_type: str  # "bug" ou "amelioration"
    description: str
    aria_memory_id: Optional[int] = None
    user_input: Optional[str] = None
    raya_response: Optional[str] = None
    device_info: Optional[str] = None


@router.post("/raya/bug-report")
def submit_bug_report(
    payload: BugReportPayload,
    user: dict = Depends(require_user),
):
    """Soumet un bug report ou une suggestion d'amélioration."""
    username = user["username"]
    tenant_id = user["tenant_id"]
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            INSERT INTO bug_reports
              (username, tenant_id, report_type, description,
               aria_memory_id, user_input, raya_response, device_info, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'nouveau')
            RETURNING id
        """, (
            username, tenant_id, payload.report_type,
            payload.description[:2000],
            payload.aria_memory_id,
            (payload.user_input or "")[:500],
            (payload.raya_response or "")[:2000],
            (payload.device_info or "")[:200],
        ))
        report_id = c.fetchone()[0]
        conn.commit()
        return {"ok": True, "id": report_id}
    except Exception as e:
        if conn:
            conn.rollback()
        return {"ok": False, "error": str(e)[:200]}
    finally:
        if conn:
            conn.close()


@router.get("/admin/bug-reports")
def list_bug_reports(
    request: Request,
    user: dict = Depends(require_admin),
    status: Optional[str] = None,
    limit: int = 50,
):
    """Liste les bug reports — accès admin uniquement.
    Aussi lisible par Opus via GitHub MCP pour traitement."""
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        if status:
            c.execute("""
                SELECT id, username, tenant_id, report_type, description,
                       aria_memory_id, user_input, raya_response,
                       device_info, status, created_at
                FROM bug_reports
                WHERE status = %s
                ORDER BY created_at DESC LIMIT %s
            """, (status, min(limit, 100)))
        else:
            c.execute("""
                SELECT id, username, tenant_id, report_type, description,
                       aria_memory_id, user_input, raya_response,
                       device_info, status, created_at
                FROM bug_reports
                ORDER BY created_at DESC LIMIT %s
            """, (min(limit, 100),))
        rows = c.fetchall()
        reports = []
        for r in rows:
            reports.append({
                "id": r[0], "username": r[1], "tenant_id": r[2],
                "report_type": r[3], "description": r[4],
                "aria_memory_id": r[5], "user_input": r[6],
                "raya_response": r[7], "device_info": r[8],
                "status": r[9],
                "created_at": r[10].isoformat() if r[10] else None,
            })
        return {"ok": True, "count": len(reports), "reports": reports}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}
    finally:
        if conn:
            conn.close()


@router.patch("/admin/bug-reports/{report_id}")
def update_bug_report_status(
    report_id: int,
    request: Request,
    user: dict = Depends(require_admin),
):
    """Met à jour le statut d'un bug report (nouveau → en_cours → résolu)."""
    conn = None
    try:
        # FastAPI ne parse pas le body pour PATCH sans modèle Pydantic,
        # donc on lit le status depuis le query param.
        new_status = request.query_params.get("status", "en_cours")
        if new_status not in ("nouveau", "en_cours", "resolu", "rejete"):
            return {"ok": False, "error": "Statut invalide"}
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            UPDATE bug_reports SET status = %s WHERE id = %s
        """, (new_status, report_id))
        conn.commit()
        return {"ok": True, "id": report_id, "status": new_status}
    except Exception as e:
        if conn:
            conn.rollback()
        return {"ok": False, "error": str(e)[:200]}
    finally:
        if conn:
            conn.close()
