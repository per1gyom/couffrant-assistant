# 📘 Playbook de vectorisation Raya — pour tout nouvel outil

**Date création** : 19 avril 2026
**Auteur** : Claude + Guillaume
**Contexte** : ce playbook capitalise sur l'expérience de la vectorisation Odoo/OpenFire (Couffrant Solar) pour permettre de rebrancher n'importe quel nouvel outil (Drive, Teams, Salesforce, HubSpot, etc.) sans refaire les mêmes galères.

---

## 🎯 Principe général

Un outil connecté à Raya passe par **une vectorisation initiale (one-shot)**, puis un mécanisme d'**update automatique** (delta nocturne ou webhooks). **On ne vectorise JAMAIS complètement deux fois** — ensuite c'est du delta.

Le playbook décrit le one-shot initial + les pièges connus + les scripts réutilisables.

---

## 📋 Étapes à suivre pour un nouvel outil

### Phase 1 — Connexion à l'outil

1. Créer le connecteur dans `app/connectors/<outil>_connector.py` avec les primitives :
   - `<outil>_authenticate()` → retourne session/token
   - `<outil>_call(entity, method, args, kwargs)` → appel d'API générique
2. Ajouter les variables d'environnement `<OUTIL>_URL`, `<OUTIL>_API_KEY`, etc. dans `.env` ET dans Railway
3. **Important** : au niveau de `<outil>_call`, **ne pas tronquer les erreurs à moins de 5000 caractères**. Les tracebacks sont longs, on a besoin du nom des champs coupables pour diagnostiquer.

### Phase 2 — Introspection automatique

1. Créer `app/scanner/adapter_<outil>.py` qui implémente :
   - `fetch_records_batch(entity, fields, offset, limit, domain, order)` → pagination
   - `count_records(entity, domain)` → total
   - `get_available_models()` → liste des entités disponibles
   - (optionnel) `list_modified_since(timestamp)` → pour la sync delta
2. Lancer l'introspection : **bouton 🔍 Inventaire** dans `/admin/panel` → peuple la table `connector_schemas` avec les modèles découverts

### Phase 3 — Génération des manifests

1. **Bouton 📋 Manifests** → génère automatiquement un manifest par modèle via classification des champs :
   - `vectorize_fields` : champs texte longs (description, body, notes)
   - `metadata_fields` : champs structurels (dates, montants, états)
   - `graph_edges` : relations many2one vers d'autres modèles (IDs)
2. Ajuster les priorités (P1 = critique pour proactivité, P2 = complémentaire)
3. Ajuster `MODEL_RECORD_LIMITS` dans `app/scanner/runner.py` pour plafonner les gros modèles (>10k records)


### Phase 4 — Test P1 sur 200 records (CRITIQUE, ne PAS sauter)

**Ne jamais lancer un Scanner P1 complet en premier**. Toujours passer par un test 200 records avant.

1. Cliquer **🧪 Test manquants** dans `/admin/panel` (pour P1)
2. Attendre ~5-10 min
3. Analyser le résultat :
   - ✅ **Si tout passe** : on peut lancer le Scanner P1 complet
   - ❌ **Si certains modèles sont abandonnés** (circuit breaker) : diagnostic nécessaire

### Phase 5 — Diagnostic des modèles qui plantent

Pour chaque modèle qui plante, **lire le `reason` complet dans `scanner_runs.stats.models_aborted`** :

```sql
SELECT stats->'models_aborted' FROM scanner_runs ORDER BY id DESC LIMIT 1;
```

**Patterns connus (exprérience Couffrant)** :

| Symptôme | Cause probable | Solution |
|---|---|---|
| `ValueError: Compute method failed to assign X.field_name` | Champ computed cassé côté serveur | Retirer `field_name` du manifest |
| `AccessDenied` | Droits API insuffisants sur ce modèle | Créer un user dédié avec ACL étendus |
| Retourne 0 records mais pas d'erreur | Filtre implicite côté serveur | Vérifier les droits + ajouter domain explicite |
| Timeout / batch > 30s | Champ HTML très lourd (body, description) | Réduire batch_size OU retirer le champ |
| `CacheMiss` sur graph_edges | Même problème que ValueError | Retirer le champ du graph_edges |

