# 📋 Rapport d'audit approfondi — Scanner Universel

**Auteur** : Claude
**Date** : 19 avril 2026, ~9h30
**Contexte** : après 4 runs de vectorisation P1 qui ont tous crashé silencieusement entre hier soir et ce matin. Objectif : comprendre en profondeur les causes, proposer une architecture durable et sûre, valable pour tous les outils (Odoo, demain Drive, Teams, etc.).

---

## 🎯 TL;DR

Le Scanner Universel a des **problèmes structurels de fiabilité** qui expliquent pourquoi il crashe sans alerte et laisse des runs fantômes en état `running` pendant des heures.

Je recommande de **reconstruire le cœur du Scanner** autour de 5 principes :

1. **Découpage fin : 1 unité de travail = 1 modèle** (pas 1 run = 16 modèles).
2. **Auto-vérification après chaque modèle** (compare odoo vs raya vs chunks DB).
3. **Alerte immédiate** si un modèle échoue, le run s'arrête proprement et t'informe.
4. **Reprise manuelle ou automatique** modèle par modèle (pas besoin de tout recommencer).
5. **Heartbeat explicite** : un watchdog qui détecte les threads morts et les nettoie.

**Les 3 bugs critiques identifiés et leurs fixes** sont à la fin du rapport, mais aucun n'est vraiment la cause racine — la cause racine, c'est l'architecture qui assume "tout va bien se passer" alors qu'une vectorisation de 16 modèles × 5000 records, c'est 80k+ appels réseau qui ne peuvent PAS tous réussir.

---

## 📐 Architecture actuelle (telle qu'elle existe)

### Le flow d'un scan P1

1. **Déclenchement** : `POST /admin/scanner/run/start` → appelle `runner.start_scan_p1()`
2. **Création du run** : `orchestrator.create_run()` insère une ligne dans `scanner_runs` avec `status='pending'`, `run_id=UUID`
3. **Thread background** : un `threading.Thread` démarre `_run_scan_worker(run_id, ...)` en mode `daemon=True`
4. **Purge initiale** (si `purge_first=True`) : vide `odoo_semantic_content`, `semantic_graph_nodes/edges`, reset `connector_schemas.last_scanned_at`
5. **Fetch manifests** : récupère la liste des modèles P1 depuis `connector_schemas`, triés par `records_count_odoo DESC`
6. **Boucle sur modèles** : pour chaque modèle, pagine par batch de 50, process chaque record, checkpoint en DB tous les 50, sleep 500ms entre batches
7. **Finalisation** : `orchestrator.finish_run()` → `status='ok'`, `finished_at=NOW()`

### Le garde-fou "cleanup_stale_runs"

Appelé **au startup de l'app FastAPI** (`main.py`), il fait :
```sql
UPDATE scanner_runs
SET status='error', finished_at=NOW(), error_message='Runtime interrupted...'
WHERE status IN ('running','pending') AND updated_at < NOW() - INTERVAL '10 minutes'
```

---

## 🔴 Les 3 bugs critiques identifiés

### BUG 1 — Le garde-fou cleanup_stale_runs est CASSÉ

**Fichier** : `app/scanner/orchestrator.py` ligne 205
**Symptôme dans les logs PostgreSQL** :
```
ERROR: column "error_message" of relation "scanner_runs" does not exist
```
Cette erreur apparaît **7 fois** dans les logs, à chaque redémarrage de l'app Railway (toutes les 5-10 minutes).

**Cause** : le code utilise `error_message` alors que la vraie colonne s'appelle `error` (comme utilisée dans `fail_run()` au même fichier, ligne 97).

**Impact dramatique** :
- À chaque restart de l'app, le cleanup **échoue silencieusement** (le `try/except` dans `main.py` avale l'erreur avec juste un `logger.warning`)
- Les runs fantômes restent en `status='running'` **pour toujours**
- Résultat constaté : 4 runs en état `running` depuis le 18/04 à 14h40, aucun n'a jamais été cleanup

**Fix direct** : remplacer `error_message` par `error` à ligne 205.

