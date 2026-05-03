# Audit isolation user↔user intra-tenant — Phase 1 Cartographie

> **Date** : 28 avril 2026 fin de soirée
> **Auteur** : session Guillaume + Claude
> **Statut** : Phase 1 (Cartographie) terminée. Phases 2-4 à attaquer dans
> les jours qui viennent.

## Contexte

L'audit isolation 25/04 (33 findings tous traités, cf.
`docs/audit_isolation_25avril_complementaire.md`) s'est focalisé sur
l'isolation **tenant↔tenant** (couffrant_solar vs juillet). Excellent
travail, validé en pratique.

**Mais l'isolation user↔user dans un même tenant** (Guillaume vs Pierre
vs Sabrina dans couffrant_solar) n'a **jamais eu d'audit dédié sérieux**.

C'est devenu critique car Guillaume veut déployer la version d'essai à
Charlotte (tenant juillet, déjà OK) + 2-3 personnes dans le tenant
couffrant_solar dans les jours qui viennent.

**Décision Guillaume 24/04** : pas de mutualisation des règles /
conversations / mails entre users d'un même tenant. Reste à valider
que cette décision est bien implémentée partout dans le code.

## Plan d'audit en 4 phases

| Phase | Description | Effort | Statut |
|---|---|---|---|
| 1 — Cartographie | Lister toutes les tables sensibles, classer | ~1h | ✅ Ce doc |
| 2 — Audit code | Audit fichier par fichier des tables Cat A | ~2-3h | 🔴 À faire |
| 3 — Remédiation | Fixer les trous trouvés (LOTs commitables) | ~1-3h | 🔴 À faire |
| 4 — Tests pierre_test | Validation pratique avec un user fictif | ~1h | 🔴 À faire |

## Méthodologie Phase 1

1. Liste de toutes les tables `public` qui ont au moins une colonne de scope
   (`tenant_id`, `username`, `user_id`, `created_by`, `owner_username`).
2. Classification de chaque table en 3 catégories :
   - **Cat A** — Filtrage `username` OBLIGATOIRE (donnée privée user)
   - **Cat B** — Partagé tenant (filtre `tenant_id` seulement)
   - **Cat C** — Gestion users (cas particuliers)
3. Vérification structurelle : PKs et contraintes UNIQUE.
4. Findings préliminaires à creuser en Phase 2.

## Inventaire — 53 tables avec scope identifiées

### Cat A — Filtrage `username` OBLIGATOIRE (38 tables)

> Ces tables contiennent des données strictement personnelles à un user.
> Si un autre user lit la donnée, c'est une fuite. **Tous les SELECT, INSERT,
> UPDATE, DELETE doivent filtrer sur `username`** en plus de `tenant_id`.

#### A.1 — Mémoire et apprentissage (12 tables)

| Table | Contenu | Sensibilité |
|---|---|---|
| `aria_memory` | Conversations user ↔ Raya | 🔴 Critique |
| `aria_rules` | Règles apprises par user | 🔴 Critique |
| `aria_rules_history` | Historique modifications règles | 🟠 Important |
| `aria_rule_audit` | Audit règles | 🟠 Important |
| `aria_insights` | Insights perso extraits | 🟠 Important |
| `aria_patterns` | Patterns détectés | 🟠 Important |
| `aria_profile` | Profil user (signature, prefs) | 🟠 Important |
| `aria_response_metadata` | Métadata réponses Raya | 🟠 Important |
| `aria_session_digests` | Résumés de sessions | 🟠 Important |
| `aria_style_examples` | Exemples de style rédactionnel | 🟠 Important |
| `aria_onboarding` | État onboarding user | 🟢 Attention |
| `aria_hot_summary` | Résumé "chaud" user | 🟠 Important |

#### A.2 — Mails (4 tables)

| Table | Contenu | Sensibilité |
|---|---|---|
| `mail_memory` | Mails reçus du user (32 colonnes !) | 🔴 Critique |
| `sent_mail_memory` | Mails envoyés du user | 🔴 Critique |
| `email_signatures` | Signatures du user | 🟢 Attention |
| `reply_learning_memory` | Apprentissage par diff réponses | 🟠 Important |

#### A.3 — Tokens et auth (3 tables)

| Table | Contenu | Sensibilité |
|---|---|---|
| `gmail_tokens` | Tokens Gmail user (legacy) | 🔴 Critique |
| `oauth_tokens` | Tokens OAuth user (Microsoft, Gmail) | 🔴 Critique |
| `password_reset_tokens` | Tokens reset mot de passe | 🟠 Important |

#### A.4 — UI / personnalisation (4 tables)

