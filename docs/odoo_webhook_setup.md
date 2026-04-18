# 🔌 Configuration des webhooks Odoo vers Raya

**Version** : 1.0
**Date** : 18 avril 2026
**Prérequis** : Odoo avec module `base_automation` installé (natif depuis Odoo 14)

Ce document explique comment configurer Odoo pour envoyer **en temps réel** les créations, modifications et suppressions de records vers Raya, qui met à jour le graphe sémantique et les embeddings immédiatement.

## 📐 Architecture

```
Odoo (création/modification d'un record)
    │
    ▼
base_automation.rule déclenchée (on create/write/unlink)
    │
    ▼
Action serveur Python : requests.post()
    │
    ▼ (header X-Webhook-Token: <secret>)
POST https://app.raya-ia.fr/webhooks/odoo/record-changed
    │
    ▼ (réponse 202 immédiate)
Raya traite en background thread :
    ├── Met à jour semantic_graph (nœuds + arêtes)
    ├── Re-vectorise le record dans odoo_semantic_content
    └── Invalide les caches éventuels
```


## 🔐 Étape 1 — Générer le secret partagé

Le secret sert à authentifier les appels Odoo → Raya. Sans ce secret, n'importe qui pourrait spammer ton endpoint avec de fausses mises à jour.

### Générer un secret aléatoire

Dans un terminal local :

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(48))"
```

Tu obtiens quelque chose comme `x7Kp9mQr3Fn8bZtVh2wY6LdPj1AcUsE4kNvMpRqXyBtCfWgHi`. Copie-le, on va s'en servir deux fois.

### Ajouter le secret côté Raya (Railway)

1. Va dans ton dashboard Railway
2. Projet `couffrant-assistant` → onglet **Variables**
3. Ajoute une variable :
   - **Nom** : `ODOO_WEBHOOK_SECRET`
   - **Valeur** : le secret généré ci-dessus
4. Railway redéploie automatiquement

### Ajouter le secret côté Odoo

Tu ajouteras ce même secret dans chaque action serveur Odoo (section suivante). **Ne le mets pas en clair dans le code** : tu peux utiliser un System Parameter d'Odoo :

1. Active le mode développeur dans Odoo (URL avec `?debug=1` à la fin, puis menu Paramètres → Général)
2. Va dans **Paramètres techniques → Paramètres système**
3. Crée un nouveau paramètre :
   - **Clé** : `raya.webhook_secret`
   - **Valeur** : le même secret
4. Dans le code des actions serveur, tu le récupéreras via `env['ir.config_parameter'].sudo().get_param('raya.webhook_secret')`


## ⚙️ Étape 2 — Créer les automatisations Odoo

Pour chaque modèle qu'on veut surveiller, on crée une règle `base.automation` qui déclenche une action serveur Python à la création/modification/suppression.

### Accéder à l'interface

1. Mode développeur activé (voir étape 1)
2. Menu **Paramètres → Techniques → Automatisation → Automatisations planifiées**
3. Cliquer **Créer**

### 🧩 Modèle 1 — res.partner (contacts)

**Configuration de la règle** :

| Champ | Valeur |
|---|---|
| Nom de la règle | `Raya — Notify res.partner changes` |
| Modèle | `Contact (res.partner)` |
| Déclencheur | `Sur création et modification` (ou 3 règles séparées si tu veux différencier create/write/unlink) |
| Type d'action | `Exécuter du code Python` |

**Code Python à coller** dans l'onglet "Code" :

```python
# Raya webhook : notifie des changements de contact
import requests
import logging

_logger = logging.getLogger(__name__)

try:
    webhook_url = "https://app.raya-ia.fr/webhooks/odoo/record-changed"
    secret = env['ir.config_parameter'].sudo().get_param('raya.webhook_secret')

    if not secret:
        _logger.warning("Raya webhook : secret manquant, skip")
    else:
        for rec in records:
            payload = {
                "model": "res.partner",
                "record_id": rec.id,
                "event": "write",
                "tenant_id": "couffrant_solar",
            }
            try:
                requests.post(
                    webhook_url,
                    json=payload,
                    headers={"X-Webhook-Token": secret},
                    timeout=3,
                )
            except Exception as e:
                _logger.warning("Raya webhook failed for partner %s: %s", rec.id, e)
