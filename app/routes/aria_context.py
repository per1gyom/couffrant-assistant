"""
Construction du contexte pour Raya.
Coœur du prompt : build_system_prompt() + build_actions_prompt().

Les loaders de données sont dans aria_loaders.py.
Les blocs de prompt sont dans prompt_blocks.py.
Les actions disponibles sont dans prompt_actions.py.
Les garde-fous sont dans prompt_guardrails.py.

REFACTOR-3 : blocs extraits dans prompt_blocks.py.
"""
import json
from datetime import datetime

from app.database import get_pg_conn
from app.rule_engine import get_contacts_keywords
from app.memory_loader import (
    get_hot_summary, get_contact_card, get_style_examples,
)
from app.capabilities import get_user_capabilities_prompt
import app.cache as cache
from app.routes.prompt_guardrails import GUARDRAILS
from app.routes.prompt_actions import build_actions_prompt
from app.routes.prompt_blocks import (
    build_maturity_block, build_patterns_block, build_narrative_block,
    build_alerts_block, build_report_block, build_team_block,
    build_topics_block, build_web_info, build_ton_block,
)

# ─── Loaders réexportés pour compatibilité avec raya.py ───
from app.routes.aria_loaders import (
    load_user_tools, load_db_context, load_live_mails,
    load_agenda, load_teams_context, load_mail_filter_summary,
)

__all__ = [
    "load_user_tools", "load_db_context", "load_live_mails",
    "load_agenda", "load_teams_context", "load_mail_filter_summary",
    "build_system_prompt", "build_actions_prompt",
]


