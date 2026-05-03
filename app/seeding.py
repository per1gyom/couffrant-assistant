"""
Seeding initial des regles d'un tenant.

Au lieu de hardcoder les regles metier dans rule_engine.py et ai_client.py,
on les insere dans aria_rules au premier demarrage avec une confidence basse.
Raya peut ensuite les modifier, les renforcer ou les supprimer naturellement.

Profils disponibles :
    pv_french      — Couffrant Solar (photovoltaique, France)
    event_planner  — Organisatrice evenementielle
    generic        — Nouveau tenant sans metier specifique
    artisan        — Artisan / BTP (plombier, electricien, menuisier...)
    immobilier     — Agent immobilier
    conseil        — Cabinet de conseil / expertise comptable
    commerce       — Commerce / retail
    medical        — Praticien de sante / cabinet medical
"""
from app.memory_rules import save_rule


# --- REGLES UX COMMUNES A TOUS LES PROFILS ---
# Ces regles codifient du bon sens UX, pas des preferences personnelles.
# Elles sont seedees pour tous les tenants, tous profils confondus.

COMMON_BEHAVIOR_RULES = [
    # C6 : corbeille = action directe, pas de confirmation
    "Mise a la corbeille (DELETE) = action directe sans confirmation. C'est recuperable.",
    # Confirmation uniquement pour les actions vraiment irreversibles
    "Confirmer uniquement les actions irreversibles : envoi mail, envoi Teams, creation evenement calendrier, deplacement fichier Drive, copie fichier Drive.",
    # Note : ancienne regle "Quand tu apprends plusieurs choses..."
    # retiree le 02/05/2026 — elle reinjectait des references aux tags
    # legacy [ACTION:LEARN] dans aria_rules, qui polluaient le prompt v2
    # via _load_user_preferences. La logique "une regle = une seule idee"
    # est portee par le tool remember_preference (raya_tools.py).
]


# --- PROFILS DE SEEDING ---

PROFILE_PV_FRENCH = {
    "categories_mail": [
        "raccordement", "consuel", "chantier", "commercial", "financier",
        "fournisseur", "reunion", "securite", "interne", "notification", "autre",
    ],
    "Regroupement": [
        "categorie raccordement = urgent",
        "categorie consuel = urgent",
        "categorie financier contenant 'relance', 'retard' = urgent",
        "categorie financier = a_traiter",
        "categorie notification = faible",
    ],
    "Tri mails": [
        "Mails contenant 'enedis', 'consuel', 'raccordement' -> categorie raccordement",
        "Mails contenant 'devis', 'offre', 'contrat' -> categorie commercial",
        "Mails contenant 'reunion', 'meeting' -> categorie reunion",
        "Mails contenant 'chantier', 'planning', 'installation' -> categorie chantier",
        "Mails contenant 'facture', 'paiement', 'echeance' -> categorie financier",
        "Mails contenant 'fournisseur', 'livraison', 'commande' -> categorie fournisseur",
    ],
    "Mémoire": [
        "synth_threshold:15",
        "keep_recent:5",
        "purge_days:90",
    ],
}

PROFILE_EVENT_PLANNER = {
    "categories_mail": [
        "client", "prestataire", "lieu", "logistique", "commercial", "interne",
        "notification", "autre",
    ],
    "Regroupement": [
        "categorie commercial contenant 'urgent', 'relance', 'retard' = urgent",
        "categorie client contenant 'urgent', 'asap', 'demain' = urgent",
        "categorie lieu = a_traiter",
        "categorie prestataire = a_traiter",
        "categorie notification = faible",
    ],
    "Tri mails": [
        "Mails contenant 'devis', 'contrat', 'facture', 'acompte' -> categorie commercial",
        "Mails contenant 'traiteur', 'fleuriste', 'DJ', 'photographe', 'son', 'lumiere' -> categorie prestataire",
        "Mails contenant 'salle', 'chateau', 'domaine', 'lieu', 'espace' -> categorie lieu",
        "Mails contenant 'transport', 'livraison', 'montage', 'installation' -> categorie logistique",
        "Mails contenant 'mariage', 'reception', 'evenement', 'ceremonie' -> categorie client",
    ],
    "Comportement": [
        "Quand je parle d'un evenement, il y a un client principal et plusieurs prestataires impliques.",
        "La coordination de prestataires est au coeur du metier : dates, disponibilites et confirmations sont cruciales.",
        "Les delais sont souvent serres : traite les relances sans reponse comme urgentes.",
    ],
    "Mémoire": [
        "synth_threshold:15",
        "keep_recent:5",
        "purge_days:90",
    ],
}

