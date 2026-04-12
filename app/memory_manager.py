"""
DÉPRÉCIÉ — ce fichier n'est plus utilisé.
memory_loader.py importe désormais directement depuis les modules source.
Conservé uniquement pour éviter une erreur si un import résiduel existe.
À supprimer définitivement lors du nettoyage Phase 6.
"""
from app.memory_rules import (  # noqa
    get_aria_rules, save_rule, delete_rule, seed_default_rules,
)
from app.rule_engine import (  # noqa
    get_rules_by_category, get_antispam_keywords,
    get_memoire_param, get_contacts_keywords,
)
from app.memory_contacts import (  # noqa
    get_contact_card, rebuild_contacts, get_all_contact_cards,
)
from app.memory_style import (  # noqa
    get_style_examples, save_style_example, learn_from_correction,
    load_sent_mails_to_style, save_reply_learning,
)
from app.memory_synthesis import (  # noqa
    get_hot_summary, get_aria_insights, save_insight,
    synthesize_session, rebuild_hot_summary, purge_old_mails,
)
