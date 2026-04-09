"""
DEPRECATED — couche de compatibilité, conservée pour les imports existants.
Le code réel est dans :
  app.memory_rules      → get_aria_rules, get_rules_by_category, get_memoire_param...
  app.memory_contacts   → get_contact_card, get_contacts_keywords, rebuild_contacts
  app.memory_style      → get_style_examples, save_reply_learning, learn_from_correction
  app.memory_synthesis  → get_hot_summary, get_aria_insights, save_insight, synthesize_session
"""
from app.memory_rules import (  # noqa
    get_aria_rules, get_rules_by_category, get_antispam_keywords,
    get_contacts_keywords, get_memoire_param, save_rule, delete_rule,
    seed_default_rules,
)
from app.memory_contacts import get_contact_card, rebuild_contacts  # noqa
from app.memory_style import get_style_examples, save_reply_learning, learn_from_correction  # noqa
from app.memory_synthesis import (  # noqa
    get_hot_summary, get_aria_insights, save_insight,
    synthesize_session, rebuild_hot_summary, purge_old_mails,
)
