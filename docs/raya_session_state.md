# Raya — État de session vivant

**Dernière mise à jour : 13/04/2026 après-midi** — Opus

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
- **Opus = architecte. Sonnet = exécutant.**
- **Repo local Mac abandonné.** Tout via GitHub.

## 1. Stack
FastAPI Python 3.13, Railway, PostgreSQL+pgvector, Anthropic 3 tiers, OpenAI embeddings.
Repo `github.com/per1gyom/couffrant-assistant` main.

## 2. État 13/04/2026
**PHASES 5A, 5B, 5C : TERMINÉES ✅**
**PHASE 5D EN COURS (2/4)** — 5D-1 table user_tenant_access ✅, 5D-3 admin secours ✅

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

## 3. PROCHAINE ÉTAPE : 5D-2

**Contexte multi-tenant dans le prompt.** C'est la tâche la plus complexe :
- Créer une fonction `get_user_tenants(username)` qui interroge `user_tenant_access`
- Modifier `build_system_prompt` pour injecter le contexte de TOUS les tenants d'un dirigeant
- Modifier le RAG (`retrieve_context`) pour chercher dans tous les tenants
- Permettre à Raya de croiser : « Dupont relance sur le chantier (tenant A) ET la facture est en attente (tenant B) »

Après 5D-2 : 5D-4 (onboarding par tenant) puis Phase 5E.

## 4. ROADMAP
~~5A~~ → ~~5B~~ → ~~5C~~ → **5D** (2/4) → 5E → 5G → 5F → Phase 7 (Jarvis) → Phase 6.
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
