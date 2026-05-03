# Audit complet du système de graphes — 27 avril 2026

> Audit en lecture seule, ~45 min d'investigation, AUCUN code modifié.
> Objectif : comprendre l'état actuel avant toute action structurelle.

## Résumé en 30 secondes

Le projet a **deux systèmes de graphe** qui coexistent en parallèle. **Le V1 est mort depuis le 17 avril** (10 jours sans écriture) mais 2 fichiers continuent à le LIRE → données obsolètes injectées dans Raya. **Le V2 est vivant et bien peuplé** (5643 nœuds, 6007 arêtes). Le `graph_indexer` qu'on a fixé ce soir écrit dans le V2 mais ne sait pas raccrocher les conversations aux entités existantes (0 lien créé sur 196 conversations indexées) parce qu'il **utilise la mauvaise API**.

**Action minimale durable** : fixer le `graph_indexer` pour utiliser l'API existante `find_nodes_by_label()` + débrancher les 2 lectures restantes du V1 → V2.

**Action complète** : décommissionner V1 propre + nettoyer la dette architecturale.

---

## 🗺️ Cartographie complète

### Tables en base de données

| Table | Lignes (couffrant_solar) | Première écriture | Dernière écriture | Verdict |
|---|---|---|---|---|
| `entity_links` (V1) | 1367 | 17/04 15h19 | **17/04 22h49** | 🪦 **MORT** depuis 10 jours |
| `semantic_graph_nodes` (V2) | 5643 | 18/04 08h32 | 27/04 11h35 | ✅ Vivant |
| `semantic_graph_edges` (V2) | 6007 | 18/04 08h32 | 27/04 11h35 | ✅ Vivant |

### Modules Python

| Module | Système | Rôle |
|---|---|---|
| `app/entity_graph.py` | V1 | API et peuplement de la V1. Plus appelé en écriture. |
| `app/semantic_graph.py` | V2 | API et helpers V2 (`add_node`, `add_edge`, `find_node_id`, `find_nodes_by_label`, `traverse`, `get_context_around`) |
| `app/jobs/odoo_vectorize.py` | V2 | Peuple V2 depuis Odoo (Person, Company, Deal, Lead, Event, Product) |
| `app/jobs/drive_scanner.py` | V2 | Peuple V2 depuis OneDrive/SharePoint (File, Folder) |
| `app/scanner/processor.py` | V2 | Peuple V2 depuis le scanner universel |
| `app/jobs/graph_indexer.py` | V2 (mais utilise V1 via `_extract_entity_keys`) | Indexe les Conversations + tente de les lier aux entités |
| `app/retrieval.py` | V2 | Lit V2 (`find_node_id`, `traverse`) |
| `app/routes/aria_context.py` | **V1** | ⚠️ Lit `entity_links` (mort) via `build_team_roster_block` et `get_entity_context_text` |
| `app/routes/admin/super_admin_system.py` | V1 + V2 | Endpoints d'admin (peuplement manuel V1, comptage V2) |

---

## 📐 Architecture des deux systèmes

### V1 — `entity_links` (l'ancienne)

```
entity_links
  id, tenant_id
  entity_type      ← 'contact', 'company', 'project', 'team_member'
  entity_key       ← 'coullet-francine' (slug du nom)
  entity_name      ← 'Coullet Francine' (nom affiché)
  resource_type    ← 'invoice', 'order', 'mail', 'lead', 'task', ...
  resource_id      ← id de la ressource dans la source
  resource_source  ← 'odoo', 'gmail', 'outlook', 'sharepoint'
  resource_label   ← description courte
  resource_data    ← JSON avec les détails
```

**Modèle** : "table plate" ou "liste enrichie". Une entité peut avoir N ressources qui lui sont rattachées. Pas de lien entre entités. Pas de typage strict. Format de clé arbitraire (slug).

**Avantages** : simple, rapide à requêter, facile à comprendre.
**Limites** : pas de relations cross-entités (Francine ↔ son entreprise), pas de traversée multi-hop, pas de score de confiance, pas de versioning.

### V2 — `semantic_graph_nodes` + `semantic_graph_edges` (la nouvelle)

