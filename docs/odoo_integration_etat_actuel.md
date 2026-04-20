# État actuel de l'intégration Odoo Raya ↔ OpenFire

**Version** : 1.0 (20 avril 2026)
**Statut** : solution de transition en place, attente retour OpenFire
**Remplace** : `archives/odoo_webhook_setup.md` et `archives/odoo_webhook_setup_guide_couffrant.md` (spécifications de base_automation webhooks périmées après découverte du blocage sandbox Odoo 16)

---

## 🎯 Architecture actuelle (valide au 20/04/2026)

```
Odoo/OpenFire (instance entreprisecouffrant.openfire.fr)
   │
   ▼ (read-only, via JSON-RPC, user API dedié)
Raya (app.raya-ia.fr)
   ├─ Scanner universel : vectorise au batch (manuel ou nuit complète)
   └─ Polling 2 min    : détecte les modifications récentes
        └─ enqueue dans vectorization_queue
             └─ worker webhook_queue.py traite à son rythme
                  └─ met à jour odoo_semantic_content + graphe
```

**Pas de webhook temps-réel pour l'instant.** Latence = 1 à 2 minutes.


## 📜 Historique du choix

**18 avril 2026** : spécification initiale d'un système de webhooks temps-réel via `base.automation` d'Odoo. L'idée : à chaque création/modification/suppression, Odoo appelle `requests.post(https://app.raya-ia.fr/webhooks/odoo/record-changed)` avec un secret partagé. Implémentation côté Raya faite pendant la session du 19/04 au soir (endpoint, queue, dédup, anti-rejeu, worker, dashboard, ronde de nuit).

**20 avril 2026 matin** : tentative de configuration côté OpenFire. **Blocage** : la sandbox `safe_eval` d'Odoo 16 Community interdit tous les imports Python (`urllib`, `requests`, `json`, `secrets`) dans les actions `base_automation`. Erreur :

```
forbidden opcode(s) in 'import urllib.request...'
IMPORT_NAME
```

La spec du 18/04 est donc inapplicable **sans module Odoo custom**.

**20 avril 2026 matin** : **pivot en deux temps** décidé avec Guillaume :

1. **Court terme** : implémentation d'un polling côté Raya qui simule les webhooks. Réutilise toute l'infrastructure codée le 19/04 (queue, dédup, worker, dashboard, ronde de nuit). Seul l'émetteur change — c'est Raya qui détecte maintenant, pas Odoo.
2. **Long terme** : demande formelle envoyée à OpenFire pour développer un module Odoo custom qui permettra d'appeler Raya depuis les actions automatisées (voir `docs/demande_openfire_webhooks_temps_reel.md`). Quand ils livrent, bascule sans modification côté Raya.


## ⚙️ Configuration actuelle (Railway)

Variables d'environnement en place :

| Variable | Rôle |
|---|---|
| `ODOO_WEBHOOK_SECRET_COUFFRANT` | Secret partagé du webhook (reste utile quand les vrais webhooks arriveront) |
| `SCHEDULER_ODOO_POLLING_ENABLED=true` | Active le polling 2 min |
| `SCHEDULER_WEBHOOK_NIGHT_PATROL_ENABLED=true` | Active la ronde de nuit 5h (filet de sécurité) |
| `RECENT_WINDOW_MINUTES=15` | Fenêtre d'affichage "récent" dans les dashboards |

## 📋 Modèles polling actuels

Liste maintenue dans `app/jobs/odoo_polling.py` constante `POLLED_MODELS` :

```
sale.order, sale.order.line, crm.lead,
mail.activity, calendar.event, res.partner,
account.move, account.payment,
of.planning.tour, of.planning.task,
of.planning.intervention.template,
of.custom.document
```

Retirés temporairement (manifest cassé ou droits manquants, cf. `raya_scanner_suspens.md`) :
- `of.survey.answers` — champ `name` inexistant sur ce modèle chez Couffrant
- `of.survey.user_input.line` — même problème
- `mail.message` — droits par défaut Odoo masquent les messages (en attente OpenFire)
- `account.payment.line` — groupe `Extra Rights/Accounting/Payments` manquant (en attente OpenFire)
- `stock.valuation.layer` — groupe `Inventory/Administrator` manquant (pas utilisé métier)

Tous ces modèles sont référencés dans la table `deactivated_models` avec leur raison et statut.


## 🔍 Monitoring

Dashboard **🔌 Webhooks** dans le panel admin super-admin. Affiche :
- Verdict global coloré (🟢🟡🟠🔴)
- Compteurs récents (fenêtre 15 min configurable)
- Erreurs fantômes (modèles désactivés) vs erreurs réelles
- Regroupement par modèle
- 20 derniers jobs en détail technique (replié par défaut)
- Bouton 🧹 Purger les erreurs fantômes quand utile

Dashboard **📊 Intégrité** pour voir le % de vectorisation par modèle, avec distinction visuelle entre vrais problèmes et suspens documentés.

## 🗂️ Fichiers clés du code

| Fichier | Rôle |
|---|---|
| `app/jobs/odoo_polling.py` | Polling 2 min qui enqueue les modifications |
| `app/webhook_queue.py` | Worker + queue + anti-rejeu (partagé avec vrais webhooks futurs) |
| `app/routes/webhook_odoo.py` | Endpoint `/webhooks/odoo/record-changed` (déjà en place, attend les vrais webhooks) |
| `app/jobs/webhook_night_patrol.py` | Ronde de nuit 5h (filet de sécurité) |
| `app/routes/admin/super_admin_system.py` | Endpoints dashboard |

## 🎯 Prochaine étape (quand OpenFire livre le module custom)

1. Mettre `SCHEDULER_ODOO_POLLING_ENABLED=false` dans Railway
2. Configurer les règles `base_automation` côté Odoo (ou utiliser le nouveau type d'action serveur qu'OpenFire aura créé)
3. Vérifier dans le dashboard 🔌 Webhooks que les jobs arrivent via webhook plutôt que via polling
4. Laisser la ronde de nuit 5h en place comme filet de sécurité définitif

**Aucune modification du code Raya nécessaire**. L'endpoint `/webhooks/odoo/record-changed` est déjà en place et accepte exactement ce qu'OpenFire lui enverra.

## 🔗 Docs liés

- `docs/demande_openfire_webhooks_temps_reel.md` — le mail envoyé à OpenFire pour demander le module custom
- `docs/demande_openfire_droits_produits_lignes.md` — le mail envoyé pour demander l'ouverture des droits sur sale.order.line, product.product, etc.
- `docs/suivis_demandes_openfire.md` — tracking des 2 demandes ci-dessus avec leur statut
- `docs/raya_scanner_suspens.md` — liste des suspens techniques par modèle
