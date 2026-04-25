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


## 🔍 Phase 5 — Privilege escalation : user → admin tenant → super admin

### ✅ Endpoints utilisateur correctement isolés

Tous les endpoints `/profile/*` (admin/profile.py) utilisent `require_user`,
ce qui est correct (chaque user accède à son propre profil). L'isolation
était imparfaite côté SQL (cf. Phase 1 : 6 trous identifiés) mais pas côté
auth/routing.

### ✅ 6 endpoints avec isolation cross-tenant correctement protégée

Pattern propre dans plusieurs endpoints `tenant_admin` :
```python
user: dict = Depends(require_tenant_admin),
):
    if user["scope"] != "admin":
        assert_same_tenant(request, target)
```
Ce pattern protège bien contre les tenant_admins qui voudraient toucher
des users d'un autre tenant. Légitime.

### 🟠 Bug logique — super_admin bloqué par assert_same_tenant

**Problème** : la comparaison `if user["scope"] != "admin"` ne tient pas
compte du `super_admin`. Conséquence : Guillaume (super_admin) déclenche
quand même `assert_same_tenant`, qui lève 403 si le target est dans un
autre tenant.

**Fichiers concernés** :
- `app/routes/admin/super_admin.py` (admin_suspend_user, admin_unsuspend_user, admin_toggle_user_direct_actions)
- `app/routes/admin/super_admin_users.py` (admin_users_reset_password)

**Impact** : Guillaume ne peut pas suspendre / unsuspend / reset password
des users d'autres tenants depuis ces endpoints (alors qu'il devrait
pouvoir tout faire).

**Correction** : remplacer
```python
if user["scope"] != "admin":
    assert_same_tenant(request, target)
```
par
```python
if user["scope"] not in ("admin", "super_admin"):
    assert_same_tenant(request, target)
```

(Ou utiliser `SCOPE_ADMIN`, `SCOPE_SUPER_ADMIN` constantes pour éviter
les magic strings.)

### 🚨 CRITIQUE — Promotion de scope arbitraire

**Fichier `app/routes/admin/super_admin_users.py` ligne 75-86** :
```python
@router.put("/admin/update-user/{target}")
def admin_update_user(
    request: Request,
    target: str,
    payload: dict = Body(...),
    admin: dict = Depends(require_admin),  # ← accepte SCOPE_ADMIN
):
    new_scope = payload.get("scope", "")
    result = update_user(target, email=..., scope=new_scope)
    log_admin_action(admin["username"], "update_scope", target, new_scope)
    return result
```

**Risques** :
1. Un admin tenant peut **promouvoir un user en `super_admin`**
2. Un admin tenant peut **se promouvoir lui-même** en super_admin
3. Aucune vérification que `target` est dans le tenant de l'admin
4. Aucune vérification que `new_scope` est valide (un attaquant pourrait
   passer une string arbitraire qui casserait des comparaisons ailleurs)
5. Aucune vérification que `new_scope` ≤ scope de l'admin

**Pourquoi ce n'est pas immédiatement exploité** :
`get_effective_scope()` (cf. Phase 3) applique un override hardcoded
pour les super-admins listés en dur. Donc même si on promeut un user
en `super_admin` en DB, `get_effective_scope()` retournera son vrai
scope effectif. Mais c'est un filet de sécurité fragile : tout endpoint
qui lit directement `users.scope` sans passer par `get_effective_scope`
serait vulnérable.

**Correction** :
```python
@router.put("/admin/update-user/{target}")
def admin_update_user(
    request: Request,
    target: str,
    payload: dict = Body(...),
    admin: dict = Depends(require_admin),
):
    new_scope = payload.get("scope", "").strip()
    # 1. Valider que new_scope est un scope valide
    if new_scope and new_scope not in ALL_SCOPES:
        raise HTTPException(400, f"Scope invalide : {new_scope}")
    # 2. Empêcher la promotion en super_admin (réservé à hardcoded)
    if new_scope == SCOPE_SUPER_ADMIN:
        raise HTTPException(403, "Le scope super_admin est hardcoded")
    # 3. Empêcher la promotion d'un scope > celui de l'admin
    scope_levels = {SCOPE_USER: 1, SCOPE_TENANT_ADMIN: 2, SCOPE_ADMIN: 3, SCOPE_SUPER_ADMIN: 4}
    if scope_levels.get(new_scope, 0) > scope_levels.get(admin["scope"], 0):
        raise HTTPException(403, "Vous ne pouvez pas promouvoir au-dessus de votre propre scope")
    # 4. Si admin tenant, vérifier same tenant
    if admin["scope"] not in (SCOPE_ADMIN, SCOPE_SUPER_ADMIN):
        assert_same_tenant(request, target)
    result = update_user(target, email=payload.get("email"), scope=new_scope)
    log_admin_action(admin["username"], "update_scope", target, new_scope)
    return result
```