```
semantic_graph_nodes
  id, tenant_id
  node_type        ← 'Person', 'Company', 'Deal', 'Lead', 'Event', 'Product', 'File', 'Folder', 'Conversation'
  node_key         ← 'odoo-partner-3795' (clé technique stable)
  node_label       ← 'Coullet Francine' (nom humain)
  node_properties  ← JSON
  source           ← 'odoo', 'drive', 'aria_memory', ...
  source_record_id ← id dans la source

semantic_graph_edges
  id, tenant_id
  edge_from, edge_to  ← FK vers semantic_graph_nodes.id
  edge_type           ← 'parent_of', 'has_line', 'contact_of', 'partner_of', 'mentioned_in', ...
  edge_confidence     ← 0.0 à 1.0
  edge_source         ← 'explicit_source', 'llm_inferred', 'manual'
  edge_metadata       ← JSON
```

**Modèle** : graphe typé (nodes + edges). Permet de représenter "Francine est la conjointe de Jacques qui est contact_of de l'entreprise X qui a 3 devis dont D2600374".

**Avantages** : sémantique riche, traversée multi-hop (`get_context_around("Francine", max_hops=2)` ramène tout le contexte), score de confiance pour distinguer faits vs hypothèses LLM, source-agnostique.
**Limites** : plus complexe à requêter, exige discipline sur les `node_type` et `edge_type`.

---

## 🚨 Les 4 problèmes structurels identifiés

### Problème 1 — Le V1 est zombie : mort en écriture mais vivant en lecture

`entity_links` a reçu sa dernière écriture le **17 avril 22h49**. Personne ne le peuple plus. **Mais 2 fichiers continuent à le LIRE** :

- `app/routes/aria_context.py:264` — `build_team_roster_block()` pour injecter "ÉQUIPE INTERNE" dans le prompt système de Raya
- `app/routes/aria_context.py:337` — `get_entity_context_text()` pour injecter le contexte d'une entité mentionnée

**Conséquence concrète** : quand Raya cherche le contexte de "Francine Coullet", elle reçoit les données **figées au 17 avril**. Si Francine a payé une facture le 25 avril, Raya ne le sait pas (sauf si elle re-questionne Odoo en LIVE). Si l'équipe a changé (ajout/retrait), Raya hallucine sur l'ancien roster.

**Impact** : silencieux, mais **dégrade les réponses de Raya quotidiennement** depuis 10 jours.

### Problème 2 — Le `graph_indexer` n'utilise pas l'API qu'il faudrait

Le `graph_indexer` extrait des mots des conversations ("Francine Coullet", "Renoult"…) et tente de les **matcher comme `node_key`**. Or les `node_key` du V2 ont un format technique (`odoo-partner-3795`, `drive-file-XXXX`).

**Résultat mesuré** : 196 conversations indexées, **0 lien créé sur les 67 mots extraits** (échantillon de 5 conversations).

**Mais** : le module `app/semantic_graph.py` propose **déjà** la fonction `find_nodes_by_label()` qui fait exactement ce qu'il faudrait (recherche par `node_label` plutôt que par `node_key`). Le `graph_indexer` ne l'utilise simplement pas.

**Cause probable** : le `graph_indexer` a été écrit le 21 avril en réutilisant le pattern de `_extract_entity_keys` (= API V1) sans réaliser que pour V2 il fallait `find_nodes_by_label`.

### Problème 3 — Dépendance V1 cachée dans le `graph_indexer`

Pire : le `graph_indexer` (V2) **importe encore** une fonction de `entity_graph.py` (V1) :

```python
# app/jobs/graph_indexer.py:157
from app.entity_graph import _extract_entity_keys
```

Si on supprime `entity_graph.py` un jour, le `graph_indexer` plante. C'est un couplage fragile entre l'ancienne et la nouvelle architecture.

### Problème 4 — Pas de doc sur la migration V1 → V2

Le doc `raya_memory_architecture.md` (18 avril) décrit la cible (V2) mais **ne mentionne pas la V1 ni la stratégie de migration**. Du coup pendant 10 jours, deux systèmes ont coexisté sans plan de transition formalisé. C'est ce qui explique les angles morts ci-dessus.

---

## 📊 État chiffré du V2 aujourd'hui

### Nœuds dans `semantic_graph_nodes` (couffrant_solar)

