"""
Scheduler de jobs périodiques Raya — orchestrateur principal.
Chaque job est dans son propre module app/jobs/.

Les imports de jobs sont LAZY (dans _register_jobs) pour éviter qu'un
module cassé ne bloque le démarrage du serveur.

Variables d'environnement :
  SCHEDULER_EXPIRE_ENABLED=false       → désactive expire_pending
  SCHEDULER_DECAY_ENABLED=false        → désactive confidence_decay
  SCHEDULER_AUDIT_ENABLED=false        → désactive opus_audit
  SCHEDULER_WEBHOOK_ENABLED=false      → désactive webhook_setup + webhook_renewal
  SCHEDULER_TOKEN_ENABLED=false        → désactive token_refresh
  SCHEDULER_PROACTIVITY_ENABLED=false  → désactive proactivity_scan
  SCHEDULER_PATTERNS_ENABLED=false     → désactive pattern_analysis
  SCHEDULER_HEARTBEAT_ENABLED=false    → désactive heartbeat_morning (7-6R)
  SCHEDULER_BRIEFING_ENABLED=false     → désactive meeting_briefing (7-BRIEF)
  SCHEDULER_GMAIL_ENABLED=true         → active gmail_polling (7-1b) — défaut: false
  SCHEDULER_MONITOR_ENABLED=false      → désactive system_monitor (7-7) — défaut: true
  SCHEDULER_ANOMALY_ENABLED=true       → active anomaly_detection (8-ANOMALIES) — défaut: false
  SCHEDULER_OBSERVER_ENABLED=true      → active external_observer (8-OBSERVE) — défaut: false
"""
import os
from app.logging_config import get_logger
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger

logger = get_logger("raya.scheduler")
_scheduler: BackgroundScheduler | None = None


def _job_enabled(env_var: str, default: bool = True) -> bool:
    val = os.getenv(env_var, "true" if default else "false").lower()
    return val not in ("false", "0", "no", "off")


def get_scheduler() -> BackgroundScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = BackgroundScheduler(
            job_defaults={"coalesce": True, "max_instances": 1, "misfire_grace_time": 300},
            timezone="Europe/Paris",
        )
    return _scheduler


def start():
    scheduler = get_scheduler()
    if scheduler.running:
        return
    _register_jobs(scheduler)
    scheduler.start()
    jobs = scheduler.get_jobs()
    logger.info(f"[Scheduler] Démarré — {len(jobs)} job(s) : {[j.id for j in jobs]}")


def stop():
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("[Scheduler] Arrêté")
    _scheduler = None


from app.scheduler_jobs import _register_jobs  # noqa
