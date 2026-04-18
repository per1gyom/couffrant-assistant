# 🎯 Plan — Scanner Universel Odoo + Vectorisation totale

**Version** : 1.0 (draft, en cours de validation section par section)
**Date** : 18 avril 2026
**Auteur** : Claude + Guillaume
**Statut** : Document de planification, à valider par section avant tout code

---

## 📖 Section 1 — Contexte et objectif

### D'où on vient (ce matin 18/04)

On a construit en une journée un chantier mémoire à 4 couches (architecture
documentée, graphe sémantique, vectorisation, webhooks, hybrid search). C'est
une bonne base, mais les tests en conditions réelles (bug Coullet/Glandier,
recherche SE100K) ont révélé une limite fondamentale :

> **On a vectorisé une FRACTION des données Odoo en codant à la main les
> modèles qu'on connaissait (res.partner, sale.order, crm.lead, calendar.event),
> en ne prenant que quelques champs par modèle, et en ignorant les modèles
> custom, les historiques, les commentaires, les pièces jointes, les relations
> internes (kits, nomenclatures, fournisseurs).**

Conséquence : Raya a accès à ~5% de ce que contient ton Odoo. Elle est
intelligente sur ces 5%, mais aveugle sur les 95% restants. D'où les
hallucinations et les réponses incomplètes.

### Ce que tu veux (validé en conversation 14h05-14h20)

> *« Il faut être sûr dans ce que nous mettons en place qu'aucune donnée ne
> manque, aucun détail, aucune sous-fenêtre, aucun sous-fichier, aucun détail
> concernant ni un article, ni un modèle, ni une personne, ni un client, ni un
> prospect, ni un devis, ni une facture, ni un élément de signature, ni des
> commentaires [...] Qui a fait le devis, qui l'a modifié, qui le suit, qui est
> le commercial du client... Raya doit avoir tout, tout, tout. »*

**Dimensions additionnelles ajoutées à 14h20** :

**Le CRM** — chaque lead a son étape de qualification (prospect, RDV pris,
étude en cours, devis envoyé, signé, perdu, gagné...) et son historique de
passage d'étape en étape. Raya doit voir qui est à quelle étape et depuis
combien de temps, pour détecter les dossiers qui stagnent.

**Le planning des interventions** — chaque événement contient l'adresse
précise du chantier (avec lien GPS recoupé au client), les intervenants
assignés, et surtout **les comptes-rendus post-intervention**. Ces
comptes-rendus ne sont pas de simples notes : ils contiennent des
**instructions exploitables** que Guillaume ou ses collègues laissent pour
la suite (*« penser à mettre à jour le devis »*, *« renvoyer aux clients les
documents techniques »*, *« planifier un autre rendez-vous »*, *« faire une
variante à la proposition »*).

**Routage intelligent des instructions** — Raya doit non seulement lire ces
instructions mais aussi **les router automatiquement vers les bons
collaborateurs** selon leur nature :
- Envoi de documents techniques → tel collègue
- Mise à jour du devis → autre collègue
- Planification RDV → encore un autre
- etc.

C'est un niveau au-dessus de la simple vectorisation : c'est de
**l'automatisation intelligente pilotée par les données**.

### ⭐ Méthode d'auto-inventaire — Raya se découvre elle-même

Suite à l'idée de Guillaume 14h35 : *« On pourra lui demander un inventaire
des informations auxquelles elle peut avoir accès. Pour lui faire lister et
ensuite exploiter ça. »*

**Méthode** : notre connexion XML-RPC Odoo a déjà les droits pour lire le
schéma Odoo via les modèles système `ir.model` et `ir.model.fields`. On crée
un nouveau tag ACTION :

- `[ACTION:ODOO_INTROSPECT]` → Raya lance l'inventaire complet
- Retourne un rapport structuré :
  - Liste des modèles accessibles avec compteur de records par modèle
  - Pour chaque modèle : tous les champs avec nom, type, label, relation
  - Détection des champs custom (préfixés `x_`)
  - Détection des modèles personnalisés (pas de préfixe `ir.` ou `res.`)

**Workflow utilisateur** :
1. Tu demandes à Raya : *« Fais l'inventaire complet d'Odoo »*
2. Elle retourne un tableau structuré (tu le vois dans la chat)
3. Ensemble on valide quels modèles activer pour la vectorisation
4. Le scanner vectorise en se basant sur cette sélection

