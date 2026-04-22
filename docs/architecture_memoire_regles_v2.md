# Architecture mémoire de règles v2 — Couches A/B + vectorisation

**Date** : 22 avril 2026
**Origine** : échange Guillaume après l'audit des 158 règles actives dans
aria_rules (dont 10 de pollution multi-tenant venues d'un autre user).

---

## 🎯 Problèmes constatés en v1 (actuelle)

1. **158 règles actives** dont 45 à supprimer (28% de déchet)
2. **Pollution multi-tenant** : 10 règles d'un autre utilisateur ont
   contaminé la base de Guillaume (source = "onboarding" du 15/04)
3. **Doublons massifs** : 5 règles "ne pas supprimer mails", 4 sur Simon
   Ducasse, 3 sur attestation Consuel, etc.
4. **Catégorie fourre-tout** : 75 règles dans "auto" sans structure
5. **Pas de retrieval** : TOUTES les règles sont injectées à chaque requête
6. **Pas d'évolution** : aucun mécanisme de fusion, archivage, décroissance
7. **Pas de distinction** entre règles structurelles (équipe, structures)
   et règles contextuelles (procédure métier, préférence)

---

## 🏗️ Architecture proposée : 2 couches

### Couche A — Contexte permanent (injection systématique)

Ce qui **définit l'identité et le cadre de travail**, toujours pertinent.

**Caractéristiques** :
- Volume limité : 20-30 règles max
- Injecté dans le prompt système à CHAQUE requête
- Ne grandit pas dans le temps (stable)
- Catégories fermées : `équipe`, `structures`, `outils_connectés`,
  `règles_non_négociables`

**Exemples** :
- Équipe Couffrant Solar : Pierre (associé), Jérôme (électricien), Arlène
  (assistante), Sabrina (secrétaire), Benoît (commercial), Aurélien
  (poseur), Karen (boîte contact@)
- Structures : SARL Couffrant Solar (principale), SAS GPLH, SCI Gaucherie,
  SCI Romagui, holding en cours
- Outils connectés : Outlook (pro), Gmail (perso), SharePoint, Teams, Odoo
- Règles non négociables : confirmation pour actions irréversibles,
  archiver dans Archives (pas corbeille), etc.

### Couche B — Règles contextuelles (retrieval par pertinence)

Ce qui **s'applique uniquement dans certains contextes métier**.

**Caractéristiques** :
- Volume illimité : 100, 500, 1000 règles possibles
- Vectorisé via Cohere embed ou OpenAI
- Retrieved par similarité cosine avec la question
- Top N pertinentes injectées (N = 5-10 selon longueur question)

**Exemples** :
- "RFAC = Règlement de FACture (pas un avoir)" → pertinent compta
- "SC-144A = dossier technique Consuel" → pertinent PV/Consuel
- "Simon Ducasse (Enryk) = AMO ACC SARL des Moines" → pertinent Legroux
- "Les Amis du Glandier = association Jacques + Francine Coullet" →
  pertinent Coullet

---

## 🔍 Mécanisme de retrieval

### Étape 1 — Embedding de la question
À la réception d'une question, on calcule son embedding (Cohere
embed-multilingual-v3.0, 1024 dimensions, ~0.0001€ par requête).

### Étape 2 — Recherche vectorielle dans pgvector
```sql
SELECT id, rule, embedding <=> :question_emb AS distance
FROM aria_rules
WHERE layer = 'B' AND active = true
ORDER BY distance ASC
LIMIT 10;
```

### Étape 3 — Injection du top N
Les 5-10 règles les plus pertinentes sont injectées dans le prompt système
sous une section dédiée :

```
=== RÈGLES MÉTIER APPLICABLES À CETTE QUESTION ===
- RFAC = Règlement de FACture (pas un avoir)
- Francine Coullet-Herzog = épouse de Jacques Coullet, projet Château
- ...
```

### Gain de tokens

Avec 500 règles dans la base :
- **v1 actuelle** : 500 × 200 chars ≈ 100 000 chars = 25 000 tokens
- **v2 retrieval** : 10 × 200 chars ≈ 2 000 chars = 500 tokens

**Économie : 98% sur la partie règles contextuelles** pour des questions
ciblées. Sur les questions vagues, on laisse plus de règles (top 20).

---

## 🌙 Job nocturne rules_optimizer

### Déclenchement
APScheduler, tous les jours à 03h00, feature flag
`SCHEDULER_RULES_OPTIMIZER_ENABLED=true`.

### Philosophie AUTONOME (ajustement Guillaume 22/04 matin)

**Principe** : Raya agit comme une assistante humaine. Elle ne demande
pas la permission à chaque ménage, elle fait le boulot et te dit le
matin ce qu'elle a fait. L'admin ne gère pas une todo-list de
validations — il consulte un rapport et peut corriger si besoin.

**Zero friction quotidienne. Filet de sécurité via rollback.**

