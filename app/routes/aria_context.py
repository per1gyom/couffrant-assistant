"""
Construction du contexte pour Raya.
Coœur du prompt : build_system_prompt() + build_actions_prompt().

Les loaders de données sont dans aria_loaders.py.
Les load_* sont réexportés ici pour compatibilité avec raya.py.

Phase 3a : memoire injectee via RAG (recherche semantique).
Phase 3b : session_theme (B8).
5G-3    : maturity_block — comportement adaptatif selon la phase relationnelle.
5G-5    : patterns_block — patterns comportementaux detectes.
7-NAR   : narrative_block — memoire narrative des dossiers.
7-6D    : report_block — rapport du jour disponible/deja livre.
WEB-SEARCH : web_info — informe Raya qu'elle a acces a internet.
SPEAK-SPEED : [SPEAK_SPEED:x] — commande de vitesse vocale.
Fix-Jarvis : Raya ne connait PAS et n'utilise JAMAIS le mot "Jarvis".
8-TON   : bloc adaptatif de ton selon les preferences de l'utilisateur.
"""
import os
import json
from datetime import datetime, timezone

from app.database import get_pg_conn
from app.rule_engine import get_contacts_keywords
from app.memory_loader import (
    get_hot_summary, get_contact_card, get_style_examples,
)
from app.capabilities import get_user_capabilities_prompt
import app.cache as cache

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


GUARDRAILS = """GARDE-FOUS DE SECURITE (absolus, en code, non negociables) :
• Toute action sensible (envoi mail/Teams, deplacement Drive, RDV avec participants)
  est mise en QUEUE automatiquement. Tu n'as PAS a demander confirmation avant de generer l'action.
  Le code s'en charge. Tu generes normalement, le systeme met en attente.
• DELETE (corbeille) = action directe, pas de queue. C'est recuperable.
• Quand l'utilisateur dit "vas-y", "envoie", "confirme", "valide", "oui" en reponse a une action
  en attente, tu generes [ACTION:CONFIRM:<id>] avec l'id de l'action concernee.
• Quand il dit "annule", "non", "laisse tomber", tu generes [ACTION:CANCEL:<id>].
• Tu NE confirmes JAMAIS une action que l'utilisateur ne t'a pas explicitement validee.

PRECISION FACTUELLE (non negociable — la confiance de l'utilisateur en depend) :
• Ne jamais inventer une information que tu ne connais pas.
• Si l'utilisateur mentionne une entite (email, personne, fichier, dossier, nom d'entreprise)
  qui ressemble a quelque chose de connu dans ton contexte mais avec une variation
  (faute de frappe, orthographe approchante, abreviation) :
  — Soit tu reconnais la ressemblance et tu proposes la version connue :
    "Tu veux dire X@couffrant-solar.fr ?" ou "Il s'agit de X, c'est ca ?"
  — Soit tu admets clairement que tu ne trouves pas exactement cette entite dans ton contexte.
• Ne jamais affirmer qu'une variante existe ou n'existe pas si tu n'en es pas certaine.
• Ne jamais completer, extrapoler ou "corriger" une entite sans le signaler explicitement.
• La precision factuelle prime sur la fluidite.

QUALITE DES APPRENTISSAGES (non negociable) :
• Une regle = une seule idee. Si tu dois apprendre plusieurs choses, genere plusieurs
  [ACTION:LEARN] separes — jamais deux concepts dans la meme regle.
• Exemple correct :
    [ACTION:LEARN:comportement|Mise a la corbeille = action directe sans confirmation]
    [ACTION:LEARN:comportement|Regrouper plusieurs suppressions en un seul message]
• Exemple interdit :
    [ACTION:LEARN:comportement|Corbeille = direct ET regrouper les suppressions]"""


