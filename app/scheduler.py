"""
Scheduler de jobs périodiques Raya — Phase 4 + 7.

Utilise APScheduler (BackgroundScheduler) pour exécuter des tâches
de maintenance sans bloquer le serveur FastAPI.

Variables d'environnement pour désactiver un job individuellement :
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

Valeur par défaut : true (tous les jobs actifs), sauf gmail_polling (false).

Jobs :
  expire_pending    : toutes les heures
  confidence_decay  : lundi 02h00 (adaptatif par user, 5G-2)
  opus_audit        : dimanche 03h00
  webhook_setup     : 30s au démarrage (une fois)
  webhook_renewal   : toutes les 6h
  token_refresh     : toutes les 45 min
  proactivity_scan  : toutes les 30 min (5E-4b)
  pattern_analysis  : dimanche 04h00 (5G-4 + 7-WF activity_log)
  meeting_briefing  : 06h30 chaque matin (7-BRIEF) — briefings réunions du jour
  heartbeat_morning : 07h00 chaque matin (7-6R) — rapport stocké + ping seulement
  gmail_polling     : toutes les 3 min (7-1b) — désactivé par défaut
  system_monitor    : toutes les 10 min (7-7) — monitoring composants + alertes
"""
import os
from app.logging_config import get_logger
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger

logger = get_logger("raya.scheduler")

_scheduler: BackgroundScheduler | None = None

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
        scheduler.add_job(func=_job_expire_pending, trigger=IntervalTrigger(hours=1),
                          id="expire_pending", name="Expiration des actions en attente", replace_existing=True)
        logger.info("[Scheduler] Job enregistré : expire_pending (toutes les heures)")
    else:
        logger.info("[Scheduler] Job DÉSACTIVÉ : expire_pending")

    if _job_enabled("SCHEDULER_DECAY_ENABLED"):
        scheduler.add_job(func=_job_confidence_decay, trigger=CronTrigger(day_of_week="mon", hour=2, minute=0),
                          id="confidence_decay", name="Décroissance de confiance", replace_existing=True)
        logger.info("[Scheduler] Job enregistré : confidence_decay (lundi 02h00)")
    else:
        logger.info("[Scheduler] Job DÉSACTIVÉ : confidence_decay")

    if _job_enabled("SCHEDULER_AUDIT_ENABLED"):
        scheduler.add_job(func=_job_opus_audit, trigger=CronTrigger(day_of_week="sun", hour=3, minute=0),
                          id="opus_audit", name="Audit de cohérence Opus", replace_existing=True)
        logger.info("[Scheduler] Job enregistré : opus_audit (dimanche 03h00)")
    else:
        logger.info("[Scheduler] Job DÉSACTIVÉ : opus_audit")

    if _job_enabled("SCHEDULER_WEBHOOK_ENABLED"):
        from datetime import datetime, timedelta
        scheduler.add_job(func=_job_webhook_setup, trigger="date",
                          run_date=datetime.now() + timedelta(seconds=30),
                          id="webhook_setup", replace_existing=True)
        scheduler.add_job(func=_job_webhook_renewal, trigger=IntervalTrigger(hours=6),
                          id="webhook_renewal", replace_existing=True)
        logger.info("[Scheduler] Jobs enregistrés : webhook_setup + webhook_renewal")
    else:
        logger.info("[Scheduler] Jobs DÉSACTIVÉS : webhook")

    if _job_enabled("SCHEDULER_TOKEN_ENABLED"):
        scheduler.add_job(func=_job_token_refresh, trigger=IntervalTrigger(minutes=45),
                          id="token_refresh", replace_existing=True)
        logger.info("[Scheduler] Job enregistré : token_refresh (45 min)")
    else:
        logger.info("[Scheduler] Job DÉSACTIVÉ : token_refresh")

    if _job_enabled("SCHEDULER_PROACTIVITY_ENABLED"):
        scheduler.add_job(func=_job_proactivity_scan, trigger=IntervalTrigger(minutes=30),
                          id="proactivity_scan", name="Scan proactif mails + agenda", replace_existing=True)
        logger.info("[Scheduler] Job enregistré : proactivity_scan (30 min)")
    else:
        logger.info("[Scheduler] Job DÉSACTIVÉ : proactivity_scan")

    if _job_enabled("SCHEDULER_PATTERNS_ENABLED"):
        scheduler.add_job(func=_job_pattern_analysis, trigger=CronTrigger(day_of_week="sun", hour=4, minute=0),
                          id="pattern_analysis", name="Détection de patterns comportementaux", replace_existing=True)
        logger.info("[Scheduler] Job enregistré : pattern_analysis (dimanche 04h00)")
    else:
        logger.info("[Scheduler] Job DÉSACTIVÉ : pattern_analysis")

    if _job_enabled("SCHEDULER_BRIEFING_ENABLED"):
        scheduler.add_job(func=_job_meeting_briefing, trigger=CronTrigger(hour=6, minute=30),
                          id="meeting_briefing", name="Briefings réunions du jour", replace_existing=True)
        logger.info("[Scheduler] Job enregistré : meeting_briefing (06h30)")
    else:
        logger.info("[Scheduler] Job DÉSACTIVÉ : meeting_briefing")

    if _job_enabled("SCHEDULER_HEARTBEAT_ENABLED"):
        scheduler.add_job(func=_job_heartbeat_morning, trigger=CronTrigger(hour=7, minute=0),
                          id="heartbeat_morning", name="Heartbeat matinal Raya", replace_existing=True)
        logger.info("[Scheduler] Job enregistré : heartbeat_morning (07h00)")
    else:
        logger.info("[Scheduler] Job DÉSACTIVÉ : heartbeat_morning")

    # Gmail polling — désactivé par défaut (activer via SCHEDULER_GMAIL_ENABLED=true)
    if _job_enabled("SCHEDULER_GMAIL_ENABLED", default=False):
        scheduler.add_job(func=_job_gmail_polling, trigger=IntervalTrigger(minutes=3),
                          id="gmail_polling", name="Gmail polling", replace_existing=True)
        logger.info("[Scheduler] Job enregistré : gmail_polling (3 min)")
    else:
        logger.info("[Scheduler] Job DÉSACTIVÉ : gmail_polling (activer via SCHEDULER_GMAIL_ENABLED=true)")

    # System monitor (7-7) — actif par défaut
    if _job_enabled("SCHEDULER_MONITOR_ENABLED"):
        scheduler.add_job(func=_job_system_monitor, trigger=IntervalTrigger(minutes=10),
                          id="system_monitor", name="Monitoring système", replace_existing=True)
        logger.info("[Scheduler] Job enregistré : system_monitor (10 min)")
    else:
        logger.info("[Scheduler] Job DÉSACTIVÉ : system_monitor")


