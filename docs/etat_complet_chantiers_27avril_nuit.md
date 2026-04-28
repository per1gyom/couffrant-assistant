# 📊 État complet des chantiers — 27 avril 2026 nuit

> **Auteur** : Claude, à la demande de Guillaume. **But** : faire un tri propre de TOUT ce qui est fait, en cours, à faire, pour préparer demain à frais. **Méthode** : lecture systématique de tous les docs + vérification en code/git/DB. **Statut** : DOCUMENT EN COURS DE CONSTRUCTION — ne pas effacer.

---

## 🎯 Sommaire

1. [Chantiers de la session 27/04 (aujourd'hui)](#chantiers-2704)
2. [Audit isolation multi-tenant — état précis](#audit-isolation)
3. [Audit graphes — état précis](#audit-graphes)
4. [Autres chantiers en cours](#autres-chantiers)
5. [Idées notées pour plus tard](#idees-notees)
6. [Synthèse priorisée pour demain](#synthese-demain)

---

## 1. Chantiers de la session 27/04 — TERMINÉS ✅

11 commits déployés en prod aujourd'hui (du plus ancien au plus récent) :

#CommitQuoi1`02019e1`Étape 0 : normalisation tenant `couffrant` → `couffrant_solar`. 13 occurrences hardcodées corrigées dans le code + variable Railway renommée. Migration DB : 840 563 lignes basculées en transaction unique sur 7 tables, 0 conflit.2`2a771f6`Étape 1 graphage : refonte du graphage des conversations. Création du module `app/conversation_entities.py` (collecteur d'entités via ContextVar), branchement dans 4 outils (search_graph, search_odoo, search_drive, get_client_360) + boucle agent.3`20bf2cd`Fix requête SQL cassée du collecteur (filtre par node_type pertinents). Validation : conv 405 a créé 67 edges automatiquement.4`48af2f9`Suppression du job `graph_indexer` (376 lignes obsolètes). Remplacé par graphage temps réel.5`f81f5f8`Fix metadata feedback en mode V2 : `_load_user_preferences` retourne tuple `(text, rule_ids, via_rag)`. `save_response_metadata` appelée en thread background après chaque conversation.6`dc95e86`Notes des 3 anomalies découvertes au test (👍 ne s'enregistre pas, badge Sonnet superposé, planning sans détail).7`7f4e28a`Fix TypeError silencieux sur le 👍. JSONB désérialisé en list par psycopg2 → `json.loads(list)` plantait silencieusement dans le thread daemon. Fix isinstance dans 3 fonctions.8`3977980`Fix UI badge Sonnet superposé. padding-top 22px sur la bulle. Bump cache v=79→v=80.9`2874fea`Doc : audit révèle que le refactor formats de clés est trivial (1881/1894 anciens noeuds = doublons des nouveaux).10`af50b16`Fix mapping `_enrich_with_graph` : 17 modèles (vs 7) au nouveau format `odoo:res.partner:3795`. Ajout Tour, TourStop, Task. Bug 3 du planning corrigé.11`f581f58`Nettoyage anciens noeuds : suppression du fichier `app/jobs/odoo_vectorize.py` (797 lignes legacy) + endpoint admin obsolète. Migration DB : DELETE 1894 noeuds + 2517 edges en transaction. État final : 100% format moderne.

### Bilan factuel

DomaineAvantAprèsTenant orphelin `couffrant` (sans `_solar`)840 563 lignes0Edges sur conversations0 (graph_indexer cassé)67 sur conv 405Metadata feedback0 depuis le 21/04Stockée à chaque échange👍 fonctionnelNon (TypeError silencieux)Oui, renforce les règlesBadge SonnetSuperposait le texteBien positionnéFormat clés graphe2 formats parallèles100% moderneMapping `_enrich_with_graph`7 modèles, ancien format17 modèles, nouveau formatCode legacy`odoo_vectorize.py` (797 lignes)Supprimé

---

## 2. Audit isolation multi-tenant — état précis

### Document de référence

`docs/audit_isolation_25avril_complementaire.md` (758 lignes, créé le 25/04 soir).

Bilan des findings à l'époque :

- 🔴 CRITIQUE : 8 — Étapes 0+A déployées le 26/04, théoriquement tous fixés
- 🟠 IMPORTANT : 15 — Statut à vérifier individuellement (vérification ci-dessous)
- 🟡 ATTENTION : 10 — Statut à vérifier individuellement

### Liste exhaustive des 25 findings — état vérifié

⏳ Vérification en cours en ouvrant chaque fichier mentionné dans l'audit pour voir si la requête mentionne désormais `tenant_id`.

### Vérification individuelle des findings (réalisée 27/04 nuit)

**Méthode** : pour chaque finding, j'ai ouvert le fichier mentionné et regardé si la requête / l'endpoint mentionne désormais `tenant_id` ou si le bug est toujours présent.

#### 🟠 IMPORTANT — État actuel

IDFichierStatutPreuve / ObservationI.1`app/routes/admin/profile.py:248`❌ NON FIXÉ`SELECT COUNT(*) FROM aria_rules WHERE username=%s` toujours sans tenant_idI.2`app/routes/admin/profile.py:254`❌ NON FIXÉ`FROM sent_mail_memory WHERE username=%s` toujours sans tenant_idI.3`app/routes/admin/profile.py:260`❌ NON FIXÉ`FROM aria_session_digests WHERE username=%s`I.4`app/routes/admin/profile.py:267`❌ NON FIXÉ`FROM sent_mail_memory ...` (contacts)I.5`app/routes/admin/profile.py:311`❌ NON FIXÉ`FROM oauth_tokens WHERE username = %s`I.6`app/routes/admin/profile.py:427`❌ NON FIXÉ`FROM llm_usage WHERE username = %s`I.7`app/memory_teams.py:33`❌ NON FIXÉ`FROM teams_sync_state WHERE username = %s`I.8`app/memory_teams.py:85`❌ NON FIXÉ`DELETE FROM teams_sync_state WHERE username=%s AND chat_id=%s`I.9`app/synthesis_engine.py:171`❌ NON FIXÉ`UPDATE aria_hot_summary SET embedding = %s WHERE username = %s`I.10`app/routes/actions/report_actions.py:21`❌ NON FIXÉ`FROM daily_reports WHERE username = %s AND report_date = CURRENT_DATE`I.11`POST /admin/create-user`✅ FIXÉCommentaire explicite "Durci le 26/04 (etape B.1a-1)". Validation scope, blocage cross-tenant si pas super_admin, retrait fallback DEFAULT_TENANT.I.12`POST /admin/drive/select`❌ NON FIXÉ`tenant_id = (payload.get("tenant_id") or "").strip()` lu sans contrôleI.13`POST /admin/sharepoint/select`❌ NON FIXÉPareil que I.12I.14`app/connection_token_manager.py` `_get_v2_token`, `_get_v2_email`❌ NON FIXÉJOIN `tenant_connections` sans filtre tenant_idI.15bug `scope != "admin"` (super_admin bloqué)❌ NON FIXÉ5 occurrences trouvées : `super_admin.py:657, 670, 707, 721` + `rgpd.py:150`

#### 🟡 ATTENTION — État actuel

IDFichierStatutPreuve / ObservationA.1`super_admin_users.py:249`❌ NON FIXÉ`FROM aria_rules WHERE username=%s`A.2`super_admin_users.py:275`❌ NON FIXÉ`FROM aria_insights WHERE username=%s`A.3`super_admin_users.py:705`❌ NON FIXÉ`UPDATE aria_memory SET archived = true WHERE username = %s`A.4`super_admin_users.py:743`❌ NON FIXÉ`FROM aria_memory WHERE username = %s`A.5`outlook_calendar.py:32` `_build_email_html(username="guillaume")`❌ NON FIXÉLe default `"guillaume"` est toujours làA.6Magic strings `"admin"`🟡 PARTIEL1 occurrence restante (`hardcoded_permissions.py:92`) — à vérifier si intentionnelA.7-A.10Bug logique scope❌ Inclus dans I.15—

### Bilan honnête

**Sur 25 findings de l'audit du 25/04 :**

- ✅ 1 fixé (I.11 = `POST /admin/create-user`)
- 🟡 1 partiel (A.6, presque clean)
- ❌ 23 toujours ouverts

**Donc l'étape C de l'audit isolation n'a quasi pas été touchée.** Le commentaire dans `a_faire.md` qui dit "🚧 À FAIRE : Étape C (15 IMPORTANT + 10 ATTENTION)" reflète bien la réalité.

### Pourquoi ce n'est pas critique pour l'instant

Le système actuel a :

- 5 users dans `couffrant_solar` (tous Couffrant)
- 1 user dans `juillet` (Charlotte)
- **Aucun homonyme cross-tenant**

Les findings IMPORTANT et ATTENTION sont des **fuites latentes** : ils deviennent réels uniquement si un homonyme existe entre 2 tenants. Tant que ce n'est pas le cas, pas de fuite réelle observée.

Mais : **avant d'onboarder Pierre, Sabrina, Benoît ou un nouveau tenant**, il faudra avoir corrigé tout ça. Surtout I.11→I.13 (endpoints admin acceptant tenant_id arbitraire) qui sont de vraies portes ouvertes.

### Estimation de l'effort

- **I.1-I.10** (requêtes SQL [profile.py](http://profile.py) + memory_teams.py + synthesis_engine.py + report_actions.py) : \~30 min de fixes mécaniques (ajouter `AND tenant_id = %s`)
- **I.12, I.13** (endpoints drive/sharepoint select) : \~20 min (forcer `tenant_id = admin["tenant_id"]` si scope != super_admin)
- **I.14** (connection_token_manager) : \~30 min (ajouter `AND tc.tenant_id = %s` dans 2 fonctions + propager le tenant_id depuis l'appelant)
- **I.15** (bug scope != admin) : \~30 min (remplacer par `if user["scope"] not in (SCOPE_ADMIN, SCOPE_SUPER_ADMIN):`)
- **A.1-A.4** (super_admin_users.py) : \~20 min, faible priorité (super_admin only)
- **A.5** (default "guillaume") : \~5 min
- **A.6** (1 magic string restante) : \~5 min

**Total : \~2h30 pour tout fermer proprement.**

---

## 3. Audit système de graphes — état précis

### Document de référence

`docs/audit_systeme_graphes_27avril.html` (rapport interactif Mermaid livré aujourd'hui).

### État

L'audit a identifié 2 systèmes de graphes coexistants :

- **V1 =** `entity_links` (créé le 17/04, commit `ff59146`) — vue à plat utilisée par le **CŒUR de Raya** : `aria_context.py` via `build_team_roster_block` + `get_entity_context_text`
- **V2 =** `semantic_graph_nodes/edges` (créé le 18/04, commit `2dd6402`) — graphe typé multi-hop utilisé par les **OUTILS** : `retrieval.py`, `raya_tool_executors.py`

### Ce qui a été fait aujourd'hui (Étape 1)

- ✅ Refonte du graphage des conversations (collecteur d'entités)
- ✅ Suppression du job `graph_indexer` obsolète
- ✅ Migration tenant `couffrant` → `couffrant_solar` (840k lignes)
- ✅ Mapping `_enrich_with_graph` au nouveau format de clés
- ✅ Suppression des 1 894 anciens noeuds + 2 517 edges (doublons)
- ✅ Suppression du fichier `odoo_vectorize.py` (797 lignes legacy)

### Ce qui reste pour les graphes

ÉtapeQuoiEffortPrioritéÉtape 2Migration cœur V1 (`entity_links`) → V2 (`semantic_graph`)3-5hMoyenneÉtape 3Suppression définitive de `entity_links` une fois V2 branché partout30 minAprès étape 2Étape futureRefonte profonde du système de mise en grapheÀ évaluerAvec prestataire spécialisé (décision Guillaume)Sous-bugComportement agentique multi-tour : Raya creuse-t-elle quand le graphe ne montre que des labels techniques ?À tester demain (3-4 questions)HauteSous-bug12 partners orphelins (encore actifs dans odoo_semantic_content mais sans noeud graphe)30 min via re-scan cibléFaible

---

## 4. Autres chantiers en cours / à faire (extraits de `docs/a_faire.md`)

### 🔴 Priorité 1 — Audit isolation multi-tenant

**Statut** : ✅ Étape 0 + A déployées le 26/04 · ❌ Étape C non démarrée · ❓ Étape D partielle.

Voir section 2 ci-dessus pour le détail. **23 findings sur 25 toujours ouverts**, 2h30 estimées pour fermer proprement.

### 🟠 Priorité 2 — Connexion simplifiée des outils tiers (panel admin tenant)

**Statut** : ⏳ Non démarré.

**Objectif** : permettre à un tenant_admin (ou super_admin) d'ajouter facilement un connecteur (Gmail, SharePoint, Drive, etc.) sans avoir à faire 5 fichiers de config. Vision : interface auto-pilotée qui guide pas à pas.

**Connecteurs prioritaires** :

1. Gmail (ajout ou remplacement Outlook par tenant)
2. Microsoft 365 multi-tenant (Azure)
3. WhatsApp Business
4. Slack (à voir selon usage)

**Effort estimé** : 4-8h selon scope retenu.

### 🟡 Priorité 3 — Tests utilisateur bout-en-bout v2.x

**Statut** : ⏳ Non démarré formellement (mais des tests ad-hoc ont eu lieu).

Plan détaillé dans `docs/plan_tests_isolation_pierre_test.md` (créé le 24/04, jamais lancé).

Idée : créer un user `pierre_test` dans `couffrant_solar`, dérouler les 5 scénarios de fuite. Tester aussi sur Charlotte (`juillet`).

**Effort estimé** : 1h.

### 🟢 Priorité 4 — Nettoyage doublons règles

**Statut** : ⏳ Non démarré.

Deux options :

- A : en conversation avec Raya (20 min)
- B : via endpoint `/admin/rules/cleanup-ui` (10 min)

**Effort estimé** : 10-20 min.

### 🔵 Priorité 5 — Job nocturne rules_optimizer

**Statut** : ⏳ Non démarré.

But : optimiser les règles pendant la nuit (consolidation, détection de contradictions, archivage automatique des règles inactives).

Détection de contradictions → table `pending_rules_questions` avec question posée au premier message du lendemain.

**Effort estimé** : 2-3h dev + 1h tests. **Prérequis** : audit multi-tenant (Priorité 1) terminé pour garantir que le job nocturne respecte l'isolation.

### 🟣 Priorité 6 — Résilience & sécurité

**Statut** : 🟡 Plan rédigé (`docs/plan_resilience_et_securite.md`), implémentation partielle.

### 🟣 Priorité 7 — Résilience pool de connexions DB (suite incident 25-26/04)

3 sous-chantiers :

#### 7.1 — Migration progressive des 152 patterns `conn = get_pg_conn()` sans `with` block

**Statut** : ⏳ Non démarré.

Il y a 152 endroits dans le code qui utilisent `conn = get_pg_conn()`sans `with` block. Si une exception lève entre l'ouverture et le close explicite, le conn fuite (zombie connection dans le pool).

**Effort estimé** : 3-5h.

#### 7.2 — Monitoring proactif du pool

**Statut** : ⏳ Non démarré.

Ajouter dans `system_monitor.py` une métrique du nombre de connexions actives + alerte si on approche du max.

**Effort estimé** : 30-45 min.

#### 7.3 — Migration `mail_memory.created_at` text → TIMESTAMP

**Statut** : ⏳ Non démarré.

Anti-pattern actuel : la colonne stocke des timestamps en TEXT, donc les comparaisons `WHERE created_at > NOW() - INTERVAL...` font des casts implicites coûteux à chaque scan.

**Effort estimé** : 1-2h (migration + backfill + propagation).

### 🟠 Priorité 8 — Connexion Odoo durable (en attente OpenFire)

**Statut** : 🟡 En attente d'un retour d'OpenFire.

3 manifests cassés à régénérer dès que OpenFire répond :

- `of.survey.answers`
- `of.survey.user_input.line`
- `mail.activity`

**Effort dès retour** : 1h.

### Phase B finalisée (commits 26/04)

D'après le résumé en début de conversation :

- ✅ Soft-delete + workflow purge
- ✅ Seat counter
- ✅ UI complète onglet Équipe dans `/settings`
- ✅ Force-purge super_admin
- ✅ Fix bug 500 import `SCOPE_ADMIN`

### Sujet noté pour bien plus tard : Renommage Raya → Saiyan

Énorme chantier dédié, à faire avec recul.

- Renommer `Raya` → `Saiyan` partout dans le code, l'UI, le prompt
- Renommer le domaine `raya-ia.fr` → `saiyan-ai`
- Migrer DB / config / docs

**Effort** : 6-12h selon le scope.

---


<a id="idees-notees"></a>
## 5. Idées notées pour plus tard (à ne pas oublier)

### 💡 Idée 27/04 nuit — Auto-détection des manques par Raya

**L'idée** : quand Raya cherche une info et ne trouve rien dans son
graphe (ex : `adresse de Coullet ?` → vide), elle pourrait se rendre
compte du manque et **proposer un re-scan ciblé** pour combler le trou.

**Sécurité** : pas dangereux si Raya **propose** (jamais auto-execute),
demande confirmation avant écriture, périmètre limité à 1 record cible.

**Effort estimé** : 4-6h (détecter le manque + nouvel outil
`request_data_refresh` + UI confirmation + connexion au scanner).

**Quand** : après stabilisation du système actuel.

### 🧠 Idée 27/04 nuit (2) — Comportement agentique multi-tour

**L'idée / question** : ne l'a-t-on pas un peu bridée à force de
couches de prompts ? Le test de la tournée #449 montre que Raya voit
la structure mais ne fait pas spontanément un 2e search pour avoir
le détail des stops.

**Diagnostic préliminaire** :
- Le prompt système V2 est plutôt sain (1 200 chars, encourage le multi-tour)
- La détection de boucle peut freiner légèrement (warning au 2e appel identique)
- Mais surtout : le format des résultats expose des labels TECHNIQUES
  (`[of.planning.tour#449]` puis `🔗 TourStop: of.planning.tour.line#4647`).
  Pas une invitation naturelle à creuser.

**Plan validé** :
1. Mini-test sur 3-4 questions variant le niveau de détail demandé
2. Selon résultat : ne rien toucher OU retoucher prompt OU formatage

**Pistes si modif** :
- Renommer les labels techniques en termes parlants
- Ajouter une règle de raisonnement générique au prompt
- Adoucir la détection de boucle (warning au 3e appel au lieu du 2e)

**Effort si modif** : 1-2h.

### Refonte profonde du système de mise en graphe

Décidé avec Guillaume aujourd'hui : à faire bien plus tard, avec un
prestataire spécialisé. Pas un sujet de 1h le soir.

### Renommage Raya → Saiyan

Voir section précédente (Priorité longue).

---

<a id="synthese-demain"></a>
## 6. Synthèse priorisée pour demain

### Ce qu'on a accompli aujourd'hui (récap rapide)

11 commits propres, ~1 500 lignes de code legacy supprimées, 3 bugs
structurels corrigés, 1 894 doublons nettoyés en DB, 4 anomalies
identifiées et notées, formats de clés du graphe unifiés.

### Ordre logique pour les prochaines sessions

#### Session 1 — Audit isolation Étape C (~2h30)

**Pourquoi en premier** : c'est le seul vrai bloqueur avant l'onboarding
de nouveaux users / tenants. Tout le reste est de l'amélioration.

**Découpage suggéré** :
1. **Lot 1 — Fixes mécaniques admin/profile.py** (~30 min) : I.1 → I.6
2. **Lot 2 — Fixes mécaniques memory/synthesis** (~20 min) : I.7 → I.10
3. **Lot 3 — Endpoints admin laxistes** (~20 min) : I.12, I.13
4. **Lot 4 — connection_token_manager** (~30 min) : I.14
5. **Lot 5 — Bug logique scope** (~30 min) : I.15
6. **Lot 6 — ATTENTION super_admin** (~20 min) : A.1 → A.4
7. **Lot 7 — Détails A.5, A.6** (~10 min)

#### Session 2 — Test agentique multi-tour (~30 min observation + décision)

3 questions à Raya :
- "J'ai quoi demain ?" — 1 search suffit
- "Qui je vais voir demain dans ma tournée ?" — doit creuser
- "Quels documents emmener demain ?" — doit creuser

Selon résultats, soit on touche au prompt/formatage, soit on laisse.

#### Session 3 — Étape D tests isolation (~1h)

Suivre `docs/plan_tests_isolation_pierre_test.md`. Créer un user
`pierre_test` dans `couffrant_solar`, dérouler 5 scénarios de fuite.

#### Session 4 — Migration cœur graphe V1 → V2 (~3-5h)

Plus risqué. À frais, avec budget temps confortable. Pas un soir.

#### En arrière-plan / opportuniste

- Priorités 4-7 selon le moment
- Renommage Raya → Saiyan : à planifier en bloc, pas à grappiller

### Mon avis personnel sur la priorité absolue

**L'Étape C de l'audit isolation** est le seul sujet où le report a un
coût réel : tant qu'on ne l'a pas fait, on **ne peut pas onboarder
en sécurité un nouveau tenant**. Tout le reste peut attendre.

Et c'est ~2h30 de fixes mécaniques, pas de la haute architecture.
Découpé en lots de 20-30 min, c'est faisable en une matinée.

### État de la roadmap `docs/a_faire.md`

Je n'ai PAS modifié le fichier. Il reflète bien le statut, sauf qu'il
dit "🚧 À FAIRE Étape C" sans préciser que c'est presque rien qui a
été fait. Le présent document complète cette information avec la
liste précise des findings et leur statut.

---

## ✅ Document terminé — sauvegardé en `docs/etat_complet_chantiers_27avril_nuit.md`

Si demain tu veux rapidement savoir :
- **Ce qui a été fait aujourd'hui** → section 1
- **L'état précis de l'audit isolation** → section 2
- **Où on en est sur les graphes** → section 3
- **Tous les autres chantiers** → section 4
- **Les idées à creuser** → section 5
- **Par où commencer** → section 6

Bonne nuit.


---

## 🔍 MINI-AUDIT À FRAIS — 28 avril 2026 matin

Réécriture complète de la section 2 après vérification individuelle de chaque finding ce matin. La distinction "actif vs latent" change la priorité.

### Verdict synthétique

| Catégorie | Description | Compte |
|---|---|---|
| ✅ **Vraiment fixé** | Le code a été corrigé proprement | 1 (I.11) |
| 🔴 **Faille active** | Un acteur malveillant peut l'exploiter aujourd'hui | 2 (I.12, I.13) |
| 🟠 **Bug logique réel** | Pas une fuite mais un comportement faux à corriger | 1 (I.15) |
| 🟡 **Latent (homonymie cross-tenant)** | Devient une fuite UNIQUEMENT si 2 users ont le même username dans 2 tenants. Aujourd'hui : 0 homonyme. | 16 (I.1→I.10, I.14, A.1→A.4) |
| 🟢 **Anti-pattern à nettoyer** | Faible risque, hygiène | 2 (A.5, A.6) |

### Distinction critique par rapport à hier soir

Hier soir j'ai marqué 23/25 findings "non fixés" sans distinguer **actif** vs **latent**. Ce matin la lecture précise du code montre :

- **2 failles actives** (I.12, I.13) : un tenant_admin peut connecter un dossier Drive ou un site SharePoint à n'importe quel tenant en passant le `tenant_id` dans le payload. **Vraie porte ouverte**, à fixer en premier.
- **16 findings latents** : ils s'activent UNIQUEMENT en cas d'homonymie. Aujourd'hui aucun homonyme cross-tenant n'existe en DB. **Mais avant d'onboarder un nouveau tenant qui pourrait avoir un user "guillaume" ou "pierre", il faut les fermer.**
- **1 bug logique** (I.15) : `scope != "admin"` au lieu de `scope not in (SCOPE_ADMIN, SCOPE_SUPER_ADMIN)`. Pas une fuite, juste un comportement faux pour super_admin.

### Plan de fix priorisé (ordre logique)

**🔴 LOT URGENT — Failles actives** (~25 min)

| # | Finding | Fix | Effort |
|---|---|---|---|
| 1 | I.12 — `POST /admin/drive/select` | Forcer `tenant_id = admin["tenant_id"]` si scope != admin/super_admin | 10 min |
| 2 | I.13 — `POST /admin/sharepoint/select` | Idem | 10 min |
| 3 | Vérifier qu'aucun autre endpoint admin n'a le même schéma | Audit grep | 5 min |

**🟠 LOT BUG LOGIQUE** (~20 min)

| # | Finding | Fix | Effort |
|---|---|---|---|
| 4 | I.15 — bug `scope != "admin"` | Remplacer par `scope not in (SCOPE_ADMIN, SCOPE_SUPER_ADMIN)` dans les 5 occurrences | 20 min |

**🟡 LOT FERMETURE LATENTS — Tier 1** (~50 min)

Les requêtes appelées dans des contextes utilisateur authentifié — risque d'homonymie réel à terme.

| # | Finding | Fix | Effort |
|---|---|---|---|
| 5 | I.1-I.6 — `profile.py` | Ajouter `AND tenant_id = %s` à 6 requêtes | 20 min |
| 6 | I.7-I.8 — `memory_teams.py` | Idem | 10 min |
| 7 | I.9 — `synthesis_engine.py` UPDATE | Idem | 5 min |
| 8 | I.10 — `report_actions.py` | Idem | 5 min |
| 9 | I.14 — `connection_token_manager.py` | Ajouter `AND tc.tenant_id = %s` dans 2 fonctions, propager tenant_id | 10 min |

**🟡 LOT FERMETURE LATENTS — Tier 2** (~25 min)

Endpoints super_admin only (Guillaume), faible impact mais hygiène.

| # | Finding | Fix | Effort |
|---|---|---|---|
| 10 | A.1-A.4 — `super_admin_users.py` | Ajouter `AND tenant_id = %s` à 4 requêtes | 20 min |
| 11 | A.5 — default `username="guillaume"` | Retirer le default, lever un TypeError si manquant | 5 min |

**🟢 LOT NETTOYAGE** (~5 min)

| # | Finding | Fix | Effort |
|---|---|---|---|
| 12 | A.6 — magic string `"admin"` (1 occurrence dans hardcoded_permissions.py) | Remplacer par SCOPE_ADMIN | 5 min |

### Total : ~2h05

Décomposé en lots de 20-50 min, faisable dans la matinée.

### Réorientation — ce qu'on fait maintenant

🛑 Vu que les 2 vrais sujets actifs (I.12, I.13) sont rapides à fixer, je propose qu'on attaque dans cet ordre :

1. **LOT URGENT** (25 min) — I.12, I.13 + vérif qu'il n'y a pas d'autre endpoint similaire
2. **LOT BUG LOGIQUE** (20 min) — I.15
3. **LOT TIER 1** (50 min) — I.1 à I.10, I.14
4. Pause / break si fatigue
5. **LOT TIER 2** (25 min) — A.1 à A.5
6. **LOT NETTOYAGE** (5 min) — A.6

Chaque lot = 1 commit propre. 6 commits attendus pour fermer toute l'étape C de l'audit isolation.


---

## 🗺️ Audit profond du LOT URGENT — 28 avril matin

### Reformulation de la priorité après audit

**Verdict révisé** : I.12 et I.13 (admin/drive/select et admin/sharepoint/select) ne sont **pas des failles actives** comme l'audit du 25/04 le pensait. Ce sont des features cohérentes avec le modèle de rôles intentionnel :

- `super_admin` (toi, hardcoded par email) : pouvoir total
- `admin` (collaborateur Raya, futur) : cross-tenant volontairement, te suppléer sur la gestion. **Ne peut pas modifier le statut super_admin**.
- `tenant_admin` : limité à son tenant
- `user` : devrait être renommé `tenant_user` pour cohérence (toujours attaché à un tenant en DB - NOT NULL déjà)

### Matrice complète des 27 endpoints `/admin/*` avec tenant_id

- **24 endpoints** en `require_admin` (admin Raya OU super_admin) — cross-tenant intentionnel
- **3 endpoints** en `require_super_admin` — sécurisés correctement
- **0 endpoint** en `require_tenant_admin` avec tenant_id exposé

Aujourd'hui : 1 seul user a scope=`super_admin` (Guillaume). 0 user en scope=`admin`. Donc aucun de ces 24 endpoints n'est exploitable maintenant.

### Plan validé pour la suite

**Ordre** (validé Guillaume 28/04) :

1. **LOT 2 — Bug logique I.15** (~20 min, 1 commit) : remplacer `scope != "admin"` par `scope not in (SCOPE_ADMIN, SCOPE_SUPER_ADMIN)` dans 5 occurrences
2. **LOT 3 — Fixes SQL Tier 1** (~50 min, 1 commit) : I.1-I.10 + I.14
3. **LOT 4 — Fixes SQL Tier 2** (~25 min, 1 commit) : A.1-A.5
4. **LOT 5 — Nettoyage** (~5 min, 1 commit) : A.6 (1 magic string restante)
5. **LOT 6 — Renommage user → tenant_user** (~1h, 1 commit séparé) :
   - 22 occurrences de `SCOPE_USER` dans le code
   - 4 lignes en DB à migrer (UPDATE `users` SET `scope` = 'tenant_user' WHERE `scope` = 'user')
   - 2 occurrences `== "user"` (à vérifier individuellement, ce sont des roles OpenAI/Anthropic, pas le scope)
   - **+ Suppression du legacy `SCOPE_CS`** au passage (0 user le porte aujourd'hui)

### Observations

- Le LOT 1 "URGENT" annulé (I.12/I.13 = features intentionnelles)
- Le renommage simplifie le modèle : 4 vrais scopes (super_admin, admin, tenant_admin, tenant_user) au lieu de 5
- Le renommage est plus simple que prévu : ~22 fichiers Python centralisés, 4 lignes DB


---

## 🛠️ LOT 3 — Audit profond et plan détaillé (28/04 matin)

### Vérifications préalables faites

1. **Toutes les tables concernées ont déjà la colonne `tenant_id`** (8 tables vérifiées)
2. **Aucune ligne avec `tenant_id` NULL** dans aucune de ces tables (0/2089 lignes au total)
3. **Imports déjà présents** dans les fichiers modifiés (sauf rgpd.py qu'on a fixé en LOT 2)

### Découpage du LOT 3 en 3 mini-commits

**3a** — Fixes SQL simples (~25 min, 1 commit)
- `app/routes/admin/profile.py` : 6 SELECTs (I.1-I.6) — tenant_id dispo via require_user
- `app/synthesis_engine.py:171` : UPDATE aria_hot_summary (I.9) — tenant_id dispo localement
- `app/routes/actions/report_actions.py:21` : SELECT daily_reports (I.10) — tenant_id optionnel pour 3 call-sites

**3b** — Memory teams (~15 min, 1 commit)
- `app/memory_teams.py` : get_teams_markers, set_teams_marker, delete_teams_marker, get_teams_context_summary (I.7-I.8)
- Propagation tenant_id depuis aria_loaders.py et teams_actions.py qui ont déjà l'info

**3c** — Connection token manager (~20 min, 1 commit)
- `app/connection_token_manager.py` : 4 fonctions internes + 2 publiques (I.14)
- Tenant_id optionnel ; si non fourni, résolution interne via users
- Touche le critique (auth) → tester en post-deploy

### Note sur les "sujets profonds" identifiés mais HORS LOT 3

- `aria_hot_summary` a une PK `username` au lieu de `(username, tenant_id)`. ON CONFLICT(username) DO UPDATE peut écraser les data en cas d'homonymie. À traiter dans une session "PK composites" plus tard.
- 2 occurrences `== "user"` dans `elicitation_questions.py:27` et `onboarding.py:148` correspondent au rôle "user" d'un message Anthropic/OpenAI, pas au scope. À ne PAS toucher au moment du renommage user → tenant_user (LOT 6).


---

## 📌 Followup LOT 4 (A.5) — A traiter plus tard

**Sujet** : `_build_email_html` dans `outlook_calendar.py` n a plus de
default 'guillaume', mais 4 call-sites de `perform_outlook_action` ne
propagent pas encore l username explicitement. Resultat : un warning
log [A.5] est emis a chaque envoi/reponse de mail, et la signature
retombe sur le fallback statique au lieu de la signature personnalisee.

**A faire** :
1. Ajouter parametre `username: str` a `perform_outlook_action(action, params, token)`
2. Mettre a jour les 10+ call-sites pour passer `username`
3. Propager `username` aux 4 appels `_build_email_html` dans le fichier

**Effort** : ~30-40 min, commit dedie.
**Detection facile** : grep des warnings `[A.5]` dans les logs Railway.

