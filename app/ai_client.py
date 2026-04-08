import json
import re
import anthropic

from app.config import ANTHROPIC_API_KEY, ANTHROPIC_MODEL_FAST
from app.database import get_pg_conn

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
MODEL = ANTHROPIC_MODEL_FAST


def _parse_json_safe(text: str) -> dict:
    """Parse JSON robustement."""
    text = text.strip()
    text = re.sub(r'^```(?:json)?\s*', '', text, flags=re.MULTILINE)
    text = re.sub(r'\s*```$', '', text, flags=re.MULTILINE)
    return json.loads(text.strip())


def get_learning_examples(limit: int = 5) -> list[dict]:
    """Récupère les derniers exemples de correction (toutes catégories)."""
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            SELECT mail_subject, mail_from, mail_body_preview, category, ai_reply, final_reply
            FROM reply_learning_memory
            ORDER BY id DESC LIMIT %s
        """, (limit,))
        rows = c.fetchall()
        return [
            {"mail_subject": r[0], "mail_from": r[1], "mail_body_preview": r[2],
             "category": r[3], "ai_reply": r[4], "final_reply": r[5]}
            for r in rows
        ]
    except Exception:
        return []
    finally:
        if conn: conn.close()


def build_learning_text(examples: list[dict]) -> str:
    if not examples:
        return "Aucun exemple disponible."
    blocks = []
    for i, ex in enumerate(examples, 1):
        blocks.append(
            f"Exemple {i}\nSujet : {ex.get('mail_subject', '')}\n"
            f"Expéditeur : {ex.get('mail_from', '')}\n"
            f"Contenu : {ex.get('mail_body_preview', '')}\n"
            f"Réponse IA : {ex.get('ai_reply', '')}\n"
            f"Réponse corrigée : {ex.get('final_reply', '')}"
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
        return {
            "client_trouve": True,
            "client_nom": p.get("name"),
            "client_email": p.get("email"),
            "client_telephone": p.get("phone"),
            "client_ville": p.get("city"),
            "chantiers": projects.get("result", []),
        }
    except Exception:
        return {"client_trouve": False}


def get_style_profile(username: str = 'guillaume') -> str:
    """Charge le profil de style rédactionnel d'un utilisateur."""
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


def analyze_single_mail_with_ai(
    message: dict,
    instructions: list[str] | None = None,
    username: str = 'guillaume'
) -> dict:
    """
    Analyse un mail avec Claude.
    Les règles d'urgence, de tri et de style sont chargées dynamiquement
    depuis aria_rules — elles évoluent avec les apprentissages d'Aria.
    Aucune règle métier n'est codée en dur ici.
    """
    instructions = instructions or []

    sender_email = message.get("from", {}).get("emailAddress", {}).get("address", "Expéditeur inconnu")
    odoo_context = get_odoo_context(sender_email)
    style_profile = get_style_profile(username)

    # Chargement dynamique des règles Aria pour ce mail
    aria_rules_text = ""
    try:
        from app.memory_manager import get_rules_as_text
        aria_rules_text = get_rules_as_text(['tri_mails', 'urgence', 'style_reponse'], username)
    except Exception as e:
        print(f"[ai_client] Impossible de charger les règles: {e}")

    learning_examples = get_learning_examples(limit=4)
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

    system_instructions = f"""Tu es Aria, l'assistante de Couffrant Solar.

Analyse ce mail et retourne UNIQUEMENT un objet JSON valide, sans texte avant ou après, sans bloc markdown.

Champs requis (tous obligatoires) :
- display_title : string
- category : "raccordement"|"consuel"|"chantier"|"commercial"|"financier"|"fournisseur"|"reunion"|"securite"|"interne"|"notification"|"autre"
- priority : "haute"|"moyenne"|"basse"
- reason : string
- suggested_action : string
- short_summary : string
- group_hints : array of strings
- confidence : number between 0 and 1
- confidence_level : "haute"|"moyenne"|"basse"
- needs_review : boolean
- needs_reply : boolean
- reply_urgency : "haute"|"moyenne"|"basse"
- reply_reason : string
- response_type : "oui_non"|"planification"|"demande_info"|"demande_document"|"accuse_reception"|"relance"|"pas_de_reponse"|"autre"
- missing_fields : array of strings
- suggested_reply_subject : string
- suggested_reply : string (sans signature)

Garde-fous de sécurité (immuables) :
- Retourner UNIQUEMENT du JSON valide
- Ne jamais inventer d'information absente du mail
- Ne jamais mettre de signature dans suggested_reply

Règles d'Aria pour la classification de ce mail (apprises, évolutives — à appliquer en priorité) :
{aria_rules_text if aria_rules_text else "Pas de règles spécifiques encore — utilise ton jugement."}

Profil rédactionnel de l'utilisateur :
{style_profile[:600] if style_profile else "Style direct et concis."}

Contexte Odoo :
{json.dumps(odoo_context, ensure_ascii=False)}

Consignes utilisateur :
{json.dumps(instructions, ensure_ascii=False)}

Exemples de corrections passées :
{learning_text}
""".strip()

    response = client.messages.create(
        model=MODEL,
        max_tokens=1024,
        system=system_instructions,
        messages=[{"role": "user", "content": json.dumps(payload, ensure_ascii=False)}]
    )
    return _parse_json_safe(response.content[0].text)


def summarize_messages(messages: list[dict], instructions: list[str] | None = None, username: str = 'guillaume') -> dict:
    items = []
    for msg in messages:
        try:
            item = analyze_single_mail_with_ai(msg, instructions or [], username)
        except Exception:
            item = {
                "display_title": msg.get("subject", "(Sans objet)"),
                "category": "autre", "priority": "moyenne",
                "reason": "Analyse indisponible", "suggested_action": "Lire",
                "short_summary": msg.get("bodyPreview", ""),
                "group_hints": [], "confidence": 0.0, "confidence_level": "basse",
                "needs_review": True, "needs_reply": False, "reply_urgency": "basse",
                "reply_reason": "", "response_type": "pas_de_reponse",
                "missing_fields": [], "suggested_reply_subject": "", "suggested_reply": "",
            }
        items.append({
            "display_title": item.get("display_title"),
            "from": msg.get("from", {}).get("emailAddress", {}).get("address", "Expéditeur inconnu"),
            "receivedDateTime": msg.get("receivedDateTime", ""),
            "category": item.get("category"), "priority": item.get("priority"),
            "reason": item.get("reason"), "suggested_action": item.get("suggested_action"),
            "short_summary": item.get("short_summary"), "mail_count": 1,
        })
    return {"count": len(items), "items": items}
