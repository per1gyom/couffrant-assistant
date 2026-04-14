"""
Enregistrement des jobs APScheduler de Raya.
Extrait de scheduler.py -- SPLIT-8.
"""
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.schedulers.background import BackgroundScheduler
from app.logging_config import get_logger

logger = get_logger("raya.scheduler")


def _job_enabled(env_var: str, default: bool = True) -> bool:
    import os
    val = os.getenv(env_var, "").strip().lower()
    if not val: return default
    return val in ("1", "true", "yes", "on")

def _register_jobs(scheduler: BackgroundScheduler):
    """Enregistre tous les jobs. Chaque import est lazy + protégé par try/except."""

    if _job_enabled("SCHEDULER_EXPIRE_ENABLED"):
        try:
            from app.jobs.maintenance import _job_expire_pending
            scheduler.add_job(func=_job_expire_pending, trigger=IntervalTrigger(hours=1),
                              id="expire_pending", name="Expiration des actions en attente",
                              replace_existing=True)
            logger.info("[Scheduler] Job enregistré : expire_pending (toutes les heures)")
        except Exception as e:
            logger.error(f"[Scheduler] Import échoué pour expire_pending: {e}")
    else:
        logger.info("[Scheduler] Job DÉSACTIVÉ : expire_pending")

    if _job_enabled("SCHEDULER_DECAY_ENABLED"):
        try:
            from app.jobs.confidence_decay import _job_confidence_decay
            scheduler.add_job(func=_job_confidence_decay,
                              trigger=CronTrigger(day_of_week="mon", hour=2, minute=0),
                              id="confidence_decay", name="Décroissance de confiance",
                              replace_existing=True)
            logger.info("[Scheduler] Job enregistré : confidence_decay (lundi 02h00)")
        except Exception as e:
            logger.error(f"[Scheduler] Import échoué pour confidence_decay: {e}")
    else:
        logger.info("[Scheduler] Job DÉSACTIVÉ : confidence_decay")

    if _job_enabled("SCHEDULER_AUDIT_ENABLED"):
        try:
            from app.jobs.maintenance import _job_opus_audit
            scheduler.add_job(func=_job_opus_audit,
                              trigger=CronTrigger(day_of_week="sun", hour=3, minute=0),
                              id="opus_audit", name="Audit de cohérence Opus",
                              replace_existing=True)
            logger.info("[Scheduler] Job enregistré : opus_audit (dimanche 03h00)")
        except Exception as e:
            logger.error(f"[Scheduler] Import échoué pour opus_audit: {e}")
    else:
        logger.info("[Scheduler] Job DÉSACTIVÉ : opus_audit")

    if _job_enabled("SCHEDULER_WEBHOOK_ENABLED"):
        try:
            from app.jobs.maintenance import _job_webhook_setup, _job_webhook_renewal
            from datetime import datetime, timedelta
            scheduler.add_job(func=_job_webhook_setup, trigger="date",
                              run_date=datetime.now() + timedelta(seconds=30),
                              id="webhook_setup", replace_existing=True)
            scheduler.add_job(func=_job_webhook_renewal, trigger=IntervalTrigger(hours=6),
                              id="webhook_renewal", replace_existing=True)
            logger.info("[Scheduler] Jobs enregistrés : webhook_setup + webhook_renewal")
        except Exception as e:
            logger.error(f"[Scheduler] Import échoué pour webhook jobs: {e}")
    else:
        logger.info("[Scheduler] Jobs DÉSACTIVÉS : webhook")

    if _job_enabled("SCHEDULER_TOKEN_ENABLED"):
        try:
            from app.jobs.maintenance import _job_token_refresh
            scheduler.add_job(func=_job_token_refresh, trigger=IntervalTrigger(minutes=45),
                              id="token_refresh", replace_existing=True)
            logger.info("[Scheduler] Job enregistré : token_refresh (45 min)")
        except Exception as e:
            logger.error(f"[Scheduler] Import échoué pour token_refresh: {e}")
    else:
        logger.info("[Scheduler] Job DÉSACTIVÉ : token_refresh")

    if _job_enabled("SCHEDULER_PROACTIVITY_ENABLED"):
        try:
            from app.jobs.proactivity_scan import _job_proactivity_scan
            scheduler.add_job(func=_job_proactivity_scan, trigger=IntervalTrigger(minutes=30),
                              id="proactivity_scan", name="Scan proactif mails + agenda",
                              replace_existing=True)
            logger.info("[Scheduler] Job enregistré : proactivity_scan (30 min)")
        except Exception as e:
            logger.error(f"[Scheduler] Import échoué pour proactivity_scan: {e}")
    else:
        logger.info("[Scheduler] Job DÉSACTIVÉ : proactivity_scan")

    if _job_enabled("SCHEDULER_PATTERNS_ENABLED"):
        try:
            from app.jobs.pattern_analysis import _job_pattern_analysis
            scheduler.add_job(func=_job_pattern_analysis,
                              trigger=CronTrigger(day_of_week="sun", hour=4, minute=0),
                              id="pattern_analysis", name="Détection de patterns comportementaux",
                              replace_existing=True)
            logger.info("[Scheduler] Job enregistré : pattern_analysis (dimanche 04h00)")
        except Exception as e:
            logger.error(f"[Scheduler] Import échoué pour pattern_analysis: {e}")
    else:
        logger.info("[Scheduler] Job DÉSACTIVÉ : pattern_analysis")

    if _job_enabled("SCHEDULER_BRIEFING_ENABLED"):
        try:
            from app.jobs.briefing import _job_meeting_briefing
            scheduler.add_job(func=_job_meeting_briefing,
                              trigger=CronTrigger(hour=6, minute=30),
                              id="meeting_briefing", name="Briefings réunions du jour",
                              replace_existing=True)
            logger.info("[Scheduler] Job enregistré : meeting_briefing (06h30)")
        except Exception as e:
            logger.error(f"[Scheduler] Import échoué pour meeting_briefing: {e}")
    else:
        logger.info("[Scheduler] Job DÉSACTIVÉ : meeting_briefing")

    if _job_enabled("SCHEDULER_HEARTBEAT_ENABLED"):
        try:
            from app.jobs.heartbeat import _job_heartbeat_morning
            scheduler.add_job(func=_job_heartbeat_morning,
                              trigger=CronTrigger(hour=7, minute=0),
                              id="heartbeat_morning", name="Heartbeat matinal Raya",
                              replace_existing=True)
            logger.info("[Scheduler] Job enregistré : heartbeat_morning (07h00)")
        except Exception as e:
            logger.error(f"[Scheduler] Import échoué pour heartbeat_morning: {e}")
    else:
        logger.info("[Scheduler] Job DÉSACTIVÉ : heartbeat_morning")

    if _job_enabled("SCHEDULER_GMAIL_ENABLED", default=False):
        try:
            from app.jobs.gmail_polling import _job_gmail_polling
            scheduler.add_job(func=_job_gmail_polling, trigger=IntervalTrigger(minutes=3),
                              id="gmail_polling", name="Gmail polling",
                              replace_existing=True)
            logger.info("[Scheduler] Job enregistré : gmail_polling (3 min)")
        except Exception as e:
            logger.error(f"[Scheduler] Import échoué pour gmail_polling: {e}")
    else:
        logger.info("[Scheduler] Job DÉSACTIVÉ : gmail_polling (activer via SCHEDULER_GMAIL_ENABLED=true)")

    if _job_enabled("SCHEDULER_MONITOR_ENABLED"):
        try:
            from app.jobs.system_monitor import _job_system_monitor
            scheduler.add_job(func=_job_system_monitor, trigger=IntervalTrigger(minutes=10),
                              id="system_monitor", name="Monitoring système",
                              replace_existing=True)
            logger.info("[Scheduler] Job enregistré : system_monitor (10 min)")
        except Exception as e:
            logger.error(f"[Scheduler] Import échoué pour system_monitor: {e}")
    else:
        logger.info("[Scheduler] Job DÉSACTIVÉ : system_monitor")

    # Anomaly detection (8-ANOMALIES) — désactivé par défaut (activer si Odoo connecté)
    if _job_enabled("SCHEDULER_ANOMALY_ENABLED", default=False):
        try:
            from app.jobs.anomaly_detection import _job_anomaly_detection
            scheduler.add_job(func=_job_anomaly_detection, trigger=IntervalTrigger(hours=6),
                              id="anomaly_detection", name="Détection d'anomalies Odoo vs mails",
                              replace_existing=True)
            logger.info("[Scheduler] Job enregistré : anomaly_detection (toutes les 6h)")
        except Exception as e:
            logger.error(f"[Scheduler] Import échoué pour anomaly_detection: {e}")
    else:
        logger.info("[Scheduler] Job DÉSACTIVÉ : anomaly_detection (activer via SCHEDULER_ANOMALY_ENABLED=true)")

    # External observer (8-OBSERVE) — désactivé par défaut
    if _job_enabled("SCHEDULER_OBSERVER_ENABLED", default=False):
        try:
            from app.jobs.external_observer import _job_external_observer
            scheduler.add_job(func=_job_external_observer, trigger=IntervalTrigger(minutes=30),
                              id="external_observer", name="Observateur activité externe",
                              replace_existing=True)
            logger.info("[Scheduler] Job enregistré : external_observer (30 min)")
        except Exception as e:
            logger.error(f"[Scheduler] Import échoué pour external_observer: {e}")
    else:
        logger.info("[Scheduler] Job DÉSACTIVÉ : external_observer (activer via SCHEDULER_OBSERVER_ENABLED=true)")