PROFILE_GENERIC = {
    "categories_mail": [
        "commercial", "financier", "interne", "notification", "autre",
    ],
    "Mémoire": [
        "synth_threshold:15",
        "keep_recent:5",
        "purge_days:90",
    ],
}

PROFILE_ARTISAN = {
    "categories_mail": [
        "chantier", "client", "fournisseur", "devis", "financier",
        "administratif", "notification", "autre",
    ],
    "Tri mails": [
        "Mails contenant 'chantier', 'travaux', 'intervention', 'planning' -> categorie chantier",
        "Mails contenant 'devis', 'estimation', 'prix' -> categorie devis",
        "Mails contenant 'facture', 'paiement', 'relance' -> categorie financier",
        "Mails contenant 'commande', 'livraison', 'materiel' -> categorie fournisseur",
    ],
    "Comportement": [
        "Le planning chantier est la priorite : interventions, rendez-vous clients, livraisons.",
        "Les devis en attente de reponse depuis plus de 7 jours meritent une relance.",
    ],
    "Mémoire": ["synth_threshold:15", "keep_recent:5", "purge_days:90"],
}

PROFILE_IMMOBILIER = {
    "categories_mail": [
        "mandat", "visite", "acquereur", "notaire", "financier",
        "marketing", "notification", "autre",
    ],
    "Tri mails": [
        "Mails contenant 'mandat', 'estimation', 'compromis' -> categorie mandat",
        "Mails contenant 'visite', 'rendez-vous', 'disponibilite' -> categorie visite",
        "Mails contenant 'notaire', 'acte', 'signature' -> categorie notaire",
        "Mails contenant 'pret', 'financement', 'banque' -> categorie financier",
        "Mails contenant 'annonce', 'photo', 'diffusion' -> categorie marketing",
    ],
    "Comportement": [
        "Les compromis et signatures chez le notaire sont des echeances critiques.",
        "Chaque bien a un vendeur et potentiellement plusieurs acquereurs a coordonner.",
    ],
    "Mémoire": ["synth_threshold:15", "keep_recent:5", "purge_days:90"],
}

PROFILE_CONSEIL = {
    "categories_mail": [
        "client", "mission", "livrable", "facturation", "recrutement",
        "interne", "notification", "autre",
    ],
    "Tri mails": [
        "Mails contenant 'mission', 'projet', 'proposition', 'offre' -> categorie mission",
        "Mails contenant 'rapport', 'livrable', 'presentation', 'audit' -> categorie livrable",
        "Mails contenant 'facture', 'honoraires', 'paiement' -> categorie facturation",
        "Mails contenant 'candidat', 'entretien', 'recrutement' -> categorie recrutement",
    ],
    "Comportement": [
        "Chaque mission a un client, un perimetre et des echeances de livrables.",
        "La facturation suit les jalons de mission — surveiller les retards de paiement.",
    ],
    "Mémoire": ["synth_threshold:15", "keep_recent:5", "purge_days:90"],
}

