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


---

## 🗺️ Section 3 — Cartographie Odoo exhaustive (basée sur l'inventaire réel)

**Source** : inventaire live de l'Odoo de Guillaume, 18/04 ~15h30.
**Chiffres** : 717 modèles découverts, 186 non-vides, 627 015 records totaux.
**Stack identifié** : Odoo 16 Community + **module OpenFire** (éditeur français
spécialisé BTP/photovoltaïque, préfixe `of.*`).

### 3.1 — Les 186 modèles classés par priorité de traitement

Règle de tri : combinaison du **volume métier**, de la **densité sémantique**
des champs, et de la **fréquence d'usage** par Raya.

**Priorité 1 — Vectorisation + graphe (16 modèles)**
Le cœur métier. Sans ça, Raya est aveugle sur l'essentiel.

| Modèle | Records | Rôle |
|---|---|---|
| `res.partner` | 1 226 | Clients, prospects, fournisseurs, contacts |
| `crm.lead` | 139 | Leads et opportunités commerciales |
| `sale.order` | 310 | Devis et commandes |
| `sale.order.line` | 3 743 | Lignes de devis (article, qté, prix, description) |
| `sale.order.template` | 9 | **Modèles de devis pré-établis** (contrôle qualité) |
| `sale.order.template.line` | 119 | Lignes des modèles de devis |
| `calendar.event` | 1 162 | **Interventions + comptes-rendus** |
| `product.template` | 133 112 | Catalogue articles (nom, description, réf technique) |
| `of.product.pack.lines` | 5 518 | **Composants des kits Couffrant** (ENT_KIT ...) |
| `product.pack.line` | 715 | Autre système de packs (à investiguer) |
| `mail.message` | 29 139 | Commentaires et notes sur tous les records |
| `mail.tracking.value` | 22 850 | Historique des modifications (qui a changé quoi) |
| `of.planning.tour` | 5 373 | Tournées terrain des équipes |
| `of.planning.tour.line` | 2 753 | Étapes des tournées (adresses GPS) |
| `of.survey.answers` | 5 320 | **Formulaires de relevé chantier remplis** |
| `of.survey.user_input.line` | 687 | Réponses utilisateurs aux formulaires |


**Priorité 2 — Vectorisation + graphe (15 modèles)**
Support métier important pour la proactivité et le suivi.

| Modèle | Records | Rôle |
|---|---|---|
| `account.move` | 408 | Factures clients et fournisseurs |
| `account.move.line` | 2 450 | Lignes comptables (articles facturés) |
| `account.payment` | 175 | Paiements reçus et émis |
| `of.sale.payment.schedule` | 6 203 | **Échéanciers de paiement devis** |
| `of.account.move.payment.schedule` | 434 | Échéanciers sur factures |
| `of.invoice.product.pack.lines` | 1 340 | Lignes de kits facturés |
| `stock.picking` | 206 | Bons de livraison / réception |
| `of.image` | 1 577 | Photos intervention chantier |
| `of.custom.document` + `.field` | 59 | Documents custom métier |
| `of.service.request` + `.stage` + `.type` | 24 | Tickets SAV client |
| `of.planning.intervention.template` + `.line` | 30 | Modèles d'intervention |
| `of.planning.intervention.section` | 8 | Sections de compte-rendu |
| `of.planning.task` | 31 | Tâches planifiées |
| `hr.employee` | 7 | Salariés Couffrant |
| `mail.activity` | 107 | Activités à faire (rappels, appels) |

**Priorité 3 — Graphe uniquement (30 modèles)**
Pas de texte sémantique riche, mais liaisons essentielles pour la navigation.

| Modèle | Records | Rôle |
|---|---|---|
| `product.product` | 133 112 | Variantes articles (pointent vers template) |
| `product.supplierinfo` | 124 607 | Relation produit ↔ fournisseur |
| `res.city.zip` + `res.city` | 87 762 | Référentiel géo (code postal ↔ ville) |
| `res.partner.industry/category/title` | 40 | Étiquettes partners |
| `of.res.partner.phone` | 1 148 | Téléphones multiples des contacts |
| `crm.stage` + `.tag` + `.lost.reason` + `.team` | 24 | Étapes CRM et étiquettes |
| `mail.followers` | 12 576 | Qui suit quel record |
| `calendar.attendee` | 1 792 | Participants aux événements |
| `of.planning.available.slot` | 4 817 | Créneaux disponibles équipes |
| `product.category` + `.tag` + `of.product.brand` | 32 | Taxonomie produits |
| `uom.uom` + `uom.category` | 45 | Unités de mesure |
| `account.account` + `account.journal` + `account.tax` + ... (~15 modèles) | 2 500 | Plan comptable et paramétrage |

**Ignorés (125 modèles restants)**
Infrastructure, logs, dashboards, rapports, imports, paiement en ligne, etc.
Aucune valeur pour Raya.
- Toutes les catégories `M_Technique` (7 modèles) et `Z_Autres` (31 modèles)
- Les `account.*` de paramétrage pur (fiscal.position, edi.format, etc.)
- Les `*.report`, `*.log`, `ks_dashboard_ninja.*`, `base_import.*`

