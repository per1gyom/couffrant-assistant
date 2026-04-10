"""
Seeding initial des règles d'un tenant.

Au lieu de hardcoder les règles métier dans rule_engine.py et ai_client.py,
on les insère dans aria_rules au premier démarrage avec une confidence basse.
Raya peut ensuite les modifier, les renforcer ou les supprimer naturellement.

Profils disponibles :
    pv_french      — Couffrant Solar (photovoltaïque, France)
    event_planner  — Organisatrice événementielle (femme de Guillaume)
    generic        — Nouveau tenant sans métier spécifique
"""
from app.memory_rules import save_rule


# ─── PROFILS DE SEEDING ───

PROFILE_PV_FRENCH = {
    "categories_mail": [
        "raccordement", "consuel", "chantier", "commercial", "financier",
        "fournisseur", "reunion", "securite", "interne", "notification", "autre",
    ],
    "regroupement": [
        "catégorie raccordement = urgent",
        "catégorie consuel = urgent",
        "catégorie financier contenant 'relance', 'retard' = urgent",
        "catégorie financier = a_traiter",
        "catégorie notification = faible",
    ],
    "tri_mails": [
        "Mails contenant 'enedis', 'consuel', 'raccordement' → catégorie raccordement",
        "Mails contenant 'devis', 'offre', 'contrat' → catégorie commercial",
        "Mails contenant 'réunion', 'meeting' → catégorie reunion",
        "Mails contenant 'chantier', 'planning', 'installation' → catégorie chantier",
        "Mails contenant 'facture', 'paiement', 'échéance' → catégorie financier",
        "Mails contenant 'fournisseur', 'livraison', 'commande' → catégorie fournisseur",
    ],
    "memoire": [
        "synth_threshold:15",
        "keep_recent:5",
        "purge_days:90",
    ],
}

PROFILE_EVENT_PLANNER = {
    "categories_mail": [
        "client",        # mails de clients existants ou prospects
        "prestataire",   # traiteurs, lieux, DJ, fleuristes, photographes, etc.
        "lieu",          # mails liés à des lieux d'événements
        "logistique",    # transport, livraison, montage, démontage
        "commercial",    # devis, contrats, factures, acomptes
        "interne",       # collaborateurs, équipe
        "notification",  # confirmations automatiques, agendas
        "autre",
    ],
    "regroupement": [
        "catégorie commercial contenant 'urgent', 'relance', 'retard' = urgent",
        "catégorie client contenant 'urgent', 'asap', 'demain' = urgent",
        "catégorie lieu = a_traiter",
        "catégorie prestataire = a_traiter",
        "catégorie notification = faible",
    ],
    "tri_mails": [
        "Mails contenant 'devis', 'contrat', 'facture', 'acompte' → catégorie commercial",
        "Mails contenant 'traiteur', 'fleuriste', 'DJ', 'photographe', 'son', 'lumière' → catégorie prestataire",
        "Mails contenant 'salle', 'château', 'domaine', 'lieu', 'espace' → catégorie lieu",
        "Mails contenant 'transport', 'livraison', 'montage', 'démontage', 'installation' → catégorie logistique",
        "Mails contenant 'mariage', 'réception', 'événement', 'cérémonie' → catégorie client",
    ],
    "comportement": [
        "Quand je parle d'un événement, considère qu'il y a un client principal et plusieurs prestataires impliqués.",
        "La coordination de prestataires est au cœur du métier : dates, disponibilités et confirmations sont cruciales.",
        "Les délais sont souvent serrés en organisation événementielle — traite les relances sans réponse comme urgentes.",
    ],
    "memoire": [
        "synth_threshold:15",
        "keep_recent:5",
        "purge_days:90",
    ],
}

PROFILE_GENERIC = {
    "categories_mail": [
        "commercial", "financier", "interne", "notification", "autre",
    ],
    "memoire": [
        "synth_threshold:15",
        "keep_recent:5",
        "purge_days:90",
    ],
}

PROFILES = {
    "pv_french":     PROFILE_PV_FRENCH,
    "event_planner": PROFILE_EVENT_PLANNER,
    "generic":       PROFILE_GENERIC,
}


def seed_tenant(tenant_id: str, admin_username: str,
                profile: str = "pv_french") -> dict:
    """
    Insère les règles initiales d'un tenant dans aria_rules.
    Idempotent : si une règle identique existe déjà, elle est juste renforcée.

    Args:
        tenant_id     : identifiant du tenant
        admin_username: utilisateur principal (les règles sont scopées par username)
        profile       : 'pv_french', 'event_planner' ou 'generic'

    Returns:
        Dict compteur par catégorie : {"categories_mail": 8, "tri_mails": 5, ...}
    """
    if profile not in PROFILES:
        raise ValueError(f"Profil inconnu : '{profile}'. Disponibles : {list(PROFILES.keys())}")

    counts = {}
    for category, rules in PROFILES[profile].items():
        counts[category] = 0
        for rule_text in rules:
            try:
                save_rule(
                    category=category,
                    rule=rule_text,
                    source="seed",
                    confidence=0.5,       # Confidence basse — Raya peut les modifier
                    username=admin_username,
                    tenant_id=tenant_id,  # Scopé au tenant dès la création
                )
                counts[category] += 1
            except Exception as e:
                print(f"[seeding] Erreur [{category}] '{rule_text[:40]}': {e}")
    return counts


def is_tenant_seeded(username: str) -> bool:
    """Retourne True si le user a déjà au moins une règle avec source='seed'."""
    from app.database import get_pg_conn
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute(
            "SELECT COUNT(*) FROM aria_rules WHERE username = %s AND source = 'seed'",
            (username,)
        )
        return c.fetchone()[0] > 0
    finally:
        if conn: conn.close()
