# ✅ Permissions tenant Read/Write/Delete v1 — Livraison 18/04/2026

## Synthèse

Système de permissions 3 niveaux (`read` / `read_write` / `read_write_delete`)
avec hiérarchie super admin → tenant admin, implémenté en **7 étapes sur 7**
dans la nuit du 18/04/2026.

**Plan stratégique source** : `docs/raya_permissions_plan.md` (319 lignes)

## Étapes livrées

### Étape 1 — Migration DB (commit `70174c6`)

- 3 colonnes ajoutées à `tenant_connections` :
  - `super_admin_permission_level` (default `'read'`)
  - `tenant_admin_permission_level` (default `'read'`)
  - `previous_permission_level` (null par défaut, pour le toggle)
- 2 CHECK constraints (valeurs autorisées)
- Nouvelle table `permission_audit_log` avec 2 index

### Étape 2 — Module core (commit `70174c6`)

Fichier `app/permissions.py` (456 lignes) :
- `PERMISSION_LEVELS` : ('read', 'read_write', 'read_write_delete')
- `ACTION_PERMISSION_MAP` : **45 tags mappés** (ODOO_*, SEND_MAIL, etc.)
- `get_required_permission(tag)` : fallback `'read_write_delete'` pour inconnus
- `level_satisfies(current, required)` : comparaison hiérarchique
- `cap_level(wanted, cap)` : minimum entre les 2
- `check_permission(tenant_id, username, action_tag, excerpt)` : fonction principale
- `_log_audit(...)` : insert silencieux dans audit log
- `get_all_permissions_for_tenant(tenant_id)` : pour injection prompt
- `update_permission(tenant, connection_id, level, actor_role)` : hiérarchie
- `toggle_all_read_only(tenant_id, actor_role)` : bouton 🔒

### Étape 3 — Middleware d'interception (commit `a949c16`)

- `app/routes/actions/odoo_actions.py` : helper `_check_perm()` qui wrappe
  ODOO_CREATE, ODOO_UPDATE, ODOO_NOTE
