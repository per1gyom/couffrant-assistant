# 🔍 AUDIT À FAIRE : Exemples par défaut & textes d'aide impersonnels

**Date création** : 02/05/2026
**Priorité** : moyenne (pas urgent mais important avant onboarding nouveaux clients)
**Demandé par** : Guillaume

## Contexte du problème

Au fil des sessions de développement, Claude/Anthropic a tendance à reprendre dans
les exemples par défaut, placeholders, et textes d'aide des éléments **spécifiques
au contexte business de Guillaume / Couffrant Solar** :

- Noms d'associés ou collaborateurs réels
- Noms de dossiers internes (ex: "Drive Direction", "Comptabilité", "RH",
  "Salaires", "1_Photovoltaïque")
- Termes métier spécifiques à l'activité solaire/photovoltaïque
- Intitulés liés à la structure interne de Couffrant Solar

**Problème** : ces éléments deviennent visibles aux **autres tenants** (ex: juillet,
et tous les futurs clients). Cela donne une impression peu professionnelle, casse
l'effet "produit générique multi-tenant" et expose des informations internes.

## Exemples concrets identifiés (liste à compléter)

### 📁 Drive config (chantier 02/05/2026)

**Fichier** : `app/templates/_drive_config_modal_snippet.html`
**Fichier** : `app/templates/admin_connexions.html` (modale inline)
**Fichier** : `app/templates/tenant_panel.html` (modale inline)
**Fichier** : `app/static/admin-drive-config.js` (commentaires)

Placeholders à remplacer :
- "ex: Drive Direction" → "ex: Mes Documents" ou "ex: Documents Société"
- "ex: Direction" (site) → "ex: Equipe" ou "ex: Marketing"
- "ex: Comptabilité" (path) → "ex: Dossier Projets"
- "ex: Drive Direction/RH" → "ex: Documents/Confidentiel"
- "ex: RH confidentiel" (raison) → "ex: Données sensibles"
- "ex: Drive Direction/RH/contrat.docx" → "ex: Documents/Confidentiel/fichier.docx"

Exemples dans les blocs d'aide :
- "Inclus Comptabilité = tout indexé"
- "Exclus Comptabilité/Salaires = sauf ce sous-dossier"
- "Inclus Comptabilité/Salaires/Public = sauf ce sous-sous-dossier"

→ À remplacer par des exemples génériques : `DossierA / DossierA/SousDossier /
DossierA/SousDossier/SousSousDossier` ou alors `Public / Public/Confidentiel /
Public/Confidentiel/Equipe-A`.

### 🚨 Note d'aide tenant_panel.html (Drive)

**Fichier** : `app/templates/tenant_panel.html`
Ligne actuelle :
> "Pour ajouter un nouveau drive (ex: Drive Direction), demande au super-admin..."

→ Remplacer "ex: Drive Direction" par formulation générique sans nom.

## Stratégie d'audit complet

À faire en une session dédiée :

### 1. Recherche systématique des termes métier Couffrant Solar

```bash
cd /Users/per1guillaume/couffrant-assistant
grep -rniE "couffrant|photovoltaïque|photovoltaique|solar|guillaume|charlotte|julie|romorantin|drive direction|comptabilité|salaires|RH" \
  app/templates/ app/static/ app/routes/ 2>&1 | grep -v ".bak" | grep -v "node_modules"
```

Filtrer ce qui est :
- Du code logique légitime (ex: tenant_id="couffrant_solar" en seed) → à conserver
- Des exemples / placeholders / textes d'aide → à neutraliser

### 2. Recherche des prénoms / noms propres

```bash
grep -rniE "prenom|prénom|monsieur|madame|directeur|directrice|associé|salarié" \
  app/templates/ app/static/
```

### 3. Audit des textes d'aide / tooltips / placeholders

- Tous les `placeholder=` dans les templates
- Tous les `<small>`, blocs `.info`, `.warn`, `.help`
- Tous les `console.log` / `alert` / `prompt` / `confirm` qui pourraient
  contenir un exemple métier
- Les commentaires dans le JS (souvent visibles dans le code source navigateur)

### 4. Liste blanche de termes génériques à utiliser comme remplacements

Dossiers : `Documents`, `Projets`, `Archives`, `Equipe`, `Public`, `Confidentiel`
Sites SharePoint : `Equipe`, `Marketing`, `Communication`, `Public`
Mails : `prenom.nom@societe.fr`, `contact@entreprise.fr`
Personnes : `John Doe`, `Jane Smith`, ou simplement `Utilisateur 1`, `Admin`
Sociétés : `Acme`, `Société X`, `Ma Société`

### 5. Convention de placeholder

Adopter une convention claire :
- Pour les exemples → toujours préfixer par `ex:` ou `(exemple)`
- Pour les noms de personnes → `Prénom Nom`
- Pour les sociétés → `Société` (sans nom)
- Pour les emails → `email@domaine.fr`

## Périmètre estimé

- **20-30 fichiers** templates HTML probablement concernés
- **Quelques fichiers JS** avec des exemples dans les commentaires
- **Documentation utilisateur** (CGU, FAQ) si elle existe
- **Messages système et IA** : voir si Raya elle-même cite des exemples
  spécifiques quand elle explique son fonctionnement

## Risque si non fait

- Quand un nouveau client (ex: tenant "juillet" ou autre) ouvre le panel,
  il voit des références à "Drive Direction", "Comptabilité Couffrant", etc.
- Donne l'impression d'un produit développé pour UN seul client
- Casse la confiance pro pour l'onboarding (M&A futur)

## Plan d'exécution suggéré

1. **Session dédiée d'audit** (1-2h) : grep systématique + liste exhaustive
2. **Validation par Guillaume** : valider la liste de termes à remplacer
3. **Refactor en une seule passe** : un commit "chore: textes generiques pour
   exemples par defaut" qui touche tous les fichiers d'un coup
4. **Tests** : vérifier qu'aucun test fonctionnel n'utilise ces strings comme matcher

## Statut

🟡 **À PLANIFIER** — pas urgent, mais à traiter avant tout nouveau prospect.
Note ajoutée par Claude le 02/05/2026 suite à feedback Guillaume sur la modale
Drive config qui contenait "Drive Direction" / "Comptabilité" / "RH" comme exemples.
