# ✅ Checklist permanente — Isolation multi-tenant

**Source** : extraite de `audit_isolation_25avril_complementaire.md`
**Usage** : à passer **systématiquement** avant chaque nouvelle fonctionnalité
qui touche aux données utilisateur ou multi-tenant.

> Cette checklist est la **source de vérité** pour les futures sessions.
> Une fonctionnalité qui ne coche pas tous ces points = ne pas merger.

---

## 1. Pour toute nouvelle table en DB

- [ ] La table a-t-elle `tenant_id TEXT NOT NULL` (sauf cas users-only documenté) ?
- [ ] La table a-t-elle `username TEXT NOT NULL` (si user-scoped) ?
- [ ] Index sur `(tenant_id, username)` créé ?
- [ ] La migration backfill correctement les anciennes lignes ?
- [ ] La migration est-elle ajoutée dans `app/database_migrations.py` (idempotent) ?

## 2. Pour toute nouvelle requête SQL

- [ ] La requête filtre-t-elle `username = %s` (si user-scoped) ?
- [ ] La requête filtre-t-elle `tenant_id = %s` (toujours, sauf jobs cross-tenant) ?
- [ ] Le paramètre `tenant_id` est-il bien passé dans le tuple de paramètres ?
- [ ] Si UPDATE/DELETE, le filtre tenant_id est-il dans le WHERE ?
- [ ] Pas de pattern dangereux `WHERE username IN (SELECT ... WHERE tenant_id)` :
      préférer un filtre direct `WHERE tenant_id = %s AND username = %s` ?

## 3. Pour tout nouvel endpoint HTTP

- [ ] Le décorateur `Depends(require_user)` (ou plus restrictif) est-il là ?
- [ ] L'endpoint refuse-t-il `username` et `tenant_id` venant du client
      (sauf super-admin légitime) ?
- [ ] Si paramètre `target` (user à manipuler), `assert_same_tenant` est-il
      appelé pour les non-admin globaux ?
- [ ] Les requêtes SQL utilisent-elles `user["tenant_id"]` (et pas un
      fallback hardcoded) ?
- [ ] Si endpoint super-admin, utilise `require_super_admin` (PAS `require_admin`) ?
- [ ] Si endpoint admin, utilise `require_admin` (PAS `require_user`) ?

## 4. Pour toute manipulation de scope/role

- [ ] Le scope demandé est-il dans `ALL_SCOPES` (validation enum) ?
- [ ] Le scope demandé est-il ≤ scope du caller (pas d'escalation) ?
- [ ] Si scope = `super_admin`, l'opération est-elle refusée
      (super_admin = hardcoded uniquement) ?
- [ ] Le changement est-il loggé dans `admin_audit_log` ?

## 5. Pour toute fonction qui prend `username` en paramètre

- [ ] Le paramètre est-il **sans valeur par défaut** ?
      (`username: str` et **pas** `username: str = "guillaume"`)
- [ ] La fonction prend-elle aussi `tenant_id` ?
- [ ] Les appelants passent-ils explicitement `user["tenant_id"]` ?
- [ ] Pas de fallback silencieux `DEFAULT_TENANT` qui masquerait une erreur ?

## 6. Pour toute manipulation cross-tenant (super-admin only)

- [ ] L'opération est-elle protégée par `Depends(require_super_admin)` ?
- [ ] Le `tenant_id` cible est-il loggé dans `admin_audit_log` ?
- [ ] Y a-t-il une trace explicite "super-admin a modifié tenant X" ?

## 7. Tests de non-régression

- [ ] Le plan `plan_tests_isolation_pierre_test.md` passe sans fuite ?
- [ ] Aucune ligne nouvelle avec `tenant_id IS NULL` après le déploiement ?
- [ ] Cohérence `JOIN users` reste OK pour toutes les tables sensibles ?

---

## Anti-patterns à NE PAS reproduire

### ❌ Default value sur un paramètre username/tenant_id

```python
# INTERDIT
def get_token(username: str = "guillaume"):
    ...
```

Si un appelant oublie le paramètre, on retombe silencieusement sur Guillaume.
Catastrophe en cas d'homonyme cross-tenant.

```python
# CORRECT
def get_token(username: str, tenant_id: str):
    ...
```

### ❌ Fallback silencieux DEFAULT_TENANT

```python
# INTERDIT
def get_tenant_id(username):
    try:
        ...
    except Exception:
        return DEFAULT_TENANT  # ← masque les bugs
```

```python
# CORRECT
def get_tenant_id(username):
    try:
        ...
    except Exception as e:
        raise ValueError(f"Cannot resolve tenant_id for {username}: {e}")
```

### ❌ Comparaison string `scope != "admin"`

```python
# INTERDIT (le super_admin n'est pas "admin", donc déclenche assert_same_tenant)
if user["scope"] != "admin":
    assert_same_tenant(request, target)
```

```python
# CORRECT
if user["scope"] not in (SCOPE_ADMIN, SCOPE_SUPER_ADMIN):
    assert_same_tenant(request, target)
```

### ❌ Endpoint admin avec `require_user`

```python
# INTERDIT
@router.delete("/admin/tenants/{tenant_id}")
def delete_tenant(_: dict = Depends(require_user)):
    ...
```

Tout endpoint sous `/admin/` doit avoir au minimum `require_admin`.
Tout endpoint qui touche cross-tenant doit avoir `require_super_admin`.

### ❌ Accepter `tenant_id` du payload sans contrôle

```python
# INTERDIT
@router.post("/admin/connect-drive")
def connect_drive(payload: dict, admin: dict = Depends(require_admin)):
    tenant_id = payload.get("tenant_id")  # ← admin tenant peut cibler n'importe quoi
    ...
```

```python
# CORRECT
@router.post("/admin/connect-drive")
def connect_drive(payload: dict, admin: dict = Depends(require_admin)):
    if admin["scope"] not in (SCOPE_ADMIN, SCOPE_SUPER_ADMIN):
        # Tenant_admin peut seulement cibler son propre tenant
        tenant_id = admin["tenant_id"]
    else:
        tenant_id = payload.get("tenant_id", admin["tenant_id"])
    ...
```

---

*Document vivant. À mettre à jour après chaque nouvel anti-pattern détecté.*
