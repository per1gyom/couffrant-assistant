# 🧪 Tests d'isolation multi-tenant — 26 avril 2026

**Date** : 26 avril 2026, après-midi **Auteur** : Claude (revue de code) + Guillaume (validation) **Format** : Revue de code par scénarios + requêtes SQL en lecture seule **Pourquoi ce document** : valider en réel que les fixes des étapes 0+A sont bien en place et fonctionnent. Document durable, ré-exécutable visuellement à chaque session future.

---

## 📋 Contexte

### Ce qui a été déployé aujourd'hui (8 commits)

- `8196001` — Hotfix pool DB (proactivity_scan + garde-fou \_PooledConn)
- `e937dca` — Étape 0 : 6 migrations DB (quota max_users, tenant_id NOT NULL, fix default scope)
- `2bdddb0` — A.2 + A.3 + A.4 : durcissement endpoints admin
- `0f333da` — A.1 : isolation tokens OAuth
- `ddee2f8` — Doc roadmap
- `1bb333e` — `.prettierignore`
- `a6b33f8` — Fix graph_indexer + désactivation mail.activity
- `d791168` — Doc Priorité 8 (Odoo en attente OpenFire)

### Architecture validée

- **Modèle SaaS multi-tenant** : un username peut exister dans plusieurs tenants (option B)
- **Isolation par** `(tenant_id, username)` au niveau DB
- **Quotas par tenant** : couffrant_solar=5, juillet=1
- **2 tenants en prod** : couffrant_solar (5 users), juillet (1 user — Charlotte)

### Méthode des tests

- **Aucune modification** (code, DB, config)
- **Lecture seule** : SQL `SELECT`, lecture de code, grep
- **Si trou trouvé** → STOP immédiat, on documente, on décide ensemble

---

## 🎯 Liste des 9 scénarios

#CatScénarioStatut1.1AuthCharlotte ne voit pas les `aria_rules` de Guillaume⏳1.2AuthCharlotte ne voit pas les `aria_memory` de Guillaume⏳1.3AuthCharlotte ne voit pas les `mail_memory` de Guillaume⏳2.1Admin`POST/DELETE /admin/tenants` exige `require_super_admin`⏳2.2Admin`PUT /admin/update-user` bloque les 3 vecteurs d'escalation⏳3.1Tokens`get_valid_microsoft_token('inconnu')` retourne None⏳3.2Tokens`get_connected_providers` filtre bien `tenant_id`⏳4.1DB0 ligne `tenant_id IS NULL` dans les nouvelles données⏳4.2PoolGarde-fou rollback `_PooledConn.close()` + 0 zombie⏳

Légende : ⏳ à faire, ✅ OK, ⚠️ attention, ❌ trou

---

## Scénario 1.1 — `aria_rules` : Charlotte vs Guillaume

**Statut** : ⚠️ ATTENTION (trou latent identifié, à fixer en A.5)

### Test DB (lecture seule)

```sql
SELECT tenant_id, username, count(*) AS nb_regles
FROM aria_rules GROUP BY tenant_id, username;
```

tenant_idusernamenb_reglescouffrant_solarguillaume203 (162 actives)juilletCharlotte10 (10 actives)

→ ✅ Données bien isolées en DB. Aucune ligne mélangée.

### Revue de code — `app/memory_rules.py`

3 fonctions avec **anti-pattern multi-tenant** identique à celui qu'on a fixé sur `token_manager.py` ce matin :

```python
def get_aria_rules(username: str = 'guillaume', tenant_id: str = None) -> str:
def delete_rule(rule_id: int, username: str = 'guillaume', ...):
def seed_default_rules(username: str = 'guillaume'):
```

**Problèmes combinés** :

1. Default `username='guillaume'` (anti-pattern multi-tenant)
2. `tenant_id=None` déclenche un fallback non-isolé dans la requête SQL :

```python
if tenant_id:
    c.execute("... AND (tenant_id = %s OR tenant_id IS NULL) ...")
else:
    c.execute("... WHERE username = %s ...")  # ← PAS de filtre tenant
```

### Risque concret

