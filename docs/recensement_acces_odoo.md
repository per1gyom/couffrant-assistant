# Recensement complet des accès Odoo — Couffrant Solar

**Objectif** : document de référence unique. On le met à jour quand un accès est ouvert, refusé, ou qu'un nouveau besoin apparaît. Évite d'avoir à relancer OpenFire par petits bouts.

**Dernière mise à jour** : 22 avril 2026 (soir) — suite aux 2 mails envoyés à Dorian

---

## 📊 Tableau de synthèse

### Légende
- ✅ **OK** : accès ouvert, utilisé sans problème
- 🟡 **Demandé** : accès demandé à OpenFire, en attente de réponse
- 🔴 **À demander** : besoin identifié mais pas encore envoyé
- ⚪ **Pas besoin** : modèle standard Odoo non pertinent pour notre usage
- 🚫 **Refusé** : OpenFire a refusé / ne peut pas ouvrir

### Accès principaux

| Modèle Odoo | Statut | Priorité | Date demande | Note |
|---|---|---|---|---|
| `res.partner` | ✅ OK | — | — | Contacts / clients / fournisseurs. Lu OK. |
| `sale.order` | ✅ OK | — | — | Devis / commandes. Métadonnées OK. |
| `sale.order.line` | ✅ OK | — | 22/04/2026 | Lignes de devis (produits). **Ouvert aujourd'hui.** |
| `account.move` | ✅ OK | — | — | Factures. Métadonnées OK. |
| `account.move.line` | 🟡 Demandé | P1 | 22/04/2026 soir | Lignes de facture. **Critique**. Relance officielle dans le mail principal du 22/04. |
| `account.payment` | ✅ OK | — | — | Paiements. |
| `account.payment.line` | 🟡 Demandé | P2 | 22/04/2026 soir | Extra Rights manquant. Relance officielle dans le mail principal du 22/04. |
| `crm.lead` | ✅ OK | — | — | Leads / opportunités CRM. |
| `calendar.event` | ✅ OK | — | — | RDV / agenda. |
| `mail.message` | 🟡 Demandé | P2 | 22/04/2026 soir | User API ne voit que ses propres messages. Approche à caler avec Dorian sur le filtrage par défaut. |
| `mail.activity` | ✅ OK | — | — | Activités planifiées. |
| `product.product` | 🟡 Demandé | P1 | 22/04/2026 soir | Variantes produit. |
| `product.template` | 🟡 Demandé | P1 | 22/04/2026 soir | Catalogue produits. |
| `res.partner.child_ids` | 🟡 Demandé | P1 | 22/04/2026 soir | Relation gérant ↔ société. **Ajouté dans le mail complément du 22/04 soir.** |
| `res.partner.parent_id` | 🟡 Demandé | P1 | 22/04/2026 soir | Remontée société depuis fiche personne. **Ajouté dans le mail complément du 22/04 soir.** |
| `ir.attachment` | 🟡 Demandé | P1 | 22/04/2026 soir | Pièces jointes (KBIS, mandats, devis PDF, fiches techniques). **Ajouté dans le mail complément du 22/04 soir.** Métadonnées + `datas` + `res_model`/`res_id`. Fallback possible sur périmètre restreint si volume. |
| `helpdesk.ticket` | ✅ OK | — | — | Tickets SAV. |
| `project.project` | ✅ OK | — | — | Projets. |
| `project.task` | ✅ OK | — | — | Tâches de chantier. |
| `purchase.order` | ✅ OK | — | — | Bons de commande fournisseurs. |
| `hr.employee` | ✅ OK | — | — | Équipe. |
| `hr.leave` | ✅ OK | — | — | Congés. |
| `planning.slot` | ✅ OK | — | — | Planning chantiers. |
| `stock.picking` | ✅ OK | — | — | Livraisons stock. |
| `stock.location` | ✅ OK | — | — | Emplacements stock. |
| `stock.warehouse` | ✅ OK | — | — | Entrepôts. |

### Accès désactivés temporairement

