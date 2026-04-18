# 🧠 Architecture Mémoire de Raya — Modèle de Référence Universel

**Version** : 1.0
**Date création** : 18 avril 2026
**Statut** : RÈGLE ARCHITECTURALE FONDAMENTALE — à appliquer à toute nouvelle
connexion de Raya (Odoo, Drive, Gmail, SharePoint, Teams, futures intégrations
WhatsApp/Signal/ERP/CRM/etc.)

---

## 📐 Principe directeur

Pour chaque outil ou source de données auquel Raya est connectée, **4 couches
coexistent systématiquement**. Aucune nouvelle source n'est considérée comme
"intégrée" à Raya tant que les 4 couches ne sont pas implémentées.

L'objectif est que Raya ait une **compréhension sémantique complète** de l'activité
de l'utilisateur, pas juste un accès factuel aux données. Elle doit pouvoir faire
des connexions transversales (matériel, contacts, projets, commentaires), détecter
des patterns, anticiper des besoins — comme un humain qui aurait une mémoire
parfaite et réfléchirait plus vite.


---

## 🏛️ Les 4 couches

### Couche 1 — Accès LIVE (temps réel)

**Rôle** : requêtes directes vers la source au moment de la question, pour les
données factuelles précises qui peuvent avoir changé dans la dernière seconde.

**Fraîcheur** : absolue (lecture à la demande).

**Exemples** :
- Odoo : `CLIENT_360`, `ODOO_SEARCH`, `ODOO_MODELS`
- Gmail/Outlook : lecture live + webhook push
- Drive : `drive_fetch`, `drive_search`
- Teams : lecture live + webhooks Microsoft

**Règle** : **toujours la source de vérité pour les montants, dates, états, contenus
exacts**. Ne jamais servir une donnée financière ou opérationnelle depuis le cache.

---

### Couche 2 — Graphe sémantique typé

**Rôle** : cache structurel local qui stocke les **nœuds** (entités) et les
**arêtes** (liaisons entre entités) avec typage explicite et score de confiance.
Permet la navigation rapide et la mise en évidence de liens transversaux que la
source elle-même ne modélise pas.

**Schéma de stockage** :

Table `semantic_graph` (universelle, pas par source) :
- **Nœuds** : `node_id`, `node_type`, `node_key`, `node_properties (jsonb)`,
  `tenant_id`, `source` ('odoo'/'gmail'/'drive'/...)
- **Arêtes** : `edge_id`, `edge_from`, `edge_to`, `edge_type`, `edge_confidence`
  (0.0-1.0), `edge_source` ('explicit_source'/'llm_inferred'/'manual'),
  `edge_metadata (jsonb)`, `tenant_id`

**Types de nœuds** : `Person`, `Company`, `Project`, `Product`, `Deal` (devis),
`Invoice`, `Payment`, `Event`, `Document`, `Mail`, `Ticket`, `Task`.

**Types d'arêtes** :
- *Explicites* (issues de la source) : `parent_id`, `partner_of`, `contact_of`,
  `has_line`, `has_invoice`, `has_payment`, `mentioned_in`, `assigned_to`
- *Implicites* (déduites par LLM) : `spouse_of`, `colleague_of`, `works_on`,
  `installed_on`, `replaces`, `follow_up_of`

**Traversée multi-hop** : fonction `traverse(start_node, max_hops=3, filter_types=[])`
qui ramène tous les nœuds accessibles dans un rayon de N sauts, utilisable pour
remonter "Francine → spouse_of → Jacques → contact_of → Les Amis du Glandier →
has_deals → 2 devis".

**Fraîcheur** : proche temps réel via webhooks ; sync nocturne en filet de sécurité.

---

### Couche 3 — Vectorisation sémantique + recherche hybrid

**Rôle** : embeddings de **tous les champs texte pertinents** de la source (notes,
descriptions, commentaires, historique, corps de mails, contenu documents), couplés
à une recherche hybrid dense + sparse pour retrouver l'information par SENS ET par
terme exact.

**Stack technique** :
- **Embeddings** : OpenAI `text-embedding-3-small` à 1536 dimensions (cohérence
  cross-sources, coût négligeable, qualité largement suffisante pour l'usage métier
  PME)
- **Stockage dense** : colonne `embedding vector(1536)` avec index HNSW cosine
- **Stockage sparse** : colonne `content_tsv tsvector` avec dictionnaire français
  et index GIN pour full-text search
- **Fusion** : Reciprocal Rank Fusion (k=60) des deux listes de résultats
- **Reranking** : Cohere `rerank-3-multilingual` en 2e étage sur les top 50
  candidats → top 10 finaux (+3-5 points de pertinence)

**Schéma de stockage** :

Une table dédiée par source majeure, toutes en 1536 dims pour permettre les
comparaisons cross-sources :
- `odoo_semantic_content` : contenu Odoo vectorisé (devis, lignes, events, tâches, commentaires)
- `mail_memory` (existant) : mails vectorisés
- `aria_memory` (existant) : conversations vectorisées
- `aria_contacts` (existant) : contacts vectorisés
- Futures : `drive_semantic_content`, `teams_semantic_content`, etc.

