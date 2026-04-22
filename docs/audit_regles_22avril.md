# Audit des règles aria_rules — 22 avril 2026

**161 règles** dont **158 actives**, créées entre le 07/04 et le 21/04.
**75 règles** dans la catégorie "auto" (fourre-tout).

---

## 🚨 Problème CRITIQUE : pollution multi-tenant

**10+ règles appartenant à un autre utilisateur** sont actives dans la base
de Guillaume. Source = "onboarding" du 15/04. Elles mentionnent
"Charlotte", "Lab Events", "Camus", "B2B événementiel", "écosystème Google".

Ces règles sont injectées dans le prompt de Raya à chaque requête.
Potentiellement cause de comportements bizarres.

### Règles à DÉSACTIVER immédiatement (pollution)

| ID | Règle | À supprimer |
|---|---|---|
| 92 | "ton direct avec Charlotte, pas de fioritures" | ✅ |
| 93 | "registre littéraire, philosophie juillet, Camus" | ✅ |
| 94 | "gagner du temps sur templates événementiels" | ✅ |
| 95 | "Charlotte ne sait pas ce qu'elle pourrait améliorer" | ✅ |
| 96 | "écosystème Google, Lab Events outils centraux" | ✅ |
| 97 | "Charlotte a un stack établi, temps contraint" | ✅ |
| 98 | "dimension artistique et scénographique ADN agence" | ✅ |
| 99 | "contexte B2B événementiel" | ✅ |
| 100 | "Charlotte arrive avec tâche floue" | ✅ |
| 101 | "Charlotte besoin livrables, pas de framework" | ✅ |

**Action** : UPDATE aria_rules SET active=false WHERE id IN (92,93,94,95,96,97,98,99,100,101)

---

## 📋 Doublons et redondances majeures

### Groupe 1 : "Ne pas supprimer les mails / corbeille = récupérable"

| ID | Règle |
|---|---|
| 2 | Ne jamais supprimer définitivement un mail — toujours déplacer corbeille |
| 6 | Ne jamais supprimer définitivement un mail sans confirmation |
| 69 | Archiver = dossier Archives, jamais corbeille. Corbeille = suppression explicite |
| 74 | Archiver = Archives (pas corbeille). Corbeille = suppression ou bruit |
| 71 | Mise à la corbeille = action directe, pas de confirmation |
| 76 | Toute action récupérable (corbeille) = directe sans confirmation |
| 104 | Mise à la corbeille (DELETE) = action directe, récupérable |

**Consolidation** : garder 1 règle fusionnée.
**À supprimer** : 2, 6, 69, 71, 104 (garder 74 + 76).

### Groupe 2 : Boîtes mail connectées

| ID | Règle |
|---|---|
| 70 | Boîtes mail : guillaume@couffrant-solar.fr + per1.guillaume@gmail.com |
| 73 | Adresse pro = guillaume@, adresse perso = per1.guillaume@ |
| 102 | Boîte Outlook guillaume@ = "boîte Couffrant Solar" |
| 103 | Boîte Gmail per1.guillaume@ = "boîte perso" |
| 119 | Contacts perso dans Gmail, pas dans Microsoft |
| 124 | contact@couffrant-solar.fr à connecter prochainement |

**Consolidation** : 1 règle qui liste tout clairement.
**À supprimer** : 70, 73 (les 2 plus floues).

### Groupe 3 : Tagger par entité

| ID | Règle |
|---|---|
| 9 | Tags : couffrant-solar, sci-gaucherie, sci-romagui, sas-gplh |
| 18 | [couffrant-solar], [sci-gaucherie], [sci-romagui], [sas-gplh] |

**À supprimer** : 9 (garder 18, plus récente).

### Groupe 4 : Attestation Consuel

| ID | Règle |
|---|---|
| 24 | L'attestation Consuel s'appelle "attestation visée" |
| 27 | L'attestation peut s'appeler : "attestation visée", "attestation Consuel", "consuel visé" |
| 29 | Variantes acceptées : 'attestation Consuel', 'attestation visée', 'Consuel visé' |

**À supprimer** : 24, 29 (garder 27, plus explicite).

### Groupe 5 : Équipe Couffrant Solar

| ID | Règle |
|---|---|
| 130 | Pierre Couffrant = associé et chef d'équipe opérationnel |
| 134 | Pierre Couffrant = associé et chef d'équipe opérationnel (copie) |
| 142 | Pierre Couffrant = co-gérant et co-associé |
| 133 | Sabrina Lecomte = secrétaire |
| 136 | Sabrina = secrétaire (copie) |
| 129 | Jérôme Couffrant = électricien, opérationnel terrain |
| 131 | Benoît Nicolle = commercial et bureau d'études |
| 132 | Aurélien Le Maistre = équipier terrain |
| 17 | Arlène Desnoues = assistante, transfère mails d'info |
| 135 | Romain = apprenti, arrêt maladie jusqu'en mai |
| 146 | Karen = boîte contact partagée, pas de mail individuel |

**Consolidation** : 1 règle tableau équipe.
**À supprimer** : 134, 136 (doublons exacts).
**À reformuler** : les autres en 1 bloc "équipe".

### Groupe 6 : Simon Ducasse / SARL des Moines

| ID | Règle |
|---|---|
| 110 | Projet ACC SARL des Moines — Simon Ducasse (Enryk) |
| 126 | Simon Ducasse = interlocuteur ACC SARL des Moines |
| 149 | Simon Ducasse = interlocuteur direct SARL des Moines |
| 160 | SARL des Moines = Legroux + Simon Ducasse AMO ACC |
| 161 | Simon Ducasse = Enryk, AMO technique ACC |

