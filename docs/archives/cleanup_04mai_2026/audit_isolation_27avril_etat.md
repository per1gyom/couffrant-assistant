---
date: 27 avril 2026 nuit
auteur: Claude (audit autonome) + Guillaume (validation à venir)
statut: AUDIT FAIT - corrections non appliquées
---

# Audit isolation multi-tenant — État au 27 avril 2026

## 🎯 Pourquoi ce document ?

Reprise de l'audit du 25 avril (`audit_isolation_25avril_complementaire.md`)
qui avait identifié **33 findings** (8 CRITIQUE + 15 IMPORTANT + 10 ATTENTION).

Plusieurs sessions de correction ont eu lieu depuis (étapes 0, A.1-A.5,
B.1, B.2). Mais la roadmap n'avait jamais été remise à jour de manière
exhaustive. Ce document fait le point **finding par finding** sur
l'état actuel en code.

**Méthode** : lecture seule (grep, view, requêtes SQL read-only).
Aucune correction appliquée ce soir.

---

## 📊 Bilan global au 27/04

| Gravité | Total | ✅ Corrigés | ⚠️ Partiels | ❌ Non corrigés |
|---|---|---|---|---|
| 🔴 CRITIQUE | 8 | 7 | 1 | 0 |
| 🟠 IMPORTANT | 8 (15 lignes) | 1 | 0 | 7 |
| 🟡 ATTENTION | 4 (10 lignes) | 0 | 1 | 3 |
| **TOTAL** | **20** | **8** | **2** | **10** |

**Progrès depuis le 25/04** : tous les CRITIQUES sont fixés (sauf 1
partiel avec mitigation log). Les 8 trous IMPORTANT identifiés ont en
revanche été peu traités : 1 sur 8.

**Bonne nouvelle complémentaire** : 2 trous DÉCOUVERTS APRÈS le 25/04
ont été corrigés en plus :

- A.5 part 1 (commit `58f53ce`) : `memory_rules.py` (38 occurrences `tenant_id`)
- A.5 part 2 (commit `57a9999`) : `aria_memory` + audit complet

---

## 🔴 CRITIQUES — Détail finding par finding

### Finding #1 — `token_manager.py:230 get_connected_providers()`

**État** : ✅ **CORRIGÉ** (commit `0f333da`, étape A.1, 26/04)

Filtre `AND tenant_id = %s` ajouté + `_resolve_tenant_strict` introduit
(retourne None si user inconnu, pas de fallback silencieux).

### Finding #2 — `token_manager.py` toutes les fonctions tokens

**État** : ✅ **CORRIGÉ** (commit `0f333da`, étape A.1, 26/04)

Toutes les fonctions touchées :

- `get_valid_microsoft_token` : default 'guillaume' retiré, filtre tenant
- `save_microsoft_token` : raise si user inconnu, ON CONFLICT élargi
- `get_valid_google_token` : idem
- `save_google_token` : idem
- `get_all_users_with_tokens` : volontairement cross-tenant + commentaire
  explicite pour les callers (à re-resolve tenant_id ligne par ligne)
- `get_connected_providers` : déjà fix dans #1

### Finding #3 — `POST /admin/tenants` accessible aux tenant_admin

**État** : ✅ **CORRIGÉ** (commit `2bdddb0`, étape A.3, 26/04)

`Depends(require_super_admin)` au lieu de `require_admin`.
Commentaire `# FIX 26/04 : etait require_admin` laissé en place.

### Finding #4 — `DELETE /admin/tenants/{id}` accessible aux tenant_admin

**État** : ✅ **CORRIGÉ** (commit `2bdddb0`, étape A.3, 26/04)

Idem #3.

### Finding #5 — `PUT /admin/update-user/{target}` promotion arbitraire

**État** : ✅ **CORRIGÉ** (commit `2bdddb0`, étape A.4, 26/04)

3 vecteurs d'escalation bloqués :

1. Validation enum scope contre `ALL_SCOPES`
2. Refus explicite `super_admin` (hardcoded uniquement)
3. `assert_same_tenant` si appelant n'est pas global admin

### Finding #6 — `DEFAULT_TENANT` silencieux dans `get_tenant_id`

**État** : ⚠️ **PARTIELLEMENT CORRIGÉ** (commit `2bdddb0`, étape A.2, 26/04)