**Règle** : tout champ texte libre (note, description, commentaire, corps) d'une
source doit être vectorisé. Les champs structurés (IDs, montants, dates) ne le sont pas.

---

### Couche 4 — Surveillance proactive et actions dérivées

**Rôle** : jobs périodiques (ou webhooks) qui scannent les nouveautés et génèrent
des **signaux actionnables** pour Raya. Permet de passer d'un assistant réactif à
un assistant proactif.

**Mécanismes** :
- **Briefing matinal** (6h30 quotidien) : scan des events du jour + commentaires
  ajoutés depuis 24h + nouveaux devis + factures passant un seuil critique + mails
  urgents. Extraction des actions à faire via LLM.
- **Détection d'anomalies** : facture annulée le même jour qu'un impayé, dormance
  client > 180j, délai réponse devis > 15j, etc.
- **Propositions d'automatisation** : Raya repère un pattern répétitif et propose
  de l'automatiser (ex : "tu as envoyé 3 relances manuelles cette semaine, je peux
  automatiser ça ?")

**Règle** : chaque source doit avoir au moins un scanner proactif qui alimente le
briefing matinal.

---

## 🔄 Règles de rafraîchissement (cadence)

| Couche | Mécanisme principal | Filet de sécurité |
|---|---|---|
| 1 — LIVE | Lecture à la demande | Aucun nécessaire |
| 2 — Graphe | Webhooks (temps réel) | Sync incrémental nocturne 3h30 |
| 3 — Vectorisation | Webhooks (vectorisation async) | Sync incrémental nocturne 3h30 |
| 4 — Surveillance | CRON planifié (6h30 briefing, horaire détection) | N/A |

**Principe clé** : les données sont **toujours lues en live** (couche 1) pour les
questions factuelles. Le cache (couches 2 et 3) sert à la navigation rapide et à
la recherche sémantique. Si un webhook rate, le sync incrémental nocturne rattrape.

**Pas de polling fréquent en background** — les webhooks sont la règle, le sync
nocturne est juste un filet de sécurité.

---

## 🔌 Règles pour toute nouvelle source de données

Quand on intègre une nouvelle source (ex : ajouter un ERP X, un CRM Y, un messaging Z),
on applique systématiquement les 4 couches. Voici la checklist :

1. **Couche 1** : Coder un connecteur live (`{source}_connector.py`) avec les fonctions
   de recherche/lecture à la demande. Créer les tags ACTION correspondants dans le
   prompt système.

2. **Couche 2** : Étendre `populate_from_{source}` pour créer les nœuds et arêtes
   typés dans `semantic_graph` depuis les entités de la source. Identifier les
   arêtes explicites (issues de relations natives de la source).

3. **Couche 3** : Créer la table `{source}_semantic_content` avec colonnes embedding
   + tsvector. Implémenter `vectorize_{source}_record(record)` pour chaque type
   d'entité vectorisable. Créer l'indexation initiale en batch (`vectorize_{source}_initial`).

4. **Couche 4** : Créer au moins un scanner proactif dans `app/jobs/` qui alimente
   le briefing matinal avec les signaux issus de cette source.

5. **Mise à jour** : configurer les webhooks de la source vers Raya (endpoint
   `/webhooks/{source}/record-changed`). Ajouter la source au sync incrémental
   nocturne comme filet de sécurité.

6. **Recherche unifiée** : s'assurer que le tag `[ACTION:SEMANTIC_SEARCH:query]`
   peut chercher dans cette nouvelle source via hybrid search + rerank.

---

## 🎯 Pipeline d'une question utilisateur

Illustration complète de ce qui se passe quand Guillaume demande *"Topo sur
Francine Coullet qui est mariée à Jacques et liés au projet Les Amis du Glandier"*
ou *"Je prépare un devis avec un onduleur SE100K, qu'ai-je déjà fait avec ce
modèle ?"*.

```
┌───────────────────────────────────────────────────────────┐
│  QUESTION UTILISATEUR                                     │
└───────────────────────────────────────────────────────────┘
                        │
                        ▼
┌───────────────────────────────────────────────────────────┐
│  1. Recherche hybrid dense + sparse (couche 3)            │
│     → Top 50 candidats parmi TOUTES les sources           │
│       vectorisées (odoo, mails, conversations, contacts)  │
└───────────────────────────────────────────────────────────┘
                        │
                        ▼
┌───────────────────────────────────────────────────────────┐
│  2. Reranking Cohere sur les top 50 (couche 3)            │
│     → Top 10 finaux, classés par pertinence sémantique    │
└───────────────────────────────────────────────────────────┘
                        │
                        ▼
┌───────────────────────────────────────────────────────────┐
│  3. Traversée du graphe sémantique (couche 2)             │
│     → Pour chaque top 10, remonter les nœuds liés         │
│       (multi-hop jusqu'à 3 sauts)                         │
│     Ex : Francine → Jacques → Amis du Glandier → Devis    │
└───────────────────────────────────────────────────────────┘
                        │
                        ▼
┌───────────────────────────────────────────────────────────┐
│  4. Enrichissement live sur les entités remontées (c. 1)  │
│     → CLIENT_360 live sur les partners trouvés            │
│     → Données fraîches : montants, états, dates réels     │
└───────────────────────────────────────────────────────────┘
                        │
                        ▼
┌───────────────────────────────────────────────────────────┐
│  5. Synthèse par Raya (Claude Opus)                       │
│     → Réponse structurée exploitant TOUTES les liaisons   │
└───────────────────────────────────────────────────────────┘
```