**Script de diagnostic réutilisable** : `scripts/diagnose_odoo_models.py` (à adapter pour chaque nouvel outil — binary search sur les champs du manifest pour identifier les tueurs).

### Phase 6 — Correction des manifests

1. Retirer les champs cassés via script Python direct sur la DB (pas de redéploiement nécessaire — les manifests vivent en DB) :

```python
from app.database import get_pg_conn
with get_pg_conn() as conn:
    cur = conn.cursor()
    cur.execute("SELECT manifest FROM connector_schemas WHERE model_name='X'")
    m = cur.fetchone()[0]
    m['graph_edges'] = [e for e in m['graph_edges'] if e['field'] != 'bad_field']
    cur.execute("UPDATE connector_schemas SET manifest=%s WHERE model_name='X'", (json.dumps(m),))
    conn.commit()
```

2. Relancer **🧪 Test manquants** pour vérifier que ça passe
3. Itérer jusqu'à ce que tout soit vert


### Phase 7 — Scan complet P1

Une fois que le Test manquants donne 0 abandons :

1. Cliquer **🚀 Scanner P1** (avec purge_first=True si première fois, False sinon)
2. Modale "Êtes-vous sûr ?" → Oui
3. Attendre 30-90 min selon volume
4. Bouton **⏹️ Stop** disponible en cas de besoin (l'arrêt est propre : finit le modèle en cours)

### Phase 8 — Test P2 sur 200 records + scan complet P2

Même démarche que pour P1 :
1. Script `scripts/test_p2_200.py` (à adapter par outil, garder le pattern)
2. Diagnostic + correction manifests
3. Scan complet P2

### Phase 9 — Sync delta (post-bootstrap)

Une fois le one-shot terminé, **on ne rescane PLUS l'intégralité**. On met en place :

- **Option A — Delta nocturne** : cron/APScheduler qui scanne uniquement les records modifiés depuis la dernière sync (via `write_date > last_sync`)
- **Option B — Webhooks** : l'outil pousse les changements en temps réel à Raya (si supporté)
- **Option C — Polling périodique** : toutes les N minutes, check des updates

Pour Odoo : Option A implémentée via `write_date` sur chaque modèle.

---

## 🚨 Règles d'or (apprises à la dure)

1. **NE JAMAIS** lancer un Scanner complet en premier, **toujours** 200 records test avant.
2. **NE JAMAIS** tronquer les messages d'erreur à moins de 5000 chars (on a perdu 2h à cause d'un `[:500]` qui cachait le nom du champ coupable).
3. **NE JAMAIS** purger avant d'avoir une cause racine identifiée. Les chunks qui marchent sont précieux.
4. **TOUJOURS** un circuit breaker (5 erreurs consécutives = abandon du modèle, pas du run entier).
5. **TOUJOURS** un heartbeat (`updated_at` à jour dans `scanner_runs` toutes les 10s pendant un scan) pour que le watchdog puisse nettoyer les runs fantômes.
6. **TOUJOURS** une double validation UI sur les actions destructives (purge, suppression, etc.).
7. **TOUJOURS** une logique d'arrêt propre (bouton Stop) avec finalisation du modèle en cours.

---

## 🛠️ Scripts réutilisables

| Script | Usage |
|---|---|
| `scripts/diagnose_odoo_models.py` | Binary search sur champs pour identifier les tueurs |
| `scripts/scan_nuit.py` | Complément vectorisation multi-étapes (exemple concret) |
| `scripts/test_p2_200.py` | Test sur 200 records pour un palier de priorité |

**Pattern à suivre pour un nouveau script** :
- Charger `.env` avant les imports `app.*`
- Logs horodatés (heure Paris, DB en UTC donc +2h en été)
- Chaque étape dans un try/except indépendant (ne pas bloquer la suite)
- Recap AVANT/APRÈS avec comptage DB réel
- `purge_first=False` par défaut sauf justification explicite


---

## 📐 Architecture de référence (Odoo/OpenFire, validé 19/04/2026)

### Tables DB clés

- `connector_schemas` : manifests (1 ligne par tenant × source × model)
- `scanner_runs` : historique des runs (run_id UUID, status, stats JSONB, error, stop_requested)
- `odoo_semantic_content` : chunks vectorisés (embedding pgvector 1536)
- `semantic_graph_nodes` / `semantic_graph_edges` : graphe relationnel