Si un caller appelle `get_aria_rules(username='Charlotte')` sans `tenant_id`, on tombe dans le `else` qui ne filtre pas par tenant. Si demain un homonyme `Charlotte` existait dans `couffrant_solar`, les règles des deux tenants seraient mélangées.

**Aujourd'hui** : pas d'homonyme en DB → trou **latent**, pas actif. **Demain** : dès qu'un homonyme apparaît → fuite immédiate.

### À fixer en Étape A.5

- Retirer le default `username='guillaume'` des 3 fonctions
- Forcer la résolution `tenant_id` (raise si non fourni, ou résoudre depuis username via `_resolve_tenant_strict` comme dans token_manager)
- Supprimer la branche `else` non-isolée

---

## Scénario 1.2 — `aria_memory` : Charlotte vs Guillaume

**Statut** : ⚠️ ATTENTION (1 trou trouvé, à fixer en A.5)

### Test DB (lecture seule)

tenant_idusernamenb_conversationscouffrant_solarguillaume200juilletCharlotte9

→ ✅ Données isolées en DB.

### Revue de code — fichiers visités

Échantillon de fichiers vérifiés en lecture, **OK** (filtre `tenant_id`bien présent) :

- `app/feedback.py:186` ✅
- `app/memory_synthesis.py:78, 85` ✅
- `app/routes/raya_agent_core.py:208` ✅
- `app/jobs/pattern_analysis.py:60` ✅

### ❌ Trou trouvé — `app/routes/admin/super_admin_users.py:440`

Fonction `admin_debug_last_memories(target: str)` :

```python
@router.get("/admin/.../debug-memories/{target}")
def admin_debug_last_memories(
    request: Request,
    target: str,
    limit: int = 10,
    _: dict = Depends(require_admin),  # accepte tenant_admin !
):
    c.execute("""
        SELECT id, user_input, aria_response, archived, created_at, ...
        FROM aria_memory
        WHERE username = %s         # ← PAS de filtre tenant_id !
        ORDER BY id DESC LIMIT %s
    """, (target, ...))
```

**Risque concret** : Charlotte (tenant_admin de juillet) peut appeler cet endpoint avec `target='guillaume'` ou n'importe quel user de `couffrant_solar` et récupérer leurs conversations. **Fuite directe cross-tenant**.

**Conditions** : Charlotte doit connaître ou deviner les usernames cross-tenant. Mais c'est facile (logique : les noms sont souvent les mêmes — Pierre, Marie, Sabrina, etc.).

### À fixer en Étape A.5

- Ajouter `assert_same_tenant(request, target)` si caller != super_admin
- OU : ajouter `AND (tenant_id = %s OR tenant_id IS NULL)` dans la requête
- Préférer le pattern combiné : assert_same_tenant + filtre tenant_id en défense en profondeur

---

## Scénario 1.3 — `mail_memory` : Charlotte vs Guillaume

**Statut** : ✅ OK

### Test DB

tenant_idusernamenb_mailscouffrant_solarguillaume946

→ Charlotte n'a aucun mail (Outlook/Gmail pas connectés sur juillet). Test négatif satisfait par défaut.

### Revue de code — échantillon de 5 fichiers

Tous filtrent `tenant_id` correctement :

- `app/entity_graph.py:703` ✅
- `app/tool_discovery.py:388` ✅
- `app/jobs/anomaly_detection.py:80` ✅
- `app/jobs/pattern_analysis.py:68` ✅
- `app/routes/raya_tool_executors.py:213` ✅

### Note pour A.5

Si pendant l'étape A.5 on revisite tous les `FROM mail_memory`, ne pas oublier de vérifier également :

