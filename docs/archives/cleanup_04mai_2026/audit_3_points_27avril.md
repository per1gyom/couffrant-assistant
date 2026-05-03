# Audit nocturne — 3 points en suspens (26-27/04/2026)

> Investigation menée pendant que tu dormais. Rapport rédigé pour ton réveil.

## Résumé en 30 secondes

| # | Point | Statut |
|---|---|---|
| 1 | Bug `indexed_in_graph` | ✅ **Fix qui marche** : 196/209 conversations indexées en 1h. **MAIS** anomalie résiduelle découverte (0 edges) |
| 2 | Mystère fichiers fantômes | 🟡 **Cause probable identifiée** mais pas avec certitude absolue |
| 3 | Erreur "did not match the expected pattern" | ✅ **Fix correct, propre** + audit confirme aucun bug similaire ailleurs |

État prod fin de session : pool DB sain (0 zombie), Phase B fonctionnelle, app stable.

---

## Point 1 — Bug `am.indexed_in_graph does not exist`

### Contexte
Erreur en boucle dans les logs Railway depuis le 21/04 (~5 jours). Job `graph_indexer` plantait toutes les 3 minutes sans pouvoir indexer aucune conversation. Cause racine : la fonction `ensure_schema()` qui devait créer les colonnes était à l'intérieur de `run_batch()`, lui-même bloqué par `should_run_batch()` qui plantait sur la colonne manquante. Cycle fermé architecturalement.

