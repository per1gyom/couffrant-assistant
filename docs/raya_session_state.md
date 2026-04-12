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
- **Prompts pour Sonnet : Opus les donne directement dans le chat, pas dans des fichiers.**

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
**TOUTES LES PHASES 5 TERMINÉES ✅** (5D-4 + 5G-7 reportés)
**PROCHAINE : PHASE 7** (Jarvis complet)

| Phase | Statut | Résumé |
|---|---|---|
| 5A Sécurité | ✅ | Mot de passe, cookie, rate limit, audit log |
| 5B Prompt | ✅ | Injection dynamique, hot_summary, cache, dédupe |
| 5C Robustesse | ✅ | Structured logging, health check, timeout |
| 5D Multi-tenant | ✅ | user_tenant_access, RAG cross-tenant, LEARN ciblé, prompt multi-société |
| 5E Conscience + Proactivité | ✅ | Capacités par user, descriptions fonctionnelles, triage 3 niveaux, scan 30min, Twilio WhatsApp |
| 5G Maturité | ✅ | Score 3 phases, params adaptatifs, prompt adaptatif, moteur patterns, hot_summary évolutif |
| 5F Dashboard | ✅ | /admin/costs, versioning règles + rollback, aria_actions splitté en 6 modules |

Reporté : 5D-4 (onboarding par tenant), 5G-7 (modèle générique — après Charlotte).

## 3. PROCHAINE ÉTAPE : Phase 7 (Jarvis)

La destination finale. Raya devient le filtre intelligent entre le monde et l'utilisateur.
Voir `docs/raya_roadmap_v2.md` section Phase 7 pour le détail des 10 tâches (7-1 à 7-10).

Priorités immédiates :
- 7-1 : Multi-mailbox (Microsoft + Gmail)
- 7-2 : Modèle d'urgence enrichi (score 0-100)
- 7-3 : Canal sortant WhatsApp structuré
- 7-10 : Mode ombre (shadow mode) — calibration avant mise en production

## 4. ROADMAP
~~5A~~ → ~~5B~~ → ~~5C~~ → ~~5D~~ → ~~5E~~ → ~~5G~~ → ~~5F~~ → **Phase 7** → Phase 6.

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

## 9. Variables Railway à configurer
Pour activer Jarvis minimal (notifications WhatsApp) :
- `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_WHATSAPP_FROM`
- `NOTIFICATION_PHONE_GUILLAUME=+33xxxxxxxxx`
