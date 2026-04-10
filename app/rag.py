"""
RAG (Retrieval-Augmented Generation) pour Raya — Phase 3a.

Phase 3b : retrieve_rules retourne maintenant {text, ids} pour que
raya.py puisse stocker les rule_ids dans aria_response_metadata
et les utiliser pour le feedback 👍👎.
"""
from app.embedding import search_similar, is_available
from app.database import get_pg_conn

RAG_RULES_LIMIT    = 10
RAG_INSIGHTS_LIMIT = 6
RAG_MAILS_LIMIT    = 5
RAG_CONV_LIMIT     = 4


def retrieve_rules(query: str, username: str, tenant_id: str = None,
                   limit: int = RAG_RULES_LIMIT) -> dict:
    """
    Retourne {text: str, ids: list[int]} — règles les plus pertinentes.
    Fallback (pas d'embedding) : text = injection en bloc, ids = [].
    """
    if not is_available():
        from app.memory_rules import get_aria_rules
        return {"text": get_aria_rules(username, tenant_id=tenant_id), "ids": []}

    rows = search_similar(
        table="aria_rules",
        username=username,
        query_text=query,
        limit=limit,
        tenant_id=tenant_id,
        extra_filter="active = true AND category != 'memoire'",
    )
    if not rows:
        from app.memory_rules import get_aria_rules
        return {"text": get_aria_rules(username, tenant_id=tenant_id), "ids": []}

    lines = [f"[id:{r['id']}][{r['category']}] {r['rule']}" for r in rows]
    return {
        "text": "\n".join(lines),
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
    """Retourne les mails sémantiquement proches. Fallback : liste vide."""
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
    """Retourne les échanges passés pertinents. Fallback : chaîne vide."""
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
    lines = [
        f"Q: {r.get('user_input', '')[:150]}\nR: {r.get('aria_response', '')[:200]}"
        for r in rows
    ]
    return "\n---\n".join(lines)


def retrieve_context(
    query: str,
    username: str,
    tenant_id: str = None,
) -> dict:
    """
    Point d'entrée principal.

    Retourne :
        rules_text     : str  — règles pertinentes pour le prompt
        rule_ids       : list — IDs des règles injectées (pour feedback)
        insights_text  : str  — insights pertinents
        conv_text      : str  — conversations passées pertinentes
        relevant_mails : list — mails pertinents (bruts)
        via_rag        : bool — True si embedding actif
    """
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
