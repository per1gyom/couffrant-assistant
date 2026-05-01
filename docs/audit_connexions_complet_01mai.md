# Audit complet des connexions Raya — 1er mai 2026

**Statut :** Audit Phase 1 (vue d'ensemble) terminé
**Méthode :** Inspection DB + lecture code, AUCUNE modification de prod
**Demandé par :** Guillaume, suite découverte 500 sur webhook Microsoft
**Périmètre :** Toutes les connexions de données (entrantes ET sortantes)

---

## 🎯 Règle d'or rappelée par Guillaume

> "Toutes les données auxquelles Raya a accès doivent être mises en
> graphe et vectorisées. Pas d'exception. Une donnée non graphée
> est une donnée invisible. Le graphe doit être ultra complet,
> ultra précis, et le plus performant possible."

Cette règle s'applique à **toutes** les sources : mails (entrant ET
sortant), fichiers Drive/SharePoint, ERP/CRM, conversations Teams,
WhatsApp, et toute future intégration.

---

## 📊 Inventaire des connexions (vue tenant_connections)

| ID | Type | Label | Status | Email | Creds | Tenant |
|---|---|---|---|---|---|---|
| 1 | drive | SharePoint Commun | connected | NULL | **VIDE** | couffrant_solar |
| 2 | outlook | Outlook Guillaume | connected | NULL | **VIDE** | couffrant_solar |
| 3 | odoo | Openfire Guillaume | connected | NULL | **VIDE** | couffrant_solar |
| 4 | gmail | per1.guillaume@gmail.com | connected | per1.guillaume@gmail.com | OK | couffrant_solar |
| 6 | microsoft | guillaume@couffrant-solar.fr | connected | guillaume@couffrant-solar.fr | OK | couffrant_solar |
| 7 | gmail | GPLH | connected | sasgplh@gmail.com | OK | couffrant_solar |
| 8 | gmail | Romagui | connected | sci.romagui@gmail.com | OK | couffrant_solar |
| 9 | gmail | Gaucherie | connected | sci.gaucherie@gmail.com | OK | couffrant_solar |
| 10 | gmail | MTBR | connected | sci.mtbr@gmail.com | OK | couffrant_solar |
| 12 | outlook | Contact Couffrant Solar | connected | guillaume@couffrant-solar.fr | OK | couffrant_solar |
| 13 | gmail | charlottecouffrant@gmail.com | not_configured | NULL | VIDE | juillet |

**Total : 11 connexions (10 actives, 1 en attente)**

---

## 🔴 Problèmes critiques identifiés

### P1. Webhook Microsoft retourne 500 depuis ~17 jours

**Symptôme** : `POST /webhook/microsoft` retourne systématiquement 500.

**Conséquence** :
- 0 mail Outlook ingéré depuis le 14 avril 2026
- Microsoft renvoie automatiquement les notifications mais elles
  sont toutes perdues
- Risque de désactivation de la subscription par Microsoft (déjà
  cassée et recréée plusieurs fois probablement)

**Stack trace** : tronquée dans les logs Railway, on voit les
middlewares Starlette/FastAPI mais pas le code applicatif. Cela
suggère que l'erreur est levée dans un import lazy, dans un
middleware, ou avant d'atteindre le handler du router.

**Cause exacte** : non identifiée — nécessite instrumentation 
(wrapping try/except large + traceback.format_exc) au moment du fix.

**Pistes possibles** :
1. Import lazy de `webhook_ms_handlers` qui plante
2. SecurityHeadersMiddleware qui plante en accédant à
   response.headers sur une réponse en streaming
3. Exception non-HTTPException qui passe par le handler 303 
   ajouté en LOT 3 du chantier 2FA et qui re-raise mal

### P2. Polling Gmail INACTIF par défaut

**Symptôme** : la variable `SCHEDULER_GMAIL_ENABLED` n'est PAS posée
sur Railway (vérifié par Guillaume). Le code utilise default=False.

**Conséquence** :
- 0 mail Gmail ingéré depuis le 6 avril 2026 (25 jours)
- Aucune des 5 boîtes Gmail (perso + 4 SCI) ne fait de polling
- Les boîtes SCI créées le 28/04 n'ont JAMAIS reçu de mail en base

**Anomalie de design** :
- Webhook Microsoft : default=True (actif)
- Gmail polling : default=False (inactif)
- Asymétrie sans raison documentée

**Réparation possible** :
- Court terme : poser `SCHEDULER_GMAIL_ENABLED=true` sur Railway
- Long terme : changer le default à True dans le code, retirer la
  variable inutile

### P3. Connexions fantômes (status menteur)

**3 connexions affichées comme "connected" mais avec credentials VIDES** :
- ID=1 "SharePoint Commun" → credentials dans variables Railway 
  probablement, mais incohérent avec le modèle V2
