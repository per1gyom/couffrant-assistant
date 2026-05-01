# Journal de session — 1er mai 2026

**Date :** vendredi 1er mai 2026
**Auteur :** Guillaume + Claude (session entiere)
**Contexte :** Implementation des Semaines 1, 2 et 3 du chantier
Connexions Universelles (voir docs/vision_connexions_universelles_01mai.md)

---

## 🎯 Resume ultra-court

```
Une journee massive : 3 semaines de roadmap implementees, deployees
en prod, et validees en conditions reelles.

LE BUG 17 JOURS (du 14/04 au 01/05) EST OFFICIELLEMENT ENTERRE.
4 niveaux de defense en place pour le mail Outlook. Plus jamais
possible.
```

---

## 📦 Ce qui a ete livre en prod aujourd'hui

### Semaine 1 — Foundations (matin)

```
✅ 7 nouvelles tables DB (M-CU01 a M-CU07)
   - connection_health (etat de chaque connexion)
   - connection_health_events (historique des polls)
   - attachment_index, attachment_chunks (pieces jointes)
   - tenant_drive_blacklist, tenant_whatsapp_whitelist
   - tenant_attachment_rules

✅ Module connection_health (459 lignes)
   Liveness check universel : a chaque poll, on log l event.
   Le silence = absence de log recent = vraie panne.

✅ Module connection_resilience (441 lignes)
   Self-healing 4 etapes + circuit breaker.
   Decorateur @protected reutilisable.

✅ Module alert_dispatcher (619 lignes)
   5 niveaux : info / warning / attention / critical / blocking
   Multi-canaux : Twilio SMS, email, push, chat in-app, Teams

✅ Module attachment_pipeline (502 lignes)
   Pipeline comprehension : extraction texte -> Vision IA conditionnelle

✅ Page /admin/health/page (302 lignes)
   Dashboard avec pastille couleur par connexion.
```

### Semaine 2 — Odoo (debut apres-midi)

```
✅ Odoo branche au monitoring universel
   Polling toutes les 2 min instrumente avec record_poll_attempt
   Apparait dans /admin/health/page comme les autres connexions

✅ Resilience XML-RPC
   @protected sur _poll_model() pour retry automatique

✅ Reconciliation nocturne 4h
   Compare count Odoo vs count Raya par modele
   Alerte WARNING si delta > 1%

✅ Decision Q12bis tranchee : Odoo 16 COMMUNITY confirme
   (sandbox safe_eval bloque les imports Python dans
   base.automation, donc pas de webhooks natifs possibles
   sans un module custom OpenFire en attente)
```

### Semaine 3 — Outlook (refonte complete)

```
✅ 3.3 - Module mail_outlook_delta_sync (582 lignes)
   Polling delta toutes les 5 min sur 3 dossiers :
     - Inbox (entrants)
     - SentItems (sortants - INVISIBLE avant)
     - JunkEmail (rattrapage spam)
   Stocke delta_link par dossier dans connection_health.metadata

✅ 3.4 - Mode WRITE activable
   Variable Railway OUTLOOK_DELTA_SYNC_WRITE_MODE
   Reutilise process_incoming_mail (source-agnostic) pour
   ingerer les mails. Anti-doublon via mail_exists.

✅ 3.5 - Lifecycle Notifications Microsoft (LE FIX BUG 17 JOURS)
   3 events ecoutes :
     - subscriptionRemoved -> recreation auto + alerte
     - missed -> rattrapage par polling
     - reauthorizationRequired -> refresh token + renew sub

✅ 3.6 - Mode TRIGGER du webhook
   Variable Railway OUTLOOK_WEBHOOK_TRIGGER_MODE
   Le webhook ne fait plus fetch direct : il declenche un poll
   delta sur la connexion concernee. Un seul code path d ingestion.
   Reactivite ~30 sec preservee.

✅ 3.7 - Reconciliation nocturne mail (4h30)
   Compare count Microsoft vs count mail_memory
   Alerte WARNING si delta > 1% et > 50 mails

⏳ 3.8 - Suppression du code legacy fetch
   Reportee : a faire apres 24-48h de validation prolongee
```

### Bugs detectes et fixes en cours de route