- `app/routes/actions/mail_actions.py` : check SEND_MAIL dans `_queue_send_mail`
- Refus explicite avec message 🔒 dans `confirmed` (Raya peut l'expliquer)
- En cas d'erreur système : autorise par défaut (ne bloque pas Raya)

### Étape 4 — UI tenant_panel (commit `67f5daf`)

- 3 endpoints dans `app/routes/admin/tenant_admin.py` :
  - `GET /tenant/permissions`
  - `POST /tenant/permissions/update`
  - `POST /tenant/permissions/toggle-read-only`
- Section "🔐 Permissions des connexions" dans `tenant_panel.html`
- Tableau avec radio buttons par connexion (3 niveaux)
- Bouton "🔒 Tout en lecture seule" avec toggle restore
- Radios grisés au-dessus du plafond super admin
- 3 fonctions JS : `loadPermissions()`, `updatePermission()`, `toggleReadOnly()`

### Étape 5 — UI admin_panel super admin (commit `9c277c6`)

- 3 endpoints dans `app/routes/admin/super_admin.py` :
  - `GET /admin/permissions/overview`
  - `POST /admin/permissions/update-cap`
  - `POST /admin/permissions/toggle-read-only-global`
- Bouton "🔒 Tout en lecture (GLOBAL)" dans le tab Sociétés
- Fonction JS `toggleReadOnlyGlobal()` avec confirm préalable
- Cache-bust `admin-panel.js` v=40 → v=41

### Étape 6 — Injection dans le prompt Raya (commit `186b79e`)

- Fonction `_build_permissions_block(tenant_id)` dans `app/routes/aria_context.py`
- Injection `{PERMISSIONS_BLOCK}` après `tools_listing`
- Raya voit désormais :
  ```
  === TES PERMISSIONS SUR LES CONNEXIONS ===
  - odoo : LECTURE SEULE (chercher, lister, consulter)
  - gmail : LECTURE + ECRITURE (creer, modifier, envoyer)
  Respecte ces limites...
  ```

### Étape 7 — Tests (ce commit)

Tests unitaires de régression passés :
- `ODOO_SEARCH` → `read` ✅
- `ODOO_CREATE` → `read_write` ✅
- `ODOO_DELETE` → `read_write_delete` ✅
- `TAG_INCONNU` → `read_write_delete` (sécurité par défaut) ✅
- `level_satisfies('read_write', 'read')` → True ✅
- `level_satisfies('read', 'read_write')` → False ✅
- `cap_level('read_write_delete', 'read')` → `'read'` ✅

Compile check : **7 modules** importés avec succès
(permissions, database_migrations, aria_context, odoo_actions, mail_actions,
tenant_admin, super_admin).

## Roadmap v2 future

Tout ce qui est codé en v1 reste pérenne. La v2 ajoutera :
- Granularité par **famille d'action** pour le tenant admin (SEARCH/CREATE/UPDATE/DELETE/SEND)
- Possibilité pour l'**user** de se restreindre sous son plafond admin
- Le **super admin reste** au niveau connexion (jamais de famille d'action)
- Vue détaillée "Plafonds par tenant" (tableau tenants × connexions × niveau)

Conditions de passage à v2 : v1 stable 2-3 semaines + 3+ tenants actifs
+ retours indiquant besoin de granularité fine.

## Politique sécurité temporaire active

Toutes les connexions en `read` par défaut à la création.
Seule exception consciente : compte Guillaume en `read_write` pour tests.
À passer en `read` total avant ouverture aux early adopters.

## Commits de la journée (permissions)

1. `0a2d501` — Plan stratégique 319 lignes
2. `70174c6` — Étapes 1+2 (DB + module 456 lignes)
3. `186b79e` — Étape 6 (injection prompt)
4. `a949c16` — Étape 3 (middleware Odoo + Mail)
5. `67f5daf` — Étape 4 (UI tenant_panel)
6. `9c277c6` — Étape 5 (UI admin_panel)
7. `[ce commit]` — Étape 7 (tests + doc livraison)

**Total : ~550 lignes de code + 320 lignes de plan + 1 table DB + 3 colonnes.**


---

## 🔧 PATCH v1.1 — Nuit 18→19/04 (~3h dev UX)

Après livraison v1 initiale, Guillaume a testé et signalé une série de bugs
UX qui ont nécessité 10+ patchs correctifs. État stabilisé à 3h du matin.

### Fixes livrés

**Backend** (`app/permissions.py`)
- Nouveau `get_tenant_lock_status(tenant_id)` pour état détaillé
- Fix critique dans `toggle_all_read_only` : ne touche PLUS JAMAIS à
  `super_admin_permission_level` (évite l'effondrement du plafond lors
  d'un cycle verrouiller/restaurer)

**Backend endpoints** (`app/routes/admin/`)
- `GET /tenant/permissions/lock-status` (tenant admin)
- `GET /admin/tenant/{id}/lock-status` (super admin)
- `GET /admin/tenant/{id}/permissions` (super admin)
- `POST /admin/tenant/{id}/permissions/update` (super admin)
- `POST /admin/tenant/{id}/toggle-read-only` (super admin)

**Frontend tenant_panel** (`app/templates/tenant_panel.html`)
- Variable globale `_lastPermissionsState` (source unique de vérité)
- Repaint forcé avant prompt() (2 animation frames + 50ms)
- Cache-bust `?_=Date.now()` + {cache: 'no-store'}
- Radios disabled + opacity 0.5 + bandeau rouge quand verrouillé
- Cadenas correct : 🔒 Lecture seule (rouge) / 🔓 Lecture écriture (transparent)
- Confirmation textuelle "oui" (plus de confirm())

**Frontend admin-panel** (`app/static/admin-panel.js` v=51)
- Section "🔐 Permissions des connexions" dans chaque carte tenant
- 2 colonnes de radios : Plafond super admin / Niveau appliqué tenant
- Bouton `🔒 Lecture seule` / `🔓 Lecture écriture` par tenant (plus de bouton global)
- `_tenantLockState` cache local invalidé après chaque action
- Confirmation textuelle "oui" aussi

**Migration DB**
- Valeur par défaut `super_admin_permission_level` passée de `'read'` à `'read_write_delete'`
- UPDATE manuel des 5 connexions Couffrant Solar pour nettoyer l'historique

### Cascade de permissions — règle finale

```
Plafond super_admin (read/read_write/read_write_delete)
  └─> Niveau appliqué tenant_admin (≤ plafond)
       └─> Permissions effectives pour Raya (middleware)
```

- Super admin peut TOUT : modifier plafond ET niveau tenant, verrouiller globalement
- Tenant admin peut : modifier niveau appliqué jusqu'à son plafond, verrouiller son tenant
- Les 2 actions "verrouiller" ne touchent QUE `tenant_admin_permission_level`,
  jamais le plafond (sinon risque d'effondrement irréversible)

### ⚠️ Audit recommandé

Voir `docs/raya_permissions_audit_todo.md` pour checklist complète.

À faire à tête reposée avant d'ouvrir les permissions à d'autres tenants.
