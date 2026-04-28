# Audit isolation user↔user intra-tenant — Phase 2 (Audit code) + Plan d'action

> **Date** : 28 avril 2026 fin de soirée
> **Auteur** : session Guillaume + Claude
> **Statut** : Phase 2 (Audit code) terminée. Plan d'action proposé pour Phase 3.

## Résumé exécutif

✅ **L'isolation user↔user est globalement BONNE.** La majorité du code
filtre correctement par `username` et `tenant_id`. Le travail multi-tenant
fait par les LOTs 2-6 du 28/04 matin a porté ses fruits.

🚨 **10 findings identifiés** dont :
- **0 CRITIQUE bloquant** (aucune fuite user↔user prouvée en pratique)
- **5 IMPORTANT** (défauts de défense à corriger pour solidité)
- **5 ATTENTION** (anti-patterns ou cohérence à améliorer)

🛡️ **La base actuelle est suffisamment robuste pour démarrer la version
d'essai après les fixes du Plan d'action ci-dessous (~3-4h de boulot).**

## Méthodologie Phase 2

1. Grep automatique sur les 38 tables Cat A pour trouver les SQL execute
   qui ne contiennent pas le mot `username` → 104 findings bruts
2. Audit manuel de chaque finding pour distinguer :
   - Vrais trous (pas de filtre user du tout)
   - Faux positifs (filtre via `id` PK ou `connection_id` qui est suffisamment unique)
   - Cas spéciaux (jobs batch volontairement globaux, super_admin only)
3. Documentation des 10 findings réels.

## Findings détaillés

### 🚨 Findings IMPORTANT (5)

#### F.5 — `embedding.search_similar` : filtre `username` conditionnel

**Fichier** : `app/embedding.py:101`

**Code actuel** :
```python
if username:
    filters.append("username = %s")
    params.append(username)
```

**Problème** : si un caller passe `username=None` ou `username=""`,
**aucun filtre user n'est appliqué**. La requête retourne TOUTES les rows
de la table (aria_rules, mail_memory, aria_memory, etc.) tous users
confondus.

**Impact réel aujourd'hui** : faible. Les 3 callers (rag.py,
narrative.py, rule_validator.py) passent tous explicitement
`username=username`. Mais c'est un piège défensif : si quelqu'un ajoute
un nouveau caller sans username, fuite massive silencieuse.

**Fix proposé** (LOT 1) : transformer en `if not username: raise
ValueError("username obligatoire")`. Forçage à la racine.

#### F.6 — `_save_conversation` : INSERT sans `tenant_id`

**Fichier** : `app/routes/raya_agent_core.py:884-887`

**Code actuel** :
```python
c.execute(
    "INSERT INTO aria_memory (username, user_input, aria_response) "
    "VALUES (%s, %s, %s) RETURNING id",
    (username, user_input, aria_response),
)
```

**Problème** : tenant_id n'est pas inséré. Les nouvelles conversations
ont `tenant_id IS NULL` jusqu'au prochain redéploiement (où la migration
backfill `UPDATE aria_memory a SET tenant_id = u.tenant_id FROM users u
WHERE a.username = u.username AND a.tenant_id IS NULL`).

**Impact réel aujourd'hui** : pas de fuite user↔user (filtre `username`
partout en lecture). Mais entre 2 redéploiements, des conversations
toutes fraîches avec `tenant_id IS NULL` peuvent être lues
cross-tenant pour un user homonyme (si un user "guillaume" existe dans 2
tenants — improbable car `users.username UNIQUE`).

**Fix proposé** (LOT 1) : ajouter `tenant_id` au VALUES + propager le
paramètre dans la signature de `_save_conversation`.

#### F.7 — `raya_helpers` : INSERT sans `tenant_id`

**Fichier** : `app/routes/raya_helpers.py:211-213`

**Code actuel** :
```python
c.execute(
    "INSERT INTO aria_memory (username, user_input, aria_response) VALUES (%s, %s, %s) RETURNING id",
    (username, payload.query, clean_response)
)
```

**Problème** : identique à F.6.

**Fix proposé** (LOT 1) : identique. Ajouter `tenant_id`.