PROFILE_COMMERCE = {
    "categories_mail": [
        "commande", "fournisseur", "client", "logistique", "financier",
        "marketing", "notification", "autre",
    ],
    "Tri mails": [
        "Mails contenant 'commande', 'bon de commande', 'confirmation' -> categorie commande",
        "Mails contenant 'livraison', 'expedition', 'transporteur', 'stock' -> categorie logistique",
        "Mails contenant 'facture', 'paiement', 'avoir', 'relance' -> categorie financier",
        "Mails contenant 'promo', 'campagne', 'newsletter', 'soldes' -> categorie marketing",
    ],
    "Comportement": [
        "Les ruptures de stock et retards de livraison sont des alertes prioritaires.",
        "Les commandes clients en attente de traitement sont urgentes.",
    ],
    "Mémoire": ["synth_threshold:15", "keep_recent:5", "purge_days:90"],
}

PROFILE_MEDICAL = {
    "categories_mail": [
        "patient", "rendez_vous", "labo", "administratif", "confrere",
        "formation", "notification", "autre",
    ],
    "Tri mails": [
        "Mails contenant 'rendez-vous', 'consultation', 'annulation' -> categorie rendez_vous",
        "Mails contenant 'resultat', 'analyse', 'laboratoire', 'bilan' -> categorie labo",
        "Mails contenant 'CPAM', 'mutuelle', 'teletransmission', 'ordonnance' -> categorie administratif",
        "Mails contenant 'confrere', 'adressage', 'avis medical' -> categorie confrere",
    ],
    "Comportement": [
        "Les resultats de laboratoire urgents ou anormaux doivent etre signales immediatement.",
        "La confidentialite des donnees patients est absolue — jamais de nom dans les logs.",
    ],
    "Mémoire": ["synth_threshold:15", "keep_recent:5", "purge_days:90"],
}

PROFILES = {
    "pv_french":     PROFILE_PV_FRENCH,
    "event_planner": PROFILE_EVENT_PLANNER,
    "generic":       PROFILE_GENERIC,
    "artisan":       PROFILE_ARTISAN,
    "immobilier":    PROFILE_IMMOBILIER,
    "conseil":       PROFILE_CONSEIL,
    "commerce":      PROFILE_COMMERCE,
    "medical":       PROFILE_MEDICAL,
}


def seed_tenant(tenant_id: str, admin_username: str,
                profile: str = "pv_french") -> dict:
    """
    Insere les regles initiales d'un tenant dans aria_rules.
    Idempotent : si une regle identique existe deja, elle est juste renforcee.

    Seed aussi les regles UX communes (bon sens, valables pour tous).
    """
    if profile not in PROFILES:
        raise ValueError(f"Profil inconnu : '{profile}'. Disponibles : {list(PROFILES.keys())}")

    counts = {}

    # Regles UX communes en premier
    counts["Comportement"] = 0
    for rule_text in COMMON_BEHAVIOR_RULES:
        try:
            save_rule(
                category="Comportement",
                rule=rule_text,
                source="seed",
                confidence=0.8,  # Confidence plus haute : ce sont des garde-fous UX
                username=admin_username,
                tenant_id=tenant_id,
            )
            counts["Comportement"] += 1
        except Exception as e:
            print(f"[seeding] Erreur [Comportement] '{rule_text[:40]}': {e}")

    # Regles specifiques au profil
    for category, rules in PROFILES[profile].items():
        if category not in counts:
            counts[category] = 0
        for rule_text in rules:
            try:
                save_rule(
                    category=category,
                    rule=rule_text,
                    source="seed",
                    confidence=0.5,
                    username=admin_username,
                    tenant_id=tenant_id,
                )
                counts[category] += 1
            except Exception as e:
                print(f"[seeding] Erreur [{category}] '{rule_text[:40]}': {e}")

    return counts


def is_tenant_seeded(username: str, tenant_id: str = None) -> bool:
    """Retourne True si le user a deja au moins une regle avec source='seed'."""
    from app.database import get_pg_conn
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute(
            "SELECT COUNT(*) FROM aria_rules "
            "WHERE username = %s AND source = 'seed' "
            "AND (tenant_id = %s OR tenant_id IS NULL)",
            (username, tenant_id)
        )
        return c.fetchone()[0] > 0
    finally:
        if conn: conn.close()
