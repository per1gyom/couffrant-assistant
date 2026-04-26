# 🩺 Incident pool de connexions DB — 25-26 avril 2026

**Statut** : ✅ RÉSOLU — fixes déployés le 26/04 matin **Diagnostic + fix** : Claude (audit) + Guillaume (validation des décisions) **Pourquoi ce document** : tracer un vrai incident de prod pour que les futures sessions sachent ce qui s'est passé, comment on l'a résolu, et ce qu'il reste à faire pour ne plus jamais y revenir.

> Ce document est la **source de vérité** sur la résilience du pool de connexions DB. À relire avant tout chantier touchant aux requêtes SQL ou à l'ajout de nouvelles fonctionnalités qui consomment la DB.

---

## 🚨 Le symptôme — ce qu'on a vu

Dimanche 26 avril 2026 à 10h39, vague continue de warnings dans les logs Railway :

```
[raya.db] WARNING: [DB] Pool getconn() échoué (connection pool exhausted) — connexion directe
```

40+ warnings en 18 secondes, en boucle. L'app continuait de fonctionner mais en mode dégradé : à chaque requête, fallback sur une "connexion directe" (ouverture/fermeture TCP à chaque coup, lent et coûteux).

## 🔍 Le diagnostic — comment on a trouvé

### Étape 1 — Voir le code du pool

Dans `app/database.py`, le pool est configuré :

```python
_pool = ThreadedConnectionPool(2, 15, DATABASE_URL)
```

Donc 15 connexions max. Le wrapper `_PooledConn` retourne automatiquement la connexion au pool via `close()`, et un `__exit__` rollback en cas d'exception dans un `with` block.

### Étape 2 — État réel des connexions en prod

Une requête en lecture seule sur `pg_stat_activity` a tout révélé :

statecountactive1idle0idle in transaction0**idle in transaction (aborted)15** ⚠️

15 connexions sur 16 en état "transaction abortée". Postgres refuse toute nouvelle commande sur ces connexions tant qu'on ne fait pas de `ROLLBACK`. Le pool est donc rempli de **connexions zombies**.

### Étape 3 — La signature qui dénonce le coupable

Les 15 connexions zombies avaient toutes :

- **Exactement la même requête** (un SELECT sur `mail_memory` avec filtre `priority = 'haute'` et comparaison de date)
- **Des** `idle_since` **espacés de 30 minutes pile** (14h03, 13h33, 13h03, 12h33, ...)
- **La plus ancienne datait de \~14h** → ce qui ramène à hier soir vers 20h42 si on remonte le temps

30 min = fréquence de `proactivity_scan` (cf. `app/scheduler_jobs.py`, `IntervalTrigger(minutes=30)`). Verdict immédiat : c'est ce job qui laisse fuir une connexion à chaque tick.

### Étape 4 — Reproduction de l'erreur en lecture seule

J'ai exécuté la requête zombie isolée dans `pg_stat_activity` :

```sql
SELECT id, ... FROM mail_memory
WHERE created_at > NOW() - INTERVAL '48 hours'
```

→ Erreur Postgres. Confirmé : **la requête plante**.

Pourquoi ? `mail_memory.created_at` est de type `text` (vu via `information_schema.columns`). La comparaison avec `NOW() - INTERVAL`force une conversion implicite text → timestamp. Cette conversion échouait sur les nouvelles lignes du soir du 25/04.

---

## 🎯 La cause racine — en français simple

Trois ingrédients combinés :

1. `mail_memory.created_at` **est en type** `text` (legacy schema, jamais migré en timestamp). Tant qu'aucune ligne ne tombe dans la fenêtre filtrée, la requête ne provoque pas de crash car Postgres n'a pas besoin de faire la conversion. Hier soir (\~20h42), un mail récent est arrivé dans la fenêtre \[-48h ; -2h\] → conversion déclenchée → crash.

