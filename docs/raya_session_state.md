# Raya — État de session vivant

**Dernière mise à jour : 11/04/2026 ~17h45** — Opus

> Source de vérité unique pour reprendre une conversation Opus. Coller : « Lis `docs/raya_session_state.md` sur main, puis reprends. »

## 1. Identités & rôles
- **Guillaume** : dirigeant Couffrant Solar, Mac, ne code pas. Vocabulaire « Terminal ». Concis par défaut.
- **Opus** : architecte. Postgres MCP + GitHub MCP. Rédige prompts courts pour Sonnet.
- **Sonnet** : exécutant, autre conversation.
- **Règle d'or** : aucune écriture sans « ok vas-y » explicite de Guillaume.

## 2. Stack & accès
FastAPI Python 3.13 sur Railway. Repo public `github.com/per1gyom/couffrant-assistant` main. Railway projet `invigorating-wholeness` / env `production` / service `Aria` (CLI liée). Postgres+pgvector base `railway`, tenant `couffrant_solar`. Anthropic Claude 3 tiers + OpenAI text-embedding-3-small.

## 3. État vérifié 11/04/2026
**RAG vectoriel ACTIVÉ ✅** — backfill 1045/1045 embeddings via `railway ssh` + `python scripts/backfill_embeddings.py`. 17,4s, ~0,0005 USD, 0 erreur.
- aria_rules 76/76, aria_insights 20/20, aria_memory 12/12, mail_memory 937/937
- OPENAI_API_KEY confirmée dans Variables Railway service Aria
- rule_validator.py peut détecter doublons sémantiques. **Blocant Phase 4 levé.**

**Tests Phase 4 EN COURS** : plan validé par Opus, pré-vol `pytest --collect-only` à lancer. 4 scénarios : (a) DUPLICATE/REFINE/NEW via rule_validator, (b) capabilities dans prompt, (c) parser LEARN robuste crochets, (d) feedback. Cleanup fixture isolée sur `username='test_phase4'`, sans risque pour les 76 règles couffrant_solar.

## 4. Phase 4 — à faire
1. ✅ EN COURS — 4 scénarios apprentissage (`tests/test_phase4_apprentissage.py`)
2. Diagnostic webhook Teams ValidationError 400
3. Second compte super_admin de secours
4. proactivity_scan B10
5. Dashboard /admin/costs B17
6. Premiers MCP par tenant B16
7. user_tenant_access
8. Migration Alembic scope/status (B11/B12/B25, non urgent)

## 5. Décisions B1–B32 (résumé)
B1-B2 routage 3 tiers Haiku/Sonnet/Opus. B3-B7/B14/B30/B32 RAG vectoriel + rule_validator NEW/DUPLICATE/REFINE/SPLIT/CONFLICT, mémoire 4 couches, audit hebdo Opus. B11-B12 multi-tenant 3 rôles. B16/B18/B23 tools_registry, MCP par tenant facturé. B21-B22 skills par RDV Odoo, hiérarchie règle>skill>code. B9-B10/B15/B27 3 niveaux notifs, bouton Pourquoi, mode hors-cadre. B13 onboarding élicitation 8 échanges. B29 honnêteté épistémique capabilities.py. B17 /admin/costs. B19 dégradation gracieuse. B20 rename aria→raya à la fin. B24 API externe Phase 5. B25 versioning règles. B26 audit profil trimestriel. B28 moteur élicitation générique. B31 boucle feedback 👍👎.

## 6. Schéma aria_rules
`id, category, rule, source, confidence, reinforcements, active(bool), created_at, updated_at, context, username, tenant_id, embedding(vector)`. Pas de scope/status. Scope implicite (username NULL = tenant). Migration Alembic B11/B12/B25 à faire.

## 7. Facturation
Forfait tenant 150-300€/mois (5 users + onboarding inclus). User sup 30-50€/mois. Multi-tenant 50-80€/tenant. MCP par serveur. Surcoût LLM hors quota.

## 8. Pièges
- Repo local Mac abandonné depuis ~3 jours, conflit `git pull`. Ne pas y toucher sauf session dédiée.
- 12 patch_*.py locaux = vieux scripts one-shot déjà appliqués, sans valeur active.
- 2 projets Railway parasites (`gregarious-wholeness`, `celebrated-achievement`) à supprimer plus tard avec triple vérif.
- 2 versions de `get_memoire_param` (memory_rules vs rule_engine), signatures différentes.
- Table `gmail_tokens` legacy.
- Webhook Teams ValidationError 400 dans logs, à diagnostiquer.

## 9. Outils Opus
GitHub MCP (26), Postgres MCP query lecture sur base `railway` prod, filesystem (14), Claude in Chrome (19). Différés via `tool_search`.

## 10. Reprise nouvelle conversation
Coller : « Bonjour Opus. Projet Raya, Guillaume. Lis `docs/raya_session_state.md` sur `per1gyom/couffrant-assistant` main via GitHub MCP, puis reprends. Règle d'or : aucune écriture sans mon ok. Vocabulaire : Terminal. Concis. »

## 11. RÈGLE — Mise à jour obligatoire de ce fichier
**Non négociable.** À chaque jalon — test passé/échoué, blocant levé, commit applicatif important, décision archi, changement état prod (embeddings, migrations, services, variables Railway), nouveau bug, nouvelle priorité — Opus **propose** une mise à jour, attend le « ok » de Guillaume, **commit**. Ce fichier doit refléter l'état réel à ±24h près. Si Opus oublie, Guillaume rappelle, Opus s'exécute immédiatement. Cette règle s'applique à TOUTES les futures instances Opus du projet.
