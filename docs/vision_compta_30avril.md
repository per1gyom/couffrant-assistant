# Vision Module Compta Raya — `accounting_engine`

**Statut :** Vision documentée le 30/04/2026 nuit — pas encore implémenté
**Auteurs :** Guillaume + Claude (échange du 30/04 nuit, 4 itérations)
**Objectif :** Capturer la vision complète et propre pour que rien ne se
perde quand on y reviendra (semaines/mois plus tard).

---

## 🎯 Thèse fondamentale (insight Guillaume)

> Le graphe et la vectorisation des données, c'est la clé de Raya.
> Si la vectorisation et le graphe sont performants, l'outil sera efficace.
> Parce que derrière, ce n'est pas Raya qui pense — c'est Claude (Sonnet/Opus).
> Claude est puissant si on lui donne :
>   1. Des prompts efficaces
>   2. Des outils précis
>   3. Un graphe riche
>   4. Une vectorisation efficace
>   5. Un graphe RAG

Le module compta n'est qu'**un cas d'usage de plus** qui exploite cette
infrastructure. Pas un produit séparé. Pas un mini-Pennylane interne.

---

## 🎯 Périmètre clairement défini

### Ce que c'est

> Un OUTIL Raya pour aider à la pré-compta.
> Sa mission : livrer au comptable un dossier mensuel propre, rangé,
> lettré, où il n'a plus qu'à passer les écritures dans SON logiciel.

### Ce que ce n'est PAS (volontairement hors périmètre)

```
✗ Pas de plan comptable interne
✗ Pas de FEC normé pour le fisc
✗ Pas d'écritures comptables
✗ Pas de TVA déclarée
✗ Pas de bilan / liasse fiscale
✗ Pas de remplacement du comptable
✗ Pas un mini-Pennylane

→ Tout ça reste le travail de l'expert-comptable.
  Raya l'aide juste à recevoir un dossier propre.
```

### Insight commercial

> Le comptable facture à l'heure. Si Raya fait gagner des heures de
> ressaisie au comptable, le client paie moins cher. C'est la vraie
> valeur : pas remplacer le comptable, mais lui livrer un dossier
> **prêt à valider** au lieu d'un dossier **à ressaisir**.

---

## 🏗️ Architecture en 2 modules distincts

### Module 1 : `accounting_engine` (feature flag, natif Raya)

Le moteur de pré-compta. Quand activé sur un tenant, **enrichit le graphe
sémantique de Raya** avec de nouveaux types de nœuds et d'edges. Le moteur
vit dans Raya, comme une extension.

### Module 2 : `accounting_connector` (connexion, futur lointain)

Connexion vers logiciel comptable tiers (Pennylane, Cegid, EBP, Sage...).
Pour V2 ou plus tard. Pas une priorité immédiate.

→ C'est une **connexion** (`tenant_connections`), comme Outlook/Drive.

---

## 💎 Idée centrale : la compta comme extension du graphe sémantique

Quand `accounting_engine = ON`, Raya enrichit son graphe avec :

**Nouveaux types de nœuds :**
- `BankStatement` — un relevé de compte (PDF banque ou CSV)
- `BankTransaction` — une ligne de relevé
- `Justification` — un ticket, facture, justificatif

**Nouveaux types d'edges :**
- `contains` — BankStatement → BankTransaction
- `justified_by` — BankTransaction → Justification (le lettrage)
- `extracted_from` — Justification → Email / File (origine du document)
- `supplier` — Justification → Contact (lien vers le fournisseur connu)
- `paid_to` — BankTransaction → Contact (lien vers le bénéficiaire)

**Bénéfice direct : Raya peut répondre à des questions naturelles**

```
"Combien j'ai dépensé chez Castorama en avril ?"
   → Query graphe : Castorama (Contact) ← supplier ← Justifs ← BankTransactions
   → Somme automatique

"Toutes mes factures EDF de l'année ?"
   → Query graphe : EDF (Contact) ← Justifs ← Files

"Cette ligne de 4 800€ du 15 avril, ça correspond à quoi ?"
   → Query graphe : BankTransaction (4800€, 15/04) → justified_by → liste

"Cette facture Castorama, je l'ai bien payée ?"
   → Query graphe : Justif → justified_by → BankTransaction (si présente = payée)

"Quelles factures n'ont pas encore été payées ?"
   → Query graphe : Justifs sans edge justified_by sortant
```

**Bénéfice indirect : aucune duplication**

Les fournisseurs (Contact) sont les mêmes dans Outlook, Drive, Vesta,
Odoo et compta. Le graphe est unifié.

---

## 📥 Workflow utilisateur cible

