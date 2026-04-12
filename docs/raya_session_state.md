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

### Ce qui rend Raya unique (discussion du 12/04/2026 soir)

Trois propriétés combinées qu'aucun outil n'offre :

**1. Compréhension cumulative.** Raya connaît les dossiers, les interlocuteurs, les habitudes, les priorités. Pas parce qu'on lui a fait une fiche — parce qu'elle observe depuis des semaines/mois. Chaque jour elle comprend mieux. Un assistant humain mettrait 6 mois.

**2. Vision transversale.** Guillaume a 10 boîtes mail, plusieurs sociétés, des outils éparpillés. Personne — pas même lui — n'a une vision unifiée en temps réel. Raya oui. "Dupont relance sur Couffrant Solar ET sa facture Juillet est en retard."

**3. Intelligence de workflow (FONDAMENTAL).** Raya ne surveille pas que les mails. Elle observe COMMENT l'utilisateur travaille à travers TOUS ses outils. Exemples concrets :

- **Séquences apprises** : "Quand Guillaume reçoit un mail chantier, il ouvre le dossier Drive, vérifie le devis Odoo, puis répond." Après 5 occurrences, Raya connaît cette séquence.
- **Anticipation** : "Tu viens de recevoir un mail chantier Dupont. Voici le dossier Drive et le résumé Odoo — prêt."
- **Détection d'oublis** : "Tu as répondu au client mais tu n'as pas mis à jour le statut Odoo comme d'habitude. Oubli ?"
- **Amélioration** : "Tu fais cette séquence 3 fois par semaine. Je peux la faire pour toi automatiquement."
- **Détection d'anomalies** : "Le devis Odoo dit 12k€ mais le mail fournisseur mentionne 15k€. Écart à vérifier."

C'est ce qui fait de Raya un outil indispensable. Avec le temps, sa compréhension des tâches et responsabilités de son utilisateur devient d'une puissance phénoménale. C'est ça le projet novateur.

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
| 5D Multi-tenant | ✅ | user_tenant_access, RAG cross-tenant, LEARN ciblé par tenant, prompt multi-société |
| 5E Conscience + Proactivité | ✅ | Capacités par user, descriptions fonctionnelles, triage 3 niveaux, scan 30min, Twilio WhatsApp |
| 5G Maturité | ✅ | Score 3 phases, params adaptatifs, patterns (5 types), hot_summary évolutif |
| 5F Dashboard | ✅ | /admin/costs, versioning règles + rollback, aria_actions splitté en 6 modules |

## 3. ARCHITECTURE CLÉ (pour le prochain Opus)

### Fichiers critiques
- `app/routes/raya.py` — endpoint /raya, _raya_core(), charge user_tenants
- `app/routes/aria_context.py` — build_system_prompt() (prompt principal)
- `app/routes/actions/` — 6 sous-modules (confirmations, mail, drive, teams, memory, __init__)
- `app/rag.py` — RAG complet, supporte tenant_ids (liste)
- `app/embedding.py` — search_similar supporte tenant_ids
- `app/router.py` — routage tier + detect_session_theme + detect_query_domains + route_mail_action
- `app/maturity.py` — score maturité + params adaptatifs
- `app/proactive_alerts.py` — CRUD alertes + notification WhatsApp
- `app/scheduler.py` — 7 jobs APScheduler
- `app/tenant_manager.py` — CRUD tenants + get_user_tenants()
- `app/memory_rules.py` — save_rule(personal=True), rollback_rule()
- `app/capabilities.py` — get_user_capabilities_prompt(username, tools)
- `app/tools_registry.py` — 23 outils avec functional_description
- `app/connectors/twilio_connector.py` — WhatsApp + SMS
- `app/llm_client.py` — SEUL point d'entrée LLM (agnostic)

## 4. PROCHAINE ÉTAPE : Phase 7 (Jarvis)

### Vision Phase 7 (discussion Guillaume 12/04/2026 soir)

Phase 7 n'est PAS "ajouter des notifications". C'est le moment où Raya passe
de RÉACTIVE à PROACTIVE. Elle devient un collaborateur indispensable.

**Deux axes de proactivité :**

**Axe 1 — Filtre intelligent (roadmap existante)** : Raya surveille les entrées
(mails, Teams, calendrier) et filtre/alerte/agit. Entonnoir 5 étages.

**Axe 2 — Intelligence de workflow (nouveau, clé du projet)** : Raya observe
COMMENT l'utilisateur travaille à travers ses outils. Elle apprend les séquences
d'actions, détecte les oublis, repère les anomalies, et propose des améliorations.
C'est ce qui la rend véritablement indispensable avec le temps.

Concrètement il faudra :
- Table `activity_log` : logger les actions faites via Raya (quoi, quand, sur quoi)
- Étendre le moteur de patterns (5G-4) pour analyser les SÉQUENCES D'ACTIONS cross-outils
- Étendre le proactivity_scan pour vérifier "séquence habituelle suivie ?"
- En phase Maturité : proposer d'automatiser les séquences répétitives

### Priorités Phase 7

1. **7-10 Mode ombre** — calibration du jugement avant d'agir seule
2. **7-2 Modèle d'urgence enrichi** — score 0-100, certitude, escalade Opus
3. **7-1 Multi-mailbox** — voir toutes les boîtes (Microsoft + Gmail)
4. **7-3 WhatsApp structuré** — messages avec résumé + options d'action
5. **7-NEW Activity log + workflow patterns** — observer les processus de travail
6. **7-5 Préférences de sollicitation** — plages horaires, VIP, contexte calendrier
7. **7-6 Heartbeat matinal** — preuve de vie quotidienne

DÉJÀ FAIT : Twilio connector, proactive_alerts, notification WhatsApp,
triage 3 niveaux, route_mail_action, moteur de patterns. Le socle est là.

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
- `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_WHATSAPP_FROM`
- `NOTIFICATION_PHONE_GUILLAUME=+33xxxxxxxxx`
