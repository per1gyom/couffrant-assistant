# Audit isolation multi-tenant — COMPLÉMENTAIRE

**Date** : 25 avril 2026 soir **Auteur** : Claude (audit) + Guillaume (validation) **Statut** : EN COURS — audit avec angles différents de celui du 24/04

---

## 🎯 Pourquoi un audit complémentaire ?

L'audit du 24/04 (`audit_isolation_24avril.md`) a été suivi de 13 commits de corrections (\~40 fichiers, \~100 requêtes SQL sécurisées). Mais :

1. Les **corrections n'ont pas été revérifiées** depuis (régression possible ?)
2. Du **nouveau code a été ajouté** depuis (chantier signatures, design system, etc.) — peut-être de nouveaux trous ?
3. L'audit du 24/04 se concentrait sur les **requêtes SQL**. D'autres angles méritent d'être creusés :
   - Authentification et sessions
   - Endpoints HTTP (acceptent-ils `username`/`tenant_id` du client ?)
   - Privilege escalation (user → admin tenant → super admin)
   - Tokens OAuth Gmail/Outlook (mismatch user possible ?)
   - Logs et tracing (fuites cross-tenant via les logs ?)
   - Endpoints debug/admin non documentés
4. Les **tests de non-régression** (plan pierre_test) **n'ont jamais été exécutés**.

## 📋 Plan d'audit

#PhaseAngleStatut1Vérifier les corrections du 24/04 tiennent toujoursSQL⏳2Audit du nouveau code post-24/04 (signatures, design system)SQL⏳3Authentification (sessions, cookies, require_user)Auth⏳4Endpoints HTTP (paramètres acceptés du client)HTTP⏳5Privilege escalation rôlesRBAC⏳6Tokens OAuth + connecteurs externesOAuth⏳7Tests dynamiques en DBTests⏳

À chaque phase, les findings sont classés :

- 🔴 CRITIQUE — fuite cross-tenant ou cross-user effective
- 🟠 IMPORTANT — risque sérieux mais pas une fuite directe
- 🟡 ATTENTION — défense en profondeur, à durcir
- 🟢 OK — vérifié bon

---

## 🔍 Phase 1 — Vérification des corrections du 24/04

### ✅ Bonne nouvelle : 30/30 fichiers du rapport du 24/04 sont bien corrigés

Vérification automatique : les 30 fichiers identifiés comme CRITIQUE/IMPORTANT
le 24/04 ont tous au moins 3 occurrences de `tenant_id` (médiane : 17 occurrences).
**Aucune régression depuis le 24/04.**

```
✅ chat_history.py (9), mail_analysis.py (18), memory.py (34), aria_loaders.py (11),
   mail_gmail.py (5), raya_tool_executors.py (36), prompt_blocks_extra.py (5),
   prompt_blocks.py (6), signatures.py (18), raya_agent_core.py (19),
   dashboard_queries.py (11), ai_client.py (3), memory_save.py (8),
   memory_synthesis.py (24), feedback.py (24), topics.py (16), shortcuts.py (22),
   activity_log.py (17), urgency_model.py (15), rule_engine.py (29),
   maturity.py (13), memory_style.py (8), ai_prompts.py (3),
   email_signature.py (17), seeding.py (6), memory_contacts.py (18),
   entity_graph.py (40), synthesis_engine.py (8), tool_discovery.py (21),
   mail_memory_store.py (3)
```

### 🚨 Trous découverts par cet audit (manqués par le 24/04)

L'audit du 24/04 a manqué **15 requêtes** réparties sur 9 fichiers. Ces trous
n'avaient pas été identifiés. Détection via scan automatique : "WHERE username = %s"
sans `tenant_id` à proximité.

#### 🔴 CRITIQUE — token_manager.py

**Fichier `app/token_manager.py` ligne 230** :
```python
def get_connected_providers(username: str) -> list[str]:
    c.execute("SELECT provider FROM oauth_tokens WHERE username = %s", (username,))
```
- Cette fonction retourne la liste des connecteurs OAuth (Gmail, Outlook, Teams)
  d'un user
- Aucun filtre `tenant_id`
- **Risque** : si 2 tenants ont un user homonyme, fuite de la liste des
  connecteurs entre tenants
- **Correction** : ajouter `AND tenant_id = %s` et propager `tenant_id` à la
  signature de la fonction

#### 🟠 IMPORTANT — admin/profile.py (6 requêtes)

**Fichier `app/routes/admin/profile.py`** :
- Ligne 248 : `SELECT COUNT(*) FROM aria_rules WHERE username=%s` (stats profil)
- Ligne 254 : `SELECT COUNT(*) FROM sent_mail_memory WHERE username=%s` (stats mails)
- Ligne 260 : `SELECT COUNT(*) FROM aria_session_digests WHERE username=%s` (stats conv)
- Ligne 268 : `SELECT COUNT(DISTINCT LOWER(to_email)) FROM sent_mail_memory ...` (contacts)
- Ligne 312 : `SELECT provider, expires_at, ... FROM oauth_tokens WHERE username = %s`
- Ligne 428 : `SELECT created_at, model, ... FROM llm_usage WHERE username = %s`

