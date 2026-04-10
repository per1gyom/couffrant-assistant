"""
Scheduler de jobs périodiques Raya — Phase 4.

Utilise APScheduler (BackgroundScheduler) pour exécuter des tâches
de maintenance sans bloquer le serveur FastAPI.

Jobs enregistrés :
  expire_pending     : toutes les heures   — expire les pending_actions trop vieilles

[à venir — commits séparés]
  confidence_decay   : hebdomadaire lundi 02h00   — décroissance de confiance des règles inactives (B6)
  opus_audit         : hebdomadaire dimanche 03h00 — audit de cohérence Opus (B5)
  proactivity_scan   : toutes les 30 min          — alertes et rappels (B10)

Démarrage : scheduler.start() dans main.py au startup FastAPI.
Arrêt     : scheduler.stop()  dans main.py au shutdown FastAPI.
"""
import logging
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

logger = logging.getLogger(__name__)

_scheduler: BackgroundScheduler | None = None


def get_scheduler() -> BackgroundScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = BackgroundScheduler(
            job_defaults={
                "coalesce": True,           # Plusieurs exécutions ratées → une seule rattrapante
                "max_instances": 1,         # Pas de chevauchement pour le même job
                "misfire_grace_time": 300,  # 5 min de tolérance si le serveur était down
            },
            timezone="Europe/Paris",
        )
    return _scheduler


def start():
    """
    Démarre le scheduler et enregistre tous les jobs.
    Idémpotent : appels multiples sans effet si déjà actif.
    """
    scheduler = get_scheduler()
    if scheduler.running:
        return

    _register_jobs(scheduler)
    scheduler.start()
    jobs = scheduler.get_jobs()
    print(f"[Scheduler] Démarré — {len(jobs)} job(s) : {[j.id for j in jobs]}")


def stop():
    """Arrête proprement le scheduler (shutdown FastAPI)."""
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        print("[Scheduler] Arrêté")
    _scheduler = None


def _register_jobs(scheduler: BackgroundScheduler):
    """
    Enregistre tous les jobs périodiques.
    Chaque job est ajouté avec replace_existing=True (idémpotent au redémarrage).
    """

    # ─ Job 1 : expiration des pending_actions (toutes les heures) ─
    scheduler.add_job(
        func=_job_expire_pending,
        trigger=IntervalTrigger(hours=1),
        id="expire_pending",
        name="Expiration des actions en attente",
        replace_existing=True,
    )

    # Les commits suivants ajouteront :
    # scheduler.add_job(_job_confidence_decay, CronTrigger(day_of_week='mon', hour=2), id='confidence_decay', ...)
    # scheduler.add_job(_job_opus_audit,       CronTrigger(day_of_week='sun', hour=3), id='opus_audit', ...)
    # scheduler.add_job(_job_proactivity_scan, IntervalTrigger(minutes=30),             id='proactivity_scan', ...)


# ─── FONCTIONS JOB ───

def _job_expire_pending():
    """
    Expire les pending_actions dont expires_at est dépassé.
    Appelle expire_old_pending() qui existe déjà dans pending_actions.py.
    """
    try:
        from app.pending_actions import expire_old_pending
        n = expire_old_pending()
        if n:
            print(f"[Scheduler] expire_pending : {n} action(s) expirée(s)")
    except Exception as e:
        print(f"[Scheduler] ERREUR expire_pending : {e}")