#### F.8 — `memory_synthesis` : default `username='guillaume'`

**Fichier** : `app/memory_synthesis.py:30, 45`

**Code actuel** :
```python
def get_hot_summary(username: str = 'guillaume', tenant_id: str = None) -> str:
def get_aria_insights(limit: int = 8, username: str = 'guillaume', tenant_id: str = None) -> str:
```

**Problème** : si un caller appelle ces fonctions **sans username**,
elles retournent par défaut les données de Guillaume. Anti-pattern
multi-user dangereux.

**Impact réel aujourd'hui** : faible (les callers connus passent tous
explicitement `username`). Mais piège pour le futur.

**Fix proposé** (LOT 1) : retirer le default, rendre `username`
obligatoire.

#### F.9 — `token_manager` : fallback `gmail_tokens` sans tenant_id

**Fichier** : `app/token_manager.py:175`

**Code actuel** :
```python
c.execute("SELECT access_token, refresh_token FROM gmail_tokens WHERE username = %s LIMIT 1", (username,))
```

**Problème** : code de fallback legacy (lecture depuis ancienne table
`gmail_tokens` quand pas de match dans `oauth_tokens` nouveau format).
Pas de filtre `tenant_id`.

**Impact réel aujourd'hui** : très faible. `users.username` est UNIQUE
globalement donc un username donné est toujours dans le même tenant.

**Fix proposé** (LOT 1) : ajouter `AND tenant_id = %s` ou retirer
carrément le fallback legacy si plus utilisé.

### 🟡 Findings ATTENTION (5)

#### F.1 — `get_aria_rules` : branche `else` sans tenant_id

**Fichier** : `app/memory_rules.py:56-83`

Déjà documenté avec WARNING dans le code. Quand `tenant_id` est None,
filtre seulement par `username`. Risque tenant↔tenant en cas
d'homonyme (impossible aujourd'hui car `users.username` UNIQUE).

**Action** : retirer la branche `else` à terme. Actuellement les
warnings n'ont jamais déclenché en logs (à confirmer Phase 3).

#### F.2 — `feedback.py` : UPDATE final sans tenant_id

**Fichier** : `app/feedback.py:291-296`

```python
UPDATE aria_response_metadata
SET feedback_type = 'negative', feedback_comment = %s, corrective_rule_id = %s
WHERE aria_memory_id = %s AND username = %s
```

Manque `(tenant_id = %s OR tenant_id IS NULL)`. Mais protégé par
`aria_memory_id` (PK globalement unique) + `username`. Pas de fuite
possible en pratique.

**Action** : ajouter `tenant_id` pour cohérence stylistique avec le
reste du fichier.

#### F.4 — `feedback.py:163` : même pattern

Idem F.2 dans `process_positive_feedback`. Même verdict.

**Action** : même fix.

#### F.10 — `admin_rules.py` : UPDATE sans username_filter

**Fichier** : `app/routes/admin_rules.py:79-90`

Si le caller ne passe pas `username_filter`, l'UPDATE s'applique aux
rules de TOUS les users matchant `id IN (rule_ids)`. Mais l'endpoint
est `require_super_admin`, donc c'est intentionnel pour les migrations
en masse.

**Action** : aucun fix obligatoire. Documenter clairement dans le
docstring de la fonction que c'est un outil super_admin global.

#### F.X — Default `username='guillaume'` dans plusieurs fonctions

Pattern récurrent dans plusieurs fichiers : `username: str = 'guillaume'`
en valeur par défaut. Exemples :
- `app/memory_synthesis.py` (déjà couvert F.8)
- `app/memory_rules.py:seed_default_rules`
- Probablement d'autres

**Action** (à faire en parallèle des fixes F.1-F.10) : grep tous les
`username.*=.*['\"]guillaume['\"]` dans `app/`, retirer le default
partout.

## Findings Phase 1 (rappel — contraintes UNIQUE)

Pour mémoire, les 6 findings sur les contraintes UNIQUE déjà documentés
dans `audit_isolation_user_user_phase1.md` :

