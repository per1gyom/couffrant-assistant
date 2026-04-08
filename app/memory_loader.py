"""
Chargeur mémoire avec fallbacks gracieux.
Importer depuis ici pour éviter de dupliquer le try/except partout.
"""

try:
    from app.memory_manager import (
        get_hot_summary, rebuild_hot_summary,
        get_contact_card, get_all_contact_cards, rebuild_contacts,
        get_style_examples, save_style_example, learn_from_correction,
        load_sent_mails_to_style, purge_old_mails,
        get_aria_rules, save_rule, delete_rule,
        get_aria_insights, save_insight,
        synthesize_session, seed_default_rules,
    )
    MEMORY_OK = True
except Exception as _mem_err:
    print(f"[Memory] Module non disponible: {_mem_err}")
    MEMORY_OK = False

    def get_hot_summary(username="guillaume"): return ""
    def rebuild_hot_summary(username="guillaume"): return ""
    def get_contact_card(x): return ""
    def get_all_contact_cards(): return []
    def rebuild_contacts(): return 0
    def get_style_examples(**kwargs): return ""
    def save_style_example(**kwargs): pass
    def learn_from_correction(**kwargs): pass
    def load_sent_mails_to_style(**kwargs): return 0
    def purge_old_mails(**kwargs): return 0
    def get_aria_rules(username="guillaume"): return ""
    def save_rule(*a, **kw): return 0
    def delete_rule(*a, **kw): return False
    def get_aria_insights(**kwargs): return ""
    def save_insight(*a, **kw): return 0
    def synthesize_session(**kwargs): return {}
    def seed_default_rules(username="guillaume"): pass