# ─── FONCTIONS JOB ───

def _job_expire_pending():
    try:
        from app.pending_actions import expire_old_pending
        n = expire_old_pending()
        if n: logger.info(f"[Scheduler] expire_pending : {n} action(s) expirée(s)")
    except Exception as e:
        logger.error(f"[Scheduler] ERREUR expire_pending : {e}")


def _job_confidence_decay():
    """Décroissance de confiance adaptée par utilisateur (5G-2)."""
    try:
        from app.database import get_pg_conn
        from app.maturity import get_adaptive_params

        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("SELECT DISTINCT username FROM aria_rules WHERE active = true")
        users = [r[0] for r in c.fetchall()]

        total_decayed = 0
        total_masked  = 0

        for uname in users:
            try:
                params = get_adaptive_params(uname)
                decay = params["decay_per_week"]
                mask  = params["mask_threshold"]

                c.execute("""
                    UPDATE aria_rules SET confidence = GREATEST(0.0, confidence - %s), updated_at = NOW()
                    WHERE active = true AND username = %s
                      AND source NOT IN ('seed', 'onboarding')
                      AND updated_at < NOW() - INTERVAL '30 days'
                """, (decay, uname))
                total_decayed += c.rowcount

                c.execute("""
                    UPDATE aria_rules SET active = false, updated_at = NOW()
                    WHERE active = true AND username = %s
                      AND source NOT IN ('seed', 'onboarding')
                      AND confidence < %s
                """, (uname, mask))
                total_masked += c.rowcount
            except Exception as e:
                logger.error(f"[Scheduler] confidence_decay erreur {uname}: {e}")

        conn.commit()
        conn.close()
        parts = []
        if total_decayed: parts.append(f"{total_decayed} décrémentée(s)")
        if total_masked:  parts.append(f"{total_masked} masquée(s)")
        logger.info(f"[Scheduler] confidence_decay ({len(users)} users) : "
                    f"{', '.join(parts) if parts else 'aucune règle concernée'}")
    except Exception as e:
        logger.error(f"[Scheduler] ERREUR confidence_decay : {e}")


