import os
import json
import sqlite3
import anthropic

DEFAULT_SIGNATURE = """Solairement,

Guillaume Perrin
06 49 43 09 17
www.couffrant-solar.fr"""

from app.config import ANTHROPIC_API_KEY, ANTHROPIC_MODEL_FAST, ANTHROPIC_MODEL_SMART
from app.config import ASSISTANT_DB_PATH

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
MODEL = ANTHROPIC_MODEL_FAST


MAIL_SCHEMA = {
    "type": "object",
    "properties": {
        "display_title": {"type": "string"},
        "category": {
            "type": "string",
            "enum": [
                "raccordement", "consuel", "chantier", "commercial",
                "financier", "fournisseur", "reunion", "securite",
                "interne", "notification", "autre",
            ],
        },
        "priority": {"type": "string", "enum": ["haute", "moyenne", "basse"]},
        "reason": {"type": "string"},
        "suggested_action": {"type": "string"},
        "short_summary": {"type": "string"},
        "group_hints": {"type": "array", "items": {"type": "string"}},
        "confidence": {"type": "number"},
        "confidence_level": {"type": "string", "enum": ["haute", "moyenne", "basse"]},
        "needs_review": {"type": "boolean"},
        "needs_reply": {"type": "boolean"},
        "reply_urgency": {"type": "string", "enum": ["haute", "moyenne", "basse"]},
        "reply_reason": {"type": "string"},
        "response_type": {
            "type": "string",
            "enum": [
                "oui_non", "planification", "demande_info", "demande_document",
                "accuse_reception", "relance", "pas_de_reponse", "autre",
            ],
        },
        "missing_fields": {"type": "array", "items": {"type": "string"}},
        "suggested_reply_subject": {"type": "string"},
        "suggested_reply": {"type": "string"},
    },
    "required": [
        "display_title", "category", "priority", "reason", "suggested_action",
        "short_summary", "group_hints", "confidence", "confidence_level",
        "needs_review", "needs_reply", "reply_urgency", "reply_reason",
        "response_type", "missing_fields", "suggested_reply_subject", "suggested_reply",
    ],
    "additionalProperties": False,
}