| Modèle | Raison |
|---|---|
| `of.survey.answers` | Champ `name` absent sur notre instance (spécifique Couffrant) |
| `of.survey.user_input.line` | Idem |
| `stock.valuation.layer` | Non pertinent pour notre usage |

### Webhooks

| Type | Statut | Priorité |
|---|---|---|
| Webhook temps-réel pour modèles modifiés | 🟡 Demandé | P3 (non bloquant, palliatif polling 2 min en place) |


---

## 🎯 Ce qu'il faudrait encore si l'usage le révèle (pistes à surveiller)

| Besoin potentiel | Modèle(s) concerné(s) | Quand on en aura besoin |
|---|---|---|
| Historique des modifications (qui a changé quoi, quand) | `mail.tracking.value` | Pour audit changements de prix, de statuts |
| OCR sur pièces jointes | Pas un modèle, un traitement | Pour chercher dans le contenu des PDF |
| Liens documents ↔ records | `ir.attachment.res_model` / `res_id` | Pour relier un devis PDF à son sale.order |
| Tags / catégories | `res.partner.category_id` | Pour segmenter les clients |
| Pricelist articles | `product.pricelist.item` | Pour voir les remises client |
| Workflow states custom | Selon modules installés | Si workflow personnalisé chez Couffrant |

## 📖 Procédure quand un nouveau besoin apparaît

1. **Vérifier ici** si le modèle est déjà listé (demandé / ouvert / autre)
2. Si nouveau besoin : **ajouter une ligne** dans le tableau avec statut 🔴
3. Attendre d'avoir 2-3 besoins nouveaux ou un besoin bloquant, **puis seulement** écrire un mail à OpenFire (éviter de les spammer)
4. Mettre à jour les statuts quand OpenFire ouvre les accès

## 📧 Historique des mails envoyés à OpenFire

| Date | Objet | Contenu | Statut |
|---|---|---|---|
| 20/04/2026 matin | Webhooks temps-réel | Demande module webhooks natifs | ⏳ En attente |
| 20/04/2026 après-midi | Droits produits & lignes | 4 modèles (sale.order.line, account.move.line, product.*, mail.message, account.payment.line) | ⏳ En attente |
| 21/04/2026 | Mail consolidé (brouillon interne) | Reprise + ajout child_ids + ir.attachment — **non envoyé tel quel**, Guillaume a préféré un envoi en 2 temps | 📝 Référence interne |
| 22/04/2026 soir | Mail principal à Dorian | Ouverture droits API lecture sur 5 modèles (sale.order.line, product.*, account.move.line, account.payment.line, mail.message) avec ACLs suggérées | ⏳ En attente |
| 22/04/2026 soir | **Mail complément** (voir `mail_openfire_complement_22avril_soir.md`) | Ajout 2 éléments oubliés : `res.partner.child_ids`/`parent_id` + `ir.attachment` (+ rappel webhooks) | ⏳ En attente |

### Note sur la stratégie d'envoi

Le mail consolidé du 21/04 préparé en interne regroupait tout en un seul envoi. Guillaume a finalement préféré découper en 2 mails le 22/04 soir : un mail principal propre et bien structuré + un mail complément court pour les 2 éléments oubliés. Dorian a donc la vue complète en 2 messages consécutifs, ce qui est plus digeste qu'un mail fleuve unique.

**Les deux mails du 22/04 soir couvrent ENSEMBLE l'intégralité des demandes en cours. Plus rien à relancer tant que Dorian n'a pas répondu.**

## 🔗 Docs liés

- `docs/mail_openfire_consolide_21avril.md` — Le mail complet à envoyer aujourd'hui
- `docs/demande_openfire_webhooks_temps_reel.md` — Premier mail du 20/04 matin
- `docs/demande_openfire_droits_produits_lignes.md` — Deuxième mail du 20/04 après-midi
- `docs/suivis_demandes_openfire.md` — Suivi des retours OpenFire
- `docs/odoo_integration_etat_actuel.md` — Documentation technique de l'intégration Odoo