| Table | Contenu | Sensibilité |
|---|---|---|
| `user_shortcuts` | Raccourcis sidebar user | 🟢 Attention |
| `user_topics` | Sujets "Mes sujets" du user | 🟢 Attention |
| `user_tools` | Outils activés par user | 🟢 Attention |
| `connection_assignments` | Assignment connexions ↔ users | 🟠 Important |

#### A.5 — Workflows et actions (5 tables)

| Table | Contenu | Sensibilité |
|---|---|---|
| `pending_actions` | Actions en attente confirmation | 🟠 Important |
| `agent_continuations` | Continuations agent multi-tour | 🟠 Important |
| `elicitation_sessions` | Sessions élicitation Raya | 🟢 Attention |
| `proactive_alerts` | Alertes proactives user | 🟠 Important |
| `daily_reports` | Rapports journaliers user | 🟠 Important |

#### A.6 — Apprentissage règles (3 tables)

| Table | Contenu | Sensibilité |
|---|---|---|
| `rule_modifications` | Modifs règles user | 🟠 Important |
| `rules_optimization_log` | Log optim règles | 🟢 Attention |
| `rules_pending_decisions` | Décisions règles en attente | 🟠 Important |

#### A.7 — Logs et audit (3 tables)

| Table | Contenu | Sensibilité |
|---|---|---|
| `activity_log` | Log activité user | 🟢 Attention |
| `permission_audit_log` | Audit permissions | 🟠 Important |
| `llm_usage` | Usage LLM par user (coûts, tokens) | 🟠 Important |

#### A.8 — Spécifiques (4 tables)

| Table | Contenu | Sensibilité |
|---|---|---|
| `dossier_narratives` | Narratifs dossiers user | 🟠 Important |
| `teams_sync_state` | État sync Teams par user | 🟢 Attention |
| `webhook_subscriptions` | Abonnements webhook par user | 🟠 Important |
| `bug_reports` | Bug reports remontés par users | 🟢 Attention |

### Cat B — Partagé tenant (15 tables)

> Ces tables contiennent des données métier partagées par tous les users
> du tenant. **Le filtrage est sur `tenant_id` seulement**, pas `username`.

| Table | Contenu | Notes |
|---|---|---|
| `tenant_connections` | Connexions outils du tenant | + `created_by` (audit) |
| `aria_contacts` | Contacts métier partagés tenant | |
| `connector_schemas` | Schemas de connecteurs | |
| `tool_schemas` | Schemas d'outils | |
| `drive_folders` | Dossiers Drive partagés | |
| `drive_semantic_content` | Contenu Drive vectorisé | |
| `odoo_semantic_content` | Contenu Odoo vectorisé | |
| `entity_links` | Liens entités legacy | |
| `semantic_graph_nodes` | Graphe nodes — métier partagé | |
| `semantic_graph_edges` | Graphe edges — métier partagé | |
| `vectorization_queue` | Queue de vectorisation | |
| `scanner_runs` | Runs du scanner | |
| `system_alerts` | Alertes système — admin | |
| `tenant_events` | Events tenant | |
| `global_instructions` | Instructions globales tenant | |

### Cat C — Gestion users (2 tables)

| Table | Notes |
|---|---|
| `users` | Filtrage par `username` pour CRUD propre user, par `tenant_id` pour list par tenant_admin. Le super_admin voit tout. |
| `user_tenant_access` | Accès cross-tenant pour super_admin (volontairement cross-tenant, cf. A.4 audit 25/04) |

## Vérifications structurelles

### Clés primaires (PKs)

✅ Toutes les 53 tables ont une PK = `id` simple.

C'est **structurellement OK** car le filtrage par `username`/`tenant_id`
se fait au niveau du WHERE applicatif, pas de la PK. Pas de bug
modélisation à signaler ici.

### Contraintes UNIQUE — 🚨 6 findings préliminaires

#### 🔴 CRITIQUE — Empêche un `username` d'exister dans plusieurs tenants

**U.1** : `users.users_username_key UNIQUE (username)`
- Un même nom d'utilisateur ne peut pas exister dans 2 tenants distincts.
- Pas un bug d'isolation user↔user **dans le même tenant** (qui est notre
  cible), mais une décision design implicite à valider.
- **Impact pratique** : si Charlotte (tenant juillet) et un autre user nommé
  "Charlotte" voulaient cohabiter dans des tenants différents, conflit.
- **Décision Guillaume requise** : on garde cette contrainte (1 username
  global) ou on migre en `UNIQUE (username, tenant_id)` ? Le statu quo est
  acceptable tant qu'on est en early stage.

**U.2** : `aria_onboarding.aria_onboarding_username_key UNIQUE (username)`
- Pareil : empêche le même user d'avoir un état d'onboarding différent par
  tenant.
