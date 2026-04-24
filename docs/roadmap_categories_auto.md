# Roadmap — Nettoyage des catégories "auto" et tags implicites

**Créé le 25 avril 2026** — découverte lors du test de la page /settings
onglet Mes règles.

## 🎯 Problème identifié

Sur les 134 règles actives de Guillaume, **23 catégories différentes**
dont :

- **59 règles dans `auto`** (catégorie fallback quand rules_optimizer
  n'arrive pas à classer)
- **35 de ces 59 règles ont un tag implicite** au début de leur texte :
  `[équipe]`, `[odoo]`, `[patrimoine]`, `[clients]`, `[comportement]`,
  `[roadmap]`, `[outils]`, etc.
- **13 catégories n'ont qu'une ou 2 règles** (doublons évidents :
  `tri_mails` + `tri-mails` + `categories_mail` par ex.)

Le bug est en amont : quand Raya crée une règle avec `[tag] contenu de
la règle`, le tag devrait être extrait comme catégorie et retiré du
texte, mais ça n'est pas fait.

## 🔍 Exemples de règles mal taggées

| ID  | Catégorie actuelle | Texte (début)                                 | Catégorie souhaitée |
| --- | ------------------ | --------------------------------------------- | ------------------- |
| 148 | auto               | `[odoo] Les IDs partners Odoo connus...`      | Odoo                |
| 146 | auto               | `[équipe] Karen = utilise uniquement...`      | Équipe              |
| 145 | auto               | `[patrimoine] Couffrant Solar : Guillaume...` | Patrimoine          |
| 149 | auto               | `[clients] Simon Ducasse (Enryk)...`          | Clients             |
| 150 | auto               | `[comportement] Les requêtes Odoo...`         | Comportement        |

Il y en a 35 comme ça dans `auto`. Un simple regex `^\[(\w+)\]` suffit
à les extraire.

## 📋 Solution proposée

### Phase 1 — Migration one-shot (rapide)

Un script de migration qui :
1. Parcourt toutes les règles en `category='auto'`
2. Détecte un tag `[xxx]` au début du texte via regex
3. Normalise le tag : `équipe` → `Équipe`, `odoo` → `Odoo`, etc.
4. Met à jour `category` et retire le tag du texte
5. Logge chaque modification dans `rule_modifications`

Script proposé : `scripts/migrate_auto_category_tags.py`

Résultat attendu : 35 règles reclassées, ~10 catégories propres créées.

### Phase 2 — Fusionner les doublons de catégories

Doublons évidents à fusionner :

- `tri_mails` + `tri-mails` → `Tri mails` (10 règles)
- `categories_mail` → `Tri mails` (11 règles supplémentaires)
- `drive` + `drive_pv` → `Drive` (5 règles)
- `communication` + `ton` → `Communication` (3 règles)

Interface admin à créer :
- Endpoint `GET /admin/categories/duplicates` : propose des fusions
- Endpoint `POST /admin/categories/merge` : applique une fusion
- Page dans le panel super-admin pour valider

### Phase 3 — Corriger rules_optimizer

Modifier `rules_optimizer.py` pour que :
- Extraction auto du tag `[xxx]` au moment de la création
- Suggestion de catégorie à l'insert via llm_complete (si pas de tag)
- Validation anti-doublon : si un user a déjà `tri_mails`, ne pas créer
  `tri-mails` (distance de Levenshtein < 3 ou slugs identiques)

## 📊 Impact attendu

Avant :
- 23 catégories, 8 à 1 règle, 59 dans le fallback `auto`
- Chip "Toutes 134" + chip "auto 59" en second = catégorie sac à dos

Après Phase 1 :
- ~12 catégories propres
- `auto` redescend à ~24 règles (vraiment pas classables)
- Chip "Équipe 8", "Odoo 6", "Patrimoine 3", etc.

Après Phase 2 :
- ~8 catégories principales + "Divers" pour les petites
- Plus de `tri_mails`/`tri-mails` dupliqués

Après Phase 3 :
- Plus jamais de règle créée dans `auto` si elle a un tag explicite
- Plus jamais de doublon de catégorie par faute d'orthographe

## ⚠️ Priorité

Pas urgent mais **avant d'ouvrir à des utilisateurs tiers**. Sinon
chaque nouvel utilisateur aura le même chaos au bout de 2 semaines.

**Estimation** : Phase 1 = 1-2h, Phase 2 = 3h, Phase 3 = 2h.
