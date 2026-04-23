# Audit isolation multi-tenant et utilisateur — Raya v2

**Date** : 24 avril 2026 matin.
**Auteur** : Claude (audit) + Guillaume (validation).
**Statut** : AUDIT SEUL — aucune correction n'a été appliquée.

---

## 🎯 Rappel du modèle d'isolation (décision Guillaume 24/04)

### Niveau tenant
Isolation COMPLÈTE. Société A ne voit jamais données société B.

### Niveau utilisateur dans un tenant
Isolation STRICTE aujourd'hui. Chaque utilisateur a sa propre base de
règles, ses propres conversations, ses propres mails. Seul ce qui vient
de sources externes métier (Odoo, SharePoint, Drive commun) est partagé
au niveau tenant.

Donc la règle générale dans le code devient :

- **Données user** (aria_rules, aria_memory, mail_memory, etc.) →
  `WHERE username = %s AND tenant_id = %s`
- **Données tenant** (aria_contacts, odoo_semantic_content, etc.) →
  `WHERE tenant_id = %s`

---

## 📊 PHASE 1 — Cartographie DB (57 tables)

### 🟥 Tables utilisateur PRIVÉES (30 tables)
Doivent filtrer `username + tenant_id` dans les SELECT, UPDATE, DELETE.

`aria_rules`, `aria_rules_history`, `aria_rule_audit`, `aria_memory`,
`aria_hot_summary`, `aria_session_digests`, `aria_patterns`,
`aria_profile`, `aria_insights`, `aria_onboarding`,
`aria_style_examples`, `aria_response_metadata`, `mail_memory`,
`sent_mail_memory`, `reply_learning_memory`, `email_signatures`,
`user_shortcuts`, `user_topics`, `pending_actions`,
`agent_continuations`, `proactive_alerts`, `bug_reports`,
`daily_reports`, `dossier_narratives`, `elicitation_sessions`,
`teams_sync_state`, `activity_log`, `llm_usage`, `oauth_tokens`,
`permission_audit_log`