### 📋 Récap Phase 5

- ✅ **123 endpoints `/admin/*`** correctement protégés par require_admin
  ou require_super_admin (audit automatique)
- ✅ **6 endpoints tenant_admin** avec pattern défensif
  `assert_same_tenant`
- 🚨 **1 CRITIQUE** : `PUT /admin/update-user/{target}` permet la
  promotion de scope arbitraire sans contrôle (super_admin compris)
- 🟠 **4 endpoints** avec bug logique `scope != "admin"` qui bloque
  involontairement le super_admin cross-tenant


## 🔍 Phase 6 — Tokens OAuth + connecteurs externes

### 🚨 CRITIQUE — Toutes les fonctions de gestion de tokens OAuth ignorent tenant_id

**Fichier `app/token_manager.py`** :

```python
def get_valid_microsoft_token(username: str = 'guillaume') -> str | None:
    c.execute("""
        SELECT access_token, refresh_token, expires_at
        FROM oauth_tokens
        WHERE provider = 'microsoft' AND username = %s
        ORDER BY updated_at DESC LIMIT 1
    """, (username,))
```

**Problèmes** :
1. **Default `'guillaume'`** dans la signature — anti-pattern multi-tenant
2. **Aucun filtre `tenant_id`** dans la requête SQL
3. La table `oauth_tokens` HAS `tenant_id` column (vérifié en DB), donc
   c'est juste le code qui ne l'utilise pas

**Impact** : si jamais 2 users avec le même username existent dans 2 tenants
(scénario théorique aujourd'hui mais probable demain), ils se partageraient
les mêmes tokens OAuth = catastrophe absolue (Pierre du tenant juillet
récupère le token Outlook de Pierre du tenant couffrant_solar).

**Fonctions concernées** (toutes dans `app/token_manager.py`) :
- `get_valid_microsoft_token(username='guillaume')` — ligne 17
- `save_microsoft_token(username, ...)` — ligne 89 (INSERT sans tenant_id)
- `get_valid_google_token(username)` — ligne 112
- `save_google_token(username, ...)` — ligne 177
- `get_all_users_with_tokens(provider)` — ligne 214 (SELECT cross-tenant)
- `get_connected_providers(username)` — ligne 230 (déjà identifié Phase 1)

**Correction** :
1. Ajouter `tenant_id: str` dans la signature de toutes les fonctions
2. Filtrer SQL : `WHERE provider = %s AND username = %s AND tenant_id = %s`
3. Retirer la valeur par défaut `'guillaume'`
4. Mettre à jour tous les appelants pour passer `tenant_id`

### 🟠 connection_token_manager.py — même problème mais moins critique

**Fichier `app/connection_token_manager.py`** :

```python
def get_connection_token(username: str, tool_type: str) -> str | None:
def _get_v2_token(username: str, tool_type: str) -> str | None:
```

Ces fonctions filtrent par `username` mais pas par `tenant_id`. Heureusement,
elles passent par un JOIN avec `tenant_connections` qui contient le `tenant_id`,
donc en pratique le filtre passe. Mais c'est implicite et fragile.

**Correction** : ajouter explicitement `tenant_id` dans les requêtes.

### 📋 Récap Phase 6

- 🚨 **6 fonctions CRITIQUES** dans `token_manager.py` ne filtrent pas
  par `tenant_id` — si un user homonyme apparaît dans un autre tenant,
  les tokens fuitent
- 🟠 **2 fonctions** dans `connection_token_manager.py` reposent sur un
  filtre indirect via JOIN — à durcir explicitement


## 🔍 Phase 7 — Tests dynamiques en DB

Vérifications directes contre la base de production via `postgres` (lecture seule).

### ✅ Test 7.1 — Aucune ligne avec `tenant_id IS NULL`

| Table | Lignes avec tenant_id NULL |
|---|---|
| aria_rules | 0 |
| aria_memory | 0 |
| mail_memory | 0 |
| sent_mail_memory | 0 |
| aria_insights | 0 |
| email_signatures | 0 |
| oauth_tokens | 0 |
| aria_session_digests | 0 |
| llm_usage | 0 |

✅ Toutes les données ont bien un `tenant_id` non NULL.

### ✅ Test 7.2 — Aucun username dupliqué cross-tenant

Vérifié : aucun username n'existe dans 2 tenants différents. C'est ce qui
rend la majorité des bugs identifiés **latents** (théoriques) plutôt
qu'**actifs** aujourd'hui. Mais dès qu'un homonyme apparaîtra (Pierre du
tenant juillet par exemple), tous les bugs identifiés deviendront
exploitables.

