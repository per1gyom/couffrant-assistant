"""
Blocs de contexte injectés dans le prompt système de Raya.
Chaque fonction retourne une string (vide en cas d'erreur).
Extrait de aria_context.py — REFACTOR-3.
"""
import os
from datetime import datetime, timezone
import app.cache as cache
from app.routes.prompt_blocks_extra import build_team_block, build_topics_block, build_web_info, build_ton_block  # noqa


def build_maturity_block(username: str, display_name: str) -> tuple:
    """5G-3 : comportement adaptatif selon la maturite. Retourne (maturity_block, adaptive)."""
    cache_key = f"maturity:{username}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached
    maturity_block = ""
    adaptive = {}
    try:
        from app.maturity import get_adaptive_params
        adaptive = get_adaptive_params(username)
        phase = adaptive["phase"]
        score = adaptive["score"]

        if phase == "discovery":
            maturity_block = f"""

=== PHASE RELATIONNELLE : DECOUVERTE (score {score}/100) ===
Tu decouvres {display_name}. Comportement attendu :
- Confirme tes apprentissages : "j'ai l'impression que tu preferes X, c'est bien ca ?"
- Pose des questions pour mieux comprendre son fonctionnement
- Apprends BEAUCOUP (genere des LEARN frequemment)
- Ne propose PAS d'automatisations, tu n'as pas assez de recul
- Sois attentive et curieuse, montre que tu ecoutes"""
        elif phase == "consolidation":
            maturity_block = f"""

=== PHASE RELATIONNELLE : CONSOLIDATION (score {score}/100) ===
Tu connais bien {display_name}. Comportement attendu :
- Confirme tes apprentissages seulement sur les NOUVEAUX sujets
- Propose des raccourcis : "la derniere fois tu as fait X, tu veux que je relance ?"
- Apprends de facon moderee et qualitative
- Commence a suggerer ponctuellement : "je pourrais surveiller X pour toi"
- Sois efficace, moins de questions, plus d'action"""
        elif phase == "maturity":
            maturity_block = f"""

=== PHASE RELATIONNELLE : MATURITE (score {score}/100) ===
Tu connais {display_name} en profondeur. Comportement attendu :
- Agis de facon autonome dans les limites connues
- Propose des automatisations : "tu fais X chaque semaine, je peux le faire pour toi"
- N'apprends que sur le NOUVEAU (pas de LEARN redondant)
- Confirme UNIQUEMENT sur les sujets inedits ou les actions a haut risque
- Sois proactive : anticipe les besoins avant qu'il les exprime"""
    except Exception:
        pass
    result = (maturity_block, adaptive)
    cache.set(cache_key, result, ttl=120)   # 2 min — phase change lentement
    return result


def build_patterns_block(username: str, adaptive: dict, maturity_block: str,
                         tenant_id: str = None) -> str:
    """5G-5 : injection des patterns comportementaux (consolidation + maturity)."""
    cache_key = f"patterns:{username}:{tenant_id or 'notenant'}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached
    patterns_block = ""
    try:
        if maturity_block:
            from app.database import get_pg_conn as _pg
            _conn = None
            pattern_rows = []
            try:
                _conn = _pg()
                _c = _conn.cursor()
                _c.execute("""
                    SELECT pattern_type, description, confidence, occurrences
                    FROM aria_patterns
                    WHERE username = %s
                      AND (tenant_id = %s OR tenant_id IS NULL)
                      AND active = true AND confidence >= 0.4
                    ORDER BY confidence DESC, occurrences DESC
                    LIMIT 8
                """, (username, tenant_id))
                pattern_rows = _c.fetchall()
            finally:
                if _conn:
                    _conn.close()
            if pattern_rows:
                lines = [f"  [{r[0]}] {r[1]} (confiance: {r[2]:.0%}, vu {r[3]}x)"
                         for r in pattern_rows]
                patterns_block = (
                    "\n\n=== PATTERNS DETECTES ===\n"
                    "Comportements recurrents que tu as observes :\n"
                    + "\n".join(lines)
                )
                if adaptive.get("phase") == "maturity":
                    patterns_block += (
                        "\nUtilise ces patterns pour ANTICIPER les besoins. "
                        "Propose des automatisations concretes basees sur ces habitudes."
                    )
    except Exception:
        pass
    cache.set(cache_key, patterns_block, ttl=120)
    return patterns_block


def build_narrative_block(query: str, username: str, tenant_id: str) -> str:
    """7-NAR : memoire narrative des dossiers."""
    narrative_block = ""
    try:
        from app.narrative import search_narratives
        narratives = search_narratives(query, username, tenant_id=tenant_id, limit=3)
        if narratives:
            lines = []
            for n in narratives:
                lines.append(f"  [{n['entity_type']}:{n['entity_key']}] {n['narrative'][:300]}")
                if n.get("key_facts"):
                    for fact in n["key_facts"][-3:]:
                        lines.append(f"    \u2022 {fact.get('date', '?')} : {fact.get('fact', '')[:100]}")
            narrative_block = (
                "\n\n=== DOSSIERS EN CONTEXTE ===\n"
                + "\n".join(lines)
            )
    except Exception:
        pass
    return narrative_block


def build_alerts_block(username: str) -> str:
    """5E-4c : alertes proactives."""
    alerts_block = ""
    try:
        from app.proactive_alerts import get_active_alerts, mark_seen
        alerts = get_active_alerts(username, limit=5)
        if alerts:
            lines = []
            for a in alerts:
                icon = {"critical": "\U0001f534", "high": "\U0001f7e0", "normal": "\U0001f7e1", "low": "\u26aa"}.get(a["priority"], "\U0001f7e1")
                lines.append(f"  {icon} [{a['alert_type']}] {a['title']}")
                if a.get("body"):
                    lines.append(f"     {a['body'][:150]}")
            alerts_block = (
                "\n\n=== ALERTES PROACTIVES ===\n"
                "Tu as des alertes a mentionner a l'utilisateur :\n"
                + "\n".join(lines)
                + "\nMENTIONNE ces alertes naturellement dans ta reponse. "
                "Ne les ignore pas. Si l'utilisateur parle d'autre chose, "
                "mentionne-les en fin de message : 'Au fait, j'ai remarque que...'"
            )
            mark_seen([a["id"] for a in alerts], username)
    except Exception:
        pass
    return alerts_block


def build_report_block(username: str) -> str:
    """7-6D : rapport du jour disponible."""
    cache_key = f"report:{username}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached
    report_block = ""
    try:
        from app.routes.actions.report_actions import get_today_report
        report = get_today_report(username)
        if report and not report["delivered"]:
            report_block = (
                "\n\n=== RAPPORT DU JOUR (pr\u00eat, non livr\u00e9) ===\n"
                "Un rapport matinal est disponible pour l'utilisateur.\n"
                "Si l'utilisateur demande son rapport, lis-le ou envoie-le selon sa pr\u00e9f\u00e9rence.\n"
                f"Contenu du rapport :\n{report['content'][:1000]}\n"
                "Apr\u00e8s livraison, le rapport sera marqu\u00e9 comme lu."
            )
        elif report and report["delivered"]:
            report_block = (
                "\n\n=== RAPPORT DU JOUR (d\u00e9j\u00e0 livr\u00e9) ===\n"
                f"Le rapport a \u00e9t\u00e9 livr\u00e9 via {report['delivered_via']}.\n"
                "L'utilisateur peut le redemander s'il veut."
            )
    except Exception:
        pass
    cache.set(cache_key, report_block, ttl=300)   # 5 min
    return report_block

