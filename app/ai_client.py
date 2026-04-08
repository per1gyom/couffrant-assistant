"""
Analyse des mails entrants par Claude.

Les règles de tri, d'urgence et de style sont chargées dynamiquement
depuis aria_rules via rule_engine. Aucune règle métier n'est codée en dur.

Seuls garde-fous immuables dans ce module :
- Retourner uniquement du JSON valide
- Ne jamais inventer d'informations absentes du mail
- Ne jamais inclure de signature dans suggested_reply
"""

import json
import re
import anthropic

from app.config import ANTHROPIC_API_KEY, ANTHROPIC_MODEL_FAST, ANTHROPIC_MODEL_SMART
from app.database import get_pg_conn
from app.rule_engine import get_rules_as_text, get_rules_by_category

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
MODEL = ANTHROPIC_MODEL_FAST


def _parse_json_safe(text: str) -> dict:
    text = text.strip()
    text = re.sub(r'^```(?:json)?\s*', '', text, flags=re.MULTILINE)
    text = re.sub(r'\s*```$', '', text, flags=re.MULTILINE)
    return json.loads(text.strip())


def get_learning_examples(category: str, username: str = 'guillaume', limit: int = 3) -> list[dict]:
    """Exemples de corrections passées pour le few-shot learning — filtrés par username."""
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        # Fix 1c — filtre par username pour isolation correcte
        c.execute("""
            SELECT mail_subject, mail_from, mail_body_preview, category, ai_reply, final_reply
            FROM reply_learning_memory
            WHERE category = %s AND username = %s
            ORDER BY id DESC LIMIT %s
        """, (category, username, limit))
        return [{"mail_subject": r[0], "mail_from": r[1], "mail_body_preview": r[2],
                 "category": r[3], "ai_reply": r[4], "final_reply": r[5]} for r in c.fetchall()]
    except Exception:
        return []
    finally:
        if conn: conn.close()


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


def _get_hint_category(full_text: str, username: str) -> str:
    from app.rule_engine import extract_category_keywords
    categories = ["raccordement", "commercial", "reunion", "chantier", "financier"]
    for cat in categories:
        kws = extract_category_keywords(username, cat)
        if not kws:
            fallbacks = {
                "raccordement": ["enedis", "consuel", "raccordement"],
                "commercial":   ["devis", "offre", "contrat"],
                "reunion":      ["réunion", "meeting", "teams.microsoft"],
                "chantier":     ["chantier", "planning", "installation"],
                "financier":    ["facture", "paiement", "échéance"],
            }
            kws = fallbacks.get(cat, [])
        if any(kw in full_text for kw in kws):
            return cat
    return "autre"


def analyze_single_mail_with_ai(
    message: dict,
    instructions: list[str] | None = None,
    username: str = 'guillaume'
) -> dict:
    instructions = instructions or []
    sender_email = message.get("from", {}).get("emailAddress", {}).get("address", "Expéditeur inconnu")
    odoo_context = get_odoo_context(sender_email)
    style_profile = get_style_profile(username)
    rules_text = get_rules_as_text(username, ["tri_mails", "urgence", "style_reponse"])

    full_lower = (
        f"{message.get('subject', '')} "
        f"{message.get('bodyPreview', '')} "
        f"{sender_email}"
    ).lower()
    hint_cat = _get_hint_category(full_lower, username)
    learning_examples = get_learning_examples(hint_cat, username)
    learning_text = build_learning_text(learning_examples)

    payload = {
        "subject": message.get("subject", ""),
        "from": sender_email,
        "receivedDateTime": message.get("receivedDateTime", ""),
        "bodyPreview": message.get("bodyPreview", ""),
        "body": (
            message.get("body", {}).get("content", "")
            if isinstance(message.get("body"), dict)
            else message.get("body", "")
        ),
        "odoo_context": odoo_context,
    }

    rules_section = (
        f"=== RÈGLES D'ARIA (apprise et évolutives) ===\n{rules_text}\n"
        if rules_text else
        "Pas encore de règles enregistrées. Utilise le bon sens métier photovoltaïque.\n"
    )

    system_prompt = f"""Tu es Aria, l'assistante de Couffrant Solar.
Analyse ce mail et retourne UNIQUEMENT un objet JSON valide, sans texte avant ou après, sans bloc markdown.

{rules_section}

Garde-fous immuables :
- Retourner UNIQUEMENT du JSON valide, rien d'autre
- Ne jamais inventer d'information absente du mail
- Ne jamais mettre de signature dans suggested_reply

Tu appliques les règles avec ton jugement. Si une situation n'est pas couverte, utilise le bon sens métier.

Champs JSON requis :
display_title, category, priority (haute/moyenne/basse), reason,
suggested_action, short_summary, group_hints (array), confidence (0-1),
confidence_level (haute/moyenne/basse), needs_review (bool), needs_reply (bool),
reply_urgency (haute/moyenne/basse), reply_reason,
response_type (oui_non/planification/demande_info/demande_document/
accuse_reception/relance/pas_de_reponse/autre),
missing_fields (array), suggested_reply_subject, suggested_reply (sans signature)

Catégories valides : raccordement, consuel, chantier, commercial, financier,
fournisseur, reunion, securite, interne, notification, autre

Profil de style :
{style_profile[:600] if style_profile else "Écrire de façon directe et concise."}

Contexte Odoo :
{json.dumps(odoo_context, ensure_ascii=False)}

Consignes additionnelles :
{json.dumps(instructions, ensure_ascii=False)}
{f"Exemples de corrections passées :{chr(10)}{learning_text}" if learning_text else ""}"""

    response = client.messages.create(
        model=MODEL, max_tokens=1024,
        system=system_prompt,
        messages=[{"role": "user", "content": json.dumps(payload, ensure_ascii=False)}]
    )
    return _parse_json_safe(response.content[0].text)


def summarize_messages(
    messages: list[dict],
    instructions: list[str] | None = None,
    username: str = 'guillaume'
) -> dict:
    items = []
    for msg in messages:
        try:
            item = analyze_single_mail_with_ai(msg, instructions or [], username)
        except Exception:
            item = {
                "display_title": msg.get("subject", "(Sans objet)"),
                "category": "autre", "priority": "moyenne",
                "reason": "Analyse indisponible", "suggested_action": "Lire",
                "short_summary": msg.get("bodyPreview", ""), "group_hints": [],
                "confidence": 0.0, "confidence_level": "basse", "needs_review": True,
                "needs_reply": False, "reply_urgency": "basse", "reply_reason": "",
                "response_type": "pas_de_reponse", "missing_fields": [],
                "suggested_reply_subject": "", "suggested_reply": "",
            }
        items.append({
            "display_title": item.get("display_title"),
            "from": msg.get("from", {}).get("emailAddress", {}).get("address", ""),
            "receivedDateTime": msg.get("receivedDateTime", ""),
            "category": item.get("category"), "priority": item.get("priority"),
            "reason": item.get("reason"), "suggested_action": item.get("suggested_action"),
            "short_summary": item.get("short_summary"), "mail_count": 1,
        })
    return {"count": len(items), "items": items}
