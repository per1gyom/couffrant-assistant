# Raya — État de session vivant

**Dernière mise à jour : 11/04/2026 ~19h45** — Opus

## 0. CONSIGNES PERMANENTES GUILLAUME
- **Ne JAMAIS suggérer de changer de conversation.** On reste, on relit ce fichier si besoin.
- Vocabulaire : « Terminal » (jamais « shell SSH »).
- Concis par défaut. Langage simple, jamais de jargon non expliqué.
- Marquer commandes 🟢 lecture / 🟡 modifie / 🔴 sensible. Une à la fois.
- **Règle d'or : aucune écriture sans « ok vas-y » explicite de Guillaume**.
- **Après chaque push GitHub, refaire `exit` puis `railway ssh`** pour récupérer le code à jour dans le conteneur Aria (sinon ancien code).

## 1. Rôles
Guillaume (dirigeant, ne code pas) / Opus (architecte, MCP GitHub+Postgres) / Sonnet (exécutant, autre conv).

## 2. Stack
FastAPI Python 3.13 sur Railway. Repo public `github.com/per1gyom/couffrant-assistant` main. Railway projet `invigorating-wholeness` / env `production` / service `Aria`. Postgres+pgvector base `railway`, tenant `couffrant_solar`. Anthropic 3 tiers + OpenAI text-embedding-3-small.

## 3. État vérifié 11/04/2026 fin de journée
**RAG vectoriel ACTIVÉ ✅** — 1045/1045 embeddings (aria_rules 76, aria_insights 20, aria_memory 12, mail_memory 937). 17,4s, ~0,0005 USD.

**Tests Phase 4 — 16/16 VERTS ✅** :
- (a) TestDuplicateDetection 4/4 ✅
- (b) TestCapabilitiesInPrompt 4/4 ✅
- (c) TestLearnParser 5/5 ✅
- (d) TestFeedbackEndpoint 3/3 ✅

Commits du jour : `f5f9d78` (fix mock cible llm_complete) puis `ff5ff10` (fix clé `rule` au lieu de `rule_text` dans le mock). Aucun changement code applicatif.

## 4. Phase 4 — TODO ordre priorité (16/16 acquis)
1. Diagnostic webhook Teams ValidationError 400 (pollue logs)
2. Second compte super_admin de secours
3. proactivity_scan B10
4. Dashboard /admin/costs B17
5. Premiers MCP par tenant B16
6. user_tenant_access
7. Migration Alembic scope/status (B11/B12/B25, non urgent)
8. Nettoyage : 12 patch_*.py locaux + 2 projets Railway parasites + repo local Mac

## 5. Décisions B1–B32 (résumé)
B1-B2 routage Haiku/Sonnet/Opus. B3-B7/B14/B30/B32 RAG + rule_validator NEW/DUPLICATE/REFINE/SPLIT/CONFLICT, mémoire 4 couches. B11-B12 multi-tenant 3 rôles. B16/B18/B23 tools_registry, MCP par tenant facturé. B21-B22 hiérarchie règle>skill>code. B9-B10/B15/B27 3 niveaux notifs, bouton Pourquoi, mode hors-cadre. B13 onboarding élicitation. B29 honnêteté épistémique. B17 /admin/costs. B20 rename aria→raya à la fin. B24 API externe Phase 5. B25 versioning règles. B31 boucle feedback 👍👎.

## 6. Schéma aria_rules
`id, category, rule, source, confidence, reinforcements, active(bool), created_at, updated_at, context, username, tenant_id, embedding(vector)`. Pas de scope/status. Scope implicite (username NULL = tenant). Migration Alembic à faire.

## 7. Facturation
Forfait tenant 150-300€/mois. User sup 30-50€/mois. Multi-tenant 50-80€/tenant. MCP par serveur. Surcoût LLM hors quota.

## 8. Pièges
- Repo local Mac abandonné, conflit `git pull`. Ne pas y toucher sauf session dédiée.
- 12 patch_*.py locaux = vieux scripts one-shot, sans valeur.
- 2 projets Railway parasites (`gregarious-wholeness`, `celebrated-achievement`) à supprimer plus tard.
- 2 versions `get_memoire_param` (memory_rules vs rule_engine).
- Webhook Teams ValidationError 400 dans logs.
- Cleanup fixture tests Phase 4 isolée sur `username='test_phase4'`.
- **CLI Railway oublie le linking quand on change de session/dossier** — refaire `cd ~/couffrant-assistant && railway link` si besoin.

## 9. Outils Opus
GitHub MCP, Postgres MCP query lecture base prod `railway`, filesystem, Claude in Chrome. Différés via `tool_search`.

## 10. Reprise nouvelle conversation (uniquement si vraiment nécessaire)
« Bonjour Opus. Projet Raya, Guillaume. Lis `docs/raya_session_state.md` sur main, puis reprends. »

## 11. RÈGLE — Mise à jour obligatoire
À chaque jalon (test passé/échoué, blocant levé, commit important, décision archi, changement état prod, nouveau bug, nouvelle priorité), Opus **propose** mise à jour, attend « ok », commit. Non négociable. S'applique à toutes les futures Opus.