- `app/mail_memory_store.py:16`
- `app/memory_synthesis.py:241` (DELETE)
- `app/jobs/external_observer.py:82`
- `app/jobs/heartbeat.py:59`
- `app/jobs/briefing.py:76`
- `app/dashboard_queries.py:23`
- `app/routes/aria_loaders.py:39`
- `app/synthesis_engine.py:41`
- `app/retrieval.py:670`
- `app/jobs/proactivity_scan.py:72, 98` (déjà fixé ce matin lignes 50, 76 mais vérifier qu'il n'y a pas d'autres requêtes plus bas dans le fichier)

→ Au lieu d'audit ligne-à-ligne, mieux vaut un grep automatisé pour identifier les anti-patterns (méthode systématique en A.5).

---

## Scénario 2.1 — `POST/DELETE /admin/tenants` exigent `require_super_admin`

**Statut** : ✅ OK (validation A.3)

### Code en prod (commit `2bdddb0`)

`app/routes/admin/super_admin.py` :

```python
@router.post("/admin/tenants")
def create_tenant_endpoint(
    request: Request, payload: dict = Body(...),
    _: dict = Depends(require_super_admin),  # FIX 26/04 : etait require_admin
):
    ...

@router.delete("/admin/tenants/{tenant_id}")
def delete_tenant_endpoint(
    request: Request, tenant_id: str,
    _: dict = Depends(require_super_admin),  # FIX 26/04 : etait require_admin
):
    ...
```

→ Charlotte (tenant_admin de juillet) ne peut plus créer ni supprimer de tenant. Seul guillaume (super_admin) peut.

---

## Scénario 2.2 — `PUT /admin/update-user/{target}` bloque les 3 vecteurs d'escalation

**Statut** : ✅ OK (validation A.4)

### Code en prod (commit `2bdddb0`)

`app/routes/admin/super_admin_users.py:76-115` durci avec 3 contrôles :

1. **Validation enum** : `new_scope` doit être dans `ALL_SCOPES`→ Refuse les scopes arbitraires (str injection)
2. **Promotion super_admin interdite** : `if new_scope == SCOPE_SUPER_ADMIN: raise 403`→ Personne ne peut se hisser super_admin par cette voie (hardcoded only)
3. **Cross-tenant bloqué** : `if admin.scope not in (admin, super_admin): assert_same_tenant(request, target)`→ Charlotte ne peut pas modifier un user de couffrant_solar

### Test en lecture

3 garde-fous présents tels que documentés dans le commit `2bdddb0`. Aucune incohérence entre la doc et le code déployé.

---

## Scénarios 3.1 & 3.2 — Tokens OAuth (validation A.1)

**Statut** : ✅ OK (validation A.1)

### Test 3.1 — `get_valid_microsoft_token('inconnu')` → None

`app/token_manager.py:34-58` :

```python
def get_valid_microsoft_token(username: str) -> str | None:
    # Default 'guillaume' RETIRE
    conn = get_pg_conn()
    tenant_id = _resolve_tenant_strict(username, conn)
    if not tenant_id:
        return None  # User inconnu : pas de token, pas de fallback
    c.execute("""
        SELECT ... FROM oauth_tokens
        WHERE provider = 'microsoft'
          AND username = %s
          AND tenant_id = %s
    """, (username, tenant_id))
```

✅ Pour `username='inconnu'` non présent dans `users` :

- `_resolve_tenant_strict` retourne None
- La fonction retourne None immédiatement
- Pas de fallback `'guillaume'`
- Pas de risque de fuite cross-tenant

### Test 3.2 — `get_connected_providers` filtre `tenant_id`

`app/token_manager.py:283-300` :

```python
def get_connected_providers(username: str) -> list[str]:
    conn = get_pg_conn()
    tenant_id = _resolve_tenant_strict(username, conn)
    if not tenant_id:
        return []
    c.execute(
        "SELECT provider FROM oauth_tokens "
        "WHERE username = %s AND tenant_id = %s",
        (username, tenant_id),
    )
```

✅ Tenant_id résolu depuis l'username, AND tenant_id dans le SELECT. Aucune fuite possible en cas d'homonyme cross-tenant.

### Test additionnel — `oauth_tokens` schema en prod

VérifRésultat`tenant_id` NOT NULL✅Contrainte UNIQUE composite `(provider, username, tenant_id)`✅Tokens existants intacts✅ guillaume/microsoft + guillaume/google

---

## Scénario 1.1 — Charlotte ne voit pas les `aria_rules` de Guillaume

### Test données (DB)

```sql
SELECT tenant_id, username, count(*) AS nb_regles, count(*) FILTER (WHERE active = true) AS nb_actives
FROM aria_rules GROUP BY tenant_id, username ORDER BY tenant_id, username;
```

tenant_idusernamenb_reglesnb_activescouffrant_solarguillaume203162juilletCharlotte1010

✅ Données isolées proprement en DB.

### Test code (revue)

`app/memory_rules.py` contient **3 fonctions avec anti-pattern** identique à celui qu'on a fixé sur `token_manager.py` ce matin :

LigneFonctionAnti-pattern37`get_aria_rules(username='guillaume', tenant_id=None)`Default `'guillaume'` + `tenant_id=None` qui déclenche fallback non isolé (branche `else` de la requête)184`delete_rule(rule_id, username='guillaume', ...)`Default `'guillaume'`290`seed_default_rules(username='guillaume')`Default `'guillaume'`

❌ **TROU LATENT 1.1.A** — Aucun homonyme cross-tenant aujourd'hui, donc pas de fuite **active**, mais bug **latent** : si demain on a une `Charlotte` dans couffrant_solar et qu'un caller appelle `get_aria_rules(username='Charlotte')` sans tenant_id, on récupère les règles des deux Charlotte mélangées.

**Action** : à fixer dans Étape A.5 (même méthode que `token_manager.py` : résolution stricte `_resolve_tenant_strict`, suppression default `'guillaume'`).

### Statut : ⚠️ ATTENTION (latent, non actif)

---

## Scénario 1.1 — Charlotte ne voit pas les `aria_rules` de Guillaume

### Test données (DB) ✅

```sql
SELECT tenant_id, username, count(*) AS nb_regles,
       count(*) FILTER (WHERE active = true) AS nb_actives
FROM aria_rules
GROUP BY tenant_id, username
ORDER BY tenant_id, username;
```

tenant_idusernamenb_reglesnb_activescouffrant_solarguillaume203162juilletCharlotte1010

→ Données parfaitement isolées en base. 0 fuite.

### Revue de code ⚠️ TROU DÉTECTÉ

`app/memory_rules.py` — 3 fonctions avec anti-pattern multi-tenant :

- `get_aria_rules(username='guillaume', tenant_id=None)` ligne 37
  - Default `username='guillaume'` (legacy, anti-pattern multi-tenant)
  - Pattern conditionnel `if tenant_id: ... else:` → si caller passe sans tenant_id, branche `else` qui ne filtre PAS par tenant
- `delete_rule(rule_id, username='guillaume', ...)` ligne 184
  - Default `username='guillaume'`
- `seed_default_rules(username='guillaume')` ligne 290
  - Default `username='guillaume'`

**Risque actuel** : LATENT. Pas d'homonyme cross-tenant en DB aujourd'hui.

**Risque dès qu'un homonyme apparaît** : si `Charlotte` existait dans les 2 tenants, un appel `get_aria_rules('Charlotte')` sans tenant_id mélangerait les règles des 2.

**Verdict** : ❌ TROU → à fixer dans une session future (étape A.5 ou intégrer à l'étape C de l'audit).

---

## Scénario 1.2 — Charlotte ne voit pas les `aria_memory` de Guillaume

### Test données (DB) ✅

```sql
SELECT COALESCE(tenant_id, 'NULL') AS tenant_id, username, count(*)
FROM aria_memory GROUP BY tenant_id, username ORDER BY tenant_id, username;
```

tenant_idusernamenb_conversationscouffrant_solarguillaume200juilletCharlotte9

→ Données isolées en base. 0 ligne `tenant_id IS NULL`.

### Revue de code ⚠️ À CREUSER

24 occurrences `FROM aria_memory` dans 14+ fichiers. Un grep grossier révèle \~14 endroits avec `WHERE username = %s` sans `tenant_id` à proximité immédiate, mais le filtre peut être 5 lignes plus loin (grep insuffisant pour conclure).

Fichiers à auditer en détail :

- `feedback.py`, `memory_synthesis.py`, `synthesis_engine.py`
- `retrieval.py`, `jobs/pattern_analysis.py`, `maturity.py`
- `routes/raya_agent_core.py`, `routes/aria_loaders.py`
- `routes/admin/super_admin_users.py`, `routes/raya_deepen.py`
- `routes/chat_history.py`

**Verdict** : ⚠️ ATTENTION → audit détaillé requis dans une session dédiée. Pour l'instant, données en base prouvées isolées (test 1.2 OK sur l'aspect comportemental).

