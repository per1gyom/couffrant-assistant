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

**Opus = architecte.** Il audite le code via GitHub MCP, conçoit l'architecture,
rédige des prompts précis pour Sonnet. **Opus ne code PAS et ne pousse PAS de commits lui-même.**
Ses tokens sont chers — il les utilise pour la réflexion, la conception,
et la durée de session. Plus Opus économise ses tokens, plus la session dure longtemps.

**Sonnet = exécutant.** Il reçoit les prompts d'Opus (copiés par Guillaume),
code les modifications, et pousse directement sur `main` via GitHub MCP.

**Le cycle :**
1. Opus lit le code via GitHub MCP (`get_file_contents`), identifie les changements
2. Opus rédige des prompts Sonnet précis (fichier, fonction, lignes, format commit)
3. Opus donne les prompts directement dans le chat (entre barres de code pour copier-coller)
4. Guillaume copie-colle chaque prompt dans une conversation Sonnet séparée
5. Sonnet exécute et rapporte (fichier, SHA)
6. Guillaume rapporte le résultat à Opus
7. Opus vérifie si besoin et passe à la tâche suivante

**ATTENTION :** Opus ne doit JAMAIS utiliser `push_files` pour pousser du code Python.
Le double-escaping JSON corrompt les `\n` en littéraux. Seul Sonnet pousse du code
via `create_or_update_file` qui n'a pas ce problème.

## 1. Stack
FastAPI Python 3.13, Railway, PostgreSQL+pgvector, Anthropic 3 tiers, OpenAI embeddings.
Repo `github.com/per1gyom/couffrant-assistant` main.

## 2. État 12/04/2026 soir
**TOUTES LES PHASES 5 TERMINÉES ✅** (5D-4 + 5G-7 reportés)
**PROCHAINE : PHASE 7** (Jarvis complet)

| Phase | Statut | Résumé |
|---|---|---|
| 5A Sécurité | ✅ | Mot de passe env, cookie 7j, rate limit 60/h, audit log, LLM agnostic complet |
| 5B Prompt | ✅ | Injection dynamique par domaine, hot_summary 3 niveaux, cache TTL 5min, dédupe RAG |
| 5C Robustesse | ✅ | Structured logging, health check DB+LLM, timeout 30s, APScheduler complet |
| 5D Multi-tenant | ✅ | user_tenant_access, get_user_tenants(), RAG cross-tenant, LEARN ciblé par tenant, prompt multi-société, save_rule(personal=True) pour règles user |
| 5E Conscience + Proactivité | ✅ | Capacités par user dynamiques, 23 descriptions fonctionnelles, triage webhook 3 niveaux (IGNORER/STOCKER_SIMPLE/ANALYSER), proactive_alerts table + scan 30min + injection prompt, Twilio WhatsApp connector + notifications auto sur alertes high/critical |
| 5G Maturité | ✅ | Score maturité (5 critères × 20pts → discovery/consolidation/maturity), params adaptatifs (decay+mask par phase), prompt adaptatif (3 comportements), moteur patterns (5 types, analyse hebdo Opus), patterns dans prompt (top 8), hot_summary évolutif (factuel→analytique→portrait) |
| 5F Dashboard | ✅ | /admin/costs (par tenant/user/modèle/purpose/jour), versioning règles (aria_rules_history + rollback), aria_actions.py splitté en 6 sous-modules (app/routes/actions/) |

Reporté : 5D-4 (onboarding par tenant — attendre Charlotte), 5G-7 (modèle générique — après 2 clients).

## 3. ARCHITECTURE CLÉ (pour le prochain Opus)

