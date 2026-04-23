"""
Blocs supplementaires du prompt Raya (team, topics, web, ton).
Extrait de prompt_blocks.py -- SPLIT-EXTRA.
"""
import os
from datetime import datetime, timezone


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


def build_topics_block(username: str, tenant_id: str = None) -> str:
    """TOPICS : injecter les sujets actifs de l'utilisateur."""
    topics_block = ""
    try:
        from app.database import get_pg_conn
        _conn_t = get_pg_conn()
        _c_t = _conn_t.cursor()
        _c_t.execute("""
            SELECT title, status FROM user_topics
            WHERE username = %s
              AND (tenant_id = %s OR tenant_id IS NULL)
              AND status != 'archived'
            ORDER BY updated_at DESC LIMIT 10
        """, (username, tenant_id))
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

