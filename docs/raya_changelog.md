# Raya — Changelog

*Archive des modifications par session. Mis à jour par Opus à chaque jalon.*

---

## Session 12-13/04/2026 (Opus + Sonnet + Guillaume)

### Audit global + Roadmap V2
- `758a975` — docs: Roadmap V2 complète + state file mis à jour

### Phase 5A — Sécurité & dette technique (14/14 ✅)

| Tâche | Fichier(s) | Description | SHA |
|---|---|---|---|
| 5A-1 | `app/config.py` | Mot de passe par défaut supprimé, APP_USERNAME/APP_PASSWORD obligatoires en env | (Sonnet) |
| 5A-2 | `app/main.py` | Cookie session 30j → 7j | `9e4124b` |
| 5A-3 (1/2) | `app/rate_limiter.py` | Nouveau fichier : rate limiter 60 req/h par user | `df6f93c` |
| 5A-3 (2/2) | `app/routes/raya.py` | Intégration rate limiter dans endpoint /raya | `adf3ecb` |
| 5A-4 (1/2) | `app/admin_audit.py` | Nouveau fichier : module audit log admin | `39c7db9` |
| 5A-4 (2/2) | `app/routes/admin.py` | 10 appels log_admin_action intégrés | (Sonnet) |
| 5A-5 | `app/ai_client.py` | Migré vers `llm_complete()` — plus d'import Anthropic direct | (Sonnet) |
| 5A-6 | `app/memory_contacts.py` | Migré vers `llm_complete()` | `ca4cfa8` |
| 5A-7 | `app/memory_style.py` | Migré vers `llm_complete()` — **agnosticisme LLM complet** | `95329c8` |
| 5A-8 | `app/memory_contacts.py` | Doublon `get_contacts_keywords` supprimé | (Sonnet) |
| 5A-9+13 | `app/memory_rules.py` + `app/memory_manager.py` | Wrappers dépréciés supprimés, imports redirigés vers rule_engine | (Sonnet) |
| 5A-10 (1/2) | `app/pending_actions.py` | `is_sensitive()` consulte tools_registry en priorité | (Sonnet) |
| 5A-10 (2/2) | `app/tools_registry.py` | Fallback local, dépendance circulaire cassée | (Sonnet) |
| 5A-11 (1/2) | `app/scheduler.py` | 3 jobs ajoutés : webhook_setup, webhook_renewal, token_refresh | (Sonnet) |
| 5A-11 (2/2) | `app/main.py` | 3 threads daemon supprimés (~50 lignes) | (Sonnet) |
| 5A-12 | Racine repo | 9 scripts legacy supprimés (Guillaume via GitHub web) | (Guillaume) |
| 5A-14 | `app/memory_loader.py` + `app/memory_manager.py` | Import direct depuis les 4 modules source, memory_manager déprécié | `d58038f` |

### Hotfixes
| Fichier | Description | SHA |
|---|---|---|
| `app/routes/memory.py` | Migré vers `llm_complete()` — 4ème fichier oublié qui causait crash import | `9866d19` |

### Documentation
| Fichier | Description | SHA |
|---|---|---|
| `docs/raya_roadmap_v2.md` | Roadmap complète V2 (Phases 5A–7 + Phase 6) | `758a975` |
| `docs/raya_session_state.md` | State file enrichi : section ÂME DU PROJET, modèle prompt Sonnet | `323fc4c` + mises à jour |
| `docs/raya_changelog.md` | Ce fichier — archive des commits | (ce commit) |

---

## Sessions précédentes (avant Roadmap V2)

Voir les commits du repo pour l'historique complet.
Phases 1–4 terminées : RAG, multi-tenant, rule_validator, feedback, scheduler, tests.
Dernière version stable avant audit : commits `f5f9d78`, `ff5ff10`, `942099e` (11/04/2026).