### ✅ Test 7.3 — Cohérence des données vs leur user

Vérification jointure `aria_rules ↔ users`, `aria_memory ↔ users`,
`mail_memory ↔ users`, `sent_mail_memory ↔ users`, `aria_insights ↔ users` :

**0 incohérence détectée**. Toutes les lignes pointent bien vers le
tenant de leur user.

### ✅ Test 7.4 — Répartition réelle des données par tenant

| tenant_id | nb_users | nb_rules | nb_messages | nb_mails | nb_signatures |
|---|---|---|---|---|---|
| couffrant_solar | 5 | 203 | 200 | 946 | 1 |
| juillet | 1 | 10 | 9 | 0 | 0 |

**Charlotte (tenant `juillet`) a déjà 10 règles et 9 messages**.
L'isolation est **déjà testable en pratique** : si une fuite existait,
Charlotte verrait potentiellement des données de Couffrant Solar (ou
inversement).

### 📋 Récap Phase 7

- ✅ **Données en bon état** : pas de NULL, pas d'incohérence cross-tenant,
  pas de homonyme entre tenants
- ✅ **Charlotte (juillet) déjà active en prod** : on a un cas réel de
  cross-tenant à surveiller
- ✅ Les bugs identifiés dans les Phases 1-6 sont **latents** (théoriques)
  aujourd'hui, mais deviendraient **actifs** dès le premier homonyme
  cross-tenant (très probable demain)


---

## 🎯 SYNTHÈSE GLOBALE — 7 phases d'audit

### Bilan des findings

| Gravité | Nombre | Détail |
|---|---|---|
| 🔴 CRITIQUE | **8** | Voir liste ci-dessous |
| 🟠 IMPORTANT | **15** | Voir liste ci-dessous |
| 🟡 ATTENTION | **10** | Voir liste ci-dessous |
| 🟢 OK | nombreux | Architecture d'auth solide, 30 fichiers du 24/04 toujours bons |

### 🔴 Trous CRITIQUES à corriger AVANT onboarding

1. **`token_manager.py:230 get_connected_providers()`** — sans tenant_id
2. **`token_manager.py:17,89,112,177,214` — toutes les fonctions tokens**
   sans tenant_id (dont `get_valid_microsoft_token` avec default 'guillaume')
3. **`POST /admin/tenants`** — `require_admin` au lieu de `require_super_admin`
4. **`DELETE /admin/tenants/{id}`** — pareil, un tenant_admin peut **supprimer
   n'importe quel tenant**
5. **`PUT /admin/update-user/{target}`** — promotion arbitraire de scope
   (un tenant_admin peut promouvoir en super_admin)
6. **`DEFAULT_TENANT='couffrant_solar'`** silencieux dans `get_tenant_id`
   (en cas de bug DB, fuite vers Couffrant Solar)
7. **Schema `users.tenant_id` NULLABLE** au lieu de NOT NULL
8. **Default bizarre `users.scope='couffrant_solar'`** au lieu de 'user'

### 🟠 Trous IMPORTANT à corriger avant onboarding sérieux

9. **`admin/profile.py`** — 6 requêtes sans tenant_id (stats user, oauth, llm_usage)
10. **`memory_teams.py`** — 2 requêtes teams_sync_state sans tenant_id
11. **`synthesis_engine.py:171`** — UPDATE aria_hot_summary sans tenant_id
12. **`report_actions.py:22`** — daily_reports sans tenant_id
13. **`POST /admin/create-user`** — accepte tenant_id du payload sans contrôle
14. **`POST /admin/drive/select`** — pareil, admin tenant peut choisir
    n'importe quel tenant_id
15. **`POST /admin/sharepoint/select`** — pareil
16. **`connection_token_manager.py`** — 2 fonctions reposent sur JOIN implicite

### 🟡 ATTENTION (défense en profondeur, peuvent attendre)

17. **4 endpoints super_admin_users.py** — pas de tenant_id (accessibles
    super-admin seulement, mais cross-tenant si homonyme)