```
❌ BUG 1 - Query SQL "username does not exist"
   La colonne username n existe pas dans tenant_connections
   Fix : JOIN avec connection_assignments pour resoudre l user
   Commit dedie

❌ BUG 2 - Doublons mail_memory (3 cas detectes en prod)
   Cause : mail_exists() avait un filtre tenant_id casse en SQL
   (`tenant_id = NULL` est unknown, pas false)
   Fix : si tenant_id None passe en parametre, on ne filtre pas dessus

❌ BUG 3 - tenant_id NULL pour les nouveaux mails (17 cas)
   Cause : insert_mail() ne mettait pas tenant_id dans le INSERT
   Fix : on lit data.get("tenant_id") avec fallback _resolve_tenant_id

✅ Migration cleanup automatique
   Supprime les 3 doublons existants au prochain redemarrage
   (Guillaume n a rien eu a faire manuellement)
```

---

## 🛡️ 4 niveaux de defense actifs sur Outlook

```
NIVEAU 1 - Webhook trigger        ← reactif ~30 sec
NIVEAU 2 - Polling delta 5 min    ← garantie max 5 min
NIVEAU 3 - Lifecycle Notifications ← anti-silence Microsoft
NIVEAU 4 - Reconciliation 4h30    ← filet ULTIME, max 24h

Pour qu un mail manque, il faudrait que les 4 defenses tombent
en meme temps. Probabilite quasi nulle.
```

---

## ✅ Validations en prod

```
TEST FONCTIONNEL VALIDE :
  - Guillaume envoie un mail test depuis Gmail vers Outlook a 14h49
  - Microsoft notifie le webhook
  - Le webhook (mode TRIGGER) declenche un poll delta sur la conn #6
  - Mail ingere dans mail_memory a 14h49:41 avec tenant_id rempli
  - Event log dans connection_health_events a 14h49:43
  - Reactivite totale : ~30 sec ✅

OBSERVATIONS POSITIVES :
  - Mail SORTANT (Re: ouverture API) capte via SentItems
    (avant Semaine 3 : INVISIBLE dans Raya)
  - 0 doublon en base
  - 0 mail avec tenant_id NULL
  - 3 connexions Outlook healthy en permanence
  - Odoo healthy (le polling continue normalement)
```

---

## ⚠️ A PREVOIR — Scan de rattrapage + onboarding historique mails

### Le besoin

```
Demande Guillaume (1er mai 16h00 environ) :

  "Une fois que tout ca marche, faire un scan de mes boites mail
   pour mettre en graphe tous les mails qui sont :
     - passes au travers pendant les pauses / pannes / mises a jour
     - les historiques plus anciens
   Il faudra prevoir de mettre ca au propre avant que je l utilise
   correctement."
```

### Pourquoi c'est important

```
Periode de panne identifiee :
  Du 14/04 au 01/05 -> 17 JOURS de mails Outlook potentiellement
  non ingeres (le webhook plantait silencieusement).
  
Le polling delta peut rattraper PARTIELLEMENT cette periode si le
delta_link initial revient assez loin (Microsoft retient ~30 jours
de delta history par defaut).

Mais pour les mails ANTERIEURS au 14/04, et pour les pauses futures
(maintenance, redeploys longs), il faut un mecanisme dedie.
```

### Ce qu'on doit construire

```
SCAN DE RATTRAPAGE (post-incident)
  Endpoint admin /admin/sync/outlook ou bouton dans la UI
  Pour une connexion donnee + une periode donnee :
    - Recupere TOUS les mails de cette periode via Microsoft Graph
      (pas via delta, mais via /me/messages?$filter=receivedDateTime)
    - Verifie pour chaque mail s il est deja en base (mail_exists)
    - Si non : passage par process_incoming_mail (filtrage, analyse,
      vectorisation, graphe)
  Defaut : 30 derniers jours
  Configurable : 3 mois, 6 mois, 12 mois, tout
  
ONBOARDING HISTORIQUE (a la connexion d une nouvelle boite)
  Quand un user connecte une boite Outlook ou Gmail :
    UI demande la profondeur souhaitee :
      [ ] 3 mois     [ ] 6 mois     [x] 12 mois     [ ] tout
    Job de fond lance dans la foulee :
      - Pagination Microsoft Graph par batch de 50-100 mails
      - Insertion progressive avec progress visible dans UI
      - Resume si interrompu (curseur sauvegarde)
  Pour Guillaume : "tout" (decision tracee dans le doc vision)
  Pour les futurs clients : 12 mois par defaut

PROTECTION CONTRE LES PANNES FUTURES
  La reconciliation nocturne (Etape 3.7) detecte deja les
  divergences en max 24h. Si une fuite est detectee, l alerte
  WARNING devra proposer un bouton "rattrapage automatique"
  qui declenche le scan de la periode incriminee.
```

