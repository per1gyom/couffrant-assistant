"""
Scheduler de jobs périodiques Raya — Phase 4.

Utilise APScheduler (BackgroundScheduler) pour exécuter des tâches
de maintenance sans bloquer le serveur FastAPI.

Variables d'environnement pour désactiver un job individuellement
(filet de sécurité — couper un job sans toucher au code) :
  SCHEDULER_EXPIRE_ENABLED=false   → désactive expire_pending
  SCHEDULER_DECAY_ENABLED=false    → désactive confidence_decay
  SCHEDULER_AUDIT_ENABLED=false    → désactive opus_audit
  SCHEDULER_WEBHOOK_ENABLED=false  → désactive webhook_setup + webhook_renewal
  SCHEDULER_TOKEN_ENABLED=false    → désactive token_refresh

Valeur par défaut : true (tous les jobs actifs).
Exemple Railway : ajouter SCHEDULER_AUDIT_ENABLED=false pour couper l'audit
sans redéploiement.

Jobs :
  expire_pending   : toutes les heures          — expire les pending_actions trop vieilles
  confidence_decay : hebdomadaire lundi 02h00   — décroissance de confiance (B6)
  opus_audit       : hebdomadaire dimanche 03h00 — audit de cohérence Opus (B5)
  webhook_setup    : 30s après démarrage (une fois) — setup initial des webhooks Microsoft
  webhook_renewal  : toutes les 6 heures            — renouvellement des webhooks Microsoft
  token_refresh    : toutes les 45 minutes           — refresh des tokens Microsoft

[à venir]
  proactivity_scan : toutes les 30 min          — alertes et rappels intelligents (B10)
"""
import os
import logging
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)

_scheduler: BackgroundScheduler | None = None

CONFIDENCE_MASK_THRESHOLD = 0.3
CONFIDENCE_DECAY_STEP     = 0.05
AUDIT_MIN_RULES           = 5


