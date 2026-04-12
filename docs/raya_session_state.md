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

### Ce qui rend Raya unique — les 8 dimensions (discussion 12/04/2026)

**1. Compréhension cumulative.** Raya observe depuis des semaines/mois. Chaque jour elle comprend mieux. Un assistant humain mettrait 6 mois.

**2. Vision transversale.** 10 boîtes mail, plusieurs sociétés, outils éparpillés. Personne n'a cette vision unifiée en temps réel. Raya oui.

**3. Intelligence de workflow.** Raya observe COMMENT l'utilisateur travaille à travers TOUS ses outils : séquences apprises (mail → Drive → Odoo → réponse), anticipation des prochaines étapes, détection d'oublis ("tu n'as pas mis à jour Odoo comme d'habitude"), proposition d'améliorations ("tu fais ça 3x/semaine, je peux automatiser"), détection d'anomalies cross-outils ("le devis Odoo dit 12k€ mais le mail dit 15k€").

**4. Mémoire narrative des dossiers.** Pas juste des règles — l'HISTOIRE d'un dossier. "Le projet Dupont a commencé en janvier, 3 retards, dernier devis 15k€, relation tendue depuis le dépassement de mars."

**5. Préparation anticipée.** Réunion demain dans le calendrier → Raya prépare : derniers mails, statut Odoo, documents Drive, points en suspens. Briefing WhatsApp le matin même.

**6. Intelligence d'équipe.** Raya comprend l'équipe à travers les échanges. "Pierre gère les raccordements, Marie l'administratif." Mail raccordement → "D'habitude Pierre s'en charge, je lui transfère ?"

**7. Conscience du rythme business.** Fin de mois = factures. Fin de trimestre = reporting. "On est le 28, 3 factures en retard totalisant 24k€."

**8. Méta-apprentissage.** Raya apprend de ses propres erreurs. "Je me trompe souvent sur le financier → je confirme davantage dans ce domaine."

### Les 3 modes d'utilisation de Raya

Il faut bien distinguer le dirigeant multi-tenant et l'admin managérial d'un tenant. Ce sont deux rôles différents, parfois portés par la même personne.

**Mode 1 — Raya personnelle du dirigeant (multi-tenant)**
Guillaume voit TOUTES ses sociétés (Couffrant Solar, Juillet, etc.) + ses comptes perso (mails perso, données perso s'il le souhaite). Vision transversale totale. Personne d'autre ne voit cette vue. C'est son cerveau privé. Techniquement : user avec plusieurs entrées dans `user_tenant_access` + un espace personnel (tenant_id=NULL).

**Mode 2 — Raya professionnelle du collaborateur (mono-tenant)**
Pierre chez Couffrant Solar a accès à Raya pour son travail. Il ne voit que le tenant Couffrant Solar. Raya apprend ses habitudes de travail, l'aide dans ses tâches pro. L'admin du tenant (Guillaume) peut voir des MÉTRIQUES sur comment Pierre travaille (supervision managériale) — mais PAS lire ses conversations avec Raya ni ses données personnelles.

**Mode 3 — Raya perso du collaborateur (avantage en nature)**
Guillaume peut décider d'offrir à Pierre un accès PERSONNEL à Raya — comme un avantage en nature (mutuelle, véhicule de fonction). Pierre peut alors connecter ses mails perso, son agenda perso. Cet espace est 100% PRIVÉ : Guillaume ne le voit PAS, même en tant qu'admin. Zéro supervision sur l'espace perso. Activé par l'admin via un flag "personal_space_enabled" par utilisateur.

Ce 3e mode est un levier commercial puissant :
- Augmente l'engagement (usage pro + perso = indispensable)
- Fidélise les collaborateurs (c'est un vrai bénéfice)
- Accélère l'apprentissage de Raya (plus d'interactions = plus de données)
- Effet de réseau : plus les gens l'utilisent, plus la valeur augmente

### Supervision managériale (admin d'un tenant)

L'admin d'un tenant (souvent le gérant) a accès à une couche de supervision :
- Statistiques par collaborateur : activité, temps de traitement, processus suivis
- Identification des meilleures pratiques : si Pierre fait en 3 étapes ce que Marie fait en 5
- Transfert de compétences : Raya suggère à Marie une meilleure méthode observée chez Pierre
- Tableau de bord d'efficacité de l'équipe : tendances, progrès, points de friction
- Rapport Guillaume : "L'efficacité sur les raccordements a progressé de 20% ce mois"

Frontière stricte : l'admin voit les MÉTRIQUES et PATTERNS, jamais le CONTENU des conversations ni les données personnelles (Mode 3).

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

### Les 4 piliers de Phase 7

**Pilier 1 — Filtre intelligent** (roadmap 7-1 à 7-10)
Surveiller toutes les entrées, trier, alerter au bon moment par le bon canal.

**Pilier 2 — Intelligence de workflow**
activity_log, séquences cross-outils, détection d'oublis, proposition d'améliorations, automatisation des tâches répétitives.

**Pilier 3 — Mémoire narrative + Préparation anticipée**
Historique vivant par dossier/contact, briefings automatiques avant réunions, conscience du rythme business.

**Pilier 4 — Supervision managériale**
Vue admin sur l'équipe : métriques par collaborateur, meilleures pratiques, transfert de compétences, tableau de bord d'efficacité. Cloisonnement strict : métriques oui, contenu conversations non.

### Priorités immédiates

1. **7-10 Mode ombre** — calibration du jugement
2. **7-2 Modèle d'urgence enrichi** — score 0-100
3. **7-1 Multi-mailbox** — Microsoft + Gmail
4. **7-3 WhatsApp structuré** — résumé + options
5. **7-NEW Activity log + workflow patterns**
6. **7-5 Préférences de sollicitation**
7. **7-6 Heartbeat matinal**

DÉJÀ FAIT : Twilio connector, proactive_alerts, notification WhatsApp,
triage 3 niveaux, route_mail_action, moteur de patterns.

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