### 3.2 — Champs systématiques transversaux (sur TOUS les records P1 et P2)

Odoo ajoute automatiquement certains champs à tous les modèles hérités de
`mail.thread`, `mail.activity.mixin`, etc. Ces champs sont **critiques** pour
la traçabilité et doivent être captés systématiquement.

**Traçabilité (nœuds d'arêtes dans le graphe)**
- `create_uid` (many2one res.users) → arête `(record) -[:CREATED_BY]-> (user)`
- `write_uid` (many2one res.users) → arête `(record) -[:LAST_MODIFIED_BY]-> (user)`
- `create_date` / `write_date` → metadata sur le nœud

**Abonnés (followers) — qui suit le dossier**
- `message_follower_ids` (one2many mail.followers) → arêtes
  `(record) -[:FOLLOWED_BY]-> (user)` pour chaque follower
- Permet à Raya de répondre *"qui est sur ce dossier Coullet ?"*

**Commentaires (mail.message) — le fil de discussion**
Relation polymorphique via `res_model` + `res_id` (déjà vectorisé en P1).
Chaque commentaire a :
- `author_id` (many2one res.partner) → arête `(message) -[:AUTHORED_BY]-> (partner)`
- `body` (html) → **vectorisé** (c'est le contenu sémantique riche)
- `date` (datetime) → metadata
- `attachment_ids` (many2many ir.attachment) → pièces jointes du message
- `model` + `res_id` → arête `(message) -[:ABOUT]-> (record_parent)`

**Historique de modifications (mail.tracking.value)**
Pour chaque `mail.message` de type tracking, on capte :
- `field_desc` (char) → nom du champ modifié (ex: *"Étape"*)
- `old_value_char/datetime/float` et `new_value_char/datetime/float`
- Permet à Raya de répondre *"le devis est passé de draft à sent le 18/03 par
  Guillaume, puis de sent à sale le 20/03 par Arlène"*

**Pièces jointes (ir.attachment)**
Relation polymorphique via `res_model` + `res_id`. Pour chaque attachment :
- `name` (char), `mimetype` (char) → metadata
- `datas` (binary) → **contenu à extraire et vectoriser**
  - PDF → texte via pdfplumber
  - DOCX → texte via python-docx
  - XLSX → texte via openpyxl
  - Images → OCR via Tesseract (si photos de chantier avec texte)
- Arête `(attachment) -[:ATTACHED_TO]-> (record_parent)`

**Activités à faire (mail.activity)**
- `summary` (char) → **vectorisé**
- `note` (html) → **vectorisé**
- `activity_type_id` → type (appel, mail, RDV)
- `user_id` → arête `(activity) -[:ASSIGNED_TO]-> (user)`
- `date_deadline` → metadata

### 3.3 — Règle universelle pour chaque record traité

**Pour chaque record d'un modèle P1 ou P2, le scanner doit systématiquement :**

1. Créer le **nœud principal** avec label + type
2. Vectoriser les **champs texte sémantiques** définis pour ce modèle
3. Créer les **arêtes sortantes** depuis les many2one vers leurs cibles
4. Traiter les **champs transversaux** :
   - Arêtes `CREATED_BY`, `LAST_MODIFIED_BY`, `FOLLOWED_BY`
   - Fetch + vectorisation des `mail.message` liés (avec auteurs)
   - Fetch + stockage des `mail.tracking.value` (historique)
   - Fetch + extraction + vectorisation des `ir.attachment` liés
   - Fetch + vectorisation des `mail.activity` en cours

**C'est ce traitement transversal systématique qui manquait aux Blocs 1-4
d'hier**. On avait juste le nom et 2-3 champs du record principal, rien du
fil de discussion ni de l'historique.

### 3.4 — Cas spéciaux Couffrant / OpenFire (sujets métier spécifiques)

Ces cas nécessitent un traitement dédié et ne sont pas couverts par la règle
universelle de 3.3.

**Cas 1 — Les kits Couffrant (priorité absolue)**

Découverte clé : les kits **ne sont PAS dans `mrp.bom`** comme l'Odoo standard,
mais dans `of.product.pack.lines` (5 518 records). C'est une table OpenFire.

Structure :
- `parent_product_id` (many2one `sale.order.line`) → ligne de devis qui contient
  le kit
- `product_id` (many2one `product.product`) → composant du kit
- `quantity` (float) → quantité du composant
- `price_unit` (float) → prix unitaire

Traitement spécifique :
- Pour chaque ligne de `of.product.pack.lines`, créer l'arête
  `(sale_order_line) -[:CONTAINS]-> (product)` avec quantité en metadata
- Permet à Raya de répondre *"quels kits utilisent le module DMEGC 450 HBT ?"*
  en traversant `(product) <-[:CONTAINS]- (sale_order_line) -[:BELONGS_TO]->
  (sale_order) -[:HAS_PRODUCT]-> (kit_product)`

**Cas 2 — Les modèles de devis (contrôle qualité)**

`sale.order.template` (9 modèles) + `sale.order.template.line` (119 lignes)

Objectif : permettre à Raya de comparer un devis réel à son modèle source et
détecter les écarts. Ex : *"Arlène a oublié le kit maintenance sur ce devis
par rapport au modèle standard"*.

Traitement :
- Vectoriser chaque template + ses lignes
- Pour chaque `sale.order`, détecter le template source (champ
  `sale_order_template_id` sur `sale.order`)
- Créer arête `(sale_order) -[:BASED_ON]-> (template)`
- Raya peut alors faire du diff template ↔ order

**Cas 3 — Tournées GPS et planning terrain**

`of.planning.tour` (5 373) + `.line` (2 753) + `of.planning.available.slot` (4 817)

Contient les tournées avec adresses GPS des interventions. Champs critiques :
- `of.planning.tour.line.address_city/address_zip` → géoloc
- `distance_one_way`, `duration_one_way` → km et temps de trajet
- `endpoint_geometry_data` (text) → données GeoJSON du trajet
- `employee_id` (many2one) → qui fait la tournée

Traitement :
- Vectoriser les tournées pour permettre *"quelles tournées près de Guéret
  cette semaine ?"*
- Arêtes vers `res.partner` (client visité) et `hr.employee` (technicien)

**Cas 4 — Formulaires de relevé chantier**

`of.survey.*` (ensemble ~22 000 records)
- `of.survey.survey` → définition du questionnaire (ex : *"Étude préalable PV"*)
- `of.survey.question` → questions posées
- `of.survey.user_input` → session de réponse (lié à un lead/intervention)
- `of.survey.user_input.line` → réponse à une question donnée
- `of.survey.answers` → réponses texte libre des utilisateurs

Mine d'or pour Raya : les réponses contiennent les caractéristiques techniques
relevées chez le client (type de toiture, orientation, puissance cible, etc.).

Traitement : vectoriser les `user_input.line` + `answers` avec liaison vers
le lead ou l'intervention parent.

**Cas 5 — Signatures électroniques YouSign**

`of.yousign.request.template` + `.signatory` (2 + 1 records)

Peu volumineux mais important pour la traçabilité juridique.
Sur chaque devis signé, capter :
- Template de signature utilisé
- Signataires (partner ou email)
- Date de signature

Pour l'instant volume faible → traitement simple en arêtes, pas de
vectorisation.

**Cas 6 — Images intervention**

`of.image` (1 577 records) avec champs `image_1024`, `image_1920` (binary) et
`caption` (text), liés via `intervention_id` (many2one calendar.event).

Traitement :
- Vectoriser le `caption` (description de la photo)
- Créer arête `(image) -[:FROM_INTERVENTION]-> (calendar.event)`
- Option future : OCR sur les images de chantier pour extraire les textes
  visibles (repères techniques, numéros de série équipements)

**Cas 7 — Documents custom et DMS**

`of.custom.document` (3) + `.field` (56) + `of.dms.virtual_file_report` (7)

Petit volume aujourd'hui mais à surveiller. Ce sont des documents que
Guillaume peut créer avec des champs personnalisés (ex : fiche technique
produit, rapport d'intervention custom).

Traitement : vectoriser le contenu + créer arêtes vers les entités liées.

---

**→ Fin de la Section 3. Validation demandée.**

Tu valides cette cartographie complète ?
- Les **3 niveaux de priorité** (P1/P2/P3) te conviennent ?
- Les **champs transversaux** (3.2/3.3) capturent bien ta phrase *"qui a fait
  le devis, qui l'a modifié, qui le suit"* ?
- Les **7 cas spéciaux** (3.4) sont-ils tous pertinents ?
- Quelque chose manque ou doit être déplacé ?

---

## ⚙️ Section 4 — Stratégie d'introspection technique

Cette section décrit **COMMENT** on construit le scanner, au niveau code.
Objectif : un moteur générique piloté par configuration, pas du code en dur
modèle par modèle.

### 4.1 — Architecture en 3 couches

```
┌─────────────────────────────────────────────────────────┐
│  COUCHE 1 : Orchestrateur central                       │
│  - Lit le manifest (config JSON en DB)                  │
│  - Planifie les runs (init / delta / rebuild)           │
│  - Gère checkpointing et reprise                        │
└─────────────────────────────────────────────────────────┘
               ↓
┌─────────────────────────────────────────────────────────┐
│  COUCHE 2 : Adaptateur Odoo                             │
│  - Fetch paginé par modèle (batch 100 records)          │
│  - Résolution relations (many2one, one2many, m2m)       │
│  - Fetch transversal (mail.message, tracking, attach)   │
└─────────────────────────────────────────────────────────┘
               ↓
┌─────────────────────────────────────────────────────────┐
│  COUCHE 3 : Processeur de record                        │
│  - Construit le texte composite à vectoriser            │
│  - Appelle OpenAI embedding (batch 100 textes)          │
│  - Écrit en DB (nodes + edges + semantic_content)       │
└─────────────────────────────────────────────────────────┘
```

Chaque couche est **indépendante** et **réutilisable** pour d'autres sources
(Drive, Teams) en changeant juste la Couche 2.

### 4.2 — Le manifest (config JSON stockée en DB)

Pour chaque modèle actif, un objet JSON définit ce qu'on en fait.
Table `connector_schemas` :
```json
{
  "model": "sale.order",
  "enabled": true,
  "priority": 1,
  "vectorize_fields": ["name", "client_order_ref", "note", "partner_id.name"],
  "graph_edges": [
    {"field": "partner_id", "type": "BELONGS_TO_CLIENT"},
    {"field": "user_id", "type": "ASSIGNED_TO"},
    {"field": "order_line", "type": "HAS_LINE", "one2many": true},
    {"field": "sale_order_template_id", "type": "BASED_ON"}
  ],
  "metadata_fields": ["amount_total", "state", "date_order"],
  "handle_mail_thread": true,
  "handle_attachments": true,
  "handle_trackings": true
}
```
Le manifest est généré automatiquement à partir de l'inventaire (Section 4.3)
puis éditable via panel admin.

### 4.3 — Génération auto du manifest initial

Règle de classification par type de champ Odoo :

| Type Odoo | Classification par défaut |
|---|---|
| `char`, `text`, `html` | → `vectorize_fields` (si label sémantique) |
| `many2one` | → `graph_edges` (arête sortante) |
| `one2many`, `many2many` | → `graph_edges` (arêtes multiples) |
| `selection`, `boolean` | → `metadata_fields` |
| `integer`, `float`, `monetary` | → `metadata_fields` |
| `date`, `datetime` | → `metadata_fields` |
| `binary` | → `handle_attachments` si `name`/`mimetype` |
| `reference` | → `graph_edges` polymorphique |

Filtres automatiques pour éviter le bruit :
- Champs `create_uid`, `write_uid`, `create_date`, `write_date` → traitement
  transversal, pas dans metadata
- Champs `*_tag_ids`, `activity_*`, `message_*_id` → ignorer (gérés par
  transversaux)
- Champs techniques (`_uid`, `__last_update`, `access_token`) → ignorer


### 4.4 — Pipeline de vectorisation par modèle

Pour chaque modèle activé, une boucle unique :

```
pour chaque batch de 100 records :
    1. Fetch Odoo : tous les champs déclarés dans le manifest
    2. Fetch transversal : mail.message + mail.tracking.value + ir.attachment
    3. Pour chaque record :
       a. Construire texte_composite (concat des vectorize_fields)
       b. Construire les arêtes depuis graph_edges
    4. Appel OpenAI embedding (1 call pour les 100 textes)
    5. INSERT ON CONFLICT en DB :
       - semantic_graph_nodes (1 nœud par record)
       - semantic_graph_edges (N arêtes par record)
       - odoo_semantic_content (1 chunk par record)
    6. Checkpoint : sauver last_processed_id en DB
    7. Rate limit : pause 200ms entre batches
```

**Texte composite** : assemblage structuré des champs pour donner du contexte
à l'embedding. Exemple pour `sale.order` :
```
Devis S01545 de [AZEM Société].
Référence client : PROJ-2026-017.
Note : "Attente retour ENEDIS pour augmentation puissance".
Commercial : Arlène Desnoues.
Modèle source : PV Résidentiel 9kWc Toiture.
Lignes : 2x SE100k Manager, 1x Module DMEGC 450 HBT, 1x MOE1.
```

L'embedding de ce texte est **beaucoup plus précis** qu'un simple embedding
du `name` seul.

### 4.5 — Traitement transversal (mail.thread)

Pour chaque record d'un modèle avec `handle_mail_thread: true` :

**a) Fetch des messages**
```python
messages = odoo_call("mail.message", "search_read",
    domain=[("model", "=", model), ("res_id", "=", record_id)],
    fields=["id", "body", "author_id", "date", "attachment_ids"])
```
Pour chaque message :
- Nettoyer le HTML → texte brut
- Vectoriser (nœud `message` + chunk sémantique)
- Créer arêtes `(message) -[:AUTHORED_BY]-> (partner)` et
  `(message) -[:ABOUT]-> (record)`

**b) Fetch des trackings**
```python
trackings = odoo_call("mail.tracking.value", "search_read",
    domain=[("mail_message_id", "in", message_ids)],
    fields=["field_desc", "old_value_char", "new_value_char", ...])
```
Pour chaque tracking : stocker en metadata sur le nœud message (pas
d'embedding, c'est de la donnée structurée).

**c) Fetch des followers**
Arêtes `(record) -[:FOLLOWED_BY]-> (partner)`.

