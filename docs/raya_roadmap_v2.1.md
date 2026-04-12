# Mise à jour roadmap V2.1 — Phase 5D terminée

**Date :** 12/04/2026 soir
**Auteur :** Opus

## Ce qui a été fait

Phase 5D complète (4/4 tâches) :
- 5D-1 ✅ Table user_tenant_access (session précédente)
- 5D-2 ✅ Contexte multi-tenant dans le prompt (6 sous-tâches, cette session)
- 5D-3 ✅ Admin secours (session précédente)
- 5D-4 ⭕ Onboarding par tenant (prochaine étape)

## Détail 5D-2 (cette session)

| Sous-tâche | Description | Fichier(s) |
|---|---|---|
| 5D-2a | `get_user_tenants(username)` | tenant_manager.py |
| 5D-2b | `search_similar` accepte `tenant_ids: list` | embedding.py |
| 5D-2c | Toutes fonctions RAG propagent `tenant_ids` | rag.py |
| 5D-2d | LEARN avec tenant cible + `save_rule(personal=True)` | aria_actions.py, memory_rules.py |
| 5D-2e | `build_system_prompt` multi-tenant (bloc sociétés, RAG cross-tenant, contacts) | aria_context.py |
| 5D-2f | `_raya_core` charge et passe `user_tenants` | raya.py |

## Architecture multi-tenant

- **Lecture** : un dirigeant voit les données de TOUS ses tenants (RAG cross-tenant)
- **Écriture** : chaque LEARN est tagé avec le tenant concerné. Format : `[ACTION:LEARN:cat|rule|tenant_id]`
- **Règles perso** : `[ACTION:LEARN:cat|rule|_user]` → `tenant_id=NULL` en base
- **Isolation** : un collaborateur avec 1 seul tenant ne voit QUE ses données. Zéro changement pour lui.
- **Rétro-compatible** : tout le code fonctionne identiquement si `user_tenants` contient 1 seul tenant.

## Prochaine étape

5D-4 : Onboarding par tenant, puis Phase 5E (Conscience des outils + Proactivité).

---

*Ce fichier complète `raya_roadmap_v2.md` (V2.1). La roadmap principale reste la référence pour l'ordre des phases.*