### Fix appliqué (commit `4c94f0f`, ce soir)
- Migrations `M-G01` et `M-G02` ajoutées dans `app/database_migrations.py` (création des 2 colonnes + 1 index partiel au démarrage de l'app)
- Suppression de `ensure_schema()` dans `graph_indexer.py` (devenu redondant)
- Source unique de vérité au niveau application

### Validation post-déploiement (mesurée à 23h32, soit ~1h après le push)

| Indicateur | Avant fix | Après 1h |
|---|---|---|
| Conversations indexées | 0 | 196 |
| Conversations en attente | 209 | 13 |
| Nœuds Conversation dans le graphe | 0 | 196 |
| Erreurs `column does not exist` dans logs | toutes les 3 min | aucune |
| Pool DB | sain | sain (0 zombie) |

**Le job rattrape son retard à un rythme d'environ 196 conversations en 1h, soit ~3 par cycle de 3 min.** Les 13 conversations restantes seront indexées dans les ~12 prochaines minutes.

### ⚠️ Anomalie résiduelle découverte

**Les 196 nœuds Conversation sont créés, MAIS il y a 0 edges `mentioned_in` dans le graphe.**

Or le rôle principal du `graph_indexer` (selon le commentaire de tête du fichier) est précisément de connecter les conversations aux **entités citées** (clients, devis, etc.) via ces edges `mentioned_in`. Sans ces edges, on a juste une liste de conversations stockées dans le graphe, sans aucun lien vers le reste — donc les recherches `search_graph("Legroux")` ne remontent toujours pas les conversations passées.

**Hypothèse** : la fonction `_extract_entity_keys()` ne trouve pas d'entités, ou l'API d'écriture des edges plante silencieusement. Le code dans `index_conversation()` log juste `logger.debug(...)` quand un lien échoue (pas WARNING) donc on ne le voit pas dans les logs Railway.

**Ce qu'il faudrait faire** : investiguer pourquoi 0 edges. Probablement 30 min à 1h de travail :
1. Lancer `index_conversation()` manuellement sur une conversation typique
2. Vérifier la sortie de `_extract_entity_keys()`
3. Regarder si les entités existent bien dans `semantic_graph_nodes`
4. Tester l'appel `add_edge()` directement

**Recommandation** : à mettre en priorité 2 dans `a_faire.md` (pas critique mais ça affaiblit un fonctionnement qu'on croit OK).

---

## Point 2 — Mystère des fichiers fantômes `.md`

### Contexte
3 fichiers (`docs/raya_changelog.md`, `docs/audit_isolation_25avril_complementaire.md`, `docs/checklist_isolation_multitenant.md`) apparaissent régulièrement comme **modifiés** dans `git status`, sans qu'on les ait touchés. Diff réel : quelques caractères (1 à 100) sur des fichiers de 14k-26k caractères → cosmétique pur (encoding/normalisation).

### Hypothèses initiales investiguées et **ÉCARTÉES** ce soir

| # | Hypothèse | Test | Résultat |
|---|---|---|---|
| H1 | OneDrive Microsoft sync | Vérification du chemin réel du projet | ❌ Le projet est à `~/couffrant-assistant/`, pas dans OneDrive |
| H2 | iCloud Drive sync sur `~/Documents/` | `xattr -l` sur le dossier projet | ❌ Aucun attribut `file-provider-domain-id` |
| H3 | Process périodique externe | `fswatch` 5 min sans intervention | ❌ Aucune modification détectée |
| H4 | Auto-save VS Code/Cursor | Test `Cmd+S` Safari sans activité | ❌ Rien ne se déclenche |
| H5 | `edit_block` fuzzy match | Re-occurrence ce soir avec **uniquement** des `start_process` Python | ❌ Apparu même sans edit_block |
| H6 | Configuration git autocrlf/autoeol | `git config --get-all core.autocrlf` | ❌ Non défini, valeur par défaut |
| H7 | Filter git via `.gitattributes` | `cat .gitattributes` | ❌ Fichier inexistant |

### 🎯 Hypothèse forte (probable mais non certifiée)

**Claude Desktop App garde un nombre anormal de file descriptors ouverts** sur les fichiers du projet.

#### Preuve
La commande `lsof +D /Users/per1guillaume/couffrant-assistant` montre que l'app Claude Desktop (PID 69988) garde simultanément plus de 20 handles `r` (read) ouverts sur des fichiers comme `user_settings.html`, sans jamais les fermer. Pareil pour les `.md` du dossier `docs/` (`README.md`, `plan_resilience_et_securite.md`, `a_faire.md` ont chacun 6 handles ouverts simultanément).

#### Mécanisme suspecté
Quand Claude Desktop ouvre un fichier pour le lire (par exemple via le tool `read_multiple_files` ou similaire), il :
1. Ouvre un nouveau file descriptor
2. Lit le contenu
3. **Ne ferme pas correctement** le descriptor

Au fil de la session, des dizaines de handles s'accumulent. Et il existe possiblement une routine périodique côté Claude Desktop qui :
- Vérifie l'état des fichiers ouverts
- Détecte des "drifts" entre son cache interne et le disque
- **Réécrit** silencieusement le fichier pour normaliser (encoding, fin de ligne, etc.)

C'est une routine bénéfique en théorie (cache cohérent) mais qui **modifie l'mtime** et provoque des micro-changements visibles dans `git status`.

### Pourquoi ce ne sont QUE ces 3 fichiers ?

Les 3 fichiers fantômes ont en commun d'être **les plus volumineux et les plus modifiés** récemment :
- `raya_changelog.md` : 17 965 octets, modifié à toutes les sessions
- `audit_isolation_25avril_complementaire.md` : 31 991 octets, lu/modifié plusieurs fois ce week-end
- `checklist_isolation_multitenant.md` : 7 101 octets, idem

Plus un fichier est lu/modifié, plus Claude Desktop accumule de handles dessus, plus la probabilité d'un "rebalance" est élevée.

### Comment confirmer (si tu veux trancher définitivement)

Méthode scientifique : laisser tourner `fswatch` sur le dossier `docs/` pendant **plusieurs heures** avec Claude Desktop ouvert mais sans interaction utilisateur, et logger TOUS les events. Si on capture une modification spontanée, on aura la timestamp et on pourra corréler avec les logs de Claude Desktop. ~30 min à mettre en place + ~2h d'observation.

### Solutions possibles (par ordre de robustesse)

| Option | Effort | Efficacité |
|---|---|---|
| **A**. Quitter complètement Claude Desktop (Cmd+Q) entre les sessions | 0 | Devrait éliminer les handles persistants |
| **B**. Restart Claude Desktop avant chaque session de code | 5 sec | Repart à zéro |
| **C**. Rapporter le bug à Anthropic via le bouton thumbs-down | 2 min | Long terme, mais c'est la vraie correction |
| **D**. Ajouter un `.gitattributes` qui force l'encoding/eof normalisé | 5 min | Pansement : git ignorera les diffs cosmétiques |

**Recommandation** : combiner **A + C**. Quitter Claude Desktop chaque soir, et signaler le bug à Anthropic.

### À noter — c'est inoffensif fonctionnellement

Les fantômes ne **cassent rien** :
- Le contenu réel des fichiers est toujours préservé
- Tu peux `git checkout HEAD -- docs/...` à tout moment pour annuler
- Les commits poussés en prod n'ont jamais inclus de fantômes

Le seul "coût" est l'agacement et les 5 secondes que prend de revert le diff fantôme avant un commit.

---

## Point 3 — "The string did not match the expected pattern"

### Contexte
Bug visible dans l'onglet Équipe à 21h22 ce soir. L'erreur JS native opaque cachait un crash serveur 500 sur l'endpoint `GET /admin/tenants/{tenant_id}/quota`.

### Diagnostic et fix (commit `bcccc4a` puis `a05c363`)
1. **Instrumentation diagnostique** ajoutée dans `loadTeamData()` pour exposer le vrai code HTTP et le body de la réponse → screenshot a montré `[quota] HTTP 500 : Internal Server Error`
2. **Cause racine identifiée** : `app/routes/admin/super_admin.py` utilisait `SCOPE_ADMIN` et `SCOPE_SUPER_ADMIN` ligne 246 sans les avoir importés en haut du fichier → `NameError` → 500
3. **Fix** : ajouter les 2 constantes dans la liste d'imports

### Audit de robustesse (que je viens de faire à 23h)

J'ai cherché si **d'autres endpoints** récents (créés ce soir) ont le **même pattern de bug** : utilisation de `SCOPE_ADMIN`/`SCOPE_SUPER_ADMIN` sans import explicite.

**Méthode** : pour chaque fichier sous `app/routes/`, comparer la liste des constantes `SCOPE_*` utilisées dans le code avec la liste des imports.

#### Résultats

✅ **Aucun fichier ne reproduit le même bug.** Tous les fichiers qui utilisent `SCOPE_ADMIN`, `SCOPE_SUPER_ADMIN`, `SCOPE_TENANT_ADMIN`, `SCOPE_USER` les importent correctement.

Détail des fichiers vérifiés :
- `app/routes/admin/super_admin.py` ✅ (corrigé ce soir, fonctionne)
- `app/routes/admin/super_admin_users.py` ✅ (importe SCOPE_SUPER_ADMIN ligne 39)
- `app/routes/admin/tenant_admin.py` ✅ (importe SCOPE_TENANT_ADMIN, SCOPE_CS, SCOPE_USER)
- `app/routes/admin/profile.py` ✅ (n'utilise pas de SCOPE_*)
- `app/routes/deps.py` ✅ (importe tout depuis `app_security`)

### Observation positive

L'**instrumentation diagnostique** ajoutée dans `loadTeamData()` (commit `bcccc4a`) est **toujours en place** et restera utile pour tout futur bug réseau dans l'onglet Équipe. Trois améliorations notables vs avant :
1. Helper `_teamFetchJson(url, label)` qui distingue erreur réseau / erreur HTTP / JSON invalide
2. Affichage de l'erreur en monospace avec stack lisible (au lieu d'un message JS opaque)
3. `console.error(...)` en plus pour DevTools

### Bonus — pattern à généraliser

Ce qu'on a appris ce soir : quand FastAPI rencontre une `NameError` à l'exécution d'un endpoint, il retourne un **HTTP 500 avec body HTML** au lieu d'un body JSON. Côté client, `r.json()` plante avec un message JS opaque ("did not match the expected pattern"). C'est un pattern **classique** des bugs cachés derrière une UX de mauvaise qualité.

**Suggestion** : appliquer le même pattern d'instrumentation (`_xxxFetchJson(url, label)`) aux autres pages qui font plusieurs `fetch()` en parallèle. Notamment dans `admin_panel.html` et `tenant/panel.html`. Effort : ~30 min par page.

À noter pour `a_faire.md` en priorité 4 (qualité de vie dev).

---

## 🎯 Synthèse des actions à mener

### Court terme (cette semaine)
1. **🟢 Investiguer pourquoi 0 edges `mentioned_in`** dans le graphe (Point 1 anomalie). 30 min - 1h. Priorité moyenne.
2. **🟢 Quitter Claude Desktop entre sessions** (Point 2 mitigation A). 0 effort, prendre l'habitude.
3. **🟢 Rapporter à Anthropic le bug fd handles** (Point 2 long terme C). 2 min via thumbs-down.

### Moyen terme (semaine prochaine ou plus tard)
4. **🟡 Étendre l'instrumentation `_teamFetchJson` aux autres pages** (Point 3 bonus). 30 min/page.
5. **🟡 Décider du déplacement du projet** vers `~/Code/Saiyan-ai/` ou non (le sync cloud n'est PAS la cause des fantômes, donc moins urgent qu'on pensait).

### Pas pressé
6. **🔵 Renommage Raya → Saiyan / raya-ia.fr → saiyan-ai** (gros chantier dédié, voir prochaine session)
7. **🔵 Nettoyer le vieux dossier obsolète** `~/Documents/couffrant-assistant/` (5 jours de retard, branche pas à jour). Bon ménage.

---

## État final mesuré (23h45)

| Système | État |
|---|---|
| Pool DB | 3 connexions, 0 zombie |
| Tenants | couffrant_solar 5/5, juillet 1/1 |
| aria_memory | 209 conversations totales, 196 indexées dans graphe |
| Job graph_indexer | Fonctionnel, ne plante plus |
| Onglet Équipe | Fonctionnel (validé par screenshot 22h05) |
| App.raya-ia.fr | Stable |

**Tu peux dormir tranquille. L'app est en bon état.**

Bonne nuit. 🌙

— Claude