### BUG 2 — Le worker crashe silencieusement, personne ne le sait

**Fichiers** : `app/scanner/runner.py` lignes 289-296

**Cause** : le thread est `daemon=True`. Si l'app Railway redémarre (OOM, healthcheck, deploy, crash), le thread est **tué instantanément, sans finalisation** :
- Pas de `orchestrator.fail_run()` appelé
- Pas d'entrée dans les logs
- Le run reste en `running` en DB

**Indice dans nos logs** : le run #4 s'est "figé" à `of.survey.answers` avec `updated_at=00:28`, alors qu'on a des logs PG qui montrent des restarts répétés de l'app toutes les ~10 minutes depuis 19:57 UTC.

**Impact** :
- Guillaume croit que ça tourne → attend → constate au matin que c'est mort depuis des heures
- Aucun moyen automatique de relancer ce qui a été interrompu
- Le cleanup qui était censé gérer ça est cassé (bug 1)

**Fix** : voir la section "Nouvelle architecture" plus bas — ce n'est pas un fix ponctuel, c'est un repenser du modèle d'exécution.

### BUG 3 — mail.message : 0 records malgré 10k attendus

**Fichier** : pas clair. Soit `adapter_odoo.fetch_records_batch` soit `processor.process_record` soit `_write_semantic_chunk`.

**Observation** :
- `connector_schemas`: `mail.message`, `records_count_odoo=29139`, `records_count_raya=0`, `last_scanned_at=18/04 23:38`
- `progress`: `mail.message done=0/10000 pct=0.0%`
- `stats.errors=109` (énorme, la majorité vient probablement de là)

**Hypothèse dominante** : `mail.message` en XML-RPC retourne des erreurs parce que le champ `body` contient du HTML très lourd (des emails entiers avec CSS inline, images base64, etc.). Le `fetch_records_batch` lève une exception, le worker catch, skip, réessaie le batch suivant, rebelotte → 109 erreurs cumulées.

**Preuve circonstancielle** : dans le code runner ligne 200-210 :
```python
except Exception as e:
    logger.exception("[Runner run=%s] fetch %s offset=%d", ...)
    global_stats["errors"] += 1
    offset += batch_size
    if offset > (total_records or 0) + batch_size * 2:
        break
    continue
```
Le worker **n'abandonne pas** le modèle après N erreurs. Il essaye TOUS les offsets jusqu'à dépasser `total_records + 100`, en consommant 500ms × nb_batches inutiles. Pour `mail.message` avec limite 10000 / batch 50 = **200 batches ratés** avant d'abandonner.

**Fix ponctuel possible** :
1. Vérifier les vrais champs utiles de `mail.message` (peut-être `body` peut être skippé ou tronqué)
2. Ajouter un "circuit breaker" : après 5 échecs consécutifs, skip le modèle et passer au suivant

---

## 🧨 Problèmes structurels (au-delà des 3 bugs)

### Problème A — Unité de travail trop grosse

Le Scanner traite les 16 modèles d'un bloc. Si un modèle plante, tout est perdu. Si Railway restart, tout recommence à zéro au prochain scan (avec `purge_first=True` !).

**Ce qu'on devrait faire** : 1 run = 1 modèle. 16 modèles P1 = 16 runs indépendants séquentiels (ou parallèles modérés).

### Problème B — Pas d'auto-vérification

Aujourd'hui, `records_count_raya` est mis à jour **APRÈS** la boucle de vectorisation, mais **AVANT** que la commit DB soit effectivement flush. Si le worker crashe entre les deux → on a 4980 chunks en DB mais la colonne `records_count_raya` reste vide (exactement ce qui est arrivé à `of.survey.answers`).

**Ce qu'on devrait faire** : après chaque modèle, **recompter les chunks réellement en DB** :
```sql
SELECT COUNT(*) FROM odoo_semantic_content
WHERE tenant_id=? AND source_model=?
```
Comparer avec le compteur attendu, alerter si écart > 5%.

### Problème C — Pas d'alerte immédiate