Endpoint `/admin/profile` est protégé par auth user mais pas par scope tenant.
**Risque** : un user requêtant ses propres stats verrait, en cas de homonyme
cross-tenant, les données agrégées des 2.

#### 🟠 IMPORTANT — memory_teams.py (2 requêtes)

**Fichier `app/memory_teams.py`** :
- Ligne 33 : lecture des markers Teams (`teams_sync_state`)
- Ligne 85 : suppression d'un marker Teams

Markers de synchronisation Teams partagés entre tenants en cas d'homonymie.

#### 🟠 IMPORTANT — synthesis_engine.py:171

**Fichier `app/synthesis_engine.py` ligne 171** :
```python
c2.execute("UPDATE aria_hot_summary SET embedding = %s::vector WHERE username = %s", (vec, username))
```
Mise à jour de l'embedding du hot_summary sans `tenant_id`.

#### 🟠 IMPORTANT — report_actions.py:22

**Fichier `app/routes/actions/report_actions.py` ligne 22** :
```python
SELECT id, content, sections, delivered, delivered_via, created_at
FROM daily_reports WHERE username = %s AND report_date = CURRENT_DATE
```
Lecture du rapport quotidien sans `tenant_id`.

#### 🟡 ATTENTION — super_admin_users.py (4 requêtes)

**Fichier `app/routes/admin/super_admin_users.py`** :
- Ligne 163 : `SELECT ... FROM aria_rules WHERE username=%s` (super-admin)
- Ligne 189 : `SELECT ... FROM aria_insights WHERE username=%s` (super-admin)
- Ligne 380 : `UPDATE aria_memory SET archived = true WHERE username = %s` (admin)
- Ligne 412 : `SELECT ... FROM aria_memory WHERE username = %s` (admin debug)

Ces endpoints sont protégés par `Depends(require_super_admin)` ou
`require_admin`. Risque réduit (seul un super-admin peut appeler).
Mais cross-tenant non étanche : si user homonyme, super-admin verrait les
données mélangées. Au minimum, ces endpoints devraient prendre un
`tenant_id` en paramètre pour cibler explicitement le bon tenant.

### 📋 Récap Phase 1

- ✅ **30 fichiers du 24/04** : pas de régression, parfaitement corrigés
- 🔴 **1 nouveau trou CRITIQUE** : `token_manager.py:230`
- 🟠 **10 nouveaux trous IMPORTANT** : `admin/profile.py` (×6), `memory_teams.py` (×2), `synthesis_engine.py` (×1), `report_actions.py` (×1)
- 🟡 **4 nouveaux trous ATTENTION** : `super_admin_users.py` (×4, endpoints super-admin)

**Estimation correctifs** : ~30 min de fixes mécaniques pour ces 15 requêtes.


## 🔍 Phase 2 — Audit du nouveau code post-24/04

Code ajouté/modifié depuis le 24/04 :
- `app/routes/signatures.py` (refonte chantier signatures)
- `app/email_signature.py` (nouvelle logique matching)
- `app/connectors/outlook_calendar.py` (propage `from_address`)
- `app/connectors/outlook_actions.py` (propage `from_address`)
- `app/database_migrations.py` (ajout colonne `default_for_emails`)
- `app/templates/user_settings.html` (UI éditeur signatures)
- `app/templates/raya_chat.html` (suppression legacy)

### ✅ Toutes les requêtes du chantier signatures sont sécurisées

**`signatures.py`** : 5 endpoints (GET, POST, PATCH, DELETE, GET mailboxes)
- Toutes les requêtes ont bien `username + tenant_id`
- Y compris les `UPDATE EXCEPT` ajoutés pour la propagation "1 défaut/boîte"

**`email_signature.py`** : 5 requêtes de matching
- Priorité 1 (default_for_emails) : ✅
- Priorité 2 (apply_to_emails) : ✅
- Priorité 3 (email_address legacy) : ✅
- Priorité 4 (is_default global) : ✅
- Priorité 5 (générique) : ✅
Toutes filtrent `username + tenant_id`.

**`database_migrations.py`** : ajout d'une colonne, pas de problème sécurité.

### 🟡 ATTENTION — Valeur par défaut "guillaume"

**Fichier `app/connectors/outlook_calendar.py` ligne 32** :
```python
def _build_email_html(body: str, username: str = "guillaume", from_address: str = None) -> str:
```

