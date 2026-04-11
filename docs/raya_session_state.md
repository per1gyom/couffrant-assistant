# Raya — État de session vivant

**Dernière mise à jour : 12/04/2026 ~19h00** — Opus

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

## 3. État vérifié 12/04/2026
**RAG vectoriel ACTIVÉ ✅** — 1045/1045 embeddings.
**Tests Phase 4 — 16/16 VERTS ✅** (a/b/c/d).
**Webhook Teams ✅** : subscription Microsoft valide, renouvellement auto 6h via thread daemon.
**Audit global ✅** : réalisé le 12/04/2026, tous les fichiers lus. Roadmap V2 commitée.

## 4. TODO — ROADMAP V2 (voir `docs/raya_roadmap_v2.md` pour détails)
Ordre d'exécution :
1. **Phase 5A** — Sécurité & dette technique (14 tâches, 5A-1 à 5A-14)
2. **Phase 5B** — Optimisation prompt (5 tâches)
3. **Phase 5C** — Robustesse (4 tâches)
4. **Phase 5D** — Mode Dirigeant multi-société (4 tâches)
5. **Phase 5E** — Conscience outils + proactivité + Jarvis minimal (5 tâches)
6. **Phase 5G** — Maturité relationnelle (7 tâches)
7. **Phase 5F** — Dashboard & refactoring (3 tâches)
8. **Phase 7** — Jarvis complet (10 tâches)
9. **Phase 6** — Ouverture (6 tâches)

**Prochaine étape immédiate :** Phase 5A-1 (supprimer mot de passe par défaut config.py)

## 5. Décisions B1–B32 (résumé)
B1-B2 routage Haiku/Sonnet/Opus ✅. B3-B7/B14/B30/B32 RAG + rule_validator ✅. B5 audit Opus ✅. B6 décroissance ✅. B8 session thématique ✅. B9 notifs ✅. B11-B12 multi-tenant 🟡 partiel. B13 onboarding ✅. B16/B18/B23 tools_registry 🟡. B17 /admin/costs ❌. B20 rename 🟡. B21-B22 hiérarchie ✅. B24 API ❌. B25 versioning ❌. B27 Pourquoi ✅. B29 honnêteté ✅. B31 feedback ✅. B10 proactivity ❌. B15 hors-cadre ❌.

## 6. Schéma aria_rules
`id, category, rule, source, confidence, reinforcements, active(bool), created_at, updated_at, context, username, tenant_id, embedding(vector)`. Pas de scope/status. Scope implicite. Migration Alembic à faire (Phase 6-5).

## 7. Utilisateurs cibles
- **Guillaume Perrin** — Couffrant Solar (PV, Loire). Microsoft 365 + Odoo + SharePoint. ~10 boîtes mail (mix MS/Gmail).
- **Charlotte Couffrant** — Juillet (événementiel). Gmail + LinkedIn + Instagram. Beta test multi-tenant.

## 8. Pièges
- Repo local Mac abandonné, conflit `git pull`. Ne pas y toucher sauf session dédiée.
- 12 patch_*.py locaux = vieux scripts one-shot, sans valeur.
- 2 projets Railway parasites à supprimer plus tard.
- 2 versions `get_memoire_param` (memory_rules vs rule_engine) → 5A-9.
- Double `get_contacts_keywords` (rule_engine vs memory_contacts) → 5A-8.
- 3 fichiers contournent `llm_client.py` (ai_client, memory_contacts, memory_style) → 5A-5/6/7.
- `tools_registry` pas consulté par `aria_actions.py` → 5A-10.
- Cleanup fixture tests Phase 4 isolée sur `username='test_phase4'`.
- CLI Railway oublie linking quand on change session/dossier — refaire `cd ~/couffrant-assistant && railway link`.

## 9. Outils Opus
GitHub MCP, Postgres MCP query lecture base prod `railway`, filesystem, Claude in Chrome. Différés via `tool_search`.

## 10. Reprise nouvelle conversation
« Bonjour Opus. Projet Raya, Guillaume. Lis `docs/raya_session_state.md` sur main, puis reprends. »

## 11. RÈGLE — Mise à jour obligatoire
À chaque jalon, Opus propose mise à jour, attend ok, commit. Non négociable. S'applique à toutes les futures Opus.
