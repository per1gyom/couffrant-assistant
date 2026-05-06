# Audit complet : connexions, fraîcheur, stabilité

**Date** : 06 mai 2026 — fait à la demande de Guillaume après la refonte du matin
**Contexte** : Guillaume a une intuition que des webhooks sont déjà en place et veut s'assurer qu'on ne crée pas de redondance avec le polling adaptatif qu'on vient de pousser (commits `4d96286` à `d12b74a`).

---

## 🎯 TL;DR

L'intuition de Guillaume est juste : **un système webhook existe**. Mais en réalité il est très partiellement actif :

- ✅ **1 webhook Microsoft Graph actif** sur **1 connexion sur 9** (conn=6 `guillaume@couffrant-solar.fr` Inbox uniquement)
- ❌ **0 watch Gmail Pub/Sub actif** (job désactivé via env var Railway, setup GCP non finalisé)
- ❌ **conn=14 `contact@couffrant-solar.fr`** (la boîte qui reçoit le PLUS de mails — 13/4h) **n'a pas de webhook** parce qu'elle utilise `auth_type='manual'` qui ne supporte pas les Graph subscriptions

**Conclusion** : le polling 5 min reste **indispensable comme voie principale** pour 8/9 connexions. Les étapes 5 + 6 du matin (polling adaptatif jour/nuit + tool refresh on-demand) sont **complémentaires aux webhooks**, pas redondantes. Aucun travail jeté.

**3 leviers d'amélioration possibles** identifiés en fin de doc.

---

## 🗺️ État détaillé des canaux d'ingestion par connexion

### Vue d'ensemble (06/05/2026 11h57)

| ID | Type | Boîte | Polling delta | Webhook | Notes |
|---|---|---|---|---|---|
| 1 | drive | SharePoint Commun | ✅ 5 min | ❌ | Pas de webhook implémenté |
| 3 | odoo | Openfire Guillaume | ✅ 2 min | ⚠️ partiel* | Cf. webhook_odoo.py |
| 4 | gmail | per1.guillaume@gmail.com | ✅ 5 min | ❌ | Pas de Pub/Sub watch |
| 6 | microsoft | guillaume@couffrant-solar.fr | ✅ 5 min | ✅ Inbox seul | Subscription expire 7/05 05:35 |
| 7 | gmail | sasgplh (GPLH) | ✅ 5 min | ❌ | manual, pas de Pub/Sub |
| 8 | gmail | sci.romagui (Romagui) | ✅ 5 min | ❌ | manual, pas de Pub/Sub |
| 9 | gmail | sci.gaucherie (Gaucherie) | ✅ 5 min | ❌ | manual, pas de Pub/Sub |
| 10 | gmail | sci.mtbr (MTBR) | ✅ 5 min | ❌ | manual, pas de Pub/Sub |
| 14 | outlook | contact@couffrant-solar.fr | ✅ 5 min | ❌ | auth=manual bloque webhook |

\* *Odoo : le code webhook existe mais Odoo n'envoie pas de notifications natives, c'est plutôt utilisé pour des événements internes (création de devis, etc.). Le polling 2 min reste la voie principale.*

### Activité réelle constatée (4h dernières)

```
conn= 1 SharePoint Commun           polls= 45  new=1
conn= 3 Openfire Guillaume          polls=117  new=2069
conn= 4 per1.guillaume@gmail.com    polls= 52  new=4
conn= 6 guillaume@couffrant-solar   polls= 48  new=2  ← webhook actif sur celui-ci
conn= 7 GPLH                        polls= 45  new=0
conn= 8 Romagui                     polls= 45  new=0
conn= 9 Gaucherie                   polls= 45  new=0
conn=10 MTBR                        polls= 45  new=0
conn=14 contact@couffrant-solar.fr  polls= 45  new=13  ← la plus active, sans webhook
```

**Observation clé** : conn=14 capte 13 nouveaux mails en 4h **uniquement via le polling 5 min**. Si on faisait sauter le polling (en pensant que les webhooks couvrent tout), on raterait ces 13 mails (ou on les détecterait avec 4h de retard).

---

## 🏗️ Architecture du canal webhook Microsoft Graph

### Vue logique