**À supprimer** : 110, 126, 149, 161 (garder 160 qui est plus complet).

### Groupe 7 : AZEM plus gros client

| ID | Règle |
|---|---|
| 138 | AZEM = plus gros client par CA facturé (179k€), facture non payée |
| 155 | AZEM = plus gros client, à surveiller (impayés, doublons) |

**À supprimer** : 138 (chiffre figé, moins utile que 155).

### Groupe 8 : Capacités PDF/Excel/Images

| ID | Règle |
|---|---|
| 82 | Raya peut créer/modifier des images |
| 85 | Capacités en cours : PDF, Excel, images |
| 86 | Raya peut générer/proposer téléchargement PDF |
| 87 | Raya peut lire/modifier PDF et Excel |

**Consolidation** : 1 règle "outils de création" à jour.
**À supprimer** : 82, 85, 86 (garder 87 + update).

### Groupe 9 : Catégories tri-mails vs tri_mails

Doublons par erreur d'orthographe (tiret vs underscore).

| Catégorie "tri-mails" (5 règles) | Catégorie "tri_mails" (6 règles) |
|---|---|
| #12 Microsoft 365 expiré = rouge | #48 enedis/consuel = raccordement |
| #13 Contrats à signer = rouge | #49 devis/offre/contrat = commercial |
| #14 Alertes sécurité = orange | #50 réunion/meeting = reunion |
| #15 Mails d'Arlène = jaune | #51 chantier/planning = chantier |
| #16 Newsletters = archiver | #52 facture/paiement = financier |
|  | #53 fournisseur/livraison = fournisseur |

**Consolidation** : renommer tout en "tri_mails" (1 seule catégorie).

---

## 🐛 Règles buggées

### ID #1 : entrée de test
```
category: "category"
rule: "rule"
```
**À supprimer** (bug évident de seed).

### Règles obsolètes v1

| ID | Règle | Pourquoi obsolète |
|---|---|---|
| 4 | "J'ai le pouvoir d'ancrer mes règles..." | v2 utilise `remember_preference` comme tool |
| 5 | "Avant de modifier règle validée, demander confirmation" | v2 = pas de modification |
| 7 | "Ancrer directement règles sauf doute" | v1 mécanisme |
| 8 | "Modifier/supprimer règle = confirmation préalable" | v1 mécanisme |
| 21 | "Construire apprentissage via corrections Guillaume" | v1 comportement |
| 106 | "Génère plusieurs [ACTION:LEARN] séparés" | Syntaxe v1 ACTION obsolète |

**À désactiver** : toutes ces règles ne s'appliquent plus à la v2 agent.

---

## 🟡 Règles vagues, pas actionnables

| ID | Règle | Problème |
|---|---|---|
| 10 | "Autonomie par défaut : ne pas interroger pour décisions courantes" | Trop vague, déjà couvert par le prompt v2 |
| 11 | "Mails courts : préférence confirmée" | Absence de critère |
| 22 | "Être transparent sur les limites" | Déjà dans les règles du prompt v2 |
| 30 | "Être honnête sur mes capacités réelles" | Redondant avec 22 |
| 31 | "Être concis et directement utile" | Déjà dans le prompt v2 (règle 4) |
| 57 | "Répondre de manière directe et concise par défaut" | Redondant avec 31, 63 |
| 63 | "Traiter Guillaume comme chef d'entreprise à autonomie" | Redondant avec 10, 57 |
| 65 | "Identifier la casquette active" | Trop vague |

**À désactiver** : ces règles ajoutent du bruit sans ajouter de valeur.

---

## 📊 Synthèse

| Catégorie | Nombre | Action recommandée |
|---|---|---|
| Règles **pollution** (Charlotte/agence) | 10 | **Désactiver toutes** |
| Règles **buggées** | 1 | Supprimer |
| Règles **doublons** | ~20 | Fusionner |
| Règles **obsolètes v1** | 6 | Désactiver |
| Règles **vagues/redondantes** | 8 | Désactiver |
| Règles **solides à garder** | ~115 | Garder, éventuellement reformuler |

**Total à désactiver ou supprimer** : ~45 règles (sur 158 actives).

---

## 🎯 Plan d'action proposé

### Étape 1 — URGENT : supprimer la pollution Charlotte (2 min)
```sql
UPDATE aria_rules SET active=false 
WHERE id IN (92,93,94,95,96,97,98,99,100,101);
```

### Étape 2 — Nettoyer les bugs et obsolètes v1 (5 min)
```sql
UPDATE aria_rules SET active=false 
WHERE id IN (1, 4, 5, 7, 8, 21, 106);
```

### Étape 3 — Fusionner les doublons (30 min)
Garder 1 règle consolidée par groupe, désactiver le reste.

### Étape 4 — Supprimer les règles vagues (10 min)
Les règles "faire confiance à Guillaume, être concis" sont déjà dans le
prompt v2. Les désactiver.

### Étape 5 — Réorganiser les catégories (20 min)
- Fusionner `tri-mails` et `tri_mails` → `tri_mails`
- Réduire la catégorie `auto` fourre-tout en sous-catégories vraies
  (client, équipe, outils, comportement, procédure)

### Bonus — Corriger le bug multi-tenant dans save_rule

Vérifier dans `app/memory_rules.py` que `save_rule()` filtre bien par
`username` et `tenant_id` pour ne JAMAIS laisser une règle d'un autre
user polluer la base d'un autre. C'est ce qui a permis aux 10 règles
"Charlotte" d'arriver chez Guillaume.