### Fichiers critiques
- `app/routes/raya.py` — endpoint /raya, _raya_core(), charge user_tenants
- `app/routes/aria_context.py` — build_system_prompt() (prompt principal Raya)
- `app/routes/actions/` — 6 sous-modules (confirmations, mail, drive, teams, memory, __init__)
- `app/routes/aria_actions.py` — 3 lignes de réexport (rétrocompat)
- `app/rag.py` — RAG complet, supporte tenant_ids (liste)
- `app/embedding.py` — search_similar supporte tenant_ids
- `app/router.py` — routage tier + detect_session_theme + detect_query_domains + route_mail_action
- `app/maturity.py` — score maturité + params adaptatifs
- `app/proactive_alerts.py` — CRUD alertes + notification WhatsApp
- `app/scheduler.py` — 6 jobs APScheduler (expire, decay, audit, webhook, token, proactivity, patterns)
- `app/tenant_manager.py` — CRUD tenants + get_user_tenants()
- `app/memory_rules.py` — save_rule(personal=True), rollback_rule()
- `app/capabilities.py` — get_user_capabilities_prompt(username, tools)
- `app/tools_registry.py` — 23 outils avec functional_description
- `app/connectors/twilio_connector.py` — WhatsApp + SMS
- `app/llm_client.py` — SEUL point d'entrée LLM (agnostic)

### Multi-tenant (5D-2)
- Lecture : dirigeant voit TOUS ses tenants (RAG cross-tenant via tenant_ids)
- Écriture : LEARN taggé `[ACTION:LEARN:cat|rule|tenant_id]` ou `|_user` pour perso
- Isolation : collaborateur mono-tenant = zéro changement, voit que son tenant
- Table : `user_tenant_access` (username, tenant_id, role)

### Maturité (5G)
- Score 0-100 calculé à chaque appel (1 requête SQL agrégée)
- 3 phases : discovery (<40), consolidation (40-74), maturity (75+)
- Paramètres adaptatifs (decay, mask_threshold, synth_frequency)
- Prompt comportemental injecté dans build_system_prompt
- Moteur de patterns (analyse hebdo Opus, 5 types, table aria_patterns)

### Proactivité (5E-4/5)
- proactivity_scan : job APScheduler 30min
- Crée des alertes dans proactive_alerts (5 types, 4 priorités)
- Alertes injectées dans prompt, marquées vues après
- Si priority high/critical : notification WhatsApp via Twilio
- Déjà prêt pour Phase 7 (socle Jarvis minimal)

## 4. PROCHAINE ÉTAPE : Phase 7 (Jarvis)

La destination finale. Voir `docs/raya_roadmap_v2.md` section Phase 7 (10 tâches).

Priorités immédiates :
- 7-1 : Multi-mailbox (Microsoft webhook existant + Gmail API/polling)
- 7-2 : Modèle d'urgence enrichi (score 0-100, certitude, escalade Opus)
- 7-3 : Canal WhatsApp structuré (Twilio connector existe déjà)
- 7-10 : Mode ombre (shadow mode) — calibration avant mise en prod

DÉJÀ FAIT pour Phase 7 : Twilio connector, proactive_alerts, notification WhatsApp,
triage 3 niveaux dans webhook, route_mail_action. Le socle est là.

## 5. ROADMAP
~~5A~~ → ~~5B~~ → ~~5C~~ → ~~5D~~ → ~~5E~~ → ~~5G~~ → ~~5F~~ → **Phase 7** → Phase 6.

## 6. Utilisateurs
- **Guillaume Perrin** — Couffrant Solar. MS365 + Odoo. ~10 boîtes mail.
- **Charlotte Couffrant** — Juillet (événementiel). Gmail + LinkedIn + Instagram. Beta ~mi-juin.

## 7. Modèle prompt Sonnet
```
Projet Raya — Tâche [NUM] assignée par Opus.
Repo `per1gyom/couffrant-assistant` branche `main`. Pousse directement.
[PROBLÈME]
Ce que tu dois faire : [INSTRUCTIONS]
Commit message : `[TYPE](scope): description — [NUM]`
Rapport pour Opus : fichier(s), ligne(s), SHA.
```

## 8. Reprise
« Bonjour Opus. Projet Raya, Guillaume. On se tutoie, en français, vocabulaire Terminal, concis. Lis `docs/raya_session_state.md` puis `docs/raya_roadmap_v2.md` sur `per1gyom/couffrant-assistant` main via GitHub MCP. Règle d'or : aucune écriture sans mon ok. Reprends où on en était. »

## 9. RÈGLE
À chaque jalon, Opus met à jour ce fichier. Non négociable.

## 10. Variables Railway à configurer
Pour activer Jarvis minimal (notifications WhatsApp) :
- `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_WHATSAPP_FROM`
- `NOTIFICATION_PHONE_GUILLAUME=+33xxxxxxxxx`
