"""
Seeding initial des règles d'un tenant.

Au lieu de hardcoder les règles métier dans rule_engine.py et ai_client.py,
on les insère dans aria_rules au premier démarrage avec une confidence basse.
Raya peut ensuite les modifier, les renforcer ou les supprimer naturellement.

Pour un nouveau tenant non-PV, appeler :
    seed_tenant(tenant_id, username, profile='generic')
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
    "pv_french": PROFILE_PV_FRENCH,
    "generic": PROFILE_GENERIC,
}


def seed_tenant(tenant_id: str, admin_username: str, profile: str = "pv_french") -> dict:
    """
    Insère les règles initiales d'un tenant dans aria_rules.
    Idempotent : si une règle identique existe déjà, elle est juste renforcée.

    Args:
        tenant_id     : identifiant du tenant
        admin_username: utilisateur principal (les règles sont scopées par username)
        profile       : 'pv_french' ou 'generic'

    Returns:
        Dict compteur par catégorie : {"categories_mail": 11, "tri_mails": 6, ...}
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
                    confidence=0.5,   # Confidence basse — Raya peut les modifier
                    username=admin_username,
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