def _job_opus_audit():
    try:
        _ensure_audit_table()
        from app.database import get_pg_conn
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            SELECT tenant_id, username, COUNT(*) FROM aria_rules
            WHERE active = true AND source NOT IN ('seed')
            GROUP BY tenant_id, username HAVING COUNT(*) >= %s
        """, (AUDIT_MIN_RULES,))
        targets = c.fetchall()
        conn.close()
        if not targets:
            logger.info("[Scheduler] opus_audit : aucun tenant à auditer")
            return
        audited = 0
        for tenant_id, username, nb_rules in targets:
            try:
                _audit_one(tenant_id, username, nb_rules)
                audited += 1
            except Exception as e:
                logger.error(f"[Scheduler] ERREUR opus_audit {username}: {e}")
        logger.info(f"[Scheduler] opus_audit : {audited} tenant(s) audité(s)")
    except Exception as e:
        logger.error(f"[Scheduler] ERREUR opus_audit : {e}")


def _job_webhook_setup():
    try:
        from app.connectors.microsoft_webhook import ensure_all_subscriptions
        ensure_all_subscriptions()
        logger.info("[Scheduler] webhook_setup : OK")
    except Exception as e:
        logger.error(f"[Scheduler] ERREUR webhook_setup : {e}")


def _job_webhook_renewal():
    try:
        from app.connectors.microsoft_webhook import ensure_all_subscriptions
        ensure_all_subscriptions()
        logger.info("[Scheduler] webhook_renewal : OK")
    except Exception as e:
        logger.error(f"[Scheduler] ERREUR webhook_renewal : {e}")


def _job_token_refresh():
    try:
        from app.token_manager import get_valid_microsoft_token, get_all_users_with_tokens
        for username in get_all_users_with_tokens():
            try:
                token = get_valid_microsoft_token(username)
                if not token:
                    logger.error(f"[Scheduler] token_refresh ECHEC {username}")
                    try:
                        from app.connectors.microsoft_webhook import _send_revoked_alert
                        _send_revoked_alert(username)
                    except Exception:
                        pass
                else:
                    logger.info(f"[Scheduler] token_refresh {username}: OK")
            except Exception as e:
                logger.error(f"[Scheduler] token_refresh erreur {username}: {e}")
    except Exception as e:
        logger.error(f"[Scheduler] ERREUR token_refresh : {e}")


def _job_proactivity_scan():
    try:
        from app.database import get_pg_conn
        from app.proactive_alerts import create_alert, cleanup_expired
        cleanup_expired()
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("SELECT DISTINCT username FROM aria_memory WHERE created_at > NOW() - INTERVAL '7 days'")
        active_users = [r[0] for r in c.fetchall()]
        conn.close()
        for username in active_users:
            try:
                _scan_user(username)
            except Exception as e:
                logger.error(f"[Proactivity] Erreur scan {username}: {e}")
        logger.info(f"[Proactivity] Scan terminé — {len(active_users)} utilisateur(s)")
    except Exception as e:
        logger.error(f"[Proactivity] ERREUR scan global: {e}")


def _scan_user(username: str):
    from app.database import get_pg_conn
    from app.proactive_alerts import create_alert
    from app.app_security import get_tenant_id
    tenant_id = get_tenant_id(username)
    conn = get_pg_conn()
    c = conn.cursor()
    c.execute("""
        SELECT id, subject, from_email, priority, received_at FROM mail_memory
        WHERE username = %s AND priority = 'haute'
          AND created_at > NOW() - INTERVAL '48 hours'
          AND created_at < NOW() - INTERVAL '2 hours'
          AND id NOT IN (
              SELECT CAST(source_id AS INTEGER) FROM proactive_alerts
              WHERE username = %s AND source_type = 'mail'
                AND created_at > NOW() - INTERVAL '24 hours'
          ) LIMIT 5
    """, (username, username))
    for row in c.fetchall():
        create_alert(username=username, tenant_id=tenant_id, alert_type="mail_urgent", priority="high",
                     title=f"Mail urgent non traité : {row[1][:60]}",
                     body=f"De : {row[2]} — reçu il y a plus de 2h, priorité haute.",
                     source_type="mail", source_id=str(row[0]))
    c.execute("""
        SELECT id, subject, from_email, reply_urgency FROM mail_memory
        WHERE username = %s AND needs_reply = 1 AND reply_status = 'pending'
          AND created_at < NOW() - INTERVAL '24 hours'
          AND created_at > NOW() - INTERVAL '7 days'
          AND id NOT IN (
              SELECT CAST(source_id AS INTEGER) FROM proactive_alerts
              WHERE username = %s AND source_type = 'mail_reply'
                AND created_at > NOW() - INTERVAL '24 hours'
          ) LIMIT 5
    """, (username, username))
    for row in c.fetchall():
        prio = "high" if row[3] == "haute" else "normal"
        create_alert(username=username, tenant_id=tenant_id, alert_type="reminder", priority=prio,
                     title=f"Réponse en attente : {row[1][:60]}",
                     body=f"De : {row[2]} — en attente depuis plus de 24h.",
                     source_type="mail_reply", source_id=str(row[0]))
    conn.close()


def _job_gmail_polling():
    """Polling Gmail pour les utilisateurs avec credentials configurés. (7-1b)"""
    try:
        from app.connectors.gmail_connector import fetch_new_messages, is_configured
        from app.routes.webhook import process_incoming_mail
        from app.database import get_pg_conn

        if not is_configured():
            logger.info("[Gmail] GMAIL_CLIENT_ID / GMAIL_CLIENT_SECRET non configurés, skip")
            return

        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("SELECT username FROM users WHERE gmail_credentials IS NOT NULL")
        gmail_users = [r[0] for r in c.fetchall()]
        conn.close()

        if not gmail_users:
            return

        total = 0
        for username in gmail_users:
            try:
                messages = fetch_new_messages(username, max_results=20)
                for msg in messages:
                    process_incoming_mail(
                        username=username,
                        sender=msg["sender"],
                        subject=msg["subject"],
                        preview=msg["preview"],
                        message_id=msg["message_id"],
                        received_at=msg["received_at"],
                        mailbox_source="gmail",
                    )
                    total += 1
            except Exception as e:
                logger.error(f"[Gmail] Erreur polling {username}: {e}")

        if total > 0:
            logger.info(f"[Gmail] {total} nouveau(x) mail(s) traité(s)")

        # Heartbeat monitoring (7-7)
        try:
            from app.database import get_pg_conn as _hb_get
            _hb = _hb_get()
            _hb_c = _hb.cursor()
            _hb_c.execute("""
                INSERT INTO system_heartbeat (component, last_seen_at, status)
                VALUES ('gmail_polling', NOW(), 'ok')
                ON CONFLICT (component)
                DO UPDATE SET last_seen_at = NOW(), status = 'ok'
            """)
            _hb.commit()
            _hb.close()
        except Exception:
            pass

    except Exception as e:
        logger.error(f"[Gmail] ERREUR polling: {e}")


def _job_system_monitor():
    """Vérifie que tous les composants critiques sont actifs. (7-7)"""
    try:
        from app.database import get_pg_conn
        from datetime import datetime, timedelta

        conn = get_pg_conn()
        c = conn.cursor()

        # Enregistrer que le scheduler est vivant
        c.execute("""
            INSERT INTO system_heartbeat (component, last_seen_at, status)
            VALUES ('scheduler', NOW(), 'ok')
            ON CONFLICT (component)
            DO UPDATE SET last_seen_at = NOW(), status = 'ok'
        """)
        conn.commit()

        # Vérifier les composants critiques
        threshold = datetime.utcnow() - timedelta(minutes=15)
        c.execute("""
            SELECT component, last_seen_at, status FROM system_heartbeat
            WHERE last_seen_at < %s AND status != 'disabled'
        """, (threshold,))
        stale = c.fetchall()
        conn.close()

        if stale:
            stale_names = [r[0] for r in stale]
            logger.warning(f"[Monitor] Composants inactifs : {stale_names}")
            _send_monitor_alert(stale_names)

    except Exception as e:
        logger.error(f"[Monitor] ERREUR: {e}")


def _send_monitor_alert(stale_components: list):
    """Envoie une alerte monitoring via WhatsApp (fallback SMS). (7-7)"""
    phone = os.getenv("NOTIFICATION_PHONE_ADMIN", "").strip()
    if not phone:
        phone = os.getenv("NOTIFICATION_PHONE_GUILLAUME", "").strip()
    if not phone:
        phone = os.getenv("NOTIFICATION_PHONE_DEFAULT", "").strip()
    if not phone:
        return

    message = (
        f"⚠️ Raya Monitor — Composant(s) inactif(s) depuis >15min :\n"
        f"{', '.join(stale_components)}\n"
        f"Vérifier Railway."
    )

    # Essayer WhatsApp d'abord, SMS en fallback
    try:
        from app.connectors.twilio_connector import send_whatsapp, send_sms
        result = send_whatsapp(phone, message)
        if result.get("status") != "ok":
            send_sms(phone, message)
    except Exception:
        try:
            from app.connectors.twilio_connector import send_sms
            send_sms(phone, message)
        except Exception as e:
            logger.error(f"[Monitor] Impossible d'alerter: {e}")


def _job_meeting_briefing():
    """Prépare des briefings pour les réunions du jour. (7-BRIEF)"""
    try:
        from app.database import get_pg_conn

        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            SELECT DISTINCT username FROM aria_memory
            WHERE created_at > NOW() - INTERVAL '7 days'
        """)
        active_users = [r[0] for r in c.fetchall()]
        conn.close()

        for username in active_users:
            try:
                _prepare_briefings(username)
            except Exception as e:
                logger.error(f"[Briefing] Erreur {username}: {e}")

        logger.info(f"[Briefing] Scan terminé — {len(active_users)} utilisateur(s)")
    except Exception as e:
        logger.error(f"[Briefing] ERREUR: {e}")