---

## 📊 État d'application par source (au 18/04/2026)

| Source | Couche 1 (live) | Couche 2 (graphe) | Couche 3 (vecteur) | Couche 4 (proactif) |
|---|---|---|---|---|
| Odoo | ✅ CLIENT_360, SEARCH | 🔄 en cours (étape 2 OK, graphe typé en cours) | 🔄 en cours (cette journée) | 🔄 partiel (anomalies vue 360°) |
| Gmail | ✅ | ⚙️ via `link_mail_to_graph` | ✅ `mail_memory` | ✅ `gmail_polling` |
| Outlook | ✅ | ⚙️ partiel | ✅ `mail_memory` | ✅ webhook Microsoft |
| Drive | ✅ | ❌ à faire | ❌ à faire | ❌ à faire |
| Teams | ✅ | ❌ à faire | ⚙️ partiel (`teams_sync_state`) | ❌ à faire |
| Calendar | ✅ | ⚙️ partiel | ❌ à faire | ✅ briefing matinal |
| SharePoint | ✅ | ❌ à faire | ❌ à faire | ❌ à faire |

**Priorité de complétion** :
1. Odoo (cette journée) — bloquant pour les early adopters
2. Drive (semaine suivante) — contient beaucoup de contexte projet chez Guillaume
3. Teams (ensuite) — messaging interne équipe
4. Calendar (amélioration progressive)

---

## 🔧 Stack technique commune

**Base de données** : PostgreSQL avec extension `pgvector` (HNSW indexes pour
recherche vectorielle, GIN indexes pour tsvector).

**Embeddings** : OpenAI `text-embedding-3-small` à 1536 dimensions, via
`app/embedding.py`. Cohérent pour toutes les tables.

**Reranking** : Cohere `rerank-3-multilingual` via l'API, appelé uniquement sur
les top 50 candidats après fusion hybrid.

**Recherche hybrid** : module `app/retrieval.py` (à créer) avec fonction
`hybrid_search(query, sources=['odoo','mail','conversation'], filters={})` qui
fusionne dense + sparse via RRF, puis rerank.

**Graphe** : module `app/semantic_graph.py` (à créer) avec `add_node`, `add_edge`,
`traverse(start, max_hops, filter_types)`, `get_neighbors(node, edge_types)`.

**Webhooks** : endpoints FastAPI dans `app/routes/webhook_{source}.py`,
authentifiés par token secret, déclenchent vectorisation + mise à jour graphe
de manière asynchrone (thread background).

---

## 🎓 Justifications des choix (pour futures relectures)

### Pourquoi `text-embedding-3-small` et pas `large` ?

Le gain de `large` vs `small` sur MTEB est de +1.8 points (62.3 → 64.1), soit
**1-2% de gain réel de pertinence** sur les cas d'usage PME (noms propres,
termes techniques standards, français courant). Coût 6.5× supérieur.

Le vrai gain de pertinence vient **ailleurs** :
- Hybrid search (dense + BM25) : **+5 à 10 points**
- Reranking Cohere : **+3 à 5 points**
- Graphe sémantique typé : **débloque des cas impossibles** avec embeddings seuls

Priorité donc donnée à l'architecture de recherche plutôt qu'à la taille du
modèle d'embeddings.

### Pourquoi 1536 dims et pas 3072 ?

- Cohérence avec l'existant (7 tables déjà en 1536)
- Permet les comparaisons cross-sources (devis ↔ mails ↔ conversations)
- Gain qualité 3072 vs 1536 = +0.5 points MTEB seulement
- Stockage 2× plus léger, recherche 2× plus rapide

### Pourquoi OpenAI et pas voyage-3 ou BGE self-hosted ?

- OpenAI déjà en place, pas de nouveau SDK/secret
- Qualité multilingue française suffisante
- voyage-3-large donnerait +0.3 pt MTEB pour 1.4× le coût (marginal)
- BGE-M3 self-hosted demanderait GPU + infra (150-800€/mois) non justifié
- NV-Embed-v2 (meilleur MTEB) est sous licence non-commerciale (CC-BY-NC)

### Pourquoi pas de polling Odoo fréquent ?

Les données sont **toujours lues en live** via CLIENT_360 et ODOO_SEARCH. Le
graphe et les embeddings sont juste un cache pour la navigation sémantique.
Les webhooks (base_automation) suffisent pour garder le cache frais, avec sync
nocturne comme filet de sécurité.

Polling fréquent = gaspillage (99% des cycles retourneraient zéro changement).

---

## 📅 Historique des versions

- **v1.0** (18/04/2026) : Document fondateur, établi lors de la réflexion
  architecturale de la journée "chantier mémoire". Validé par Guillaume.
