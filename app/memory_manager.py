"""
Gestionnaire de mémoire Raya — module de compatibilité.
Réexporte tout depuis les sous-modules spécialisés.
Aucun autre fichier n'a besoin d'être modifié.
"""

from app.memory_rules import (
    get_aria_rules, save_rule, delete_rule,
    get_rules_by_category, get_rules_as_text,
    get_antispam_keywords, get_memoire_param,
    extract_keywords_from_rule, seed_default_rules,
)

from app.memory_contacts import (
    get_contact_card, get_all_contact_cards,
    get_contacts_keywords, rebuild_contacts,
)

from app.memory_style import (
    get_style_examples, save_style_example,
    learn_from_correction, load_sent_mails_to_style,
    save_reply_learning,
)

from app.memory_synthesis import (
    get_hot_summary, rebuild_hot_summary,
    get_aria_insights, save_insight,
    synthesize_session, purge_old_mails,
)

__all__ = [
    # règles
    'get_aria_rules', 'save_rule', 'delete_rule',
    'get_rules_by_category', 'get_rules_as_text',
    'get_antispam_keywords', 'get_memoire_param',
    'extract_keywords_from_rule', 'seed_default_rules',
    # contacts
    'get_contact_card', 'get_all_contact_cards',
    'get_contacts_keywords', 'rebuild_contacts',
    # style
    'get_style_examples', 'save_style_example',
    'learn_from_correction', 'load_sent_mails_to_style',
    'save_reply_learning',
    # synthèse
    'get_hot_summary', 'rebuild_hot_summary',
    'get_aria_insights', 'save_insight',
    'synthesize_session', 'purge_old_mails',
]