- ID=2 "Outlook Guillaume" → vraie connexion fantôme (résidu legacy)
- ID=3 "Openfire Guillaume" (Odoo) → credentials dans variables
  Railway (ODOO_URL/LOGIN/PASSWORD/API_KEY)

**Conséquence** :
- ID=2 affiche "connected" alors qu'elle ne fait rien
- L'utilisateur ne sait pas si une connexion fonctionne vraiment
- Aucune source unique de vérité sur l'état réel d'une connexion

### P4. Subscription webhook Microsoft incomplète

**Constat DB** :
- 2 boîtes Outlook actives (ID=6 et ID=12)
- 1 SEULE subscription webhook (pour ID=6 Guillaume principal)
- ID=12 "Contact Couffrant Solar" n'a AUCUN webhook abonné

**Conséquence** :
- Même si on répare le bug 500, les mails de la boîte
  contact@couffrant-solar.fr ne seront pas notifiés
- Il faut que `ensure_all_subscriptions` les voie ET puisse résoudre
  l'email associé (ID=12 a connected_email rempli, donc devrait OK)

### P5. Aucun monitoring de fraîcheur

**Constat** :
- Pas de table `connection_health_events` qui trace chaque
  tentative de polling/ingestion
- Pas d'alerte automatique si une boîte ne reçoit rien depuis X heures
- Tu n'as eu AUCUNE notification du silence depuis 17 jours

**C'est précisément ce qui te manque pour vendre Raya avec une
promesse "alertes proactives"**.

### P6. Heartbeats figés depuis le reboot

**Constat** : tous les composants (sauf scheduler) ont un heartbeat
figé à l'heure du dernier reboot Railway (30/04 22:34) :
- webhook_microsoft
- gmail_polling (normal, désactivé)
- proactivity_scan
- heartbeat_morning

**Hypothèses** :
- Soit ces jobs plantent silencieusement au démarrage
- Soit ces jobs tournent mais ne posent pas leur heartbeat 
  (régression du pattern heartbeat)
- Soit le scheduler ne les enregistre pas correctement

**Action** : à investiguer en lisant les logs Railway des 24
dernières heures pour voir les "[Scheduler] Job enregistré : ..."
au démarrage.

### P7. Doublon legacy/V2

**Constat** : `per1.guillaume@gmail.com` existe DANS `gmail_tokens` 
(legacy) ET DANS `tenant_connections` (V2). Risque de conflit de
tokens lors du refresh.

**Conséquence** : si les deux pointent vers le même refresh_token
et qu'un des deux le refresh, l'autre devient invalide.

---

## 🟡 Problèmes moyens

### M1. Drive/SharePoint figé depuis 11 jours

**Constat** : `drive_semantic_content` a 5 086 records, dernier
indexé le 20 avril. Pas catastrophique car les fichiers SharePoint
changent peu souvent.

**À vérifier** : y a-t-il un job de scan Drive et tourne-t-il ?

### M2. Mail sortant (sent_mail_memory) figé depuis le 5 avril

**Constat** : `sent_mail_memory` n'a rien depuis 26 jours. Probablement
même cause que les mails entrants (polling Gmail désactivé +
webhook Outlook cassé).

### M3. Subscription Microsoft expire le 3 mai

**Constat** : la seule subscription active expire dans 1j 21h. Si
`_job_webhook_renewal` (default=True donc actif) plante, on perd
définitivement la subscription. Pas de filet de sécurité.

---

## ✅ Ce qui fonctionne

- **Connexion Microsoft Guillaume (ID=6)** : token vivant, refresh OK
  (last update il y a 27 min)
- **5 boîtes Gmail** : tokens présents (mais polling inactif)
- **Odoo polling** : fonctionne, 62 200 records indexés, polling 
  toutes les 2 min
- **Webhook queue worker** : actif, traite les records Odoo
- **Scheduler principal** : actif (heartbeat -1 min)
- **Connection assignments** : tous les assignements existent et
  sont enabled
- **Tokens crypto** : le système de chiffrement/déchiffrement 
  fonctionne (les Gmail SCI ont des tokens lisibles)

---

## 📋 Plan de réparation recommandé (Phases 2 à 5)

### Phase 2 — Réparations urgentes (3-5h)

**Priorité 1 — Webhook Microsoft 500**
- Instrumenter le handler avec try/except large + traceback complet
- Déployer
- Attendre la prochaine notification, lire la VRAIE stack trace
- Fixer la cause identifiée
- Lancer /learn-inbox-mails pour récupérer les ~17 jours de mails
  perdus côté Outlook

**Priorité 2 — Polling Gmail**
- Poser `SCHEDULER_GMAIL_ENABLED=true` sur Railway
- Observer les logs : le job se déclenche-t-il ?
- Si oui, attendre 3-6 min et vérifier que des mails arrivent en
  base