### Flow d'un scan

```
POST /admin/scanner/run/start  OU  scripts/scan_*.py
    ↓
orchestrator.create_run() → scanner_runs INSERT status='pending'
    ↓
Thread daemon _run_scan_worker
    ↓
Pour chaque modèle P1 (trié par records_count_odoo DESC) :
    ↓ check is_stop_requested() — si oui, stop_run() et return
    ↓ Si record_limits[m] == 0 : skip
    ↓ Boucle batch_size=50 :
        ↓ adapter.fetch_records_batch(model, fields, offset, limit, domain)
        ↓ circuit breaker : 5 erreurs consécutives → model_aborted_reason
        ↓ Pour chaque record : processor.process_record() → chunk + nodes + edges
        ↓ Checkpoint en DB (last_id, done, total)
        ↓ Sleep 500ms (rate limit + laisse respirer le /health Railway)
    ↓ UPDATE connector_schemas : chunks RÉELLEMENT en DB (SELECT COUNT)
    ↓ Log verdict OK/WARNING/CRITICAL
    ↓
orchestrator.finish_run() → status='ok'
```

### Gardes-fous actifs

1. **Circuit breaker** : 5 erreurs consécutives / modèle = abandon propre (code dans runner.py)
2. **Recomptage réel** : `records_count_raya` = vrai `SELECT COUNT` en fin de modèle (pas l'estimation in-memory)
3. **Cleanup stale runs** : au startup Railway, marque en erreur les runs > 10 min sans update (fix appliqué 19/04, bug `error_message` → `error` corrigé)
4. **Stop graceful** : flag `stop_requested` vérifié avant chaque modèle
5. **Double validation UI** : modale HTML "Êtes-vous sûr ?" sur Scanner P1, Test manquants, Stop, Suppressions
6. **Dashboard 6 severities** : ok / warning / critical / limited (plafond volontaire) / graph_only (pas de vectorize_fields) / unknown

### Endpoints API

- `POST /admin/scanner/manifests/generate` → Phase 3 introspection
- `POST /admin/scanner/run/start?priority_max=1&purge_first=true` → Scanner P1 complet
- `POST /admin/scanner/run/test-missing?sample_size=200` → Test sur manquants (ou complet si >=10000)
- `POST /admin/scanner/run/stop?run_id=<uuid>` → Stop graceful
- `GET /admin/scanner/run/status?run_id=<uuid>` → Polling status
- `GET /admin/scanner/run/list?limit=10` → Liste runs récents
- `GET /admin/scanner/integrity` → Dashboard intégrité
- `GET /admin/scanner/db-size` → Taille DB (monitoring saturation)

---

## 📝 Historique des décisions

| Date | Décision | Rationale |
|---|---|---|
| 18/04/2026 | Circuit breaker à 5 erreurs consécutives | mail.message avait fait 109 erreurs silencieuses sur 200 batches ratés |
| 18/04/2026 | `MODEL_RECORD_LIMITS` pour plafonner | product.template = 133k articles, saturait la DB Railway (5 Go) |
| 19/04/2026 | Fix `error_message` → `error` dans cleanup_stale_runs | 4 runs fantômes en running pendant 18h à cause d'une colonne inexistante |
| 19/04/2026 | Troncature erreurs Odoo 500 → 5000 chars | Nom du champ coupable était après la coupure |
| 19/04/2026 | Retrait 3 champs `gb_*` des manifests P1 | Méthodes compute OpenFire cassées (CacheMiss) |
| 19/04/2026 | Bouton Stop avec option A (finit modèle courant) | Choix Guillaume : données cohérentes plutôt qu'arrêt brutal |
| 19/04/2026 | Scanner test 200 records avant scan complet | Éviter 1h30 d'attente pour découvrir un bug de manifest |
| 19/04/2026 | Dashboard 6 severities | Plus de faux rouges sur modèles limités volontairement ou graph-only |
| 19/04/2026 | Limite mail.tracking.value 10k → 25k | Couffrant a 22 850 trackings, besoin de tous |
| 19/04/2026 | product.template filtré sur devis+kits | 133k articles c'est 95% d'inutile ; on vectorise les articles métier |

---

**Fin du playbook.** À maintenir à jour à chaque nouveau branchement d'outil.
