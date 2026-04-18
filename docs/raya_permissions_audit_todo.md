# 🔍 Audit permissions v1 — à refaire tête reposée

**Créé le 19/04/2026 à 3h du matin après session marathon de ~20h.**

## Contexte

Session intense avec Guillaume où on a livré les permissions v1 (7 étapes)
puis enchaîné **15+ patchs** sur l'UX/UI en quelques heures. Guillaume a
lui-même suggéré de noter cette partie comme "à auditer" car à force de
correctifs successifs on n'a peut-être pas fait quelque chose de propre
de bout en bout.

## Objectif de l'audit

Relire à tête reposée l'ensemble de la chaîne des permissions pour
vérifier la cohérence, l'absence de régressions, et la propreté du code.

## Chaîne complète à auditer

### 1. Backend — `app/permissions.py`

- [ ] `check_permission(tenant_id, tool_type, action)` : fallback et mapping OK ?
- [ ] `update_permission(tenant_id, connection_id, new_level, actor_role)`
  - [ ] actor_role='super_admin' : écrit bien super_admin_permission_level ?
  - [ ] actor_role='tenant_admin' : cappe bien au plafond super ?
  - [ ] Cas limite : qu'est-ce qui se passe si new_level > plafond super ?
- [ ] `toggle_all_read_only(tenant_id, actor_role)`
  - [ ] Ne touche PAS à super_admin_permission_level (bug fixé mais à revérifier)
  - [ ] previous_permission_level bien restauré ?
  - [ ] Cas tenant_id=None (tous les tenants) fonctionne ?
- [ ] `get_tenant_lock_status(tenant_id)` : logique cohérente avec loadPermissions frontend ?

### 2. Backend — Endpoints

**Fichier `app/routes/admin/tenant_admin.py`** :
- [ ] `GET /tenant/permissions` → retourne correctement label AS name ?
- [ ] `POST /tenant/permissions/update` → valide bien les inputs ?
- [ ] `POST /tenant/permissions/toggle-read-only` → appelle toggle avec actor_role='tenant_admin' ?
- [ ] `GET /tenant/permissions/lock-status` → ok ?

**Fichier `app/routes/admin/super_admin.py`** :
- [ ] `GET /admin/tenant/{id}/permissions` → retourne les bonnes données ?
- [ ] `POST /admin/tenant/{id}/permissions/update` → accepte bien scope_type ?
- [ ] `POST /admin/tenant/{id}/toggle-read-only` → actor_role='super_admin' ?
- [ ] `GET /admin/tenant/{id}/lock-status` → ok ?
- [ ] `POST /admin/permissions/toggle-read-only-global` : est-ce qu'on le garde ou on le supprime ?

### 3. Frontend — `app/templates/tenant_panel.html`

- [ ] `loadPermissions()` : détection `isAllLocked` cohérente avec backend ?
- [ ] `_lastPermissionsState` : bien mise à jour en temps réel ?
- [ ] `toggleReadOnly()` : le repaint forcé fonctionne sur tous les navigateurs ?
- [ ] `updatePermission()` : le recall est bien fait avec un setTimeout ?
- [ ] Les radios sont-ils bien grisés quand `isAllLocked=true` ?
- [ ] Le bandeau rouge est-il bien affiché au bon moment ?

### 4. Frontend — `app/static/admin-panel.js`

- [ ] `loadPermissionsForTenant()` : idem tenant_panel ?
- [ ] `updatePermissionCap()` : gère bien scope_type (super_admin vs tenant_admin) ?
- [ ] `toggleReadOnlyForTenant()` : repaint forcé, cache-bust ?
- [ ] `_tenantLockState` : bien invalidé après chaque action ?
- [ ] `updateLockButtonState()` : met bien à jour le bouton ET le cache ?

### 5. Middleware — `app/routes/actions/odoo_actions.py` et `mail_actions.py`

- [ ] `_check_perm()` intercepte bien toutes les actions ODOO_CREATE/UPDATE/NOTE ?
- [ ] SEND_MAIL dans `_queue_send_mail` bien intercepté ?
- [ ] En cas de permission refusée, le message d'erreur est-il clair ?

### 6. Injection prompt — `app/routes/aria_context.py`

- [ ] `_build_permissions_block()` : injecte bien dans le prompt système ?
- [ ] Format lisible pour Raya ?
- [ ] Respect des permissions observé dans les tests réels ?

## Problèmes spécifiques à retester

1. **Cycle verrouiller → restaurer** : le plafond super_admin ne bouge
   vraiment jamais ? (Bug historique fixé par commit 79f39ca)

2. **Radios grisés quand locked** : tous les radios disabled + styles
   cohérents dans tenant_panel ET super admin panel ?

3. **Cohérence visuelle modal vs bouton** : après le fix repaint
   (commit e9d6abb), plus jamais d'incohérence entre l'état affiché
   sur le bouton et celui indiqué dans le prompt modal ?

4. **Cache navigateur** : le cache-bust `?_=Date.now()` + no-store
   suffit-il vraiment ? Faut-il aussi ajouter des headers
   Cache-Control côté serveur ?

5. **Modification en parallèle** : si 2 onglets modifient les permissions
   en même temps, que se passe-t-il ?

## Commits sur lesquels revenir

Tous les commits de la nuit du 18/04 au 19/04 (session marathon) :

- `70174c6` feat : étapes 1+2 (DB + module permissions.py)
- `a949c16` feat : étape 3 (middleware interception)
- `67f5daf` feat : étape 4 (UI tenant_panel)
- `9c277c6` feat : étape 5 (UI super admin + bouton global)
- `186b79e` feat : étape 6 (injection prompt Raya)
- `b15bc50` feat : étape 7 (tests unitaires + doc)
- `dc96ecc` fix : bouton par tenant + confirmation 'oui' + fix label vs name
- `88572ea` feat : Fix 1+2+3 plafonds réels + feedback visuel + UI complete super admin
- `8d2d37b` fix : cadenas correct (🔒/🔓) + textes
- `79f39ca` fix : toggle_all_read_only ne touche PAS super_admin
- `b7c0d87` fix : radios grisés quand verrouillé
- `e0f18cf` fix : source unique de vérité pour état verrouillage
- `b8bce20` fix : toggle toujours relire l'état avant (plus de cache obsolète)
- `2fcaffb` fix : cache-bust sur tous les fetchs
- `e9d6abb` fix : force repaint avant prompt() (cause racine visuelle)

## Propositions d'amélioration

1. **Remplacer `prompt()` par un vrai modal HTML non-bloquant**
   - Évite les soucis de repaint
   - Plus joli visuellement
   - Permet une UX plus riche (icônes, couleurs, etc.)

2. **Fix 4 de la roadmap : unifier UIs tenant_panel et super admin**
   - Actuellement 2 UIs différentes pour le même concept
   - Factoriser en un seul composant

3. **Ajouter des tests automatisés**
   - Tests e2e Playwright sur le toggle verrouiller/restaurer
   - Vérifier la cohérence bouton + bandeau + radios + modal

4. **Headers Cache-Control côté serveur**
   - Pour les endpoints /tenant/permissions* et /admin/permissions*
   - `Cache-Control: no-store, no-cache, must-revalidate`
   - Plus robuste que le cache-bust côté client seul

## Quand faire l'audit

Dans une session dédiée, tête reposée, après avoir bien dormi.
Prévoir **2-3h** pour faire le tour proprement.
Idéalement avant d'ouvrir les permissions à d'autres tenants (Juillet,
futurs clients) pour éviter qu'un bug n'impacte plusieurs utilisateurs.
