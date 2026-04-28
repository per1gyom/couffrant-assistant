# 🔍 Onboarding Raya sur un nouvel outil — Mode "découverte guidée"

> **Créé le** : 28 avril 2026 matin **Statut** : NOTE DE TRAVAIL — à approfondir dans une session dédiée **Lien avec** : `docs/a_faire.md` Priorité 2 (Connexion simplifiée des outils tiers)

---

## 🎯 Le besoin (formulé par Guillaume le 28/04)

Quand Raya découvre un nouvel outil tiers (Odoo, SharePoint, Drive, et bientôt Vesta, Microsoft 365 multi-tenant, WhatsApp Business...), elle ne sait pas spontanément :

- Comment cet outil est **structuré** pour cette entreprise spécifique
- Quelles **conventions métier** sont en place (qui voit quoi, comment filtrer, quels champs ont du sens humain)
- Quelles **fonctions cachées** ou **données peu évidentes** existent
- Comment répondre de manière **cohérente** à ce que l'utilisateur attend

### Cas d'usage qui a déclenché la réflexion

Le 28/04 matin, test sur le planning :

- Raya a accès à `calendar.event` Odoo (planning d'équipe partagé)
- Question "qui je vais voir dans ma tournée ?" → Raya a sorti **les rendez-vous de Pierre, Jérôme, Aurélien** comme étant ceux de Guillaume
- Cause racine : Raya ne savait pas que pour identifier "**ses**" rendez-vous, il faut filtrer sur `of_employees_names = guillaume`
- Ce n'est PAS une fuite d'isolation (les plannings d'équipe sont volontairement partagés) — c'est un **manque de connaissance métier**

## 💡 La solution proposée — Mode "découverte guidée"

Quand un nouvel outil est connecté à Raya (par un super_admin ou un tenant_admin), elle propose un **tour d'inspection initial** :

1. **Lister** les modèles / objets / dossiers / endpoints disponibles
2. **Comprendre** la structure (champs, relations, contenu)
3. **Identifier** les conventions métier propres à l'entreprise
4. **Demander** au super_admin des précisions sur les ambiguïtés (ex : "Le champ `of_employees_names` semble lister les intervenants. Faut-il que je filtre sur l'utilisateur courant pour les questions de type 'mon planning' ?")
5. **Stocker** ces apprentissages comme **règles métier** (pas dans `aria_rules` qui est utilisateur, mais dans une nouvelle table `tenant_business_rules` partagée par tous les utilisateurs du tenant)

### Voie 1 (apprentissage par usage) reste valable en complément

Tu l'as bien dit : l'onboarding initial **dégrossit**, mais ensuite l'utilisateur affine au fil de l'eau via le système de feedback existant (qu'on a réparé hier soir).

L'onboarding initial **ne doit PAS être restreignant** : Raya doit rester libre, et l'utilisateur doit pouvoir exprimer des besoins / envies différentes selon son utilisation.

## 🛠️ Pistes techniques à creuser (dans la session dédiée)

### Architecture

- Nouveau **type de table** : `tenant_business_rules` (pas `aria_rules` qui est utilisateur)
  - Colonnes : `tenant_id`, `tool_type` (odoo / drive / vesta / ...), `rule`, `confidence`, `created_by`, `created_at`
  - Lecture systématique au démarrage de la boucle agent quand un outil correspondant est utilisé
- **Mode "tour guidé"** : nouveau `RAYA_DISCOVERY_MODE` ou nouvel endpoint `/admin/discover/{tool_type}`
- **Workflow** : Raya pose des questions au super_admin, stocke les réponses comme règles, puis se déclare "prête"

### Comportement attendu

- Quand le super_admin connecte un nouvel outil → Raya propose **automatiquement** "veux-tu qu'on fasse un tour de découverte ?"
- Tour de découverte non-obligatoire (le super_admin peut sauter)
- Tour partiellement progressif : on peut découvrir 3 modèles aujourd'hui, 2 autres demain
- Si tour non fait, Raya marche quand même mais peut faire des erreurs comme celles du 28/04

### Outils prioritaires à connecter (et qui auront ce besoin)

D'après `a_faire.md` Priorité 2 et discussion 28/04 :

OutilSpécificités probables**Vesta**Logiciel de dimensionnement PV, accès API ouverts. Convention métier : à découvrir.**Microsoft 365 multi-tenant**Comptes Azure, structure par boîte aux lettres**Gmail**Boîte unique par user, mais labels/filtres propres à chaque entreprise**WhatsApp Business**Messages pro vs perso, fils de discussion, contacts**Slack**Canaux publics/privés, conventions de nommage propres à l'équipe

Chaque connexion d'un de ces outils déclenchera le besoin d'un tour de découverte.

## 📋 À définir lors de la session dédiée

- \[ \] Architecture précise de `tenant_business_rules` (vs `aria_rules`)
- \[ \] Format des questions que Raya pose au super_admin (libre vs structuré)
- \[ \] UI de l'onboarding (chat dédié ? page de configuration ?)
- \[ \] Comment les règles métier influencent le retrieval / la formulation
- \[ \] Mécanisme de **mise à jour** d'une règle métier (quand l'entreprise change de pratique)
- \[ \] Cohabitation avec l'apprentissage par feedback utilisateur
- \[ \] Visibilité multi-tenant : un super_admin doit-il voir les règles métier des autres tenants ?

## 🛑 Engagement Guillaume du 28/04

- Ne PAS attaquer ça entre 2 chantiers : c'est un **gros sujet** qui mérite une session dédiée
- Le faire **avant** ou **en parallèle** des prochaines connexions d'outils (Vesta notamment)
- L'outil doit rester **libre**, pas être bridé par l'onboarding

---

## 🔗 Liens vers les autres documents

- `docs/a_faire.md` § "Priorité 2 — Connexion simplifiée des outils tiers"
- `docs/etat_complet_chantiers_27avril_nuit.md` § 5 (Idée auto-détection des manques — sujet voisin)
- `docs/audit_isolation_25avril_complementaire.md` (pour ne pas confondre avec un sujet d'isolation)
