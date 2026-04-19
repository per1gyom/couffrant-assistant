# 📌 Suspens Scanner Raya — à reprendre plus tard

Ce document liste les **problèmes connus non résolus** côté vectorisation, avec leur contexte et la piste de résolution. À relire chaque fois qu'on améliore le scanner ou quand on a un peu de temps pour débloquer une ligne.

---

## 🔐 SUSPENS #1 — Accès Odoo `account.payment.line` (lignes de paiement)

**Date détection** : 19 avril 2026 (test P2)
**Impact métier** : **Important** — Guillaume veut mettre à jour les devis et savoir où en sont les paiements. Sans ces lignes, la proactivité financière est incomplète.

**Erreur Odoo exacte** :
```
AccessError: Vous n'êtes pas autorisé à accéder aux enregistrements
'Payment Lines' (account.payment.line).
Cette opération est autorisée pour les groupes suivants :
  - Extra Rights/Accounting / Payments
```

**Modèles concernés (abandonnés à cause de ça)** :
- `account.move.line` → essaie de lire `account.payment.line` en cascade
- `account.move` → idem (partiellement)

**Ce qu'on fait en attendant** (Option A validée par Guillaume le 19/04) :
- Retirer des manifests les `graph_edges` qui pointent vers `account.payment.line`
- On perd la visibilité sur les lignes de paiement détaillées
- Les devis/factures/paiements globaux restent vectorisés (via `sale.order`, `account.move` si on arrive à le sauver)

**Piste de résolution quand Guillaume aura le temps** :
- Donner au user Odoo de Raya le groupe **"Extra Rights / Accounting / Payments"** dans OpenFire
- Procédure probable (à vérifier avec support OpenFire ou Guillaume PO) :
  1. Se connecter à OpenFire en admin
  2. Paramètres → Utilisateurs & sociétés → Utilisateurs
  3. Trouver le user de Raya (celui qui a l'API key)
  4. Onglet "Droits d'accès" ou "Groupes"
  5. Ajouter le groupe "Extra Rights / Accounting / Payments"
  6. Sauvegarder
- Une fois fait : relancer le test P2 sur `account.move.line` et `account.move`, ils devraient passer

---

## 📦 SUSPENS #2 — Accès Odoo `stock.valuation.layer` (valorisation stock)

**Date détection** : 19 avril 2026 (test P2)
**Impact métier** : **Faible** — Guillaume confirme qu'il n'utilise pas la gestion des stocks dans OpenFire sur ce logiciel. Pas de perte métier.

**Erreur Odoo exacte** :
```
AccessError: Vous n'êtes pas autorisé à accéder aux enregistrements
'Stock Valuation Layer' (stock.valuation.layer).
Cette opération est autorisée pour les groupes suivants :
  - Inventory/Administrator
```

**Ce qu'on fait** :
- Retirer des manifests les `graph_edges` qui pointent vers `stock.valuation.layer`
- Pas de piste à rouvrir ultérieurement (pas de valeur métier)

---

## 📧 SUSPENS #3 — `mail.message` retourne 0 records

**Date détection** : 18 avril 2026 (scan P1 #6)
**Impact métier** : **Important** — sans vectorisation des messages, Raya ne peut pas proposer de proactivité basée sur les emails/commentaires échangés sur les devis/leads/tâches.

**Symptôme** : le modèle ne plante pas techniquement (pas d'erreur Odoo), mais retourne systématiquement 0 records via `search_read` alors qu'il y a **29 139 messages** en base.

**Hypothèse dominante** : droits par défaut Odoo qui masquent les messages quand l'user API n'est pas auteur/destinataire/follower.

**Piste de résolution** :
- Tester un appel `mail.message search_count` via Raya pour voir combien on lit réellement
- Si 0 ou très faible : demander un groupe technique OpenFire qui autorise la lecture de tous les messages, ou créer un user dédié avec ACL étendus
- À traiter dans une session dédiée avec la tête reposée

---

## 📋 Récapitulatif — Modèles qui resteront à 0 chunks après Option A

| Modèle | Cause | Gravité |
|---|---|---|
| `mail.message` | Droits Odoo (0 records lus) | 🟠 Important |
| `account.move.line` lignes paiement détaillées | Droit `Extra Rights/Accounting/Payments` manquant | 🟠 Important |
| `stock.valuation.layer` (via `account.move`) | Droit `Inventory/Administrator` manquant | 🟢 Négligeable |

**Quand Guillaume obtient les droits Odoo** : relancer Test P2 ciblé sur ces modèles, si ça passe → relancer Compléter manquants et ces modèles s'ajouteront à la base vectorisée sans toucher au reste.

---

## 📝 Historique des retraits manifests (19/04/2026)

### Session 1 (après P1 run #6)
- `of.planning.tour.graph_edges.gb_sector_id` (compute cassé)
- `sale.order.line.graph_edges.of_gb_partner_tag_id` (compute cassé)
- `calendar.event.graph_edges.of_gb_employee_id` (compute cassé)

### Session 2 (après test P2 run #13)
- `of.sale.payment.schedule.metadata_fields.is_last` (compute cassé)
- `of.account.move.payment.schedule.metadata_fields.is_last` (compute cassé)
- `account.move.line.graph_edges.payment_line_ids` (droit manquant — suspens #1)
- `account.move.line.graph_edges.stock_valuation_layer_ids` (droit manquant — suspens #2)
- `account.move.graph_edges.stock_valuation_layer_ids` (droit manquant — suspens #2)

### Session 3 (après test P2 run #14)
- `account.move.line.graph_edges.of_gb_partner_tag_id` (compute `gb_*` cassé)
- `account.move.metadata_fields.payment_line_count` (compute lit account.payment.line — suspens #1)
- `account.payment.metadata_fields.payment_line_count` (préventif, même cause — suspens #1)
- `account.payment.graph_edges.payment_line_ids` (préventif — suspens #1)

### Pattern-check final
Aucun champ contenant `gb_*` ni `payment_line*` ne subsiste dans les manifests P1+P2 actifs.