### Brique 1 : Collecte au fil de l'eau (silencieuse, permanente)

```
Comportement permanent une fois activé :

  Quand un mail arrive avec une PJ qui ressemble à une facture/justif :
    1. Détection IA : "ce mail/PJ contient-il une justif comptable ?"
    2. Selon règle utilisateur :
       • Auto-classer si fournisseur reconnu (règle apprise)
       • Demander à l'utilisateur sinon (proposition)
    3. Si validé :
       • Création nœud Justification dans le graphe
       • Edge extracted_from vers le mail source
       • Edge supplier vers le Contact si reconnu
       • Stockage du fichier dans Drive : compta_YYYY-MM/
       • Renommage : "2026-04-12_125.00€_EDF.pdf"
       • Extraction métadonnées (date, montant TTC, HT, TVA, n° facture)
    4. Si l'utilisateur dit "toutes les factures de X comme ça toujours"
       → Création règle dans aria_rules pour les fois suivantes

Comportement adaptatif :
  • La 1ère facture EDF → demande à l'utilisateur où la classer
  • L'utilisateur dit "compta du mois courant"
  • L'utilisateur dit "toutes les factures EDF, fais-le toujours"
  • La 2ème facture EDF arrive → Raya classe automatiquement, sans demander
  • La 3ème, idem
  
→ Cohérent avec la philosophie Raya : règles apprises adaptatives
```

### Brique 2 : Check-up à la demande (conversationnel)

L'utilisateur conduit, Raya exécute :

```
"Raya, scan le dossier compta d'avril"
   → Parcourt le dossier Drive
   → OCR des fichiers non encore traités
   → Crée/maj les nœuds Justification manquants

"Raya, voici le relevé d'avril" (upload)
   → Crée nœud BankStatement
   → Parse les transactions, crée les BankTransaction
   → Lance le rapprochement automatique
   → Crée les edges justified_by

"Raya, dis-moi ce qui manque"
   → Query : transactions sans edge justified_by
   → Catégorisation :
     🔴 Vraiment manquant (à scanner/demander)
     🟢 Pas de justif requis (frais bancaire connu)
     🔵 Récurrent (lien vers contrat)

"Raya, renomme tout dans l'ordre du relevé"
   → Reorder par date + montant
   → Renommage avec lettre A, B, C selon ordre relevé
   → Annotation PDF du relevé (coches + lettres)

"Raya, prépare le dossier final pour le comptable"
   → Compilation ZIP :
     ├── 00_index.pdf       (synthèse du mois)
     ├── 01_releve_annote.pdf
     └── justifs/
         ├── 2026-04-01_125.00€_EDF_A.pdf
         ├── 2026-04-12_89.00€_CASTO_B.pdf
         └── ...
   → Tu envoies ce dossier au comptable. Fin.
```

---

## 💎 Subtilités fonctionnelles à gérer

Liste consolidée de ce que Raya doit savoir traiter :

### 1. Rapprochement N↔M (pas juste 1↔1)

| Cas | Description |
|---|---|
| 1 ligne ↔ 1 justif | Cas simple (la majorité) |
| 1 ligne ↔ N justifs | Virement groupé (1250€ Castorama = 3 factures) |
| N lignes ↔ 1 justif | Encaissement multi-paiements (CB + chèque) |
| 1 ligne ↔ 1 justif multi-postes | Ticket Leclerc avec essence + course + parking |

### 2. Catégorisation des manquants (pas tous identiques)

| Catégorie | Action |
|---|---|
| 🔴 Vraiment manquant | À demander/scanner |
| 🟢 Pas de justif requis | Frais bancaire, agios — pas alarmant |
| 🔵 Récurrent | Loyer, abonnement → lien vers contrat |

### 3. Conformité fiscale des justifs numériques

Règle PVC (procédure de copie fiable) — Raya alerte si :
- Photo floue → "refais-la avant envoi"
- Ticket coupé → "je ne vois pas la TVA"
- Pas de date détectée → "confirme la date ?"

→ Seul l'utilisateur peut décider si le justif est utilisable.

### 4. Traçabilité (les originaux ne sont JAMAIS écrasés)

L'original (mail, PDF, photo) reste intact. Les annotations Raya
sont sur des copies. En cas de contrôle fiscal, l'original non
modifié doit être disponible.

### 5. Hors périmètre intentionnel

❌ Plan comptable PCG, FEC, TVA ventilée par taux, ventilation analytique
sont **HORS périmètre** car ce sont les missions du comptable. Raya livre
un dossier propre. Le comptable décide des codes finaux.

---

## 🎯 Configuration produit

### Toggle au niveau tenant (feature_flag)

