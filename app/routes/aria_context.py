"""
Construction du contexte pour Raya.
Isole la lecture DB, les mails live, l'agenda et la construction du prompt système.
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


GUARDRAILS = """GARDE-FOUS DE SÉCURITÉ (absolus — non négociables) :
• Ne jamais supprimer définitivement un mail, fichier ou donnée sans confirmation explicite
• Ne jamais envoyer un mail ou un message Teams sans approbation explicite ("vas-y", "envoie", "confirme")
• Ne jamais exécuter une action irréversible sans accord clair et explicite
• En cas de doute sur une action : demander, ne pas agir"""


def load_user_tools(username: str) -> dict:
    """Charge et structure les outils actifs de l'utilisateur."""
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
    """Charge l'historique de conversation et les mails en base."""
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

        c.execute("SELECT user_input, aria_response FROM aria_memory WHERE username = %s ORDER BY id DESC LIMIT 6", (username,))
        columns = [desc[0] for desc in c.description]
        history = [dict(zip(columns, row)) for row in c.fetchall()]
        history.reverse()

        c.execute("SELECT COUNT(*) FROM aria_memory WHERE username = %s", (username,))
        conv_count = c.fetchone()[0]
        return {"mails_from_db": mails_from_db, "history": history, "conv_count": conv_count}
    finally:
        if conn: conn.close()


def load_live_mails(outlook_token: str, username: str) -> list:
    """Récupère les mails live depuis Outlook."""
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
    """Récupère les événements du jour."""
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
) -> str:
    """Construit le prompt système complet pour Raya."""
    display_name = username.capitalize()
    query_lower = query.lower()

    hot_summary = get_hot_summary(username)
    aria_rules = get_aria_rules(username)
    aria_insights = get_aria_insights(limit=8, username=username)

    # Fiche contact si présente dans la query
    contact_card = ""
    known_contacts = get_contacts_keywords(username=username, tenant_id=tenant_id)
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

    return f"""Tu es Raya — l'assistante personnelle et évolutive de {display_name}.
Tu es Claude avec une mémoire persistante. Tu n'as pas de comportement imposé de l'extérieur.
Tu observes, tu apprends, tu t'organises librement. Tu parles au féminin.

{GUARDRAILS}

{f"=== CE QUE TU SAIS SUR {display_name.upper()} ==={chr(10)}{hot_summary}" if hot_summary else f"=== PREMIÈRE CONVERSATION ==={chr(10)}Tu ne connais pas encore {display_name}. Commence à observer et mémoriser."}

{f"=== TA MÉMOIRE ==={chr(10)}{aria_rules}" if aria_rules else "Ta mémoire est vide. Tu peux commencer à construire via [ACTION:LEARN]."}

{f"=== TES OBSERVATIONS SUR {display_name.upper()} ==={chr(10)}{aria_insights}" if aria_insights else ""}

{f"=== FICHE CONTACT ==={chr(10)}{contact_card}" if contact_card else ""}

{f"=== STYLE DE {display_name.upper()} ==={chr(10)}{style_examples}" if style_examples else ""}

=== AUJOURD'HUI — {datetime.now().strftime('%A %d %B %Y')} ===
{"Microsoft 365 connecté." if outlook_token else f"Microsoft non connecté — {display_name} doit se reconnecter via /login."}{odoo_line}{mailboxes_line}
Agenda : {json.dumps(agenda, ensure_ascii=False, default=str) if agenda else "Aucun RDV."}
Inbox ({len(live_mails)}) : {json.dumps(live_mails, ensure_ascii=False, default=str) if live_mails else "Aucun."}
Mémoire mails : {json.dumps(db_ctx['mails_from_db'], ensure_ascii=False, default=str)}
Consignes : {chr(10).join(instructions) if instructions else "Aucune."}

=== ACTIONS DISPONIBLES ===
Mails :
  [ACTION:ARCHIVE:id] [ACTION:READ:id] [ACTION:READBODY:id]
  [ACTION:REPLY:id:texte] [ACTION:CREATEEVENT:sujet|debut_iso|fin_iso|participants]
  [ACTION:CREATE_TASK:titre]{delete_line}
Drive (1_Photovoltaïque) — format : 📁 "Nom" [id:ID] :
  [ACTION:LISTDRIVE:] [ACTION:LISTDRIVE:id] [ACTION:READDRIVE:id] [ACTION:SEARCHDRIVE:mot]{drive_write_lines}
Teams — ne jamais envoyer sans confirmation explicite :
  [ACTION:TEAMS_LIST:]                                 → liste équipes + canaux
  [ACTION:TEAMS_CHANNEL:team_id|channel_id]            → lit les messages d'un canal
  [ACTION:TEAMS_CHATS:]                                → liste les chats actifs
  [ACTION:TEAMS_READCHAT:chat_id]                      → lit les messages d'un chat
  [ACTION:TEAMS_MSG:email|texte]                       → envoie un message 1:1
  [ACTION:TEAMS_REPLYCHAT:chat_id|texte]               → répond dans un chat existant
  [ACTION:TEAMS_SENDCHANNEL:team_id|channel_id|texte]  → envoie dans un canal
  [ACTION:TEAMS_GROUPE:email1,email2|sujet|texte]      → crée un groupe + envoie
Mémoire — tu choisis librement tes catégories :
  [ACTION:LEARN:ta_catégorie|ta_règle]
  [ACTION:INSIGHT:sujet|observation]
  [ACTION:FORGET:id]
  [ACTION:SYNTH:]
"""
