from app.mail_config import (
    LOW_PRIORITY_DOMAINS,
    INTERNAL_DOMAINS,
    GRID_KEYWORDS,
    MEETING_KEYWORDS,
)


def contains_any(text: str, keywords: list[str]) -> bool:
    text = (text or "").lower()
    return any(keyword.lower() in text for keyword in keywords)


def domain_matches(sender: str, domains: list[str]) -> bool:
    sender = (sender or "").lower()
    return any(domain in sender for domain in domains)


def analyze_single_mail(message: dict) -> dict:
    subject = message.get("subject") or "(Sans objet)"
    sender = (
        message.get("from", {})
        .get("emailAddress", {})
        .get("address", "Expéditeur inconnu")
    )
    body_preview = (message.get("bodyPreview") or "").strip()
    full_text = f"{subject} {body_preview}".lower()

    category = "autre"
    priority = "moyenne"
    reason = "Mail à qualifier."
    suggested_action = "Lire et qualifier"

    # =====================
    # LOGIQUE EXISTANTE
    # =====================

    if domain_matches(sender, LOW_PRIORITY_DOMAINS):
        category = "notification"
        priority = "basse"
        reason = "Notification ou communication peu prioritaire."
        suggested_action = "Classer ou ignorer"

    elif contains_any(full_text, GRID_KEYWORDS):
        category = "raccordement"
        priority = "haute"
        reason = "Sujet raccordement ENEDIS / Consuel détecté."
        suggested_action = "Analyser et suivre"

    elif contains_any(full_text, MEETING_KEYWORDS):
        category = "reunion"
        priority = "moyenne"
        reason = "Invitation ou sujet de réunion détecté."
        suggested_action = "Ajouter au calendrier"

    elif domain_matches(sender, INTERNAL_DOMAINS):
        category = "interne"
        priority = "moyenne"
        reason = "Mail interne détecté."
        suggested_action = "Relire si suivi nécessaire"

    # =====================
    # NOUVELLE LOGIQUE REPONSE
    # =====================

    needs_reply = False
    reply_urgency = "faible"
    reply_reason = ""
    suggested_reply_subject = f"Re: {subject}"
    suggested_reply = ""

    # Détection simple améliorée
    if (
        "?" in full_text
        or "merci de" in full_text
        or "pouvez-vous" in full_text
        or "peux-tu" in full_text
    ) and category not in ["notification"]:

        needs_reply = True
        reply_urgency = "haute" if priority == "haute" else "moyenne"
        reply_reason = "Le mail contient une demande ou une question."

        # éviter newsletters / marketing
        if "rt connecting" in full_text or "newsletter" in full_text:
            needs_reply = False

        # Réponse simple générique
        if needs_reply:
                suggested_reply = (
                "Bonjour,\n\n"
                "Nous avons bien pris en compte votre message et revenons vers vous rapidement avec les éléments nécessaires.\n\n"
                "Solairement,"
            )

    # Cas raccordement (plus spécifique)
    if category == "raccordement":
        needs_reply = True
        reply_urgency = "haute"
        reply_reason = "Sujet raccordement nécessitant un suivi."

        suggested_reply = (
            "Bonjour,\n\n"
            "Nous avons bien pris en compte votre demande concernant le raccordement. "
            "Nous revenons vers vous dès que nous avons les éléments ou le retour nécessaire.\n\n"
            "Solairement,"
        )

    return {
        "display_title": subject,
        "category": category,
        "priority": priority,
        "reason": reason,
        "suggested_action": suggested_action,
        "short_summary": body_preview[:180] + ("..." if len(body_preview) > 180 else ""),

        # NOUVEAUX CHAMPS
        "needs_reply": needs_reply,
        "reply_urgency": reply_urgency,
        "reply_reason": reply_reason,
        "suggested_reply_subject": suggested_reply_subject,
        "suggested_reply": suggested_reply,
    }