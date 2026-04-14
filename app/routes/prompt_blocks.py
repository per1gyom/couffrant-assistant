"""
Blocs de contexte injectés dans le prompt système de Raya.
Chaque fonction retourne une string (vide en cas d'erreur).
Extrait de aria_context.py — REFACTOR-3.
"""
import os
from datetime import datetime, timezone


def build_maturity_block(username: str, display_name: str) -> tuple:
    """5G-3 : comportement adaptatif selon la maturite. Retourne (maturity_block, adaptive)."""
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
    return maturity_block, adaptive


def build_patterns_block(username: str, adaptive: dict, maturity_block: str) -> str:
    """5G-5 : injection des patterns comportementaux (consolidation + maturity)."""
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
                    WHERE username = %s AND active = true AND confidence >= 0.4
                    ORDER BY confidence DESC, occurrences DESC
                    LIMIT 8
                """, (username,))
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
    return report_block


def build_team_block(username: str, tenant_id: str) -> str:
    """8-COLLAB : evenements non vus de l'equipe du tenant."""
    team_block = ""
    try:
        from app.tenant_events import get_unseen_events, mark_seen_batch
        unseen = get_unseen_events(username, tenant_id, limit=5)
        if unseen:
            now = datetime.now(timezone.utc)
            lines = []
            for ev in unseen:
                created = ev["created_at"]
                try:
                    if hasattr(created, "replace"):
                        if created.tzinfo is None:
                            created = created.replace(tzinfo=timezone.utc)
                        diff_min = int((now - created).total_seconds() / 60)
                        if diff_min < 60:
                            when = f"il y a {diff_min} min"
                        elif diff_min < 1440:
                            when = f"il y a {diff_min // 60}h"
                        else:
                            when = f"il y a {diff_min // 1440}j"
                    else:
                        when = str(created)[:10]
                except Exception:
                    when = "recemment"
                lines.append(
                    f"  [{ev['source_username'].capitalize()}] {ev['title']} ({when})"
                )
                if ev.get("body"):
                    lines.append(f"    \u2192 {ev['body'][:120]}")
            team_block = (
                "\n\n=== ACTIVITE DE L'EQUIPE (non vu) ===\n"
                + "\n".join(lines)
                + "\nMENTIONNE ces activites naturellement si elles sont pertinentes pour "
                  "la question de l'utilisateur. Utilise-les comme contexte pour enrichir "
                  "tes reponses sur les dossiers en cours. Tu peux aussi en informer "
                  "l'utilisateur spontanement : 'Au fait, Pierre a termine...'"
            )
            mark_seen_batch([ev["id"] for ev in unseen], username)
    except Exception:
        pass
    return team_block


def build_topics_block(username: str) -> str:
    """TOPICS : injecter les sujets actifs de l'utilisateur."""
    topics_block = ""
    try:
        from app.database import get_pg_conn
        _conn_t = get_pg_conn()
        _c_t = _conn_t.cursor()
        _c_t.execute("""
            SELECT title, status FROM user_topics
            WHERE username = %s AND status != 'archived'
            ORDER BY updated_at DESC LIMIT 10
        """, (username,))
        _topic_rows = _c_t.fetchall()
        _conn_t.close()
        if _topic_rows:
            _lines = [f"  - {r[0]} ({r[1]})" for r in _topic_rows]
            topics_block = (
                "\n\n=== SUJETS DE L'UTILISATEUR ===\n"
                + "\n".join(_lines)
                + "\nQuand l'utilisateur parle d'un sujet ci-dessus, utilise-le comme contexte."
                + "\nPour creer un nouveau sujet : [ACTION:CREATE_TOPIC:titre du sujet]"
            )
    except Exception:
        pass
    return topics_block


def build_web_info() -> str:
    """WEB-SEARCH : informe Raya qu'elle a acces a internet."""
    web_info = ""
    try:
        web_enabled = os.getenv("RAYA_WEB_SEARCH_ENABLED", "true").lower() == "true"
        if web_enabled:
            web_info = (
                "\n\n=== ACCES INTERNET ===\n"
                "Tu as acces a internet via la recherche web. "
                "Si l'utilisateur te pose une question d'actualite, te demande de verifier "
                "un site web, de chercher un prix, une meteo, une info recente, "
                "ou toute question dont la reponse necessite des donnees a jour, "
                "tu peux faire une recherche web. "
                "Cite tes sources quand tu utilises des informations trouvees en ligne."
            )
    except Exception:
        pass
    return web_info


def build_ton_block(hot_summary: str, display_name: str) -> str:
    """8-TON : bloc adaptatif de ton selon les preferences de l'utilisateur."""
    if hot_summary and "TON ET COMMUNICATION" in hot_summary.upper():
        return (
            "\n\nTON ET COMMUNICATION (adapte obligatoirement) :\n"
            "Ton hot_summary contient une section \"TON ET COMMUNICATION\" — applique-la "
            "scrupuleusement a chaque reponse. C'est une preference connue de l'utilisateur, "
            "pas une suggestion."
        )
    return (
        "\n\nTON ET COMMUNICATION (observation en cours) :\n"
        f"Tu ne connais pas encore les preferences de ton de {display_name}. "
        "Observe : s'il ecrit court, reponds court. S'il pose des questions detaillees, "
        "developpe. S'il est informel, sois decontractee. S'il est formel, reste professionnelle. "
        "Des qu'il exprime une preference explicite (\"sois plus concis\", \"je prefere les details\", "
        "\"parle-moi comme un collegue\"), genere [ACTION:LEARN:ton|sa_preference]."
    )