2. **Le code de** `_scan_user` **n'avait aucune protection contre les exceptions SQL** :

   ```python
   def _scan_user(username):
       conn = get_pg_conn()    # ← sans 'with', sans 'try/finally'
       c = conn.cursor()
       c.execute("...SELECT...")  # ← plante
       # JAMAIS de conn.close() après l'exception
   ```

   Quand l'exception remonte, `conn` est abandonnée. Postgres garde la transaction ouverte (en état "aborted"). La connexion ne revient pas au pool.

3. **Le wrapper** `_PooledConn.close()` **ne rollback pas avant** `putconn`, donc même si l'app appelait `close()`, la connexion était rendue au pool dans un état corrompu.

**Mécanique de l'effet boule de neige** : à chaque tick (30 min), 1
connexion supplémentaire fuite du pool. En 7h30, le pool de 15 est
saturé. À partir de là, toutes les requêtes app utilisent le fallback
"connexion directe" — l'app reste debout mais lente.

---

## 🔧 Les correctifs déployés (26/04 matin)

Deux niveaux d'intervention, intentionnellement combinés.

### Niveau 1 — Le bug précis (`app/jobs/proactivity_scan.py`)

Tactique. Bouche le trou exact qui faisait fuir des connexions.

- **Cast `created_at::timestamp`** ajouté aux 4 endroits où on comparait
  `mail_memory.created_at` avec `NOW() - INTERVAL`.
- **Wrapper `try/finally`** : `_scan_user` est devenu un wrapper qui
  ouvre la connexion et garantit son retour au pool même en cas
  d'exception. La logique métier a été extraite en `_scan_user_inner`
  qui prend la connexion injectée en paramètre.
- **`conn.close()` final supprimé** : redondant maintenant que le
  wrapper s'en charge (sinon double-close).

### Niveau 2 — Le garde-fou structurel (`app/database.py`)

**Stratégique.** Empêche n'importe quel autre bout de code de répéter
le même piège dans le futur.

- **`_PooledConn.close()`** fait maintenant `conn.rollback()` AVANT
  `pool.putconn(conn)`. Si la connexion est saine, le rollback ne fait
  rien. Si elle est en transaction abortée, le rollback la nettoie.
  Dans tous les cas, ce qui revient au pool est utilisable.

C'est ce niveau 2 qui rend le système résilient : même si un futur
développeur (ou un futur Claude) écrit du code SQL imparfait, le pool
ne pollue plus en cascade.

---

## 📋 Ce qui reste à faire (futures sessions)

Le fix d'aujourd'hui est une **bonne mi-mesure**, pas une mi-mesure
paresseuse. Voici ce qui reste à faire pour aller au bout, dans
l'ordre de priorité :

### 1. 🟠 Migration progressive des 152 patterns dangereux

Un audit du codebase a révélé **152 endroits** où le code utilise le
pattern dangereux `conn = get_pg_conn()` sans `with` block ni
`try/finally`. Grâce au garde-fou Niveau 2 d'aujourd'hui, ils ne sont
plus des bombes à retardement, mais ils restent **perfectibles**.

**Action** : convertir progressivement ces 152 patterns vers le pattern
sain `with get_pg_conn() as conn:`. Pas urgent, mais à intégrer dans
toute session qui touche à un fichier concerné (réflexe à acquérir).

**Estimation** : ~5-10 min par fichier × 30 fichiers principaux = 3-5h
réparties sur plusieurs sessions.

**Comment commencer** : depuis ce repo, `grep -rn "conn = get_pg_conn()"
app/ --include="*.py"` donne la liste exhaustive.

### 2. 🟠 Monitoring du pool de connexions

Aujourd'hui on ne sait pas que le pool sature **avant** de voir les
warnings. Il faut un monitoring proactif.

**Action** : ajouter dans `app/jobs/system_monitor.py` (qui tourne déjà
toutes les 10 min) une vérification :

```sql
SELECT count(*) FROM pg_stat_activity
WHERE datname = current_database()
  AND state = 'idle in transaction (aborted)'
```

