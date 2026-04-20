# Demande à OpenFire — Module de notification HTTP temps-réel

**Destinataire** : équipe technique OpenFire
**Expéditeur** : Guillaume Perrin — Couffrant Solar (instance `entreprisecouffrant.openfire.fr`)
**Date de demande** : 20 avril 2026
**Urgence** : pas urgent — à prévoir dans les prochains mois

---

## Contexte

Nous avons développé une intelligence artificielle métier (Raya) qui se connecte à Odoo pour aider au pilotage quotidien de l'entreprise. Raya a besoin d'être informée en temps réel quand des données sont créées, modifiées ou supprimées dans Odoo (devis, interventions, leads, contacts, etc.), afin de maintenir une représentation à jour.

## Le besoin

Nous aimerions déclencher, à chaque création/modification/suppression sur certains modèles, un appel HTTP POST vers notre API externe (hébergée sur `https://app.raya-ia.fr`).

Typiquement :
```
sale.order créé  →  POST vers app.raya-ia.fr/webhooks/odoo/record-changed
                     headers : X-Webhook-Token, X-Webhook-Nonce, X-Webhook-Timestamp
                     body    : {model, record_id, op}
```

## Le problème rencontré

Nous avons tenté de le faire via une règle `base.automation` de type "Exécuter du code Python". Le code utilisait les librairies `urllib.request` et `json`. Odoo 16 rejette ce code avec l'erreur :

```
forbidden opcode(s) in 'import urllib.request\nimport urllib.error\nimport json...'
IMPORT_NAME
```

La sandbox `safe_eval` d'Odoo 16 Community ne permet aucun import externe, y compris `requests` ou `urllib`.

## Solution de contournement actuelle

Nous avons mis en place un **polling côté Raya** (interrogation périodique d'Odoo toutes les 1-2 minutes). Cela fonctionne mais génère une latence de 1-2 minutes et une charge permanente inutile sur Odoo. Ce n'est qu'un palliatif.

## Ce que nous vous demandons

**Déployer un module Odoo custom** (ou une extension existante) qui expose une méthode appelable depuis `base.automation` pour envoyer un webhook HTTP. Exemple d'interface souhaitée :

```python
# Dans l'action automatisée Odoo, le code serait simplement :
for record in records:
    record._notify_external_webhook(
        url="https://app.raya-ia.fr/webhooks/odoo/record-changed",
        headers={
            "X-Webhook-Token": env['ir.config_parameter'].sudo().get_param('raya.webhook_secret'),
            "X-Webhook-Nonce": uuid.uuid4().hex,
            "X-Webhook-Timestamp": str(int(time.time())),
        },
        payload={
            "model": "sale.order",
            "record_id": record.id,
            "op": "create",
        },
        timeout=3,
    )
```

Ou alternativement, un **type d'action serveur "Notification HTTP"** intégré (sans code Python) configurable via l'interface Odoo avec :
- URL de destination
- Headers (dont secret partagé)
- Template de payload (Jinja2)
- Timeout
- Retry policy

## Exigences techniques

| Exigence | Détail |
|---|---|
| **Sécurité** | Header secret (type `X-Webhook-Token`), timestamp, nonce anti-rejeu |
| **Non bloquant** | Si l'endpoint externe est down ou lent, Odoo ne doit pas bloquer la sauvegarde du record (try/except, timeout court 3-5s, log silencieux) |
| **Logging** | Trace dans `ir.logging` pour diagnostic (succès/échec, durée, code HTTP) |
| **Configurable par System Parameter** | Pas de secret en dur dans le code Python des actions automatisées |
| **Compatible base_automation** | Déclenchable depuis `on create`, `on write`, `on unlink` via l'interface standard Odoo |

## Modèles concernés côté Couffrant

Dans un premier temps (pilote) :
- `sale.order` (devis / commandes)
- `crm.lead` (opportunités)
- `mail.activity` (activités planifiées)

Puis élargissement progressif à :
- `res.partner`, `calendar.event`, `account.move`
- `of.planning.tour`, `of.planning.task`, `of.planning.intervention.template`
- `of.survey.answers`, `of.survey.user_input.line`, `of.custom.document`

Environ **14 modèles** au total. Pour chaque modèle, 3 règles (`create`, `write`, `unlink`).

## Bénéfices attendus

- **Temps-réel strict** (< 1s de latence au lieu de 1-2 min actuellement en polling)
- **Charge Odoo réduite** (pas de polling permanent)
- **Réutilisable pour d'autres intégrations externes** (Slack, Teams, bus interne, etc.)
- **Conforme pratiques modernes** (webhooks = standard d'intégration 2020+)

## Ce dont nous avons besoin de votre part

1. **Confirmation de faisabilité** : cette évolution est-elle envisageable dans votre roadmap ?
2. **Devis et délai indicatif** si développement payant
3. **Alternative éventuelle** : existe-t-il déjà un module de la communauté Odoo (OCA ou autre) qui ferait l'affaire et que vous pourriez installer/maintenir sur notre instance ?

## Contact

Guillaume Perrin
Couffrant Solar — 18 rue de Langon, 41200 Romorantin-Lanthenay
[contact à compléter]

---

**Note** : côté Raya, toute l'infrastructure de réception des webhooks est **déjà en place et testée** (endpoint `/webhooks/odoo/record-changed`, vérification de secret, anti-rejeu par nonce, dédoublonnage, queue persistée, worker asynchrone, monitoring temps-réel). Il ne manque que la partie "émission côté Odoo" qui est bloquée par la sandbox.