- **U.1 CRITIQUE** : `users.username UNIQUE` (décision design à valider)
- **U.2 CRITIQUE** : `aria_onboarding.username UNIQUE` (idem)
- **U.3 IMPORTANT** : `mail_memory` UNIQUE manque tenant_id
- **U.4 IMPORTANT** : `sent_mail_memory` idem
- **U.5 IMPORTANT** : `email_signatures` idem
- **U.6 IMPORTANT** : `teams_sync_state` idem

## Tables auditées en pratique

| Table | Statut |
|---|---|
| `aria_rules` | ✅ Très bien (memory_rules.py + rag.py + user_rules.py + jobs filtrent partout) |
| `aria_memory` | ⚠️ INSERT sans tenant_id (F.6, F.7) — protégé en lecture |
| `aria_response_metadata` | ⚠️ 2 UPDATE sans tenant_id (F.2, F.4) — protégé par aria_memory_id |
| `mail_memory` | ✅ proactivity_scan + jobs filtrent correctement |
| `oauth_tokens` | ✅ token_manager filtre proprement avec _resolve_tenant_strict |
| `gmail_tokens` (legacy) | ⚠️ fallback sans tenant_id (F.9) |
| `aria_hot_summary` | ✅ memory_synthesis filtre par username + tenant_id |
| `aria_insights` | ✅ memory_synthesis filtre |
| `aria_profile` | ✅ profile.py filtre |
| `email_signatures` | ✅ signatures.py filtre |
| `pending_actions` | ✅ pending_actions.py filtre |
| `webhook_subscriptions` | ✅ microsoft_webhook filtre |
| `connection_assignments` | ✅ connections.py filtre par connection_id (suffisant) |
| `proactive_alerts` | ✅ proactive_alerts.py filtre |
| Jobs batch (confidence_decay, rules_optimizer, etc.) | ✅ globaux par design, pas de mélange entre users |

## Plan d'action — 4 LOTs

### LOT 1 — Fixes structurels critiques (~1h30)

> **Objectif** : forcer la défense en profondeur, supprimer les pièges
> qui pourraient causer des fuites futures même si pas de fuite
> aujourd'hui.

| ID | Fichier | Action | Effort |
|---|---|---|---|
| L1.1 | `app/embedding.py:101` | F.5 — `if not username: raise ValueError`. Retire le `if username:` conditionnel. | 5 min |
| L1.2 | `app/routes/raya_agent_core.py:880,886` | F.6 — Ajouter `tenant_id` au signature de `_save_conversation` + au INSERT. Propager depuis l'appel ligne 699. | 10 min |
| L1.3 | `app/routes/raya_helpers.py:211` | F.7 — Ajouter `tenant_id` au INSERT. Propager depuis le handler. | 10 min |
| L1.4 | `app/memory_synthesis.py:30,45` | F.8 — Retirer `username='guillaume'` default. Lever `ValueError` si username manquant. | 5 min |
| L1.5 | `app/token_manager.py:175` | F.9 — Soit ajouter filtre tenant_id, soit retirer carrément le fallback legacy si plus utilisé (vérifier en DB que `gmail_tokens` est vide). | 15 min |
| L1.6 | Plusieurs fichiers | F.X — Grep tous les `username.*=.*'guillaume'` en valeur par défaut. Retirer partout. | 20 min |
| L1.7 | `app/feedback.py:163,291` | F.2, F.4 — Ajouter `tenant_id` aux 2 UPDATE pour cohérence. | 5 min |
| L1.8 | `app/memory_rules.py:51-83` | F.1 — Retirer la branche `else` sans tenant_id (rendre tenant_id obligatoire). Vérifier que tous les callers passent bien tenant_id avant. | 20 min |

**Tests après LOT 1** : lancer en local, faire 5 conversations user
guillaume, vérifier que rien ne casse + DB cohérente.

**Commit** : 1 commit englobant `fix(isolation): durcir filtre user-user
en lecture/écriture (LOT 1 audit user-user)`.

### LOT 2 — Migrations DB cohérence UNIQUE (~45 min)

> **Objectif** : passer toutes les contraintes UNIQUE multi-tenant safe.

