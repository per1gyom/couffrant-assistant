"""
RAG (Retrieval-Augmented Generation) pour Raya — Phase 3a + 3b + 4.

Phase 3a : injection par similarité sémantique au lieu d'injection en bloc.
Phase 3b : retrieve_rules retourne {text, ids} pour traçabilité feedback.
           retrieve_theme_context enrichit le contexte si session thématique (B8).
Phase 4  : filtre confidence >= 0.30 dans retrieve_rules (décroissance B6).
           Les règles sous le seuil sont masquées du RAG mais restent en base.
"""
from app.embedding import search_similar, is_available
from app.database import get_pg_conn

RAG_RULES_LIMIT    = 10
RAG_INSIGHTS_LIMIT = 6
RAG_MAILS_LIMIT    = 5
RAG_CONV_LIMIT     = 4

RAG_THEME_RULES_EXTRA    = 5
RAG_THEME_INSIGHTS_EXTRA = 3
RAG_THEME_MAILS_EXTRA    = 3

# Seuil de confiance minimum pour l'injection RAG (lié à la décroissance B6)
RAG_CONFIDENCE_THRESHOLD = 0.30


def retrieve_rules(query: str, username: str, tenant_id: str = None,
                   limit: int = RAG_RULES_LIMIT) -> dict:
    """
    Retourne {text: str, ids: list[int]} — règles les plus pertinentes.
    Phase 4 : exclut les règles avec confidence < 0.30 (décroissance B6).
    """
    conf_filter = f"active = true AND category != 'memoire' AND confidence >= {RAG_CONFIDENCE_THRESHOLD}"

    if not is_available():
        # Fallback injection en bloc avec filtre confidence
        try:
            conn = get_pg_conn()
            c = conn.cursor()
            if tenant_id:
                c.execute("""
                    SELECT id, category, rule FROM aria_rules
                    WHERE active = true AND username = %s
                      AND (tenant_id = %s OR tenant_id IS NULL)
                      AND category != 'memoire' AND confidence >= %s
                    ORDER BY confidence DESC, reinforcements DESC LIMIT 60
                """, (username, tenant_id, RAG_CONFIDENCE_THRESHOLD))
            else:
                c.execute("""
                    SELECT id, category, rule FROM aria_rules
                    WHERE active = true AND username = %s
                      AND category != 'memoire' AND confidence >= %s
                    ORDER BY confidence DESC, reinforcements DESC LIMIT 60
                """, (username, RAG_CONFIDENCE_THRESHOLD))
            rows = c.fetchall()
            conn.close()
            if not rows:
                return {"text": "", "ids": []}
            return {
                "text": "\n".join([f"[id:{r[0]}][{r[1]}] {r[2]}" for r in rows]),
                "ids":  [r[0] for r in rows],
            }
        except Exception:
            return {"text": "", "ids": []}

    rows = search_similar(
        table="aria_rules",
        username=username,
        query_text=query,
        limit=limit,
        tenant_id=tenant_id,
        extra_filter=conf_filter,
    )
    if not rows:
        return {"text": "", "ids": []}

    return {
        "text": "\n".join([f"[id:{r['id']}][{r['category']}] {r['rule']}" for r in rows]),
        "ids":  [r["id"] for r in rows],
    }


def retrieve_insights(query: str, username: str, tenant_id: str = None,
                      limit: int = RAG_INSIGHTS_LIMIT) -> str:
    """Retourne les insights les plus pertinents. Fallback : top N par reinforcements."""
    if not is_available():
        from app.memory_synthesis import get_aria_insights
        return get_aria_insights(limit=8, username=username, tenant_id=tenant_id)

    rows = search_similar(
        table="aria_insights",
        username=username,
        query_text=query,
        limit=limit,
        tenant_id=tenant_id,
    )
    if not rows:
        from app.memory_synthesis import get_aria_insights
        return get_aria_insights(limit=8, username=username, tenant_id=tenant_id)

    return "\n".join([f"[{r['topic']}] {r['insight']}" for r in rows])


def retrieve_relevant_mails(query: str, username: str, tenant_id: str = None,
                             limit: int = RAG_MAILS_LIMIT) -> list:
    if not is_available():
        return []
    return search_similar(
        table="mail_memory",
        username=username,
        query_text=query,
        limit=limit,
        tenant_id=tenant_id,
    )


def retrieve_relevant_conversations(query: str, username: str,
                                     tenant_id: str = None,
                                     limit: int = RAG_CONV_LIMIT) -> str:
    if not is_available():
        return ""
    rows = search_similar(
        table="aria_memory",
        username=username,
        query_text=query,
        limit=limit,
        tenant_id=tenant_id,
    )
    if not rows:
        return ""
    return "\n---\n".join([
        f"Q: {r.get('user_input', '')[:150]}\nR: {r.get('aria_response', '')[:200]}"
        for r in rows
    ])


def retrieve_theme_context(theme: str, username: str, tenant_id: str = None) -> dict:
    """Enrichit le contexte avec tout ce qui concerne le thème de session (B8)."""
    if not is_available() or not theme:
        return {"extra_rules": "", "extra_insights": "", "extra_mails": []}

    conf_filter = f"active = true AND category != 'memoire' AND confidence >= {RAG_CONFIDENCE_THRESHOLD}"

    extra_rules_rows = search_similar(
        table="aria_rules", username=username, query_text=theme,
        limit=RAG_THEME_RULES_EXTRA, tenant_id=tenant_id, extra_filter=conf_filter,
    )
    extra_insights_rows = search_similar(
        table="aria_insights", username=username, query_text=theme,
        limit=RAG_THEME_INSIGHTS_EXTRA, tenant_id=tenant_id,
    )
    extra_mails = search_similar(
        table="mail_memory", username=username, query_text=theme,
        limit=RAG_THEME_MAILS_EXTRA, tenant_id=tenant_id,
    ) or []

    return {
        "extra_rules":    "\n".join([f"[id:{r['id']}][{r['category']}] {r['rule']}" for r in (extra_rules_rows or [])]),
        "extra_insights": "\n".join([f"[{r['topic']}] {r['insight']}" for r in (extra_insights_rows or [])]),
        "extra_mails":    extra_mails,
    }


def retrieve_context(query: str, username: str, tenant_id: str = None) -> dict:
    """Point d'entrée principal — retourne tout le contexte RAG."""
    via_rag = is_available()
    rules_result   = retrieve_rules(query, username, tenant_id)
    insights_text  = retrieve_insights(query, username, tenant_id)
    conv_text      = retrieve_relevant_conversations(query, username, tenant_id)
    relevant_mails = retrieve_relevant_mails(query, username, tenant_id)
    return {
        "rules_text":     rules_result["text"],
        "rule_ids":       rules_result["ids"],
        "insights_text":  insights_text,
        "conv_text":      conv_text,
        "relevant_mails": relevant_mails,
        "via_rag":        via_rag,
    }