def build_system_prompt(
    username: str,
    tenant_id: str,
    query: str,
    tools: dict,
    db_ctx: dict,
    outlook_token: str,
    live_mails: list,
    agenda: list,
    instructions: list,
    teams_context: str = "",
    mail_filter_summary: str = "",
    pending_actions: list = None,
    session_theme: str | None = None,
    domains: list[str] | None = None,
    user_tenants: list | None = None,
) -> str:
    display_name = username.capitalize()
    if domains is None:
        domains = ["mail", "drive", "teams", "calendar", "memory", "workflow"]
    query_lower = query.lower()

    cache_key_hot = f"hot_summary:{username}"
    hot_summary = cache.get(cache_key_hot)
    if hot_summary is None:
        hot_summary = get_hot_summary(username)
        cache.set(cache_key_hot, hot_summary)

    # Blocs de contexte — chacun dans prompt_blocks.py
    maturity_block, adaptive = build_maturity_block(username, display_name)
    patterns_block  = build_patterns_block(username, adaptive, maturity_block)
    narrative_block = build_narrative_block(query, username, tenant_id)
    alerts_block    = build_alerts_block(username)
    report_block    = build_report_block(username)
    team_block      = build_team_block(username, tenant_id)
    topics_block    = build_topics_block(username)
    web_info        = build_web_info()
    ton_block       = build_ton_block(hot_summary, display_name)

    try:
        from app.rag import retrieve_context
        rag_ctx = retrieve_context(query, username, tenant_id)
        aria_rules    = rag_ctx["rules_text"]
        aria_insights = rag_ctx["insights_text"]
        conv_context  = rag_ctx["conv_text"]
    except Exception:
        from app.memory_rules import get_aria_rules
        from app.memory_synthesis import get_aria_insights
        aria_rules    = get_aria_rules(username, tenant_id=tenant_id)
        aria_insights = get_aria_insights(limit=8, username=username, tenant_id=tenant_id)
        conv_context  = ""

    if conv_context and db_ctx.get("history"):
        recent_inputs = {h.get("user_input", "")[:80].lower() for h in db_ctx["history"] if h.get("user_input")}
        filtered_parts = []
        for block in conv_context.split("\n---\n"):
            if not any(inp and inp in block.lower() for inp in recent_inputs):
                filtered_parts.append(block)
        conv_context = "\n---\n".join(filtered_parts) if filtered_parts else ""

    theme_context_block = ""
    if session_theme:
        try:
            from app.rag import retrieve_theme_context
            theme_ctx = retrieve_theme_context(session_theme, username, tenant_id)
            theme_parts = [p for p in [theme_ctx.get("extra_rules", ""), theme_ctx.get("extra_insights", "")] if p]
            if theme_parts:
                theme_context_block = (
                    f"\n\n=== SESSION EN COURS : {session_theme.upper()} ===\n"
                    + "\n".join(theme_parts)
                )
        except Exception:
            pass

    if not teams_context:
        teams_context = load_teams_context(username)
    if not mail_filter_summary:
        mail_filter_summary = load_mail_filter_summary(username)

    contact_card = ""
    known_contacts = get_contacts_keywords(username=username, tenant_id=tenant_id)
    for name in known_contacts:
        if name in query_lower:
            contact_card = get_contact_card(name, tenant_id=tenant_id)
            if contact_card:
                break

    style_examples = get_style_examples(
        context=query[:100] if any(w in query_lower for w in ["repond", "redige", "ecris", "mail"]) else "",
        username=username
    )

    odoo_line = ""
    if tools["odoo_enabled"]:
        if tools["odoo_access"] == "full":
            odoo_line = "\nOdoo (acces complet)."
        else:
            shared = f" via {tools['odoo_shared_user'].capitalize()}" if tools["odoo_shared_user"] else ""
            odoo_line = f"\nOdoo (lecture seule{shared})."
    mailboxes_line = f"\nBoites supplementaires : {', '.join(tools['mail_extra_boxes'])}" if tools["mail_extra_boxes"] else ""

    # P0-1 : données externes protégées contre l'injection
    teams_context_block = f"\n\n=== TEAMS ===\n<donnees_externes>{teams_context}</donnees_externes>" if teams_context else ""
    mail_filter_block = f"\n\n=== FILTRE MAILS ===\n{mail_filter_summary}" if mail_filter_summary else ""
    conv_context_block = f"\n\n=== ECHANGES PASSES PERTINENTS ===\n{conv_context}" if conv_context else ""

    pending_block = ""
    if pending_actions:
        lines = [f"  #{a['id']} [{a['action_type']}] {a['label'] or ''}" for a in pending_actions]
        pending_block = (
            f"\n\n=== ACTIONS EN ATTENTE DE CONFIRMATION ===\n"
            + "\n".join(lines)
            + "\nSi l'utilisateur valide une action ci-dessus, genere [ACTION:CONFIRM:id]. "
            + "S'il l'annule, genere [ACTION:CANCEL:id]."
        )

    capabilities_block = "\n\n" + get_user_capabilities_prompt(username, tools)

    MAILBOX_BLOCK = f"""
=== BOITES MAIL DE {display_name.upper()} ===
Quand tu parles d'un mail, indique toujours de quelle boite il provient :
- Boite Outlook (guillaume@couffrant-solar.fr) = "boite Couffrant Solar"
- Boite Gmail (per1.guillaume@gmail.com) = "boite perso"
Ne jamais afficher l'adresse email brute — utilise toujours le nom de la boite.
"""
    FORMAT_BLOCK = """
=== FORMAT DES REPONSES ===
- N'utilise PAS d'emojis decoratifs en debut de chaque point d'une liste (ex: 🔹📌🎯💡)
- Utilise des tirets simples (-) ou des listes numerotees pour structurer tes reponses
- Reserve les emojis fonctionnels : ✅ (succes confirme), ❌ (echec/refus), ⚠️ (avertissement important)
- Prefere une prose fluide et claire aux listes quand c'est possible
- Evite les titres en gras inutiles (### Titre) pour les reponses courtes ou conversationnelles
- Sois direct et concis : la qualite prime sur la longueur
- Ne jamais inclure de signature dans un mail que tu rediges : la signature est ajoutee automatiquement par le systeme apres le corps du message
- Quand tu rediges un corps de mail (REPLY ou SEND_MAIL) : formate-le comme un vrai mail professionnel. Commence par "Bonjour [Prenom]," suivi d'un saut de ligne, puis le corps en paragraphes clairs. Corrige systematiquement les fautes d'orthographe et de grammaire (notamment celles issues de la dictee vocale). Ameliore la tournure si necessaire pour que le mail soit clair et professionnel, en restant fidelee au sens voulu.
- Quand une action mail est mise en queue (REPLY ou SEND_MAIL), annonce-le en langage naturel et chaleureux — JAMAIS de termes techniques comme "en queue", "action #XX", "pending", "queued". Dis par exemple : "Voilà la réponse, je l'envoie dès que tu valides !" ou "C'est prêt, tu confirmes ?"
- IMPORTANT : quand tu génères [ACTION:SEND_MAIL:...] ou [ACTION:REPLY:...], NE REPRODUIS PAS le contenu du mail dans ta réponse textuelle (ni le corps, ni le destinataire, ni le sujet). L'aperçu complet est affiché automatiquement dans la carte de confirmation. Ta réponse texte doit juste être la phrase d'annonce, courte.
- BOÎTE D'EXPÉDITION : tu peux envoyer depuis la boîte Microsoft (Outlook) ou depuis Gmail si l'utilisateur est connecté. Si l'utilisateur précise une boîte ("ma boîte perso", "depuis Gmail"), utilise la bonne boîte. Si aucune boîte n'est précisée, utilise la boîte Microsoft par défaut. Pour SEND_MAIL, indique la boîte souhaitée dans le label de l'action si l'utilisateur l'a précisé.
- CONTACTS : si tu ne connais pas l'adresse email d'un destinataire, utilise [ACTION:SEARCH_CONTACTS:prénom nom] pour chercher dans les contacts Microsoft AVANT de rédiger le mail. N'invente JAMAIS une adresse email. Si la recherche ne trouve rien, demande l'adresse à l'utilisateur.
"""
    return f"""Tu es Raya \u2014 l'assistante personnelle et evolutive de {display_name}.
Tu es Claude avec une memoire persistante. Tu n'as pas de comportement impose de l'exterieur.
Tu observes, tu apprends, tu t'organises librement. Tu parles au feminin.
Tu ne connais PAS le mot "Jarvis" et tu ne l'utilises JAMAIS. Tu es Raya, c'est ton seul nom.

{GUARDRAILS}{ton_block}
{FORMAT_BLOCK}
{capabilities_block}{web_info}

{f"=== CE QUE TU SAIS SUR {display_name.upper()} ==={chr(10)}{hot_summary}" if hot_summary else f"=== PREMIERE CONVERSATION ==={chr(10)}Tu ne connais pas encore {display_name}. Commence a observer et memoriser."}{maturity_block}{patterns_block}{narrative_block}

{f"=== TA MEMOIRE (pertinente pour cette question) ==={chr(10)}{aria_rules}" if aria_rules else "Ta memoire est vide. Tu peux commencer a construire via [ACTION:LEARN]."}

{f"=== TES OBSERVATIONS SUR {display_name.upper()} ==={chr(10)}{aria_insights}" if aria_insights else ""}{theme_context_block}{conv_context_block}{teams_context_block}{mail_filter_block}{pending_block}{alerts_block}{report_block}{team_block}

{topics_block}

{f"=== FICHE CONTACT ==={chr(10)}{contact_card}" if contact_card else ""}

{f"=== STYLE DE {display_name.upper()} ==={chr(10)}{style_examples}" if style_examples else ""}

{MAILBOX_BLOCK}
=== AUJOURD'HUI \u2014 {datetime.now().strftime('%A %d %B %Y')} ===
{"Microsoft 365 connecte." if outlook_token else f"Microsoft non connecte \u2014 {display_name} doit se reconnecter via /login."}{odoo_line}{mailboxes_line}
Agenda :
<donnees_externes>{json.dumps(agenda, ensure_ascii=False, default=str) if agenda else "Aucun RDV."}</donnees_externes>
Inbox ({len(live_mails)}) :
<donnees_externes>{json.dumps(live_mails, ensure_ascii=False, default=str) if live_mails else "Aucun."}</donnees_externes>
Memoire mails :
<donnees_externes>{json.dumps(db_ctx['mails_from_db'], ensure_ascii=False, default=str)}</donnees_externes>
Consignes : {chr(10).join(instructions) if instructions else "Aucune."}

{build_actions_prompt(domains, tools)}
"""
