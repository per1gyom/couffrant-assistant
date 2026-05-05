# Projet — Apprentissage hiérarchisé de Raya (Mini-Graphiti)

*Démarré le 05/05/2026 soir par Guillaume après l'incident règle 124.*
*Architecture validée le 05/05 soir : mini-Graphiti custom dans notre stack Postgres existante.*

---

## Contexte et déclencheur

Voir `raya_changelog.md`, session 05/05/2026 après-midi, point 6.

Résumé : la règle 124 datée du 17/04 disait *"boîte contact@ à connecter prochainement"*. Le 05/05 vers 17h, Guillaume reconnecte la boîte. Bien que `connected_mailboxes` (liste vivante) affichait correctement contact@ comme connectée, Raya a fait confiance à la règle 124 plutôt qu'à la donnée vivante. Symptôme d'un système où **toutes** les règles sont traitées de la même manière sans hiérarchie ni dimension temporelle.

---

## Vision (Guillaume)

> *Raya doit apprendre comme un humain le ferait, avec des priorisations d'importance et des notions différentes entre règle, information générale, information passagère, culture générale ou connaissance de son utilisateur. Pour la règle 124, elle aurait dû soit me dire qu'on avait évoqué de la connecter plus tard, soit me demander si elle est connectée maintenant, soit aller vérifier elle-même. Un humain dans la plupart du temps va être autonome et n'embêtera son responsable qu'en cas de doute sérieux ou de blocage.*

---

## État de l'art étudié (05/05/2026 soir)

Recherche menée sur 4 frameworks majeurs :

| Framework | Score LongMemEval | Architecture | Adapté à Raya ? |
|---|---|---|---|
| **Mem0 / Mem0g** | 49% | Vector DB + graphe optionnel, cloud | ❌ Faible sur le temporel, lock-in $249/mo |
| **Zep / Graphiti** | 63.8% | Knowledge graph temporel (Neo4j) | ⚠️ Lock-in cloud ou Neo4j à gérer |
| **Letta (ex-MemGPT)** | Moyen | Memory blocks éditables (Postgres + pgvector) | ⚠️ 42 tables, paradigme différent |
| **OMEGA** | 95.4% (auto-rapporté, méthodo douteuse) | SQLite local single-user | ❌ Inadapté multi-tenant SaaS |

**Conclusion** : adopter un framework existant = jeter notre stack (Postgres + semantic_graph_nodes 122k + aria_rules avec embedding). Construire un mini-Graphiti dans notre stack = bénéficier de l'existant + maîtrise totale + score attendu ~60-65% LongMemEval.

Le **bi-temporal model** de Graphiti et la **classification orthogonale type/temporal_class** d'OpenAI cookbook *"Temporal Agents with Knowledge Graphs"* sont les patterns adoptés.

---

## Architecture finale validée

### Dimension A — Type (qu'est-ce que c'est)

4 valeurs orthogonales à la temporalité :

| Valeur | Description | Exemple |
|---|---|---|
| `Fact` | Information objective sur le monde | "Charlotte est ma comptable", "siège à St Laurent" |
| `Preference` | Préférence du user | "j'aime les réponses courtes", "tutoiement" |
| `Behavior` | Règle de comportement Raya | "DELETE = action directe sans confirmation" |
| `Knowledge` | Culture métier / vocabulaire | "CONSUEL = certificat conformité", "TVA solaire = 10%" |

### Dimension B — Temporal class (comment ça vit dans le temps)

3 valeurs :

| Valeur | Description | Exemple |
|---|---|---|
| `Static` | Immuable, ne change quasi jamais | Date naissance, valeurs fondamentales |
| `Dynamic` | Peut évoluer, a une fin probable | "Charlotte en arrêt jusqu'en mai", "boîte à connecter" |
| `Atemporal` | Vrai sans cadre temporel | "CONSUEL = certificat", "Charlotte = compta" |

### Dimension C — Bi-temporal timestamps (quand c'est vrai)

4 timestamps (inspiré directement de Graphiti) :

| Colonne | Sens | Notre cas |
|---|---|---|
| `created_at` | Quand on a appris l'info (ingestion système) | déjà existant |
| `valid_at` | Quand l'info est devenue vraie dans le monde réel | NOUVEAU |
| `invalid_at` | Quand elle a cessé d'être vraie (NULL = encore vraie) | NOUVEAU |
| `active` (existant, = expired_at) | Suppression logique | déjà existant |

### Hiérarchie de priorisation à l'utilisation

Quand 2 sources contredisent au moment de répondre :

```
1. DONNÉE VIVANTE (connected_mailboxes, calendar, mail_memory récent)
   → toujours fait foi, jamais périmée
2. DÉCLARATION EXPLICITE RÉCENTE (< 7j) de l'utilisateur dans la conversation courante
3. Fact + Static + reinforced récemment + confidence haute
4. Behavior + reinforced + confidence haute
5. Fact + Dynamic + invalid_at IS NULL + valid_at récent
6. Knowledge (rarement contradictoire)
7. Fact + Static ancien jamais reinforced
8. Fact + Dynamic + invalid_at IS NOT NULL OU valid_at ancien
   → ne pas affirmer, soit vérifier via tool, soit demander à l'user
9. Inférence / hypothèse → toujours à confirmer
```

