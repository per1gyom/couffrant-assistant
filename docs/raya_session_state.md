# Raya — État de session vivant

**Dernière mise à jour : 11/04/2026 ~17h** — Opus (cette instance)

> Ce fichier est la **source de vérité unique** pour reprendre une conversation avec Opus sans repartir de zéro. À chaque nouvelle conversation Opus, Guillaume colle simplement : « Lis `docs/raya_session_state.md` sur `per1gyom/couffrant-assistant` main, puis reprends. »

---

## 1. Identités & rôles
- **Guillaume Perrin** : dirigeant Couffrant Solar, ne code pas, sur Mac, parle français. Vocabulaire : « Terminal » (pas « shell SSH »). Réponses concises par défaut, denses uniquement sur les points critiques. Pose des questions s'il ne comprend pas.
- **Opus** : architecte. Vérifie via Postgres MCP + GitHub MCP. Rédige des prompts courts pour Sonnet.
- **Sonnet** : exécutant. Code, commits, push, déploiement. Travaille dans une autre conversation.
- **Règle d'or** : aucune écriture (commit, push, base, script non dry-run) sans « ok vas-y » explicite de Guillaume.

## 2. Stack & accès
- FastAPI Python 3.13 sur Railway
- Repo public : `github.com/per1gyom/couffrant-assistant` branche `main`
- Railway : projet `invigorating-wholeness` / env `production` / service `Aria` (CLI liée localement sur le Mac)
- Prod : `couffrant-assistant-production.up.railway.app`
- Postgres + pgvector, base `railway`, tenant unique `couffrant_solar`
- LLM : Anthropic Claude 3 tiers + OpenAI `text-embedding-3-small`

## 3. État vérifié 11/04/2026 fin de journée
**RAG vectoriel ACTIVÉ ✅** — backfill exécuté avec succès via `railway ssh` puis `python scripts/backfill_embeddings.py`. Résultat : 1045/1045 embeddings, 0 erreur, 17,4s, ~0,0005 USD.
- `aria_rules` : 76/76 ✅
- `aria_insights` : 20/20 ✅
- `aria_memory` : 12/12 ✅
- `mail_memory` : 937/937 ✅

`OPENAI_API_KEY` confirmée présente dans Variables Railway service Aria. Le `rule_validator.py` peut désormais détecter les doublons sémantiques. **Le blocant Phase 4 est levé.**

## 4. Phase actuelle : Phase 4 (en cours)
Fait : scheduler APScheduler, jobs expire/decay/audit, PWA installable, onboarding migré vers moteur d'élicitation, rule_validator.py avec vectorisation, capabilities registry, parser LEARN robuste, feedback vocal, **RAG vectoriel actif (11/04)**.

**À faire, ordre de priorité :**
1. Re-tester les 4 scénarios apprentissage (DUPLICATE sémantique, capabilities, parser LEARN crochets, feedback 👍👎) — fichier de tests cherché : `tests/test_phase4_apprentissage.py` ou similaire (commit `bd9578b`)
2. Diagnostic webhook Teams ValidationError 400 (pollue les logs)
3. Créer un second compte super_admin de secours
4. `proactivity_scan` (B10)
5. Dashboard `/admin/costs` (B17) exposant `llm_usage`
6. Premiers MCP par tenant (B16)
7. `user_tenant_access`
8. Migration Alembic scope/status (B11/B12/B25, non urgent)