**Avantage majeur** : Raya découvre toute seule ce qui est custom chez
Guillaume, sans qu'on ait besoin de le lui dire. Universel et transparent.

### Mise à jour dynamique — 4 mécanismes coordonnés (révisé)

Après recul (réponse à la demande Guillaume 14h35), voici la répartition
finale des 4 mécanismes qui couvrent 100% des cas de mise à jour :

| # | Mécanisme | Quand déclenché | Volume | Fréquence |
|---|---|---|---|---|
| 1 | **Webhook temps réel** | Modification Odoo | 1 record | ~5s après modif |
| 2 | **Delta incrémental nocturne** | CRON | Modifiés depuis 24h | 1×/jour à 3h30 |
| 3 | **Audit d'intégrité** | CRON | Compte Odoo vs compte Raya | 1×/semaine |
| 4 | **Rebuild ciblé** | Audit détecte écart >1% OU activation initiale OU changement schéma | 1 modèle ou tout | Rare (<1×/mois) |

**Différence clé avec approche initiale** : l'**audit d'intégrité** est une
nouveauté. Il fait le diff des compteurs Odoo vs Raya chaque semaine, et si
écart, déclenche un **rebuild ciblé** automatique (pas manuel). Toi tu
regardes juste le dashboard une fois par semaine.

**Pourquoi cette combinaison est robuste** :
- Les webhooks traitent le flux normal (95% des cas)
- Si un webhook rate (réseau, crash Railway), le delta nocturne rattrape (4%)
- Si le delta rate aussi (cas très rare), l'audit hebdo le détecte (1%)
- Le rebuild ciblé est l'ultime filet de sécurité, et il est **automatique**

Aucun cas n'est oublié. Aucune action humaine requise en fonctionnement
normal. Tu gardes la main via le dashboard si tu veux voir ce qui se passe.

### Ce qu'on va faire

Construire un **Scanner Universel Odoo** : un outil introspectif qui, une fois
déclenché depuis le panel admin, :

1. **Découvre automatiquement** tous les modèles Odoo accessibles dans TON
   Odoo (y compris les modèles custom que je ne peux pas deviner)
2. **Inventorie tous les champs** de chaque modèle via l'API d'introspection
   Odoo (`ir.model` et `ir.model.fields`)
3. **Classe automatiquement** chaque champ : texte vectorisable, relation
   (arête du graphe), métadonnée numérique, binaire (pièce jointe à extraire)
4. **Te propose un rapport** : *« J'ai découvert 127 modèles, 3412 champs dont
   489 vectorisables. Voici la liste, coche ceux que tu veux activer. »*
5. **Vectorise de façon exhaustive** ce que tu as coché, incluant :
   - Tous les champs texte (char, text, html)
   - Les commentaires (`mail.message`)
   - L'historique de modifications (`mail.tracking.value`)
   - Les pièces jointes (`ir.attachment`) avec extraction du contenu
   - Les signatures électroniques
6. **Garantit l'exhaustivité** : un système de vérification qui compare le
   nombre de records côté Odoo vs côté Raya à tout instant, et remonte une
   alerte en cas d'écart.

### ⭐ Distinction fondamentale — Stocker vs Graphe vs Live

Suite à la discussion 14h20-14h40 avec Guillaume, clarification architecturale
majeure. On distingue **3 niveaux de traitement** pour chaque donnée Odoo :

**Niveau 1 — Graphe sémantique (pour TOUTES les entités)**
Un nœud léger par entité : id, label, type, source. ~200 octets par nœud.
Création quasi-gratuite. C'est la CARTOGRAPHIE complète. Tout passe dans le
graphe : les 133k articles, tous les partners, devis, commentaires, etc.
Permet la navigation, la traversée multi-hop, la détection de doublons.

**Niveau 2 — Vectorisation (règle simple, validée 14h50)**

**Par défaut : on vectorise**. Tout ce qui peut aider Raya à retrouver une
entité ou comprendre un sujet est vectorisé — sans plafond budgétaire, la
règle est "dans le doute, on vectorise".

Cela inclut notamment :
- Noms d'articles, d'entreprises, de personnes
- **Références techniques** (SE100K, ENT_KIT centrale PV Pro, GER_1047611,
  DMEGC, etc.) — ESSENTIEL pour que Guillaume puisse dire *"crée-moi un devis
  avec le kit PV Pro"* et que Raya identifie l'article
- Descriptions produit (`description_sale`, `description_purchase`, norme,
  `description_fabricant`, descriptions logistiques)
