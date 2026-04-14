"""
Memoire : synthese des sessions et resume chaud.
Vectorisation automatique des insights et conversations.

Phase 3a :
  - rebuild_hot_summary    -> model_tier="deep" (Opus)
  - synthesize_session     -> model_tier="deep" (Opus) + prompt enrichi des regles existantes
    Opus compare les nouvelles regles candidates avec celles deja en base
    pour eviter les doublons semantiques.
5G-6 : rebuild_hot_summary adapte selon la phase de maturite.
8-TON : section "Ton et communication" ajoutee au hot_summary.

Signatures canoniques utilisees ici (depuis rule_engine) :
  get_memoire_param(username, param, default, tenant_id=None)
  get_rules_by_category(username, category, tenant_id=None)
"""
import json
import re

from app.database import get_pg_conn
from app.synthesis_engine import rebuild_hot_summary, _vectorize_conversations_batch  # noqa
from app.llm_client import llm_complete, log_llm_usage
from app.rule_engine import get_rules_by_category, get_memoire_param
from app.memory_rules import save_rule

DEFAULT_TENANT = 'couffrant_solar'


def get_hot_summary(username: str = 'guillaume') -> str:
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("SELECT content FROM aria_hot_summary WHERE username = %s", (username,))
        row = c.fetchone()
        return row[0] if row else ""
    finally:
        if conn: conn.close()


def get_aria_insights(limit: int = 8, username: str = 'guillaume',
                      tenant_id: str = None) -> str:
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        if tenant_id:
            c.execute("""
                SELECT topic, insight, reinforcements FROM aria_insights
                WHERE username = %s AND (tenant_id = %s OR tenant_id IS NULL)
                ORDER BY reinforcements DESC, updated_at DESC LIMIT %s
            """, (username, tenant_id, limit))
        else:
            c.execute("""
                SELECT topic, insight, reinforcements FROM aria_insights
                WHERE username = %s
                ORDER BY reinforcements DESC, updated_at DESC LIMIT %s
            """, (username, limit))
        rows = c.fetchall()
        if not rows: return ""
        return "\n".join([f"[{r[0]}] {r[1]}" for r in rows])
    finally:
        if conn: conn.close()


def save_insight(topic: str, insight: str, source: str = "conversation",
                 username: str = None, tenant_id: str = None) -> int:
    if not username:
        raise ValueError("save_insight : username obligatoire")
    if not topic or not insight:
        raise ValueError("save_insight : topic et insight obligatoires")

    topic_clean = topic.strip()
    effective_tenant = tenant_id or DEFAULT_TENANT
    embed_text = f"[{topic_clean}] {insight}"
    vec = _vec_str(_embed(embed_text))

    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            SELECT id FROM aria_insights
            WHERE username = %s AND LOWER(TRIM(topic)) = LOWER(TRIM(%s))
            LIMIT 1
        """, (username, topic_clean))
        existing = c.fetchone()
        if existing:
            if vec:
                c.execute("""
                    UPDATE aria_insights SET insight=%s,
                    reinforcements=reinforcements+1, updated_at=NOW(),
                    embedding=%s::vector WHERE id=%s
                """, (insight, vec, existing[0]))
            else:
                c.execute("""
                    UPDATE aria_insights SET insight=%s,
                    reinforcements=reinforcements+1, updated_at=NOW()
                    WHERE id=%s
                """, (insight, existing[0]))
            conn.commit()
            return existing[0]

        if vec:
            c.execute("""
                INSERT INTO aria_insights (username, tenant_id, topic, insight, source, embedding)
                VALUES (%s, %s, %s, %s, %s, %s::vector) RETURNING id
            """, (username, effective_tenant, topic_clean, insight, source, vec))
        else:
            c.execute("""
                INSERT INTO aria_insights (username, tenant_id, topic, insight, source)
                VALUES (%s, %s, %s, %s, %s) RETURNING id
            """, (username, effective_tenant, topic_clean, insight, source))
        insight_id = c.fetchone()[0]
        conn.commit()
        return insight_id
    finally:
        if conn: conn.close()


def _load_existing_rules_summary(username: str, tenant_id: str) -> str:
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            SELECT category, rule FROM aria_rules
            WHERE active = true AND username = %s
              AND (tenant_id = %s OR tenant_id IS NULL)
              AND category != 'memoire'
            ORDER BY confidence DESC, reinforcements DESC LIMIT 40
        """, (username, tenant_id))
        rows = c.fetchall()
        if not rows: return ""
        return "\n".join([f"[{r[0]}] {r[1]}" for r in rows])
    except Exception:
        return ""
    finally:
        if conn: conn.close()