### Statut

```
NON IMPLEMENTE -- A FAIRE APRES Semaine 4 (Gmail)
A integrer dans le doc vision section onboarding historique
Note : ne pas oublier d inclure aussi Gmail (history API)
       et Drive (delta query) dans le meme mecanisme universel.
```

---

## 🚦 Ce qui reste pour cloturer Outlook

```
A FAIRE DANS UNE PROCHAINE SESSION (calmement) :
  - Etape 3.8 : suppression du code legacy fetch
    Une fois mode TRIGGER valide depuis 24-48h en prod
    Le code _process_mail (fetch direct) devient obsolete
    Suppression propre dans un commit dedie

  - Scan de rattrapage Outlook (voir section au-dessus)
    Avant que Guillaume utilise vraiment l outil au quotidien
```

---

## 📊 Statistiques de la session

```
COMMITS PUSHES SUR MAIN AUJOURD HUI :
  ~15 commits (Semaines 1, 2, 3 + 3 fixes deploiement + cleanup auto)

LIGNES DE CODE AJOUTEES :
  ~4500 lignes brutes
  
FICHIERS MODIFIES OU CREES :
  - app/connection_health.py (459 nouvelles lignes)
  - app/connection_resilience.py (441 nouvelles lignes)
  - app/alert_dispatcher.py (619 nouvelles lignes)
  - app/attachment_pipeline.py (502 nouvelles lignes)
  - app/jobs/connection_health_check.py (60 nouvelles lignes)
  - app/jobs/odoo_polling.py (instrumentation +120 lignes)
  - app/jobs/odoo_reconciliation.py (218 nouvelles lignes)
  - app/jobs/mail_outlook_delta_sync.py (582 nouvelles lignes)
  - app/jobs/mail_outlook_reconciliation.py (282 nouvelles lignes)
  - app/connectors/microsoft_webhook.py (+22 lignes)
  - app/routes/webhook.py (+193 lignes lifecycle + 76 trigger)
  - app/routes/admin/health.py (302 nouvelles lignes)
  - app/database_migrations.py (+190 lignes : 7 tables + cleanup)
  - app/scheduler_jobs.py (+47 lignes : 4 nouveaux jobs)
  - app/mail_memory_store.py (refonte : +82 lignes pour les fixes)

VARIABLES RAILWAY AJOUTEES PAR GUILLAUME :
  - SCHEDULER_OUTLOOK_DELTA_SYNC_ENABLED=true
  - OUTLOOK_DELTA_SYNC_WRITE_MODE=true
  - OUTLOOK_WEBHOOK_TRIGGER_MODE=true

ZERO REGRESSION EN PROD.
LE WEBHOOK ET LE POLLING ONT TOURNE EN PARALLELE TOUT L APRES-MIDI.
```

---

## 🎯 Suite immediate

```
PROCHAIN OBJECTIF : Semaine 4 - Gmail

Refonte Gmail similaire a Outlook :
  - Polling history API toutes les 5 min
  - Multi-boites (Guillaume a 6 boites Gmail)
  - Pub/Sub Watch (equivalent webhook Microsoft via Google Cloud)
  - Watch renewal nocturne (expiration 7 jours chez Google)
  - Reconciliation nocturne 5h

ATTENTION SIGNALEE :
  Logs Railway montrent des erreurs 401 Unauthorized sur Gmail
  depuis le matin :
    [GmailConnector] search_mail: 401 Client Error: Unauthorized
  Les tokens Gmail sont expires/revoquees. A reauthentifier avant
  d entamer la Semaine 4 (sinon le polling tournera dans le vide).
```