**Règle d'or pour le prompt système** :
> *"Si une info dans `<infos_a_confirmer>` ou une règle Dynamic ancienne contredit ce que tu vois dans `<donnees_vivantes>`, fais confiance aux données vivantes et marque l'info à mettre à jour. Si l'info est centrale à la réponse mais pas vérifiable par données vivantes, vérifie avant d'affirmer (via search_mail, list_connexions, etc.) ; ne demande à l'utilisateur qu'en dernier recours."*

---

## Pipeline de capture "RAG-before-write" (Phase 6)

Quand Raya capture une nouvelle règle :

1. **Recherche** des 5 règles existantes les plus proches (embedding + BM25 sur node_label)
2. **Appel LLM Sonnet** avec : nouvelle info + contexte conversation + 5 règles proches + invalidation prompt
3. **Décision LLM** :
   - `nouvelle` → INSERT avec type / temporal_class / valid_at / confidence
   - `mise_a_jour_id_X` → UPDATE de la règle X (texte fusionné)
   - `invalide_id_X` → UPDATE règle X avec `invalid_at = NOW`, et INSERT nouvelle règle
   - `doublon_id_X` → UPDATE `last_reinforced_at = NOW`, `confidence++`
   - `ephemere` → ignorer (info passagère utilisée une fois)
4. **Action** selon décision

**Coût estimé** : ~3000 tokens input + 500 output par capture. Sonnet : 0.017€ / capture. Pour 5 captures/jour → 2.5€/mois.

---

## Plan d'exécution en 8 phases

### 🟢 MVP minimum viable (~5h) — résout l'incident règle 124

#### Phase 1 — Schéma SQL (1h)

**Objectif** : ajouter les colonnes nécessaires sans casser l'existant.

```sql
-- Sur aria_rules
ALTER TABLE aria_rules ADD COLUMN type TEXT DEFAULT 'Fact';
ALTER TABLE aria_rules ADD COLUMN temporal_class TEXT DEFAULT 'Atemporal';
ALTER TABLE aria_rules ADD COLUMN valid_at TIMESTAMP DEFAULT NULL;
ALTER TABLE aria_rules ADD COLUMN invalid_at TIMESTAMP DEFAULT NULL;

-- Sur semantic_graph_edges (pour quand on poussera les règles dans le graphe)
ALTER TABLE semantic_graph_edges ADD COLUMN valid_at TIMESTAMP DEFAULT NULL;
ALTER TABLE semantic_graph_edges ADD COLUMN invalid_at TIMESTAMP DEFAULT NULL;

-- Index pour retrieval rapide (uniquement règles encore valides)
CREATE INDEX idx_aria_rules_active_valid ON aria_rules (type, temporal_class)
  WHERE active = true AND invalid_at IS NULL;
```

**Validation** : aucune régression sur les jobs existants (rules_optimizer, rules_pending_decisions).

#### Phase 2 — Reclassement Opus des 273 règles (2h)

**Objectif** : reclassifier toutes les règles existantes avec analyse fine.

Étapes :
1. Read all 273 rules
2. Pour chacune, Opus produit `type` + `temporal_class` + `valid_at` (à partir de `created_at` ou indices texte) + `invalid_at` si déjà obsolète
3. Output : un fichier SQL d'UPDATE
4. Review échantillonnage Guillaume sur 30 cas tirés au hasard
5. Apply