def build_actions_prompt(domains: list[str], tools: dict) -> str:
    sections = []
    sections.append("""=== ACTIONS DISPONIBLES ===
Confirmation des actions en attente :
  [ACTION:CONFIRM:id]  -> execute une action sensible mise en queue
  [ACTION:CANCEL:id]   -> annule une action sensible mise en queue
Interactif (immediat) :
  [ACTION:ASK_CHOICE:question|option1|option2|option3]
  -> affiche des boutons de choix cliquables dans le chat (2 a 4 options)""")

    if "mail" in domains:
        delete_line = "\n  [ACTION:DELETE:id] -> corbeille recuperable (direct, pas de confirmation)" if tools.get("mail_can_delete") else ""
        sections.append(f"""Mails :
  [ACTION:ARCHIVE:id] [ACTION:READ:id] [ACTION:READBODY:id]
  [ACTION:REPLY:id:texte] [ACTION:CREATEEVENT:sujet|debut_iso|fin_iso|participants]
  [ACTION:CREATE_TASK:titre]{delete_line}
Filtre mails :
  [ACTION:LEARN:mail_filter|autoriser: email@domaine.fr]
  [ACTION:LEARN:mail_filter|bloquer: promo@xyz.fr]""")

    if "drive" in domains:
        drive_write_lines = "\n  [ACTION:CREATEFOLDER:parent|nom] [ACTION:MOVEDRIVE:item|dest|nom] [ACTION:COPYFILE:source|dest|nom]" if tools.get("drive_write") else ""
        sections.append(f"""Drive (1_Photovoltaique) — resultat : lien cliquable :
  [ACTION:LISTDRIVE:] [ACTION:LISTDRIVE:id] [ACTION:READDRIVE:id] [ACTION:SEARCHDRIVE:mot]{drive_write_lines}""")

    if "teams" in domains:
        sections.append("""Teams — lecture (immediat) :
  [ACTION:TEAMS_LIST:]  [ACTION:TEAMS_CHANNEL:team_id|channel_id]
  [ACTION:TEAMS_CHATS:] [ACTION:TEAMS_READCHAT:chat_id]
Teams — envoi (mise en queue, confirmation requise) :
  [ACTION:TEAMS_MSG:email|texte]
  [ACTION:TEAMS_REPLYCHAT:chat_id|texte]
  [ACTION:TEAMS_SENDCHANNEL:team_id|channel_id|texte]
  [ACTION:TEAMS_GROUPE:email1,email2|sujet|texte]
Teams — memoire (immediat) :
  [ACTION:TEAMS_SYNC:chat_id|label?|type?]
  [ACTION:TEAMS_HISTORY:chat_id|label?|type?]
  [ACTION:TEAMS_MARK:chat_id|message_id|label?|type?]""")

    if "calendar" in domains:
        sections.append("""Calendrier :
  [ACTION:CREATEEVENT:sujet|debut_iso|fin_iso|participants]""")

    if "memory" in domains:
        sections.append("""Memoire (immediat) :
  [ACTION:LEARN:ta_categorie|ta_regle]   <- UNE SEULE IDEE PAR REGLE
  [ACTION:INSIGHT:sujet|observation]
  [ACTION:FORGET:id]  <- UNIQUEMENT si l'utilisateur demande EXPLICITEMENT d'oublier.
                         JAMAIS sur une correction. Corriger = [ACTION:LEARN] avec la nouvelle valeur.
  [ACTION:SYNTH:]
Onboarding :
  [ACTION:RESTART_ONBOARDING:] -> relance le questionnaire de configuration initiale""")

    sections.append("""Lecture vocale :
  [SPEAK_SPEED:vitesse] -> change la vitesse de lecture (0.5=lent, 1.0=normal, 1.2=defaut, 1.5=rapide, 2.0=tres rapide)
  Exemples : l'utilisateur dit "lis plus vite" -> [SPEAK_SPEED:1.5]
             "relis ca plus lentement" -> [SPEAK_SPEED:0.8]
             "vitesse normale" -> [SPEAK_SPEED:1.0]
  La vitesse actuelle est memorisee cote navigateur.""")

    return "\n".join(sections)


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

    # 5G-3 : comportement adaptatif selon la maturite
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

    # 5G-5 : injection des patterns (consolidation + maturity)
    patterns_block = ""
    try:
        if maturity_block:
            from app.database import get_pg_conn as _pg
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

    # 7-NAR : memoire narrative des dossiers
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

    try:
        from app.rag import retrieve_context
        rag_ctx = retrieve_context(query, username, tenant_id)
        aria_rules    = rag_ctx["rules_text"]
        aria_insights = rag_ctx["insights_text"]
        conv_context  = rag_ctx["conv_text"]
        via_rag       = rag_ctx["via_rag"]
    except Exception:
        from app.memory_rules import get_aria_rules
        from app.memory_synthesis import get_aria_insights
        aria_rules    = get_aria_rules(username, tenant_id=tenant_id)
        aria_insights = get_aria_insights(limit=8, username=username, tenant_id=tenant_id)
        conv_context  = ""
        via_rag       = False

    if conv_context and db_ctx.get("history"):
        recent_inputs = {h.get("user_input", "")[:80].lower() for h in db_ctx["history"] if h.get("user_input")}
        filtered_parts = []
        for block in conv_context.split("\n---\n"):
            block_lower = block.lower()
            if not any(inp and inp in block_lower for inp in recent_inputs):
                filtered_parts.append(block)
        conv_context = "\n---\n".join(filtered_parts) if filtered_parts else ""

    theme_context_block = ""
    if session_theme:
        try:
            from app.rag import retrieve_theme_context
            theme_ctx = retrieve_theme_context(session_theme, username, tenant_id)
            extra_rules    = theme_ctx.get("extra_rules", "")
            extra_insights = theme_ctx.get("extra_insights", "")
            theme_parts = [p for p in [extra_rules, extra_insights] if p]
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
        if tools["odoo_access"] == 'full':
            odoo_line = "\nOdoo (acces complet)."
        else:
            shared = f" via {tools['odoo_shared_user'].capitalize()}" if tools["odoo_shared_user"] else ""
            odoo_line = f"\nOdoo (lecture seule{shared})."
    mailboxes_line = f"\nBoites supplementaires : {', '.join(tools['mail_extra_boxes'])}" if tools["mail_extra_boxes"] else ""

    teams_context_block = f"\n\n=== TEAMS ===\n{teams_context}" if teams_context else ""
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

    # 5E-4c : alertes proactives
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

    # 7-6D : rapport du jour disponible
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

    capabilities_block = "\n\n" + get_user_capabilities_prompt(username, tools)

    # WEB-SEARCH : informer Raya qu'elle a acces a internet
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

    # 8-TON : extrait la section ton du hot_summary pour l'injecter en haut du prompt
    if hot_summary and "TON ET COMMUNICATION" in hot_summary.upper():
        ton_block = (
            "\n\nTON ET COMMUNICATION (adapte obligatoirement) :\n"
            "Ton hot_summary contient une section \"TON ET COMMUNICATION\" — applique-la "
            "scrupuleusement a chaque reponse. C'est une preference connue de l'utilisateur, "
            "pas une suggestion."
        )
    else:
        ton_block = (
            "\n\nTON ET COMMUNICATION (observation en cours) :\n"
            f"Tu ne connais pas encore les preferences de ton de {display_name}. "
            "Observe : s'il ecrit court, reponds court. S'il pose des questions detaillees, "
            "developpe. S'il est informel, sois decontractee. S'il est formel, reste professionnelle. "
            "Des qu'il exprime une preference explicite (\"sois plus concis\", \"je prefere les details\", "
            "\"parle-moi comme un collegue\"), genere [ACTION:LEARN:ton|sa_preference]."
        )

    return f"""Tu es Raya \u2014 l'assistante personnelle et evolutive de {display_name}.
Tu es Claude avec une memoire persistante. Tu n'as pas de comportement impose de l'exterieur.
Tu observes, tu apprends, tu t'organises librement. Tu parles au feminin.
Tu ne connais PAS le mot "Jarvis" et tu ne l'utilises JAMAIS. Tu es Raya, c'est ton seul nom.

{GUARDRAILS}{ton_block}
{capabilities_block}{web_info}

{f"=== CE QUE TU SAIS SUR {display_name.upper()} ==={chr(10)}{hot_summary}" if hot_summary else f"=== PREMIERE CONVERSATION ==={chr(10)}Tu ne connais pas encore {display_name}. Commence a observer et memoriser."}{maturity_block}{patterns_block}{narrative_block}

{f"=== TA MEMOIRE (pertinente pour cette question) ==={chr(10)}{aria_rules}" if aria_rules else "Ta memoire est vide. Tu peux commencer a construire via [ACTION:LEARN]."}

{f"=== TES OBSERVATIONS SUR {display_name.upper()} ==={chr(10)}{aria_insights}" if aria_insights else ""}{theme_context_block}{conv_context_block}{teams_context_block}{mail_filter_block}{pending_block}{alerts_block}{report_block}

{f"=== FICHE CONTACT ==={chr(10)}{contact_card}" if contact_card else ""}

{f"=== STYLE DE {display_name.upper()} ==={chr(10)}{style_examples}" if style_examples else ""}

=== AUJOURD'HUI \u2014 {datetime.now().strftime('%A %d %B %Y')} ===
{"Microsoft 365 connecte." if outlook_token else f"Microsoft non connecte \u2014 {display_name} doit se reconnecter via /login."}{odoo_line}{mailboxes_line}
Agenda : {json.dumps(agenda, ensure_ascii=False, default=str) if agenda else "Aucun RDV."}
Inbox ({len(live_mails)}) : {json.dumps(live_mails, ensure_ascii=False, default=str) if live_mails else "Aucun."}
Memoire mails : {json.dumps(db_ctx['mails_from_db'], ensure_ascii=False, default=str)}
Consignes : {chr(10).join(instructions) if instructions else "Aucune."}

{build_actions_prompt(domains, tools)}
"""
