"""
Sauvegarde des insights et chargement des regles.
Extrait de memory_synthesis.py.
"""
from app.database import get_pg_conn
from app.logging_config import get_logger
logger=get_logger("raya.memory")


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
            WHERE username = %s
              AND (tenant_id = %s OR tenant_id IS NULL)
              AND LOWER(TRIM(topic)) = LOWER(TRIM(%s))
            LIMIT 1
        """, (username, effective_tenant, topic_clean))
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