### Tâches (toutes auto-résolues par défaut)

**1. Auto-fusion des doublons (similarité cosine ≥ 0.90)**

Si 2 règles sont quasi-identiques (même sens, formulation proche) :
- Garde la plus récente OU la plus longue (plus informative)
- Archive l'autre avec `status='merged'` et `replaced_by=<id nouvelle>`
- Log dans `rules_change_log` avec les 2 textes originaux pour rollback

**2. Auto-archivage des règles dormantes**

```sql
UPDATE aria_rules
SET status = 'archived', archived_at = NOW(),
    archived_reason = 'non_utilisée_90j'
WHERE last_used_at < NOW() - INTERVAL '90 days'
  AND status = 'active'
  AND layer = 'B';  -- Jamais pour couche A (contexte permanent)
```

**3. Auto-normalisation structurelle**

- Catégories : `tri-mails` → `tri_mails`, `priorités` → `priorites`
- Suppression des règles vides ou < 10 caractères
- Dédoublonnage strict : si 2 règles ont un texte identique mot pour
  mot après normalisation → garde la plus ancienne (ID inférieur)

**4. Détection de contradictions**

Pour chaque paire suspecte (similarité sémantique haute + termes de
polarité inversée type "toujours"/"jamais", "oui"/"non") :
```python
response = llm_complete(
    system="Ces 2 règles métier se contredisent-elles ? " \
           "Réponds uniquement OUI_FOND / OUI_FORME / NON.",
    messages=[{"role": "user", "content": f"A: {rule_a}\nB: {rule_b}"}],
    model_tier="fast",  # Haiku suffit
)
```

Si résultat :
- **OUI_FORME** (contradiction de style/ton) → auto-résolue, garde la
  règle la plus récente
- **OUI_FOND** (contradiction de comportement métier) → **seule
  exception** : flag dans le rapport matinal pour décision humaine
- **NON** → paire ignorée

**5. Décroissance progressive de confidence**

```sql
UPDATE aria_rules
SET confidence = GREATEST(confidence - 0.05, 0)
WHERE last_used_at < NOW() - INTERVAL '30 days'
  AND status = 'active';
```

Quand confidence atteint 0 et dernière utilisation > 90j → archivage.

### Rapport matinal (dans le heartbeat 7h)

Format concis, informatif, pas de demande de validation sauf contradiction
de fond :

```
📊 Ménage des règles cette nuit :
  - 3 doublons fusionnés (signature mail, mise à la corbeille, équipe)
  - 2 règles archivées (non utilisées depuis >90j)
  - 1 catégorie normalisée (tri-mails → tri_mails)

Total règles actives : 113 (-6 vs hier)

⚠️ 1 contradiction de FOND détectée, tranche stp :
  A: "Archiver mails = action directe sans confirmation"
  B: "Toute action sur mail nécessite confirmation"
  → dis-moi "garde A" ou "garde B"
```

### Rollback — la vraie sécurité

Tous les changements sont loggés dans `rules_change_log` :

```sql
CREATE TABLE rules_change_log (
    id SERIAL PRIMARY KEY,
    changed_at TIMESTAMP DEFAULT NOW(),
    action VARCHAR(30),  -- 'auto_merge', 'auto_archive', 'auto_resolve_contradiction'
    rule_id INTEGER,
    previous_state JSONB,  -- snapshot complet de la règle avant changement
    reason TEXT,
    rolled_back BOOLEAN DEFAULT FALSE,
    rollback_at TIMESTAMP
);
```

**Commandes de rollback** que l'utilisateur peut donner à Raya à tout moment :
- *"Annule la fusion des règles sur la signature"* → identifie la
  fusion correspondante dans le log, restaure les 2 règles originales
- *"Ramène les règles archivées cette nuit"* → UPDATE status='active'
  sur les règles log.changed_at > NOW() - INTERVAL '24 hours'
- *"Garde B sur la contradiction archivage"* → résout la contradiction
  flaggée

Ces commandes sont des tools agent standard : `rollback_rule_change`,
`resolve_contradiction`.

### Seuils ajustables (démarrage prudent)

| Paramètre | Semaine 1 | Semaine 2 | Régime normal |
|---|---|---|---|
| Seuil fusion (cosine) | 0.95 | 0.92 | 0.90 |
| Archivage après N jours sans usage | 120 | 100 | 90 |
| Contradictions auto-résolues (forme) | non | oui | oui |

On démarre prudent et on assouplit si Guillaume ne voit pas de problème.

### Rapport d'observation hebdomadaire

Chaque dimanche matin, en plus du rapport quotidien :
```
📈 Récap hebdo règles :
  - 14 actions automatiques cette semaine (0 rollback demandé)
  - 2 contradictions de fond résolues par toi
  - Base stable à 110 règles actives (-2 net sur la semaine)
```

Si Guillaume voit dans le log qu'il fait souvent des rollbacks → signal
que les seuils sont trop agressifs, on les remonte.

