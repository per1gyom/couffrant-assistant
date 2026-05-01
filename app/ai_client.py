"""
Analyse des mails entrants par Claude.

Principes :
- Catégories de mail : lues depuis aria_rules (catégorie 'categories_mail') — Raya les évole librement
- Prompt conditionnel : Odoo/style/exemples injectés uniquement si pertinents — économie 20-30% tokens
- Zéro règle métier codée en dur

Garde-fous immuables :
- Retourner uniquement du JSON valide
- Ne jamais inventer d'informations absentes du mail
- Ne jamais inclure de signature dans suggested_reply
"""

import json
import re

from app.llm_client import llm_complete
from app.database import get_pg_conn
from app.rule_engine import get_rules_as_text, get_rules_by_category
# Fix imports orphelins :
#   - 21/04/2026 nuit : ajout de _DEFAULT_CATEGORIES, build_learning_text,
#     _parse_json_safe (utilises sans etre importes -> NameError silencieux).
#   - 01/05/2026 : ajout de get_odoo_context et get_style_profile (meme
#     bug, oubli du fix precedent). Sans ces imports, analyze_single_mail_with_ai
#     levait NameError a chaque appel et tous les mails arrivaient en
#     analysis_status='fallback' (sans analyse IA, sans alerte d urgence).
from app.ai_prompts import (
    _DEFAULT_CATEGORIES, build_learning_text, _parse_json_safe,
    get_odoo_context, get_style_profile,
)


def get_mail_categories(username: str) -> list[str]:
    """
    Charge les catégories de mail depuis aria_rules (catégorie 'Tri mails').
    Raya les fait évoluer via [ACTION:LEARN:Tri mails|nouvelle_categorie].
    Si vide, retourne les catégories par défaut et les seed en base.
    """
    # Phase 3 : lecture dans la categorie canonique 'Tri mails' en priorite,
    # fallback sur l'ancienne 'categories_mail' pour retro-compat.
    rules = get_rules_by_category(username, 'Tri mails')
    if not rules:
        rules = get_rules_by_category(username, 'categories_mail')
    if rules:
        return [r.strip().lower() for r in rules if r.strip()]
    # Première utilisation : seed en base pour que Raya puisse les modifier
    _seed_default_categories(username)
    return _DEFAULT_CATEGORIES


def _seed_default_categories(username: str):
    """Insère les catégories par défaut en base (une seule fois au premier démarrage)."""
    try:
        from app.memory_rules import save_rule
        for cat in _DEFAULT_CATEGORIES:
            # Phase 3 : 'Tri mails' (forme canonique) au lieu de 'categories_mail'
            save_rule('Tri mails', cat, 'seed', 0.9, username)
    except Exception:
        pass


# ─── CONTEXTE ET PROFIL ───

def get_learning_examples(category: str, username: str = None, limit: int = 3,
                          tenant_id: str = None) -> list[dict]:
    """Exemples de corrections passées pour le few-shot learning."""
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            SELECT mail_subject, mail_from, mail_body_preview, category, ai_reply, final_reply
            FROM reply_learning_memory
            WHERE category = %s AND username = %s
              AND (tenant_id = %s OR tenant_id IS NULL)
            ORDER BY id DESC LIMIT %s
        """, (category, username, tenant_id, limit))
        return [{"mail_subject": r[0], "mail_from": r[1], "mail_body_preview": r[2],
                 "category": r[3], "ai_reply": r[4], "final_reply": r[5]} for r in c.fetchall()]
    except Exception:
        return []
    finally:
        if conn: conn.close()


def _get_hint_category(full_text: str, username: str) -> str:
    from app.rule_engine import extract_category_keywords
    # Catégories à tester : toutes sauf 'autre', 'notification', 'interne'
    categories = get_mail_categories(username)
    for cat in categories:
        if cat in ('autre', 'notification', 'interne', 'securite'):
            continue
        kws = extract_category_keywords(username, cat)
        if not kws:
            # Fallbacks légers uniquement pour les catégories techniques
            fallbacks = {
                "raccordement": ["enedis", "consuel", "raccordement"],
                "commercial":   ["devis", "offre", "contrat"],
                "reunion":      ["réunion", "meeting", "teams.microsoft"],
                "chantier":     ["chantier", "planning", "installation"],
                "financier":    ["facture", "paiement", "échéance"],
                "fournisseur":  ["fournisseur", "livraison", "commande"],
            }
            kws = fallbacks.get(cat, [])
        if any(kw in full_text for kw in kws):
            return cat
    return "autre"


# ─── ANALYSE PRINCIPALE ───

# Mots-clés indiquant qu'une réponse est probablement attendue
_REPLY_HINTS = ["?", "merci de", "pouvez-vous", "peux-tu", "svp", "s'il vous plaît",
                "pourriez", "auriez", "avez-vous", "avez vous", "demande"]


def analyze_single_mail_with_ai(
    message: dict,
    instructions: list[str] | None = None,
    username: str = None
) -> dict:
    instructions = instructions or []
    sender_email = message.get("from", {}).get("emailAddress", {}).get("address", "Expéditeur inconnu")

    full_lower = (
        f"{message.get('subject', '')} "
        f"{message.get('bodyPreview', '')} "
        f"{sender_email}"
    ).lower()

    # ─ Catégories dynamiques (depuis DB, évolutives par Raya)
    mail_categories = get_mail_categories(username)
    categories_str = ", ".join(mail_categories)

    # ─ Règles métier
    rules_text = get_rules_as_text(username, ["tri_mails", "urgence", "style_reponse"])

    # ─ Détection de catégorie pour le few-shot
    hint_cat = _get_hint_category(full_lower, username)

    # ─ Odoo : uniquement si le client est trouvé (pas de requête inutile)
    odoo_context = get_odoo_context(sender_email)
    include_odoo = odoo_context.get("client_trouve", False)

    # ─ Profil de style : uniquement si le mail semble nécessiter une réponse
    needs_reply_hint = any(w in full_lower for w in _REPLY_HINTS)
    style_profile = get_style_profile(username) if needs_reply_hint else ""

    # ─ Exemples de corrections : uniquement si catégorie clairement détectée
    learning_examples = get_learning_examples(hint_cat, username) if hint_cat != "autre" else []
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
    }

    rules_section = (
        f"=== RÈGLES (apprises, évolutives) ===\n{rules_text}\n"
        if rules_text else
        "Pas encore de règles. Utilise le bon sens métier photovoltaïque.\n"
    )

    # Blocs conditionnels
    odoo_block  = f"\nContexte Odoo :\n{json.dumps(odoo_context, ensure_ascii=False)}" if include_odoo else ""
    style_block = f"\nProfil de style :\n{style_profile[:600]}" if style_profile else ""
    examples_block = f"\nExemples de corrections passées :\n{learning_text}" if learning_text else ""
    instructions_block = f"\nConsignes : {json.dumps(instructions, ensure_ascii=False)}" if instructions else ""

    system_prompt = f"""Tu es Raya, l'assistante de Couffrant Solar.
Analyse ce mail et retourne UNIQUEMENT un objet JSON valide, sans texte avant ou après, sans bloc markdown.

{rules_section}

Garde-fous immuables :
- Retourner UNIQUEMENT du JSON valide
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

Catégories valides : {categories_str}{odoo_block}{style_block}{examples_block}{instructions_block}"""

    result = llm_complete(
        messages=[{"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
        model_tier="fast",
        max_tokens=1024,
        system=system_prompt,
    )
    return _parse_json_safe(result["text"])


def summarize_messages(
    messages: list[dict],
    instructions: list[str] | None = None,
    username: str = None
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