def _prepare_briefings(username: str):
    """Prépare un briefing pour chaque réunion du jour."""
    from app.token_manager import get_valid_microsoft_token
    from app.connectors.outlook_connector import perform_outlook_action
    from app.proactive_alerts import create_alert
    from app.app_security import get_tenant_id
    from app.llm_client import llm_complete, log_llm_usage
    from app.database import get_pg_conn
    from datetime import datetime, timezone
    import json

    token = get_valid_microsoft_token(username)
    if not token:
        return

    tenant_id = get_tenant_id(username)

    now = datetime.now(timezone.utc)
    start = now.replace(hour=0, minute=0, second=0).isoformat()
    end = now.replace(hour=23, minute=59, second=59).isoformat()
    try:
        result = perform_outlook_action("list_calendar_events",
            {"start": start, "end": end, "top": 10}, token)
        events = result.get("items", [])
    except Exception:
        return

    if not events:
        return

    for event in events:
        subject = event.get("subject", "")
        attendees = event.get("attendees", [])
        event_start = event.get("start", "")

        if not subject or not attendees:
            continue

        attendee_emails = [a.get("email", "") for a in attendees if a.get("email")]
        if not attendee_emails:
            continue

        conn = get_pg_conn()
        c = conn.cursor()
        placeholders = ",".join(["%s"] * len(attendee_emails))
        c.execute(f"""
            SELECT from_email, subject, short_summary, received_at
            FROM mail_memory
            WHERE username = %s AND from_email IN ({placeholders})
            ORDER BY received_at DESC LIMIT 5
        """, [username] + attendee_emails)
        recent_mails = c.fetchall()
        conn.close()

        narratives_text = ""
        try:
            from app.narrative import search_narratives
            narrs = search_narratives(subject, username, tenant_id=tenant_id, limit=2)
            if narrs:
                narratives_text = "\n".join(
                    f"  {n['entity_key']}: {n['narrative'][:200]}" for n in narrs
                )
        except Exception:
            pass

        mails_text = "\n".join(
            f"  {r[0]} — {r[1]} ({r[3]})" for r in recent_mails
        ) if recent_mails else "Aucun mail récent."

        prompt = (
            f"Réunion aujourd'hui : {subject}\n"
            f"Heure : {event_start}\n"
            f"Participants : {', '.join(attendee_emails)}\n\n"
            f"Mails récents avec ces participants :\n{mails_text}\n\n"
            f"Contexte dossiers :\n{narratives_text or 'Aucun dossier connu.'}\n\n"
            f"Prépare un briefing de 3-5 lignes pour cette réunion : "
            f"contexte, points en suspens, choses à préparer."
        )

        try:
            result = llm_complete(
                messages=[{"role": "user", "content": prompt}],
                model_tier="fast",
                max_tokens=300,
                system="Tu es Raya. Prépare un briefing concis et actionnable.",
            )
            briefing = result["text"].strip()
            log_llm_usage(result, username=username, tenant_id=tenant_id,
                          purpose="meeting_briefing")
        except Exception:
            briefing = (
                f"Réunion '{subject}' avec {', '.join(attendee_emails[:3])}. "
                f"{len(recent_mails)} mail(s) récent(s)."
            )

        create_alert(
            username=username, tenant_id=tenant_id,
            alert_type="reminder", priority="normal",
            title=f"\U0001f4cb Briefing : {subject[:60]}",
            body=briefing[:500],
            source_type="calendar_briefing",
            source_id=event.get("id", subject[:50]),
        )

    logger.info(f"[Briefing] {username} : {len(events)} événement(s) traité(s)")