| Type | Count | Source |
|---|---|---|
| File | 3239 | Drive (peuplé le 20/04) |
| Person | 912 | Odoo (peuplé le 18/04) |
| Folder | 314 | Drive (peuplé le 20/04) |
| Deal | 310 | Odoo (peuplé le 18/04) |
| Event | 300 | Odoo (peuplé le 18/04) |
| Conversation | 196 | aria_memory (peuplé le 26/04 ce soir) |
| Product | 145 | Odoo (peuplé le 18/04) |
| Lead | 139 | Odoo (peuplé le 18/04) |
| Company | 88 | Odoo (peuplé le 18/04) |

⚠️ **Tout (sauf les Conversation) est figé aux 18-20 avril.** Pas de re-rafraîchissement programmé. Les nouveautés Odoo et Drive depuis 9 jours ne sont pas dans le graphe.

### Arêtes dans `semantic_graph_edges` (couffrant_solar)

| Type | Count | Sens |
|---|---|---|
| `contains` | 3524 | Folder → File |
| `has_line` | 1600 | Deal → ses lignes (sale.order.line) |
| `scheduled_for` | 451 | Event → Person/Deal |
| `partner_of` | 337 | Person → Company |
| `contact_of` | 95 | Person → Company |
| `mentioned_in` | **0** | Conversation → entité (objet du `graph_indexer`) |

---

## 🎯 Trois architectures cibles possibles

### Option A — Fix minimal et tactique (~1h)

**But** : fixer les bugs identifiés sans refonte structurelle.

1. **Modifier `graph_indexer.py`** pour utiliser `find_nodes_by_label()` au lieu de `_extract_entity_keys` + recherche par `node_key`. Le matching cherche par label, prend les top 5, crée les edges `mentioned_in`.
2. **Reset des 196 conversations** (`indexed_in_graph = false`) pour qu'elles soient ré-indexées avec les liens.
3. **Migrer `aria_context.py`** des 2 lectures V1 → V2 :
   - `build_team_roster_block()` → lire `node_type='Person'` avec `source_record_id` indiquant un team_member
   - `get_entity_context_text()` → utiliser `get_context_around()` du V2

**Avantages** :
- Rapide
- Résout le problème immédiat (Raya retrouve enfin les conversations passées)
- Débranche les lectures du V1 mort

**Limites** :
- N'aborde pas le problème de fraîcheur (V2 figé au 18-20 avril)
- Garde V1 zombie en base (1367 lignes inutilisées)
- Garde le couplage `entity_graph.py` ↔ `graph_indexer.py`

### Option B — Décommissionnement V1 complet (~3-4h)

**But** : supprimer V1 proprement et migrer toute logique vers V2.

1. Toutes les actions de l'Option A, plus :
2. **Audit fonctionnel de `populate_from_odoo()`** dans `entity_graph.py` pour voir si quelque chose y est fait que `odoo_vectorize.py` ne fait pas. Si oui, le porter dans V2.
3. **Migration des données** : créer un script qui lit `entity_links` et insère dans `semantic_graph_nodes`/`edges` ce qui n'existe pas déjà. Optionnel : on peut aussi décider que V2 a déjà tout ce qu'il faut et qu'on peut juste droper V1.
4. **Suppression de `entity_graph.py`** et des imports.
5. **Drop de la table `entity_links`** (migration M-X01) ou archivage.
6. **Suppression des endpoints V1 de `super_admin_system.py`** (ou redirection vers V2).

**Avantages** :
- Source unique de vérité
- Plus de dette architecturale
- Plus de risque que quelqu'un peuple V1 par erreur dans le futur

**Limites** :
- Plus long
- Risque de casser des trucs en supprimant `entity_graph.py` (à auditer avant)

### Option C — Refonte cible : V2 + rafraîchissement périodique (~1-2 jours)

**But** : Option B + résoudre le problème de fraîcheur du V2.