`accounting_engine = ON / OFF` au niveau du tenant via le panel
super_admin (déjà en place dans la card société).

### Attribution au niveau user (feature_assignments — NEW)

Le `tenant_admin` choisit qui dans son équipe peut utiliser le module :
- Guillaume (dirigeant) → oui
- Arlène (secrétaire) → oui (elle fera la saisie)
- Pierre (technicien) → non (pas de saisie compta)

→ Nouvelle table `feature_assignments(tenant_id, feature_key, username)`
  même pattern que `connection_assignments` pour les connexions.

### Stockage obligatoire sur Drive externe

Le module **exige** une connexion Drive (SharePoint ou Google Drive)
sur le tenant. Pas de stockage en base interne Raya — trop de volume.

→ Si la feature est activée mais aucun Drive connecté, Raya alerte :
  "Pour utiliser le module compta, connectez d'abord un Drive."

### Interface utilisateur

**Bouton dédié dans la sidebar gauche du chat**, optionnel et retirable :
- Apparaît automatiquement pour les users à qui la feature est attribuée
- Click → envoie un prompt préformaté à Raya
- L'utilisateur peut le **masquer** depuis ses préférences pour épurer
- Reste accessible via commande chat ou voix : "Raya, scan le dossier compta"

→ Cohérent avec le pattern "Mes sujets" actuel.

---

## 🎯 Plan MVP en 3 étapes

```
ÉTAPE 1 — Brique 1 : Collecte au fil de l'eau (3-4 semaines)
   → Couvre 80-90% de la valeur du module
   
   Contenu :
   • Définition des nouveaux node_types et edge_types
   • Hook dans pipeline mail entrant : détection IA des justifs
   • Création nœud Justification + edges (extracted_from, supplier)
   • Stockage standardisé Drive : compta_YYYY-MM/
   • Renommage standard : "YYYY-MM-DD_montant€_fournisseur.pdf"
   • Règles utilisateur adaptatives (aria_rules étendu)
   • Bouton sidebar "🧮 Compta" (optionnel)

ÉTAPE 2 — Brique 2 : Check-up à la demande (1-2 semaines)
   → Vérification mensuelle, identification manquants
   
   Contenu :
   • Commande "scan dossier compta du mois X"
   • Upload relevé → BankStatement + BankTransactions
   • Algo matching transaction ↔ justification (gestion N↔M)
   • Catégorisation manquants (🔴🟢🔵)
   • Apprentissage des règles de classification

ÉTAPE 3 — Brique 3 : Compilation finale (1 semaine)
   → Dossier prêt à expédier
   
   Contenu :
   • Renommage chronologique avec lettres A, B, C
   • Annotation PDF du relevé (coches + lettres)
   • Index PDF de synthèse (page de garde)
   • Génération ZIP final
```

**Total : 5-7 semaines** pour un produit complet et différenciant.

L'étape 1 seule (3-4 semaines) donne déjà un MVP utile et vendable
("Raya range automatiquement vos justifs"). Les étapes 2 et 3
arrivent ensuite par incréments.

---

## 🤔 Questions à valider avec un expert-comptable

À demander à un expert-comptable AVANT de commencer le code :

1. **Format préféré des justifs** : PDF/PNG ? Tailles min ? Métadonnées ?
2. **Convention de renommage** : la nôtre tient-elle ? Y a-t-il un standard ?
3. **Lettrage** : convention A/B/C ou code numérique 26-001 ?
4. **PDF annoté** : suffit-il pour le comptable ou faut-il autre chose ?
5. **Manquants** : comment les présenter pour qu'ils soient actionnables ?
6. **Volumétrie** : quel format ZIP préférer (par mois, par trimestre, par an) ?
7. **Sécurité** : le comptable accepte-t-il un lien Drive ou veut-il du PJ ?

À demander à Guillaume :

1. Volume mensuel typique de Couffrant Solar (transactions, justifs) ?
2. Comment reçois-tu tes factures aujourd'hui (mail / papier / mixed) ?
3. Tu as combien de comptes bancaires (pro, holding, SCI...) ?
4. Tu mélanges parfois pro/perso à clarifier ?
5. Tu utilises quel logiciel comptable actuellement (toi/comptable) ?

---

## 🔌 Outils techniques pertinents

