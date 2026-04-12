# Raya — État de session vivant

**Dernière mise à jour : 12/04/2026 soir** — Opus

---

## ⭐ ÂME DU PROJET — LIRE EN PREMIER

**Ce que Guillaume veut construire :**

Raya n'est PAS un chatbot. Raya n'est PAS un outil de tri de mails. Raya n'est PAS un assistant classique qui répond quand on lui parle.

Raya est un **cerveau supplémentaire** pour un dirigeant d'entreprise. Comme Jarvis pour Tony Stark dans Iron Man. Quelqu'un qui connaît son utilisateur en profondeur, qui comprend comment il fonctionne, qui anticipe ses besoins, et qui AGIT de façon autonome dans les limites que l'utilisateur a fixées.

**L'expérience visée :**

Guillaume a ~10 boîtes mail. Le rêve : désactiver TOUTES les alertes mail et ne garder qu'un seul canal — Raya. Raya surveille tout en permanence. Si un mail important arrive, Raya envoie un message WhatsApp. Si c'est critique, Raya appelle. Le matin, Raya envoie un résumé même si rien d'urgent — preuve de vie.

Guillaume possède plusieurs sociétés. Raya fait le lien entre elles : vision transversale.

**L'apprentissage — le cœur :** Raya apprend comme deux humains qui se rencontrent. Découverte → Consolidation → Maturité. Règles évolutives, jamais figées dans le code.

**LLM-agnostic :** La mémoire est le vrai asset. Le modèle IA est interchangeable.

**Proactivité :** Raya INITIE les interactions. Entonnoir 5 étages pour le triage.

**Guillaume n'est PAS programmeur.** Expliquer simplement, sans jargon.

---

## 0. CONSIGNES
- Vocabulaire : « Terminal ». Concis. Langage simple.
- **Règle d'or : aucune écriture sans « ok vas-y » explicite.**
- **Repo local Mac abandonné.** Tout via GitHub.

### Workflow Opus / Sonnet (NON NÉGOCIABLE)

**Opus = architecte.** Il audite le code, conçoit l'architecture, rédige des prompts
précis pour Sonnet. **Opus ne code PAS et ne pousse PAS de commits lui-même.**
Ses tokens sont chers — il les utilise pour la réflexion, la conception,
et la durée de session. Plus Opus économise ses tokens, plus la session dure longtemps.

**Sonnet = exécutant.** Il reçoit les prompts d'Opus (copiés par Guillaume),
code les modifications, et pousse directement sur `main`.

**Le cycle :**
1. Opus lit le code, identifie les changements nécessaires
2. Opus rédige des prompts Sonnet précis (fichier, fonction, lignes, format commit)
3. Guillaume valide les prompts
4. Guillaume copie-colle chaque prompt dans une conversation Sonnet
5. Sonnet exécute et rapporte (fichier, SHA)
6. Opus vérifie si besoin et passe à la tâche suivante

## 1. Stack
FastAPI Python 3.13, Railway, PostgreSQL+pgvector, Anthropic 3 tiers, OpenAI embeddings.
Repo `github.com/per1gyom/couffrant-assistant` main.

## 2. État 12/04/2026 soir
**PHASES 5A, 5B, 5C : TERMINÉES ✅**
**PHASE 5D TERMINÉE ✅** (4/4)

| Fait | Détail |
|---|---|
| Agnosticisme LLM ✅ | Zéro import anthropic hors llm_client.py |
| Injection dynamique actions ✅ | 30-60% tokens économisés |
| Cache TTL 5min ✅ | hot_summary, teams_ctx, mail_filter |
| Hot_summary 3 niveaux ✅ | Situation + Patterns + Préférences, vectorisé |
| Structured logging ✅ | main.py + scheduler.py |
| Health check profond ✅ | DB + LLM |
| Timeout 30s ✅ | /raya |
| Rate limiting ✅ | 60 req/h |
| Admin audit log ✅ | 10 actions loguées |
| APScheduler complet ✅ | Webhooks + tokens + decay + audit + expire |
| user_tenant_access ✅ | Table many-to-many créée + migration données |
| Admin secours ✅ | Configurable par env BACKUP_ADMIN_* |
| **get_user_tenants() ✅** | Retourne tous les tenants d'un user avec rôle + nom |
| **RAG multi-tenant ✅** | search_similar + retrieve_* acceptent tenant_ids (liste) |
| **LEARN avec tenant cible ✅** | Format [ACTION:LEARN:cat\|rule\|tenant] + _user pour règles perso |
| **Prompt multi-tenant ✅** | build_system_prompt injecte le contexte de TOUS les tenants dirigeant |
| **Core multi-tenant ✅** | _raya_core charge user_tenants et les passe au prompt builder |
| **save_rule personal=True ✅** | Règles utilisateur (tenant_id=NULL) pour mode dirigeant |

## 3. PROCHAINE ÉTAPE : 5D-4

**Onboarding par tenant.** Quand un dirigeant ajoute une nouvelle société, Raya lance
un questionnaire adapté au métier (photovoltaïque ≠ événementiel). Les questions sont
générées par le moteur d'élicitation existant.

Après 5D-4 : Phase 5E.

## 4. ROADMAP
~~5A~~ → ~~5B~~ → ~~5C~~ → ~~5D~~ → **5E** → 5G → 5F → Phase 7 (Jarvis) → Phase 6.
Voir `docs/raya_roadmap_v2.md`.

## 5. Utilisateurs
- **Guillaume Perrin** — Couffrant Solar. MS365 + Odoo. ~10 boîtes mail.
- **Charlotte Couffrant** — Juillet (événementiel). Gmail + LinkedIn + Instagram. Beta ~mi-juin.

## 6. Modèle prompt Sonnet
```
Projet Raya — Tâche [NUM] assignée par Opus.
Repo `per1gyom/couffrant-assistant` branche `main`. Pousse directement.
[PROBLÈME]
Ce que tu dois faire : [INSTRUCTIONS]
Commit message : `[TYPE](scope): description — [NUM]`
Rapport pour Opus : fichier(s), ligne(s), SHA.
```

## 7. Reprise
« Bonjour Opus. Projet Raya, Guillaume. On se tutoie, en français, vocabulaire Terminal, concis. Lis `docs/raya_session_state.md` puis `docs/raya_roadmap_v2.md` sur `per1gyom/couffrant-assistant` main via GitHub MCP. Règle d'or : aucune écriture sans mon ok. Reprends où on en était. »

## 8. RÈGLE
À chaque jalon, Opus met à jour ce fichier + `docs/raya_changelog.md`. Non négociable.

## 9. Commits 5D-2 (12/04/2026)
| SHA | Message |
|---|---|
| `9a7eca4` | feat(tenant): get_user_tenants() — 5D-2a |
| `1b899cf` | feat(embedding): search_similar multi-tenant — 5D-2b |
| `40b3f87` | feat(rag): multi-tenant retrieval — 5D-2c |
| `d124ed4` | feat(actions): LEARN with tenant target + personal flag — 5D-2d |
| `4fbcc8b` | feat(actions): LEARN with tenant target parsing — 5D-2d |
| `eb44268` | feat(context+raya): multi-tenant prompt + core wiring — 5D-2e/5D-2f |