1. Toutes les actions de l'Option B, plus :
2. **Job `graph_refresh`** programmé toutes les heures qui appelle `odoo_vectorize.run_full()` pour re-peupler V2 depuis Odoo. Aujourd'hui, ce job existe mais n'est pas dans le scheduler (il faut vérifier).
3. **Suppression des nœuds orphelins** (entité qui n'existe plus dans Odoo) via une routine de nettoyage hebdomadaire.
4. **Tests de cohérence** : un job qui compare les counts entre Odoo (live) et V2 (cache) et alerte si écart > 5%.
5. **Documentation à jour** : compléter `raya_memory_architecture.md` avec le statut "V1 supprimé, V2 = source unique" + diagrammes.
6. **Mise à jour `docs/a_faire.md`** avec le nouveau modèle.

**Avantages** :
- Architecture vraiment durable
- Raya a toujours des données fraîches
- Documentation à jour
- Confiance retrouvée dans le système

**Limites** :
- Le plus long
- Demande de réfléchir à la fréquence de refresh (compromis fraîcheur/coût Odoo API)

---

## 💡 Ma recommandation

**Option C en 3 étapes étalées** :

1. **Maintenant ce soir** (~30 min) : faire l'Option A (fix tactique). Au moins, le `graph_indexer` marche, Raya retrouve les conversations passées, les lectures V1 sont débranchées. C'est durable même si on ne fait pas la suite.

2. **Demain ou prochaine session** (~1-2h) : compléter avec l'Option B (décommissionnement V1). Code plus propre, dette technique réduite.

3. **Plus tard, dédié** (~1 jour) : compléter avec l'Option C (rafraîchissement V2). C'est un sujet à part qui mérite une session dédiée pour bien réfléchir aux fréquences et au coût Odoo.

Pourquoi ce séquencement : **chaque étape laisse le système dans un état cohérent et meilleur que la précédente**. Si on s'arrête après l'étape 1, on a déjà résolu le problème immédiat. Si on va jusqu'à 2, on a un système propre. Si on va jusqu'à 3, on a un système durable et frais.

Ce que je veux **éviter à tout prix** : une refonte big-bang d'un jour entier qui mélange tout et qui casse des choses qu'on n'avait pas anticipées. Petits pas, validés à chaque étape.

---

## 🗒️ Annexes

### Annexe A — Sample de désaccords entre V1 et V2 (Francine Coullet)

**Dans V1 (`entity_links`)** :
```
entity_key='francinecoullet41@gmail.com'  entity_name='Coullet Francine'
entity_key='coullet-francine'             entity_name='Coullet Francine' (×9)
```

**Dans V2 (`semantic_graph_nodes`)** :
```
[Person]  node_key='odoo-partner-3795'  node_label='Coullet Francine'
[Person]  node_key='odoo-partner-3643'  node_label='Coullet Francine'
[Event]   node_key='odoo-event-1340'    node_label='Coullet Francine 41200 Villeherviers'
[Event]   node_key='odoo-event-1300'    node_label='Coullet Francine 41200 Villeherviers'
[Folder]  node_key='drive-folder-...'   node_label='Coullet (Les Amis du Glandier)'
[File]    node_key='drive-file-...'     node_label='PV - Visite technique - Coullet Francine - 2026-01'
```

→ **V2 a beaucoup plus de richesse**. C'est lui qu'il faut servir à Raya.

### Annexe B — Endpoints d'admin liés aux graphes

`super_admin_system.py` a plusieurs endpoints utiles pour debugger :
- `populate_from_odoo` (V1) — ne sert plus à rien
- `populate_from_drive`, `populate_from_calendar`, `populate_from_contacts` (V1) — idem
- `count_graph` (V2) — utile, à garder
- `find_nodes_by_label`, `get_neighbors` (V2) — utile, à garder

### Annexe C — Fonctions inutilisées dans `entity_graph.py` (candidates à la suppression)

À supprimer en Option B :
- `link_entity()` — plus appelée nulle part en écriture
- `populate_from_odoo()` — désactivée
- `populate_from_mail_memory()` — désactivée
- `populate_from_drive()` — désactivée
- `populate_from_calendar()` — désactivée
- `populate_from_contacts()` — désactivée

À conserver (encore lues) puis migrer :
- `_extract_entity_keys()` — utilisée par `graph_indexer.py`. À déplacer ou supprimer après fix de `graph_indexer`.
- `normalize_key()` — peut servir, à conserver dans une util commune.
- `build_team_roster_block()` — à migrer V2.
- `get_entity_context_text()` — à migrer V2.

---

**Document écrit le 27 avril 2026 à 12h30 par Claude.**
**Prochaine action : décision Guillaume sur l'Option A/B/C, puis exécution étape 1.**
