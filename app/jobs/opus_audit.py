"""
Audit hebdomadaire de cohérence des règles par Opus (décision Opus B5) — Phase 4.

Planification : dimanche à 2h00 (app/scheduler.py)

Workflow :
  1. Charge les règles actives de chaque tenant (max 80)
  2. Appel Opus → JSON : {contradictions, redondances, obsoletes, suggestions, resume}
  3. Stocke le rapport dans opus_audit_reports
  4. Consultable via GET /admin/audit

IMPORTANT : résultats = SUGGESTIONS uniquement.
Aucune règle n'est modifiée ou supprimée automatiquement.
L'utilisateur valide les suggestions depuis le panel admin.
"""
import json
from app.database import get_pg_conn


def _ensure_table():
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS opus_audit_reports (
                id           SERIAL PRIMARY KEY,
                tenant_id    TEXT NOT NULL,
                run_at       TIMESTAMP DEFAULT NOW(),
                rules_count  INTEGER,
                report_json  JSONB NOT NULL DEFAULT '{}',
                status       TEXT DEFAULT 'done'
            )
        """)
        c.execute(
            "CREATE INDEX IF NOT EXISTS idx_audit_tenant_date "
            "ON opus_audit_reports (tenant_id, run_at DESC)"
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[OpusAudit] Migration table : {e}")


_ensure_table()


def _load_rules_for_audit(tenant_id: str, limit: int = 80) -> list:
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            SELECT id, category, rule, confidence, reinforcements, source
            FROM aria_rules
            WHERE active = true
              AND (tenant_id = %s OR tenant_id IS NULL)
              AND category != 'Mémoire'
            ORDER BY confidence DESC, reinforcements DESC
            LIMIT %s
        """, (tenant_id, limit))
        cols = [d[0] for d in c.description]
        rows = [dict(zip(cols, r)) for r in c.fetchall()]
        conn.close()
        return rows
    except Exception:
        return []


def run_for_tenant(tenant_id: str) -> dict:
    """Lance l'audit Opus pour un tenant. Retourne le rapport JSON."""
    rules = _load_rules_for_audit(tenant_id)
    if not rules:
        return {"status": "no_rules", "tenant_id": tenant_id}

    rules_text = "\n".join([
        f"[id:{r['id']}][{r['category']}][conf:{r['confidence']:.2f}] {r['rule']}"
        for r in rules
    ])

    prompt = f"""Tu es l'auditeur de cohérence des règles de Raya pour le tenant '{tenant_id}'.
Voici les {len(rules)} règles actives :

{rules_text}

Analyse et retourne en JSON strict (sans backticks) :
{{
  "contradictions": [
    {{"rule_ids": [id1, id2], "description": "Ces règles se contredisent car..."}}
  ],
  "redondances": [
    {{"rule_ids": [id1, id2], "description": "Ces règles disent la même chose..."}}
  ],
  "obsoletes": [
    {{"rule_id": id, "description": "Cette règle semble obsolète car..."}}
  ],
  "suggestions": ["Suggestion d'amélioration générale..."],
  "resume": "Résumé global en 2-3 phrases."
}}

Si aucune anomalie dans une catégorie, renvoie [].
Ces suggestions sont examinées par un humain avant toute action."""

    try:
        from app.llm_client import llm_complete, log_llm_usage
        import re
        result = llm_complete(
            messages=[{"role": "user", "content": prompt}],
            model_tier="deep",
            max_tokens=1500,
        )
        log_llm_usage(result, username="system", tenant_id=tenant_id,
                      purpose="opus_weekly_audit")
        raw = re.sub(r'^```(?:json)?\s*', '', result["text"].strip(), flags=re.MULTILINE)
        raw = re.sub(r'\s*```$', '', raw, flags=re.MULTILINE).strip()
        report = json.loads(raw)
    except Exception as e:
        print(f"[OpusAudit] Erreur Opus pour {tenant_id} : {e}")
        report = {
            "contradictions": [], "redondances": [], "obsoletes": [],
            "suggestions": [], "resume": f"Erreur audit : {e}"
        }

    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute(
            "INSERT INTO opus_audit_reports (tenant_id, rules_count, report_json) VALUES (%s, %s, %s)",
            (tenant_id, len(rules), json.dumps(report))
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[OpusAudit] Erreur sauvegarde rapport {tenant_id} : {e}")

    n_issues = (len(report.get("contradictions", [])) +
                len(report.get("redondances", [])) +
                len(report.get("obsoletes", [])))
    print(f"[Scheduler] opus_audit {tenant_id} : {len(rules)} règles, {n_issues} problème(s)")
    return {"status": "ok", "tenant_id": tenant_id,
            "rules_audited": len(rules), "issues": n_issues, "report": report}


def run_all_tenants() -> list:
    """Lance l'audit sur tous les tenants actifs."""
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("SELECT id FROM tenants ORDER BY id")
        tenant_ids = [r[0] for r in c.fetchall()]
        conn.close()
    except Exception:
        tenant_ids = ["couffrant_solar"]
    return [run_for_tenant(tid) for tid in tenant_ids]


def get_latest_report(tenant_id: str) -> dict | None:
    """Retourne le dernier rapport d'audit pour un tenant."""
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            SELECT report_json, run_at, rules_count FROM opus_audit_reports
            WHERE tenant_id = %s ORDER BY run_at DESC LIMIT 1
        """, (tenant_id,))
        row = c.fetchone()
        conn.close()
        if not row:
            return None
        return {"report": row[0], "run_at": str(row[1]), "rules_count": row[2]}
    except Exception:
        return None