Si le résultat dépasse un seuil (ex. 3), créer une alerte dans
`system_alerts` avec severity `warning`. Si ça dépasse 10, severity
`critical`.

**Estimation** : 30-45 min de dev + tests.

### 3. 🟡 Migration du type `mail_memory.created_at` en timestamp

La cause profonde du bug initial est que `created_at` est en `text`
plutôt qu'en `timestamp`. Le cast `::timestamp` qu'on a ajouté est un
contournement, pas une vraie solution.

**Pourquoi c'est `text` aujourd'hui** : legacy, schema initial. Plusieurs
autres tables sont probablement dans le même cas (à auditer).

**Action** :
1. Auditer toutes les colonnes `created_at`, `updated_at`,
   `received_at` de la DB → faire la liste de celles qui sont en `text`
2. Pour chacune, écrire une migration idempotente dans
   `app/database_migrations.py` :
   - Ajouter une nouvelle colonne `created_at_ts TIMESTAMP`
   - Backfill via `created_at_ts = created_at::timestamp`
   - Switch les requêtes vers la nouvelle colonne
   - Drop l'ancienne colonne `text`
3. Retirer les `::timestamp` casts une fois la migration faite

**Estimation** : 1-2h selon le nombre de tables concernées.

**Précaution** : à faire **après** un backup propre (cf.
`plan_resilience_et_securite.md` étape 2).

---

## ⚠️ Règle de prévention permanente

Ajoutée dans `docs/checklist_isolation_multitenant.md` (section "Règle 8") :

> **Toute nouvelle fonction qui ouvre une connexion DB DOIT utiliser
> le pattern `with get_pg_conn() as conn:`**, jamais `conn = get_pg_conn()`
> sans protection. Le `with` garantit le rollback automatique en cas
> d'exception et le retour au pool.

À vérifier à chaque code review.

---

## 💡 Leçons retenues (pour Claude et Guillaume)

### Pour Claude

1. **Quand ça plante en prod, regarder l'état réel de la DB d'abord**.
   `pg_stat_activity` est la 1ʳᵉ source de vérité, pas le code source.
   Le code montre ce qui *devrait* se passer, la DB montre ce qui *se
   passe vraiment*.

2. **Toujours regarder l'espacement des timestamps des erreurs**. Une
   régularité de 30 min, 2 min, 1h identifie souvent un job scheduler
   précis. C'est un raccourci diagnostic puissant.

3. **Distinguer fix tactique vs fix stratégique**. Quand on identifie un
   bug, se poser la question : *"Et si quelqu'un d'autre fait la même
   bêtise demain dans un autre fichier ?"*. Si oui, ajouter un garde-fou
   au niveau structure (comme le rollback dans `_PooledConn.close()`).

### Pour Guillaume

1. **Le warning "pool exhausted" n'est pas anodin**. C'est le signal que
   du code laisse fuir des connexions. Si ça revient un jour, c'est
   qu'un nouveau bout de code n'a pas suivi la règle 8 de la checklist.

2. **L'app reste debout en mode dégradé** grâce au fallback "connexion
   directe", mais c'est lent et coûteux (chaque requête = ouverture
   TCP). Il faut traiter ces warnings comme une priorité.

3. **Le restart Railway est un pansement temporaire**. Il libère les
   connexions zombies actuelles, mais si la cause root n'est pas fixée,
   le pool sera de nouveau saturé en 7-8 heures. **Toujours fixer la
   cause avant de restart**.

---

## 🔗 Documents liés

- `docs/checklist_isolation_multitenant.md` — règle 8 (pattern `with`)
- `docs/a_faire.md` — Priorité 7 (résilience pool DB)
- `docs/plan_resilience_et_securite.md` — résilience générale
- `app/database.py` — code du pool (`_PooledConn`)
- `app/jobs/proactivity_scan.py` — fichier qui a déclenché l'incident

---

*Document créé le 26 avril 2026 par Claude (audit + fix) avec Guillaume
(décisions). À mettre à jour si l'incident se reproduit ou si une des
3 actions de suivi est complétée.*