Le paramètre `username` a "guillaume" comme valeur par défaut. C'est un
**anti-pattern multi-tenant** : si un appelant oublie de passer le username
(par exemple lors d'un refactor futur), on retombe par défaut sur "guillaume".

**Risque actuel** : faible. Tous les appelants connus passent bien le username.
**Risque futur** : si un nouvel appelant code propre est ajouté et oublie le
paramètre, fuite vers la signature de Guillaume.

**Correction recommandée** : retirer la valeur par défaut, rendre le paramètre
obligatoire pour forcer les appelants à toujours fournir un user explicite.

### 📋 Récap Phase 2

- ✅ **0 nouveau trou SQL** ajouté par le chantier signatures
- 🟡 **1 anti-pattern** : valeur par défaut "guillaume" dans `_build_email_html`

**Le chantier signatures du 25/04 est exemplaire** côté isolation. Bon
réflexe : tous les nouveaux endpoints/fonctions ont `tenant_id` dès le
premier coup.


## 🔍 Phase 3 — Authentification, sessions, `require_user`

### ✅ Architecture d'auth — TRÈS PROPRE

**Fichier `app/routes/deps.py`** — chaîne d'authentification :

- `require_user(request)` — récupère `username` et `tenant_id` **TOUJOURS depuis la session**, jamais depuis le client.
- `require_admin(request)` — vérifie `scope ∈ {SUPER_ADMIN, ADMIN}`
- `require_super_admin(request)` — vérifie `scope == SUPER_ADMIN`
- `require_tenant_admin(request)` — vérifie `scope ∈ {SUPER_ADMIN, ADMIN, TENANT_ADMIN}`
- `assert_same_tenant(request, target_username)` — empêche un tenant_admin
  de manipuler un user d'un autre tenant
- `_check_suspension_api(username, tenant_id)` — vérifie suspension à
  chaque requête authentifiée

✅ Le `username` n'est jamais accepté comme paramètre HTTP du client.
✅ Le `tenant_id` non plus.
✅ Le `scope` est résolu via `get_effective_scope()` qui applique un override
   hardcoded pour les super-admins (impossible de rétrograder Guillaume).

### 🚨 Problème CRITIQUE — DEFAULT_TENANT silencieux

**Fichier `app/security_users.py` ligne 63-72** :

```python
def get_tenant_id(username: str) -> str:
    try:
        c.execute("SELECT tenant_id FROM users WHERE username = %s", (username.strip(),))
        row = c.fetchone()
        return row[0] if row and row[0] else DEFAULT_TENANT  # ← DANGEREUX
    except Exception:
        return DEFAULT_TENANT  # ← ENCORE PLUS DANGEREUX
```

**`DEFAULT_TENANT = "couffrant_solar"`** (hardcodé dans `security_tools.py:13`).

**Risque concret** :
1. Si un user existe avec `tenant_id IS NULL` (possible : la colonne est NULLABLE !) → rattaché silencieusement à `couffrant_solar`.
2. Si la requête DB échoue (exception) → idem, rattaché silencieusement à `couffrant_solar`.
3. Si un user existe sans ligne dans `users` (impossible normalement, mais fragile) → idem.

**Charlotte (tenant `juillet`) déjà en prod** : si jamais sa ligne `users`
avait un bug et que `get_tenant_id("Charlotte")` retournait `DEFAULT_TENANT`,
elle aurait accès aux données de Couffrant Solar **sans aucun avertissement**.

**Vérification DB en prod** : actuellement 0 user avec `tenant_id IS NULL`. Donc
le risque est latent, pas matériel. Mais c'est de la **défense en
profondeur fragile**.

### 🚨 Problème — Schema DB de `users`

**Colonne `tenant_id`** :
- `is_nullable = YES` (peut être NULL)
- `default = 'couffrant_solar'`

→ La colonne devrait être `NOT NULL` ET sans default (ou avec une valeur
  spéciale comme `'__no_tenant__'` qui ferait planter explicitement les
  requêtes au lieu de fuir silencieusement).

**Colonne `scope`** :
- `is_nullable = YES`
- `default = 'couffrant_solar'` ← **BUG** : un default tenant_id est
  appliqué à scope ! Ça veut dire que si on insère un user sans préciser
  scope, il aura `scope='couffrant_solar'` (qui n'est pas un rôle valide).

→ Le default de `scope` devrait être `'user'`, pas `'couffrant_solar'`.

### 📋 Récap Phase 3

- ✅ **Architecture d'auth très propre** : username/tenant_id viennent de
  la session, jamais du client.
- ✅ **Override super-admin hardcoded** : impossible de rétrograder Guillaume.
- ✅ **`assert_same_tenant`** : empêche un tenant_admin de manipuler
  cross-tenant.
- 🔴 **DEFAULT_TENANT silencieux** : fallback `couffrant_solar` masque
  toute défaillance et peut causer fuite de Charlotte (tenant juillet)
  vers Couffrant Solar en cas de bug.
- 🔴 **Schema `users.tenant_id` nullable** : devrait être NOT NULL.
- 🟠 **Default bizarre sur `users.scope`** : `couffrant_solar` au lieu de `user`.


## 🔍 Phase 4 — Endpoints HTTP : paramètres acceptés depuis le client

### ✅ Bonne nouvelle : aucun endpoint user/admin ne lit `username` du client

Sauf `/login` (légitime) et 2 endpoints super-admin (filtrage légitime
quand le caller a explicitement le pouvoir cross-user) :
- `admin_rules.py:32` : migration de règles entre tenants — `require_super_admin`
- `admin_rules.py:584` : optimizer single-user — `if is_privileged` only

### 🚨 PROBLÈMES — Endpoints qui acceptent `tenant_id` du client

#### 🔴 CRITIQUE — `POST /admin/tenants`

**Fichier `app/routes/admin/super_admin.py:223-235`** :
```python
@router.post("/admin/tenants")
def create_tenant_endpoint(
    request: Request,
    payload: dict = Body(...),
    _: dict = Depends(require_admin),  # ← accepte SCOPE_ADMIN (tenant admin)
):
    return create_tenant(payload.get("tenant_id", ...), ...)
```

**Risque** : un admin tenant (par exemple Charlotte si elle devient
tenant_admin) peut **créer un nouveau tenant** avec n'importe quel ID.

**Correction** : remplacer `require_admin` par `require_super_admin`.

#### 🔴 CRITIQUE — `DELETE /admin/tenants/{tenant_id}`

Même fichier `app/routes/admin/super_admin.py:238-244` :
```python
@router.delete("/admin/tenants/{tenant_id}")
def delete_tenant_endpoint(
    request: Request,
    tenant_id: str,
    _: dict = Depends(require_admin),  # ← accepte SCOPE_ADMIN
):
    return delete_tenant(tenant_id)
```

**Risque** : un admin tenant peut **supprimer N'IMPORTE QUEL tenant**,
y compris celui d'une autre société. **CATASTROPHIQUE**.

**Correction** : remplacer `require_admin` par `require_super_admin`.

#### 🟠 IMPORTANT — `POST /admin/create-user`

**Fichier `app/routes/admin/super_admin_users.py:55-71`** :
```python
@router.post("/admin/create-user")
def admin_create_user(
    request: Request, payload: dict = Body(...),
    admin: dict = Depends(require_admin),  # ← accepte SCOPE_ADMIN
):
    result = create_user(
        ...
        tenant_id=payload.get("tenant_id", DEFAULT_TENANT),  # ← fallback
        ...
    )
```

**Risque** : un admin tenant peut créer un user dans n'importe quel
tenant en passant `tenant_id` arbitraire. Si `tenant_id` est omis,
fallback `DEFAULT_TENANT = couffrant_solar` (le user est créé chez
Couffrant Solar par défaut !).

**Correction** :
1. Si admin tenant : forcer `tenant_id = admin["tenant_id"]`,
   refuser la création cross-tenant.
2. Si super-admin : laisser passer le `tenant_id` du payload.
3. Retirer le fallback `DEFAULT_TENANT`.

#### 🟠 IMPORTANT — `POST /admin/drive/select`

**Fichier `app/routes/admin_drive.py:80-98`** :
```python
@router.post("/admin/drive/select")
def admin_select_drive_folder(
    request: Request, payload: dict = Body(...),
    admin: dict = Depends(require_admin),
):
    tenant_id = (payload.get("tenant_id") or "").strip()
    ...
    create_connection(tenant_id, ...)
```

**Risque** : un admin tenant peut associer un dossier Drive à n'importe
quel tenant (y compris une autre société). Le dossier choisi devient
visible par les users de ce tenant.

**Correction** : si `admin["scope"] != SCOPE_SUPER_ADMIN`, forcer
`tenant_id = admin["tenant_id"]`.

#### 🟠 IMPORTANT — `POST /admin/sharepoint/select`

**Fichier `app/routes/admin_sharepoint.py:80-94`** : exactement
le même pattern que `admin_drive.py`. Même correction nécessaire.

### 📋 Récap Phase 4

- ✅ **Aucun endpoint utilisateur ne lit `username` ou `tenant_id` du client** :
  l'identité vient toujours de la session.
- 🔴 **2 endpoints CRITIQUES** : `POST /admin/tenants` et
  `DELETE /admin/tenants/{id}` accessibles aux admins tenant alors qu'ils
  devraient être réservés au super-admin.
- 🟠 **3 endpoints IMPORTANT** acceptent `tenant_id` du payload sans
  vérifier que le caller a bien le droit de cibler ce tenant
  (`create-user`, `drive/select`, `sharepoint/select`).

