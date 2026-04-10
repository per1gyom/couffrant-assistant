"""
Construction du contexte pour Raya.
Isole la lecture DB, les mails live, l'agenda et la construction du prompt système.

Les appels réseau (mails live, agenda, contexte Teams) sont lancés
en parallèle depuis raya_endpoint() pour réduire la latence.
"""
import json
from datetime import datetime, timezone

from app.graph_client import graph_get
from app.database import get_pg_conn
from app.token_manager import get_valid_microsoft_token
from app.app_security import get_user_tools
from app.memory_manager import get_contacts_keywords
from app.connectors.outlook_connector import perform_outlook_action
from app.memory_loader import (
    get_hot_summary, get_aria_rules, get_aria_insights,
    get_contact_card, get_style_examples,
)
from app.feedback_store import get_global_instructions


GUARDRAILS = """GARDE-FOUS DE SÉCURITÉ (absolus, en code, non négociables) :
• Toute action sensible (envoi mail/Teams, suppression, déplacement Drive, RDV avec participants)
  est mise en QUEUE automatiquement par le système. Tu n'as PAS à demander confirmation avant
  de générer l'action — le code s'en charge. Tu génères normalement, le système met en attente.
• Quand Guillaume dit "vas-y", "envoie", "confirme", "valide" en réponse à une action en attente,
  tu génères [ACTION:CONFIRM:<id>] avec l'id de l'action concernée.
• Quand Guillaume dit "annule", "non", "laisse tomber", tu génères [ACTION:CANCEL:<id>].
• Si plusieurs actions sont en attente, tu peux confirmer/annuler chacune indépendamment.
• Tu NE confirmes JAMAIS une action que Guillaume ne t'a pas explicitement validée."""


def load_user_tools(username: str) -> dict:
    user_tools = get_user_tools(username)
    drive_tool = user_tools.get('drive', {})
    drive_access = drive_tool.get('access_level', 'read_only') if drive_tool.get('enabled', True) else 'none'
    mail_tool = user_tools.get('outlook', {})
    odoo_tool = user_tools.get('odoo', {})
    return {
        "drive_write": drive_access in ('write', 'full'),
        "drive_can_delete": drive_tool.get('config', {}).get('can_delete', False),
        "mail_can_delete": mail_tool.get('config', {}).get('can_delete_mail', False),
        "mail_extra_boxes": mail_tool.get('config', {}).get('mailboxes', []),
        "odoo_enabled": odoo_tool.get('enabled', False) and odoo_tool.get('access_level', 'none') != 'none',
        "odoo_access": odoo_tool.get('access_level', 'none'),
        "odoo_shared_user": odoo_tool.get('config', {}).get('shared_user'),
    }


def load_db_context(username: str) -> dict:
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            SELECT id as db_id, message_id, from_email, subject, display_title, category, priority,
                   short_summary, suggested_reply, raw_body_preview, received_at, mailbox_source
            FROM mail_memory WHERE username = %s
            ORDER BY received_at DESC NULLS LAST LIMIT 10
        """, (username,))
        columns = [desc[0] for desc in c.description]
        mails_from_db = [dict(zip(columns, row)) for row in c.fetchall()]
        c.execute("SELECT user_input, aria_response FROM aria_memory WHERE username = %s ORDER BY id DESC LIMIT 6",
                  (username,))
        columns = [desc[0] for desc in c.description]
        history = [dict(zip(columns, row)) for row in c.fetchall()]
        history.reverse()
        c.execute("SELECT COUNT(*) FROM aria_memory WHERE username = %s", (username,))
        conv_count = c.fetchone()[0]
        return {"mails_from_db": mails_from_db, "history": history, "conv_count": conv_count}
    finally:
        if conn: conn.close()


def load_live_mails(outlook_token: str, username: str) -> list:
    if not outlook_token:
        return []
    try:
        data = graph_get(outlook_token, "/me/mailFolders/inbox/messages", params={
            "$top": 20, "$select": "id,subject,from,receivedDateTime,bodyPreview,isRead",
            "$orderby": "receivedDateTime DESC"})
        mails = []
        for msg in data.get("value", []):
            mails.append({
                "message_id": msg["id"],
                "from_email": msg.get("from", {}).get("emailAddress", {}).get("address", ""),
                "subject": msg.get("subject", "(Sans objet)"),
                "raw_body_preview": msg.get("bodyPreview", ""),
                "received_at": msg.get("receivedDateTime", ""),
                "is_read": msg.get("isRead", False),
                "mailbox_source": "outlook",
            })
        return mails
    except Exception as e:
        print(f"[Raya] Erreur Outlook live {username}: {e}")
        return []


def load_agenda(outlook_token: str) -> list:
    if not outlook_token:
        return []
    try:
        now = datetime.now(timezone.utc)
        start = now.replace(hour=0, minute=0, second=0).isoformat()
        end = now.replace(hour=23, minute=59, second=59).isoformat()
        result = perform_outlook_action("list_calendar_events",
            {"start": start, "end": end, "top": 10}, outlook_token)
        return result.get("items", [])
    except Exception:
        return []


def load_teams_context(username: str) -> str:
    try:
        from app.memory_teams import get_teams_context_summary
        markers_summary = get_teams_context_summary(username)
    except Exception:
        markers_summary = ""
    teams_insights = ""
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            SELECT topic, insight FROM aria_insights
            WHERE username = %s AND source = 'teams'
            ORDER BY updated_at DESC LIMIT 5
        """, (username,))
        rows = c.fetchall()
        if rows:
            lines = [f"  [{r[0]}] {r[1]}" for r in rows]
            teams_insights = "Mémoire Teams récente :\n" + "\n".join(lines)
    except Exception:
        pass
    finally:
        if conn: conn.close()
    parts = [p for p in [markers_summary, teams_insights] if p]
    return "\n".join(parts) if parts else ""