Si 109 erreurs s'accumulent sur `mail.message`, Guillaume ne le sait que le lendemain matin en ouvrant le dashboard 📊 Intégrité. Aucune notif, aucun email, aucun push.

**Ce qu'on devrait faire** :
- Envoyer un mail à Guillaume si un run échoue (il a déjà `mail_config.py` dans l'app)
- Ou afficher un banner rouge sur `/admin/panel` tant qu'un run est en erreur non-résolu

### Problème D — Pas de reprise granulaire

Si `mail.message` plante mais que les 14 autres modèles marcheraient, on ne peut pas juste "rejouer mail.message". Il faut relancer TOUT un P1 avec purge.

**Ce qu'on devrait faire** : bouton "Relancer ce modèle" par ligne du dashboard 📊 Intégrité. Supprime les chunks du modèle, rescan uniquement lui.

### Problème E — Thread daemon = crash silencieux

`daemon=True` signifie que le thread meurt instantanément quand le process principal meurt. **C'est exactement l'opposé de ce qu'on veut**. On veut que le travail soit résilient au crash, pas attaché à la vie du web serveur.

**Ce qu'on devrait faire** : externaliser le scanner dans un **vrai worker process** (genre Celery) ou au minimum dans une tâche APScheduler qui peut être interrompue proprement et reprendre.

---

## 🏗️ Nouvelle architecture proposée

### Principe directeur

> **Un scan d'outil = une séquence d'étapes atomiques, chacune vérifiable, chacune reprisable, chacune sous surveillance.**

### Changement 1 — Table `scanner_model_runs` (nouveau)

On garde `scanner_runs` pour la vue d'ensemble (1 run = 1 session complète de scan d'un tenant/source), mais on ajoute une table fille :

```sql
CREATE TABLE scanner_model_runs (
    id SERIAL PRIMARY KEY,
    run_id UUID REFERENCES scanner_runs(run_id),
    model_name TEXT NOT NULL,
    priority INT,
    status TEXT,  -- pending|running|ok|error|skipped
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    heartbeat_at TIMESTAMPTZ,  -- NEW : mis à jour toutes les 10s
    records_expected INT,
    records_processed INT,
    chunks_created INT,
    errors_count INT,
    last_error TEXT,
    last_checkpoint_id BIGINT,
    UNIQUE(run_id, model_name)
);
```

Un run = 16 lignes dans cette table (une par modèle P1). On peut voir exactement où ça a planté.

### Changement 2 — Heartbeat explicite toutes les 10 secondes

Dans le worker, pendant qu'il process des records :
```python
# Tous les 10 secondes OU tous les 100 records, met à jour heartbeat_at
if time.time() - last_heartbeat > 10:
    update_heartbeat(run_id, model_name, records_processed)
    last_heartbeat = time.time()
```

### Changement 3 — Watchdog automatique

Dans `main.py` au démarrage (et en APScheduler toutes les 2 minutes) :
```sql
-- Detecte les modèles qui n'ont pas heartbeaté depuis 2 minutes
UPDATE scanner_model_runs
SET status='error', finished_at=NOW(),
    last_error='No heartbeat for 2min - worker died'
WHERE status='running' AND heartbeat_at < NOW() - INTERVAL '2 minutes';
```

### Changement 4 — Auto-vérification après chaque modèle

```python
def verify_model_run(run_id, model_name, tenant_id, source):
    """Vérifie qu'un scan de modèle est cohérent."""
    # 1. Compte réel en DB
    chunks_db = count_chunks(tenant_id, source, model_name)
    nodes_db = count_nodes(tenant_id, source, model_name)
    expected = get_expected(run_id, model_name)
    # 2. Calcule l'intégrité
    integrity_pct = chunks_db / expected * 100 if expected else 0
    # 3. Verdict
    if integrity_pct >= 95:
        return "ok"
    elif integrity_pct >= 50:
        return "warning"  # Alerte mais continue
    else:
        return "error"    # Stop le run et alerte Guillaume
```

### Changement 5 — Flow avec circuit breaker