---

## Scénario 1.3 — Charlotte ne voit pas les `mail_memory` de Guillaume

### Test données (DB) ✅

tenant_idusernamenb_mailscouffrant_solarguillaume946

Total : 946 mails. `tenant_id IS NULL` : 0.

→ Charlotte n'a aucun mail (normal, Outlook/Gmail pas connecté côté juillet — Q5 = super_admin only). Tous les mails appartiennent bien à Guillaume/couffrant_solar.

**Verdict** : ✅ OK (données isolées + 0 NULL).

---

## Scénario 2.1 — `POST/DELETE /admin/tenants` exige `require_super_admin`

### Revue de code ✅

`app/routes/admin/super_admin.py` (commit `2bdddb0`) :

- Ligne \~225 : `@router.post("/admin/tenants")` → `_: dict = Depends(require_super_admin)`
- Ligne \~242 : `@router.delete("/admin/tenants/{tenant_id}")` → `_: dict = Depends(require_super_admin)`

**Verdict** : ✅ OK — les 2 endpoints exigent bien `require_super_admin`(et non plus `require_admin` qui acceptait scope=admin/tenant_admin).

**Verdict** : ✅ OK — les 3 vecteurs d'escalation sont bloqués :

1. Validation enum `if new_scope not in ALL_SCOPES → 400`
2. Blocage promotion super_admin `if new_scope == SCOPE_SUPER_ADMIN → 403`
3. `assert_same_tenant` si l'appelant n'est pas admin/super_admin global

