"""
Scheduler de jobs périodiques Raya — Phase 4.

Utilise APScheduler (BackgroundScheduler) pour exécuter des tâches
de maintenance sans bloquer le serveur FastAPI.

Jobs enregistrés :
  expire_pending     : toutes les heures          — expire les pending_actions trop vieilles
  confidence_decay   : hebdomadaire lundi 02h00   — décroissance de confiance des règles inactives (B6)

[à venir — commits séparés]
  opus_audit         : hebdomadaire dimanche 03h00 — audit de cohérence Opus (B5)
  proactivity_scan   : toutes les 30 min          — alertes et rappels (B10)

Démarrage : scheduler.start() dans main.py au startup FastAPI.
Arrêt     : scheduler.stop()  dans main.py au shutdown FastAPI.
"""
import logging
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)

_scheduler: BackgroundScheduler | None = None

# Seuil de confiance en dessous duquel une règle est masquée du RAG (B6)
CONFIDENCE_MASK_THRESHOLD = 0.3
# Décroissance mensuelle appliquée aux règles non renforcées
CONFIDENCE_DECAY_STEP = 0.05


def get_scheduler() -> BackgroundScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = BackgroundScheduler(
            job_defaults={
                "coalesce": True,
                "max_instances": 1,
                "misfire_grace_time": 300,
            },
            timezone="Europe/Paris",
        )
    return _scheduler


def start():
    """Démarre le scheduler et enregistre tous les jobs. Idémpotent."""
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
    """Enregistre tous les jobs périodiques (replace_existing=True → idémpotent)."""

    # ─ Job 1 : expiration des pending_actions (toutes les heures) ─
    scheduler.add_job(
        func=_job_expire_pending,
        trigger=IntervalTrigger(hours=1),
        id="expire_pending",
        name="Expiration des actions en attente",
        replace_existing=True,
    )

    # ─ Job 2 : décroissance de confiance (lundi 02h00) ─
    scheduler.add_job(
        func=_job_confidence_decay,
        trigger=CronTrigger(day_of_week="mon", hour=2, minute=0),
        id="confidence_decay",
        name="Décroissance de confiance des règles inactives",
        replace_existing=True,
    )

    # Les commits suivants ajouteront :
    # scheduler.add_job(_job_opus_audit,       CronTrigger(day_of_week='sun', hour=3), id='opus_audit', ...)
    # scheduler.add_job(_job_proactivity_scan, IntervalTrigger(minutes=30),            id='proactivity_scan', ...)


# ─── FONCTIONS JOB ───

def _job_expire_pending():
    """Expire les pending_actions dont expires_at est dépassé."""
    try:
        from app.pending_actions import expire_old_pending
        n = expire_old_pending()
        if n:
            print(f"[Scheduler] expire_pending : {n} action(s) expirée(s)")
    except Exception as e:
        print(f"[Scheduler] ERREUR expire_pending : {e}")


def _job_confidence_decay():
    """
    Décroissance de confiance des règles inactives (B6).

    Logique :
      1. Toutes les règles actives non touchées depuis > 30 jours
         (hors règles de seeding) perdent CONFIDENCE_DECAY_STEP = 0.05.
      2. Les règles dont la confiance tombe sous CONFIDENCE_MASK_THRESHOLD = 0.3
         sont masquées (active = false) mais PAS supprimées.
         Elles restent en base, récupérables via reinforcement ou feedback 👍.

    Règles protégées :
      - source = 'seed'     : règles de base du profil tenant, jamais dégradées
      - source = 'onboarding' : règles générées au premier login, protégées 90j
    """
    try:
        from app.database import get_pg_conn
        conn = get_pg_conn()
        c = conn.cursor()

        # Étape 1 : décrémenter les règles inactives depuis > 30 jours
        c.execute("""
            UPDATE aria_rules
            SET confidence  = GREATEST(0.0, confidence - %s),
                updated_at  = NOW()
            WHERE active = true
              AND source NOT IN ('seed', 'onboarding')
              AND updated_at < NOW() - INTERVAL '30 days'
        """, (CONFIDENCE_DECAY_STEP,))
        decayed = c.rowcount

        # Étape 2 : masquer les règles sous le seuil (active → false)
        c.execute("""
            UPDATE aria_rules
            SET active     = false,
                updated_at = NOW()
            WHERE active = true
              AND source NOT IN ('seed', 'onboarding')
              AND confidence < %s
        """, (CONFIDENCE_MASK_THRESHOLD,))
        masked = c.rowcount

        conn.commit()
        conn.close()

        msg_parts = []
        if decayed: msg_parts.append(f"{decayed} décrémentée(s)")
        if masked:  msg_parts.append(f"{masked} masquée(s) (conf < {CONFIDENCE_MASK_THRESHOLD})")
        if msg_parts:
            print(f"[Scheduler] confidence_decay : {', '.join(msg_parts)}")
        else:
            print("[Scheduler] confidence_decay : aucune règle concernée")

    except Exception as e:
        print(f"[Scheduler] ERREUR confidence_decay : {e}")