Pour chaque modèle, dans un try/except global :
```python
def run_single_model(run_id, model_name):
    mark_model_running(run_id, model_name)
    try:
        consecutive_errors = 0
        for batch in iterate_batches(model_name):
            try:
                process_batch(batch)
                consecutive_errors = 0
            except Exception as e:
                consecutive_errors += 1
                log_error(run_id, model_name, e)
                if consecutive_errors >= 5:
                    raise CircuitBreakerOpen(
                        f"5 erreurs consécutives, abandon du modèle"
                    )
            heartbeat(run_id, model_name)
        verdict = verify_model_run(run_id, model_name)
        mark_model_done(run_id, model_name, verdict)
        return verdict
    except Exception as e:
        mark_model_failed(run_id, model_name, str(e))
        if is_critical_model(model_name):
            raise  # Stop le run entier
        return "error"  # Continue aux modèles suivants
```

### Changement 6 — Notification immédiate

Dans `mark_model_failed()` :
```python
def mark_model_failed(run_id, model_name, error):
    update_db(status="error", last_error=error)
    send_alert_email(
        to="per1.guillaume@gmail.com",
        subject=f"🔴 Scanner Raya : échec sur {model_name}",
        body=f"Run {run_id[:8]} a échoué sur le modèle {model_name}..."
    )
```

### Changement 7 — UI pas-à-pas (Guillaume decide)

Guillaume demande la possibilité de valider modèle par modèle. Deux modes possibles :

**Mode A — Automatique avec pause sur erreur** : le scanner continue jusqu'au bout si tout va bien. Si un modèle échoue, il s'arrête et attend une action manuelle (retry / skip / abort).

**Mode B — Manuel validation par étape** : le scanner traite un modèle, affiche le résultat (N chunks, X% intégrité), attend que Guillaume clique "Valider et passer au suivant" ou "Relancer ce modèle".

Je recommande **Mode A par défaut** (automatique sauf erreur) avec **Mode B en option** pour les premiers tests d'un nouvel outil. Ça évite à Guillaume de devoir cliquer 16 fois si tout se passe bien, tout en lui donnant la possibilité de valider quand il veut.

---

## 🗺️ Généralisation pour les futurs outils

Tu m'as dit : "demain, un nouvel outil, on cartographie, on vectorise pareil." Voici comment structurer ça pour que ce soit pérenne.

### Le pattern "Scanner Universel" consolidé

```
┌─────────────────────────────────────────────────────────┐
│  1. EXPLORATION (introspection, manuel ou auto)          │
│     → Liste des entités disponibles dans l outil         │
│     → Génère la table connector_schemas                  │
└─────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────┐
│  2. MANIFESTS (description de CE QUI doit être vectorisé)│
│     → 1 manifest par entité = {fields, edges, metadata} │
│     → Stocké en DB, modifiable par Guillaume             │
└─────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────┐
│  3. SCANNER (= notre sujet du jour)                     │
│     → Lit les manifests, fetch, process, embed, écrit   │
│     → Avec heartbeat + verify + circuit breaker          │
└─────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────┐
│  4. AUTO-VÉRIFICATION                                   │
│     → Compare count outil vs count Raya                 │
│     → Valide l intégrité par modèle                     │
│     → Alerte immédiate si écart                         │
└─────────────────────────────────────────────────────────┘
                        ↓
┌─────────────────────────────────────────────────────────┐
│  5. SYNC DELTA (mode nocturne ou sur webhook)           │
│     → Identifie les records modifiés depuis dernier run │
│     → Ne rescanne QUE ceux-là                            │
└─────────────────────────────────────────────────────────┘
```

### Ce qui doit être **abstrait** (commun à tous les outils)

1. **Orchestrateur** : `create_run`, `update_progress`, `heartbeat`, `verify`, `finish_run`, `fail_run`
2. **Scheduler** : lancer un scan par modèle, un modèle à la fois, avec timeout et circuit breaker
3. **Watchdog** : détecte les workers morts, marque en erreur, notifie
4. **Vérificateur** : compare count source vs count Raya, calcule intégrité
5. **Notifier** : envoie mail/push à Guillaume en cas d'échec
6. **API REST** : start_scan / get_status / retry_model / verify / list_runs