### 4.6 — Extraction de contenu des pièces jointes (ir.attachment)

Pour chaque attachment lié au record :

| Mimetype | Extraction |
|---|---|
| `application/pdf` | `pdfplumber` → texte + tables |
| `application/vnd.openxmlformats-officedocument.wordprocessingml.document` | `python-docx` → paragraphes |
| `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet` | `openpyxl` → cellules |
| `text/plain`, `text/csv` | lecture directe |
| `image/*` | OCR Tesseract (optionnel, désactivable) |
| autres | skip avec warning en log |

**Chunking** : si texte extrait > 8000 caractères, découpe en chunks de 2000
chars avec overlap de 200, chaque chunk vectorisé indépendamment avec le
même `attachment_id` source.

**Arête** : `(chunk) -[:EXTRACTED_FROM]-> (attachment) -[:ATTACHED_TO]-> (record)`

### 4.7 — Checkpointing et reprise après interruption

Table `scanner_runs` (nouvelle) :
```
run_id          : UUID
source          : 'odoo' | 'drive' | 'teams' | ...
run_type        : 'init' | 'delta' | 'rebuild' | 'audit'
status          : 'pending' | 'running' | 'paused' | 'ok' | 'error'
started_at      : timestamp
finished_at     : timestamp nullable
params          : JSON (filtres, modèles sélectionnés)
progress        : JSON {model: {last_id, done, total}}
error           : text nullable
```