def _job_enabled(env_var: str) -> bool:
    """Retourne True si le job est activé (défaut : True)."""
    return os.getenv(env_var, "true").lower() not in ("false", "0", "no", "off")


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
    """Démarre le scheduler et enregistre les jobs actifs. Idémpotent."""
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
    Enregistre les jobs activés (contrôlés par variables d'environnement).
    Un job désactivé n'est simplement pas enregistré — pas d'erreur, pas de bruit.
    """

    if _job_enabled("SCHEDULER_EXPIRE_ENABLED"):
        scheduler.add_job(
            func=_job_expire_pending,
            trigger=IntervalTrigger(hours=1),
            id="expire_pending",
            name="Expiration des actions en attente",
            replace_existing=True,
        )
        print("[Scheduler] Job enregistré : expire_pending (toutes les heures)")
    else:
        print("[Scheduler] Job DÉSACTIVÉ : expire_pending (SCHEDULER_EXPIRE_ENABLED=false)")

    if _job_enabled("SCHEDULER_DECAY_ENABLED"):
        scheduler.add_job(
            func=_job_confidence_decay,
            trigger=CronTrigger(day_of_week="mon", hour=2, minute=0),
            id="confidence_decay",
            name="Décroissance de confiance des règles inactives",
            replace_existing=True,
        )
        print("[Scheduler] Job enregistré : confidence_decay (lundi 02h00)")
    else:
        print("[Scheduler] Job DÉSACTIVÉ : confidence_decay (SCHEDULER_DECAY_ENABLED=false)")

    if _job_enabled("SCHEDULER_AUDIT_ENABLED"):
        scheduler.add_job(
            func=_job_opus_audit,
            trigger=CronTrigger(day_of_week="sun", hour=3, minute=0),
            id="opus_audit",
            name="Audit de cohérence des règles par Opus",
            replace_existing=True,
        )
        print("[Scheduler] Job enregistré : opus_audit (dimanche 03h00)")
    else:
        print("[Scheduler] Job DÉSACTIVÉ : opus_audit (SCHEDULER_AUDIT_ENABLED=false)")

    if _job_enabled("SCHEDULER_WEBHOOK_ENABLED"):
        from datetime import datetime, timedelta
        scheduler.add_job(
            func=_job_webhook_setup,
            trigger="date",
            run_date=datetime.now() + timedelta(seconds=30),
            id="webhook_setup",
            name="Setup initial webhooks Microsoft",
            replace_existing=True,
        )
        scheduler.add_job(
            func=_job_webhook_renewal,
            trigger=IntervalTrigger(hours=6),
            id="webhook_renewal",
            name="Renouvellement webhooks Microsoft",
            replace_existing=True,
        )
        print("[Scheduler] Jobs enregistrés : webhook_setup (30s) + webhook_renewal (6h)")
    else:
        print("[Scheduler] Jobs DÉSACTIVÉS : webhook (SCHEDULER_WEBHOOK_ENABLED=false)")

    if _job_enabled("SCHEDULER_TOKEN_ENABLED"):
        scheduler.add_job(
            func=_job_token_refresh,
            trigger=IntervalTrigger(minutes=45),
            id="token_refresh",
            name="Refresh tokens Microsoft",
            replace_existing=True,
        )
        print("[Scheduler] Job enregistré : token_refresh (45 min)")
    else:
        print("[Scheduler] Job DÉSACTIVÉ : token_refresh (SCHEDULER_TOKEN_ENABLED=false)")


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
    - Règles non touchées depuis > 30j : confidence -= 0.05
    - Confidence < 0.3 → masquées (active=false), pas supprimées
    - Règles seed et onboarding sont protégées
    """
    try:
        from app.database import get_pg_conn
        conn = get_pg_conn()
        c = conn.cursor()

        c.execute("""
            UPDATE aria_rules
            SET confidence = GREATEST(0.0, confidence - %s),
                updated_at = NOW()
            WHERE active = true
              AND source NOT IN ('seed', 'onboarding')
              AND updated_at < NOW() - INTERVAL '30 days'
        """, (CONFIDENCE_DECAY_STEP,))
        decayed = c.rowcount

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

        parts = []
        if decayed: parts.append(f"{decayed} décrémentée(s)")
        if masked:  parts.append(f"{masked} masquée(s) (conf < {CONFIDENCE_MASK_THRESHOLD})")
        print(f"[Scheduler] confidence_decay : {', '.join(parts) if parts else 'aucune règle concernée'}")

    except Exception as e:
        print(f"[Scheduler] ERREUR confidence_decay : {e}")


def _job_opus_audit():
    """
    Audit de cohérence des règles par Opus — hebdomadaire (B5).
    Résultats stockés dans aria_rule_audit (suggestions, pas actions auto).
    """
    try:
        _ensure_audit_table()

        from app.database import get_pg_conn
        conn = get_pg_conn()
        c = conn.cursor()

        c.execute("""
            SELECT tenant_id, username, COUNT(*) as nb
            FROM aria_rules
            WHERE active = true AND source NOT IN ('seed')
            GROUP BY tenant_id, username
            HAVING COUNT(*) >= %s
        """, (AUDIT_MIN_RULES,))
        targets = c.fetchall()
        conn.close()

        if not targets:
            print("[Scheduler] opus_audit : aucun tenant à auditer")
            return

        audited = 0
        for tenant_id, username, nb_rules in targets:
            try:
                _audit_one(tenant_id, username, nb_rules)
                audited += 1
            except Exception as e:
                print(f"[Scheduler] ERREUR opus_audit {username}: {e}")

        print(f"[Scheduler] opus_audit : {audited} tenant(s) audité(s)")

    except Exception as e:
        print(f"[Scheduler] ERREUR opus_audit : {e}")


def _job_webhook_setup():
    """Setup initial des webhooks Microsoft — exécuté une seule fois 30s après démarrage."""
    try:
        from app.connectors.microsoft_webhook import ensure_all_subscriptions
        ensure_all_subscriptions()
        print("[Scheduler] webhook_setup : OK")
    except Exception as e:
        print(f"[Scheduler] ERREUR webhook_setup : {e}")


def _job_webhook_renewal():
    """Renouvellement des webhooks Microsoft toutes les 6h."""
    try:
        from app.connectors.microsoft_webhook import ensure_all_subscriptions
        ensure_all_subscriptions()
        print("[Scheduler] webhook_renewal : OK")
    except Exception as e:
        print(f"[Scheduler] ERREUR webhook_renewal : {e}")


def _job_token_refresh():
    """Refresh des tokens Microsoft toutes les 45 min."""
    try:
        from app.token_manager import get_valid_microsoft_token, get_all_users_with_tokens
        for username in get_all_users_with_tokens():
            try:
                token = get_valid_microsoft_token(username)
                if not token:
                    print(f"[Scheduler] token_refresh ECHEC {username}")
                    try:
                        from app.connectors.microsoft_webhook import _send_revoked_alert
                        _send_revoked_alert(username)
                    except Exception:
                        pass
                else:
                    print(f"[Scheduler] token_refresh {username}: OK")
            except Exception as e:
                print(f"[Scheduler] token_refresh erreur {username}: {e}")
    except Exception as e:
        print(f"[Scheduler] ERREUR token_refresh : {e}")


def _audit_one(tenant_id: str, username: str, nb_rules: int):
    """Audite les règles d'un utilisateur via Opus et stocke les suggestions."""
    import json, re
    from app.database import get_pg_conn
    from app.llm_client import llm_complete, log_llm_usage

    conn = get_pg_conn()
    c = conn.cursor()
    c.execute("""
        SELECT id, category, rule, confidence, reinforcements, source
        FROM aria_rules
        WHERE active = true AND tenant_id = %s AND username = %s
        ORDER BY confidence DESC, reinforcements DESC
        LIMIT 80
    """, (tenant_id, username))
    rows = c.fetchall()
    conn.close()

    if not rows:
        return

    rules_text = "\n".join([
        f"[id:{r[0]}][{r[1]}] {r[2]}  (conf={r[3]:.2f}, renf={r[4]}, src={r[5]})"
        for r in rows
    ])

    prompt = f"""Tu es Raya, en mode audit interne.

Voici les {len(rows)} règles actives de {username} :

{rules_text}

Identifie :
1. CONTRADICTIONS : deux règles qui se contredisent
2. REDONDANCES : règles qui disent la même chose différemment
3. OBSOLÈTES : règles probablement dépassées

Réponds en JSON strict (sans backticks) :
{{
  "contradictions": [{{"ids": [id1, id2], "explication": "..."}}],
  "redondances":    [{{"ids": [id1, id2], "explication": "..."}}],
  "obsoletes":      [{{"id": id, "explication": "..."}}],
  "score_coherence": 0.0,
  "resume": "résumé en 1-2 phrases"
}}

Si aucun problème : listes vides et score_coherence proche de 1.0.
Ne suggère aucune action automatique."""

    result = llm_complete(
        messages=[{"role": "user", "content": prompt}],
        model_tier="deep",
        max_tokens=1200,
    )
    log_llm_usage(result, username=username, tenant_id=tenant_id, purpose="opus_audit")

    raw = re.sub(r'^```(?:json)?\s*', '', result["text"].strip(), flags=re.MULTILINE)
    raw = re.sub(r'\s*```$', '', raw, flags=re.MULTILINE).strip()
    parsed = json.loads(raw)

    conn = get_pg_conn()
    c = conn.cursor()
    c.execute("""
        INSERT INTO aria_rule_audit
          (tenant_id, username, rules_analyzed, suggestions_json, score_coherence, resume)
        VALUES (%s, %s, %s, %s::jsonb, %s, %s)
    """, (
        tenant_id, username, len(rows),
        json.dumps(parsed, ensure_ascii=False),
        parsed.get("score_coherence"),
        parsed.get("resume", ""),
    ))
    conn.commit()
    conn.close()

    nb_issues = (
        len(parsed.get("contradictions", [])) +
        len(parsed.get("redondances", [])) +
        len(parsed.get("obsoletes", []))
    )
    print(f"[Scheduler] opus_audit {username} : {nb_rules} règles, "
          f"{nb_issues} problème(s), score={parsed.get('score_coherence', '?')}")


def _ensure_audit_table():
    """Crée la table aria_rule_audit si elle n'existe pas encore."""
    try:
        from app.database import get_pg_conn
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS aria_rule_audit (
                id               SERIAL PRIMARY KEY,
                tenant_id        TEXT NOT NULL,
                username         TEXT NOT NULL,
                audit_date       DATE DEFAULT CURRENT_DATE,
                rules_analyzed   INTEGER,
                suggestions_json JSONB DEFAULT '{}',
                score_coherence  REAL,
                resume           TEXT,
                created_at       TIMESTAMP DEFAULT NOW()
            )
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_rule_audit_user ON aria_rule_audit (tenant_id, username, audit_date DESC)")
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[Scheduler] ERREUR _ensure_audit_table : {e}")
