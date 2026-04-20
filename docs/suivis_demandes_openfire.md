# Suivi des demandes OpenFire

**But** : tracer l'avancement des demandes techniques envoyées à l'équipe support OpenFire pour l'instance Couffrant Solar (`entreprisecouffrant.openfire.fr`).

Mettre à jour ce document à chaque évolution. Il fait référence à chaque demande envoyée.

---

## 🔐 Demande #1 — Ouverture de droits API lecture

**Date d'envoi** : 20 avril 2026 (soir)
**Contenu du mail envoyé** : voir `docs/demande_openfire_droits_produits_lignes.md`
**Statut actuel** : ⏳ **envoyé, en attente de retour**

### Ce qui a été demandé

Lecture seule du user API existant sur 6 modèles supplémentaires :

| Modèle Odoo | Raison de la demande |
|---|---|
| `sale.order.line` | Lignes de devis / commande — produits, quantités, montants |
| `product.product` | Variantes produits — références exactes (SE100K, PW3, etc.) |
| `product.template` | Modèles catalogue |
| `account.move.line` | Lignes de facture — croisement devisé vs facturé |
| `account.payment.line` | Lignes de paiement détaillées |
| `mail.message` | Messages et commentaires (devis, leads, tâches) |


### Groupes de permissions suggérés

- Ajouter **Extra Rights / Accounting / Payments** pour `account.payment.line`
- Pour `mail.message` : déterminer avec OpenFire s'il existe un groupe pour la lecture globale, ou créer un groupe custom
- Pour les 4 autres : groupes standards **Sales / User: All Documents** + **Inventory / User** + **Accounting / Billing**

ACL XML alternative fournie dans le mail pour la voie "groupe custom dédié".

### Impact métier si débloqué

Raya pourra traiter les questions :
- *"Où ai-je posé des onduleurs SE100K ?"* — le cas qui a motivé la demande
- *"Combien de Tesla PW3 installés depuis janvier ?"*
- *"Écart devisé vs facturé sur le chantier X"*
- *"Clients avec factures émises mais paiements non encaissés"*
- *"Devis envoyés il y a > 15 jours sans réponse"*
- *"Stock critique : références souvent devisées pas encore facturées"*

### Journal

| Date | Événement |
|---|---|
| 20/04/2026 soir | Mail envoyé à OpenFire |
| — | _En attente de leur retour..._ |

### Actions après débloquage

1. Tester un appel `search_count` sur chaque modèle pour confirmer l'accès
2. Retirer les modèles concernés de `deactivated_models` dans la DB
3. Les ajouter à `POLLED_MODELS` dans `app/jobs/odoo_polling.py`
4. Relancer un scan Odoo ciblé pour remplir la base
5. Tester la question SE100K en condition réelle


---

## 🔌 Demande #2 — Module webhook temps-réel

**Date d'envoi** : 20 avril 2026 (matin)
**Contenu du mail envoyé** : voir `docs/demande_openfire_webhooks_temps_reel.md`
**Statut actuel** : ⏳ **envoyé, en attente de retour**
**Urgence** : faible (nous avons une solution de contournement qui marche)

### Ce qui a été demandé

Déployer un module Odoo custom sur notre instance qui permet d'appeler un endpoint HTTP externe depuis les actions `base_automation`. Contournement du blocage de la sandbox `safe_eval` d'Odoo 16 Community qui interdit tous les imports Python (`urllib`, `requests`, `json`...) dans le code des actions automatisées.

Deux formes acceptables :
1. **Méthode sur les modèles** : `record._notify_external_webhook(url, headers, payload, timeout)`
2. **Type d'action serveur natif** "Notification HTTP" configurable depuis l'interface Odoo

### Pourquoi

Sans ce module, Raya doit faire du polling toutes les 2 min (solution actuelle) ce qui :
- Génère 1-2 min de latence pour les changements
- Charge Odoo de requêtes périodiques inutiles
- Empêche le vrai temps-réel attendu par l'équipe Couffrant

### Solution actuelle (sans attendre leur retour)

Polling côté Raya implémenté le 20/04 matin (voir `docs/odoo_integration_etat_actuel.md`). Fonctionne bien, latence 1-2 min acceptable.

### Journal

| Date | Événement |
|---|---|
| 18/04/2026 | Spec initiale rédigée (archivée) |
| 20/04/2026 matin | Blocage sandbox Odoo 16 identifié, pivot polling |
| 20/04/2026 matin | Mail de demande envoyé à OpenFire |
| — | _En attente de leur retour..._ |

### Actions après débloquage

1. Mettre `SCHEDULER_ODOO_POLLING_ENABLED=false` dans Railway
2. Configurer les règles `base_automation` côté Odoo avec la nouvelle méthode
3. Vérifier dans le dashboard 🔌 Webhooks que les jobs arrivent via webhook
4. Laisser la ronde de nuit 5h en place comme filet de sécurité

Aucune modification de code Raya nécessaire : l'endpoint `/webhooks/odoo/record-changed` est déjà prêt depuis le 19/04.


---

## 📇 Contact OpenFire

À compléter :
- Email : ?
- Téléphone : ?
- Référent dossier Couffrant : ?

## 🧭 Bonnes pratiques pour une prochaine demande

1. **Rédiger le brouillon en markdown** dans `/docs/demande_openfire_<sujet>.md` avant d'envoyer
2. **Ne jamais mentionner Raya** dans le corps du mail (projet confidentiel côté Couffrant) — parler d'un "outil d'analyse interne"
3. **Fournir les erreurs exactes** rencontrées (stacktrace Odoo) pour faciliter leur diagnostic
4. **Proposer la solution XML/config** si on sait ce qu'ils doivent faire (gain de temps)
5. **Ajouter la demande ici** dans ce document avec son statut initial ⏳
6. **Mettre à jour le journal** à chaque retour d'OpenFire