except Exception as e:
    _logger.error("Raya webhook automation error: %s", e)
```

**Remarque sur `timeout=3`** : on laisse 3 secondes max. Raya répond en 50ms normalement (202 Accepted instantané), donc si Raya est down, Odoo ne reste pas bloqué. En cas d'échec, le sync nocturne (filet de sécurité) rattrapera la mise à jour.


### 🧩 Modèle 2 — sale.order (devis et chantiers)

Même principe, change juste `"model": "sale.order"` dans le payload. Configuration :

| Champ | Valeur |
|---|---|
| Nom de la règle | `Raya — Notify sale.order changes` |
| Modèle | `Bon de commande (sale.order)` |
| Déclencheur | `Sur création et modification` |

**Code Python** (change uniquement la ligne `"model"`) :

```python
import requests
import logging
_logger = logging.getLogger(__name__)

try:
    webhook_url = "https://app.raya-ia.fr/webhooks/odoo/record-changed"
    secret = env['ir.config_parameter'].sudo().get_param('raya.webhook_secret')
    if secret:
        for rec in records:
            try:
                requests.post(
                    webhook_url,
                    json={
                        "model": "sale.order",
                        "record_id": rec.id,
                        "event": "write",
                        "tenant_id": "couffrant_solar",
                    },
                    headers={"X-Webhook-Token": secret},
                    timeout=3,
                )
            except Exception as e:
                _logger.warning("Raya webhook failed for order %s: %s", rec.id, e)
except Exception as e:
    _logger.error("Raya webhook automation error: %s", e)
```

### 🧩 Modèle 3 — calendar.event (événements et RDV)

| Champ | Valeur |
|---|---|
| Nom de la règle | `Raya — Notify calendar.event changes` |
| Modèle | `Événement de calendrier (calendar.event)` |
| Déclencheur | `Sur création et modification` |

Code Python : même structure, remplace par `"model": "calendar.event"`.

**Important pour les RDV** : ce webhook se déclenche aussi quand tu ajoutes un commentaire dans la description d'un événement (c'est un `write` sur le champ `description`). Donc dès que tu tapes *"prévoir kit de fixation renforcé"* dans un RDV, Raya le voit en temps réel et peut te le rappeler le matin du RDV.

### 🧩 Modèle 4 — crm.lead (leads et opportunités)

| Champ | Valeur |
|---|---|
| Nom de la règle | `Raya — Notify crm.lead changes` |
| Modèle | `Piste/Opportunité (crm.lead)` |
| Déclencheur | `Sur création et modification` |

Code Python : remplace par `"model": "crm.lead"`.

### 🧩 Modèles additionnels (optionnels)

Tu peux ajouter les mêmes règles pour `account.move` (factures), `account.payment` (paiements), `project.task` (tâches), `helpdesk.ticket` (SAV) sur le même modèle. Le webhook Raya les gère déjà côté code.


## 🧪 Étape 3 — Tester la configuration

### Test 1 — Endpoint de santé

Depuis un terminal local ou via un navigateur :

```bash
curl https://app.raya-ia.fr/webhooks/odoo/health
```

Tu devrais recevoir :

```json
{
  "status": "ok",
  "secret_configured": true,
  "timestamp": "2026-04-18T..."
}
```

Si `secret_configured: false`, c'est que la variable `ODOO_WEBHOOK_SECRET` n'est pas définie sur Railway — retourne à l'étape 1.

### Test 2 — Envoi manuel d'un webhook (simulation Odoo)

```bash
curl -X POST https://app.raya-ia.fr/webhooks/odoo/record-changed \
  -H "Content-Type: application/json" \
  -H "X-Webhook-Token: TON_SECRET_ICI" \
  -d '{"model":"res.partner","record_id":2501,"event":"write","tenant_id":"couffrant_solar"}'