def _job_heartbeat_morning():
    """
    Prépare le rapport matinal et envoie un PING (pas le contenu). (7-6R)
    Le rapport est stocké dans daily_reports. L'utilisateur décide
    comment le recevoir (chat, vocal, mail, WhatsApp).
    """
    try:
        from app.database import get_pg_conn

        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            SELECT DISTINCT username FROM aria_memory
            WHERE created_at > NOW() - INTERVAL '7 days'
        """)
        active_users = [r[0] for r in c.fetchall()]
        conn.close()

        prepared = 0
        for username in active_users:
            try:
                _prepare_daily_report(username)
                _send_report_ping(username)
                prepared += 1
            except Exception as e:
                logger.error(f"[Heartbeat] Erreur {username}: {e}")

        logger.info(f"[Heartbeat] {prepared} rapport(s) préparé(s)")
    except Exception as e:
        logger.error(f"[Heartbeat] ERREUR: {e}")


def _prepare_daily_report(username: str):
    """Prépare et stocke le rapport du jour dans daily_reports. Ne l'envoie PAS."""
    from app.database import get_pg_conn
    from app.app_security import get_tenant_id
    import json

    tenant_id = get_tenant_id(username)
    conn = get_pg_conn()
    c = conn.cursor()

    sections = []

    # Section 1 : Mails (12 dernières heures)
    c.execute("""
        SELECT COUNT(*) as total,
               COUNT(*) FILTER (WHERE priority = 'haute') as urgent,
               COUNT(*) FILTER (WHERE priority = 'moyenne') as moyen,
               COUNT(*) FILTER (WHERE needs_reply = 1 AND reply_status = 'pending') as a_repondre
        FROM mail_memory
        WHERE username = %s AND created_at > NOW() - INTERVAL '12 hours'
    """, (username,))
    stats = c.fetchone()
    total = stats[0] or 0
    urgent = stats[1] or 0
    moyen = stats[2] or 0
    a_repondre = stats[3] or 0
    silencieux = max(0, total - urgent - moyen)

    mail_lines = []
    if total > 0:
        mail_lines.append(f"{total} mail(s) :")
        if urgent > 0: mail_lines.append(f"  \U0001f534 {urgent} urgent(s)")
        if moyen > 0: mail_lines.append(f"  \U0001f7e1 {moyen} à voir")
        if silencieux > 0: mail_lines.append(f"  \u26aa {silencieux} silencieux")
    else:
        mail_lines.append("Nuit calme, aucun mail notable.")
    if a_repondre > 0:
        mail_lines.append(f"\u2709\ufe0f {a_repondre} réponse(s) en attente")

    sections.append({
        "type": "mails",
        "title": "Mails de la nuit",
        "content": "\n".join(mail_lines),
    })

    # Section 2 : Alertes actives
    c.execute("""
        SELECT COUNT(*) FROM proactive_alerts
        WHERE username = %s AND seen = false AND dismissed = false
          AND (expires_at IS NULL OR expires_at > NOW())
    """, (username,))
    alerts_count = c.fetchone()[0]
    if alerts_count > 0:
        sections.append({
            "type": "alerts",
            "title": "Alertes",
            "content": f"\u26a0\ufe0f {alerts_count} alerte(s) active(s) à consulter.",
        })

    full_content = "\n\n".join(
        f"\U0001f4cc {s['title']}\n{s['content']}" for s in sections
    )
    full_content = f"\u2600\ufe0f Bonjour ! Raya veille.\n\n{full_content}"

    c.execute("""
        INSERT INTO daily_reports (username, tenant_id, content, sections)
        VALUES (%s, %s, %s, %s::jsonb)
        ON CONFLICT (username, report_date)
        DO UPDATE SET content = EXCLUDED.content, sections = EXCLUDED.sections,
                      created_at = NOW()
    """, (username, tenant_id, full_content, json.dumps(sections, ensure_ascii=False)))
    conn.commit()
    conn.close()