**Pourquoi Opus et pas Haiku** : erreur initiale lourde de conséquences. Capacité à voir des nuances (ex: "à connecter prochainement" → Dynamic et invalide aujourd'hui).

#### Phase 4 — Loader hiérarchisé (1h30)

**Objectif** : injecter le contexte de Raya en 4 blocs distincts au lieu d'un fourre-tout.

Modification de `aria_loaders.py` :

```
<connaissances_durables>     ← type IN ('Fact','Preference') AND temporal_class IN ('Static','Atemporal')
                                AND active=true AND invalid_at IS NULL
<infos_a_confirmer>          ← type='Fact' AND temporal_class='Dynamic'
                                AND active=true AND invalid_at IS NULL
                                MARQUER si valid_at < NOW - 30j (à reconfirmer)
<comportements>              ← type='Behavior' AND active=true AND invalid_at IS NULL
<culture_metier>             ← type='Knowledge' AND active=true AND invalid_at IS NULL
<donnees_vivantes>           ← inchangé (connected_mailboxes, etc.)
```

#### Phase 5 — Prompt système (30 min)

**Objectif** : ajouter la règle d'or et le réflexe de vérification.

Modification du system prompt de Raya (à identifier) :
- Hiérarchie explicite : donnée vivante > déclaration récente > règles
- Réflexe de vérification autonome avant d'affirmer
- Demander à l'utilisateur en dernier recours

**Test bout-en-bout** : refaire le scénario règle 124 avec une nouvelle règle obsolète → Raya doit suivre la donnée vivante, ou vérifier, ou demander.

---

### 🟡 Amélioration (~4h) — niveau Graphiti

#### Phase 3 — Pousser `aria_rules` dans `semantic_graph_nodes` (1h)

**Objectif** : faire de chaque règle un nœud du graphe pour permettre le RAG par traversal.

Pour chaque règle dans aria_rules :
- Créer un nœud `semantic_graph_nodes` avec `node_type='Rule'`, `node_key=rule_id`, `node_label=rule_text[:100]`, `node_properties={...full rule data...}`
- Lier aux entités mentionnées via edges typées :
  - `mentions` : règle → Personne mentionnée (ex: règle Charlotte → node Person Charlotte)
  - `applies_to` : règle → Connection / Mailbox / Domaine
  - `contradicts` : règle A → règle B (si contradiction détectée)
  - `replaces` : règle nouvelle → règle remplacée (avec invalid_at)

#### Phase 6 — Pipeline de capture "RAG-before-write" (3h)

**Objectif** : implémenter le flow complet capture intelligente avec invalidation.

Modification (à identifier) du code qui sauve les règles :
1. Recherche embedding + BM25 des 5 plus proches
2. Appel Sonnet avec invalidation prompt
3. Application décision (5 cas listés ci-dessus)

---

### 🔵 Polish (~5h) — quand on aura plus de règles

#### Phase 7 — Retrieval hybride (3h)

**Objectif** : retrieval pertinent quand on aura 1000+ règles.

- Embedding (déjà en place)
- BM25 via pg_trgm (Postgres natif, à activer)
- Graph traversal via semantic_graph_edges
- Fusion par Reciprocal Rank Fusion (RRF)

#### Phase 8 — Renforcement passif & invalidation auto (2h)

**Objectif** : la mémoire évolue toute seule sans intervention humaine.

- Quand une règle est utilisée et que ça marche : `last_reinforced_at = NOW()`, `confidence++`
- Quand une règle est contredite par les données vivantes : désactivation auto + journal dans `rule_modifications`
- Quand une règle Dynamic dépasse son horizon de validité (ex: > 90j sans réutilisation) : marquage `revalidate=true` pour le prochain audit

---

## Garde-fous transverses

À chaque phase :
- **Branche dédiée** : `feat/learning-hierarchy` (pas direct sur main)
- **Audit avant code** (leçon du matin 05/05)
- **Validation Guillaume** entre chaque sous-étape
- **Pas de migration destructive** : que des ALTER TABLE additifs, pas de DROP
- **Rollback testé** : si une phase casse, on revient à l'état précédent en 1 commande
- **Vérification "pas de bootstrap en cours"** avant chaque push (`SELECT id FROM mail_bootstrap_runs WHERE status IN ('pending','running')`)

---

## Suivi des phases (à mettre à jour au fur et à mesure)

| Phase | Statut | Commit | Date | Notes |
|---|---|---|---|---|
| 1 — Schéma SQL | ⏳ À faire | - | - | - |
| 2 — Reclassement Opus | ⏳ À faire | - | - | - |
| 3 — aria_rules dans graphe | ⏳ À faire | - | - | - |
| 4 — Loader hiérarchisé | ⏳ À faire | - | - | - |
| 5 — Prompt système | ⏳ À faire | - | - | - |
| 6 — Pipeline capture RAG | ⏳ À faire | - | - | - |
| 7 — Retrieval hybride | ⏳ À faire | - | - | - |
| 8 — Renforcement passif | ⏳ À faire | - | - | - |

---

## Décision sur l'ordre

**Soir 05/05/2026** : Phase 1 + Phase 2 (~3h). Bootstrap mails de Guillaume tourne en parallèle pendant la nuit.

**Demain matin / mid-week** : Phase 4 + Phase 5 (~2h). À ce stade, l'incident règle 124 ne peut plus se reproduire.

**Plus tard cette semaine** : Phases 3, 6 (amélioration → niveau Graphiti).

**Sprint suivant** : Phases 7, 8 (polish, à faire quand on aura ~500+ règles).

---

## Références

- **Zep / Graphiti paper** : https://arxiv.org/abs/2501.13956
- **OpenAI cookbook "Temporal Agents with Knowledge Graphs"** : https://developers.openai.com/cookbook/examples/partners/temporal_agents_with_knowledge_graphs/temporal_agents
- **Mem0 paper** : https://arxiv.org/abs/2504.19413
- **Architecture mémoire existante chez nous** : `docs/architecture_memoire_regles_v2_final.md` (job nocturne rules_optimizer, décroissance par non-usage, contradictions)
