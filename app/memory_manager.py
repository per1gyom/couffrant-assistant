"""
Couche de compatibilité mémoire — liste complète et définitive.

Sources :
  get_contacts_keywords   → app.rule_engine       (PAS memory_rules)
  get_all_contact_cards   → app.memory_contacts
  save_style_example      → app.memory_style
  load_sent_mails_to_style→ app.memory_style
  get_antispam_keywords   → app.memory_rules
  get_memoire_param       → app.memory_rules (signature : param, default, username)
"""
from app.memory_rules import (  # noqa
    get_aria_rules, get_rules_by_category, get_antispam_keywords,
    get_memoire_param, save_rule, delete_rule, seed_default_rules,
)
from app.rule_engine import get_contacts_keywords  # noqa — dans rule_engine, pas memory_rules
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