def _send_report_ping(username: str):
    """Envoie un PING léger pour prévenir que le rapport est prêt."""
    phone = os.getenv(f"NOTIFICATION_PHONE_{username.upper()}", "").strip()
    if not phone:
        phone = os.getenv("NOTIFICATION_PHONE_DEFAULT", "").strip()
    if not phone:
        return

    try:
        from app.notification_prefs import should_notify
        if not should_notify(username, "normal"):
            return
    except Exception:
        pass

    try:
        from app.connectors.twilio_connector import send_whatsapp
        send_whatsapp(phone, "\u2600\ufe0f Raya — Ton rapport matinal est prêt.\nDis-moi comment tu veux le recevoir.")
    except Exception as e:
        logger.error(f"[Heartbeat] Ping échoué {username}: {e}")


def _job_pattern_analysis():
    """Détecte les patterns comportementaux — hebdomadaire dimanche 04h00 (5G-4 + 7-WF)."""
    try:
        from app.database import get_pg_conn
        from app.maturity import compute_maturity_score

        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            SELECT username, COUNT(*) FROM aria_memory
            GROUP BY username HAVING COUNT(*) > 20
        """)
        candidates = [r[0] for r in c.fetchall()]
        conn.close()

        analyzed = 0
        for username in candidates:
            try:
                maturity = compute_maturity_score(username)
                if maturity["phase"] == "discovery":
                    continue
                _analyze_patterns(username)
                analyzed += 1
            except Exception as e:
                logger.error(f"[Patterns] Erreur analyse {username}: {e}")

        logger.info(f"[Patterns] Analyse terminée — {analyzed}/{len(candidates)} utilisateur(s)")
    except Exception as e:
        logger.error(f"[Patterns] ERREUR job global: {e}")


def _analyze_patterns(username: str):
    """Détecte les patterns récurrents (conversations + mails + activity_log). (5G-4 + 7-WF)"""
    import json, re
    from app.database import get_pg_conn
    from app.llm_client import llm_complete, log_llm_usage
    from app.app_security import get_tenant_id

    tenant_id = get_tenant_id(username)
    conn = get_pg_conn()
    c = conn.cursor()

    c.execute("""
        SELECT user_input, aria_response, created_at FROM aria_memory
        WHERE username = %s ORDER BY created_at DESC LIMIT 50
    """, (username,))
    convs = [{"q": r[0][:150], "r": r[1][:100], "date": str(r[2])} for r in c.fetchall()]

    c.execute("""
        SELECT from_email, subject, category, priority, created_at FROM mail_memory
        WHERE username = %s AND created_at > NOW() - INTERVAL '30 days'
        ORDER BY created_at DESC LIMIT 100
    """, (username,))
    mails = [{"from": r[0], "subject": r[1][:60], "cat": r[2], "prio": r[3],
              "date": str(r[4])} for r in c.fetchall()]

    activities = []
    try:
        c.execute("""
            SELECT action_type, action_target, action_detail, tenant_id,
                   created_at::text as ts
            FROM activity_log
            WHERE username = %s AND created_at > NOW() - INTERVAL '30 days'
            ORDER BY created_at DESC LIMIT 150
        """, (username,))
        activities = [{"type": r[0], "target": r[1][:50] if r[1] else "",
                       "detail": r[2][:60] if r[2] else "", "date": r[4]}
                      for r in c.fetchall()]
    except Exception:
        pass

    c.execute("""
        SELECT pattern_type, description FROM aria_patterns
        WHERE username = %s AND active = true ORDER BY confidence DESC LIMIT 20
    """, (username,))
    existing = [{"type": r[0], "desc": r[1]} for r in c.fetchall()]
    conn.close()

    if len(convs) < 10:
        return

    activities_section = f"""
