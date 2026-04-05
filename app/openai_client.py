import os
import json
from openai import OpenAI

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
MODEL = os.getenv("OPENAI_MODEL", "gpt-5.4")

MAIL_SCHEMA = {
    "type": "object",
    "properties": {
        "display_title": {"type": "string"},
        "category": {
            "type": "string",
            "enum": [
                "raccordement",
                "consuel",
                "chantier",
                "commercial",
                "financier",
                "fournisseur",
                "reunion",
                "securite",
                "interne",
                "notification",
                "autre",
            ],
        },
        "priority": {
            "type": "string",
            "enum": ["haute", "moyenne", "basse"],
        },
        "reason": {"type": "string"},
        "suggested_action": {"type": "string"},
        "short_summary": {"type": "string"},
        "group_hints": {
            "type": "array",
            "items": {"type": "string"},
        },
        "confidence": {"type": "number"},
        "needs_review": {"type": "boolean"},

        "needs_reply": {"type": "boolean"},
        "reply_urgency": {
            "type": "string",
            "enum": ["haute", "moyenne", "basse"],
        },
        "reply_reason": {"type": "string"},
        "suggested_reply_subject": {"type": "string"},
        "suggested_reply": {"type": "string"},
    },
    "required": [
        "display_title",
        "category",
        "priority",
        "reason",
        "suggested_action",
        "short_summary",
        "group_hints",
        "confidence",
        "needs_review",
        "needs_reply",
        "reply_urgency",
        "reply_reason",
        "suggested_reply_subject",
        "suggested_reply",
    ],
    "additionalProperties": False,
}


def analyze_single_mail_with_ai(message: dict, instructions: list[str] | None = None) -> dict:
    instructions = instructions or []

    payload = {
        "subject": message.get("subject", ""),
        "from": (
            message.get("from", {})
            .get("emailAddress", {})
            .get("address", "Expéditeur inconnu")
        ),
        "receivedDateTime": message.get("receivedDateTime", ""),
        "bodyPreview": message.get("bodyPreview", ""),
    }

    system_instructions = f"""
Tu es l'Assistante métier de Couffrant Solar.

Analyse un seul mail et retourne uniquement un JSON strict conforme au schéma.

Objectifs :
- qualifier le mail
- déterminer s'il nécessite une réponse
- proposer une réponse courte si nécessaire

Règles métier :
- raccordement / Enedis / Engie / Consuel = souvent priorité haute
- notifications marketing, newsletters, jobs, publicité, promos = notification
- si tu hésites, choisis "autre"
- résumés propres, sans signature parasite
- style de réponse : simple, direct, professionnel
- signature obligatoire exactement sous cette forme :

Solairement,

Guillaume Perrin
06 49 43 09 17
www.couffrant-solar.fr
- ne jamais inventer d'information
- si une information manque, rester prudent
- si aucune réponse n'est nécessaire :
  - needs_reply = false
  - reply_urgency = "basse"
  - reply_reason = ""
  - suggested_reply_subject = ""
  - suggested_reply = ""

Consignes utilisateur :
{json.dumps(instructions, ensure_ascii=False)}
""".strip()

    response = client.responses.create(
        model=MODEL,
        instructions=system_instructions,
        input=json.dumps(payload, ensure_ascii=False),
        text={
            "format": {
                "type": "json_schema",
                "name": "single_mail_analysis",
                "schema": MAIL_SCHEMA,
                "strict": True,
            }
        },
    )

    return json.loads(response.output_text)