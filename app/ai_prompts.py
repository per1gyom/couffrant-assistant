"""
Helpers et construction de prompts pour ai_client.
Extrait de ai_client.py -- SPLIT-F8.
"""
import json,re
from app.database import get_pg_conn
from app.logging_config import get_logger
logger=get_logger("raya.ai")


def _parse_json_safe(text: str) -> dict:
    text = text.strip()
    text = re.sub(r'^```(?:json)?\s*', '', text, flags=re.MULTILINE)
    text = re.sub(r'\s*```$', '', text, flags=re.MULTILINE)
    return json.loads(text.strip())


# ─── CATÉGORIES DYNAMIQUES ───

_DEFAULT_CATEGORIES = [
    "raccordement", "consuel", "chantier", "commercial", "financier",
    "fournisseur", "reunion", "securite", "interne", "notification", "autre"
]


def build_learning_text(examples: list[dict]) -> str:
    if not examples:
        return ""
    blocks = []
    for i, ex in enumerate(examples, 1):
        blocks.append(
            f"Exemple {i}\nSujet : {ex.get('mail_subject','')}\n"
            f"Expéditeur : {ex.get('mail_from','')}\n"
            f"Contenu : {ex.get('mail_body_preview','')}\n"
            f"Réponse IA : {ex.get('ai_reply','')}\n"
            f"Réponse corrigée : {ex.get('final_reply','')}"
        )
    return "\n\n".join(blocks)



def get_odoo_context(sender_email: str) -> dict:
    try:
        from app.connectors.odoo_connector import perform_odoo_action
        partner = perform_odoo_action("get_partner_by_email", {"email": sender_email})
        if not partner.get("result"):
            return {"client_trouve": False}
        p = partner["result"]
        projects = perform_odoo_action("get_projects_by_partner", {"partner_id": p["id"]})
        return {"client_trouve": True, "client_nom": p.get("name"), "client_email": p.get("email"),
                "client_telephone": p.get("phone"), "client_ville": p.get("city"),
                "chantiers": projects.get("result", [])}
    except Exception:
        return {"client_trouve": False}



def get_style_profile(username: str = 'guillaume') -> str:
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute(
            "SELECT content FROM aria_profile WHERE username = %s AND profile_type = 'style' ORDER BY id DESC LIMIT 1",
            (username,)
        )
        row = c.fetchone()
        return row[0] if row else ""
    except Exception:
        return ""
    finally:
        if conn: conn.close()