ACTIVITÉS (actions via Raya, 30 derniers jours) :
{json.dumps(activities[:80], ensure_ascii=False)}
""" if activities else ""

    prompt = f"""Tu es Raya en mode analyse interne.
INTERDIT : ne JAMAIS inclure le mot "Jarvis" dans les descriptions de patterns.
Voici les 50 dernières conversations, 100 derniers mails et les actions récentes de {username}.

CONVERSATIONS :
{json.dumps(convs[:30], ensure_ascii=False)}

MAILS (30 derniers jours) :
{json.dumps(mails[:50], ensure_ascii=False)}
{activities_section}
PATTERNS DÉJÀ CONNUS :
{json.dumps(existing, ensure_ascii=False) if existing else "Aucun."}

Détecte les NOUVEAUX comportements récurrents :
- temporal : "traite les mails X le jour Y"
- relational : "quand X envoie un mail, c'est toujours Y"
- thematic : "après un mail chantier, cherche toujours le dossier"
- workflow : séquences d'actions répétitives. Sois PRÉCIS sur la séquence.
- preference : "préfère des réponses courtes"

Ne répète PAS les patterns déjà connus.
Réponds en JSON strict (sans backticks) :
{{"new_patterns": [
  {{"type": "temporal|relational|thematic|workflow|preference",
    "description": "description claire en français",
    "evidence": "exemples concrets",
    "confidence": 0.0-1.0}}
]}}
Si aucun nouveau pattern : {{"new_patterns": []}}"""

    result = llm_complete(messages=[{"role": "user", "content": prompt}],
                          model_tier="deep", max_tokens=1200)
    log_llm_usage(result, username=username, tenant_id=tenant_id, purpose="pattern_analysis")

    raw = re.sub(r'^```(?:json)?\s*', '', result["text"].strip(), flags=re.MULTILINE)
    raw = re.sub(r'\s*```$', '', raw, flags=re.MULTILINE).strip()
    parsed = json.loads(raw)

    conn = get_pg_conn()
    c = conn.cursor()
    inserted = 0
    for p in parsed.get("new_patterns", []):
        c.execute("""
            INSERT INTO aria_patterns (username, tenant_id, pattern_type, description, evidence, confidence)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (username, tenant_id, p["type"], p["description"],
               p.get("evidence", ""), p.get("confidence", 0.5)))
        inserted += 1
    conn.commit()
    conn.close()
    logger.info(f"[Patterns] {username} : {inserted} nouveau(x) pattern(s)")