- Si non, debugger l'enregistrement du job

**Priorité 3 — Heartbeats figés**
- Lire les logs de démarrage Railway pour voir si les jobs sont
  bien enregistrés
- Vérifier que les jobs posent leur heartbeat à chaque exécution
- Identifier la régression (pattern heartbeat manquant ?)

**Priorité 4 — Connexion fantôme ID=2**
- La marquer comme `not_configured` ou la supprimer
- Décision Guillaume : conserver l'historique ou nettoyer ?

### Phase 3 — Système de monitoring unifié (1-2j)

**Nouvelle table `connection_health_events`** :
```sql
CREATE TABLE connection_health_events (
  id SERIAL PRIMARY KEY,
  connection_id INTEGER REFERENCES tenant_connections(id),
  event_type TEXT NOT NULL,  -- 'poll_attempt', 'poll_success',
                              -- 'poll_error', 'webhook_received',
                              -- 'webhook_processed', 'webhook_error',
                              -- 'token_refresh_ok', 'token_refresh_fail'
  records_count INTEGER DEFAULT 0,
  error_message TEXT,
  created_at TIMESTAMP DEFAULT NOW(),
  metadata JSONB DEFAULT '{}'
);
CREATE INDEX idx_che_conn_time ON connection_health_events 
  (connection_id, created_at DESC);
```

**Nouvelle table `connection_health` (état courant)** :
```sql
CREATE TABLE connection_health (
  connection_id INTEGER PRIMARY KEY REFERENCES tenant_connections(id),
  last_event_at TIMESTAMP,        -- dernier event reçu (mail/file)
  last_check_at TIMESTAMP,        -- dernière vérification réussie
  expected_throughput_per_day REAL, -- débit attendu (calibré sur 7j)
  current_status TEXT,             -- 'healthy', 'silent', 'broken'
  status_since TIMESTAMP,
  last_error TEXT,
  last_error_at TIMESTAMP
);
```

**Job `connection_health_monitor` toutes les 15 min** :
- Pour chaque connexion active, vérifie la fraîcheur
- Compare au débit attendu (calculé sur 7 jours glissants)
- Marque "silent" si > 6h sans event ET débit attendu > 0.5/h
- Marque "broken" si erreur récurrente du connecteur (3+ erreurs)

**Page `/admin/health` (super_admin) ou `/tenant/panel#health`** :
- Vue couleur : 🟢 OK / 🟡 Anormal / 🔴 Cassé
- Pour chaque connexion : nom + email + dernier event + nb 
  events 24h + statut
- Bouton "Reconnecter" si nécessaire
- Bouton "Forcer un poll" pour tester
- Refresh auto toutes les 30s

### Phase 4 — Alertes proactives (1j)

**Règles d'alerte configurables** :
- Connexion silencieuse > 6h ET débit attendu > 0
- Token expiré ou révoqué (alerte immédiate)
- Webhook qui plante > 3 fois consécutives
- Polling en retard > 30 min sur cycle prévu

**Canaux d'alerte (super_admin et tenant_admin)** :
- Email immédiat
- Notification dans /chat (bandeau persistant rouge)
- SMS / WhatsApp via Twilio (anomalies critiques uniquement)
- (futur) Teams via webhook entrant

**Anti-spam d'alertes** :
- Une alerte par anomalie, pas une toutes les 15 min
- Auto-resolve quand l'anomalie disparaît
- Récap quotidien des alertes ouvertes

### Phase 5 — Tests & validation (½ j)

- Tests manuels : couper une connexion, vérifier l'alerte < 30 min
- Documentation pour Charlotte (juillet) et futurs clients
- Doc des règles : qu'est-ce qui déclenche quoi, qui est alerté

---

## 🎯 Décisions Guillaume à prendre avant Phase 2

**D1 — Niveau d'alertes ciblé**
🅐 Pro : alertes < 30 min, multi-canaux (email + chat + SMS critiques)
🅑 Bon : alertes < 2h par email seul, dashboard simple

**D2 — Connexion fantôme ID=2**
🅐 La supprimer définitivement
🅑 La marquer not_configured et garder pour historique

**D3 — Doublon gmail_tokens legacy**
🅐 Migrer définitivement et supprimer la table legacy
🅑 Garder en lecture seule pour compat ascendante

**D4 — Variables SCHEDULER_*_ENABLED**
🅐 Toutes les passer à default=True dans le code et retirer les
   variables Railway optionnelles
🅑 Toutes les expliciter sur Railway pour que ce soit visible

**D5 — Modèle de credentials unique**
🅐 Migrer Drive/Odoo dans tenant_connections.credentials (uniformité)
🅑 Garder en variables Railway (simplicité de déploiement)

---

*Audit Phase 1 terminé le 1er mai 2026. Prêt à attaquer Phase 2 
sur validation de Guillaume.*