| ID | Migration | Effort |
|---|---|---|
| L2.1 | `mail_memory` : DROP CONSTRAINT msg_user_unique, ADD UNIQUE(message_id, username, tenant_id) | 10 min |
| L2.2 | `sent_mail_memory` : idem | 10 min |
| L2.3 | `email_signatures` : DROP username_email_address_key, ADD UNIQUE(username, email_address, tenant_id) | 10 min |
| L2.4 | `teams_sync_state` : DROP username_chat_id_key, ADD UNIQUE(username, chat_id, tenant_id) | 10 min |
| L2.5 | Vérifier en DB que les nouvelles UNIQUE n'introduisent pas de conflits avec les rows existants (count duplicatas potentiels avant migration) | 5 min |

**Migrations dans** : `app/database_migrations.py` avec patterns M-U01
à M-U05 et flags exécution unique.

**U.1 et U.2** (`users.username` et `aria_onboarding.username`) : **PAS
TRAITÉS dans ce LOT**. Décision design à prendre avec Guillaume avant de
toucher à ces contraintes (cf. LOT 4 ci-dessous).

**Commit** : `migration(isolation): contraintes UNIQUE multi-tenant safe
(LOT 2 audit user-user)`.

### LOT 3 — Tests bout-en-bout pierre_test (~1h)

> **Objectif** : valider EN PRATIQUE que l'isolation user↔user fonctionne
> avec un 2e user fictif dans le même tenant.

Plan déjà rédigé dans `docs/plan_tests_isolation_pierre_test.md`. Mais
je vais l'adapter au contexte actuel :

#### L3.1 — Setup
1. Créer `pierre_test` en DB :
   ```sql
   INSERT INTO users (username, password_hash, tenant_id, scope)
   VALUES ('pierre_test', <hash>, 'couffrant_solar', 'tenant_user')
   ```
2. Créer 1 conversation pour `pierre_test` (via API ou directement DB)
3. Créer 1 règle pour `pierre_test` (catégorie test, rule différente de
   celles de Guillaume)

#### L3.2 — Tests d'isolation
| Test | Vérification | Outil |
|---|---|---|
| T1 | Pierre login → ne voit PAS les conversations de Guillaume | Browser ou API curl |
| T2 | Pierre tape "rappelle-moi mes règles" → liste UNIQUEMENT ses règles | API |
| T3 | Pierre clique 👍 → renforce SES règles, pas celles de Guillaume | Vérif DB confidence aria_rules |
| T4 | Pierre cherche un mail → 0 résultat (pas de mail dans sa boîte) | API mail search |
| T5 | Guillaume login → ne voit PAS la conversation/règle de Pierre | Cross-check |

#### L3.3 — Tests de sécurité
| Test | Vérification |
|---|---|
| T6 | Pierre essaie GET `/admin/panel` → 403 Forbidden (scope tenant_user) |
| T7 | Pierre essaie API `/aria_rules?username=guillaume` → soit 403, soit retourne ses propres règles (jamais celles de Guillaume) |
| T8 | Vérification de TOUS les endpoints admin auxquels un tenant_user pourrait essayer d'accéder |

#### L3.4 — Cleanup
Soft-delete `pierre_test` après les tests pour ne pas polluer la DB
prod.

**Commit** : `test(isolation): validation bout-en-bout pierre_test (LOT 3
audit user-user)` avec les findings éventuels.

### LOT 4 — Décisions design à valider avec Guillaume

> **Objectif** : trancher 2 questions architecturales avant de
> potentiellement toucher au schéma users.

#### L4.1 — `users.username UNIQUE` : conserver ou migrer ?

**Question** : un même nom d'utilisateur peut-il exister dans 2 tenants
différents ?

- **Option A — Conserver UNIQUE(username) global** :
  - ✅ Simple, pas de risque de confusion d'identité
  - ✅ Évite les bugs où un user pourrait être ambigu
  - ❌ Si Charlotte (juillet) et une autre Charlotte (autre tenant client)
    voulaient cohabiter, conflit. Solution : préfixer dans l'UI
    (`charlotte_juillet`).
  - ✅ Statu quo, aucun changement nécessaire.

- **Option B — Migrer vers UNIQUE(username, tenant_id)** :
  - ✅ Permet vraiment 1 username par tenant
  - ❌ Migration risquée (FK vers `users.username` partout dans le code)
  - ❌ Complique la gestion d'identité (besoin de `(username, tenant_id)`
    en clé partout)
  - ❌ Risque de bugs subtils