- Commentaires (`mail.message`) et comptes-rendus d'intervention
- Notes internes, notes de devis, descriptions de leads
- Contenu extrait des pièces jointes PDF/Word/Excel
- Coordonnées des personnes (pour recherche inversée : *"qui a ce tel ?"*)
- Adresses, villes, codes postaux

**On ne vectorise PAS** (uniquement ces 5 cas) :
- Les **prix** (volatiles, réactualisés automatiquement par le fournisseur)
- Les **montants** totalisés (calculés, changent tout le temps)
- Les **quantités** (métadonnées pures)
- Les **états/statuts** techniques (draft, sent, done...)
- Les **dates** (requêtables en live)

**Niveau 3 — Lecture LIVE Odoo (pour les données factuelles précises)**
Quand Raya a besoin d'une donnée factuelle (prix actuel, état du devis, montant
facturé), elle la lit en temps réel via CLIENT_360 ou ODOO_SEARCH. Odoo reste
la seule source de vérité. Jamais de duplication.

**Exemple concret — requête *"chantiers avec SE100K"* :**
1. Niveau 2 trouve la ligne `"2 onduleurs SE100k Manager"` dans D2500019 via
   embedding + BM25
2. Niveau 1 traverse : ligne → appartient au devis D2500019 → client AZEM
3. Niveau 3 va chercher live les vrais montants et état actuel d'AZEM
4. Raya synthétise

**Conséquence budget** : au lieu de 30-50€ one-shot (si on vectorisait tout
bêtement), on descend à ~5-15€ parce qu'on ne vectorise que le sens. Plus
pertinent ET moins cher.

### Coût et ROI

**Coût one-shot réestimé** (après clarification Niveau 1/2/3) :
- 133k articles : nœuds graphe + vectorisation descriptions seules = ~2-3€
- Commentaires (mail.message) sur tous les records : ~2-4€
- Lignes de devis, leads, events (descriptions) : ~2-3€
- Pièces jointes avec extraction texte : ~5-10€
- **Total réestimé : 10 à 20€ one-shot** (au lieu de 30-50€ en vectorisant tout)

**Coût mensuel d'entretien** (webhooks incrémentaux) : ~2-5€/mois

**Budget validé Guillaume** : *« même 500€, cela en vaudrait la peine. Il
faut la solution la plus profonde possible. »* → on fait le choix de la
profondeur, pas de l'économie. Mais la distinction des 3 niveaux nous évite
le gaspillage inutile.

**ROI Guillaume** : comme avant (détection doublons, contrôle qualité devis,
traçabilité complète, proactivité) + **vision Jarvis** : *« Raya voit tout,
peut accéder à tout au moment où elle trouve opportun, recroise toutes les
données pour avoir une réponse précise. Si elle ne voit que 90% des données,
sa réponse ne sera pas efficace. Elle doit vraiment voir l'ensemble. »*

---

## 🏛️ Section 2 — Principes architecturaux non-négociables

### Principe 1 — Introspection avant action

**Règle** : Jamais de vectorisation en aveugle. Toujours d'abord un scan
d'introspection qui liste ce qu'on va traiter, puis une validation humaine
(Guillaume coche), puis l'exécution.

**Conséquence** : deux modes distincts dans le panel admin :
- `Scan` (rapide, ~30s) : découvre et te liste
- `Vectorisation` (long, ~5-15min) : exécute sur ce qui est coché

### Principe 2 — Exhaustivité vérifiable

**Règle** : Pour chaque modèle Odoo actif, on maintient en permanence un
compteur `records_in_odoo` vs `records_in_raya`. Tout écart > 1% déclenche une
alerte système (bandeau admin) et un re-scan ciblé.

**Conséquence** : le panel admin a un dashboard d'intégrité visible en
permanence. Pas besoin de faire confiance à l'intuition — on a la preuve.

### Principe 3 — Classification automatique, override manuel

**Règle** : Le scanner classe automatiquement chaque champ (texte /
relationnel / métadonnée / binaire). Mais Guillaume peut overrider la
classification si la règle automatique ne convient pas (ex : forcer un champ
Selection à être vectorisé comme texte libre).

**Conséquence** : chaque classification de champ est stockée en DB avec la
possibilité de la surcharger via l'admin.

### Principe 4 — Idempotence et reprise