```
┌─────────────────┐       1.notification       ┌──────────────────────┐
│  Microsoft 365  │ ─────────────────────────▶ │ POST /webhook/       │
│   (mailbox)     │   "tu as un nouveau msg"   │     microsoft        │
└─────────────────┘                            └──────────┬───────────┘
                                                          │
                              2. validate clientState     │
                                                          ▼
                                              ┌────────────────────────┐
                                              │  MODE LEGACY           │
                                              │  fetch direct du msg   │
                                              │  via Graph API         │
                                              │  → process_incoming    │
                                              └────────────────────────┘
                                                  OU
                                              ┌────────────────────────┐
                                              │  MODE TRIGGER          │
                                              │  declenche un poll     │
                                              │  delta sur conn        │
                                              │  → mail_outlook_delta  │
                                              └────────────────────────┘
```

Source : `app/routes/webhook.py:52-130`

### Mode actuel (à confirmer en lisant Railway env)

Variable Railway : `OUTLOOK_WEBHOOK_TRIGGER_MODE`. Si `true` → mode TRIGGER, sinon LEGACY (défaut).

Avantages MODE TRIGGER :
- Un seul code path d'ingestion (le polling delta), simplification
- Si webhook plante, le poll automatique 5 min rattrape sans rien à faire
- Facile à débugger (1 seul pipeline à comprendre)

Inconvénient MODE TRIGGER :
- Petite latence supplémentaire : webhook → poll delta (200-800 ms additionnels)

### Lifecycle des subscriptions

- **Création** : `app/connectors/microsoft_webhook.py:create_subscription()` au moment de la connexion OAuth + via cron `_job_webhook_setup` (run au démarrage)
- **Renouvellement** : cron `_job_webhook_renewal` toutes les 6h (renouvelle si expire dans <24h, recrée si expirée)
- **Lifecycle events Microsoft** (`subscriptionRemoved`, `missed`, `reauthorizationRequired`) : POST /webhook/microsoft/lifecycle gère les 3 cas

### Pourquoi conn=14 (contact@) n'a pas de webhook

`contact@couffrant-solar.fr` est connectée avec `auth_type='manual'`, c'est-à-dire que le mot de passe d'application a été tapé manuellement (pas via OAuth complet avec client_id/secret).

**Microsoft Graph subscriptions exigent** :
- Un access_token OAuth émis pour une app Azure AD enregistrée
- Le scope `Mail.Read` (ou supérieur)
- Une URL de webhook publique en HTTPS validée

Un token "manual" issu d'un mot de passe d'application n'a généralement pas la totalité des droits/contexte nécessaires pour créer une Graph subscription. Le job `ensure_all_subscriptions` tente de créer une sub pour conn=14, échoue silencieusement, et le polling 5 min prend le relais.

**Vérification** : aucune entrée dans `webhook_subscriptions` pour `connection_id=14`.

---

## 🏗️ Architecture du canal Gmail Pub/Sub

### Vue logique (théorique, pas activé en prod)

```
┌──────────────┐  watch()    ┌───────────────────┐    push     ┌────────────────┐
│   Gmail API  │ ─────────▶  │  GCP Pub/Sub      │ ──────────▶ │ POST /webhook/ │
│   (mailbox)  │             │  Topic            │             │  gmail/pubsub  │
└──────────────┘             └───────────────────┘             └────────┬───────┘
                                                                        │
                                                                        ▼
                                                              ┌──────────────────┐
                                                              │ extract historyId│
                                                              │ → trigger poll   │
                                                              │   gmail history  │
                                                              └──────────────────┘
```

Source : `app/routes/webhook_gmail_pubsub.py:165-302`

### Pourquoi 0 watch active

Le job `run_gmail_watch_renewal` (qui crée et renouvelle les watches) est **DÉSACTIVÉ par défaut** :

```python
# app/scheduler_jobs.py:462
if _job_enabled("SCHEDULER_GMAIL_WATCH_RENEWAL_ENABLED", default=False):
```

Probablement parce que le **setup Google Cloud Pub/Sub n'a jamais été finalisé** :
1. ☐ Créer un topic Pub/Sub côté Google Cloud Console
2. ☐ Créer une subscription Pub/Sub qui POST sur `https://app.raya-ia.fr/webhook/gmail/pubsub?token=<SECRET>`
3. ☐ Donner les permissions IAM à `gmail-api-push@system.gserviceaccount.com` pour publier sur le topic
4. ☐ Ajouter `GMAIL_WATCH_TOPIC=projects/<projectId>/topics/<topicName>` dans Railway env
5. ☐ Ajouter `GMAIL_PUBSUB_VERIFICATION_TOKEN=<SECRET>` dans Railway env
6. ☐ Activer `SCHEDULER_GMAIL_WATCH_RENEWAL_ENABLED=true` dans Railway env

