"""
Analyseur de fallback — utilisé quand Claude est indisponible.

Les règles de classification viennent de aria_rules via rule_engine.
Pas d'appel Claude — classification rapide par mots-clés extraits des règles.
Toute la logique métier est pilotable par Aria via LEARN/FORGET.
"""

from app.rule_engine import (
    get_antispam_keywords,
    extract_category_keywords,
    get_urgency_keywords,
    get_internal_domains,
    get_rules_by_category,
)


def analyze_single_mail(message: dict, username: str = 'guillaume') -> dict:
    """
    Classification rapide sans Claude — pilotée par les règles de l'utilisateur.
    Utilisée en fallback ou quand Claude est indisponible.
    """
    subject = message.get("subject") or "(Sans objet)"
    sender = message.get("from", {}).get("emailAddress", {}).get("address", "Expéditeur inconnu")
    body_preview = (message.get("bodyPreview") or "").strip()
    full_text = f"{subject} {body_preview} {sender}".lower()

    # ── Chargement des règles Aria ──
    spam_kw       = get_antispam_keywords(username)
    urgency_kw    = get_urgency_keywords(username)
    internal_doms = get_internal_domains(username)

    # Mots-clés par catégorie — extraits des règles
    # Fallbacks si la base est vide (premier démarrage avant seed)
    raccordement_kw = extract_category_keywords(username, "raccordement") or \
        ["enedis", "engie", "consuel", "raccordement", "injection", "tgbt", "point de livraison"]
    financier_kw = extract_category_keywords(username, "financier") or \
        ["facture", "paiement", "échéance", "relance", "avoir", "règlement"]
    chantier_kw = extract_category_keywords(username, "chantier") or \
        ["chantier", "planning", "intervention", "installation", "pose", "mise en service", "travaux"]
    commercial_kw = extract_category_keywords(username, "commercial") or \
        ["devis", "offre", "proposition", "tarif", "prix", "contrat", "signature"]
    reunion_kw = extract_category_keywords(username, "reunion") or \
        ["réunion", "meeting", "visioconférence", "calendar", "teams.microsoft.com"]

    # ── Classification ──
    category = "autre"
    priority = "moyenne"
    reason = "Mail à qualifier."
    suggested_action = "Lire et qualifier"

    if any(kw in full_text for kw in spam_kw):
        category = "notification"
        priority = "basse"
        reason = "Notification ou communication peu prioritaire."
        suggested_action = "Classer ou ignorer"

    elif any(kw in full_text for kw in raccordement_kw):
        category = "raccordement"
        priority = "haute"
        reason = "Sujet raccordement détecté."
        suggested_action = "Analyser et suivre"

    elif any(kw in full_text for kw in financier_kw):
        category = "financier"
        priority = "haute" if any(kw in full_text for kw in ["relance", "retard", "impéé", "mise en demeure"]) else "moyenne"
        reason = "Sujet financier détecté."
        suggested_action = "Vérifier et traiter"

    elif any(kw in full_text for kw in chantier_kw):
        category = "chantier"
        priority = "moyenne"
        reason = "Sujet chantier détecté."
        suggested_action = "Suivre le chantier"

    elif any(kw in full_text for kw in commercial_kw):
        category = "commercial"
        priority = "moyenne"
        reason = "Sujet commercial détecté."
        suggested_action = "Traiter la demande"

    elif any(kw in full_text for kw in reunion_kw):
        category = "reunion"
        priority = "moyenne"
        reason = "Invitation ou sujet de réunion."
        suggested_action = "Ajouter au calendrier"

    elif any(domain in sender.lower() for domain in internal_doms):
        category = "interne"
        priority = "moyenne"
        reason = "Mail interne."
        suggested_action = "Relire si suivi nécessaire"

    # ── Mots-clés d'urgence ──
    if priority != "basse" and any(kw in full_text for kw in urgency_kw):
        priority = "haute"
        reason += " Urgence détectée."

    # ── Réponse nécessaire ? ──
    needs_reply = False
    reply_urgency = "basse"
    reply_reason = ""
    suggested_reply = ""

    if category not in ["notification"] and (
        "?" in full_text
        or "merci de" in full_text
        or "pouvez-vous" in full_text
        or "peux-tu" in full_text
    ):
        needs_reply = True
        reply_urgency = "haute" if priority == "haute" else "moyenne"
        reply_reason = "Le mail contient une demande ou une question."

        # Réponse type issue des règles de style
        style_rules = get_rules_by_category(username, "style_reponse")
        opening = "Bonjour,"
        closing = "Solairement,"
        for r in style_rules:
            r_l = r.lower()
            if "commencer" in r_l and ":" in r:
                opening = r.split(":", 1)[-1].strip().strip("'")
            if "terminer" in r_l and ":" in r:
                closing = r.split(":", 1)[-1].strip().strip("'")

        suggested_reply = (
            f"{opening}\n\n"
            "Nous avons bien pris en compte votre message et revenons vers vous rapidement.\n\n"
            f"{closing}"
        )

    return {
        "display_title": subject,
        "category": category,
        "priority": priority,
        "reason": reason,
        "suggested_action": suggested_action,
        "short_summary": body_preview[:180] + ("..." if len(body_preview) > 180 else ""),
        "group_hints": [],
        "confidence": 0.4,
        "confidence_level": "basse",
        "needs_review": True,
        "response_type": "autre",
        "missing_fields": [],
        "needs_reply": needs_reply,
        "reply_urgency": reply_urgency,
        "reply_reason": reply_reason,
        "suggested_reply_subject": f"Re: {subject}",
        "suggested_reply": suggested_reply,
    }