**Règle** : Toute opération (scan, vectorisation) doit être **idempotente** :
relancée 10 fois, elle produit le même résultat sans doublons. Et elle doit
pouvoir **reprendre là où elle s'est arrêtée** en cas d'interruption (timeout,
crash, Railway redeploy).

**Conséquence** : un système de checkpoints en DB (table `scanner_runs`) qui
enregistre l'avancement modèle par modèle.

### Principe 5 — Respect de la structure native

**Règle** : On ne duplique pas les données Odoo dans Raya. On vectorise des
**projections** (embeddings + texte) mais on garde Odoo comme source de
vérité. Si Odoo change, Raya se met à jour. Jamais l'inverse (sauf actions
explicites).

**Conséquence** : on ne stocke jamais de montants, dates, états dans le
graphe. Ces infos sont lues **live** depuis Odoo quand Raya en a besoin. Le
graphe ne contient que des **liaisons** (arêtes) et des **étiquettes**
(labels courts).

### Principe 6 — Universalité cross-source

**Règle** : Tout ce qu'on construit pour Odoo doit être réutilisable pour
d'autres sources (Drive, Teams, SharePoint, Gmail, Salesforce, HubSpot...).
Les concepts (introspection, classification, exhaustivité, idempotence)
doivent être abstraits.

**Conséquence** : la table `semantic_graph_nodes` est déjà universelle
(champ `source`). On ajoute juste une table `connector_schemas` qui stocke le
résultat de l'introspection pour n'importe quelle source.

### Principe 7 — Pas de friction pour Guillaume

**Règle** : Tu ne dois jamais avoir à coder ou à taper du SQL pour faire
fonctionner le scanner. Tout passe par le panel admin : boutons, cases à
cocher, dashboards.

**Conséquence** : on investit massivement dans l'UX admin. Chaque opération
complexe a son bouton, chaque diagnostic a son écran.

### Principe 8 — Mise à jour incrémentale par défaut, full rebuild en exception

**Règle** : Tout changement dans une source (création, modification,
suppression d'un record) déclenche une **mise à jour ciblée** (un seul
record re-vectorisé et re-lié). Jamais un full rebuild. Le full rebuild est
réservé aux cas exceptionnels (première activation, écart d'intégrité
détecté, changement structurel majeur).

**Conséquences techniques** :
1. **Webhooks en temps réel** : chaque source doit avoir un mécanisme de
   notification push vers Raya (Odoo via `base_automation`, Drive via Google
   Push Notifications, etc.)
2. **Queue de vectorisation** : les notifications arrivent dans une queue
   PostgreSQL (table `vectorization_queue`). Un worker asynchrone dépile et
   traite un record à la fois. Évite la congestion en cas de pic.
3. **Idempotence stricte** : traiter 10 fois le même record = 1 seul résultat
   (INSERT ON CONFLICT UPDATE partout)
4. **Delta incrémental** comme filet de sécurité : un CRON nocturne scanne
   les `write_date > last_sync` et traite ce qui a été raté par les webhooks
5. **Audit d'intégrité quotidien** : compare `count_in_odoo` vs `count_in_raya`
   et remonte une alerte si écart > 1%. Tu décides alors si tu relances un
   full rebuild ou pas.

**Conséquence UX** : le panel admin montre en permanence :
- **Queue de vectorisation** : 0-50 records en attente (normal) ou >500
  (anomalie)
- **Dernier webhook reçu** : horodatage du dernier push Odoo
- **Dernier delta incrémental** : horodatage du dernier CRON nocturne
- **Intégrité** : par modèle, le pourcentage `in_raya / in_odoo`

---

**→ STOP. Validation demandée.**

Avant que j'enchaîne sur la Section 3 (cartographie Odoo exhaustive), tu
valides ou tu corriges ces 2 premières sections ? En particulier :

- Est-ce que le **cadre** de ce qu'on va faire est clair ?
- Les **8 principes** sont-ils tous pertinents, ou y en a-t-il que tu veux
  modifier, retirer, ajouter ?
- Quelque chose te choque, te manque, te paraît trop ambitieux ou pas assez ?


---

## 🗺️ Section 3 — Cartographie Odoo exhaustive

Cette section recense **tout ce qui peut vivre dans un Odoo standard** et qui
doit donc être candidat à l'introspection automatique par le scanner. C'est
une cartographie de référence pour nous assurer qu'on n'oublie rien. On la
valide sous-section par sous-section.

### 3.1 — Modèles Odoo classés par catégorie métier