Étapes 1-3 = setup GCP (~30 min, hors code). Étapes 4-6 = config Railway (~5 min).

---

## 🔍 Analyse de redondance polling vs webhooks

### Le polling reste utile même quand le webhook marche

Pour conn=6 (la seule avec webhook), polling et webhook coexistent. Est-ce de la redondance gaspillée ?

**Non, pour 4 raisons** :

1. **Filet de sécurité** : si Microsoft loupe une notification (ça arrive : `lifecycle event: missed`), le poll 5 min rattrape sans intervention. Robustesse > optimisation.

2. **Heartbeat actif** : `connection_health` a besoin de polls réguliers pour détecter qu'une connexion est en panne. Sans poll, on ne sait jamais qu'un webhook a cessé de fonctionner. Le poll sert aussi de check de santé.

3. **Délai de re-création de sub** : si une sub expire ou est supprimée Microsoft-side, on prend jusqu'à 6h avant de la recréer (cron). Pendant ces 6h, le poll est la seule voie.

4. **Coverage incomplet** : la sub conn=6 ne couvre que **Inbox**. SentItems et JunkEmail ne sont pas wébhookés. Le poll, lui, couvre les 3 dossiers.

### Quantification de l'économie potentielle

Si on désactivait le polling sur conn=6 (la seule wébhookée), on économiserait ~288 polls/jour. Sur 9 connexions, c'est <4% du trafic total. **Gain marginal vs perte de robustesse : ratio défavorable.**

L'étape 5 (polling adaptatif jour/nuit) économise **~57% de polls hors heures ouvrées** (de 12 polls/h à 2 polls/h sur 14h × 5 jours + 48h weekend = beaucoup plus que les 4% ci-dessus).

→ **Le bon levier d'économie c'était l'étape 5, pas la suppression du polling.**

---

## 🔬 Cohérence avec l'étape 5 + 6 du matin

### Étape 5 (polling adaptatif jour/nuit)
- **Effet sur conn=6 (avec webhook)** : webhook garde sa réactivité temps réel, polling tombe à 30 min la nuit. Aucun impact négatif.
- **Effet sur conn=14 (sans webhook)** : polling tombe à 30 min la nuit. **Légère perte de réactivité nocturne** (mail urgent reçu à 2h du matin vu à 2h30 max). Acceptable car Guillaume ne traite pas de mails à 2h.
- **Effet sur les autres Gmail (sans Pub/Sub)** : idem conn=14.

### Étape 6 (smart adaptive + tool refresh)
- **Niveau 2 (user actif)** : si Guillaume bosse à 22h, polling reste à 5 min sur tout le tenant. Compense l'absence de webhook sur 8/9 connexions.
- **Niveau 3 (tool refresh)** : Raya peut forcer un refresh quand elle juge utile. Compense un éventuel délai de 30 min hors heures ouvrées avec user inactif.

### Verdict cohérence
**Aucune redondance** entre les étapes 5+6 et les webhooks. Au contraire :
- Webhook conn=6 = temps réel sur 1 boîte sur 9
- Étapes 5+6 = pallient l'absence de webhook sur les 8 autres
- Polling adaptatif = garde le filet de sécurité sans gaspiller la nuit

---

## 🛠️ Recommandations (par ordre d'impact / coût)

### 🥇 Priorité 1 : étendre la subscription Microsoft conn=6 aux 3 dossiers
**Coût** : 30 min de code dans `app/connectors/microsoft_webhook.py:create_subscription`
**Gain** : couvre temps réel les 3 dossiers Inbox + SentItems + JunkEmail au lieu d'1
**Risque** : très faible, juste un paramètre `resource` à élargir

Aujourd'hui : `resource = "me/mailFolders/inbox/messages"`
Demain : créer 3 subscriptions séparées (1 par dossier) ou utiliser `me/messages` qui couvre tout.