---

## Scénario 3.1 — `get_valid_microsoft_token('inconnu')` retourne None

### Revue de code ✅

`app/token_manager.py` lignes 31-50 (commit `0f333da`) :

- Default `'guillaume'` retiré de la signature → `username: str` (sans default)
- Resolution stricte du tenant via `_resolve_tenant_strict(username, conn)`
- Si `tenant_id` non résolu (user inconnu ou sans tenant_id) → `return None` AVANT toute requête sur `oauth_tokens`
- Le SELECT inclut `AND tenant_id = %s` (filtrage strict)

### Vérification callers (lecture) ✅

23 callers de `get_valid_microsoft_token` dans le codebase, tous passent `username` explicite. Aucun ne dépendait du default `'guillaume'`. Aucun caller à modifier.

**Verdict** : ✅ OK — fonction sécurisée multi-tenant.

---

## Scénario 3.2 — `get_connected_providers` filtre bien `tenant_id`

### Revue de code ✅

`app/token_manager.py` lignes \~270-286 (commit `0f333da`) :

```python
def get_connected_providers(username: str) -> list[str]:
    conn = get_pg_conn()
    tenant_id = _resolve_tenant_strict(username, conn)
    if not tenant_id:
        return []  # User inconnu : aucun provider
    c.execute(
        "SELECT provider FROM oauth_tokens "
        "WHERE username = %s AND tenant_id = %s",
        (username, tenant_id),
    )
```

**Verdict** : ✅ OK — fonction sécurisée multi-tenant. `return []` si user inconnu (pas de fuite vers homonyme), filtre `AND tenant_id`explicite.

---

## Scénario 4.1 — 0 ligne `tenant_id IS NULL` dans les nouvelles données

### Test données (DB) ✅

Audit sur 9 tables sensibles :

| Table | Total | tenant_id IS NULL | Statut |
|---|---|---|---|
| aria_rules | 213 | 0 | ✅ |
| aria_memory | 209 | 0 | ✅ |
| mail_memory | 946 | 0 | ✅ |
| aria_insights | 26 | 0 | ✅ |
| aria_hot_summary | 1 | 0 | ✅ |
| sent_mail_memory | 1388 | 0 | ✅ |
| aria_session_digests | 19 | 0 | ✅ |
| oauth_tokens | 2 | 0 | ✅ |
| users | 6 | 0 | ✅ |

**Total** : 2810 lignes, **0 NULL**.

