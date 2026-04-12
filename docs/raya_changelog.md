# Raya — Changelog

*Archive des modifications par session. Mis à jour par Opus à chaque jalon.*

---

## Session 12-13/04/2026 (Opus + Sonnet + Guillaume)

### Audit global + Roadmap V2
- `758a975` — docs: Roadmap V2 complète + state file

### Phase 5A — Sécurité & dette technique (14/14 ✅)

| Tâche | Fichier(s) | Description |
|---|---|---|
| 5A-1 | `app/config.py` | MDP par défaut supprimé, env obligatoire |
| 5A-2 | `app/main.py` | Cookie 30j → 7j |
| 5A-3 | `app/rate_limiter.py` + `app/routes/raya.py` | Rate limiter 60 req/h |
| 5A-4 | `app/admin_audit.py` + `app/routes/admin.py` | Audit log admin (10 appels) |
| 5A-5 | `app/ai_client.py` | Migré vers llm_complete |
| 5A-6 | `app/memory_contacts.py` | Migré vers llm_complete |
| 5A-7 | `app/memory_style.py` | Migré vers llm_complete |
| 5A-8 | `app/memory_contacts.py` | Doublon get_contacts_keywords supprimé |
| 5A-9+13 | `app/memory_rules.py` + `app/memory_manager.py` | Wrappers dépréciés supprimés |
| 5A-10 | `app/pending_actions.py` + `app/tools_registry.py` | tools_registry source de vérité unique |
| 5A-11 | `app/scheduler.py` + `app/main.py` | Threads daemon → APScheduler |
| 5A-12 | Racine repo | 9 scripts legacy supprimés |
| 5A-14 | `app/memory_loader.py` + `app/memory_manager.py` | Import direct, manager déprécié |

### Phase 5B — Optimisation prompt (5/5 ✅)

| Tâche | Fichier(s) | Description |
|---|---|---|
| 5B-1 | `app/router.py` + `app/routes/aria_context.py` + `app/routes/raya.py` | Injection dynamique actions par domaine |
| 5B-2 | `app/database.py` + `app/memory_synthesis.py` | Hot_summary 3 niveaux + vectorisé |
| 5B-3 | `app/cache.py` + `app/routes/aria_context.py` | Cache TTL 5min |
| 5B-4 | `app/routes/aria_context.py` | Déduplication contexte RAG vs historique |
| 5B-5 | `app/routes/raya.py` | ThreadPoolExecutor partagé |

### Phase 5C — Robustesse (4/4 ✅)

| Tâche | Fichier(s) | Description |
|---|---|---|
| 5C-1 | `app/logging_config.py` + `app/main.py` + `app/scheduler.py` | Structured logging (3 commits) |
| 5C-2 | `app/main.py` | Health check profond DB + LLM |
| 5C-3 | `app/routes/raya.py` | Timeout 30s sur /raya |
| 5C-4 | (résolu par 5A-11) | Monitoring threads → APScheduler |

### Hotfixes
| Fichier | Description |
|---|---|
| `app/routes/memory.py` | Migré vers llm_complete (crash import) |

---

## Sessions précédentes
Phases 1–4 : RAG, multi-tenant, rule_validator, feedback, scheduler, tests.