### 🟨 Tables user-only SANS tenant_id (4 à investiguer)
- `gmail_tokens` (manque tenant_id → risque faible en pratique car
  username unique cross-tenant aujourd'hui, mais à corriger)
- `user_tools` (manque tenant_id)
- `connection_assignments` (manque tenant_id)
- `webhook_subscriptions` (manque tenant_id)

`password_reset_tokens` est acceptable tel quel (token court, expire).

### 🟦 Tables tenant-only (légitimement partagées par tenant)
`aria_contacts`, `drive_folders`, `drive_semantic_content`,
`odoo_semantic_content`, `semantic_graph_nodes`,
`semantic_graph_edges`, `entity_links`, `tenant_connections`,
`tenant_events`, `global_instructions`, `scanner_runs`,
`system_alerts`, `vectorization_queue`, `connector_schemas`,
`tool_schemas`

### 🟩 Tables globales (légitimement sans filtres)
`admin_audit_log`, `deactivated_models`, `system_heartbeat`,
`tenants`, `tools_registry`

---

## 🚨 PHASE 2 — Problèmes détectés dans le code

Synthèse des 150+ matches SQL analysés. Classés par criticité.

### 🔴 CRITIQUE — Fuites potentielles cross-tenant

Ces requêtes filtrent sur `username` SANS `tenant_id`. Si un jour un
même username existe dans deux tenants différents (théoriquement
possible, les users sont unique cross-tenant aujourd'hui mais rien
n'empêche deux "pierre" dans deux tenants demain), il y a fuite.

**Fichier `app/routes/chat_history.py`** (ligne 29-34)
```sql
SELECT user_input, aria_response, created_at, id
FROM aria_memory
WHERE username = %s
ORDER BY created_at DESC LIMIT %s
```
→ Manque `tenant_id`. Fuite historique conversationnel.

**Fichier `app/routes/mail_analysis.py`** (lignes 139-142, 192-200)
```sql
SELECT ... FROM mail_memory WHERE username = %s AND analysis_status IN ...
```
→ Manque `tenant_id`. Fuite mails.

**Fichier `app/routes/memory.py`** (lignes 111-119, 131-135, 174-178,
193, 207-211, 237-240)
Tous les SELECT/DELETE sur aria_rules, aria_insights, mail_memory,
sent_mail_memory, aria_profile filtrent uniquement `username`.
→ 5-6 endpoints admin à corriger.

**Fichier `app/routes/aria_loaders.py`** (lignes 36-48, 126-128)
```sql
SELECT ... FROM mail_memory WHERE username = %s ...
SELECT ... FROM aria_memory WHERE username = %s ...
SELECT ... FROM aria_insights WHERE username = %s AND source = 'teams'
```
→ Charge l'historique pour le prompt Aria v1. Manque `tenant_id`.

**Fichier `app/routes/mail_gmail.py`** (ligne 38-41)
Vérifie `message_id` contre `mail_memory` par username seul.
→ Manque `tenant_id`.

**Fichier `app/routes/raya_tool_executors.py`** (lignes 208-215)
Tool `read_mail` lit `mail_memory` par username seul.
→ Manque `tenant_id`.

**Fichier `app/routes/prompt_blocks_extra.py`** (ligne 61-65)
`user_topics` filtré `username` seul.
→ Manque `tenant_id`.

**Fichier `app/routes/prompt_blocks.py`** (ligne 78-84)
`aria_patterns` filtré `username` seul.
→ Manque `tenant_id`.

**Fichier `app/routes/signatures.py`** (lignes 29-33, 81, 111)
3 requêtes `email_signatures` filtrées `username` seul.
→ Manque `tenant_id`.

**Fichier `app/routes/raya_agent_core.py`** (ligne 207-210)
```sql
SELECT ... FROM aria_memory
WHERE username = %s AND archived = false
ORDER BY id DESC LIMIT %s
```
→ Charge les 3 derniers échanges pour le prompt. Manque `tenant_id`.
**CRITIQUE** car c'est le cœur de la boucle agent v2.

**Fichier `app/dashboard_queries.py`** (lignes 22-25)
`mail_memory WHERE username + date`, manque `tenant_id`.

**Fichier `app/ai_client.py`** (lignes 61-66)
`reply_learning_memory` filtré `username + category`, manque
`tenant_id`.

**Fichier `app/memory_save.py`** (lignes 26-30)
`aria_insights` vérif d'existence par `username + topic`, manque
`tenant_id`.

**Fichier `app/memory_synthesis.py`** (lignes 74-80, 167-173,
208-213)
Plusieurs UPDATE/DELETE sur `aria_memory`, `mail_memory` filtrés
`username` seul.

**Fichier `app/feedback.py`** (lignes 54-60, 115-118, 177-180,
188-200)
4 requêtes sur `aria_response_metadata`, `aria_memory`, `aria_rules`
filtrées `username` seul (parfois avec `id`).

**Fichier `app/topics.py`** (lignes 52-57, 111-114, 157-160)
`user_topics` filtré `username` seul.

**Fichier `app/shortcuts.py`** (lignes 40-42, 60-65, 82-87, 107,
145)
`user_shortcuts` filtré `username` seul dans plusieurs requêtes.

**Fichier `app/activity_log.py`** (lignes 93-100, 113-122)
`activity_log` filtré `username` seul.

**Fichier `app/urgency_model.py`** (lignes 118-123, 185-188)
`aria_rules` et `aria_patterns` filtrés `username` seul.

**Fichier `app/rule_engine.py`** (lignes 44-48)
Branche ELSE sans tenant_id : `aria_rules WHERE username + category`.
→ Branche IF OK (ligne 35-42 a tenant_id). Branche ELSE à protéger.

**Fichier `app/maturity.py`** (lignes 71-85)
5 sous-requêtes COUNT sur aria_rules, aria_memory, users,
aria_response_metadata toutes filtrées `username` seul.
→ Calcul maturité incorrect si cross-tenant.

**Fichier `app/memory_style.py`** (lignes 15-22, 87-90)
`aria_style_examples`, `sent_mail_memory` filtrés `username` seul.

**Fichier `app/ai_prompts.py`** (lignes 63-65)
`aria_profile` filtré `username` seul.

**Fichier `app/email_signature.py`** (lignes 62-94)
4 requêtes `email_signatures` filtrées `username` seul.

**Fichier `app/seeding.py`** (lignes 266-269)
`aria_rules` filtré `username` seul pour test d'existence.

**Fichier `app/memory_contacts.py`** (lignes 67-90)
2 requêtes `mail_memory`. La 1ère utilise `username IN (SELECT FROM
users WHERE tenant_id)` (OK mais plus coûteux). La 2ème ligne 86-90
N'A PAS DE FILTRE DU TOUT → **CRITIQUE**.

**Fichier `app/entity_graph.py`** (lignes 546-551, 700-708)
- 1ère : `mail_memory WHERE username IN (SELECT FROM users WHERE
  tenant_id)` → OK mais coûteux
- 2ème : `mail_memory WHERE username = %s` → manque tenant_id

**Fichier `app/synthesis_engine.py`** (lignes 41-43, 52-54)
`mail_memory` et `aria_memory` filtrés `username` seul.

**Fichier `app/tool_discovery.py`** (lignes 385-393)
`mail_memory` filtré `username` seul.

**Fichier `app/mail_memory_store.py`** (lignes 11-17)
Fonction `mail_exists(message_id, username)` par `username` seul.

---

### 🟠 ATTENTION — Requêtes sans aucun filtre (jobs nocturnes)

Ces requêtes n'ont NI `username` NI `tenant_id`. Pour l'instant elles
servent juste à trouver la liste des users actifs (pour ensuite boucler
sur chacun), donc peu risqué, mais à verrouiller si on change le
comportement.

**Fichier `app/jobs/proactivity_scan.py`** (lignes 19-23)
```sql
SELECT DISTINCT username FROM aria_memory
WHERE created_at > NOW() - INTERVAL '7 days'
```
→ Liste users actifs cross-tenants pour lancer le scan. OK.

**Fichier `app/jobs/briefing.py`** (lignes 15-18)
**Fichier `app/jobs/heartbeat.py`** (lignes 22-25)
**Fichier `app/jobs/external_observer.py`** (lignes 33-36)
**Fichier `app/jobs/anomaly_detection.py`** (lignes 37-40)
**Fichier `app/jobs/pattern_analysis.py`** (lignes 21-23)
Même pattern partout : `SELECT DISTINCT username FROM aria_memory`
cross-tenant pour boucler sur users.

**Vérifier** : les sous-requêtes qui suivent dans ces jobs filtrent
bien sur `username` individuellement ET idéalement aussi `tenant_id`.
→ D'après les grep, `username` est présent. `tenant_id` est souvent
absent. À corriger dans la partie "Corrections" ci-dessous.

---

### 🟡 SPECIFIQUE — Patterns avec JOIN vers users (acceptable mais coûteux)

Ces requêtes passent par un JOIN avec la table `users` pour filtrer
par `tenant_id`. Ça marche mais c'est coûteux en performance et
fragile (si le JOIN échoue, le filtre disparaît silencieusement).

**Fichier `app/routes/admin/tenant_admin.py`** (lignes 220-226)
```sql
SELECT ar.id, ar.username, ar.category, ar.rule, ...
FROM aria_rules ar
JOIN users u ON u.username = ar.username
WHERE u.tenant_id = %s
```
→ Fonctionne mais suboptimal. Le JOIN ajoute du coût. Plus propre
d'utiliser directement `ar.tenant_id = %s`.

**Fichier `app/jobs/graph_indexer.py`** (lignes 91-98, 128-136)
```sql
FROM aria_memory am
LEFT JOIN users u ON u.username = am.username
WHERE ... AND COALESCE(u.tenant_id, 'couffrant_solar') = %s
```
→ LEFT JOIN + COALESCE fallback 'couffrant_solar' : potentiellement
dangereux. Si un user n'a pas de tenant_id en base, il est rattaché
par défaut à couffrant_solar. Fuite possible.

**Fichier `app/memory_contacts.py`** (lignes 67-77)
```sql
FROM mail_memory
WHERE ... AND username IN (SELECT username FROM users WHERE tenant_id = %s)
```
→ Sous-requête au lieu de JOIN, même idée, même limite.

**Fichier `app/entity_graph.py`** (lignes 546-551)
Même pattern : sous-requête `username IN (SELECT FROM users)`.

---

### 🟢 BON — Requêtes correctement filtrées

Pour mémoire, certaines requêtes sont déjà correctement filtrées sur
`username + tenant_id`. Elles serviront de modèle :

**`app/routes/raya_continuation.py`** (lignes 221-231) ✅
```sql
SELECT ... FROM agent_continuations
WHERE id = %s AND username = %s AND tenant_id = %s
AND consumed = false AND expires_at > NOW()
```
Exemplaire : ownership + expiration + consommation.

**`app/routes/raya_deepen.py`** (lignes 69-74) ✅
```sql
SELECT user_input, aria_response FROM aria_memory
WHERE id = %s AND username = %s
AND (tenant_id = %s OR tenant_id IS NULL)
```
Correct, avec tolérance tenant_id NULL pour les données historiques.

**`app/routes/raya_agent_core.py`** (lignes 153-159) ✅
```sql
FROM aria_rules
WHERE username = %s
AND (tenant_id = %s OR tenant_id IS NULL)
AND active = true AND category != 'memoire'
ORDER BY confidence DESC ...
```
Correct (cœur du chargement des règles pour l'agent v2).

**`app/memory_rules.py`** (lignes 43-52) ✅
Correct avec tenant_id.

**`app/rag.py`** (lignes 37-55) ✅
Correct dans les 3 branches (tenant_ids array, tenant_id single, sans
tenant mais username filtré).

**`app/retrieval.py`** (lignes 665-730) ✅
`mail_memory` et `aria_memory` embeddings : filtre `tenant_id =
%s AND username = %s`. Exemplaire.

**`app/narrative.py`** (lignes 35-38, 157-159, 184-186, 192-194) ✅
`dossier_narratives` filtre `username + tenant_id`.

**`app/rule_validator.py`** (lignes 84-88) ✅
Correct.

**`app/jobs/opus_audit.py`** (lignes 53-58) ✅
Correct (inclut tenant_id + tolérance NULL).

**`app/pending_actions.py`** (lignes 90-97, 121-125) ✅
Correct : `username + tenant_id`.

**`app/jobs/maintenance.py`** (lignes 101-104) ✅
Correct : `tenant_id + username`.

**`app/routes/admin_rules.py`** (lignes 50-64, 125-140, 315-329)
Mix : filtres `context` (= tenant) + `username` quand nécessaire.
Vérifier le contexte d'appel (admin super-admin vs admin tenant) pour
s'assurer que le niveau de droit est OK.

---

## 🟨 PHASE 3 — Tables sans tenant_id à investiguer

### `gmail_tokens` (manque tenant_id)
Utilisée dans :
- `app/routes/signatures.py` ligne 179 (SELECT email_address FROM
  gmail_tokens WHERE username = %s)
- `app/routes/admin/super_admin_system.py` ligne 95, 104 (SELECT
  updated_at FROM gmail_tokens ORDER BY updated_at DESC LIMIT 1 —
  pas de filtre du tout !)
- `app/database_migrations.py` ligne 67 (migration vers oauth_tokens)

**Risque** : faible en pratique (gmail_tokens est en cours de
remplacement par oauth_tokens), mais la requête admin sans filtre est
problématique.

**Correction recommandée** :
1. Ajouter colonne `tenant_id` à `gmail_tokens`
2. Backfill depuis `users.tenant_id` via `username`
3. Filtrer toutes les requêtes par `tenant_id` + `username`
4. Terminer la migration vers `oauth_tokens` (qui a déjà tenant_id)

### `user_tools` (manque tenant_id)
Non encore vu dans les grep, à auditer spécifiquement.

### `connection_assignments` (manque tenant_id)
Utilisée dans :
- `app/routes/auth.py` lignes 53-58, 101-106 (JOIN avec
  tenant_connections via connection_id)
→ Le filtre `tenant_id` passe via `tenant_connections.tenant_id`.
Acceptable mais fragile (si le JOIN casse, le filtre disparaît).

### `webhook_subscriptions` (manque tenant_id)
Non encore vu dans les grep, à auditer spécifiquement.

---

## 🧭 PHASE 4 — Plan de correction proposé

### Étape 1 — Ajouter tenant_id manquant (15 min)
```sql
ALTER TABLE gmail_tokens ADD COLUMN IF NOT EXISTS tenant_id TEXT;
ALTER TABLE user_tools ADD COLUMN IF NOT EXISTS tenant_id TEXT;
ALTER TABLE connection_assignments ADD COLUMN IF NOT EXISTS tenant_id TEXT;
ALTER TABLE webhook_subscriptions ADD COLUMN IF NOT EXISTS tenant_id TEXT;

-- Backfill depuis users
UPDATE gmail_tokens g SET tenant_id = u.tenant_id
  FROM users u WHERE u.username = g.username AND g.tenant_id IS NULL;
-- idem pour les 3 autres

-- Futur : contraintes NOT NULL à ajouter quand le code est aligné
```

### Étape 2 — Ajouter tenant_id dans les SELECT utilisateur (fichier par fichier)

**Ordre suggéré du plus critique au moins critique** :

| # | Fichier | Lignes | Criticité | Effort |
|---|---|---|---|---|
| 1 | `raya_agent_core.py` | 207-210 | 🔴 CRITIQUE (cœur agent) | 1 min |
| 2 | `chat_history.py` | 29-34, 46-51 | 🔴 CRITIQUE (historique UI) | 2 min |
| 3 | `memory_contacts.py` | 86-90 | 🔴 CRITIQUE (aucun filtre) | 3 min |
| 4 | `aria_loaders.py` | 36-55, 126-128 | 🔴 (prompt v1 Aria) | 3 min |
| 5 | `memory.py` | 6 requêtes | 🔴 (endpoints admin) | 8 min |
| 6 | `maturity.py` | 71-85 | 🔴 (calcul maturité) | 5 min |
| 7 | `raya_tool_executors.py` | 208-215 | 🔴 (tool read_mail) | 2 min |
| 8 | `feedback.py` | 4 requêtes | 🔴 (sécurité feedback) | 5 min |
| 9 | `mail_analysis.py` | 139-200 | 🟠 (analyse mails) | 3 min |
| 10 | `mail_gmail.py` | 38-41 | 🟠 | 1 min |
| 11 | `memory_synthesis.py` | 74, 167, 208 | 🟠 (UPDATE/DELETE) | 5 min |
| 12 | `memory_save.py` | 26-30 | 🟠 | 1 min |
| 13 | `dashboard_queries.py` | 22-25 | 🟠 | 1 min |
| 14 | `ai_client.py` | 61-66 | 🟠 | 1 min |
| 15 | `topics.py`, `shortcuts.py`, `signatures.py` | multiples | 🟠 | 10 min |
| 16 | `activity_log.py`, `urgency_model.py`, `memory_style.py`, `ai_prompts.py`, `email_signature.py`, `seeding.py`, `synthesis_engine.py`, `tool_discovery.py`, `mail_memory_store.py`, `entity_graph.py`, `prompt_blocks.py`, `prompt_blocks_extra.py`, `rule_engine.py` (branche ELSE) | multiples | 🟡 | 20 min |

**Durée totale estimée** : ~70-80 min de corrections mécaniques.

### Étape 3 — Sécuriser les jobs nocturnes (15 min)
Ajouter `tenant_id` dans les boucles internes des 6 jobs identifiés :
`proactivity_scan.py`, `briefing.py`, `heartbeat.py`,
`external_observer.py`, `anomaly_detection.py`, `pattern_analysis.py`.

### Étape 4 — Nettoyer les JOINs coûteux (30 min, optionnel)
Remplacer les `JOIN users` par des filtres directs `ar.tenant_id = %s`
dans :
- `app/routes/admin/tenant_admin.py` lignes 220-226
- `app/jobs/graph_indexer.py` lignes 91, 128
- `app/memory_contacts.py` lignes 67-77
- `app/entity_graph.py` lignes 546-551

### Étape 5 — Tests de non-régression (30 min)

Créer un 2e user fictif `pierre_test` dans `couffrant_solar` puis
vérifier en base :

1. `pierre_test` ne voit PAS les règles de `guillaume` ❌
2. `pierre_test` ne voit PAS les conversations de `guillaume` ❌
3. `pierre_test` ne voit PAS les mails de `guillaume` ❌
4. `pierre_test` VOIT les données Odoo Couffrant ✅
5. Une règle apprise par `pierre_test` n'affecte PAS `guillaume` ❌

Puis tester isolation tenant avec `charlotte` dans
`juillet_utilisateurs` :
- `charlotte` ne voit QUE ses 10 règles, jamais celles de
  `couffrant_solar`

---

## 🎯 Synthèse globale

### Bilan sur les 57 tables

- ✅ **22 tables** ont déjà `tenant_id + username` en schéma → il faut
  juste vérifier que TOUT le code utilise bien les deux filtres
- ⚠️ **4 tables** manquent `tenant_id` → ajout de colonne + backfill
- ✅ **15 tables** tenant-only sans username sont correctement
  utilisées (partage par tenant voulu)
- ✅ **5 tables** globales sans filtres sont correctement
  sans filtres

### Bilan sur ~150 requêtes SQL analysées

- 🟢 **~20 requêtes EXEMPLAIRES** : filtrent correctement
  (raya_agent_core load règles, raya_continuation, raya_deepen, rag,
  retrieval, narrative, memory_rules, pending_actions, rule_validator,
  jobs/maintenance, jobs/opus_audit)

- 🔴 **~40 requêtes CRITIQUES** : filtrent `username` seul, besoin
  d'ajouter `tenant_id`. Principalement dans chat_history, memory,
  maturity, raya_agent_core (historique), aria_loaders, mail_analysis,
  feedback, memory_synthesis.

- 🟠 **~15 requêtes SANS FILTRE** : principalement dans les jobs
  nocturnes pour découvrir les users actifs. Peu risqué en soi mais à
  verrouiller pour éviter régression future.

- 🟡 **~10 requêtes avec JOIN coûteux** : fonctionnent mais à
  refactoriser un jour pour optimiser (suboptimal, pas critique).

### Combien de temps au total ?

**Estimation réaliste pour tout corriger** :
- Étape 1 (ALTER TABLE) : 15 min
- Étape 2 (corrections code fichier par fichier) : 70-80 min
- Étape 3 (jobs nocturnes) : 15 min
- Étape 4 (cleanup JOINs, optionnel) : 30 min
- Étape 5 (tests de non-régression) : 30 min

**Total : 2h30 à 3h**

### Risque actuel en production

**Pour toi aujourd'hui** : ZÉRO risque concret tant que tu es seul
utilisateur sur le seul tenant actif `couffrant_solar`. Les requêtes
qui filtrent `username = 'guillaume'` sans `tenant_id` retournent
exactement les mêmes résultats qu'avec le filtre tenant, puisque tu es
le seul `guillaume` en base.

**Risque dès qu'un 2e user/tenant arrive** :
- Si charlotte est activée dans `juillet_utilisateurs` → théorique
  mais elle ne partage AUCUN username avec Guillaume, donc OK
- Si Pierre rejoint `couffrant_solar` → les requêtes mal filtrées ne
  lui fuiront PAS les données de Guillaume (filtres par username
  Pierre), mais si un bug ou un admin crée un username collision,
  fuite possible

**Le risque devient réel si** :
- Deux tenants différents ont un user avec le même username
- Ou si on active l'isolation stricte par user dans un même tenant
  (qui est justement la décision de ce matin !)

### Ma recommandation d'ordre

Vu que tu es seul en prod aujourd'hui :

1. **Pas d'urgence à tout corriger en un bloc**. Le risque est
   théorique.
2. **Avant d'onboarder Pierre/Sabrina**, faire au moins les
   corrections 🔴 CRITIQUES (étapes 1, 2 items 1-10, étape 5 tests)
3. **Les corrections 🟠 ATTENTION et 🟡 SPECIFIQUE** peuvent attendre
   une session dédiée plus tard.

Je te conseille de d'abord **prendre le temps de lire ce document en
entier**, poser tes questions, avant qu'on attaque la moindre
correction. On aura alors un plan d'action précis, validé, et on
corrigera en séries de 3-5 fichiers avec commits intermédiaires pour
traçabilité.