**Verdict** : ✅ OK exemplaire. La discipline d'isolation tient sur
l'ensemble du parc de données depuis les corrections du 24/04 et les
migrations du 26/04.

---

## Scénario 4.2 — Garde-fou `_PooledConn.close()` + 0 zombie

### Revue de code ✅

`app/database.py` lignes ~75-95 (commit `8196001`) :

```python
def close(self):
    pool = self.__dict__.get("_pool")
    conn = self.__dict__.get("_conn")
    # rollback defensif AVANT putconn
    if conn:
        try: conn.rollback()
        except Exception: pass
    if pool and conn:
        try:
            pool.putconn(conn)
            return
        except Exception: pass
    ...
```

`__exit__` rollback aussi si exception dans le `with` block.

### Test pool en prod ✅

```
{'total': 3, 'active': 2, 'idle': 1, 'idle_in_tx': 0, 'zombies': 0}
```

**Verdict** : ✅ OK. Garde-fou en place + 0 zombie après une journée
entière d'activité (et malgré 2 erreurs résiduelles qui ont planté en
boucle jusqu'au fix `a6b33f8` à 16h). La preuve par l'usage que le
fix structurel fonctionne.

---

# 📊 Synthèse finale — Étape D du 26/04

## Tableau récapitulatif

| # | Scénario | Verdict |
|---|---|---|
| 1.1 | Charlotte ne voit pas les `aria_rules` de Guillaume | ✅ data, ❌ code (3 anti-patterns) |
| 1.2 | Charlotte ne voit pas les `aria_memory` de Guillaume | ✅ data, ⚠️ code (à creuser, 14 fichiers) |
| 1.3 | Charlotte ne voit pas les `mail_memory` de Guillaume | ✅ data |
| 2.1 | `POST/DELETE /admin/tenants` exige `require_super_admin` | ✅ |
| 2.2 | `PUT /admin/update-user` bloque les 3 escalations | ✅ |
| 3.1 | `get_valid_microsoft_token('inconnu')` → None | ✅ |
| 3.2 | `get_connected_providers` filtre `tenant_id` | ✅ |
| 4.1 | 0 ligne `tenant_id IS NULL` dans les nouvelles données | ✅ (2810 lignes auditées) |
| 4.2 | Garde-fou `_PooledConn.close()` + 0 zombie | ✅ |

**Score** : 7 ✅ — 1 ⚠️ — 1 ❌

## Bilan en clair

### Ce qui est SOLIDE (validé)

- **L'étape A est correctement déployée et marche** : tous les
  endpoints admin durcis, tokens OAuth tenant-scopés, default
  `'guillaume'` retiré
- **La discipline d'isolation tient en base** : 0 ligne orpheline sur
  9 tables, 2810 lignes
- **Le garde-fou pool DB tient** : 0 zombie depuis ce matin

### Ce qui DOIT être fixé (chantier futur)

**1 trou ❌ confirmé** dans `app/memory_rules.py` :
- 3 fonctions avec default `username='guillaume'` (anti-pattern)
- Pattern conditionnel `if tenant_id: ... else: pas_de_filtre`
- À fixer comme on l'a fait pour `token_manager.py`
- Estimé : ~30 min

**1 zone ⚠️ à creuser** : `aria_memory` lecture
- 24 occurrences dans 14+ fichiers à auditer en détail
- Audit grossier insuffisant pour conclure (filtres peut-être présents
  mais à 5 lignes du `WHERE username`)
- Estimé : 1-2h d'audit + ~30 min de fixes selon résultats

### Recommandation pour la suite

**Créer une "Étape A.5"** dans la roadmap (Priorité 1, audit isolation) :
- Fix des 3 fonctions de `memory_rules.py`
- Audit détaillé des 14+ fichiers `aria_memory`
- Avant l'Étape B (seat counter UI)

Aujourd'hui pas urgent : aucun homonyme cross-tenant en DB, donc les
trous sont **latents**. Mais dès qu'un homonyme existera (par exemple
quand Charlotte créera un user `Pierre` chez `juillet`), ces trous
deviendront actifs et exploitables.

---

*Document créé le 26 avril 2026, à utiliser comme référence pour
les audits d'isolation futurs. Ré-exécutable : les requêtes SQL et
les recherches de patterns sont reproductibles tel quel.*

