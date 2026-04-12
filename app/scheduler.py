"""
Scheduler de jobs périodiques Raya — orchestrateur.

Les implémentations des jobs sont dans app/jobs/* — ce fichier
ne garde que le registre, start() et stop().

Variables d'environnement pour désactiver un job :
  SCHEDULER_EXPIRE_ENABLED=false    SCHEDULER_DECAY_ENABLED=false
  SCHEDULER_AUDIT_ENABLED=false     SCHEDULER_WEBHOOK_ENABLED=false
  SCHEDULER_TOKEN_ENABLED=false     SCHEDULER_PROACTIVITY_ENABLED=false
  SCHEDULER_PATTERNS_ENABLED=false  SCHEDULER_HEARTBEAT_ENABLED=false
  SCHEDULER_BRIEFING_ENABLED=false  SCHEDULER_MONITOR_ENABLED=false
  SCHEDULER_GMAIL_ENABLED=true      (activer Gmail polling, défaut: false)

Jobs :
  expire_pending    toutes les heures
  confidence_decay  lundi 02h00
  opus_audit        dimanche 03h00
  webhook_setup     30s au démarrage (une fois)
  webhook_renewal   toutes les 6h
  token_refresh     toutes les 45 min
  proactivity_scan  toutes les 30 min (5E-4b + 8-CYCLES)
  pattern_analysis  dimanche 04h00  (5G-4 + 7-WF + 8-CYCLES)
  meeting_briefing  06h30 chaque matin (7-BRIEF)
  heartbeat_morning 07h00 chaque matin (7-6R)
  gmail_polling     toutes les 3 min (7-1b) — désactivé par défaut
  system_monitor    toutes les 10 min  (7-7)
"""
import os
from app.logging_config import get_logger
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger

# ─── Imports des jobs depuis les modules dédiés ───
from app.jobs.maintenance import (
    _job_expire_pending,
    _job_opus_audit,
    _job_token_refresh,
    _job_webhook_setup,
    _job_webhook_renewal,
)
from app.jobs.confidence_decay import _job_confidence_decay
from app.jobs.proactivity_scan import _job_proactivity_scan
from app.jobs.pattern_analysis import _job_pattern_analysis
from app.jobs.briefing import _job_meeting_briefing
from app.jobs.heartbeat import _job_heartbeat_morning
from app.jobs.gmail_polling import _job_gmail_polling
from app.jobs.system_monitor import _job_system_monitor

logger = get_logger("raya.scheduler")
_scheduler: BackgroundScheduler | None = None

# Constantes réexportées pour compatibilité descendante
CONFIDENCE_MASK_THRESHOLD = 0.3
CONFIDENCE_DECAY_STEP     = 0.05
AUDIT_MIN_RULES           = 5


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


