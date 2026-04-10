"""
Scheduler central Raya — Phase 4.

Centralise tous les jobs périodiques en threads daemon.
Pas de dépendance externe (Celery, APScheduler) — cohérent
avec le pattern threading existant de main.py.

Jobs déclarés :
  pending_expiry    : toutes les heures
                      Expire les pending_actions dépassées
  confidence_decay  : 1er du mois à 3h00 UTC
                      Décroissance de confiance des règles inactives (B6)
  opus_audit        : dimanche à 2h00 UTC
                      Audit Opus hebdomadaire de cohérence des règles (B5)

Démarré via start_all_jobs() depuis main.py au startup.
"""
import threading
import time
from datetime import datetime, timezone


def _is_first_of_month_at(hour: int = 3) -> bool:
    now = datetime.now(timezone.utc)
    return now.day == 1 and now.hour == hour


def _is_sunday_at(hour: int = 2) -> bool:
    now = datetime.now(timezone.utc)
    return now.weekday() == 6 and now.hour == hour  # 6 = dimanche


def _loop_pending_expiry():
    """Toutes les heures, expire les pending_actions dépassées."""
    time.sleep(60)  # Attente initiale
    while True:
        try:
            from app.jobs.pending_expiry import run
            run()
        except Exception as e:
            print(f"[Scheduler] pending_expiry exception : {e}")
        time.sleep(3600)


def _loop_confidence_decay():
    """Vérifie 1x/heure si c'est le moment de lancer la décroissance (1er du mois à 3h)."""
    time.sleep(300)
    _ran_today = False
    while True:
        try:
            now = datetime.now(timezone.utc)
            if _is_first_of_month_at(hour=3) and not _ran_today:
                from app.jobs.confidence_decay import run
                run()
                _ran_today = True
            elif now.hour == 4:
                _ran_today = False  # Reset pour le lendemain
        except Exception as e:
            print(f"[Scheduler] confidence_decay exception : {e}")
        time.sleep(3600)


def _loop_opus_audit():
    """Vérifie 1x/heure si c'est le moment de lancer l'audit Opus (dimanche 2h)."""
    time.sleep(600)
    _ran_this_week = False
    while True:
        try:
            now = datetime.now(timezone.utc)
            if _is_sunday_at(hour=2) and not _ran_this_week:
                from app.jobs.opus_audit import run_all_tenants
                run_all_tenants()
                _ran_this_week = True
            elif now.weekday() == 0:  # Lundi → reset
                _ran_this_week = False
        except Exception as e:
            print(f"[Scheduler] opus_audit exception : {e}")
        time.sleep(3600)


def start_all_jobs():
    """
    Lance tous les jobs en threads daemon.
    Appelé depuis main.py au startup.
    """
    jobs = [
        ("pending_expiry",   _loop_pending_expiry),
        ("confidence_decay", _loop_confidence_decay),
        ("opus_audit",       _loop_opus_audit),
    ]
    for name, target in jobs:
        t = threading.Thread(target=target, name=f"raya-job-{name}", daemon=True)
        t.start()
        print(f"[Scheduler] Job '{name}' démarré")