---

## 🗄️ Schéma DB

### Modification `aria_rules` existante
```sql
ALTER TABLE aria_rules ADD COLUMN layer CHAR(1) DEFAULT 'B';
  -- 'A' = contexte permanent, 'B' = contextuel retrieved

ALTER TABLE aria_rules ADD COLUMN embedding VECTOR(1024);
  -- Nécessite extension pgvector

ALTER TABLE aria_rules ADD COLUMN usage_count INTEGER DEFAULT 0;
ALTER TABLE aria_rules ADD COLUMN last_used_at TIMESTAMP;

ALTER TABLE aria_rules ADD COLUMN status VARCHAR(20) DEFAULT 'active';
  -- 'active', 'archived', 'merged', 'pending_review'

ALTER TABLE aria_rules ADD COLUMN replaced_by INTEGER REFERENCES aria_rules(id);
  -- Si fusionnée, pointe vers la règle qui la remplace

ALTER TABLE aria_rules ADD COLUMN archived_at TIMESTAMP;
ALTER TABLE aria_rules ADD COLUMN archived_reason VARCHAR(50);

CREATE INDEX aria_rules_embedding_idx
  ON aria_rules USING ivfflat (embedding vector_cosine_ops);

CREATE INDEX aria_rules_layer_active_idx
  ON aria_rules (layer, active);
```

### Nouvelle table `rules_optimizer_candidates`
```sql
CREATE TABLE rules_optimizer_candidates (
    id SERIAL PRIMARY KEY,
    detected_at TIMESTAMP DEFAULT NOW(),
    type VARCHAR(30),  -- 'duplicate', 'contradiction', 'merge_suggestion'
    rule_a_id INTEGER REFERENCES aria_rules(id),
    rule_b_id INTEGER REFERENCES aria_rules(id),
    similarity FLOAT,
    llm_analysis TEXT,
    status VARCHAR(20) DEFAULT 'pending',
      -- 'pending', 'accepted', 'rejected', 'auto_resolved'
    resolved_at TIMESTAMP,
    resolved_by VARCHAR(50)
);
```

---

## 🎨 Interface admin

Nouvelle page `/admin/rules` avec :
- Liste des règles par couche A/B et catégorie
- Filtres : statut, confiance, dernière utilisation
- Actions : édition, archivage, fusion manuelle
- Section "Suggestions de l'optimizer" : doublons et contradictions
  détectés cette nuit, boutons "Fusionner" / "Ignorer"
- Statistiques : nb règles par couche, usage moyen, taux de décroissance

---

## 💰 Coût estimé

| Poste | Coût mensuel |
|---|---|
| Vectorisation à l'insertion (500 règles/mois) | ~0,05 € |
| Retrieval (gratuit, local pgvector) | 0 € |
| Job nocturne (30 j × appel Opus) | ~5 € |
| **Total** | **~5 €/mois** |

Gain : économie de ~24 500 tokens par question complexe →
**~0,40 €/question** économisés avec Opus 4.7.
Sur 100 questions/jour × 30j × 0,40€ = **~1 200 €/mois économisés**.

**ROI > 240x**.

---

## 🎯 Plan d'implémentation en 4 phases

### Phase 1 — Nettoyage manuel (AUJOURD'HUI, 22/04)
Supprimer les 45 règles identifiées :
- Lot 1 : pollution Charlotte (10)
- Lot 2 : bug + obsolètes v1 (7)
- Lot 3 : doublons (20)
- Lot 4 : vagues redondantes (8)

### Phase 2 — Classification A/B (cette semaine)
- Ajouter colonne `layer` à aria_rules
- Reclasser les ~115 règles restantes en A (contexte) ou B (contextuelles)
- Injecter uniquement la couche A dans le prompt système pour commencer

### Phase 3 — Vectorisation + retrieval (semaine prochaine)
- Installer pgvector sur Railway
- Ajouter colonnes embedding, usage_count, last_used_at
- Script de vectorisation batch pour les règles existantes
- Modifier `_build_agent_system_prompt` pour retrieved 10 règles couche B
- Logging des retrievals pour alimenter usage_count

### Phase 4 — Optimizer nocturne (semaine suivante)
- Créer `app/jobs/rules_optimizer.py`
- Job APScheduler 03h00
- Page admin `/admin/rules`
- Intégration dans le heartbeat matinal

---

## ⚠️ Bug multi-tenant à corriger en parallèle

Dans `app/memory_rules.py`, fonction `save_rule()`, vérifier que le filtre
`tenant_id` + `username` est respecté à chaque INSERT, et que les règles
sont bien isolées par user à la lecture (`get_active_rules()` ou
équivalent).

C'est ce qui a permis aux 10 règles "Charlotte" de contaminer la base de
Guillaume. Sans ce fix, toute autre instance Raya future (Pierre, Sabrina,
etc.) risque de polluer les autres.
