# Raya — État de session vivant

**Dernière mise à jour : 12/04/2026 ~23h00** — Opus

## 0. CONSIGNES GUILLAUME
- Ne JAMAIS suggérer de changer de conversation. Relire ce fichier si besoin.
- Vocabulaire : « Terminal » (jamais « shell SSH »).
- Concis. Langage simple, jamais de jargon non expliqué.
- 🟢 lecture / 🟡 modifie / 🔴 sensible. Une commande à la fois.
- **Règle d'or : aucune écriture sans « ok vas-y » explicite.**
- Après push GitHub : `exit` puis `railway ssh` pour récupérer code à jour.
- **Rôle Opus = architecte uniquement** : vision, prompts courts pour Sonnet, vérification post-push via lecture code, mise à jour state file. Pas de pilotage en direct, pas de code, pas de push applicatif.
- **Prompts pour Sonnet** : inclure instruction de push direct (Guillaume ne peut pas juger le code). Ajouter en fin de prompt : « Rapport pour Opus : fichier(s) modifié(s), ligne(s) changée(s), SHA du commit. »
- **Repo local Mac abandonné.** Ne jamais travailler en local. Tout passe par GitHub MCP ou l'interface web GitHub.

## 1. Rôles
Guillaume (dirigeant) / Opus (architecte, MCP GitHub+Postgres) / Sonnet (exécutant).

## 2. Stack
FastAPI Python 3.13 sur Railway. Repo public `github.com/per1gyom/couffrant-assistant` main. Railway projet `invigorating-wholeness` / env `production` / service `Aria`. Postgres+pgvector base `railway`, tenant `couffrant_solar`. Anthropic 3 tiers + OpenAI text-embedding-3-small.

## 3. État vérifié 12/04/2026 soir
**RAG vectoriel ACTIVÉ ✅** — 1045/1045 embeddings.
**Tests Phase 4 — 16/16 VERTS ✅** (a/b/c/d).
**Webhook Teams ✅** : subscription Microsoft valide, renouvellement auto 6h.
**Audit global ✅** : réalisé le 12/04/2026, tous les fichiers lus. Roadmap V2 commitée.
**Railway tourne bien** après tous les commits Phase 5A (logs propres, schedulers OK).

## 4. AVANCEMENT PHASE 5A (en cours)

| Tâche | Statut | Description |
|---|---|---|
| 5A-1 | ✅ fait | Mot de passe par défaut supprimé config.py. APP_USERNAME/APP_PASSWORD obligatoires en env Railway. |
| 5A-2 | ✅ fait | Cookie session 30j → 7j dans main.py. |
| 5A-3 | ✅ fait | Rate limiter 60 req/h. `app/rate_limiter.py` créé + intégré dans `app/routes/raya.py`. |
| 5A-4 | ✅ fait | `app/admin_audit.py` créé + 10 appels log_admin_action dans `app/routes/admin.py`. |
| 5A-5 | ✅ fait | `ai_client.py` migré vers `llm_complete()`. |
| 5A-6 | ✅ fait | `memory_contacts.py` migré vers `llm_complete()`. |
| 5A-7 | ✅ fait | `memory_style.py` migré vers `llm_complete()`. **Agnosticisme LLM complet.** |
| 5A-8 | ✅ fait | Doublon `get_contacts_keywords` supprimé de memory_contacts.py. |
| 5A-9+13 | ✅ fait | Wrappers dépréciés supprimés de memory_rules.py + imports memory_manager.py mis à jour. |
| 5A-10 | ❌ à faire | Brancher aria_actions.py sur tools_registry pour la sensibilité des actions. |
| 5A-11 | ❌ à faire | Migrer webhook renewal/token refresh vers APScheduler. |
| 5A-12 | ❌ à faire | Supprimer 9 scripts legacy racine. **À faire par Guillaume via interface web GitHub** (MCP ne peut pas supprimer de fichiers). Fichiers : auto_ingest.py, push.bat, start_assistant.bat, test_analyzer.py, test_replies.py, upgrade_db_reply_fields.py, upgrade_reply_learning.py, upgrade_reply_status.py, reset_admin_password.py |
| 5A-14 | ❌ à faire | Simplifier memory_loader → memory_manager. |

**Prochaine étape immédiate :** 5A-12 (Guillaume supprime les fichiers via GitHub web) puis 5A-10.

## 5. TODO — ROADMAP V2 (voir `docs/raya_roadmap_v2.md`)
Ordre : 5A (10/14 faites) → 5B → 5C → 5D → 5E → 5G → 5F → Phase 7 (Jarvis) → Phase 6.

## 6. Décisions B1–B32 (résumé)
B1-B2 routage ✅. B3-B7/B14/B30/B32 RAG + rule_validator ✅. B5 audit ✅. B6 décroissance ✅. B8 session thématique ✅. B9 notifs ✅. B11-B12 multi-tenant 🟡. B13 onboarding ✅. B16/B18/B23 tools_registry 🟡. B17 costs ❌. B20 rename 🟡. B21-B22 hiérarchie ✅. B24 API ❌. B25 versioning ❌. B27 Pourquoi ✅. B29 honnêteté ✅. B31 feedback ✅. B10 proactivity ❌. B15 hors-cadre ❌.

## 7. Schéma aria_rules
`id, category, rule, source, confidence, reinforcements, active(bool), created_at, updated_at, context, username, tenant_id, embedding(vector)`. Migration Alembic Phase 6-5.

## 8. Utilisateurs cibles
- **Guillaume Perrin** — Couffrant Solar (PV, Loire). Microsoft 365 + Odoo + SharePoint. ~10 boîtes mail (mix MS/Gmail).
- **Charlotte Couffrant** — Juillet (événementiel). Gmail + LinkedIn + Instagram. Beta test ~mi-juin.

## 9. Pièges
- **Repo local Mac abandonné.** Ne jamais y toucher. Tout via GitHub.
- MCP GitHub en écriture instable le soir — `push_files` plus fiable que `create_or_update_file`.
- MCP GitHub ne peut PAS supprimer de fichiers. Pour les suppressions → Guillaume via interface web GitHub.
- `tools_registry` pas consulté par `aria_actions.py` → 5A-10.
- CLI Railway oublie linking — refaire `cd ~/couffrant-assistant && railway link`.

## 10. Outils Opus
GitHub MCP (lecture + push_files), Postgres MCP query lecture base prod `railway`. Différés via `tool_search`.

## 11. Reprise nouvelle conversation
« Bonjour Opus. Projet Raya, Guillaume. On se tutoie, en français, vocabulaire Terminal, concis. Lis `docs/raya_session_state.md` puis `docs/raya_roadmap_v2.md` sur `per1gyom/couffrant-assistant` main via GitHub MCP. Règle d'or : aucune écriture sans mon ok. Reprends où on en était. »

## 12. RÈGLE — Mise à jour obligatoire
À chaque jalon, Opus met à jour ce fichier. Non négociable.
