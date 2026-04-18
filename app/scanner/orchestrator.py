"""
Orchestrator du Scanner Universel.

Gere le cycle de vie des runs (creation, progression, completion),
le checkpointing en DB pour reprise apres interruption, et la coordination
entre l'adapter (fetch) et le processor (ecriture).

Types de runs :
- init    : premiere vectorisation complete d une source
- delta   : incremental nocturne (records modifies depuis la derniere sync)
- rebuild : reconstruction complete (full ou par modele)
- audit   : verification d integrite count_odoo vs count_raya

Statuts : pending -> running -> ok | error | paused
"""

import json
import logging
import uuid
from datetime import datetime
from typing import Optional

from app.database import get_pg_conn

logger = logging.getLogger("raya.scanner.orchestrator")


def create_run(
    tenant_id: str,
    source: str,
    run_type: str,
    params: Optional[dict] = None,
) -> str:
    """Cree un nouveau run en DB et retourne son run_id UUID.

    Args:
        tenant_id: identifiant du tenant (ex: 'couffrant')
        source: systeme source ('odoo', 'drive', 'teams'...)
        run_type: 'init' | 'delta' | 'rebuild' | 'audit'
        params: parametres JSON du run (ex: {"models": ["sale.order"]})
    """
    run_id = str(uuid.uuid4())
    with get_pg_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO scanner_runs
               (run_id, tenant_id, source, run_type, status, params, progress)
               VALUES (%s, %s, %s, %s, 'pending', %s, %s)""",
            (run_id, tenant_id, source, run_type,
             json.dumps(params or {}), json.dumps({})),
        )
        conn.commit()
    logger.info("[Scanner] run cree : %s / %s / %s (tenant=%s)",
                run_id, source, run_type, tenant_id)
    return run_id


def update_progress(run_id: str, progress: dict, stats: Optional[dict] = None):
    """Met a jour la progression d un run en cours. Appele regulierement
    par les workers pendant l execution. Le progress est un dict libre,
    typiquement {"current_model": "sale.order", "done": 150, "total": 310}.
    """
    with get_pg_conn() as conn:
        cur = conn.cursor()
        if stats is not None:
            cur.execute(
                """UPDATE scanner_runs
                   SET status='running', progress=%s, stats=%s,
                       updated_at=NOW()
                   WHERE run_id=%s""",
                (json.dumps(progress), json.dumps(stats), run_id),
            )
        else:
            cur.execute(
                """UPDATE scanner_runs
                   SET status='running', progress=%s, updated_at=NOW()
                   WHERE run_id=%s""",
                (json.dumps(progress), run_id),
            )
        conn.commit()


def finish_run(run_id: str, stats: Optional[dict] = None):
    """Marque un run comme termine avec succes."""
    with get_pg_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """UPDATE scanner_runs
               SET status='ok', finished_at=NOW(), stats=%s, updated_at=NOW()
               WHERE run_id=%s""",
            (json.dumps(stats or {}), run_id),
        )
        conn.commit()
    logger.info("[Scanner] run termine OK : %s (stats=%s)", run_id, stats)


def fail_run(run_id: str, error: str, stats: Optional[dict] = None):
    """Marque un run comme echoue avec le message d erreur."""
    with get_pg_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """UPDATE scanner_runs
               SET status='error', finished_at=NOW(),
                   error=%s, stats=%s, updated_at=NOW()
               WHERE run_id=%s""",
            (error[:2000], json.dumps(stats or {}), run_id),
        )
        conn.commit()
    logger.error("[Scanner] run echoue : %s : %s", run_id, error[:200])


def get_run_status(run_id: str) -> Optional[dict]:
    """Recupere l etat courant d un run par son UUID."""
    with get_pg_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """SELECT run_id, tenant_id, source, run_type, status,
                      started_at, finished_at, params, progress, stats, error
               FROM scanner_runs WHERE run_id=%s""",
            (run_id,),
        )
        row = cur.fetchone()
        if not row:
            return None
        return {
            "run_id": row[0],
            "tenant_id": row[1],
            "source": row[2],
            "run_type": row[3],
            "status": row[4],
            "started_at": row[5].isoformat() if row[5] else None,
            "finished_at": row[6].isoformat() if row[6] else None,
            "params": row[7] or {},
            "progress": row[8] or {},
            "stats": row[9] or {},
            "error": row[10],
        }


def list_recent_runs(tenant_id: str, limit: int = 20) -> list:
    """Liste les runs recents d un tenant, tries par date descendante."""
    with get_pg_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """SELECT run_id, source, run_type, status, started_at,
                      finished_at, stats
               FROM scanner_runs
               WHERE tenant_id=%s
               ORDER BY started_at DESC LIMIT %s""",
            (tenant_id, limit),
        )
        rows = cur.fetchall()
        return [{
            "run_id": r[0], "source": r[1], "run_type": r[2],
            "status": r[3],
            "started_at": r[4].isoformat() if r[4] else None,
            "finished_at": r[5].isoformat() if r[5] else None,
            "duration_sec": (
                (r[5] - r[4]).total_seconds() if r[4] and r[5] else None
            ),
            "stats": r[6] or {},
        } for r in rows]


def get_checkpoint(run_id: str, model_name: str) -> Optional[int]:
    """Recupere le dernier record_id traite pour un modele dans un run.
    Permet la reprise apres interruption : on repart a checkpoint+1."""
    status = get_run_status(run_id)
    if not status:
        return None
    prog = status.get("progress") or {}
    model_prog = (prog.get("models") or {}).get(model_name) or {}
    return model_prog.get("last_id")


def set_checkpoint(run_id: str, model_name: str, last_id: int,
                   done: int, total: int):
    """Enregistre un checkpoint pour un modele dans un run."""
    status = get_run_status(run_id)
    if not status:
        return
    prog = status.get("progress") or {}
    if "models" not in prog:
        prog["models"] = {}
    prog["models"][model_name] = {
        "last_id": last_id, "done": done, "total": total,
        "pct": round(100 * done / total, 1) if total else 0,
        "updated_at": datetime.utcnow().isoformat(),
    }
    prog["current_model"] = model_name
    update_progress(run_id, prog)