### Ce qui doit être **spécifique par outil** (adapter)

1. `fetch_records_batch(model_name, fields, offset, limit, domain)` — récupère un batch depuis l'outil
2. `count_records(model_name, domain)` — compte total
3. `get_available_models()` — pour l'introspection
4. `list_modified_since(timestamp)` — pour la sync delta

Pour Odoo, on a déjà `adapter_odoo.py` qui fait ça. Pour Drive, il faudra `adapter_drive.py` avec la même interface. Pour Teams, `adapter_teams.py`. **Le reste du Scanner ne changera pas**.

### Ce qui est spécifique par entité (manifest)

Le manifest décrit :
- Les champs à vectoriser (`vectorize_fields`)
- Les champs metadata (`metadata_fields`)
- Les aretes du graphe (`graph_edges` avec type, field, target_model)
- La priorité (P1 = critique, P2 = complémentaire)

Pour un nouvel outil, Guillaume (ou une routine auto d'introspection) crée les manifests, puis le scanner les consomme. **Aucun code à changer**.

---

## 📊 État actuel vs état cible

### Aujourd'hui

| Aspect | État |
|---|---|
| Unité de travail | 1 run = 16 modèles | 
| Reprise après crash | Impossible (purge obligatoire) |
| Détection crash | Cassée (bug error_message) |
| Alerte immédiate | Absente |
| Vérification post-scan | Faible (juste records_count_raya) |
| Circuit breaker | Absent (200 batches ratés possibles) |
| Notification | Aucune |
| UI granulaire | Inexistante |

### Cible

| Aspect | État cible |
|---|---|
| Unité de travail | 1 run = 1 modèle, orchestrés |
| Reprise après crash | Par modèle, depuis checkpoint |
| Détection crash | Watchdog auto toutes les 2 min |
| Alerte immédiate | Email + UI banner |
| Vérification post-scan | Comparaison complète, seuils d'alerte |
| Circuit breaker | 5 erreurs consécutives = abandon |
| Notification | Email à Guillaume sur chaque échec |
| UI granulaire | Bouton retry/skip/abort par modèle |

---

## 📅 Plan de mise en œuvre proposé (3 étapes)

### Étape 1 — Fix des bugs critiques + circuit breaker (1h30)

**Objectif** : éviter que ça recommence à casser silencieusement dès aujourd'hui.

1. Corriger `error_message` → `error` dans `cleanup_stale_runs` (BUG 1). **5 min**.
2. Nettoyer manuellement les 4 runs fantômes (UPDATE DB direct). **5 min**.
3. Ajouter un **circuit breaker simple** dans le runner : après 5 erreurs consécutives sur un modèle, on l'abandonne et on passe au suivant. Ça évite que `mail.message` consomme 100 minutes à tourner dans le vide. **30 min**.
4. Ajouter un **compteur en fin de modèle** qui recompte les chunks réellement en DB et met à jour `records_count_raya` avec la vraie valeur (pas l'estimation). **20 min**.
5. Tester en lançant un nouveau run P1 propre et observer. **30 min**.

Avec ça, tu as quelque chose de **stable pour les prochains jours**, sans refactor en profondeur.

### Étape 2 — Heartbeat + watchdog + verify (2h30)

**Objectif** : détecter automatiquement les crashes et vérifier la complétude.

1. Créer la table `scanner_model_runs` + migration. **30 min**.
2. Modifier le worker pour créer 1 entrée par modèle + heartbeat toutes les 10s. **45 min**.
3. Créer `watchdog_check_stale_models()` dans APScheduler, toutes les 2 min. **30 min**.
4. Créer `verify_model_run()` qui compare chunks_db vs expected. **30 min**.
5. Tester sur les 16 modèles P1 en mode dégradé (tuer un thread volontairement). **15 min**.

### Étape 3 — Notification + UI granulaire + généralisation (2h)

**Objectif** : rendre l'outil utilisable en production pour des clients.

1. Email d'alerte à chaque échec de modèle (via `mail_config.py` existant). **30 min**.
2. Bouton "Relancer ce modèle" par ligne dans le dashboard 📊 Intégrité. **45 min**.
3. Abstraire l'adapter en interface claire (documenter les méthodes requises). **30 min**.
4. Écrire un guide "Comment ajouter un nouvel outil" dans docs/. **15 min**.

**Total estimé : 6h de dev** sur 2-3 sessions bien reposées.

---

## ⚠️ Recommandations prudentes

### Ce que je ne ferai PAS seul (décision à prendre)

1. **Externaliser le scanner dans Celery ou RQ** : c'est THE solution pro mais ça demande d'installer Redis sur Railway, configurer les workers, changer le flow de déploiement. Lourd. On peut s'en passer pour le moment en acceptant que `threading.Thread` + heartbeat + watchdog suffit pour v1.

2. **Parallélisme entre modèles** : tentant mais risqué (conflits de DB, rate limits Odoo XML-RPC). À garder séquentiel pour v1, paralléliser plus tard si besoin de perf.

3. **Suppression du mode "purge avant rebuild"** : tu l'utilises aujourd'hui pour repartir propre. À garder comme option mais proposer aussi un "scan incrémental" qui ne purge rien.

### Avant de lancer l'Étape 1 aujourd'hui

Je propose qu'on commence par **nettoyer la DB manuellement** :
```sql
UPDATE scanner_runs
SET status='error', finished_at=NOW(), error='Manual cleanup after 18h downtime'
WHERE status='running';
```
Ça va marquer les 4 runs fantômes comme erreur et libérer le système.

Puis on fait les **fixes des bugs critiques** (points 1-4 de l'Étape 1), sans toucher à l'architecture profonde.

Puis on teste un run propre avec le circuit breaker actif.

---

## 💡 Observations finales

### Ce qui est déjà bon dans l'architecture existante

- **Séparation propre** orchestrator / runner / processor / adapter — bon découpage.
- **Manifests en DB** — permet d'ajouter des modèles sans redéployer.
- **Checkpointing `last_id`** — la structure est là, juste sous-exploitée.
- **`MODEL_RECORD_LIMITS`** — bon garde-fou contre la saturation DB.
- **Le dashboard 📊 Intégrité** — bonne idée de visualisation.

### Ce qui manque vraiment

- **Observabilité** : aucune métrique en temps réel, pas de logs structurés par modèle.
- **Résilience** : pas de retry intelligent, pas de timeout par modèle.
- **UX d'erreur** : Guillaume apprend les problèmes en regardant l'écran le matin.

### La vraie question stratégique

Est-ce qu'on veut quelque chose qui marche **suffisamment bien pour Couffrant Solar** (1 tenant, 16 modèles, ~225k records max) ou quelque chose qui **tient la charge pour 10 clients** (10 tenants × 16 modèles × 200k records = 32M records à vectoriser potentiellement) ?

Pour Couffrant Solar seul, l'Étape 1 suffit probablement. Pour scaler à des clients payants, il faudra aussi l'Étape 2 (heartbeat/watchdog) au minimum, et l'Étape 3 (notifications) pour ne pas devenir toi-même le watchdog humain.

---

## 🎯 Ma recommandation finale

1. **Ce matin** : nettoyer la DB + Étape 1 (fix bugs critiques + circuit breaker). Tester. Prendre café.

2. **Cette semaine** : si Étape 1 marche bien, passer à l'Étape 2 (heartbeat/watchdog). C'est là que l'outil devient vraiment **durable**.

3. **Avant d'ajouter Juillet ou un 2e client** : Étape 3 obligatoire (notification + UI granulaire).

Tu me dis "go étape 1" quand tu veux, je fais, sans bricoler cette fois. Promis.

---

**Fin du rapport.**

Document en `/Users/per1guillaume/couffrant-assistant/docs/raya_scanner_audit_rapport.md`
Non poussé, comme pour le précédent audit. Tu le pousses quand tu veux.
