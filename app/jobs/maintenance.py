"""
Jobs de maintenance périodique : expire, audit, token refresh, webhook renewal.
"""
import json
import re
from app.logging_config import get_logger

logger = get_logger("raya.scheduler")
AUDIT_MIN_RULES = 5


def _job_expire_pending():
    """Expire les actions pending trop vieilles."""
    try:
        from app.pending_actions import expire_old_pending
        n = expire_old_pending()
        if n:
            logger.info(f"[Scheduler] expire_pending : {n} action(s) expirée(s)")
    except Exception as e:
        logger.error(f"[Scheduler] ERREUR expire_pending : {e}")


def _job_opus_audit():
    """Audit de cohérence des règles — dimanche 03h00."""
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
    """Vérifie que tous les tokens Microsoft V2 sont valides, alerte si révoqués."""
    try:
        from app.connection_token_manager import (
            get_all_users_with_tool_connections, get_connection_token
        )
        users = get_all_users_with_tool_connections("microsoft")
        for username in users:
            try:
                token = get_connection_token(username, "microsoft")
                if not token:
                    logger.error(f"[Scheduler] token_refresh ECHEC {username}")
                    try:
                        from app.connectors.microsoft_webhook import _send_revoked_alert
                        _send_revoked_alert(username)
                    except Exception:
                        pass
                else:
                    logger.debug(f"[Scheduler] token_refresh {username}: OK")
            except Exception as e:
                logger.error(f"[Scheduler] token_refresh erreur {username}: {e}")
    except Exception as e:
        logger.error(f"[Scheduler] ERREUR token_refresh : {e}")


def _audit_one(tenant_id: str, username: str, nb_rules: int):
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
    if not rows:
        return
    rules_text = "\n".join(
        f"[id:{r[0]}][{r[1]}] {r[2]}  (conf={r[3]:.2f}, renf={r[4]}, src={r[5]})"
        for r in rows
    )
    prompt = (
        f"Tu es Raya, en mode audit interne.\n"
        f"Voici les {len(rows)} règles actives de {username} :\n{rules_text}\n\n"
        f"Identifie :\n1. CONTRADICTIONS\n2. REDONDANCES\n3. OBSOLÈTES\n\n"
        f'Réponds en JSON strict (sans backticks) :\n'
        f'{{"contradictions": [{{"ids": [id1, id2], "explication": "..."}}], '
        f'"redondances": [{{"ids": [id1, id2], "explication": "..."}}], '
        f'"obsoletes": [{{"id": id, "explication": "..."}}], '
        f'"score_coherence": 0.0, "resume": "..."}}\n\n'
        f"Si aucun problème : listes vides et score_coherence proche de 1.0."
    )
    result = llm_complete(messages=[{"role": "user", "content": prompt}],
                          model_tier="deep", max_tokens=1200)
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
    """, (tenant_id, username, len(rows), json.dumps(parsed, ensure_ascii=False),
           parsed.get("score_coherence"), parsed.get("resume", "")))
    conn.commit()
    conn.close()
    nb_issues = (
        len(parsed.get("contradictions", []))
        + len(parsed.get("redondances", []))
        + len(parsed.get("obsoletes", []))
    )
    logger.info(
        f"[Scheduler] opus_audit {username} : {nb_rules} règles, "
        f"{nb_issues} problème(s), score={parsed.get('score_coherence', '?')}"
    )


def _ensure_audit_table():
    try:
        from app.database import get_pg_conn
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS aria_rule_audit (
                id SERIAL PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                username TEXT NOT NULL,
                audit_date DATE DEFAULT CURRENT_DATE,
                rules_analyzed INTEGER,
                suggestions_json JSONB DEFAULT '{}',
                score_coherence REAL,
                resume TEXT,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """)
        c.execute(
            "CREATE INDEX IF NOT EXISTS idx_rule_audit_user "
            "ON aria_rule_audit (tenant_id, username, audit_date DESC)"
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"[Scheduler] ERREUR _ensure_audit_table : {e}")
