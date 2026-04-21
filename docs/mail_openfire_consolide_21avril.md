# Mail consolidé OpenFire — Demande complète d'ouverture d'accès API

**Destinataire** : équipe technique OpenFire
**Expéditeur** : Guillaume Perrin — Couffrant Solar
**Instance** : `entreprisecouffrant.openfire.fr`
**Objet** : Couffrant Solar — Consolidation des demandes d'accès API (3 mails récents regroupés)

---

## Objet du mail (à copier dans le client mail)

`Couffrant Solar — Récap complet des ouvertures de droits API Odoo demandées`

---

## Corps du mail (à copier tel quel)

Bonjour,

Je regroupe dans ce mail l'ensemble de mes demandes d'ouverture de droits API sur notre instance, pour éviter de vous solliciter par petits bouts et vous permettre de traiter le tout en une seule passe.

Contexte rapide : nous avons un outil d'analyse métier en lecture sur Odoo, via un utilisateur API dédié. L'outil exploite les données pour des rapports et requêtes courantes (suivi commercial, pilotage chantiers, relations client). Il lui manque aujourd'hui certains accès lecture pour être pleinement utile, et j'ai remarqué au fil de son usage qu'on a besoin de plusieurs modèles / relations supplémentaires.

**Tous les accès demandés sont en LECTURE SEULE.** Aucune écriture, aucune suppression.

---

### 🔴 Priorité 1 — Débloque la majorité des questions métier

| # | Modèle / accès | Pourquoi c'est critique |
|---|---|---|
| 1 | `sale.order.line` (lecture) | Détail des lignes de devis : produits, quantités, références techniques (SE100K, PW3, etc.). Sans cet accès, impossible de répondre à "où a-t-on posé quoi". |
| 2 | `account.move.line` (lecture) | Lignes de facture : croiser ce qui a été facturé vs ce qui a été devisé. |
| 3 | `product.product` + `product.template` (lecture) | Référentiel produits (catalogue, variantes, tarifs). Sans ça, les références matériel sont juste des IDs opaques. |
| 4 | `res.partner.child_ids` + relation parent/enfant | Pouvoir remonter les contacts rattachés à une société (gérant, comptable, chargé d'affaire). Aujourd'hui on voit les personnes isolées, sans savoir qui gère quoi. |
| 5 | `ir.attachment` (lecture) + accès au contenu des PDF | Lire les pièces jointes (KBIS, bons de commande scannés, devis PDF, fiches techniques). Actuellement ces documents existent en base mais sont invisibles à notre outil. |

### 🟡 Priorité 2 — Déjà signalé il y a quelques jours

| # | Modèle | État |
|---|---|---|
| 6 | `mail.message` | Notre user API ne voit que ses propres messages. On demande l'ouverture sur les messages liés aux ressources (chatter Odoo). |
| 7 | `account.payment.line` | Droit "Extra Rights > Accounting > Payments" manquant sur le groupe du user API. |

### 🟢 Priorité 3 — Secondaire mais souhaité

| # | Modèle | Usage |
|---|---|---|
| 8 | Ouverture du webhook entreprise temps-réel (si pas encore fait) | Voir mon mail précédent du 20/04 "Demande OpenFire webhooks temps réel" |

---

### Concrètement, ce qu'il y a à faire côté OpenFire

**Option A (la plus simple)** : ajouter au groupe de permissions du user API les groupes Odoo standards suivants :
- `Sales / User : All Documents`
- `Inventory / User`
- `Accounting / Billing Administrator` (ou équivalent read-only sur `account.move.line` et `account.payment.line`)
- `Administration / Access Rights` (pour lire `ir.attachment`)

**Option B (plus fin)** : créer des ACLs spécifiques read-only sur chacun des 10 modèles ci-dessus. Je peux fournir la liste technique formatée si besoin.

Je vous laisse choisir la méthode la plus rapide pour vous.

---

### Pour information — sur la sécurité de notre côté

- Le user API est cloisonné à notre tenant, pas d'accès cross-clients.
- Côté notre outil, nous avons un système de permissions à 3 niveaux (lecture / écriture / suppression) qui empêche toute écriture non autorisée même si un bug logiciel tentait de le faire.
- Les tokens OAuth sont chiffrés au repos.

---

### Planning

Idéalement cette semaine ou la suivante. On continue à fonctionner sans ces accès pour les questions de haut niveau, mais ça bride énormément l'outil.

Dites-moi si vous avez besoin d'échanger en visio 15 min pour aller vite, ou si vous préférez faire ça tranquillement par mail.

Merci beaucoup,

Guillaume Perrin
Couffrant Solar — 18 rue de Langon, 41200 Romorantin-Lanthenay
TVA : FR63803487586
guillaume@couffrant-solar.fr

---

## ⚠️ Note pour toi Guillaume (à NE PAS copier dans le mail)

**Ce mail couvre TOUT ce qui a été demandé jusqu'ici** :
- Mail du 20/04 matin : webhooks temps-réel (cité en priorité 3)
- Mail du 20/04 après-midi : produits + lignes devis + mail.message + account.payment.line
- Nouveau 21/04 : child_ids + ir.attachment (issu de l'analyse de Raya ce matin)

**Tu n'auras plus à les relancer séparément.** Si dans 2 semaines tu découvres un nouveau besoin, tu leur enverras juste un court complément.

## 📋 Recensement complet pour référence future

Voir `docs/recensement_acces_odoo.md` (créé en parallèle) — inventaire exhaustif de tous les modèles Odoo utilisés ou envisageables, avec leur statut (ouvert / en attente / à demander).
