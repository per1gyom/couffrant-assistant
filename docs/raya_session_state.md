# Raya — État de session vivant

**Dernière mise à jour : 12/04/2026 ~22h30** — Opus

## 0. CONSIGNES GUILLAUME
- Ne JAMAIS suggérer de changer de conversation. Relire ce fichier si besoin.
- Vocabulaire : « Terminal » (jamais « shell SSH »).
- Concis. Langage simple, jamais de jargon non expliqué.
- 🟢 lecture / 🟡 modifie / 🔴 sensible. Une commande à la fois.
- **Règle d'or : aucune écriture sans « ok vas-y » explicite.**
- Après push GitHub : `exit` puis `railway ssh` pour récupérer code à jour.
- **Rôle Opus = architecte uniquement** : vision, prompts courts pour Sonnet, vérification post-push via lecture code, mise à jour state file. Pas de pilotage en direct, pas de code, pas de push applicatif.
- **Prompts pour Sonnet** : inclure instruction de push direct (Guillaume ne peut pas juger le code). Ajouter en fin de prompt : « Rapport pour Opus : fichier(s) modifié(s), ligne(s) changée(s), SHA du commit. »

## 1. Rôles
Guillaume (dirigeant) / Opus (architecte, MCP GitHub+Postgres) / Sonnet (exécutant).

## 2. Stack
FastAPI Python 3.13 sur Railway. Repo public `github.com/per1gyom/couffrant-assistant` main. Railway projet `invigorating-wholeness` / env `production` / service `Aria`. Postgres+pgvector base `railway`, tenant `couffrant_solar`. Anthropic 3 tiers + OpenAI text-embedding-3-small.

## 3. État vérifié 12/04/2026 soir
**RAG vectoriel ACTIVÉ ✅** — 1045/1045 embeddings.
**Tests Phase 4 — 16/16 VERTS ✅** (a/b/c/d).
**Webhook Teams ✅** : subscription Microsoft valide, renouvellement auto 6h via thread daemon.
**Audit global ✅** : réalisé le 12/04/2026, tous les fichiers lus. Roadmap V2 commitée.

## 4. AVANCEMENT PHASE 5A (en cours)

| Tâche | Statut | Description |
|---|---|---|
| 5A-1 | ✅ fait | Mot de passe par défaut supprimé dans config.py. APP_USERNAME et APP_PASSWORD obligatoires en env Railway. |
| 5A-2 | ✅ fait | Cookie session réduit de 30j à 7j dans main.py. |
| 5A-3 | ✅ fait | Rate limiter 60 req/h par user. `app/rate_limiter.py` créé + intégré dans `app/routes/raya.py`. |
| 5A-4 | ✅ fait | `app/admin_audit.py` créé + 10 appels log_admin_action intégrés dans `app/routes/admin.py`. |
| 5A-5 | ✅ fait | `ai_client.py` migré vers `llm_complete()`. Plus d'import Anthropic direct. |
| 5A-6 | ⏳ EN COURS | `memory_contacts.py` à migrer vers `llm_complete()`. Prompt prêt. |
| 5A-7 | ⏳ suivant | `memory_style.py` à migrer vers `llm_complete()`. Prompt prêt. |
| 5A-8 | ❌ | Supprimer doublon `get_contacts_keywords` dans memory_contacts.py |
| 5A-9 | ❌ | Supprimer wrapper fragile `get_memoire_param` dans memory_rules.py |
| 5A-10 | ❌ | Brancher aria_actions.py sur tools_registry |
| 5A-11 | ❌ | Migrer webhook renewal/token refresh vers APScheduler |
| 5A-12 | ❌ | Supprimer scripts legacy racine |
| 5A-13 | ❌ | Supprimer wrappers dépréciés memory_rules.py |
| 5A-14 | ❌ | Simplifier memory_loader → memory_manager |

## 5. TODO — ROADMAP V2 (voir `docs/raya_roadmap_v2.md` pour détails complets)
Ordre d'exécution :
1. **Phase 5A** — Sécurité & dette technique (14 tâches, 5/14 faites)
2. **Phase 5B** — Optimisation prompt (5 tâches)
3. **Phase 5C** — Robustesse (4 tâches)
4. **Phase 5D** — Mode Dirigeant multi-société (4 tâches)
5. **Phase 5E** — Conscience outils + proactivité + Jarvis minimal (5 tâches)
6. **Phase 5G** — Maturité relationnelle (7 tâches)
7. **Phase 5F** — Dashboard & refactoring (3 tâches)
8. **Phase 7** — Jarvis complet (10 tâches) — DESTINATION FINALE
9. **Phase 6** — Ouverture (6 tâches)

## 6. Décisions B1–B32 (résumé)
B1-B2 routage ✅. B3-B7/B14/B30/B32 RAG + rule_validator ✅. B5 audit ✅. B6 décroissance ✅. B8 session thématique ✅. B9 notifs ✅. B11-B12 multi-tenant 🟡. B13 onboarding ✅. B16/B18/B23 tools_registry 🟡. B17 costs ❌. B20 rename 🟡. B21-B22 hiérarchie ✅. B24 API ❌. B25 versioning ❌. B27 Pourquoi ✅. B29 honnêteté ✅. B31 feedback ✅. B10 proactivity ❌. B15 hors-cadre ❌.

## 7. Schéma aria_rules
`id, category, rule, source, confidence, reinforcements, active(bool), created_at, updated_at, context, username, tenant_id, embedding(vector)`. Migration Alembic à faire (Phase 6-5).

## 8. Utilisateurs cibles
- **Guillaume Perrin** — Couffrant Solar (PV, Loire). Microsoft 365 + Odoo + SharePoint. ~10 boîtes mail (mix MS/Gmail).
- **Charlotte Couffrant** — Juillet (événementiel). Gmail + LinkedIn + Instagram. Beta test multi-tenant prévu ~mi-juin.

## 9. Pièges
- Repo local Mac abandonné. Ne pas y toucher.
- 12 patch_*.py locaux = sans valeur.
- 2 projets Railway parasites à supprimer.
- `get_memoire_param` doublon (memory_rules vs rule_engine) → 5A-9.
- `get_contacts_keywords` doublon (rule_engine vs memory_contacts) → 5A-8.
- `tools_registry` pas consulté par `aria_actions.py` → 5A-10.
- MCP GitHub en écriture instable le soir — `push_files` plus fiable que `create_or_update_file`.
- CLI Railway oublie linking — refaire `cd ~/couffrant-assistant && railway link`.

## 10. Outils Opus
GitHub MCP, Postgres MCP query lecture base prod `railway`, filesystem. Différés via `tool_search`.

## 11. Reprise nouvelle conversation
« Bonjour Opus. Projet Raya, Guillaume. On se tutoie, en français, vocabulaire Terminal, concis. Lis `docs/raya_session_state.md` puis `docs/raya_roadmap_v2.md` sur `per1gyom/couffrant-assistant` main via GitHub MCP. Règle d'or : aucune écriture sans mon ok. Reprends où on en était. »

## 12. RÈGLE — Mise à jour obligatoire
À chaque jalon, Opus met à jour ce fichier. Non négociable.