---

# 🔬 Phase 3 — Audit détaillé `aria_memory` (étape A.5 part 2)

**Méthode** : pour chaque fichier ayant `FROM aria_memory`, lire la
fonction concernée, classifier :

- ✅ **Sûre** : prend `tenant_id` ET le filtre dans la requête
- ⚠️ **Conditionnelle** : `if tenant_id: filtré, else: pas_de_filtre` ou pattern (`tenant_id = %s OR tenant_id IS NULL`) acceptable selon contexte
- ❌ **Dangereuse** : pas de filtre `tenant_id` du tout
- 🔵 **Cross-tenant légitime** : volontairement non isolé (jobs cron qui itèrent sur tous tenants)

## Liste des 17 fichiers

| # | Fichier | Verdict |
|---|---|---|
| 1 | feedback.py | ⏳ |
| 2 | jobs/anomaly_detection.py | ⏳ |
| 3 | jobs/briefing.py | ⏳ |
| 4 | jobs/external_observer.py | ⏳ |
| 5 | jobs/graph_indexer.py | ⏳ |
| 6 | jobs/heartbeat.py | ⏳ |
| 7 | jobs/pattern_analysis.py | ⏳ |
| 8 | jobs/proactivity_scan.py | ⏳ |
| 9 | maturity.py | ⏳ |
| 10 | memory_synthesis.py | ⏳ |
| 11 | retrieval.py | ⏳ |
| 12 | routes/admin/super_admin_users.py | ⏳ |
| 13 | routes/aria_loaders.py | ⏳ |
| 14 | routes/chat_history.py | ⏳ |
| 15 | routes/raya_agent_core.py | ⏳ |
| 16 | routes/raya_deepen.py | ⏳ |
| 17 | synthesis_engine.py | ⏳ |


## 📊 Résultats détaillés Phase 3

### Scoring final sur 17 fichiers / ~22 requêtes

| Verdict | Count | Fichiers |
|---|---|---|
| ✅ Sûre | 11 | feedback.py, graph_indexer.py (2), maturity.py, retrieval.py, aria_loaders.py (2), chat_history.py, raya_agent_core.py, raya_deepen.py, synthesis_engine.py |
| 🔵 Cross-tenant légitime | 6 | anomaly_detection.py, briefing.py, external_observer.py, heartbeat.py, proactivity_scan.py, pattern_analysis.py |
| ⚠️ Anti-pattern default | 1 | memory_synthesis.py (default username='guillaume' + DEFAULT_TENANT) |
| ❌ Dangereuse | 1 | super_admin_users.py:440 (require_admin sans filtre tenant_id) |

### Fixes appliqués le 26/04 après-midi

**Fix 1 — `super_admin_users.py:426` ❌ → ✅**
- `GET /admin/debug/last-memories/{target}` : `require_admin` → `require_super_admin`
- Charlotte (tenant_admin) ne peut plus consulter les conversations des users de couffrant_solar
- Cohérent avec philosophie SaaS : conversations user/IA = données privées, pas données admin tenant

**Fix 2 — `memory_synthesis.py` ⚠️ → ✅**
- Retiré default `username='guillaume'` (anti-pattern multi-tenant)
- Log WARNING si `tenant_id is None` (durcissement progressif)
- Callers durcis : `memory.py:113` et `memory_actions.py:186` propagent désormais `tenant_id`

**Fix 3 — 6 jobs cron 🔵 documentés**
- Ajout d'un commentaire CROSS-TENANT INTENTIONNEL au-dessus de chaque SELECT cross-tenant
- Liens vers ce doc pour le contexte
- Aucun changement fonctionnel : pure documentation pour éviter qu'un futur fix transforme par erreur ces jobs en versions tenant-scopées (= régression)

### Score global Étape A.5 (parts 1 + 2)

Au début de l'Étape D (matin) : 1 ❌ + 1 ⚠️ + 11 ✅ + 6 🔵
À la fin de l'Étape A.5 (soir) : 0 ❌ + 0 ⚠️ + 13 ✅ + 6 🔵

**Toutes les zones grises sont maintenant traitées.**