def synthesize_session(n_conversations: int = 15, username: str = 'guillaume',
                       tenant_id: str = None) -> dict:
    effective_tenant = tenant_id or DEFAULT_TENANT
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            SELECT id, user_input, aria_response, created_at FROM aria_memory
            WHERE username = %s ORDER BY id DESC LIMIT %s
        """, (username, n_conversations))
        conversations = c.fetchall()
        c.execute("SELECT COUNT(*) FROM aria_memory WHERE username = %s", (username,))
        total = c.fetchone()[0]
    finally:
        if conn: conn.close()

    keep_recent = get_memoire_param(username, 'keep_recent', 5)
    if not conversations or total <= keep_recent:
        return {"status": "nothing_to_synthesize", "total": total}

    display_name = username.capitalize()
    conv_text = "\n\n".join([
        f"{display_name}: {r[1][:200]}\nRaya: {r[2][:300]}"
        for r in reversed(conversations)
    ])

    existing_rules = _load_existing_rules_summary(username, effective_tenant)
    existing_rules_section = f"""\nRegles deja en memoire (ne pas dupliquer) :\n{existing_rules}\n""" if existing_rules else ""

    prompt = f"""Tu es Raya, assistante de {display_name}.
Voici {len(conversations)} conversations recentes a synthetiser.
{existing_rules_section}
CONVERSATIONS :
{conv_text}

Synthetise en JSON strict (sans backticks ni markdown) :
{{"summary": "resume operationnel ~150 mots", "rules_learned": ["regle nouvelle ou enrichissante, PAS deja en memoire"], "insights": [{{"topic": "x", "text": "y"}}], "topics": ["sujet principal"]}}

Pour rules_learned : ne propose que des regles NOUVELLES. Prefere la qualite a la quantite."""

    parsed = None
    try:
        result = llm_complete(messages=[{"role": "user", "content": prompt}],
                              model_tier="deep", max_tokens=1200)
        log_llm_usage(result, username=username, tenant_id=effective_tenant, purpose="synthesize_session")
        raw = re.sub(r'^```(?:json)?\s*', '', result["text"].strip(), flags=re.MULTILINE)
        raw = re.sub(r'\s*```$', '', raw, flags=re.MULTILINE).strip()
        parsed = json.loads(raw)
    except Exception as e:
        print(f"[synthesize_session] Erreur Opus: {e} — fallback smart")
        try:
            result = llm_complete(messages=[{"role": "user", "content": prompt}],
                                  model_tier="smart", max_tokens=1200)
            raw = re.sub(r'^```(?:json)?\s*', '', result["text"].strip(), flags=re.MULTILINE)
            raw = re.sub(r'\s*```$', '', raw, flags=re.MULTILINE).strip()
            parsed = json.loads(raw)
        except Exception as e2:
            return {"status": "error", "message": str(e2)}

    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            INSERT INTO aria_session_digests
            (username, conversation_count, summary, rules_learned, topics, session_date)
            VALUES (%s, %s, %s, %s, %s, CURRENT_DATE)
        """, (username, len(conversations), parsed.get("summary", ""),
               json.dumps(parsed.get("rules_learned", []), ensure_ascii=False),
               json.dumps(parsed.get("topics", []), ensure_ascii=False)))
        conn.commit()
    finally:
        if conn: conn.close()

    for rule_text in parsed.get("rules_learned", []):
        if rule_text and len(rule_text) > 10:
            save_rule("auto", rule_text, "synthesis", 0.6, username, tenant_id=effective_tenant)

    for item in parsed.get("insights", []):
        if isinstance(item, dict):
            save_insight(item.get("topic", "general"), item.get("text", str(item)),
                         username=username, tenant_id=effective_tenant)
        elif isinstance(item, str) and len(item) > 10:
            save_insight("general", item, username=username, tenant_id=effective_tenant)

    _vectorize_conversations_batch(conversations, username)

    conn = None
    purged = 0
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            DELETE FROM aria_memory WHERE username = %s AND id NOT IN (
                SELECT id FROM aria_memory WHERE username = %s ORDER BY id DESC LIMIT %s
            )
        """, (username, username, keep_recent))
        purged = c.rowcount
        conn.commit()
    finally:
        if conn: conn.close()

    return {
        "status": "ok",
        "conversations_synthesized": len(conversations),
        "rules_extracted": len(parsed.get("rules_learned", [])),
        "insights_extracted": len(parsed.get("insights", [])),
        "purged": purged,
    }


def purge_old_mails(days: int = None, username: str = 'guillaume') -> int:
    if days is None:
        days = get_memoire_param(username, 'purge_days', 90)
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            DELETE FROM mail_memory
            WHERE username = %s AND created_at < NOW() - (%s || ' days')::INTERVAL
            AND mailbox_source IN ('outlook', 'gmail_perso')
        """, (username, str(days)))
        deleted = c.rowcount
        conn.commit()
        return deleted
    finally:
        if conn: conn.close()