def _register_jobs(scheduler: BackgroundScheduler):
    if _job_enabled("SCHEDULER_EXPIRE_ENABLED"):
        scheduler.add_job(
            func=_job_expire_pending, trigger=IntervalTrigger(hours=1),
            id="expire_pending", name="Expiration des actions en attente", replace_existing=True,
        )
        logger.info("[Scheduler] Job enregistré : expire_pending (toutes les heures)")
    else:
        logger.info("[Scheduler] Job DÉSACTIVÉ : expire_pending")

    if _job_enabled("SCHEDULER_DECAY_ENABLED"):
        scheduler.add_job(
            func=_job_confidence_decay,
            trigger=CronTrigger(day_of_week="mon", hour=2, minute=0),
            id="confidence_decay", name="Décroissance de confiance", replace_existing=True,
        )
        logger.info("[Scheduler] Job enregistré : confidence_decay (lundi 02h00)")
    else:
        logger.info("[Scheduler] Job DÉSACTIVÉ : confidence_decay")

    if _job_enabled("SCHEDULER_AUDIT_ENABLED"):
        scheduler.add_job(
            func=_job_opus_audit,
            trigger=CronTrigger(day_of_week="sun", hour=3, minute=0),
            id="opus_audit", name="Audit de cohérence Opus", replace_existing=True,
        )
        logger.info("[Scheduler] Job enregistré : opus_audit (dimanche 03h00)")
    else:
        logger.info("[Scheduler] Job DÉSACTIVÉ : opus_audit")

    if _job_enabled("SCHEDULER_WEBHOOK_ENABLED"):
        from datetime import datetime, timedelta
        scheduler.add_job(
            func=_job_webhook_setup, trigger="date",
            run_date=datetime.now() + timedelta(seconds=30),
            id="webhook_setup", replace_existing=True,
        )
        scheduler.add_job(
            func=_job_webhook_renewal, trigger=IntervalTrigger(hours=6),
            id="webhook_renewal", replace_existing=True,
        )
        logger.info("[Scheduler] Jobs enregistrés : webhook_setup + webhook_renewal")
    else:
        logger.info("[Scheduler] Jobs DÉSACTIVÉS : webhook")

    if _job_enabled("SCHEDULER_TOKEN_ENABLED"):
        scheduler.add_job(
            func=_job_token_refresh, trigger=IntervalTrigger(minutes=45),
            id="token_refresh", replace_existing=True,
        )
        logger.info("[Scheduler] Job enregistré : token_refresh (45 min)")
    else:
        logger.info("[Scheduler] Job DÉSACTIVÉ : token_refresh")

    if _job_enabled("SCHEDULER_PROACTIVITY_ENABLED"):
        scheduler.add_job(
            func=_job_proactivity_scan, trigger=IntervalTrigger(minutes=30),
            id="proactivity_scan", name="Scan proactif mails + agenda", replace_existing=True,
        )
        logger.info("[Scheduler] Job enregistré : proactivity_scan (30 min)")
    else:
        logger.info("[Scheduler] Job DÉSACTIVÉ : proactivity_scan")

    if _job_enabled("SCHEDULER_PATTERNS_ENABLED"):
        scheduler.add_job(
            func=_job_pattern_analysis,
            trigger=CronTrigger(day_of_week="sun", hour=4, minute=0),
            id="pattern_analysis", name="Détection de patterns comportementaux",
            replace_existing=True,
        )
        logger.info("[Scheduler] Job enregistré : pattern_analysis (dimanche 04h00)")
    else:
        logger.info("[Scheduler] Job DÉSACTIVÉ : pattern_analysis")

    if _job_enabled("SCHEDULER_BRIEFING_ENABLED"):
        scheduler.add_job(
            func=_job_meeting_briefing, trigger=CronTrigger(hour=6, minute=30),
            id="meeting_briefing", name="Briefings réunions du jour", replace_existing=True,
        )
        logger.info("[Scheduler] Job enregistré : meeting_briefing (06h30)")
    else:
        logger.info("[Scheduler] Job DÉSACTIVÉ : meeting_briefing")

    if _job_enabled("SCHEDULER_HEARTBEAT_ENABLED"):
        scheduler.add_job(
            func=_job_heartbeat_morning, trigger=CronTrigger(hour=7, minute=0),
            id="heartbeat_morning", name="Heartbeat matinal Raya", replace_existing=True,
        )
        logger.info("[Scheduler] Job enregistré : heartbeat_morning (07h00)")
    else:
        logger.info("[Scheduler] Job DÉSACTIVÉ : heartbeat_morning")

    # Gmail polling — désactivé par défaut
    if _job_enabled("SCHEDULER_GMAIL_ENABLED", default=False):
        scheduler.add_job(
            func=_job_gmail_polling, trigger=IntervalTrigger(minutes=3),
            id="gmail_polling", name="Gmail polling", replace_existing=True,
        )
        logger.info("[Scheduler] Job enregistré : gmail_polling (3 min)")
    else:
        logger.info(
            "[Scheduler] Job DÉSACTIVÉ : gmail_polling "
            "(activer via SCHEDULER_GMAIL_ENABLED=true)"
        )

    # System monitor — actif par défaut
    if _job_enabled("SCHEDULER_MONITOR_ENABLED"):
        scheduler.add_job(
            func=_job_system_monitor, trigger=IntervalTrigger(minutes=10),
            id="system_monitor", name="Monitoring système", replace_existing=True,
        )
        logger.info("[Scheduler] Job enregistré : system_monitor (10 min)")
    else:
        logger.info("[Scheduler] Job DÉSACTIVÉ : system_monitor")