**Reprise** : si un run est marqué `paused` ou `error`, le prochain démarrage
reprend à `last_id + 1` pour chaque modèle, sans re-traiter ce qui est fait.

**Garantie d'idempotence** : tous les INSERT utilisent `ON CONFLICT (source,
source_id) DO UPDATE` → re-traiter 10 fois le même record = 1 seul nœud,
mis à jour.

### 4.8 — Concurrence et limites

**Limites à respecter** :
- **Odoo XML-RPC** : pas de limite technique mais chaque appel = ~200-500ms,
  donc fetch sériel par défaut
- **OpenAI embeddings** : 3000 requêtes/min et 1M tokens/min (plan Tier 1)
- **PostgreSQL** : pas de limite à ces volumes

**Stratégie** :
- 1 seul worker thread en mode normal (évite surcharge Odoo prod)
- Batch OpenAI de 100 textes par appel (réduit le nombre de calls)
- Rate limiting : max 10 calls OpenAI/sec
- Pour un full rebuild gros volume (133k articles) : option multi-worker à 4
  threads max, lancé manuellement via panel admin avec warning de durée

**Temps estimé pour un full rebuild complet** :
- P1 + P2 + P3 = ~200k records dont ~50k vectorisés
- 50k records / 100 par batch / 10 req/sec OpenAI = ~50 minutes d'embeddings
- + ~30 minutes de fetch Odoo en parallèle
- **Total : ~1h15 pour un full rebuild complet** (fait rarement)

### 4.9 — Observabilité (dashboard admin)

Le panel admin doit afficher en temps réel :
- **Runs actifs** : nom, type, progression, estimation restante
- **Dernier run réussi par source** : horodatage, volume, durée
- **Intégrité par modèle** : compte Odoo vs compte Raya, alerte si écart >1%
- **Queue de webhooks** : records en attente d'être vectorisés après push Odoo
- **Erreurs récentes** : derniers échecs avec contexte pour debug

Tous ces indicateurs sont stockés en DB et exposés via endpoints `/admin/scanner/*`.

---

**→ Fin de la Section 4. Validation demandée.**

Tu valides cette stratégie technique ?
- L'architecture en **3 couches** (orchestrateur / adaptateur / processeur) ?
- Le **manifest JSON** comme configuration centrale (modifiable par toi) ?
- Le **pipeline en 7 étapes** par batch ?
- Le **traitement transversal** (messages, trackings, attachments) ?
- Les **estimations de durée** (~1h15 pour full rebuild) ?

Si oui, je lance la Section 5 (phasage de développement concret + Section 6
questions ouvertes). Sinon dis-moi ce qui coince.

---

## 🚀 Section 5 — Phasage de développement

Découpage en **10 phases livrables** où chaque phase produit de la valeur
utilisable, même si on s'arrête au milieu. Total estimé : ~35-40h de dev.

### Phase 1 — Fondations (3h)
- Migrations DB : `scanner_runs`, `connector_schemas`, `vectorization_queue`
- Module `app/scanner/orchestrator.py` (squelette)
- Module `app/scanner/adapter_odoo.py` (fetch pagine + transversaux)
- Module `app/scanner/processor.py` (texte composite + embedding + write)
- Endpoint admin `/admin/scanner/health` (vérifie que tout est en place)

**Livrable** : socle technique prêt, pas encore de scan réel.

### Phase 2 — Manifest auto-généré (2h)
- Fonction `generate_manifest_from_introspection()` qui prend le résultat
  d'introspection et produit le manifest JSON pour tous les modèles P1 et P2
- UI panel admin : "Manifest de vectorisation" — éditable case par case
- Bouton "Appliquer le manifest"

**Livrable** : tu peux voir et modifier le plan avant de lancer quoi que ce soit.

### Phase 3 — Vectorisation P1 sans transversaux (4h)
- Run pour les 16 modèles P1 en mode basique (texte composite + embedding +
  nœud + arêtes many2one)
- **Pas encore** les messages/trackings/attachments (phase 5)
- Dashboard de progression en temps réel

**Livrable** : Raya voit les entités principales avec leurs relations
directes. Test possible sur cas réels (SE100K, Coullet/Glandier).

### Phase 4 — Vectorisation P2 et P3 (3h)
- Même logique que P3 pour les modèles P2 (support)
- Pour P3 : nœuds + arêtes seulement (pas de vectorisation)

**Livrable** : graphe complet avec 200k+ nœuds, Raya peut traverser.

### Phase 5 — Traitement transversal (5h)
- Fetch + vectorisation de `mail.message` pour chaque record P1/P2
- Stockage de `mail.tracking.value` en metadata
- Arêtes `FOLLOWED_BY`, `CREATED_BY`, `LAST_MODIFIED_BY`
- Intégration des `mail.activity` en cours

**Livrable** : Raya connaît l'historique complet de chaque dossier et qui a
fait quoi.

### Phase 6 — Extraction pièces jointes (4h)
- Ajout dépendances : `pdfplumber`, `python-docx`, `openpyxl`
- Module `app/scanner/attachment_extractor.py`
- Chunking + vectorisation des contenus extraits
- OCR Tesseract en option (phase ultérieure si besoin)

**Livrable** : contenus des PDF/DOCX/XLSX recherchables sémantiquement.

### Phase 7 — Cas spéciaux Couffrant (4h)
- **Kits** via `of.product.pack.lines` — arêtes `CONTAINS`
- **Modèles de devis** + arête `BASED_ON` sur les sale.order
- **Tournées GPS** `of.planning.tour.*` avec géocodage
- **Formulaires de relevé** `of.survey.*` — vectorisation des réponses
- **Signatures YouSign** — traçabilité juridique
- **Images intervention** `of.image` — vectorisation des captions

**Livrable** : tous les cas métier spécifiques couverts.

### Phase 8 — Dashboard d'observabilité (3h)
- Page `/admin/scanner/dashboard` avec :
  - Runs actifs (avec barre de progression)
  - Dernier run par source + durée + nb records
  - Intégrité par modèle (count_odoo vs count_raya)
  - Queue de webhooks
  - Erreurs récentes
- Rafraîchissement auto toutes les 10s

**Livrable** : tu vois tout sans me demander.
</content>
### Phase 9 — Audit d'intégrité automatique (2h)
- CRON hebdomadaire qui compare compte Odoo vs compte Raya par modèle
- Si écart > 1%, alerte dans bandeau admin + déclenchement rebuild ciblé auto
- Logs détaillés des écarts (quel modèle, combien, depuis quand)

**Livrable** : garantie d'exhaustivité auto-vérifiée.

### Phase 10 — Intégration webhooks Odoo au nouveau pipeline (2h)
- Le webhook existant `app/routes/webhook_odoo.py` est connecté à la
  `vectorization_queue` plutôt qu'au bloc 2 d'hier
- Worker qui dépile la queue toutes les 5s
- Idempotence : si le même record arrive 10 fois, il n'est traité qu'une fois

**Livrable** : temps réel opérationnel, modifs Odoo reflétées dans Raya en <5s.

### Phase bonus — Migration propre depuis les Blocs 1-4 d'hier (3h)
Les tables `odoo_semantic_content` et certains chunks existent déjà. On doit :
- Garder ce qui marche (structure tables, API hybrid_search)
- Remplacer la logique de vectorisation par le nouveau scanner universel
- Purger les anciens chunks incomplets (kits non traités) et les régénérer
- Vérifier que `retrieval.py` continue de fonctionner avec les nouveaux nœuds

### Récapitulatif temps

| Phase | Effort | Cumul |
|---|---|---|
| 1 — Fondations | 3h | 3h |
| 2 — Manifest | 2h | 5h |
| 3 — Vectorisation P1 | 4h | 9h |
| 4 — P2 + P3 | 3h | 12h |
| 5 — Transversaux | 5h | 17h |
| 6 — Pièces jointes | 4h | 21h |
| 7 — Cas spéciaux | 4h | 25h |
| 8 — Dashboard | 3h | 28h |
| 9 — Audit intégrité | 2h | 30h |
| 10 — Webhooks | 2h | 32h |
| Bonus — Migration | 3h | 35h |

**Total : ~35h de dev**, étalés sur plusieurs sessions. Chaque phase est
testable et livre de la valeur indépendamment.

---

## ❓ Section 6 — Questions ouvertes à trancher

Avant de coder la Phase 1, j'ai besoin de ton arbitrage sur **10 questions
techniques précises**. Ce sont des choix architecturaux qui m'engagent pour
la suite.

### Q1 — product.product vs product.template
Chez toi, `product.template` et `product.product` ont le **même volume**
(133 112) → chaque template a 1 seule variante. Vectoriser les deux =
doublons.

**Propositions** :
- **A** — Vectoriser `product.template`, créer nœud léger pour `product.product`
  avec arête `VARIANT_OF` (recommandé)
- **B** — Vectoriser les deux si tu penses qu'il peut y avoir des variantes
  différentes dans le futur

### Q2 — Profondeur des mail.message
29 139 messages, c'est beaucoup. Certains sont automatiques (log technique
Odoo), d'autres sont des vrais commentaires utiles.

**Propositions** :
- **A** — Tout vectoriser, sans filtre (exhaustif, ~5€ OpenAI, plus lent)
- **B** — Filtrer sur `message_type in ['comment', 'email']` pour éviter les
  notifications système (recommandé)
- **C** — Seulement les messages liés aux records P1 (plus restrictif)

### Q3 — OCR sur les images
`of.image` a 1 577 photos de chantier. L'OCR Tesseract sur chacune coûterait
du temps (~30 min de traitement).

**Propositions** :
- **A** — OCR activé par défaut (extrait les numéros de série, références
  visibles sur les équipements installés)
- **B** — OCR désactivé pour l'instant, on voit le besoin plus tard
  (recommandé pour gagner du temps)

### Q4 — Que faire des Blocs 1-4 d'hier
Les tables `odoo_semantic_content` et `semantic_graph_nodes` existent déjà
avec des chunks partiels (devis sans leurs lignes détaillées, pas de kits,
pas de commentaires).

**Propositions** :
- **A** — Purger à fond et reconstruire depuis zéro (le plus propre)
- **B** — Garder les tables, remplacer seulement la logique, re-vectoriser
  par-dessus (recommandé — les INSERT ON CONFLICT gèrent)
</content>
### Q5 — Modèle d'embedding OpenAI
Aujourd'hui on utilise `text-embedding-3-small` (1536 dims, ~0.02€/M tokens).

**Propositions** :
- **A** — Garder `text-embedding-3-small` (rapport qualité/prix optimal,
  largement suffisant pour du français métier — recommandé)
- **B** — Passer à `text-embedding-3-large` (3072 dims, ~0.13€/M tokens, +10%
  qualité, x4 stockage) → pertinent si qualité insuffisante

### Q6 — Déclenchement du rebuild après audit
Quand l'audit détecte un écart >1%, faut-il :

**Propositions** :
- **A** — Lancer le rebuild automatiquement sans te demander (recommandé,
  pas de friction)
- **B** — Juste afficher une alerte et attendre que tu cliques "Rebuild"
- **C** — Auto pour écarts <10%, manuel pour écarts >10%

### Q7 — Suppressions côté Odoo
Quand un record est supprimé dans Odoo (via le webhook `unlink` ou détecté
par delta), que fait-on côté Raya ?

**Propositions** :
- **A** — Soft delete (marquer `deleted_at`, garder le nœud et ses arêtes)
  pour permettre à Raya de répondre *"ce devis existait mais a été supprimé
  le X"*
- **B** — Hard delete complet (plus propre mais perd l'historique)

**Recommandation** : **A**, avec les chunks vectorisés marqués comme "stale"
(plus proposés dans les recherches).

### Q8 — Multi-tenant
Aujourd'hui, un seul tenant (Couffrant). Demain, plusieurs clients auront
chacun leur Odoo.

**Propositions** :
- **A** — Le scanner est par-tenant dès maintenant (isolation stricte, chaque
  tenant ne voit que ses données — recommandé)
- **B** — Scanner global, on gèrera l'isolation plus tard

**Recommandation** : **A**. Le modèle `semantic_graph_nodes` a déjà un champ
`tenant_id` (ou doit l'avoir), on le respecte systématiquement.

### Q9 — Provider d'extraction PDF
Plusieurs options pour l'extraction PDF :

**Propositions** :
- **A** — `pdfplumber` (pure Python, gratuit, qualité moyenne sur PDFs
  complexes — recommandé pour démarrer)
- **B** — Azure Document Intelligence (cloud, meilleure qualité sur tableaux
  et formulaires, ~1.5€/1000 pages)
- **C** — Claude Vision via API (excellent sur PDFs scannés + tableaux, mais
  plus cher : ~3€/1000 pages)

**Recommandation** : **A** d'abord, migration vers **B** ou **C** si la
qualité pose problème.

### Q10 — Phase 0 avant tout : la Section 4.3 mentionnée précédemment
Je n'ai pas encore proposé **comment tu valides le manifest** avant le
premier scan. Deux options :

**Propositions** :
- **A** — Le manifest est appliqué automatiquement (pas de validation
  manuelle), tu peux le modifier plus tard si besoin
- **B** — Tu valides le manifest modèle par modèle dans une UI dédiée avant
  le scan (plus lent mais sûr — recommandé pour la première fois)

---

## 🎯 Validation finale du plan complet

Le plan Scanner Universel fait **~900 lignes de documentation structurée**.
Il couvre :

- **Section 1** : Contexte, objectif, distinction 3 niveaux, budget
- **Section 2** : 8 principes non-négociables
- **Section 3** : Cartographie Odoo basée sur inventaire réel (186 modèles)
- **Section 4** : Stratégie technique (architecture 3 couches, manifest,
  pipeline, transversaux)
- **Section 5** : Phasage en 10+1 phases (~35h de dev)
- **Section 6** : 10 questions à trancher avant le code

**Prochaine étape** : tu réponds aux 10 questions (même brièvement, je peux
proposer des défauts raisonnables), puis on commit le plan final et on
attaque **Phase 1 — Fondations** en code.

Si tu veux répondre aux 10 questions en une fois via "mes réponses à Q1 = A,
Q2 = B, etc." c'est le plus efficace. Tu peux aussi dire "suis tes
recommandations partout" et j'applique les défauts.
</content>
---

## ✅ Section 7 — Arbitrages validés par Guillaume (18/04 ~16h30)

Les 10 questions ouvertes ont été tranchées. Ces choix deviennent des
engagements du plan et seront implémentés dans la Phase 1.

| Q | Décision | Rationale retenue |
|---|---|---|
| Q1 | **A** — `product.template` only + arête `VARIANT_OF` sur `product.product` | Pas de doublons, évolutif si variantes arrivent |
| Q2 | **A** — Tout `mail.message` vectorisé, y compris logs système auto | Guillaume veut la vision Jarvis totale ; même les logs système peuvent être utiles pour la proactivité et l'automatisation des actions |
| Q3 | **B** — OCR `of.image` désactivé au démarrage, activable plus tard | Gain de temps initial, activable en un bouton si le besoin se manifeste |
| Q4 | **A** — Purge complète des tables `odoo_semantic_content` / `semantic_graph_nodes` avant rebuild | Guillaume préfère la propreté, accepte une pause de 30 min de service |
| Q5 | **A** — `text-embedding-3-small` (1536 dims, ~0.02€/M tokens) | Suffisant pour démarrer ; migration vers `large` possible si qualité insuffisante |
| Q6 | **A** — Rebuild automatique dès détection d'écart par l'audit | Zéro friction, auto-correction |
| Q7 | **A** — Soft delete (marquer `deleted_at`, garder le nœud) | Traçabilité complète : Raya peut dire *"ce devis existait mais a été supprimé"* |
| Q8 | **A** — Multi-tenant strict dès maintenant | Validé commercialement par Guillaume : *« la personnalisation par tenant est ce qui fera la force de Raya et justifiera son prix »* ; chaque tenant aura ses propres outils (pas forcément Odoo) |
| Q9 | **A puis C** — `pdfplumber` pour démarrer, migration vers Claude Vision si qualité insuffisante sur certains PDFs | Couvre 90% des cas gratuitement, migration ciblée si besoin |
| Q10 | **A** — Manifest appliqué automatiquement au premier scan, modifiable via panel admin après | Validé par échange : Guillaume reconnaît que la classification auto des champs est mécanique (pas de jugement humain nécessaire), et que quelques euros de vectorisation en trop valent mieux que 1500 cases à cocher |

### Impacts budgétaires finaux de ces choix

- Coût one-shot rebuild initial : **~20-30€** (augmentation de ~10€ vs estimation Section 1 à cause de Q2 "tout vectoriser")
- Coût mensuel d'entretien via webhooks : **~3-6€/mois**
- Coût additionnel multi-tenant : négligeable (juste du filtrage SQL)
- **Total 1er mois : ~25-35€** — dans la fourchette "investissement modeste".

### Engagements techniques pour la Phase 1

Ces arbitrages se traduiront dans le code par :
1. Schéma `manifest` avec un champ `mail_message_filter: "all"` (et non `"comment_only"`)
2. Schéma `product.product` réduit au nœud graphe + arête `VARIANT_OF`
3. Job de purge `admin/scanner/purge-all` exécuté en tout début de rebuild
4. Soft delete : ajout d'un champ `deleted_at` sur `semantic_graph_nodes` + filtre dans les recherches
5. Respect strict de `tenant_id` dans tous les INSERT et SELECT
6. Classe `PDFExtractor` avec méthode `extract()` qui utilise pdfplumber par défaut + point d'extension pour Claude Vision
7. Ajout de `text-embedding-3-small` dans les env vars (déjà actif)
8. Pas d'UI de validation manifest avant scan (Phase 2 simplifiée)

---

**→ Le plan Scanner Universel Odoo est COMPLET et VALIDÉ.**

Prochaine étape : **Phase 1 — Fondations** (3h de code estimé), qui
implémente :
- Migrations DB (`scanner_runs`, `connector_schemas`, `vectorization_queue`)
- Module `app/scanner/orchestrator.py`
- Module `app/scanner/adapter_odoo.py`
- Module `app/scanner/processor.py`
- Endpoint `/admin/scanner/health`

Sans ces fondations, rien ne peut tourner. C'est l'étape indispensable
avant tout le reste.