- Hérité du temps mono-tenant, à passer en `UNIQUE (username, tenant_id)`.
- **Impact réel** : faible tant qu'un user n'existe que dans un seul tenant.

#### 🟠 IMPORTANT — `tenant_id` manquant dans certaines contraintes UNIQUE

**U.3** : `mail_memory.mail_memory_msg_user_unique UNIQUE (message_id, username)`
- Pas de `tenant_id`. OK fonctionnellement (un message_id Microsoft est
  globalement unique chez un user) mais pas multi-tenant safe.
- À passer en `UNIQUE (message_id, username, tenant_id)` pour cohérence.

**U.4** : `sent_mail_memory.sent_mail_msg_user_unique UNIQUE (message_id, username)`
- Même remarque.

**U.5** : `email_signatures.email_signatures_username_email_address_key UNIQUE (username, email_address)`
- Pas de `tenant_id`. À passer en `UNIQUE (username, email_address, tenant_id)`.

**U.6** : `teams_sync_state.teams_sync_state_username_chat_id_key UNIQUE (username, chat_id)`
- **Déjà identifié dans backlog hérité** ("teams_sync_state PK
  (username, chat_id) à migrer en (username, chat_id, tenant_id)").
- À traiter en même temps que les autres.

### Tables Cat A sans contrainte UNIQUE

Beaucoup de tables Cat A n'ont **pas de contrainte UNIQUE** au niveau DB.
Pour des tables comme `aria_rules`, `mail_memory` (au-delà de l'unique sur
message_id), `aria_memory`, c'est probablement intentionnel (plusieurs
rows par user). À vérifier en Phase 2 que la cohérence est bien garantie
au niveau code.

Pour des tables **singleton par user** (`aria_profile`, `aria_hot_summary`),
l'absence d'UNIQUE sur `(username, tenant_id)` est **suspecte**. Si du
code a inséré 2 fois pour le même user (race condition possible), on a
des doublons silencieux qui peuvent provoquer des bugs aléatoires
(quel row Raya lit-elle ?).

**Vérification DB 28/04 fin de soirée** : 0 doublon constaté en pratique
sur `aria_hot_summary`, `aria_profile`, `aria_onboarding`. Risque
potentiel valide pour la suite quand on aura plus de users.

## Plan Phase 2 — Audit code

Pour chaque table Cat A, on doit vérifier :
1. Tous les SELECT filtrent bien sur `username` ET `tenant_id`
2. Tous les INSERT incluent `username` ET `tenant_id`
3. Aucun JOIN cross-user accidentel

**Fichiers à auditer en priorité** (probable, à confirmer au démarrage
Phase 2 par grep ciblé sur les noms de tables Cat A) :

- `app/memory.py` (gestionnaire central aria_memory)
- `app/memory_rules.py` (gestionnaire aria_rules) ⭐ critique
- `app/feedback.py` (response_metadata + reinforcement règles)
- `app/rag.py` (retrieval sémantique)
- `app/embedding.py` (search_similar)
- `app/maturity.py` (calcul maturité par user)
- `app/connection_token_manager.py` (oauth_tokens)
- `app/jobs/gmail_polling.py` (mail_memory + sent_mail_memory)
- `app/jobs/proactivity_scan.py` (proactive_alerts)
- `app/connectors/microsoft_webhook.py` (webhook_subscriptions)
- `app/routes/raya_agent_core.py` (aria_response_metadata, agent_continuations)
- `app/routes/aria_context.py` (injection règles)
- `app/routes/profile.py` (aria_profile, email_signatures)
- `app/routes/raya.py` (pending_actions, dossier_narratives)
- `app/teams_routes.py` ou équivalent (teams_sync_state)

**Estimation Phase 2** : 2-3h pour passer en revue ces 15 fichiers.

## Synthèse Phase 1

✅ **Cartographie complète** : 53 tables classées (38 Cat A, 15 Cat B, 2 Cat C).
✅ **PKs auditées** : toutes en `id` simple, structurellement OK.
🚨 **6 findings préliminaires sur les contraintes UNIQUE** : U.1 et U.2
critiques (mais impact faible en pratique aujourd'hui), U.3-U.6 importants
(à corriger en Phase 3).

**Risque réel d'isolation user↔user** : ne peut être évalué qu'après
Phase 2 (audit du code applicatif). Mais le travail de migration multi-tenant
fait par les LOTs 2-6 du 28/04 matin laisse penser que **la majorité des
SELECT sont déjà filtrés correctement** (sinon l'audit du 25/04 aurait
explosé). Reste à valider explicitement pour le cas user↔user.

**Prochaine étape** : Phase 2 — audit code, à faire dans une session
dédiée (~2-3h).
