## 🌙 Job nocturne rules_optimizer

### Déclenchement
APScheduler, tous les jours à 03h00, feature flag
`SCHEDULER_RULES_OPTIMIZER_ENABLED=true`.

### Philosophie — 100% conversationnel, zero friction

**Ajustement final Guillaume (22/04 matin)** : pas de panel admin, pas de
tableau de validation, pas de rapport matinal systématique, pas de période
de grâce formelle. La gestion des règles se fait **exclusivement via la
conversation avec Raya**.

**Principe** :
- Raya fait le ménage seule la nuit (silencieusement)
- Les vraies contradictions de fond sont posées dans le chat au premier
  échange de la journée (question naturelle, pas notification)
- Les règles sont modifiables en direct pendant la conversation
  ("maintenant on fait plutôt comme ça" → update immédiat)
- L'utilisateur peut demander un audit à tout moment ("liste tes règles",
  "fais-moi une synthèse", etc.)

### Tâches nocturnes (toutes silencieuses, sauf contradictions de fond)

**1. Auto-fusion des doublons (similarité cosine ≥ 0.90)**

Silencieux. Garde la règle la plus longue (plus informative) ou la plus
récente. Archive l'autre avec `status='merged'` et `replaced_by`.

**2. Décroissance progressive de confidence (douce)**

Barème ajusté pour le métier PV (saisonnier, règles qui reviennent) :

```python
# Décrément -0.1 tous les 40 jours sans usage
days_since_used = (now - rule.last_used_at).days
decrement_cycles = days_since_used // 40
new_confidence = max(rule.confidence - 0.1 * decrement_cycles, 0)
```

| Durée sans usage | Confidence (base 1.0) | État |
|---|---|---|
| 0-40 jours | 1.0 | Active |
| 40-80 jours | 0.9 | Active |
| 80-120 jours | 0.8 | Active |
| 120-200 jours | 0.6-0.7 | Active |
| 200-320 jours | 0.3-0.5 | Active (retrieval moins prioritaire) |
| >320 jours | ≤ 0.2 | Active mais seuil critique |
| **>360 jours** | **≤ 0.1** | **Auto-archivée** |

Durée de vie totale ~1 an sans aucun usage. Dès qu'une règle est
retrieved ou appliquée, `last_used_at = NOW()` et la confidence
redémarre à 1.0. **Une règle saisonnière qui sert 1 fois tous les 6 mois
reste donc intacte.**

**3. Auto-normalisation structurelle** (silencieux)

- Catégories : `tri-mails` → `tri_mails`, `priorités` → `priorites`
- Suppression règles vides ou < 10 caractères
- Dédoublonnage strict sur textes identiques

**4. Détection de contradictions**

Pour chaque paire suspecte (similarité sémantique haute + polarité
inversée), appel LLM léger :

```python
response = llm_complete(
    system="Ces 2 règles métier se contredisent-elles ? "
           "Réponds uniquement par OUI_FOND / OUI_FORME / NON.",
    messages=[{"role": "user", "content": f"A: {rule_a}\nB: {rule_b}"}],
    model_tier="fast",  # Haiku
)
```

- **OUI_FORME** (contradiction de style/ton) → auto-résolu silencieux,
  garde la plus récente
- **NON** → ignoré
- **OUI_FOND** (contradiction de comportement métier réelle) → STOCKÉ
  dans table `pending_rules_questions` pour être posé en chat au premier
  message de l'utilisateur le lendemain

### Question de contradiction en chat (seule "sortie" visible)

Quand Guillaume envoie son premier message du jour, si des questions
sont en attente, Raya les injecte naturellement dans sa réponse :

```
Bonjour Guillaume. Avant de répondre à ta question, il y a un point
que j'aimerais clarifier avec toi :

Hier j'ai remarqué 2 règles qui se contredisent sur la gestion des
mails :
  - Le 8 avril tu m'as dit : "Archiver = dossier Archives, jamais la
    corbeille. Corbeille uniquement sur demande explicite."
  - Le 11 avril tu m'as dit : "Mise à la corbeille = action directe
    sans confirmation, c'est récupérable."

Dis-moi ce que tu préfères : je garde la première (archiver ≠ corbeille,
2 actions distinctes), la deuxième (les 2 sont équivalents, corbeille
directe OK), ou on reformule autrement ?

---

[ensuite Raya répond à la question initiale de Guillaume]
```

L'utilisateur tranche en une phrase. Raya met à jour et repart.

### Mécanisme "modification en direct"

Pendant n'importe quelle conversation, si l'utilisateur dit *"maintenant
on fait plutôt comme ça"* sur un sujet qui a une règle existante, Raya :

1. Identifie la règle concernée via search
2. Propose la modification inline : *"OK je mets à jour la règle '...'
   en '...' ?"*
3. Sur validation simple ("oui", "ok"), appelle `update_rule` et continue
   la conversation

Zéro friction, zéro panel séparé.

### Tools agent pour la gestion conversationnelle

3 nouveaux tools à ajouter aux 23 existants :

```
list_rules(category=None, search_query=None, limit=20)
  → Retourne les règles correspondantes. Permet "liste tes règles",
    "montre-moi les règles sur les mails", etc.

update_rule(rule_id, new_text, new_category=None)
  → Modifie une règle existante en place. Update last_used_at.

audit_rules(focus=None)
  → Analyse d'un bloc de règles et proposition de synthèse/fusion.
    "Fais-moi un audit de tes règles sur les clients" → Raya classe,
    suggère fusions, pointe incohérences.
```

Les tools existants `remember_preference` (create) et `forget_preference`
(delete) restent actifs. Les nouveaux ajoutent la dimension lecture et
modification en direct.

### Schéma DB complémentaire

