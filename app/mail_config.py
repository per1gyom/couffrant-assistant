"""
DEPRECATEÉ — ce fichier n'est plus utilisé.

Les règles métier (mots-clés, domaines, catégories) sont maintenant
stockées dans aria_rules en base de données et chargées dynamiquement
via app/rule_engine.py.

Aria peut les faire évoluer via LEARN/FORGET.
Plus aucun fichier du projet n'importe depuis mail_config.

Gardé pour référence historique uniquement.
"""

# Anciens contenus — plus utilisés
LOW_PRIORITY_DOMAINS = ["linkedin.com", "studeria.fr", "mailchimp", "brevo",
                         "sendinblue", "newsletter"]
SECURITY_DOMAINS     = ["accounts.google.com", "google.com", "microsoft.com",
                         "microsoftonline.com"]
INTERNAL_DOMAINS     = ["couffrant-solar.fr"]
GRID_KEYWORDS        = ["enedis", "engie", "raccordement", "consuel",
                         "injection", "tgbt", "point de livraison"]
MEETING_KEYWORDS     = ["teams.microsoft.com", "réunion", "meeting",
                         "visioconférence", "calendar", "invitation", "webinar"]
URGENT_KEYWORDS      = ["urgent", "immédiat", "asap", "retard",
                         "bloqué", "blocage", "alerte", "sécurité"]
