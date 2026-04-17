"""
Job d'analyse des patterns comportementaux. (5G-4 + 7-WF + 8-CYCLES)
Détecte temporal, relational, thematic, workflow, preference.
Sous-type cyclique calendaire (8-CYCLES).
"""
import json
import re
from app.logging_config import get_logger

logger = get_logger("raya.scheduler")


def _job_pattern_analysis():
    """Détecte les patterns comportementaux — quotidien 04h00."""
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
    """Détecte les patterns récurrents (conversations + mails + activity_log + cycles)."""
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
    mails = [
        {"from": r[0], "subject": r[1][:60], "cat": r[2], "prio": r[3], "date": str(r[4])}
        for r in c.fetchall()
    ]

    activities = []
    try:
        c.execute("""
            SELECT action_type, action_target, action_detail, tenant_id,
                   created_at::text as ts
            FROM activity_log
            WHERE username = %s AND created_at > NOW() - INTERVAL '30 days'
            ORDER BY created_at DESC LIMIT 150
        """, (username,))
        activities = [
            {"type": r[0], "target": r[1][:50] if r[1] else "",
             "detail": r[2][:60] if r[2] else "", "date": r[4]}
            for r in c.fetchall()
        ]
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

    activities_section = (
        f"\nACTIVITÉS (actions via Raya, 30 derniers jours) :\n"
        f"{json.dumps(activities[:80], ensure_ascii=False)}\n"
    ) if activities else ""

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

Détecte les NOUVEAUX comportements récurrents selon ces types :

- temporal : actions récurrentes liées au temps.
  Sous-type CYCLIQUE (calendaire) — cherche activement des cycles :
    * hebdomadaire : "tri mails le lundi matin", "point équipe le vendredi"
    * mensuel : "relances factures en fin de mois (j25-j31)"
    * trimestriel : "clôture comptable fin de trimestre (mars/juin/sept/déc)"
    * saisonnier : "ralentissement chantiers en août", "reprise budgets en janvier"
  Pour les cycliques, précise dans "evidence" : "cycle:mensuel|période:fin_mois"

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

    result = llm_complete(
        messages=[{"role": "user", "content": prompt}],
        model_tier="deep", max_tokens=1200,
    )
    log_llm_usage(result, username=username, tenant_id=tenant_id, purpose="pattern_analysis")

    raw = re.sub(r'^```(?:json)?\s*', '', result["text"].strip(), flags=re.MULTILINE)
    raw = re.sub(r'\s*```$', '', raw, flags=re.MULTILINE).strip()
    parsed = json.loads(raw)

    conn = get_pg_conn()
    c = conn.cursor()
    inserted = 0
    for p in parsed.get("new_patterns", []):
        c.execute("""
            INSERT INTO aria_patterns
            (username, tenant_id, pattern_type, description, evidence, confidence)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (username, tenant_id, p["type"], p["description"],
               p.get("evidence", ""), p.get("confidence", 0.5)))
        inserted += 1
    conn.commit()
    conn.close()
    logger.info(f"[Patterns] {username} : {inserted} nouveau(x) pattern(s)")
