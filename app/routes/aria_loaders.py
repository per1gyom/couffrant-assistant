"""
Chargeurs de données pour le contexte Raya.
Toutes les fonctions load_* utilisées par build_system_prompt().
"""
from datetime import datetime, timezone

from app.graph_client import graph_get
from app.database import get_pg_conn
from app.app_security import get_user_tools as _get_user_tools
from app.connectors.outlook_connector import perform_outlook_action
import app.cache as cache


def load_user_tools(username: str) -> dict:
    user_tools = _get_user_tools(username)
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
    cache_key = f"teams_ctx:{username}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached
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
            teams_insights = "Memoire Teams recente :\n" + "\n".join(lines)
    except Exception:
        pass
    finally:
        if conn: conn.close()
    parts = [p for p in [markers_summary, teams_insights] if p]
    result = "\n".join(parts) if parts else ""
    cache.set(cache_key, result)
    return result


def load_mail_filter_summary(username: str) -> str:
    cache_key = f"mail_filter:{username}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached
    try:
        from app.rule_engine import get_rules_by_category
        rules = get_rules_by_category(username, 'mail_filter')
        if not rules:
            return ""
        whitelist = [r for r in rules if r.strip().lower().startswith('autoriser:')]
        blacklist = [r for r in rules if r.strip().lower().startswith('bloquer:')]
        parts = []
        if whitelist:
            parts.append(f"Whitelist ({len(whitelist)}) : " + ", ".join(w[10:].strip() for w in whitelist[:5]))
        if blacklist:
            parts.append(f"Blacklist ({len(blacklist)}) : " + ", ".join(b[8:].strip() for b in blacklist[:5]))
        result = "\n".join(parts)
        cache.set(cache_key, result)
        return result
    except Exception:
        return ""