On organise les modèles Odoo en 10 catégories métier. Pour chaque catégorie,
le scanner doit découvrir automatiquement tous les modèles présents chez
Guillaume (y compris les modèles custom).

**Catégorie A — Partenaires et contacts (CRM socle)**
- `res.partner` : contacts, entreprises, prospects, fournisseurs
- `res.partner.category` : étiquettes clients (type, segment)
- `res.partner.industry` : secteurs d'activité
- `res.partner.title` : civilité (M., Mme, Dr.)
- `res.users` : utilisateurs du système (employés Couffrant)
- `res.company` : sociétés gérées (si multi-société)

**Catégorie B — CRM / Prospection**
- `crm.lead` : leads et opportunités
- `crm.stage` : étapes du pipeline (prospect, RDV, étude, devis, signé, perdu)
- `crm.team` : équipes commerciales
- `crm.tag` : tags de qualification
- `crm.lost.reason` : motifs de perte

**Catégorie C — Ventes / Devis / Commandes**
- `sale.order` : devis et commandes
- `sale.order.line` : lignes de devis (chaque article posé)
- `sale.order.template` : modèles de devis pré-établis (important pour
  contrôle qualité)
- `sale.order.template.line` : lignes des modèles
- `sale.order.option` : options optionnelles d'un modèle

**Catégorie D — Facturation et comptabilité**
- `account.move` : factures, avoirs, factures fournisseurs
- `account.move.line` : lignes comptables (écritures)
- `account.payment` : paiements
- `account.payment.term` : conditions de règlement
- `account.tax` : taxes (TVA, etc.)
- `account.journal` : journaux comptables
- `account.account` : plan comptable

**Catégorie E — Produits et stock**
- `product.product` : articles (les 133k de Guillaume)
- `product.template` : modèles de produits (généralisation de product)
- `product.category` : catégories de produits
- `product.pricelist` : listes de prix
- `product.pricelist.item` : règles de prix spécifiques
- `product.supplierinfo` : relation produit-fournisseur (prix achat,
  délais, références fournisseur)
- `uom.uom` : unités de mesure
- `product.attribute` : attributs produits (couleur, taille, puissance...)

**Catégorie F — Kits et nomenclatures (MRP)**
- `mrp.bom` : nomenclatures (structures de kit)
- `mrp.bom.line` : composants d'une nomenclature
- `mrp.routing` : gammes de fabrication
- Nota : c'est ici que se trouvent les **kits Couffrant** (ENT_KIT ...)
  avec leurs composants (modules + optimiseurs + MOE + protections)

**Catégorie G — Planning et interventions**
- `calendar.event` : événements calendrier (RDV, chantiers, visites)
- `calendar.attendee` : participants aux événements
- `calendar.recurrence` : récurrences
- `project.task` : tâches projet (si module projet activé)
- `project.project` : projets

**Catégorie H — Communication (mail)**
- `mail.message` : messages du fil de discussion (sur tous les records !)
- `mail.tracking.value` : historique des modifications de chaque record
- `mail.activity` : activités à faire (rappel, appel, mail)
- `mail.activity.type` : types d'activités
- `mail.followers` : abonnés à un record
- Nota : ces modèles sont **transversaux** — ils s'attachent à TOUS les
  autres records (partner, order, lead, event, task, etc.)

**Catégorie I — Pièces jointes et documents**
- `ir.attachment` : pièces jointes (sur tous les records)
- `documents.document` : documents du module Documents (si installé)
- Nota : on devra extraire le **contenu** des PDF/Word/Excel attachés

**Catégorie J — Signatures et approbations**
- `sign.request` : demandes de signature électronique
- `sign.request.item` : signataires
- `sign.template` : modèles de documents à signer
- `approval.request` : demandes d'approbation
- Nota : extraire aussi le champ `signature` binaire des records signés
  (devis signés, contrats)

**Catégorie K — Custom et inconnus**
Tous les modèles qui n'entrent pas dans les 10 catégories ci-dessus. Le
scanner doit les lister séparément et te proposer de les activer ou non.
Exemples possibles chez Couffrant :
- Modules sectoriels PV (si tu as un module photovoltaïque custom)
- Champs `x_*` ajoutés manuellement
- Modèles de devis avec options métier

---

**→ Validation Section 3.1**

Tu valides cette classification en 11 catégories (A à K) ? Quelque chose te
manque, te semble hors-sujet, ou à déplacer ?