| Brique | Outil | Pourquoi |
|---|---|---|
| OCR factures | **GPT-4 Vision** | Best-in-class pour extraction structurée |
| Extraction structurée | LLM avec schema (Instructor, Outlines) | Sortie JSON typée |
| Parsing PDF banque | pdfplumber + LLM fallback | Formats banques très variés |
| Parsing CSV banque | parser standard | Plus simple |
| Annotation PDF | pypdf + reportlab | Annotation sans réécriture |
| Renommage | Python pathlib + OS Drive API | Selon Drive utilisé |
| Stockage Drive | Microsoft Graph / Google Drive API | Réutilise connexions existantes |
| Graphe sémantique | semantic_graph_nodes/edges (existant) | Tout est déjà là |
| Vectorisation | embeddings OpenAI (existant) | Pour recherche sémantique des justifs |

**Conclusion** : on construit **dans Raya** avec ces briques, pas
besoin d'intégrer un logiciel comptable externe complet. Plus rapide,
plus intégré, et c'est notre différenciation.

---

## 🌟 Idées additionnelles pour itérations futures

(à ne PAS implémenter au MVP, à garder pour V2/V3)

- **Tableau de bord temps réel** : "ce mois, encaissé X €, dépensé Y €,
  marge Z €" calculé en live
- **Alertes proactives** : "Mardi : facture EDF de 250€ reçue, mais ton
  prélèvement habituel est de 180€ — anomalie ?"
- **Prévision trésorerie** : "Compte tenu des factures à payer cette
  semaine, ton solde sera négatif jeudi"
- **Détection fraude** : "Cet IBAN n'est pas dans ta liste habituelle"
- **Pré-déclaration TVA** : préparation des montants à déclarer (le
  comptable valide ensuite)
- **Génération automatique factures clients** : à partir des chantiers
  Vesta terminés, propose les factures à émettre
- **Connecteur Pennylane/Cegid** (V2) : push automatique des écritures
  validées dans le logiciel comptable du tenant

---

## 📎 Décisions actées le 30/04/2026

```
Q1 : Détection mails entrants
  → Adaptatif (par règle utilisateur, comme tri mails actuel)
  → Demande la 1ère fois, apprend, automatise sur règle

Q2 : Stockage des fichiers
  → Drive externe obligatoire (SharePoint ou Google Drive)
  → Pas de stockage interne Raya (trop de volume sur le serveur)
  → Pré-requis : feature exige connexion Drive sur le tenant

Q3 : Attribution
  → Par user (pas tenant entier)
  → Le tenant_admin définit qui dans son équipe peut utiliser le module
  → Pattern feature_assignments(tenant_id, feature_key, username)
  → Cohérent avec connection_assignments

Q4 : Implémentation progressive
  → Brique 1 (collecte au fil de l'eau) en premier
  → Couvre 80-90% du besoin
  → Les briques 2 et 3 viennent ensuite

Q5 : Interface utilisateur
  → Bouton sidebar gauche dédié (apparaît si feature attribuée à user)
  → Click envoie un prompt préformaté à Raya
  → Bouton retirable par l'utilisateur (préférences)
  → Toujours accessible via chat ou voix
  → Pattern similaire à "Mes sujets"
```

---

## 🎯 Prochaine étape concrète

Quand Guillaume sera prêt à lancer ce chantier (probablement après
la version d'essai vendue) :

1. **Réunion 1h avec un expert-comptable** pour valider l'architecture
   et préciser les conventions (renommage, lettrage, format ZIP)
2. **Choisir le tenant pilote** : Couffrant Solar (Guillaume lui-même)
3. **Définir le périmètre Étape 1** précisément (3-4 semaines)
4. **Vérifier que le Drive de Couffrant est connecté** (prérequis)
5. **Démarrer par** : extension du graphe (3 nœuds + 5 edges) +
   hook mail entrant + détection IA basique

→ Le flag `accounting_engine` est **déjà en place** dans
  feature_registry (commit c51db88), prêt à être activé/désactivé
  par tenant via le panel super_admin.

→ Il restera à ajouter : la table `feature_assignments` pour
  l'attribution par user (~1 jour de dev).

---

## 🧠 Fil rouge architectural

**La thèse :** Raya = graphe + vectorisation + outils + prompts + Claude

Le module compta valide cette thèse. Si Raya gère :
- des fournisseurs (Contact),
- des paiements (BankTransaction),
- des justificatifs (Justification),
- des contrats récurrents,

dans **un seul graphe unifié**, alors Claude peut répondre à
**n'importe quelle question comptable libre**, sans qu'on ait codé
spécifiquement pour cette question.

C'est la différence entre :
- Un **logiciel comptable classique** = pipeline figé
- **Raya** = connaissance interrogeable + actions précises

Cette différence est ce qui rend Raya potentiellement disruptif.

---

*Document de vision propre. À mettre à jour si la vision évolue.*
*Dernière itération : 30/04/2026 nuit, après 4 itérations
Guillaume ↔ Claude.*