```sql
CREATE TABLE pending_rules_questions (
    id SERIAL PRIMARY KEY,
    username TEXT NOT NULL,
    tenant_id TEXT NOT NULL,
    detected_at TIMESTAMP DEFAULT NOW(),
    rule_a_id INTEGER REFERENCES aria_rules(id),
    rule_b_id INTEGER REFERENCES aria_rules(id),
    contradiction_type VARCHAR(20),  -- 'fond'
    llm_analysis TEXT,
    status VARCHAR(20) DEFAULT 'pending',
    -- 'pending' | 'asked' (posé au user) | 'resolved'
    resolved_at TIMESTAMP,
    resolution_text TEXT
);
```

Au 1er message de la journée, on vérifie s'il y a des questions
`status='pending'` pour cet utilisateur. Si oui → injection dans le
prompt système + passage à `status='asked'`. Quand Raya obtient la
réponse, elle applique et passe à `status='resolved'`.

### Pas de période de grâce / rollback formel

Les règles sont des habitudes de travail, pas des garde-fous de
sécurité. Les vrais garde-fous (confirmation actions irréversibles, ne
pas supprimer les mails, etc.) sont **dans le code**, pas dans
`aria_rules`.

Donc pas de système de rollback automatique. Si l'utilisateur veut
revenir sur un changement, il le dit à Raya en conversation : *"tu as
supprimé la règle X, remets-la"*. Raya cherche dans `aria_rules_history`
(table de log existante) et restaure.


---

## 🔐 Isolation multi-tenant des règles (priorité quand plusieurs Rayas)

**Point soulevé par Guillaume le 22/04** : quand on déploiera une Raya par
collaborateur Couffrant Solar (Pierre, Sabrina, Arlène, Benoît...) et à
terme pour d'autres entreprises clientes, les règles **doivent être
strictement cloisonnées par utilisateur**.

### Ce qui a causé la pollution du 15/04

Les 10 règles "Charlotte" (agence événementielle) ont contaminé la base
de Guillaume parce que `save_rule()` dans `app/memory_rules.py`
n'appliquait pas de filtre strict lors de l'insertion OU lors de la
lecture selon `username`/`tenant_id`. À vérifier et corriger avant
déploiement multi-user.

### Audit à faire sur `memory_rules.py`

1. **À l'écriture** (`save_rule`) :
   - `username` OBLIGATOIRE (pas de défaut silencieux)
   - `tenant_id` OBLIGATOIRE (sauf règles globales explicites)
   - Rejet explicite si l'un des deux manque

2. **À la lecture** (fonctions qui récupèrent les règles pour injection
   dans le prompt) :
   - WHERE username = :user AND tenant_id = :tenant OBLIGATOIRE
   - Pas de fallback "tous les users du tenant" sauf cas explicites
   - Règles globales (catégorie `global_system`) = tenant_id NULL et
     injectées à tous

3. **Test de non-régression** :
   - Créer 2 users fictifs user_A (tenant_A) et user_B (tenant_B)
   - Ajouter 5 règles à chacun
   - Vérifier que user_A ne voit JAMAIS les règles de user_B

### Règles partageables VS règles strictement personnelles

Au sein d'un même tenant (ex: Couffrant Solar), certaines règles gagneraient
à être partagées :

- **Règles personnelles** (user_A ≠ user_B même si même tenant) :
  style rédactionnel, préférences de concision, habitudes de tri mail
- **Règles d'équipe** (tout user du tenant) : membres équipe, structures
  juridiques, clients, procédures métier PV

Solution : ajouter un champ `scope VARCHAR(20)` avec valeurs :
- `personal` : visible uniquement par ce user
- `team` : visible par tous les users du tenant
- `global` : visible par tous (règles système)

À définir quand ce sera le moment de déployer. Pour l'instant (avril 2026),
un seul utilisateur actif (Guillaume), donc scope=personal par défaut pour
tout.

---

## 🎚️ Clarification des "seuils d'auto-résolution"

**Précision suite question Guillaume 22/04** : il ne s'agit PAS de seuils
sur la confidence d'une règle individuelle, mais du **seuil de similarité
cosine** au-delà duquel Raya considère que 2 règles sont "assez proches
pour être fusionnées automatiquement".

### Auto-calibrage plutôt que paliers fixes

Au lieu de "semaine 1 : 0.95, semaine 2 : 0.92, régime normal : 0.90",
**Raya apprend du comportement de Guillaume** :

- Démarre à seuil 0.95 (très strict, seulement les doublons flagrants)
- Si pendant 3 semaines consécutives Guillaume ne revient jamais sur une
  fusion en chat (`rollback` implicite via instructions verbales) → Raya
  descend le seuil d'elle-même à 0.93
- Si Guillaume dit un jour *"tu as fusionné à tort les règles X et Y"* →
  Raya remonte le seuil à 0.97 et reste prudente pendant 15 jours avant
  de tenter à nouveau de descendre

C'est cohérent avec la philosophie "Raya apprend de l'utilisateur, pas de
config admin".

### Implémentation

Ajouter dans la table `aria_rules_system_config` (nouvelle) :
```sql
CREATE TABLE aria_rules_system_config (
    key VARCHAR(50) PRIMARY KEY,
    value FLOAT,
    username TEXT,
    tenant_id TEXT,
    updated_at TIMESTAMP DEFAULT NOW(),
    adjusted_by_feedback_count INTEGER DEFAULT 0
);

INSERT INTO aria_rules_system_config (key, value, username, tenant_id)
VALUES ('auto_merge_threshold', 0.95, 'guillaume', 'couffrant_solar');
```

Le job nocturne lit cette valeur avant chaque passage. Une fois par mois,
si aucun rollback n'a été demandé → descend de 0.02. Si rollback → remonte
de 0.02 et reset le compteur.