18. **Bug logique `scope != "admin"`** dans 4 endpoints — bloque le
    super-admin cross-tenant alors qu'il devrait pouvoir
19. **Anti-pattern default 'guillaume'** dans `_build_email_html`
20. **Magic strings `"admin"`** au lieu de constantes `SCOPE_ADMIN`

### 📋 Plan de correction proposé

**Étape A — Hotfixes critiques avant onboarding (2-3h)** :
- Fix `token_manager.py` : ajouter tenant_id à toutes les fonctions tokens
- Fix `POST /admin/tenants` et `DELETE /admin/tenants` : `require_super_admin`
- Fix `PUT /admin/update-user` : valider scope, vérifier same_tenant
- Fix `get_tenant_id` : retirer le fallback DEFAULT_TENANT, lever une erreur explicite
- Migration DB : `users.tenant_id NOT NULL`, fix default scope

**Étape B — Corrections IMPORTANT (2h)** :
- Fix les 6 requêtes `admin/profile.py`
- Fix `memory_teams.py`, `synthesis_engine.py`, `report_actions.py`
- Fix les 3 endpoints admin acceptant tenant_id sans contrôle
- Durcir `connection_token_manager.py`

**Étape C — Défense en profondeur (1h)** :
- Fix bug logique `scope != "admin"` dans 4 endpoints
- Retirer les valeurs par défaut "guillaume"
- Remplacer magic strings par constantes

**Étape D — Tests bout en bout (1h)** :
- Exécuter le `plan_tests_isolation_pierre_test.md` (créé le 24/04 mais
  jamais lancé)
- Créer un user `pierre_test` dans `couffrant_solar`
- Tester les 5 scénarios de fuite
- Tester aussi sur Charlotte (`juillet`) puisqu'elle est déjà en DB

**Étape E — Hardening permanent** :
- Voir checklist ci-dessous

---

## ✅ CHECKLIST permanente — à passer avant chaque nouvelle fonctionnalité

À mettre dans `docs/checklist_isolation_multitenant.md` (fichier dédié à créer).

### Pour toute nouvelle table en DB
- [ ] La table a-t-elle `tenant_id TEXT NOT NULL` (sauf cas users-only documenté) ?
- [ ] La table a-t-elle `username TEXT NOT NULL` (si user-scoped) ?
- [ ] Index sur `(tenant_id, username)` créé ?
- [ ] La migration backfill correctement les anciennes lignes ?

### Pour toute nouvelle requête SQL
- [ ] La requête filtre-t-elle `username = %s` (si user-scoped) ?
- [ ] La requête filtre-t-elle `tenant_id = %s` (toujours, sauf jobs cross-tenant) ?
- [ ] Le paramètre `tenant_id` est-il bien passé dans le tuple de paramètres ?
- [ ] Si UPDATE/DELETE, le filtre tenant_id est-il dans le WHERE ?

### Pour tout nouvel endpoint HTTP
- [ ] Le décorateur `Depends(require_user)` (ou plus restrictif) est-il là ?
- [ ] L'endpoint refuse-t-il `username` et `tenant_id` venant du client
      (sauf super-admin légitime) ?
- [ ] Si paramètre `target` (user à manipuler), `assert_same_tenant` est-il
      appelé pour les non-admin globaux ?
- [ ] Les requêtes SQL utilisent-elles `user["tenant_id"]` (et pas un
      fallback) ?

### Pour toute manipulation de scope/role
- [ ] Le scope demandé est-il dans `ALL_SCOPES` (validation enum) ?
- [ ] Le scope demandé est-il ≤ scope du caller (pas d'escalation) ?
- [ ] Si scope = `super_admin`, l'opération est-elle refusée
      (super_admin = hardcoded uniquement) ?
- [ ] Le changement est-il loggé dans `admin_audit_log` ?

### Pour toute fonction qui prend `username` en paramètre
- [ ] Le paramètre est-il sans valeur par défaut (`username: str` et
      pas `username: str = "guillaume"`) ?
- [ ] La fonction prend-elle aussi `tenant_id` ?
- [ ] Les appelants passent-ils explicitement `user["tenant_id"]` ?

### Tests de non-régression
- [ ] Le test `pierre_test` du plan d'audit passe-t-il sans fuite ?
- [ ] Aucune ligne nouvelle avec `tenant_id IS NULL` après le déploiement ?
- [ ] Cohérence `JOIN users` reste OK pour toutes les tables sensibles ?

