"""
Module de routage Raya — Phase 3a + 3b.

Centralise tous les micro-appels Haiku de classification :
  - route_query_tier()      : SIMPLE → smart (Sonnet) / COMPLEXE → deep (Opus)
  - route_mail_action()     : IGNORER / STOCKER / ANALYSER (pour webhook)
  - detect_session_theme()  : détecte si les échanges portent sur un sujet cohérent (B8)

Garde-fou économique :
  Le nombre d'appels Opus par user par jour est limité (configurable via
  règle mémoire opus_daily_limit:N). Par défaut : 20 appels/jour.
  Au-delà du quota → fallback Sonnet automatiquement.

Tous les futurs micro-appels de classification Haiku doivent passer par ce module.
Pas de duplication d'appels Haiku ailleurs dans le code.
"""
from app.llm_client import llm_complete

# Prompt système partagé pour tous les routages — compact et déterministe
_ROUTER_SYSTEM = (
    "Tu es un classificateur binaire. "
    "Réponds UNIQUEMENT par le mot demandé, rien d'autre."
)


def route_query_tier(
    query: str,
    username: str,
    tenant_id: str,
    history_len: int = 0,
) -> str:
    """
    Classifie la question en 'smart' (Sonnet) ou 'deep' (Opus).

    Heuristiques avant le micro-appel Haiku :
      - Question courte ou salutation  → smart directement (pas de Haiku)
      - Quota Opus dépassé             → smart (garde-fou économique)

    Sinon : micro-appel Haiku (max_tokens=3) retourne SIMPLE ou COMPLEXE.
    """
    query = (query or "").strip()

    # 1. Question vide ou très courte → smart
    if len(query) < 20:
        return "smart"

    # 2. Salutations et commandes simples → smart
    _SIMPLE_PATTERNS = (
        "bonjour", "bonsoir", "salut", "merci", "ok", "d'accord",
        "oui", "non", "vas-y", "confirme", "annule", "stop",
    )
    query_lower = query.lower()
    if any(query_lower.startswith(p) for p in _SIMPLE_PATTERNS) and len(query) < 60:
        return "smart"

    # 3. Garde-fou économique : vérifier le quota Opus du jour
    if _opus_quota_exceeded(username, tenant_id):
        return "smart"

    # 4. Micro-appel Haiku pour la classification
    try:
        result = llm_complete(
            messages=[{"role": "user", "content": (
                f"Question : {query[:400]}\n\n"
                f"Cette question nécessite-t-elle une réflexion approfondie, "
                f"une analyse complexe ou une synthèse ? "
                f"Réponds SIMPLE ou COMPLEXE."
            )}],
            system=_ROUTER_SYSTEM,
            model_tier="fast",
            max_tokens=3,
        )
        verdict = result["text"].strip().upper()
        return "deep" if "COMPLEXE" in verdict else "smart"
    except Exception:
        return "smart"


def detect_session_theme(history: list) -> str | None:
    """
    Détecte si les derniers échanges portent sur un sujet cohérent (B8).

    Si oui → retourne le thème en 3-5 mots (ex: "chantier Dupont raccordement").
    Sinon  → retourne None.

    Le thème est ensuite utilisé par build_system_prompt pour enrichir le RAG
    avec tout ce qui concerne ce sujet, pas seulement la dernière question.

    Args:
        history : liste de dicts {user_input, aria_response} (ordre chronologique)

    Returns:
        str  : sujet cohérent détecté (3-5 mots max)
        None : échanges disparates ou trop peu d'échanges
    """
    # Pas assez d'échanges pour détecter un thème
    if len(history) < 3:
        return None

    # Prend les 5 derniers échanges max pour le contexte
    recent = history[-5:]
    exchanges = "\n".join([
        f"Q: {h.get('user_input', '')[:100]}\nR: {h.get('aria_response', '')[:60]}"
        for h in recent
    ])

    try:
        result = llm_complete(
            messages=[{"role": "user", "content": (
                f"Voici les derniers échanges :\n{exchanges}\n\n"
                f"Ces échanges portent-ils TOUS sur un sujet cohérent et précis ?\n"
                f"Si oui : nomme ce sujet en 3-5 mots maximum (ex: 'chantier Dupont raccordement').\n"
                f"Si non (sujets variés ou conversation générale) : réponds AUCUN"
            )}],
            system=_ROUTER_SYSTEM,
            model_tier="fast",
            max_tokens=12,
        )
        verdict = result["text"].strip()
        if not verdict or "AUCUN" in verdict.upper() or len(verdict) < 4:
            return None
        # Nettoie le résultat (supprime ponctuation parasite)
        theme = verdict.strip('."\'')
        return theme[:60] if len(theme) > 3 else None
    except Exception:
        return None


