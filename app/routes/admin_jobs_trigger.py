"""
Endpoints admin pour declencher manuellement certains jobs scheduler.

Utilise lors du bootstrap initial ou pour test/debug, quand on ne veut pas
attendre la prochaine execution programmee du scheduler.

Tous les endpoints sont proteges par require_super_admin (Guillaume seul).
"""
from fastapi import APIRouter, Request, Depends
from fastapi.responses import JSONResponse
from app.routes.deps import require_super_admin
from app.logging_config import get_logger

logger = get_logger("raya.admin_jobs_trigger")
router = APIRouter(tags=["admin_jobs_trigger"])


@router.post("/admin/jobs/gmail/setup_watches")
def admin_trigger_gmail_watch_setup(
    request: Request,
    admin: dict = Depends(require_super_admin),
):
    """Declenche immediatement run_gmail_watch_renewal().

    Ce job tourne normalement chaque jour a 6h UTC (cron). Cet endpoint
    permet de l executer maintenant pour le bootstrap initial des
    5 watches Gmail Pub/Sub apres correction de la variable Railway.

    Pre-requis :
      - SCHEDULER_GMAIL_WATCH_RENEWAL_ENABLED=true (sinon pas grave,
        cet endpoint contourne le scheduler)
      - GMAIL_PUBSUB_TOPIC defini
      - 5 boites Gmail connectees avec scope gmail.readonly

    Retourne le resume de l execution (renewed / skipped / failed).
    """
    try:
        from app.jobs.mail_gmail_watch import run_gmail_watch_renewal
    except Exception as e:
        return JSONResponse({
            "status": "error",
            "message": f"Import echec : {str(e)[:200]}",
        }, status_code=500)

    logger.info(
        "[AdminTrigger] gmail_watch_renewal declenche manuellement par %s",
        admin.get("username", "?"),
    )

    try:
        # run_gmail_watch_renewal() ne retourne rien (logs uniquement),
        # on capture l avant/apres en interrogeant la DB pour donner
        # un retour utile a l UI.
        from app.database import get_pg_conn
        with get_pg_conn() as conn:
            c = conn.cursor()
            c.execute(
                """SELECT connection_id,
                          metadata->>'gmail_watch_history_id' as hid,
                          metadata->>'gmail_watch_expiration' as exp
                   FROM connection_health
                   WHERE connection_type='mail_gmail'
                   ORDER BY connection_id"""
            )
            before = [
                {"connection_id": r[0], "history_id": r[1],
                 "expiration": r[2]}
                for r in c.fetchall()
            ]

        run_gmail_watch_renewal()

        with get_pg_conn() as conn:
            c = conn.cursor()
            c.execute(
                """SELECT connection_id,
                          metadata->>'gmail_watch_history_id' as hid,
                          metadata->>'gmail_watch_expiration' as exp
                   FROM connection_health
                   WHERE connection_type='mail_gmail'
                   ORDER BY connection_id"""
            )
            after = [
                {"connection_id": r[0], "history_id": r[1],
                 "expiration": r[2]}
                for r in c.fetchall()
            ]

        # Compte les watches creees ou renouvelees
        before_map = {b["connection_id"]: b for b in before}
        created = 0
        renewed = 0
        unchanged = 0
        for a in after:
            cid = a["connection_id"]
            b = before_map.get(cid, {})
            if not b.get("history_id") and a.get("history_id"):
                created += 1
            elif b.get("expiration") != a.get("expiration"):
                renewed += 1
            else:
                unchanged += 1

        return JSONResponse({
            "status": "ok",
            "summary": {
                "total": len(after),
                "created": created,
                "renewed": renewed,
                "unchanged": unchanged,
            },
            "details_after": after,
        })
    except Exception as e:
        logger.error(
            "[AdminTrigger] gmail_watch_renewal crash : %s", str(e)[:300])
        return JSONResponse({
            "status": "error",
            "message": f"Crash : {str(e)[:200]}",
        }, status_code=500)


@router.get("/admin/jobs/scheduler_status")
def admin_scheduler_status(
    request: Request,
    admin: dict = Depends(require_super_admin),
):
    """Liste les jobs enregistres dans le scheduler avec leur prochaine
    execution. Utile pour verifier qu une variable Railway a bien ete
    prise en compte au redeploiement.
    """
    try:
        # Import du scheduler global initialise dans main.py
        from app.scheduler import get_scheduler
        scheduler = get_scheduler()
        if not scheduler:
            return JSONResponse({
                "status": "error",
                "message": "Scheduler non initialise",
            }, status_code=500)
        jobs = []
        for job in scheduler.get_jobs():
            jobs.append({
                "id": job.id,
                "name": job.name,
                "next_run_time": (job.next_run_time.isoformat()
                                   if job.next_run_time else None),
                "trigger": str(job.trigger),
            })
        return JSONResponse({
            "status": "ok",
            "total": len(jobs),
            "jobs": sorted(jobs, key=lambda j: j["id"]),
        })
    except Exception as e:
        return JSONResponse({
            "status": "error",
            "message": f"Crash : {str(e)[:200]}",
        }, status_code=500)