def load_mail_filter_summary(username: str) -> str:
    try:
        from app.memory_rules import get_rules_by_category
        rules = get_rules_by_category('mail_filter', username)
        if not rules:
            return ""
        whitelist = [r for r in rules if r.strip().lower().startswith('autoriser:')]
        blacklist = [r for r in rules if r.strip().lower().startswith('bloquer:')]
        parts = []
        if whitelist:
            parts.append(f"Whitelist ({len(whitelist)}) : " + ", ".join(w[10:].strip() for w in whitelist[:5]))
        if blacklist:
            parts.append(f"Blacklist ({len(blacklist)}) : " + ", ".join(b[8:].strip() for b in blacklist[:5]))
        return "\n".join(parts)
    except Exception:
        return ""


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
) -> str:
    display_name = username.capitalize()
    query_lower = query.lower()

    hot_summary = get_hot_summary(username)
    aria_rules = get_aria_rules(username)
    aria_insights = get_aria_insights(limit=8, username=username)

    if not teams_context:
        teams_context = load_teams_context(username)
    if not mail_filter_summary:
        mail_filter_summary = load_mail_filter_summary(username)

    contact_card = ""
    known_contacts = get_contacts_keywords(username=username)
    for name in known_contacts:
        if name in query_lower:
            contact_card = get_contact_card(name, tenant_id=tenant_id)
            if contact_card:
                break

    style_examples = get_style_examples(
        context=query[:100] if any(w in query_lower for w in ["répond", "rédige", "écris", "mail"]) else "",
        username=username
    )

    delete_line = "\n  [ACTION:DELETE:id] \u2192 corbeille récupérable" if tools["mail_can_delete"] else ""
    drive_write_lines = ""
    if tools["drive_write"]:
        drive_write_lines = "\n  [ACTION:CREATEFOLDER:parent|nom] [ACTION:MOVEDRIVE:item|dest|nom] [ACTION:COPYFILE:source|dest|nom]"
    odoo_line = ""
    if tools["odoo_enabled"]:
        if tools["odoo_access"] == 'full':
            odoo_line = "\nOdoo (accès complet)."
        else:
            shared = f" via {tools['odoo_shared_user'].capitalize()}" if tools["odoo_shared_user"] else ""
            odoo_line = f"\nOdoo (lecture seule{shared})."
    mailboxes_line = f"\nBoîtes supplémentaires : {', '.join(tools['mail_extra_boxes'])}" if tools["mail_extra_boxes"] else ""

    teams_context_block = f"\n\n=== TEAMS ==={chr(10)}{teams_context}" if teams_context else ""
    mail_filter_block = f"\n\n=== FILTRE MAILS ==={chr(10)}{mail_filter_summary}" if mail_filter_summary else ""

    # Bloc actions en attente de confirmation
    pending_block = ""
    if pending_actions:
        lines = [f"  #{a['id']} [{a['action_type']}] {a['label']}" for a in pending_actions]
        pending_block = (
            f"\n\n=== ACTIONS EN ATTENTE DE CONFIRMATION ===\n"
            + "\n".join(lines)
            + "\nSi Guillaume valide : [ACTION:CONFIRM:id] — S'il annule : [ACTION:CANCEL:id]"
        )

    return f"""Tu es Raya — l'assistante personnelle et évolutive de {display_name}.
Tu es Claude avec une mémoire persistante. Tu n'as pas de comportement imposé de l'extérieur.
Tu observes, tu apprends, tu t'organises librement. Tu parles au féminin.

{GUARDRAILS}

{f"=== CE QUE TU SAIS SUR {display_name.upper()} ==={chr(10)}{hot_summary}" if hot_summary else f"=== PREMIÈRE CONVERSATION ==={chr(10)}Tu ne connais pas encore {display_name}. Commence à observer et mémoriser."}

{f"=== TA MÉMOIRE ==={chr(10)}{aria_rules}" if aria_rules else "Ta mémoire est vide. Tu peux commencer à construire via [ACTION:LEARN]."}

{f"=== TES OBSERVATIONS SUR {display_name.upper()} ==={chr(10)}{aria_insights}" if aria_insights else ""}{teams_context_block}{mail_filter_block}{pending_block}

{f"=== FICHE CONTACT ==={chr(10)}{contact_card}" if contact_card else ""}

{f"=== STYLE DE {display_name.upper()} ==={chr(10)}{style_examples}" if style_examples else ""}

=== AUJOURD'HUI — {datetime.now().strftime('%A %d %B %Y')} ===
{"Microsoft 365 connecté." if outlook_token else f"Microsoft non connecté — {display_name} doit se reconnecter via /login."}{odoo_line}{mailboxes_line}
Agenda : {json.dumps(agenda, ensure_ascii=False, default=str) if agenda else "Aucun RDV."}
Inbox ({len(live_mails)}) : {json.dumps(live_mails, ensure_ascii=False, default=str) if live_mails else "Aucun."}
Mémoire mails : {json.dumps(db_ctx['mails_from_db'], ensure_ascii=False, default=str)}
Consignes : {chr(10).join(instructions) if instructions else "Aucune."}

=== ACTIONS DISPONIBLES ===
Confirmation :
  [ACTION:CONFIRM:id]  → exécute une action sensible mise en queue
  [ACTION:CANCEL:id]   → annule une action sensible mise en queue
Mails :
  [ACTION:ARCHIVE:id] [ACTION:READ:id] [ACTION:READBODY:id]
  [ACTION:REPLY:id:texte] [ACTION:CREATEEVENT:sujet|debut_iso|fin_iso|participants]
  [ACTION:CREATE_TASK:titre]{delete_line}
Drive (1_Photovoltaïque) — format : 📁 "Nom" [id:ID] :
  [ACTION:LISTDRIVE:] [ACTION:LISTDRIVE:id] [ACTION:READDRIVE:id] [ACTION:SEARCHDRIVE:mot]{drive_write_lines}
Teams — lecture/écriture (actions d'envoi mises en queue) :
  [ACTION:TEAMS_LIST:]                                       → équipes + canaux en un appel
  [ACTION:TEAMS_CHANNEL:team_id|channel_id]                  → lit un canal
  [ACTION:TEAMS_CHATS:]                                      → liste les chats actifs
  [ACTION:TEAMS_READCHAT:chat_id]                            → lit un chat
  [ACTION:TEAMS_MSG:email|texte]                             → message 1:1 (queue)
  [ACTION:TEAMS_REPLYCHAT:chat_id|texte]                     → répond dans un chat (queue)
  [ACTION:TEAMS_SENDCHANNEL:team_id|channel_id|texte]        → envoie dans un canal (queue)
  [ACTION:TEAMS_GROUPE:email1,email2|sujet|texte]            → crée un groupe (queue)
Teams — mémoire :
  [ACTION:TEAMS_SYNC:chat_id|label?|type?]
  [ACTION:TEAMS_HISTORY:chat_id|label?|type?]
  [ACTION:TEAMS_MARK:chat_id|message_id|label?|type?]
Filtre mails :
  [ACTION:LEARN:mail_filter|autoriser: email@domaine.fr]
  [ACTION:LEARN:mail_filter|bloquer: sujet:pub]
Mémoire :
  [ACTION:LEARN:ta_catégorie|ta_règle]
  [ACTION:INSIGHT:sujet|observation]
  [ACTION:FORGET:id]
  [ACTION:SYNTH:]
"""