def route_mail_action(sender: str, subject: str, preview: str) -> str:
    """
    Triage mail via Haiku : IGNORER / STOCKER_SIMPLE / ANALYSER.
    Réservé pour la Phase 3b — pas encore branché dans webhook.py.
    """
    try:
        result = llm_complete(
            messages=[{"role": "user", "content": (
                f"Mail reçu :\nDe : {sender}\nSujet : {subject}\n"
                f"Aperçu : {preview[:300]}\n\n"
                f"Catégorise ce mail : IGNORER (spam/notification auto) | "
                f"STOCKER_SIMPLE (info utile mais pas d'action) | "
                f"ANALYSER (nécessite attention/action). "
                f"Réponds par un seul mot."
            )}],
            system=_ROUTER_SYSTEM,
            model_tier="fast",
            max_tokens=5,
        )
        verdict = result["text"].strip().upper()
        if "IGNORER" in verdict:
            return "IGNORER"
        if "STOCKER" in verdict:
            return "STOCKER_SIMPLE"
        return "ANALYSER"
    except Exception:
        return "ANALYSER"


# ─── GARDE-FOU ÉCONOMIQUE ───

def _opus_daily_limit(username: str) -> int:
    try:
        from app.rule_engine import get_memoire_param
        return get_memoire_param(username, "opus_daily_limit", 20)
    except Exception:
        return 20


def _opus_calls_today(username: str, tenant_id: str) -> int:
    try:
        from app.database import get_pg_conn
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            SELECT COUNT(*) FROM llm_usage
            WHERE username = %s
              AND tenant_id = %s
              AND model ILIKE '%%opus%%'
              AND purpose = 'raya_main_conversation'
              AND created_at > NOW() - INTERVAL '1 day'
        """, (username, tenant_id))
        count = c.fetchone()[0]
        conn.close()
        return count
    except Exception:
        return 0


def _opus_quota_exceeded(username: str, tenant_id: str) -> bool:
    limit = _opus_daily_limit(username)
    calls = _opus_calls_today(username, tenant_id)
    if calls >= limit:
        print(f"[Router] Quota Opus atteint pour {username} ({calls}/{limit}) — fallback Sonnet")
        return True
    return False


def get_routing_stats(username: str, tenant_id: str) -> dict:
    """Stats de routage du jour pour /admin/costs (Phase 3b)."""
    try:
        from app.database import get_pg_conn
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            SELECT model, COUNT(*) as calls,
                   SUM(input_tokens + output_tokens) as total_tokens
            FROM llm_usage
            WHERE username = %s
              AND tenant_id = %s
              AND purpose = 'raya_main_conversation'
              AND created_at > NOW() - INTERVAL '1 day'
            GROUP BY model
        """, (username, tenant_id))
        rows = c.fetchall()
        conn.close()
        return {
            "quota_limit":     _opus_daily_limit(username),
            "opus_calls_today": _opus_calls_today(username, tenant_id),
            "by_model": [{"model": r[0], "calls": r[1], "tokens": r[2]} for r in rows],
        }
    except Exception:
        return {}