**Recommandation Claude** : Option A (statu quo). Le coût de la migration
ne se justifie pas tant que le produit est en early stage. À reconsidérer
quand on aura 50+ tenants en prod.

**Décision Guillaume** : ⏳ À trancher.

#### L4.2 — `aria_onboarding.username UNIQUE` : conserver ou composite ?

**Question** : si on garde Option A pour `users`, doit-on garder cette
contrainte aussi (un seul état d'onboarding par user) ?

**Recommandation Claude** : oui, garder. Cohérent avec L4.1 Option A.

#### L4.3 — Branches `else` sans tenant_id à retirer ?

Plusieurs fonctions ont une branche legacy sans `tenant_id` (cf. F.1 dans
`get_aria_rules`). Ces branches émettent un WARNING en log.

**Question** : retirer définitivement ces branches (force la propagation
de tenant_id partout) ou les garder ?

**Recommandation Claude** : retirer. Ça force les callers à passer
tenant_id correctement. Vérifier d'abord les logs récents pour
confirmer qu'aucun WARNING n'a été émis depuis le 27/04 (pas de caller
oublié).

**Décision Guillaume** : ⏳ À trancher.

## Bilan final + estimation totale

| Phase | Effort | Statut |
|---|---|---|
| Phase 1 — Cartographie | 1h | ✅ Terminée 28/04 soir |
| Phase 2 — Audit code | 2h | ✅ Terminée 28/04 soir (ce doc) |
| LOT 1 — Fixes structurels | ~1h30 | 🔴 À faire |
| LOT 2 — Migrations UNIQUE | ~45 min | 🔴 À faire |
| LOT 3 — Tests pierre_test | ~1h | 🔴 À faire |
| LOT 4 — Décisions design | ~30 min de discussion | 🔴 À faire (avec Guillaume) |

**Total restant : ~3h30 de dev + 30 min de discussion + commit/push.**

**Faisable en une session de 4h** dans les jours qui viennent.

## Risques résiduels après LOT 1-3

🟢 **Faible** :
- Bug théorique cross-tenant via INSERT sans tenant_id entre 2
  redéploiements : éliminé après LOT 1
- Race condition `aria_profile`/`aria_hot_summary` (insertion 2x pour le
  même user sans UNIQUE) : très peu probable, à corriger plus tard avec
  des UNIQUE supplémentaires

🟡 **Moyen** :
- Si quelqu'un crée un nouveau caller dans `embedding.search_similar`
  sans username : éliminé après LOT 1.1 (raise ValueError)
- Si un tenant_admin essaie d'accéder aux données d'un autre tenant via
  un endpoint mal isolé : à valider en LOT 3 (tests)

🔴 **À surveiller** :
- Décision L4.1 (users.username UNIQUE) sera importante quand on aura
  un 2e tenant client. À ré-aborder dans 2-3 mois.

## Conclusion

✅ **L'isolation user↔user est prête à 80%.** Les 20% restants sont :
- Durcissement défensif (LOT 1 — éviter les pièges futurs)
- Migrations cohérence (LOT 2 — DB plus robuste)
- Validation pratique (LOT 3 — tests)
- Décisions design (LOT 4 — trancher avec Guillaume)

🚀 **Après ces 4 LOTs (~4h), Raya sera prête à accueillir Pierre,
Sabrina, Benoît dans `couffrant_solar`** sans risque connu d'isolation.

**Pré-requis indépendant** (cf. `a_faire.md` section CHANTIERS URGENTS) :
plan résilience (2h15) + retrait Administration menu user (2-3h).

**Total avant déploiement version d'essai** : ~9-10h sur 2-3 sessions
dédiées dans les jours qui viennent.

## Prochaine session recommandée

1. LOT 1 + LOT 2 (~2h15) : fixes code + migrations UNIQUE → 1 session
   d'après-midi
2. LOT 3 (~1h) : tests pierre_test → en complément
3. LOT 4 (~30 min discussion) : intercalé avec le reste

Démarrage idéal : demain en fin de matinée à frais.
