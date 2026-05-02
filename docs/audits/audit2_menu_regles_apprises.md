# Audit 2 — Menu des règles apprises

**Date** : 02/05/2026 (en l'absence de Guillaume)  
**Demandé par** : Guillaume  
**Contexte** : "Je voulais aller voir cette règle dans les règles apprises mais ce n'est pas évident, je n'ai pas réussi à la trouver. Faudrait que dans les règles, on puisse avoir un endroit où on affiche toutes les règles. Et qu'on puisse les classer par date, par alphabet, par date d'ajout ou par ancienneté."

---

## 🎯 Diagnostic en une phrase

L'UI actuelle est **conçue pour l'apprentissage progressif** ("Faisons le point"), pas pour **retrouver une règle précise**. Elle offre une excellente expérience pour valider des règles récentes, mais aucun moyen simple de chercher, trier ou parcourir l'ensemble.

---

## 📊 Données réelles (couffrant_solar / guillaume)

| Indicateur | Valeur |
|---|---|
| **Total règles** | 220 (toutes confondues) |
| **Règles actives** | ~144 |
| **Catégories distinctes** | 31 |
| **Plus ancienne règle** | 07/04/2026 |
| **Plus récente** | 01/05/2026 |
| **Doublons de catégories (casse)** | "Tri mails"/"tri_mails"/"tri-mails", "Comportement"/"comportement", "Regroupement"/"regroupement", "Mémoire"/"memoire" |
| **Catégories à 1 seule règle** | 8 catégories (Accès, Limites, Sujet, Météo, etc.) |

🛑 **Constat** : 31 catégories pour 220 règles = trop fragmenté. Beaucoup sont des doublons de casse.

---

## 🔍 Ce qui existe déjà (état actuel)

### Ce qui marche bien

1. **Vue par chips de catégorie** : "À revoir", "Toutes", "Comportement", "Style", etc.
2. **Recherche texte** : champ `rulesSearchInput` avec filtre par contenu (matching simple substring).
3. **Bannière "À revoir avec Raya"** + parcours guidé en sessions de 5 règles (mode `'review'`).
4. **Modal d'édition unifiée** (review/edit/delete) avec breadcrumb.
5. **Tri intelligent par défaut** :
   - Mode `review` → règles les moins sûres en premier (conf + renforcement)
   - Sinon → tri par "importance" (`conf × log(reinf+2)`)

### Ce qui manque / pose problème

🛑 **Problème #1 — Pas de vue "Toutes les règles"**
Le chip "Toutes" affiche les règles **groupées par catégorie**, mais avec **limite de 3 cards visibles par groupe** (le bouton "Voir les X autres" affiche actuellement un `alert("Vue étendue à venir")` — fonctionnalité bouchée). Donc si une règle est dans une catégorie avec >3 entrées, elle peut être complètement invisible.

🛑 **Problème #2 — Pas de tri choisi par l'utilisateur**
Le tri est imposé : importance décroissante (en mode "Toutes") ou peu sûres en premier (en mode "review"). Aucun moyen pour l'utilisateur de demander :
- Tri par date de création (récent → ancien ou inverse)
- Tri alphabétique
- Tri par catégorie alphabétique
- Tri par renforcement / fréquence

🛑 **Problème #3 — La dernière règle ajoutée n'est pas mise en avant**
Aucun signal visuel "🆕 Ajoutée il y a 5 minutes" sur les cards. Tu peux voir l'âge ("aujourd'hui", "hier") dans `rule-meta` mais c'est dilué dans le bruit.

🛑 **Problème #4 — Recherche limitée**
Le champ dit *"Décris ce que tu cherches — Raya comprend par le sens, pas les mots exacts"* mais la recherche actuelle est **un simple `String.includes()`**. Pas de matching sémantique. Le placeholder ment au user.

🛑 **Problème #5 — Pas de catégorisation propre**
Les 31 catégories incluent des doublons (`Comportement` vs `comportement`, `Tri mails` vs `tri_mails`). L'UI les affiche comme distinctes alors qu'elles devraient être fusionnées.

🛑 **Problème #6 — Le chip "Divers" est confusant**
Toutes les catégories ≤2 règles sont mergées dans "Divers" (8 catégories actuellement). Si tu cherches une règle dans `Météo` ou `Accès`, tu vas dans "Divers" sans le savoir.

🛑 **Problème #7 — Pas de raccourci "dernière règle ajoutée"**
Aucun bouton, lien, ou notification permettant de dire "montre-moi la règle qu'on vient d'ajouter en chat".

---

## 💡 Roadmap proposée — 3 options

### Option A — Évolution incrémentale (LOW EFFORT, HIGH IMPACT)

Ajouter sans casser l'existant :

**A1. Toggle de tri**  
Au-dessus de la liste, ajouter un selector :
```
Trier par :  [Importance ▼] [Plus récent] [Plus ancien] [A → Z] [Renforcement]
```
Implémenté côté JS pur, modifie `getFilteredRules()` (ajouter un cas `_sortMode`).

**A2. Vraie vue "Toutes les règles"**  
Remplacer l'alert "Vue étendue à venir" par un vrai déploiement du groupe. Soit :
- Bouton "Voir les X autres" qui montre toutes les règles de la catégorie inline
- Ou bouton qui change `_activeFilter` vers la catégorie (déjà possible via les chips d'ailleurs)

**A3. Badge "Nouveau" sur les règles récentes**  
Sur les cards créées dans les dernières 24h, afficher un badge bleu en haut à droite :
```
[🆕 Ajoutée il y a 12 min]
```

**A4. Lien "Voir la dernière règle ajoutée"**  
En haut du panel, à côté du compteur "134 choses apprises", ajouter :
```
👀 Dernière règle : "Toujours appeler list_my_connections..." (il y a 12 min) →
```
Au clic, scroll jusqu'à la card + flash visuel.

**A5. Fusion silencieuse des catégories doublons**  
Côté backend ou côté UI, normaliser : `comportement` → `Comportement`, `tri_mails` → `Tri mails`, etc. Soit en migration SQL, soit en post-traitement JS dans `loadRules()`.

**Effort estimé** : 4-6h de dev. Aucun changement DB. Tout en JS.

### Option B — Refonte modérée (MEDIUM EFFORT)

Tout de A + :

**B1. Onglet "Toutes les règles" dédié**  
Un nouveau chip "📋 Liste complète" qui affiche un tableau plat :
| Date | Catégorie | Règle | Conf. | Renf. | Actions |
|---|---|---|---|---|---|
| 02/05 | Comportement | Toujours appeler list_my_connections... | 0.80 | 1× | ✏️🗑️ |

Avec **headers cliquables pour trier**. Pagination si >50 règles.

**B2. Recherche sémantique réelle**  
Brancher `rulesSearchInput` sur un endpoint `/rules/search?q=...` qui fait une recherche par embedding sur la colonne `embedding` (pgvector déjà présente, vu en DB).

**B3. Filtrage avancé**  
Au-dessus de la liste, panneau dépliable avec filtres :
- Confidence minimale (slider)
- Renforcement minimal (slider)  
- Période de création (date range)
- Active/Inactive/Toutes
- Catégories (multi-select)

**Effort estimé** : 1.5-2 jours. Endpoint backend `/rules/search` à créer.

### Option C — Refonte complète (HIGH EFFORT)

Tout de A et B + :

**C1. Vue "Activité" chronologique**  
Une timeline montrant les ajouts/modifications de règles avec contexte (quel échange, quel jour). Comme un journal.

**C2. Fusion intelligente assistée**  
Détecte les règles similaires sémantiquement (via embeddings) et propose à l'utilisateur de les fusionner. Réduit les 220 règles vers ~80-100.

**C3. Notifications push**  
À chaque création de règle, notification dans le chat ou dans l'UI : "🆕 J'ai noté une nouvelle règle : [voir]".

**C4. Export CSV/JSON**  
Téléchargement complet pour audit externe.

**Effort estimé** : 3-5 jours. Plus de complexité backend (algos de similarité, notifications).

---

## 🎯 Mon avis (pour discussion)

**Je recommande l'Option A en priorité absolue.** Pourquoi :

1. **Résout 100% de ta plainte** : tri (A1), vue toutes (A2), dernière règle visible (A4), badge nouveau (A3).
2. **Effort minimal** : 4-6h, rien à casser, pas de migration DB.
3. **Pas de risque** : on garde tout le bel UX "Faisons le point" intact.
4. **Tu peux mesurer l'impact** : si A suffit, B/C peuvent attendre. Si A ne suffit pas, on saura quoi cibler.

**Option B est intéressante** plus tard, surtout B2 (recherche sémantique) car le placeholder actuel ment au user. Mais ce n'est pas urgent.

**Option C est trop ambitieuse** par rapport au sujet "je n'arrive pas à retrouver une règle". On peut y revenir dans 2-3 mois si vraiment nécessaire.

---

## 🔧 Détails techniques pour Option A (le moment venu)

### A1 — Toggle de tri

Fichier : `app/templates/user_settings.html`  
Ajouter au-dessus de `<div class="filter-chips">` :
```html
<div style="display:flex;align-items:center;gap:10px;margin-bottom:14px">
  <span style="font-size:12.5px;color:var(--text-muted)">Trier par :</span>
  <select id="rulesSortMode" onchange="changeSortMode(this.value)" class="field-select" style="width:auto;padding:6px 28px 6px 12px">
    <option value="importance">Importance (par défaut)</option>
    <option value="recent">Plus récent</option>
    <option value="ancien">Plus ancien</option>
    <option value="alpha">Alphabétique (A→Z)</option>
    <option value="reinf">Plus renforcée</option>
  </select>
</div>
```

JS — modifier `getFilteredRules()` pour gérer `_sortMode`.

### A2 — Vraie vue étendue

Modifier le bouton :
```js
// Actuel (ligne ~1873)
const moreBtn = hiddenCount > 0
  ? `<div ...><button onclick="alert('Vue étendue à venir...')">Voir les ${hiddenCount} autres...`

// Remplacer par :
const moreBtn = hiddenCount > 0
  ? `<div ...><button onclick="filterByChip('${category.replace(/'/g, "\\'")}')">Voir les ${rules.length} règles de ${category}</button></div>`
```
(Le chip de catégorie existe déjà, donc clic = filtre = liste complète.)

### A3 — Badge "Nouveau"

Dans `renderRuleCard` :
```js
const isNew = rule.created_at && (Date.now() - new Date(rule.created_at).getTime()) < 24 * 3600 * 1000;
// ... dans le HTML retourné, ajouter :
${isNew ? '<span style="position:absolute;top:8px;right:8px;background:linear-gradient(135deg,#3b82f6,#0057b8);color:#fff;font-size:10px;font-weight:600;padding:2px 8px;border-radius:999px">🆕 Nouveau</span>' : ''}
```

### A4 — Lien "Dernière règle ajoutée"

Dans `loadRules()`, après avoir reçu les règles, calculer la plus récente et afficher au-dessus du panel.

### A5 — Fusion casse catégories

Migration SQL one-shot :
```sql
UPDATE aria_rules 
SET category = 'Comportement' 
WHERE category IN ('comportement') AND tenant_id = 'couffrant_solar';

UPDATE aria_rules 
SET category = 'Tri mails' 
WHERE category IN ('tri_mails', 'tri-mails') AND tenant_id = 'couffrant_solar';

UPDATE aria_rules 
SET category = 'Regroupement' 
WHERE category = 'regroupement' AND tenant_id = 'couffrant_solar';

UPDATE aria_rules 
SET category = 'Mémoire' 
WHERE category = 'memoire' AND tenant_id = 'couffrant_solar';
```

⚠️ Faire un backup DB avant. Et idéalement renforcer le `rule_validator.py` pour empêcher la création de doublons casse à l'avenir.

---

## 📁 Fichiers concernés

### Frontend
- `app/templates/user_settings.html` (ligne 690-720 = HTML panel, 1756-2150 = JS logique)
- Le panel "Mes règles Raya" est l'onglet `data-panel="regles"`

### Backend (endpoints existants)
- `GET /rules` — liste les règles actives
- `GET /rules/stats` — stats par catégorie + total
- `GET /rules/review-queue` — file de revue
- `POST /rules/{id}/confirm` — confirme une règle
- `POST /rules/{id}/skip` — passe sans confirmer
- (À créer pour Option B) `GET /rules/search?q=...` — recherche sémantique

### Modèle DB
- Table `aria_rules` (id, category, rule, source, confidence, reinforcements, active, created_at, updated_at, context, username, tenant_id, embedding, last_reinforced_at, level)

---

## 🤔 Questions ouvertes

1. **Pourquoi 31 catégories ?** Probablement à cause du système v1 qui crée des catégories libres via les tags `[ACTION:LEARN:nom_libre|...]`. Le `rule_validator` semble ne pas avoir de référentiel canonique.
2. **Faut-il une catégorisation imposée ?** 5-8 catégories canoniques (Comportement, Style, Métier, Tri mails, Outils, Équipe, Données, Divers) ou continuer en flux libre ?
3. **Que faire des règles `auto` (19 règles, conf 0.60, peu actives) ?** Probablement nettoyer en passant en bulk inactif puis supprimer si pas réactivées.

---

## 📌 Mon résumé en 3 lignes

- L'UI actuelle est **belle et bien pensée pour valider des règles**, mais **mauvaise pour en chercher une**.
- 4-6h de dev en Option A suffisent à régler ta plainte (tri + vue toutes + badge nouveau + raccourci dernière).
- Bonus à faire en passant : nettoyage des doublons de casse (4 lignes SQL).
