import re


def analyze_single_mail(message: dict, username: str = 'guillaume') -> dict:
    """
    Analyseur de secours utilisé uniquement quand l'appel IA échoue.
    Utilise les règles Aria chargées depuis aria_rules pour classifier.
    Pas d'appel Claude — classification par correspondance de mots-clés.
    Confidence faible (0.3) : indique que l'analyse doit être revue.
    """
    subject = message.get("subject") or "(Sans objet)"
    sender = message.get("from", {}).get("emailAddress", {}).get("address", "")
    body_preview = (message.get("bodyPreview") or "").strip()
    full_text = f"{subject} {body_preview} {sender}".lower()

    category = "autre"
    priority = "moyenne"
    reason = "Mail à qualifier (analyse fallback)."

    # Chargement des règles depuis la base
    try:
        from app.memory_manager import get_rules_by_category, extract_keywords_from_rule
        urgence_rules = get_rules_by_category('urgence', username)
        tri_rules = get_rules_by_category('tri_mails', username)
    except Exception:
        urgence_rules = []
        tri_rules = []

    # Classification par règles de tri
    for rule in tri_rules:
        keywords = extract_keywords_from_rule(rule)
        if any(kw.lower() in full_text for kw in keywords):
            cat_match = re.search(r"catégorie\s+(\w+)", rule.lower())
            if cat_match:
                category = cat_match.group(1)
            prio_match = re.search(r"priorité\s+(haute|moyenne|basse)", rule.lower())
            if prio_match:
                priority = prio_match.group(1)
            reason = f"Règle appliquée : {rule[:80]}"
            break

    # Surcharge de priorité par les règles d'urgence
    for rule in urgence_rules:
        keywords = extract_keywords_from_rule(rule)
        if any(kw.lower() in full_text for kw in keywords):
            priority = "haute"
            reason = f"Urgence détectée : {rule[:80]}"
            break

    return {
        "display_title": subject,
        "category": category,
        "priority": priority,
        "reason": reason,
        "suggested_action": "Lire et qualifier",
        "short_summary": body_preview[:180] + ("..." if len(body_preview) > 180 else ""),
        "group_hints": [],
        "confidence": 0.3,
        "confidence_level": "basse",
        "needs_review": True,
        "response_type": "autre",
        "missing_fields": [],
        "needs_reply": False,
        "reply_urgency": "basse",
        "reply_reason": "",
        "suggested_reply_subject": f"Re: {subject}",
        "suggested_reply": "",
    }