def get_learning_examples(category: str, limit: int = 3) -> list[dict]:
    conn = sqlite3.connect(ASSISTANT_DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("""
        SELECT mail_subject, mail_from, mail_body_preview, category, ai_reply, final_reply
        FROM reply_learning_memory
        WHERE category = ?
        ORDER BY id DESC
        LIMIT ?
    """, (category, limit))
    rows = [dict(row) for row in c.fetchall()]
    conn.close()
    return rows


def build_learning_text(examples: list[dict]) -> str:
    if not examples:
        return "Aucun exemple utilisateur pertinent disponible."
    blocks = []
    for i, ex in enumerate(examples, start=1):
        blocks.append(f"""Exemple {i}
Sujet : {ex.get('mail_subject', '')}
Expéditeur : {ex.get('mail_from', '')}
Contenu : {ex.get('mail_body_preview', '')}

Réponse IA initiale :
{ex.get('ai_reply', '')}

Réponse finale corrigée par l'utilisateur :
{ex.get('final_reply', '')}
""")
    return "\n\n".join(blocks)


def detect_hint_category(message: dict) -> str:
    subject = (message.get("subject") or "").lower()
    body = (message.get("bodyPreview") or "").lower()
    sender = (
        message.get("from", {})
        .get("emailAddress", {})
        .get("address", "")
        .lower()
    )
    full_text = f"{subject} {body} {sender}"

    if "enedis" in full_text or "engie" in full_text or "consuel" in full_text:
        return "raccordement"
    if "devis" in full_text or "offre" in full_text or "commercial" in full_text:
        return "commercial"
    if "rdv" in full_text or "réunion" in full_text or "reunion" in full_text:
        return "reunion"
    if "fournisseur" in full_text or "kstar" in full_text:
        return "fournisseur"
    return "autre"


def get_odoo_context(sender_email: str) -> dict:
    try:
        from app.connectors.odoo_connector import perform_odoo_action

        partner = perform_odoo_action(
            action="get_partner_by_email",
            params={"email": sender_email}
        )

        if not partner.get("result"):
            return {"client_trouve": False}

        p = partner["result"]
        partner_id = p["id"]

        projects = perform_odoo_action(
            action="get_projects_by_partner",
            params={"partner_id": partner_id}
        )

        return {
            "client_trouve": True,
            "client_nom": p.get("name"),
            "client_email": p.get("email"),
            "client_telephone": p.get("phone"),
            "client_ville": p.get("city"),
            "chantiers": projects.get("result", []),
        }

    except Exception as e:
        return {"client_trouve": False, "erreur": str(e)}


def analyze_single_mail_with_ai(message: dict, instructions: list[str] | None = None) -> dict:
    instructions = instructions or []

    sender_email = (
        message.get("from", {})
        .get("emailAddress", {})
        .get("address", "Expéditeur inconnu")
    )

    odoo_context = get_odoo_context(sender_email)

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

    hint_category = detect_hint_category(message)
    learning_examples = get_learning_examples(hint_category, limit=3)
    learning_text = build_learning_text(learning_examples)

    style_profile = ""
    try:
        conn_profile = sqlite3.connect(ASSISTANT_DB_PATH)
        c_profile = conn_profile.cursor()
        c_profile.execute("SELECT content FROM aria_profile WHERE profile_type = 'style' ORDER BY id DESC LIMIT 1")
        row = c_profile.fetchone()
        if row:
            style_profile = row[0]
        conn_profile.close()
    except Exception:
        pass

    system_instructions = f"""
Tu es Aria, l'assistante stratégique et opérationnelle de Couffrant Solar.

Analyse un seul mail et retourne uniquement un JSON strict conforme au schéma.

Ta mission :
- comprendre rapidement le besoin réel
- qualifier le mail correctement
- détecter s'il faut répondre
- proposer une réponse directement exploitable
- aider Guillaume à gagner du temps et à décider vite

Règles absolues :
- Tu proposes toujours, Guillaume décide toujours
- Tu n'exécutes aucune action sans validation explicite de Guillaume
- Ne jamais inventer une information absente du mail ou du contexte Odoo

Contexte client Odoo :
- Si odoo_context.client_trouve = true, utilise les données pour personnaliser l'analyse et la réponse
- Mentionne le nom du client et le chantier concerné si disponibles
- Si plusieurs chantiers existent, identifie lequel est concerné par le mail
- Si client_trouve = false, traite le mail sans données CRM

Profil de style de Guillaume :
{style_profile[:1500] if style_profile else "Profil non encore chargé — écrire de façon directe et concise"}

Personnalité :
- professionnelle, directe, claire, fiable, pragmatique, orientée solution
- avec une pointe d'humour subtil uniquement si le contexte s'y prête
- jamais sur un sujet sensible, conflictuel, financier ou litige

Règles de communication :
- pas de blabla inutile
- réponses concrètes, naturelles et directement exploitables
- phrases simples, fluides et professionnelles
- ne jamais ajouter de signature dans suggested_reply
- écrire comme Guillaume pourrait répondre : naturel, direct, efficace

Règles métier :
- raccordement / Enedis / Engie / Consuel = souvent priorité haute
- notifications marketing, newsletters = notification, priorité basse
- si tu hésites, choisis "autre"

Consignes utilisateur :
{json.dumps(instructions, ensure_ascii=False)}

Exemples de corrections passées à imiter si pertinents :
{learning_text}

Si aucune réponse n'est nécessaire :
- needs_reply = false
- reply_urgency = "basse"
- reply_reason = ""
- response_type = "pas_de_reponse"
- missing_fields = []
- suggested_reply_subject = ""
- suggested_reply = ""
""".strip()

    response = client.messages.create(
        model=MODEL,
        max_tokens=1024,
        system=system_instructions,
        messages=[
            {
                "role": "user",
                "content": json.dumps(payload, ensure_ascii=False)
            }
        ]
    )

    return json.loads(response.content[0].text)


def summarize_messages(messages: list[dict], instructions: list[str] | None = None) -> dict:
    items = []

    for msg in messages:
        try:
            item = analyze_single_mail_with_ai(msg, instructions or [])
        except Exception:
            item = {
                "display_title": msg.get("subject", "(Sans objet)"),
                "category": "autre",
                "priority": "moyenne",
                "reason": "Analyse indisponible",
                "suggested_action": "Lire",
                "short_summary": msg.get("bodyPreview", ""),
                "group_hints": [],
                "confidence": 0.0,
                "confidence_level": "basse",
                "needs_review": True,
                "needs_reply": False,
                "reply_urgency": "basse",
                "reply_reason": "",
                "response_type": "pas_de_reponse",
                "missing_fields": [],
                "suggested_reply_subject": "",
                "suggested_reply": "",
            }

        items.append({
            "display_title": item.get("display_title"),
            "from": (
                msg.get("from", {})
                .get("emailAddress", {})
                .get("address", "Expéditeur inconnu")
            ),
            "receivedDateTime": msg.get("receivedDateTime", ""),
            "category": item.get("category"),
            "priority": item.get("priority"),
            "reason": item.get("reason"),
            "suggested_action": item.get("suggested_action"),
            "short_summary": item.get("short_summary"),
            "mail_count": 1,
        })

    return {
        "count": len(items),
        "items": items,
    }