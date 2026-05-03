"""
RAG (Retrieval-Augmented Generation) pour Raya.

PERF : L'embedding du query est calculé UNE SEULE FOIS dans retrieve_context()
       et passé via precomputed_vec à chaque sous-fonction — 4x moins d'appels OpenAI.

Phase 3a : injection par similarité sémantique.
Phase 3b : retrieve_rules retourne {text, ids} pour traçabilité feedback.
Phase 4  : filtre confidence >= 0.30 (décroissance B6).
5D-2c    : supporte tenant_ids pour mode multi-tenant.
"""
from app.embedding import search_similar, is_available, embed
from app.database import get_pg_conn

RAG_RULES_LIMIT    = 10
RAG_INSIGHTS_LIMIT = 6
RAG_MAILS_LIMIT    = 5
RAG_CONV_LIMIT     = 4

RAG_THEME_RULES_EXTRA    = 5
RAG_THEME_INSIGHTS_EXTRA = 3
RAG_THEME_MAILS_EXTRA    = 3

RAG_CONFIDENCE_THRESHOLD = 0.30


def retrieve_rules(query: str, username: str, tenant_id: str = None,
                   tenant_ids: list[str] = None, limit: int = RAG_RULES_LIMIT,
                   precomputed_vec: list = None) -> dict:
    """Règles pertinentes — {text, ids}. Exclut confidence < 0.30."""
    conf_filter = f"active = true AND category != 'Mémoire' AND confidence >= {RAG_CONFIDENCE_THRESHOLD}"

    if not is_available():
        try:
            conn = get_pg_conn(); c = conn.cursor()
            if tenant_ids:
                c.execute("""
                    SELECT id, category, rule FROM aria_rules
                    WHERE active=true AND username=%s AND (tenant_id=ANY(%s) OR tenant_id IS NULL)
                    AND category != 'Mémoire' AND confidence>=%s
                    ORDER BY confidence DESC, reinforcements DESC LIMIT 60
                """, (username, tenant_ids, RAG_CONFIDENCE_THRESHOLD))
            elif tenant_id:
                c.execute("""
                    SELECT id, category, rule FROM aria_rules
                    WHERE active=true AND username=%s AND (tenant_id=%s OR tenant_id IS NULL)
                    AND category != 'Mémoire' AND confidence>=%s
                    ORDER BY confidence DESC, reinforcements DESC LIMIT 60
                """, (username, tenant_id, RAG_CONFIDENCE_THRESHOLD))
            else:
                c.execute("""
                    SELECT id, category, rule FROM aria_rules
                    WHERE active=true AND username=%s AND category != 'Mémoire' AND confidence>=%s
                    ORDER BY confidence DESC, reinforcements DESC LIMIT 60
                """, (username, RAG_CONFIDENCE_THRESHOLD))
            rows = c.fetchall(); conn.close()
            if not rows: return {"text": "", "ids": []}
            return {"text": "\n".join([f"[id:{r[0]}][{r[1]}] {r[2]}" for r in rows]),
                    "ids": [r[0] for r in rows]}
        except Exception:
            return {"text": "", "ids": []}

    rows = search_similar(
        table="aria_rules", username=username, query_text=query, limit=limit,
        tenant_id=tenant_id, tenant_ids=tenant_ids, extra_filter=conf_filter,
        precomputed_vec=precomputed_vec,
    )
    if not rows: return {"text": "", "ids": []}
    return {"text": "\n".join([f"[id:{r['id']}][{r['category']}] {r['rule']}" for r in rows]),
            "ids": [r["id"] for r in rows]}


def retrieve_insights(query: str, username: str, tenant_id: str = None,
                      tenant_ids: list[str] = None, limit: int = RAG_INSIGHTS_LIMIT,
                      precomputed_vec: list = None) -> str:
    """Insights pertinents. Fallback : top N par reinforcements."""
    if not is_available():
        from app.memory_synthesis import get_aria_insights
        return get_aria_insights(limit=8, username=username, tenant_id=tenant_id)
    rows = search_similar(
        table="aria_insights", username=username, query_text=query, limit=limit,
        tenant_id=tenant_id, tenant_ids=tenant_ids, precomputed_vec=precomputed_vec,
    )
    if not rows:
        from app.memory_synthesis import get_aria_insights
        return get_aria_insights(limit=8, username=username, tenant_id=tenant_id)
    return "\n".join([f"[{r['topic']}] {r['insight']}" for r in rows])