### 🥈 Priorité 2 : activer Gmail Pub/Sub si le ROI le justifie
**Coût** : ~30 min setup GCP + 5 min Railway env + tests (~1h total)
**Gain** : temps réel sur 5 boîtes Gmail (conn 4, 7, 8, 9, 10)
**Risque** : moyen — le code existe et a été testé, mais l'absence d'usage en prod fait qu'on ne sait pas exactement comment Gmail réagit aux watches sur des boîtes dormantes

**Question préalable à se poser** : combien de mails arrivent sur les 4 boîtes secondaires (Romagui, Gaucherie, MTBR, GPLH) en moyenne ? Vu la stat des 4h dernières (0 mail), elles dorment 99% du temps. Le webhook n'apporterait quasi rien — le polling 5 min suffit largement.

→ **Probablement pas worth it** sauf si tu actives Pub/Sub uniquement sur per1.guillaume@gmail.com (la plus active).

### 🥉 Priorité 3 : reconnecter conn=14 (contact@) en OAuth complet
**Coût** : Guillaume reconnecte la boîte via le flux OAuth complet (5 min)
**Gain** : webhook sur la boîte la plus active (13 mails / 4h !)
**Risque** : faible — flux OAuth standard

**Attention** : ça nécessite que `contact@couffrant-solar.fr` soit un compte M365 réel à part entière (pas juste un alias / shared mailbox). Si c'est une shared mailbox, il faut activer les scopes `Mail.Read.Shared` + un user "owner" qui passe l'OAuth.

D'après le doc `procedure_reconnexion_contact_05mai.md` (à vérifier), il y a peut-être déjà eu une tentative.

### 🔧 Priorité 4 (peut être noté pour plus tard) : monitoring de la subscription Microsoft
Aujourd'hui aucune alerte si la sub conn=6 expire et que `_job_webhook_renewal` échoue. On peut ajouter un check dans `connection_health` qui alerte si :
- `webhook_subscriptions.expires_at < NOW() + INTERVAL '12 hours'`
- ET pas de renew event dans les 24h

---

## ❓ Questions ouvertes / décisions à prendre par Guillaume

1. **Reconnecte-t-on conn=14 en OAuth complet ?** Si oui, on bénéficie d'un webhook sur la boîte la plus active. Quel est l'historique de pourquoi c'est resté en `auth='manual'` ?

2. **Active-t-on Gmail Pub/Sub ?** Vraisemblablement marginal vs le polling 5 min. À reporter sauf si projet de scale (>5 tenants).

3. **Activer le mode TRIGGER pour Microsoft webhook ?** Aujourd'hui défaut LEGACY (fetch direct). TRIGGER = un seul pipeline d'ingestion (plus simple à raisonner). Test côté prod possible via une variable env.

4. **Étendre la sub Microsoft à SentItems + JunkEmail ?** Win facile. Je peux le faire en 30 min si tu valides.

---

## 📊 Métriques de référence pour suivre l'effet des changements

À mesurer 1 semaine après chaque changement :

| Métrique | Source | Objectif |
|---|---|---|
| Latence d'ingestion mail (réception → en base) | logs Railway + `mail_memory.created_at - received_at` | <30 sec en jour, <30 min en nuit |
| Taux de webhook reçus / mails ingérés | webhook_subscriptions vs mail_memory | maximiser sur conn=6, viser >50% |
| Polls/jour (charge) | `connection_health_events` | -57% confirmé après étape 5 |
| Mails ratés (détectés tardivement) | écart `received_at` vs `created_at` | <0.5% |

---

## 📚 Références code

- `app/routes/webhook.py` : entry points Microsoft Graph webhooks
- `app/routes/webhook_gmail_pubsub.py` : entry point Gmail Pub/Sub
- `app/connectors/microsoft_webhook.py` : `create_subscription`, `ensure_all_subscriptions`
- `app/jobs/mail_gmail_watch.py` : `setup_gmail_watch`, `run_gmail_watch_renewal`
- `app/jobs/maintenance.py:52-69` : jobs cron `_job_webhook_setup`, `_job_webhook_renewal`
- `app/scheduler_jobs.py:91-95` + `464-475` : enregistrement APScheduler
- `app/polling_schedule.py` (nouveau ce matin) : polling adaptatif jour/nuit + détection user actif
- `app/connection_health.py` : monitoring + effective_status

---

## 🗓️ Historique de cet audit

- **06/05/2026 12h** : audit créé après refonte étapes 3-6 du matin (commits 4d96286 → d12b74a)