def _audit_one(tenant_id: str, username: str, nb_rules: int):
    import json, re
    from app.database import get_pg_conn
    from app.llm_client import llm_complete, log_llm_usage
    conn = get_pg_conn()
    c = conn.cursor()
    c.execute("""
        SELECT id, category, rule, confidence, reinforcements, source FROM aria_rules
        WHERE active = true AND tenant_id = %s AND username = %s
        ORDER BY confidence DESC, reinforcements DESC LIMIT 80
    """, (tenant_id, username))
    rows = c.fetchall()
    conn.close()
    if not rows: return
    rules_text = "\n".join([f"[id:{r[0]}][{r[1]}] {r[2]}  (conf={r[3]:.2f}, renf={r[4]}, src={r[5]})" for r in rows])
    prompt = f"""Tu es Raya, en mode audit interne.\nVoici les {len(rows)} règles actives de {username} :\n{rules_text}\n\nIdentifie :\n1. CONTRADICTIONS\n2. REDONDANCES\n3. OBSOLÈTES\n\nRéponds en JSON strict (sans backticks) :\n{{\"contradictions\": [{{\"ids\": [id1, id2], \"explication\": \"...\"}}], \"redondances\": [{{\"ids\": [id1, id2], \"explication\": \"...\"}}], \"obsoletes\": [{{\"id\": id, \"explication\": \"...\"}}], \"score_coherence\": 0.0, \"resume\": \"...\"}}\n\nSi aucun problème : listes vides et score_coherence proche de 1.0."""
    result = llm_complete(messages=[{"role": "user", "content": prompt}], model_tier="deep", max_tokens=1200)
    log_llm_usage(result, username=username, tenant_id=tenant_id, purpose="opus_audit")
    raw = re.sub(r'^```(?:json)?\s*', '', result["text"].strip(), flags=re.MULTILINE)
    raw = re.sub(r'\s*```$', '', raw, flags=re.MULTILINE).strip()
    parsed = json.loads(raw)
    conn = get_pg_conn()
    c = conn.cursor()
    c.execute("""
        INSERT INTO aria_rule_audit (tenant_id, username, rules_analyzed, suggestions_json, score_coherence, resume)
        VALUES (%s, %s, %s, %s::jsonb, %s, %s)
    """, (tenant_id, username, len(rows), json.dumps(parsed, ensure_ascii=False),
           parsed.get("score_coherence"), parsed.get("resume", "")))
    conn.commit()
    conn.close()
    nb_issues = len(parsed.get("contradictions", [])) + len(parsed.get("redondances", [])) + len(parsed.get("obsoletes", []))
    logger.info(f"[Scheduler] opus_audit {username} : {nb_rules} règles, {nb_issues} problème(s), score={parsed.get('score_coherence', '?')}")


def _ensure_audit_table():
    try:
        from app.database import get_pg_conn
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS aria_rule_audit (
                id SERIAL PRIMARY KEY, tenant_id TEXT NOT NULL, username TEXT NOT NULL,
                audit_date DATE DEFAULT CURRENT_DATE, rules_analyzed INTEGER,
                suggestions_json JSONB DEFAULT '{}', score_coherence REAL,
                resume TEXT, created_at TIMESTAMP DEFAULT NOW()
            )
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_rule_audit_user ON aria_rule_audit (tenant_id, username, audit_date DESC)")
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"[Scheduler] ERREUR _ensure_audit_table : {e}")