```

Réponse attendue (en moins d'une seconde) :

```json
{
  "status": "accepted",
  "model": "res.partner",
  "record_id": 2501,
  "event": "write"
}
```

### Test 3 — Vrai test depuis Odoo

1. Ouvre un contact existant dans Odoo (par exemple "AZEM")
2. Modifie un champ quelconque (commentaire, téléphone) et enregistre
3. Dans les logs Railway, tu devrais voir en quelques secondes :

```
[Webhook Odoo] recu write/res.partner on 2501 (tenant=couffrant_solar)
[Webhook Odoo] partner 2501 re-vectorise et graph mis a jour
```

Si rien n'apparaît dans Railway, vérifie dans Odoo :
- **Paramètres → Techniques → Journaux des automatisations** pour voir si la règle s'est bien déclenchée
- **Paramètres → Techniques → Logging** pour voir les éventuelles erreurs Python


## 🔒 Sécurité et bonnes pratiques

### Protection contre les abus

L'endpoint Raya est protégé par 3 couches :

1. **Secret partagé** `X-Webhook-Token` : sans lui, retour 401 Unauthorized
2. **Validation du payload** : `model` et `record_id` (int) obligatoires, sinon 400
3. **Rate limiting natif FastAPI** : protège contre un spam accidentel (Odoo qui tourne en boucle sur une mauvaise règle)

### Rotation du secret

Si le secret fuite, rotation en 2 étapes :

1. Générer un nouveau secret (voir étape 1)
2. Mettre à jour la variable `ODOO_WEBHOOK_SECRET` sur Railway
3. Mettre à jour le System Parameter `raya.webhook_secret` dans Odoo
4. Les webhooks reprennent immédiatement avec le nouveau token

**Recommandation** : rotation annuelle, ou immédiate si suspicion de fuite.

### Que se passe-t-il si un webhook rate ?

Scénarios possibles :
- Raya est en cours de redeploy Railway (~1-2 min)
- Problème réseau entre Odoo et Railway
- Timeout (normalement impossible, Raya répond en ~50ms)

**Filet de sécurité** : le sync incrémental nocturne à 3h30 rattrape **tous les records** modifiés depuis la dernière sync, donc rien n'est perdu durablement. Au pire, une modif faite à 14h32 qui rate le webhook sera re-synchronisée à 3h30 la nuit suivante.

Si tu veux rafraîchir immédiatement sans attendre la nuit, clique sur **🧠 Vectoriser** dans le panel admin.


## 📊 Vérifier que ça marche dans la durée

### Surveillance côté Raya

Dans le panel admin, onglet **Sociétés**, le bandeau d'alertes système affiche automatiquement :

- ⚠️ `webhook_missed` si un webhook a raté (détecté par le sync nocturne qui trouve des records modifiés sans trace de webhook reçu)
- ⚠️ `odoo_module_missing` si une règle base_automation référence un champ/modèle qui n'existe pas
- ⚠️ `fetch_limit_approached` si tu t'approches d'une limite de fetch (>90%)

### Logs Raya à surveiller

Dans Railway → onglet **Logs**, filtre par `Webhook Odoo` :

```
[Webhook Odoo] recu write/res.partner on 2501
[Webhook Odoo] partner 2501 re-vectorise et graph mis a jour
```

Fréquence normale chez Couffrant Solar : 5 à 50 webhooks/jour selon l'activité de l'équipe.

### Dashboard Odoo

Dans **Paramètres → Techniques → Automatisation → Journaux**, tu peux voir l'historique d'exécution de chaque règle `base_automation`. Si une règle plante régulièrement, ça apparaît ici.

---

## 🗺️ Roadmap d'évolution

**Aujourd'hui** (v1.0) :
- Webhooks Odoo → Raya sur res.partner, sale.order, calendar.event, crm.lead
- Sync nocturne incrémental comme filet de sécurité
- Surveillance des limites de fetch via system_alerts

**À venir** :
- Support additionnel : account.move, account.payment, project.task, helpdesk.ticket
- Webhooks Raya → Odoo (bidirectionnel) : quand Raya modifie un record via un tag ACTION, notifier Odoo
- Intelligence contextuelle : au lieu de re-vectoriser le record entier, ne re-vectoriser que si un champ textuel a réellement changé
- Détection des cascades : si on change un res.partner, re-vectoriser aussi les sale.order de ce partner dont le nom change

---

## ❓ Support

En cas de problème :

1. Vérifier `https://app.raya-ia.fr/webhooks/odoo/health` retourne `ok`
2. Vérifier les logs Railway (recherche `Webhook Odoo`)
3. Vérifier les journaux Odoo (Paramètres → Techniques → Automatisation → Journaux)
4. Regarder le bandeau d'alertes dans le panel admin Raya

**Document maintenu par** : Guillaume Perrin
**Dernière mise à jour** : 18 avril 2026
