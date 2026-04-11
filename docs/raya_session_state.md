# Raya — État de session vivant

**Dernière mise à jour : 11/04/2026 ~20h15** — Opus

## 0. CONSIGNES GUILLAUME
- Ne JAMAIS suggérer de changer de conversation. Relire ce fichier si besoin.
- Vocabulaire : « Terminal » (jamais « shell SSH »).
- Concis. Langage simple, jamais de jargon non expliqué.
- 🟢 lecture / 🟡 modifie / 🔴 sensible. Une commande à la fois.
- **Règle d'or : aucune écriture sans « ok vas-y » explicite.**
- Après push GitHub : `exit` puis `railway ssh` pour récupérer code à jour.
- **Rôle Opus = architecte uniquement** : vision, prompts courts pour Sonnet, vérification post-push via lecture code, mise à jour state file. Pas de pilotage en direct, pas de code, pas de push applicatif.

## 1. Rôles
Guillaume (dirigeant) / Opus (architecte, MCP GitHub+Postgres) / Sonnet (exécutant).

## 2. Stack
FastAPI Python 3.13 sur Railway. Repo public `github.com/per1gyom/couffrant-assistant` main. Railway projet `invigorating-wholeness` / env `production` / service `Aria`. Postgres+pgvector base `railway`, tenant `couffrant_solar`. Anthropic 3 tiers + OpenAI text-embedding-3-small.

## 3. État vérifié 11/04/2026 fin de soirée
**RAG vectoriel ACTIVÉ ✅** — 1045/1045 embeddings.
**Tests Phase 4 — 16/16 VERTS ✅** (a/b/c/d).
**Webhook Teams ✅ CLOS** : subscription Microsoft valide en base (`612c8084-...`), expire 13/04/2026 12:42 UTC, `client_state` présent, `APP_BASE_URL` correcte. Le ValidationError 400 mentionné en début de journée était un **bug historique déjà corrigé**, plus reproduit en logs récents.

Commits du jour : `f5f9d78`, `ff5ff10` (fixes tests), `942099e`, et state updates.

## 4. TODO ordre priorité
1. **AUDIT GLOBAL DU PROJET** (demande explicite Guillaume) : vérifier cohérence vision Raya, pertinence outils à disposition, modes mémoire, modes apprentissage, modes mémorisation, vectorisation, B1–B32 vs réalité prod. Comme audit fait dans conversations précédentes. À faire en début de prochaine session.
2. ⚠️ **Vérifier job renouvellement subscription Microsoft** : expire 13/04 12:42 UTC. Confirmer qu'APScheduler la renouvelle automatiquement (sinon webhook tombe dans 44h). Sonnet à mandater.
3. Second compte super_admin de secours.
4. proactivity_scan B10.
5. Dashboard /admin/costs B17.
6. Premiers MCP par tenant B16.
7. user_tenant_access.
8. Migration Alembic scope/status (B11/B12/B25, non urgent).
9. Nettoyage : 12 patch_*.py locaux + 2 projets Railway parasites (`gregarious-wholeness`, `celebrated-achievement`) + repo local Mac.

## 5. Décisions B1–B32 (résumé)
B1-B2 routage Haiku/Sonnet/Opus. B3-B7/B14/B30/B32 RAG + rule_validator NEW/DUPLICATE/REFINE/SPLIT/CONFLICT, mémoire 4 couches. B11-B12 multi-tenant 3 rôles. B16/B18/B23 tools_registry, MCP par tenant facturé. B21-B22 hiérarchie règle>skill>code. B9-B10/B15/B27 3 niveaux notifs, bouton Pourquoi, mode hors-cadre. B13 onboarding élicitation. B29 honnêteté épistémique. B17 /admin/costs. B20 rename aria→raya à la fin. B24 API externe Phase 5. B25 versioning règles. B31 boucle feedback 👍👎.

## 6. Schéma aria_rules
`id, category, rule, source, confidence, reinforcements, active(bool), created_at, updated_at, context, username, tenant_id, embedding(vector)`. Pas de scope/status. Scope implicite. Migration Alembic à faire.

## 7. Facturation
Forfait tenant 150-300€/mois. User sup 30-50€/mois. Multi-tenant 50-80€/tenant. MCP par serveur. Surcoût LLM hors quota.

## 8. Pièges
- Repo local Mac abandonné, conflit `git pull`. Ne pas y toucher sauf session dédiée.
- 12 patch_*.py locaux = vieux scripts one-shot, sans valeur.
- 2 projets Railway parasites à supprimer plus tard.
- 2 versions `get_memoire_param` (memory_rules vs rule_engine).
- Cleanup fixture tests Phase 4 isolée sur `username='test_phase4'`.
- CLI Railway oublie linking quand on change session/dossier — refaire `cd ~/couffrant-assistant && railway link`.

## 9. Outils Opus
GitHub MCP, Postgres MCP query lecture base prod `railway`, filesystem, Claude in Chrome. Différés via `tool_search`.

## 10. Reprise nouvelle conversation
« Bonjour Opus. Projet Raya, Guillaume. Lis `docs/raya_session_state.md` sur main, puis reprends. »

## 11. RÈGLE — Mise à jour obligatoire
À chaque jalon, Opus propose mise à jour, attend ok, commit. Non négociable. S'applique à toutes les futures Opus.