def retrieve_relevant_mails(query: str, username: str, tenant_id: str = None,
                             tenant_ids: list[str] = None, limit: int = RAG_MAILS_LIMIT,
                             precomputed_vec: list = None) -> list:
    if not is_available(): return []
    return search_similar(
        table="mail_memory", username=username, query_text=query, limit=limit,
        tenant_id=tenant_id, tenant_ids=tenant_ids, precomputed_vec=precomputed_vec,
    ) or []


def retrieve_relevant_conversations(query: str, username: str, tenant_id: str = None,
                                     tenant_ids: list[str] = None, limit: int = RAG_CONV_LIMIT,
                                     precomputed_vec: list = None) -> str:
    if not is_available(): return ""
    rows = search_similar(
        table="aria_memory", username=username, query_text=query, limit=limit,
        tenant_id=tenant_id, tenant_ids=tenant_ids, precomputed_vec=precomputed_vec,
    )
    if not rows: return ""
    return "\n---\n".join([
        f"Q: {r.get('user_input','')[:150]}\nR: {r.get('aria_response','')[:200]}"
        for r in rows
    ])


def retrieve_theme_context(theme: str, username: str, tenant_id: str = None,
                           tenant_ids: list[str] = None) -> dict:
    """Enrichit le contexte avec tout ce qui concerne le thème de session (B8)."""
    if not is_available() or not theme:
        return {"extra_rules": "", "extra_insights": "", "extra_mails": []}
    conf_filter = f"active = true AND category != 'Mémoire' AND confidence >= {RAG_CONFIDENCE_THRESHOLD}"
    theme_vec = embed(theme)
    extra_rules    = search_similar(table="aria_rules",    username=username, query_text=theme,
                                    limit=RAG_THEME_RULES_EXTRA, tenant_id=tenant_id,
                                    tenant_ids=tenant_ids, extra_filter=conf_filter,
                                    precomputed_vec=theme_vec) or []
    extra_insights = search_similar(table="aria_insights", username=username, query_text=theme,
                                    limit=RAG_THEME_INSIGHTS_EXTRA, tenant_id=tenant_id,
                                    tenant_ids=tenant_ids, precomputed_vec=theme_vec) or []
    extra_mails    = search_similar(table="mail_memory",   username=username, query_text=theme,
                                    limit=RAG_THEME_MAILS_EXTRA, tenant_id=tenant_id,
                                    tenant_ids=tenant_ids, precomputed_vec=theme_vec) or []
    return {
        "extra_rules":    "\n".join([f"[id:{r['id']}][{r['category']}] {r['rule']}" for r in extra_rules]),
        "extra_insights": "\n".join([f"[{r['topic']}] {r['insight']}" for r in extra_insights]),
        "extra_mails":    extra_mails,
    }


def retrieve_context(query: str, username: str, tenant_id: str = None,
                     tenant_ids: list[str] = None) -> dict:
    """
    Point d'entrée principal — retourne tout le contexte RAG.
    L'embedding du query est calculé UNE SEULE FOIS et réutilisé par toutes les fonctions.
    """
    via_rag   = is_available()
    query_vec = embed(query) if via_rag else None   # ← un seul appel OpenAI

    rules_result   = retrieve_rules(query, username, tenant_id, tenant_ids=tenant_ids,
                                    precomputed_vec=query_vec)
    insights_text  = retrieve_insights(query, username, tenant_id, tenant_ids=tenant_ids,
                                       precomputed_vec=query_vec)
    conv_text      = retrieve_relevant_conversations(query, username, tenant_id,
                                                     tenant_ids=tenant_ids,
                                                     precomputed_vec=query_vec)
    relevant_mails = retrieve_relevant_mails(query, username, tenant_id,
                                             tenant_ids=tenant_ids, precomputed_vec=query_vec)
    return {
        "rules_text":     rules_result["text"],
        "rule_ids":       rules_result["ids"],
        "insights_text":  insights_text,
        "conv_text":      conv_text,
        "relevant_mails": relevant_mails,
        "via_rag":        via_rag,
    }