## 5. 32 décisions d'architecture B1–B32 (résumé compact)
- **B1–B2** Routage Haiku/Sonnet/Opus, micro-Haiku silencieux, compteur Opus/jour. Pipeline mails Haiku→Sonnet→Opus si needs_deep_review.
- **B3–B7, B14, B30, B32** RAG vectoriel + injection contextuelle des règles, audit hebdo Opus, décroissance temporelle, mémoire hybride 4 couches, validation Opus avec recherche similarité (NEW/DUPLICATE/REFINE/SPLIT/CONFLICT), `is_learning_phase()` adaptatif.
- **B11–B12** Multi-tenant : standard mono / admin multi (voit tous ses tenants). 3 rôles : super_admin/tenant_admin/user. Scope règles : tenant ou user.
- **B16, B18, B23** `tools_registry` central, migration tool use natif Anthropic, MCP par tenant facturé, recherche unifiée `app/search.py`.
- **B21–B22** Skills déclenchés par type RDV Odoo. Hiérarchie : règle apprise > skill enregistré > code Python.
- **B9–B10, B15, B27** 3 niveaux notifications (alertes/rappels/suggestions), job 30 min, bouton « Pourquoi ? », mode hors-cadre configurable strict/souple/libre.
- **B13** Onboarding conversationnel Opus via moteur d'élicitation générique, 8 échanges max, skippable.
- **B29** Honnêteté épistémique, registre `capabilities.py`.
- **B17** dashboard `/admin/costs`. **B19** dégradation gracieuse. **B20** rename aria→raya à la toute fin. **B24** API externe `/api/v1/chat` Phase 5. **B25** versioning règles + rollback. **B26** audit profil trimestriel. **B28** moteur élicitation générique. **B31** boucle correction feedback 👍👎.

## 6. Schéma `aria_rules` réel
`id, category, rule, source, confidence, reinforcements, active (bool), created_at, updated_at, context, username, tenant_id, embedding (vector)`. Pas de colonne `scope` ni `status` — scope implicite (username NULL = tenant, sinon = user), statut = booléen `active`. B11/B12/B25 nécessitent une migration Alembic non encore faite.

## 7. Modèle de facturation validé
Forfait tenant base 150–300 €/mois (5 users + tenant_admin + onboarding). User sup 30–50 €/mois. Multi-tenant 50–80 €/tenant. MCP supplémentaire facturé par serveur actif. Surcoût LLM au-delà du quota.

## 8. Pièges & vigilance
- Repo local du Mac est **abandonné depuis ~3 jours**, en retard sur GitHub, modifs non commitées, conflit `git pull divergent`. **Ne pas y toucher** sauf session dédiée « ménage local ».
- 12 fichiers `patch_*.py` non suivis dans le repo local = vieux scripts one-shot déjà appliqués en prod, **sans valeur active**, à archiver/supprimer plus tard. Ne PAS les utiliser comme source de vérité.
- 2 projets Railway parasites à supprimer plus tard : `gregarious-wholeness`, `celebrated-achievement`. Ne pas toucher sans triple vérif (suppression définitive).
- Deux versions de `get_memoire_param` : `memory_rules.py` signature `(param, default, username)` vs `rule_engine.py` signature `(username, param, default)`. Ne pas confondre.
- Table `gmail_tokens` : legacy, ne plus alimenter (migré vers `oauth_tokens`).
- Webhook Teams ValidationError 400 toujours présent dans les logs, à diagnostiquer.

## 9. Outils Opus disponibles dans la conversation actuelle
GitHub MCP (26 outils), Postgres MCP (`query` lecture seule pointé sur la base prod `railway`), filesystem (14), Claude in Chrome (19). Tous différés via `tool_search`.

## 10. Comment reprendre dans une nouvelle conversation Opus
Coller au début : « Bonjour Opus. Projet Raya, je suis Guillaume. Lis `docs/raya_session_state.md` sur `per1gyom/couffrant-assistant` branche main via GitHub MCP, puis dis-moi où on en est et propose la prochaine action. Règle d'or : aucune écriture sans mon ok explicite. Vocabulaire : Terminal. Concis par défaut. »

Opus doit alors charger l'outil GitHub `get_file_contents` via `tool_search`, lire ce fichier, et reprendre.

## 11. Mise à jour de ce fichier
À chaque jalon (test passé, phase franchie, blocant levé, décision d'architecture), Opus propose à Guillaume une mise à jour de ce fichier. Guillaume valide, Opus commit. C'est la mémoire vivante du projet, plus précieuse que n'importe quel briefing one-shot.