Le fallback `DEFAULT_TENANT` est conservé (commentaire : "pour ne pas
casser les 21 callers existants"). Mitigation : log explicite WARNING
ou ERROR quand le fallback se déclenche.

**À faire pour vraiment fermer** : durcir progressivement les 21
callers pour qu'ils acceptent `None` proprement, puis retirer le
fallback. Effort estimé : 1-2 h.

### Finding #7 — Schema `users.tenant_id` NULLABLE

**État** : ✅ **CORRIGÉ** (commit `e937dca`, étape 0, 26/04)

`is_nullable = NO` confirmé en DB.

### Finding #8 — `users.scope` default = `'couffrant_solar'`

**État** : ✅ **CORRIGÉ** (commit `e937dca`, étape 0, 26/04)

`column_default = 'user'::text` confirmé en DB.

---

## 🟠 IMPORTANT — Détail finding par finding

### Finding #9 — `admin/profile.py` 6 requêtes sans tenant_id

**État** : ❌ **PAS CORRIGÉ**

Lignes 248, 254, 260, 267, 311, 427 : toutes filtrent juste sur
`username = %s` sans `AND tenant_id = %s`. La table `users` ligne 29
est OK (utilise `tenant_id` correctement) mais les stats user et les
oauth_tokens/llm_usage non.

**Risque actuel** : latent. Pas d'homonyme cross-tenant aujourd'hui.
**Risque futur** : actif dès le premier homonyme. Concerne /admin/profile
qui est un endpoint très utilisé.

**Effort fix** : ~20 min (mécanique : ajouter `tenant_id` aux 6 SQL).

### Finding #10 — `memory_teams.py` 2 requêtes sans tenant_id

**État** : ❌ **PAS CORRIGÉ**

Lignes 33, 85 : `WHERE username = %s` sans `tenant_id`.
La colonne `tenant_id` existe en DB (nullable, ajoutée en A.1).

**Risque** : faible (peu d'utilisateurs Teams).
**Effort fix** : ~10 min.

### Finding #11 — `synthesis_engine.py:171` UPDATE sans tenant_id

**État** : ❌ **PAS CORRIGÉ**

UPDATE `aria_hot_summary` filtré uniquement par `username`.

**Effort fix** : ~5 min.

### Finding #12 — `report_actions.py:22` daily_reports sans tenant_id

**État** : ❌ **PAS CORRIGÉ**

SELECT `daily_reports` filtré uniquement par `username`.
Colonne `tenant_id` existe en DB.

**Effort fix** : ~5 min.

### Finding #13 — `POST /admin/create-user` accepte tenant_id du payload

**État** : ✅ **CORRIGÉ** (commit `b1b9ac2`, étape B.1a-1, 26/04)

3 contrôles ajoutés :

1. Validation enum scope
2. Refus super_admin via API
3. Tenant_admin forcé sur son propre tenant

### Finding #14 — `POST /admin/drive/select` accepte tenant_id du payload

**État** : ❌ **PAS CORRIGÉ**

Toujours `payload.get("tenant_id")` sans contrôle d'autorisation.
Un tenant_admin (Charlotte si elle devient admin de juillet) pourrait
créer une connexion Drive sur un autre tenant.

**Effort fix** : ~10 min (forcer `admin["tenant_id"]` si non super_admin).

### Finding #15 — `POST /admin/sharepoint/select` accepte tenant_id du payload

**État** : ❌ **PAS CORRIGÉ**

Idem #14.

**Effort fix** : ~10 min (mêmes 5 lignes).

### Finding #16 — `connection_token_manager.py` JOIN implicite

**État** : ❌ **PAS CORRIGÉ**

5 fonctions reposent sur le JOIN avec `tenant_connections` sans filtrer
explicitement `tenant_id`. Le doc d'audit l'avait noté comme "moins
critique mais à durcir".

**Effort fix** : ~30 min (ajouter `tenant_id` à la signature et au WHERE
de 5 fonctions, propager aux callers).

---

## 🟡 ATTENTION — Détail finding par finding

### Finding #17 — `super_admin_users.py` 4 requêtes sans tenant_id

**État** : ❌ **PAS CORRIGÉ**

Lignes 249 (`aria_rules`), 275 (`aria_insights`), 705 et 744 (`aria_memory`).
Endpoints super-admin uniquement, donc risque très réduit.

**Effort fix** : ~15 min.

### Finding #18 — Bug logique `scope != "admin"` dans 4 endpoints

**État** : ❌ **PAS CORRIGÉ**

`super_admin.py` lignes 657, 670, 707, 721 : `if user["scope"] != "admin"`
sans gérer `super_admin`. Conséquence : Guillaume (super_admin) ne peut
pas suspendre/reset password des users d'autres tenants depuis ces
endpoints (cf. doc 25/04).

**Effort fix** : ~5 min (replacer par `not in ("admin", "super_admin")`).

### Finding #19 — Default `'guillaume'` dans `_build_email_html`

**État** : ❌ **PAS CORRIGÉ**

`outlook_calendar.py:32` toujours avec `username: str = "guillaume"`.

**Effort fix** : ~2 min (retirer le default, vérifier que tous les
appelants passent bien le username).

### Finding #20 — Magic strings `"admin"` au lieu de constantes

**État** : ⚠️ **PARTIELLEMENT CORRIGÉ**

6 magic strings restent :

- `super_admin.py` lignes 657, 670, 707, 721 (== finding #18)
- `rgpd.py:150`
- `hardcoded_permissions.py:92`

**Effort fix** : ~10 min (utiliser `SCOPE_ADMIN` partout).

---

## 📋 Résumé des corrections restantes

### Étape B (corrections IMPORTANT) — 7 trous restants

Estimation totale : **~1 h 30** de corrections mécaniques.

1. `admin/profile.py` : 6 requêtes (~20 min)
2. `memory_teams.py` : 2 requêtes (~10 min)
3. `synthesis_engine.py:171` : 1 UPDATE (~5 min)
4. `report_actions.py:22` : 1 SELECT (~5 min)
5. `POST /admin/drive/select` (~10 min)
6. `POST /admin/sharepoint/select` (~10 min)
7. `connection_token_manager.py` : 5 fonctions (~30 min)

### Étape C (défense en profondeur) — 4 lignes

Estimation : **~30 min**.

1. Bug logique `scope != "admin"` dans 4 endpoints (#18)
2. Default `'guillaume'` dans `_build_email_html` (#19)
3. Magic strings `"admin"` dans rgpd.py + hardcoded_permissions.py (#20)
4. Compléter étape #6 : durcir les 21 callers de `get_tenant_id` puis
   retirer le fallback `DEFAULT_TENANT` (~1 h pour celle-ci, séparée)

### Étape D (tests dynamiques) — pas commencée

**État au 27/04** : la revue de code (`tests_isolation_26avril.md`) a
été faite mais les **vrais tests dynamiques avec un user homonyme
cross-tenant** n'ont jamais eu lieu. Le user `pierre_test` du plan
n'a jamais été créé.

**À faire** :

1. Créer un user `pierre_test` dans `couffrant_solar` (homonyme du
   Pierre déjà existant).
2. Exécuter les 5 scénarios de fuite du `plan_tests_isolation_pierre_test.md`
3. Tester aussi avec Charlotte (`juillet`) puisqu'elle est déjà en DB.

**Effort estimé** : 1 h.

---

## 🎯 Recommandation

L'audit du 25/04 visait un onboarding sérieux **avant** d'accueillir de
nouveaux utilisateurs. Aujourd'hui (27/04), 2 tenants en prod,
0 homonyme. Tous les bugs IMPORTANT restants sont **latents** : ils ne
peuvent pas être exploités tant qu'il n'y a pas d'homonyme.

Mais dès qu'un Pierre arrive dans le tenant juillet (ou un Charlotte
dans couffrant_solar), tous ces trous deviennent actifs.

**Plan minimal recommandé avant le prochain onboarding** :

1. Étape B (1 h 30) — fixer les 7 trous IMPORTANT restants
2. Étape D (1 h) — exécuter les vrais tests pierre_test
3. Étape C (30 min) — défense en profondeur

**Total** : ~3 h pour fermer le chantier.

---

## ✅ Architecture saine confirmée

Au-delà des findings, l'audit du 25/04 a confirmé que **l'architecture
d'auth est très propre** :

- `username` et `tenant_id` viennent toujours de la session, jamais du
  client (sauf endpoints super-admin légitimes).
- Override hardcoded super-admin via `get_effective_scope` : impossible
  de rétrograder Guillaume.
- `assert_same_tenant` empêche les tenant_admin cross-tenant.
- 30 fichiers du précédent audit du 24/04 toujours bien isolés
  (median 17 occurrences `tenant_id`).
- Aucune ligne en DB avec `tenant_id IS NULL`.
- Aucune incohérence cross-tenant détectée sur les jointures.

---

## 📅 Historique des commits liés

| Date | Commit | Étape | Quoi |
|---|---|---|---|
| 26/04 | `8196001` | Hotfix | Pool DB |
| 26/04 | `e937dca` | 0 | 6 migrations DB (max_users, NOT NULL, default scope) |
| 26/04 | `0f333da` | A.1 | Tokens OAuth (token_manager.py) |
| 26/04 | `2bdddb0` | A.2/A.3/A.4 | Logs DEFAULT_TENANT + super_admin endpoints + update_user |
| 26/04 | `58f53ce` | A.5.1 | memory_rules.py |
| 26/04 | `57a9999` | A.5.2 | aria_memory + audit |
| 26/04 | `b1b9ac2` | B.1a-1 | Soft-delete + create-user durci |
| 26/04 | `fcfc933` | B.1a-2 | Workflow purge |
| 26/04 | `8508df9` | B.1b | Seat counter + endpoints quota |
| 26/04 | `e316f9a` | B.2-2 | Durcissement /tenant + force-purge |
| 26/04 | `70e6825` | B.2-3 | UI onglet Équipe |
| 27/04 | `02019e1` | 0-suite | Normalisation `couffrant_solar` |

