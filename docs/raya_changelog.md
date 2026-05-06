# Raya — Changelog

*Archive des modifications par session. Mis à jour par Opus à chaque jalon.*

---

## Session 06/05/2026 matin (8h-12h) — Refonte UI connexions + polling adaptatif jour/nuit + tool refresh pour Raya

**Theme** : suite de la nuit (bootstrap historique des 7 boîtes mail terminé avec 7 boîtes done). Le matin a 3 axes principaux : 1) résoudre les fix bloquants identifiés hier soir (Drive read fail, alertes spam SMS), 2) refonte complète UI connexions avec source de vérité unique `effective_status`, 3) polling adaptatif intelligent (jour/nuit + user actif + tool exposé à Raya).

**Bilan** : 11 commits poussés en 4h, 0 erreur prod, 9/9 connexions saines à l'arrivée. Voir `docs/audit_connexions_fraicheur_06mai.md` pour l'analyse globale fraîcheur/stabilité réalisée à la fin de session.

### Commits poussés (chronologique)

| Commit | Description |
|---|---|
| `2cff74a` | fix(drive) read_drive_file table drive_files → drive_semantic_content |
| `4888f28` | revert 0e7bceb (descriptions tools alourdies = +290 tokens/appel inutiles) |
| `a642818` | fix(drive) auto-fallback level=1 → level=2 dans `_execute_read_drive_file` (Excel files) |
| `d643a49` | fix(alerts) UPSERT acknowledged ne se remet plus FALSE à chaque cycle 60sec |
| `ae5168d` | fix(alerts) cooldown 4h sur SMS/WhatsApp/Email pour éviter spam (65 SMS en 7h !) |
| `973b97d` | feat(admin) endpoint /admin/health/connection/{id}/poll : test live de la connexion |
| `4d96286` | **feat(connection-health) etape 3** : `effective_status` calculé depuis connection_health (vraie santé) |
| `20134d6` | feat(admin-ui) etape 4 : page séparée `/admin/connexions` avec badges (conservée mais cachée) |
| `9f1da7b` | feat(admin-companies) etape 4bis : badge sur l'onglet Sociétés + retire bouton header |
| `c7a6730` | **feat(polling) etape 5** : adaptatif jour ouvré 5min / nuit+weekend 30min (-57% charge nuit) |
| `d12b74a` | **feat(polling) etape 6** : smart adaptive (user actif aria_memory) + tool `refresh_connections` exposé à Raya |

### 1. Drive read_drive_file table+level fallback (commits `2cff74a`, `a642818`)

**Symptôme** : Raya ne pouvait plus lire le contenu des fichiers SharePoint. L'extraction renvoyait soit du vide soit des métadonnées sans contenu.

**Cause #1** : `_execute_read_drive_file` cherchait dans la table `drive_files` qui n'existe plus depuis la refonte de fin avril. Le bon nom est `drive_semantic_content`.

**Cause #2** : pour les fichiers Excel/Sheets, le contenu est splitté en 2 chunks RAG : `level=1` (522 chars de métadonnées : nom, dossier, sheet names) et `level=2` (jusqu'à 7548 chars de contenu réel). Le code ne récupérait que level=1 → métadonnées sans contenu réel.

**Fix** : 1) corriger le nom de table, 2) si level=1 trouvé mais contenu trop court, retry avec level=2 automatiquement.

**Test validé** : Raya peut maintenant lire le fichier "S21 SOCOTEC.xlsx" et retourner le détail des onglets.

### 2. Spam SMS Twilio + bouton Acquitter cassé (commits `d643a49`, `ae5168d`)

**Symptômes** :
- 65 SMS + 65 WhatsApp envoyés en 7h pour la même alerte (boîte contact@ en panne dans la nuit)
- L'admin clique "Acquitter" sur une alerte → 60 sec plus tard l'alerte se ré-ouvre toute seule

**Cause acknowledged** : la fonction `_persist_alert` faisait un UPSERT qui forçait `acknowledged = FALSE` à chaque cycle. Donc dès que l'admin acquittait, le prochain tick la rouvrait.

**Cause spam SMS** : la fonction `_send_on_channel` n'avait aucune dédup. Le job d'alertes tournant toutes les 60sec, dès qu'une alerte critique était active, on envoyait 1 SMS toutes les 60sec.

**Fix acknowledged** : UPSERT avec CASE qui ne remet `acknowledged=FALSE` QUE si on passe de warning à critical (escalade légitime). Sinon on garde la valeur précédente.

**Fix spam** : nouvelle constante `EXTERNAL_COOLDOWN_HOURS = 4` + 2 fonctions `_should_skip_external_send` / `_record_external_sent` qui stockent `last_external_sent_at` dans `system_alerts.details::jsonb`. Effet : 1 seul SMS par alerte par 4h, mais le badge in-app reste à jour en continu.

### 3. Refonte UI connexions — source de vérité unique (commits `4d96286`, `20134d6`, `9f1da7b`)

**Problème de fond** : 3 sources de "vérité" qui se contredisaient :
- Bandeau alerte rouge en haut de l'onglet Sociétés (lit `system_alerts`)
- Pastille verte ✅ "connecté" sur chaque carte de connexion (lit `tenant_connections.status`)
- Le polling delta_sync qui plante depuis 8h (vérité métier, mais invisible)

Résultat : Guillaume voyait simultanément "Couffrant Solar a une alerte rouge" en haut et "9/9 connexions vertes" en bas. La pastille mentait.

**Solution étape 3** (commit `4d96286`) : nouveau module `app.connection_health` avec :
- `get_effective_connection_status(connection_id)` : retourne `{state: green/amber/red/unknown, reason: "OK il y a 3 min", minutes_since_ok, consecutive_failures, ...}`
- `get_effective_status_for_tenant(tenant_id)` : version bulk pour toutes les connexions d'un tenant en 1 query SQL
- Seuils relatifs : `GREEN_FACTOR=1.5x` interval, `RED_FACTOR=3x`, `RED_FAILURES_THRESHOLD=3` consécutifs

**Étape 4** (commit `20134d6`) : modifie la page `/admin/connexions` (page séparée découverte par Guillaume ce matin) pour utiliser ces nouveaux badges. Mais Guillaume a explicitement dit qu'il ne voulait pas de cette page → on laisse mais on cache l'accès.

**Étape 4bis** (commit `9f1da7b`) : LA vraie cible. Modifie l'onglet **Sociétés** du panel principal :
- Backend : `app/connections.py:list_connections()` enrichit chaque connexion avec `effective_status`
- Frontend : `admin-panel.js:loadConnections()` ajoute un badge 🟢/🟡/🔴/⚪ "OK / Attention / Panne / Inconnu" à côté du badge OAuth original (qu'on conserve)
- Pastille de résumé en haut de chaque carte tenant : compte les saines via `effective_status.state` au lieu de `status==='connected'`
- Header : retire le bouton "🔌 Connexions" pour ne plus avoir 2 endroits où chercher l'info

Test live à 11h51 : 9/9 badges 🟢 OK pour Couffrant Solar (la conn=14 contact@ s'est rétablie spontanément après le refresh OAuth de la nuit pendant le bootstrap).

### 4. Polling adaptatif jour/nuit (commit `c7a6730` — étape 5)

**Constat** : 9 connexions × 1 poll par 5 min = 2592 polls/jour, dont la moitié la nuit où personne ne bosse. Charge inutile sur Railway et sur les APIs Microsoft Graph + Gmail.

**Solution** : nouveau module `app/polling_schedule.py` avec 3 fonctions clés :
- `is_business_hours(now)` : True si lundi-vendredi 7h30-18h30 heure de Paris (zoneinfo Europe/Paris)
- `get_expected_poll_interval(now)` : retourne 300s en heures ouvrées, 1800s sinon
- `should_skip_poll_now(connection_id, now)` : True si on doit skipper ce cycle (= hors heures + dernier poll < 30 min)

Architecture : on **NE TOUCHE PAS au scheduler APScheduler** (toujours IntervalTrigger 5 min). Les **jobs eux-mêmes** appellent `should_skip_poll_now` au début de leur boucle sur chaque connexion. Avantages : reversible, granulaire, 0 risque scheduler.

4 jobs modifiés avec le pattern uniforme :
- `mail_outlook_delta_sync.py:run_outlook_delta_sync`
- `mail_gmail_history_sync.py:run_gmail_history_sync`
- `drive_delta_sync.py:run_drive_delta_sync`
- `odoo_polling.py:run_odoo_polling`

Bonus : `connection_health._compute_effective_status` utilise désormais `get_expected_poll_interval()` à la volée → les seuils green/amber/red s'adaptent automatiquement à l'heure (la nuit, un silence de 45 min n'est plus une "panne" car c'est juste 1.5× l'intervalle attendu).

### 5. Smart adaptive : user actif + tool refresh pour Raya (commit `d12b74a` — étape 6)

**Trous restants après étape 5** : 1) Guillaume bosse parfois jusqu'à 22h → il rate les mails arrivés à 21h45 pendant 30 min, 2) Raya répond avec des données qui peuvent avoir 28 min de retard.

**Niveau 2 — détection user actif** : `should_skip_poll_now` est étendu pour checker `aria_memory.created_at` du tenant. Si quelqu'un a discuté avec Raya dans les 15 dernières min → bypass du skip → mode 5 min réactivé sur tout le tenant. Transparent pour Guillaume.

**Niveau 3 — tool `refresh_connections` exposé à Raya** : approche sémantique élégante au lieu d'une regex de mots-clés fragile. Description du tool dit clairement à Raya : "à utiliser quand l'user a clairement besoin d'info fraîche (récence, urgence, 'y a-t-il quelque chose de nouveau ?'). NE PAS appeler pour les questions historiques ou théoriques. Coût ~1-3 sec." Raya décide elle-même.

Implémentation executor : `_execute_refresh_connections` appelle synchrone les 4 jobs `run_outlook_delta_sync`, `run_gmail_history_sync`, `run_drive_delta_sync`, `run_odoo_polling`, mesure le delta de mails ingérés, retourne `{status, duration_ms, reason, connections_refreshed, new_mails_seen, jobs_run, partial_errors}`.

### 6. Audit fraîcheur/stabilité connexions (doc créée fin de session)

À la demande de Guillaume après les push : audit complet pour vérifier qu'on ne crée pas de redondance avec les webhooks qu'il pensait avoir mis en place. Voir doc dédiée `docs/audit_connexions_fraicheur_06mai.md`.

**Constat principal** : 1 webhook Microsoft actif sur 9 connexions (conn=6 Inbox seulement, expire 7/05 5h35), 0 watch Gmail Pub/Sub (job désactivé en prod via env var). Le polling reste donc la voie principale d'ingestion pour 8/9 connexions. Aucune redondance avec étapes 5+6.

Recommandations dans le doc : étendre la sub Microsoft conn=6 aux 3 dossiers (Inbox+SentItems+JunkEmail) en 30 min de code, reconnecter conn=14 en OAuth complet pour avoir un webhook dessus, possiblement activer Gmail Pub/Sub (ROI marginal).

### TODOs reportés

- Tester en prod après 18h30 ce soir : passage automatique en mode 30 min puis bascule 5 min si Guillaume écrit à Raya
- Tester demain matin 7h30 : retour automatique en mode 5 min
- 74 erreurs SENT folder per1.guillaume@gmail.com lors bootstrap nuit (~12% taux erreur, à investiguer)
- contact@ : 2550 mails / ~9961 attendus → relancer bootstrap avec months_back=24 si Guillaume veut historique complet
- Évaluer reconnexion OAuth complète conn=14 pour avoir webhook
- Considérer extension sub Microsoft conn=6 aux 3 dossiers

---

## Session 05/05/2026 après-midi (13h-19h) — Mur permissions de bout en bout + V2 par-connexion + chantier apprentissage hiérarchisé lancé

**Theme** : suite directe du matin. On termine la chaine V2 par-connexion (inventaire + recon + assignment auto). On corrige le mur permissions qui ne fonctionnait pas du tout depuis son deploiement (`permission_audit_log` totalement vide). On ajoute une page d audit lisible. Test final reussi : Raya tente delete_mail sur contact@ en lecture seule -> mur intercepte -> Raya explique a Guillaume. La derniere heure ouvre un nouveau chantier de fond : reflexion sur la hierarchisation des apprentissages (ex : la regle 124 obsolete a trompe Raya).

### Commits poussés (chronologique)

| Commit | Description |
|---|---|
| `32a660c` | ❌ feat(admin-ui): dropdown permissions modifiable pour super_admin — REVERTED (panneaux deja existants) |
| `6f4c15e` | Revert `32a660c` |
| `b1065ea` | **fix(perms) CRITIQUE** : aligne mur permissions et execution sur l id technique mail_memory |
| `a43f904` | feat(admin-ui): page diagnostique permissions `/admin/permissions/audit-page` |
| `46d4cf3` | fix(outlook): inventaire + recon nocturne utilisent token V2 par-connexion |
| `19654c1` | fix(oauth): cree automatiquement l assignment apres callback OAuth (Microsoft + Gmail) |

### 1. Mur permissions ne fonctionnait pas du tout (commit `b1065ea`)

**Symptome** : `permission_audit_log` totalement VIDE depuis le deploiement de la securite (04/05 soir). Aucune trace ni d allow ni de deny.

**Cause racine** : le commit `3056fe7` du matin a expose les `mail_id` techniques (entiers) de `mail_memory` a Raya. Mais `_resolve_connection_id_for_tool` cherchait toujours par `message_id` Microsoft Graph. Quand Raya appelait `delete_mail(mail_id=1349)`, la fonction ne trouvait rien -> retournait `current_level='unknown'` -> refusait TOUT delete_mail. Et en parallele, l execution dans `confirmations.py:DELETE` passait l id technique direct a `perform_outlook_action` qui aurait plante avec une 404 Microsoft Graph.

**Fix** : 2 tentatives de lookup successives (`WHERE id=int(mail_id)` puis `WHERE message_id=mail_id`) + nouvelle fonction `_resolve_real_message_id` dans `confirmations.py` pour DELETE/ARCHIVE qui resout l id technique vers le vrai message_id Microsoft Graph avant d appeler `outlook_actions`.

**Tests valides** : mail_id=1349 + boite read_write_delete -> ALLOWED. Meme mail_id + boite forcee read -> DENIED. Garbage halluciné (`fake_mail_id_xyz`) -> DENIED.

**Note** : les pending_actions historiques contenaient des `mail_id` hallucines par Raya (format `"hello@studeria.fr_2026-03-29T08:32:51Z"` = expediteur + date ISO). Avant `3056fe7` du matin, Raya inventait ces IDs car n avait pas le vrai. L execution echouait silencieusement -> AUCUN delete_mail n a jamais reussi avant aujourd hui.

### 2. Inventaire + recon Outlook V2 par-connexion (commit `46d4cf3`)

**Symptome** : avec 2 boites Outlook, l inventaire boite mail (`/admin/mail/inventory/{conn_id}`) affichait EXACTEMENT les memes chiffres pour les 2 boites (1436 mails, Inbox 605, SentItems 446...). Les chiffres etaient ceux de guillaume@ pour les 2.

**Cause racine** : 2 fichiers utilisaient encore le legacy V1 `get_valid_microsoft_token(username)` (table `oauth_tokens` : 1 token par user/provider) :
- `app/routes/admin/admin_mail.py:admin_mail_inventory`
- `app/jobs/mail_outlook_reconciliation.py:_reconcile_connection`

Avec 2 boites Outlook, le legacy retournait toujours le token de la derniere connectee = guillaume@. Donc l API Microsoft Graph retournait l inbox de guillaume@ pour les 2 connexions.

**Fix** : aligne sur le pattern du commit matin `8eb31ab` : iterer sur `get_all_user_connections(username)`, matcher sur `connection_id`, prendre le token V2 par-connexion.

**Validation post-deploy** : inventaire de contact@ affiche maintenant 9961 mails (Inbox 3801, SentItems 2874, JunkEmail 88, Archive 1544, DeletedItems 1654) vs guillaume@ 1436 mails. Les 2 boites accedent enfin a leurs vraies donnees.

**Restent 4 fichiers V2 a migrer** (chantier propre, non urgent) : `email_signature.py`, `external_observer.py`, `drive_delta_sync.py`, `drive_reconciliation.py`. Pour Couffrant pas observable (1 seul site SharePoint), mais bug latent pour multi-tenants.

### 3. Création auto de l assignment au callback OAuth (commit `19654c1`)

**Bug racine** : quand un super_admin connectait une nouvelle boite via `/admin/connections/{tenant}/oauth/{tool}/start`, la connexion etait creee dans `tenant_connections` avec son token, MAIS aucune ligne n etait inseree dans `connection_assignments`.

Consequence : `get_all_user_connections()` filtre par `WHERE ca.enabled=true`, donc la nouvelle connexion etait INVISIBLE pour tous les jobs V2 (bootstrap, delta-sync, inventaire, reconciliation).

**Bug observe** : la reconnexion de contact@ a 15:07 a cree conn#14 avec le bon token, mais le bouton "Inventaire" ne reagissait pas car `get_all_user_connections` ne retournait pas la connexion. Workaround : INSERT manuel de l assignment en SQL.

**Fix** : nouvelle fonction `_ensure_assignment_for_admin(conn_id, request)` dans `app/routes/admin_oauth.py`, appelee depuis les 2 callbacks (Microsoft et Gmail). Recupere `username` depuis la session, recupere `tenant_id` de la connexion, INSERT avec `ON CONFLICT DO UPDATE SET enabled=true` (idempotent). Niveau par defaut `read_only` (le super_admin peut ensuite l elever via le panel).

A partir de maintenant, toute nouvelle reconnexion OAuth (Outlook ou Gmail) est automatiquement visible sans intervention manuelle.

### 4. Page diagnostique permissions (commit `a43f904`)

Apres le fix b1065ea, on avait besoin d un moyen de verifier visuellement que le mur fonctionne sans toucher SQL.

**Nouvelle page** : `/admin/permissions/audit-page` (accessible super_admin + admin Raya, lecture seule).

- Section 1 : permissions actuelles par connexion (toutes tenants), niveau plafond super_admin et niveau tenant_admin. Codes couleur : bleu = read, orange = read_write, rouge = read_write_delete.
- Section 2 : 50 dernieres tentatives d action (DELETE_MAIL, ARCHIVE_MAIL, etc.) avec date, user, tenant, connexion ciblee, niveau effectif, niveau requis, verdict (autorise vert / refuse rouge). Fond vert si autorise, rouge si refuse.
- Stats en haut : nb connexions configurees, nb actions autorisees / refusees, total tentatives.

### 5. Test bout-en-bout du mur permissions

**Avant test** : reglage de la regle obsolete id=124 (qui disait "boite contact@ a connecter prochainement") -> texte mis a jour pour refleter "connectee depuis le 05/05/2026, 9961 mails cote Microsoft".

**Test** : Guillaume demande a Raya dans une nouvelle conversation : *"Peux-tu mettre dans la corbeille le dernier mail recu sur la boite contact"*.

**Resultat** : Raya repond *"Je peux lire la boite contact@couffrant-solar.fr mais pas y effectuer de suppressions — elle est configuree en mode 'Lire seul'. Pour que je puisse supprimer des mails dessus, il faut passer la connexion au niveau 'Tout faire'."*

**Trace dans permission_audit_log** : `2026-05-05 16:42:12 guillaume DELETE_MAIL conn=14 curr=read req=read_write_delete REFUSE — excerpt: "Mettre a la corbeille mail 3632"`.

Donc Raya a bien tente `delete_mail(mail_id=3632)`, le mur a intercepte en amont et refuse, Raya a reformule la reponse pour Guillaume en mode propre. Aboutissement de la chaine de securite mise en place 04/05 soir + 05/05.

### 6. Chantier de fond identifié — Hiérarchisation des apprentissages (à attaquer maintenant)

**Probleme observe** : la regle 124 (creee le 17/04 disant "boite contact@ a connecter prochainement") a trompe Raya. Bien que la liste vivante `connected_mailboxes` injectee dans son contexte affichait correctement contact@ comme connectee, Raya a fait confiance a la regle 124 plutot qu a la donnee vivante.

**Diagnostic** : le systeme actuel `aria_rules` traite tous les apprentissages de la meme maniere :
- **Toutes** les 200+ regles actives sont au niveau "moyenne" (champ `level` existe mais inutilise)
- Pas de distinction entre fait stable, etat temporel, comportement, culture metier
- Pas de notion d expiration ou de revalidation
- Pas de hierarchie de priorisation entre donnee vivante et regle apprise

**Vision Guillaume** : Raya doit apprendre comme un humain le ferait, avec :
- Priorisation d importance entre sources (donnee vivante > declaration recente > observation > regle ancienne)
- Categorisation entre regle, info generale, info passagere, culture generale, connaissance utilisateur
- Reflex de re-verification quand une info est temporelle et ancienne
- Auto-vérification autonome (Raya verifie elle-meme avant d affirmer ; ne demande a l user qu en dernier recours)

**Architecture proposee** : voir `docs/projet_apprentissage_hierarchise.md` (a creer).

S inscrit dans le systeme existant (`docs/architecture_memoire_regles_v2_final.md`) qui a deja un job nocturne `rules_optimizer`, decroissance par non-usage, anti-doublons, contradictions via LLM. La dimension manquante est **la nature de l info** (durable vs perissable).

---

## Session 05/05/2026 matin (8h-12h) — Audit OAuth + filtre bulk + alertes + UX backend

**Theme** : marathon de 4h qui a corrige des bugs en chaine. Demarre par "le bootstrap contact@ ne ramene que 111 mails sur 1418", revele un probleme architectural sur les tokens Outlook. En auditant on a aussi trouve un filtre bulk catastrophique qui jetait factures/commandes/livraisons. Termine par les chantiers prioritaires de la TODO (UX 1.2 backend, expose mail_id).

### Commits poussés (chronologique)

| Commit | Description |
|---|---|
| `ed68f77` | feat(diag): endpoints `/admin/mail/diag/token-identity/{id}` et `/all-token-identities` lecture seule |
| `8eb31ab` | fix(outlook): bootstrap + delta-sync utilisent token V2 par-connexion via `get_connection_token(email_hint=mailbox_email)` |
| `32b5ae8` | docs : script SQL nettoyage + procedure reconnexion contact@ |
| `ed71b50` | feat(diag-ui): page HTML lisible `/admin/mail/diag/identities-page` (pas de console JS) |
| `ace46b7` | docs : prompt reprise 05mai apresmidi + changelog mis a jour |
| `0ff1b97` | **fix(filter) CRITIQUE** : retire keywords business (factures, commandes, livraisons, alertes) du filtre bulk |
| `94d3ab7` | fix(alerts): refonte severite 3 niveaux (info/warning/critical) pour webhook+odoo+gmail recon |
| `53272ad` | fix(gmail-recon): comptage pommes vs pommes (exclusion SPAM + ajout filtres Haiku) |
| `3056fe7` | feat(raya): expose `mail_id` et autres IDs techniques dans search_mail |
| `a60d31b` | fix(ux): pre-cree aria_memory au debut de la requete (UX 1.2 backend) |

### 1. Diagnostic OAuth tokens (commits `ed68f77`, `8eb31ab`, `ed71b50`, `32b5ae8`)

**Cause racine** : bootstrap utilisait `get_valid_microsoft_token(username)` (table legacy `oauth_tokens` : 1 token par user/provider). Avec 2 boites Outlook, elles utilisaient le MEME token (le dernier OAuth = guillaume@). Donc bootstrap de contact@ recuperait l inbox de guillaume@.

Le systeme V2 (token par-connexion via `tenant_connections.credentials`) existait deja mais n etait branche que sur Gmail. Outlook continuait sur le legacy.

**Fix** : `get_connection_token(username, real_tool_type, email_hint=mailbox_email)` dans `mail_bootstrap.py` et `mail_outlook_delta_sync.py`. Lookup du `tool_type` reel en base (`microsoft` vs `outlook` historique).

**Diagnostic UI** : page `/admin/mail/diag/identities-page` qui appelle `/me` Microsoft Graph et `/profile` Gmail avec chaque token et compare avec `connected_email`. Resultat sur Couffrant Solar : 7 connexions OK, conn 12 (contact@) en erreur token expire (28/04, jamais utilise par le legacy).

**Nettoyage donnees** : 111 mails reetiquetes `contact@` -> `guillaume@`. Connexion 12 supprimee par Guillaume (probleme Microsoft Authenticator empechait la reconnexion immediate).

### 2. Fix CRITIQUE filtre bulk (commit `0ff1b97`)

En auditant les filtres lors de l incident "1978 mails manquants", decouverte d un bug catastrophique. Le filtre `_is_bulk_heuristic` de `webhook_microsoft.py` jetait silencieusement TOUT mail dont :
- prefixe expediteur `alerts@`, `automated@`, `system@`, `notifications@` -> bloquait alertes critiques (Cloudflare, AWS, monitoring SAV)
- mot-cle sujet `facture n°`, `invoice #` -> bloquait factures clients/fournisseurs
- mot-cle sujet `votre commande`, `confirmation de commande`, `order confirmation` -> bloquait confirmations
- mot-cle sujet `tracking`, `livraison` -> bloquait livraisons (chantiers, internes Arlene)

**Test empirique** : sur 14 cas business reels d un dirigeant Couffrant Solar (panneaux solaires), 9 etaient JETES a tort. Estime que sur les 941 mails filtres du bootstrap per1.guillaume@gmail.com, une grande partie etaient des factures Stripe et confirmations legitimes.

**Fix** : `_BULK_SUBJECT_KEYWORDS` reduit aux vrais signaux newsletter (unsubscribe, newsletter, digest, weekly recap, do not reply, automated message, verification code, one-time password). `_NOREPLY_PREFIXES` reduit aux 100%-srs (noreply@, mailer-daemon@, bounce@, newsletter@).

**Verification post-fix** : memes 14 cas, 0 faux positif. Les 3 vraies newsletters (Enedis, LinkedIn, Medium digest) toujours filtrees.

### 3. Refonte alertes 3 niveaux (commit `94d3ab7`)

Demande Guillaume : "rouge/orange = vraies alertes graves. Vert = simple notification informative. Qu on essaye de ne plus avoir d alertes pas graves en orange et rouge."

**Reclassement seuils** :
- `webhook_night_patrol` : seuil >5 missing = warning -> seuil <=50 + autoreparation OK = info verte. Rouge si >=500 missing OU >=20% en echec.
- `odoo_reconciliation` : tout >1% = warning -> info <5% (auto-rattrape), warning 5-10%, critical >=10% OU >=100 records.
- `mail_gmail_reconciliation` : tout >1% = warning -> info <30% (filtrage Haiku legitime), warning 30-50%, critical >=50%.

**Reclassification immediate** des 2 alertes existantes en base :
- webhook_queue id=5202 (72 missing/72 rattrapes) : warning -> info
- odoo_recon id=69700 (2.7% ecart) : warning -> info
- gmail_recon id=75555 (47.8%) : reste warning, sera affine par commit suivant

### 4. Pommes vs pommes Gmail recon (commit `53272ad`)

L alerte Gmail comparait Google brut (INBOX+SENT+SPAM) vs Raya filtre (sans spam, sans newsletter) -> ecart artificiel important.

**Fix** :
- LABELS_TO_COUNT cote Google : retire SPAM (jamais bootstrape).
- count_raya cote Raya : ajoute `items_filtered_haiku` du DERNIER bootstrap par mailbox (DISTINCT ON pour eviter double-comptage).

**Resultat estime** : ancien delta 47.8% -> nouveau ~10% -> info verte au prochain run nocturne.

### 5. Expose mail_id a Raya (commit `3056fe7`)

Bug observe le 04/05 minuit : Raya repondait *"Je n ai pas l ID du mail necessaire pour le supprimer"*. La cause : `format_unified_results` n exposait pas l id technique de `mail_memory`.

**Fix** :
- `format_unified_results` ajoute `📌 [mail_id: 1234]` sous chaque resultat mail. Idem `[file_id: ...]`, `[conversation_id: ...]`, `[odoo_model: ... · odoo_id: ...]`.
- Description du tool `search_mail` actualisee : "chaque resultat affiche un identifiant technique 📌 [mail_id: N]. Cet identifiant est REQUIS pour appeler les tools read_mail, delete_mail, archive_mail, reply_to_mail."
- Description du tool `delete_mail` actualisee : "Le parametre mail_id provient OBLIGATOIREMENT d un search_mail prealable. Si tu n as pas l ID, lance d abord un search_mail."

### 6. UX 1.2 backend - pre-creation aria_memory (commit `a60d31b`)

Avant ce fix : `aria_memory` cree a la FIN de la boucle agentique. Les pending_actions inserees pendant les tool calls avaient donc `conversation_id=NULL` (82% des cas observes en base). Le frontend ne pouvait pas les rattacher au bon message Raya, fallback en bas du chat avec badge timestamp (commit `dd2c9c2` du 04/05).

**Fix** :
- Nouveau `_create_conversation_shell()` : INSERT aria_memory avec `aria_response=NULL`, retourne l ID.
- Nouveau `_update_conversation_response()` : UPDATE pour completer aria_response a la fin.
- `_raya_core_agent` appelle `_create_conversation_shell()` AVANT la boucle, passe l ID a `execute_tool()` comme `conversation_id`.
- `_save_conversation()` conserve pour fallback defensif.

**Effet** : toutes les nouvelles pending_actions auront conversation_id renseigne. Le badge timestamp du commit dd2c9c2 reste comme garde-fou.

### Lecons retenues

- **Privilegier les tests empiriques** : on a decouvert le bug filtre bulk en testant 14 cas business reels au lieu de relire le code abstraitement.
- **Audit avant fix** : Guillaume a explicitement demande "regarde si c est pas deja fait avant de toucher" -> a permis d eviter de defaire l UX 1.2 frontend qui etait deja en place.
- **Recheck des chantiers de la TODO d origine** : les 2 chantiers urgents identifies hier soir (mail_id + aria_memory) ont fini par etre faits dans la meme session que l audit OAuth, en surveillant qu on ne casse rien d autre.
- **2 systemes de tokens en parallele** = bug latent. Le legacy oauth_tokens devrait etre supprime dans une session future (chantier propre) pour eviter qu un futur job se branche dessus par erreur.

---

## Session 04/05/2026 soir + 05/05/2026 minuit — Marathon sécurité (6 commits + 1 revert + 1 reapply)

**Thème principal** : Audit complet du système de permissions, suppression des chemins d'exécution dangereux, mur physique branché sur les tools agentiques, UX pending actions, et début du chantier "débridage Raya".

**Déclencheur** : Guillaume a signalé un incident où ~100 mails ont disparu de contact@couffrant-solar.fr en 1 mois, et a demandé un audit du système de permissions par connexion. L'investigation a révélé que le système était CONÇU et CODÉ depuis le 18/04 mais BRANCHÉ NULLE PART sur le chemin d'exécution moderne (tools agentiques).

### Commits poussés en prod

- `a9a40e3` — feat(mail) : cœur fonctionnel suppression Gmail/Outlook + purge 30j
  - Détection messagesDeleted dans Gmail history + labelsAdded/Removed pour TRASH
  - Soft-delete des `@removed` Outlook au lieu de skip silencieux
  - Cron quotidien 03h15 `_job_purge_trashed_mails` qui passe les `trashed_at < NOW() - 30 days` en `deleted_at`
  - Effet : graphe et mail_memory restent fidèles à la source

- `9874d6a` — fix(sécurité) : suppression chemins B dangereux (DELETE/ARCHIVE/REPLY/CREATEEVENT direct)
  - Dans `mail_actions.py` : suppression des blocs qui exécutaient `perform_outlook_action` SANS confirmation quand `mail_can_delete=True`
  - Dans `tools_seed_data.py` : retrait des 4 entrées correspondantes
  - Dans `aria_context.py` : remplacement de l'instruction "Si l'utilisateur dit 'corbeille', génère [ACTION:DELETE]" par une directive d'utiliser les tools agentiques
  - Dans `prompt_actions.py` : retrait des mentions des 4 balises
  - Effet : toute action destructive doit OBLIGATOIREMENT passer par `pending_actions` + carte de confirmation

- `dd2c9c2` — fix(ux) : pending actions sans rattachement → badge timestamp clair
  - Bug remarqué par Guillaume : 14 cartes DELETE Studeria créées à 13:38 mais avec `conversation_id=NULL`. Quand Guillaume rouvrait le chat à 17:57, le frontend les affichait après le dernier message Raya, donnant l'illusion qu'elles venaient d'être créées par cette nouvelle question.
  - Fix : quand le rattachement par `conversation_id` échoue, ON N AJOUTE PLUS la carte après le dernier message Raya. À la place : `appendToChat` en bas avec un BADGE timestamp clair "Action en attente — créée le 04/05 à 13:38".
  - Risque : faible, modification frontend uniquement.
  - Limitation connue : 39/50 actions historiques ont `conversation_id=NULL` car les tools agentiques sont appelés AVANT que `aria_memory_id` soit créé. Sera fixé dans un commit backend séparé (UX 1.2) qui pré-créera `aria_memory` au début de la requête.

- `04a6fa3` puis revert `81e5f67` puis reapply `b7801eb` — feat(security) : MUR PHYSIQUE permissions sur tools agentiques + bug fix DELETE/ARCHIVE simples
  - Nouveau dans `permissions.py` : `check_permission_for_tool(tenant_id, username, tool_name, tool_input)` qui :
    1. Mappe `tool_name` → `action_tag` (delete_mail → DELETE_MAIL)
    2. Résout `connection_id` depuis `tool_input` :
       - tools mail (delete/archive/reply) : lookup `mail_memory` par `mail_id` → `mailbox_email` → `tenant_connections.id`
       - send_mail : utilise le `provider` (outlook/gmail) du payload
       - calendar/teams/drive : première connexion appropriée du tenant
    3. Récupère niveau effectif (cap entre `super_admin_permission_level` et `tenant_admin_permission_level`)
    4. Compare avec niveau requis via `level_satisfies()`
    5. Log dans `permission_audit_log`
    6. Retourne dict `{allowed, reason, details}` avec `current_level`, `required_level`, `remediation` que l'agent peut interpréter et relayer
  - Branchement #1 : dans `_execute_pending_action` (raya_tool_executors.py) AVANT la création de la pending_action. Si refus → retour JSON `permission_denied` à Raya avec détails. L'agent comprend, ne réessaie pas, explique à l'utilisateur.
  - Branchement #2 : dans `_execute_confirmed_action` (confirmations.py) AVANT l'exécution réelle (défense en profondeur). Si l'admin a modifié le niveau entre la création de la carte et le clic Confirmer, la nouvelle politique s'applique.
  - Bug fix bonus : `_execute_confirmed_action` ne gérait pas `action_type='DELETE'` ni `'ARCHIVE'` simples (seulement `DELETE_GROUPED`). C'est ce qui produisait *"Type d'action inconnu : DELETE"* dans le chat de Guillaume au clic Confirmer. Handlers ajoutés.
  - Incident Railway 502 (~23h) : après push, l'app a passé en 502. Diagnostic : `init_postgres()` prend 29.5s en local (260 commandes SQL de migration rejouées à chaque démarrage). Sur Railway, timeout dépassé pendant que la DB était lente. Cause finale = Railway lui-même après 5 push en 2h, pas le code. Revert puis re-push après stabilisation.

### Modifications en base

- **3 règles `aria_rules` désactivées** (id 71, 76, 187) : "DELETE = action directe sans confirmation". Plus actives, n'influencent plus le contexte Raya.
- **Permissions ajustées sur les 9 connexions Couffrant Solar** :
  - 6 boîtes mail perso/SCI (per1.guillaume, guillaume@couffrant-solar.fr, GPLH, Romagui, Gaucherie, MTBR) → `read_write_delete`
  - contact@couffrant-solar.fr, SharePoint Commun, Odoo Openfire → `read`

### Découvertes importantes

1. **Le système permissions était inerte** depuis sa création le 18/04 : la table `permission_audit_log` était totalement vide. Le check n'était appelé que dans 5 endroits anciens (SEND_MAIL via balise + 4 dans Odoo). Le chemin moderne (tools agentiques) ne le vérifiait jamais.

2. **Bug `_tool_type_for_action`** : pour SEND_MAIL il renvoyait `'mailbox'` mais `tenant_connections.tool_type` contient `'gmail'`/`'microsoft'`/`'outlook'`. Donc la lookup retournait toujours `None` → permission jamais bloquée.

3. **Bootstrap contact@ jamais fait** : seulement 1 mail en `mail_memory` pour cette boîte (envoyé par Guillaume à 15:08 le 04/05, capturé par delta-sync). L'incident "100 mails disparus" est donc presque certainement une règle Outlook côté serveur, pas Raya. Mais sans bootstrap, on ne peut pas le vérifier en relisant les anciens mails.

4. **Vision "débridage Raya" validée par Guillaume** : Raya bute sur des choses simples parce qu'elle n'a pas accès à la DB ni au code, contrairement à Claude qui aide Guillaume. Solution : donner à Raya des tools de lecture seule sur la DB et le code, encourager le doute légitime, améliorer les retours d'erreur. Chantier à attaquer dans une prochaine session.

### Leçons retenues

- **Privilégier Desktop Commander sur `postgres:query`** : `postgres:query` est instable, plante souvent. DC + `python3 + psycopg2` est plus fiable.
- **Étapes courtes** : longues bloquent le MCP. Découper.
- **Espacer les push sur Railway** : 5 push en 2h = startup en boucle, 502 perpétuel.
- **Garder un revert prêt** en cas de doute sur Railway.
- **Désactiver les règles `aria_rules` contradictoires** quand on supprime le code qui les sous-tend, sinon l'agent garde la croyance même si le code ne le permet plus.

---


## Session 17/04/2026 soir (22h-23h) — Mermaid : schémas graphiques SVG

**Objectif** : remplacer l'art ASCII illisible par de vrais schémas
rendus graphiquement (organigrammes, flux, hiérarchies, timelines).

**Approche validée avec Guillaume** : minimaliste côté prompt (~20 tokens),
robuste côté frontend. Pas de template imposé — l'utilisateur personnalise
par feedback et Raya apprend via `aria_rules`.

**4 commits successifs de mise en place puis debug** :

- `5b17771` — Ajout Mermaid.js 11.4.0 via CDN + init + `renderMermaidBlocks`
  + règle minimaliste dans `aria_context.py` + CSS `.mermaid-wrapper`
- `3a3bfd1` — Ajout `normalizeMermaidSyntax` (backticks simples → triple)
  + `tagMermaidCodeBlocks` (détection heuristique des code blocks sans tag)
- `67b5841` — Enrichissement `normalizeMermaidSyntax` pour gérer le cas
  où Raya ferme avec un `` ` `` simple + ajout `mermaid.parse()` avant
  `mermaid.render()` pour valider la syntaxe et éviter les SVG-bombes
  que Mermaid 11.x affiche au lieu de thrower
- `256bd49` — **Fix du vrai bug** : race condition DOM. `renderMermaidBlocks`
  était appelé en async fire-and-forget AVANT les `innerHTML = innerHTML.replace`
  qui réécrivaient le DOM. Le `<pre>` référencé devenait orphelin →
  `replaceChild` échouait silencieusement → rendu Mermaid fonctionnait
  mais écrivait dans le vide. Déplacement de l'appel à la FIN de `finalize()`.

**Cache-bust** : v=74 → v=78 (4 bumps successifs).

**Leçon** : Guillaume a insisté pour que je diagnostique via le texte
brut de la DB plutôt que de patcher à l'aveugle. Sans sa directive,
j'aurais continué à ajouter des regex au lieu de regarder l'ordre
d'exécution. Bon réflexe à retenir : quand « tout marche mais rien ne
s'affiche », scruter l'ordre d'exécution DOM avant de supposer un
problème de parsing.

**Résultat** : 3 schémas successifs de test (organigramme patrimonial,
version avec couleurs pastel sur demande) rendus correctement au
rechargement de page.

### Nouveau chantier identifié (🟡 priorité moyenne, après capabilities)

**Analyse complète des outils visuels/interactifs à intégrer.**

Mermaid a ouvert un nouveau registre pour Raya (visuel, pas seulement
textuel). Question ouverte : quels autres outils pourraient être ajoutés ?
Pistes : Chart.js/Plotly (graphiques de données), KaTeX (formules
financières), Excalidraw (croquis whiteboard), Leaflet/Mapbox (cartes
chantiers), timelines interactifs, tableaux triables/filtrables, code
sandbox, widgets formulaires.

Détails dans `raya_session_state.md` section « NOUVEAU CHANTIER À OUVRIR ».

---

## Session 17/04/2026 soir — Chat solide + Auto-découverte élargie + Architecture capabilities

### Fixes chat (solidification)
- `13ef8a5` — Cartes mail insérées au bon endroit : colonne `conversation_id`
  exposée par `pending_actions.get_pending` + `chat_history`, côté frontend
  `addMessage` pose `data-aria-memory-id` et `appendPendingActionToChat`
  utilise `insertAdjacentElement('afterend')` avec smart fallback.
- `5e63167` — Chat solide :
  - Backend timeout 30 → 90 s (résout le bug fantôme Opus 4.7 + 8192 tokens)
  - Polling côté client si timeout : surveille `/chat/history` 90 s et
    remplace l'erreur par la vraie réponse si elle arrive.
  - UX : scroll auto, question remonte en haut du viewport dès que Raya réfléchit.
  - Nouveau loader : sigle ✦ pulsé + texte italique rotatif (6 phrases).
  - Timezone fix : `parseServerTimestamp` + toLocaleString Europe/Paris.
  - Flag `is_error` + `error_type` sur les réponses d'erreur.

### Tests automatisés (doc)
- `51e24c8` — Création `docs/raya_test_protocol.md` : 5 batteries de tests
  via Claude in Chrome (CHAT-BASELINE, CARTES-MAIL, GRAPHE, ODOO-ACTIONS,
  UX-SCROLL) avec règles validation humaine + rate limit respecté.

### Scheduler
- `e041e5d` — Ajout du wrapper `_job_confidence_decay` manquant (import
  échoué silencieusement au démarrage du scheduler Railway).

### Auto-découverte élargie Drive / Calendar / Contacts
- `d3bb5cf` — 3 nouvelles fonctions `discover_*` dans `tool_discovery.py` +
  3 `populate_from_*` dans `entity_graph.py`. Route admin
  `/admin/discover/{tenant_id}/{tool_type}` étendue à drive / calendar /
  contacts. Bouton 🔍 Découvrir étendu aux connexions Microsoft / Gmail
  (enchaîne drive → calendar → contacts automatiquement).
- Détection dynamique des modèles Odoo (planning.slot, hr.leave, etc.)
  au lieu de la liste hardcodée.

### Architecture — Matrice de capabilities (doc de design)
- Nouveau `docs/raya_capabilities_matrix.md` — socle d'autorisation à
  3 niveaux (default → admin → user) avec verrouillage, stratégie prompt
  "ultra-minimaliste actionnable" (Stratégie 4), tests de non-régression,
  plan d'implémentation par étapes A-F.
- Mise à jour `session_state.md` : section CONTEXTE MÉTIER COUFFRANT SOLAR
  (OpenFire vs Odoo, ressources planning, couleurs chantiers) +
  philosophie découverte 360°.
- Chantiers A (`populate` planning Odoo) + B (instruction prompt) + C
  (calendar 360°) en attente du socle capabilities.

---

## Session 18/04/2026 — Refonte intelligence + Graphe de relations (~20 commits)

### Refonte intelligence Raya
- Identité : "Tu es Claude, modèle d'Anthropic" → intelligence native libérée
- Prompt restructuré : contexte d'abord (utilisateur, données), règles CORE_RULES à la fin (30 lignes)
- Historique 6 → 30 échanges, max_tokens 2048 → 8192
- Routeur assoupli, quota Opus 20 → 50/jour, rate limiter 60 → 120/h
- Anti-bluff + anti-censure : "GÉNÈRE les tags ACTION, ne décris pas ce que tu vas faire — fais-le"
- Upgrade Claude Opus 4.6 → **4.7** (meilleur suivi instructions, auto-vérification)

### Actions Odoo (complètes)
- ODOO_SEARCH, ODOO_MODELS, ODOO_CREATE, ODOO_UPDATE, ODOO_NOTE
- Parseur `_extract_action_tags` — gère les crochets imbriqués (JSON Odoo)
- `_safe_parse_domain` — parse robuste des domaines Odoo
- Retry automatique sur KeyError (champs inconnus → fallback `name`)

### Auto-découverte outils (couche 2 — vectorisation)
- `tool_schemas` table DB avec embeddings vectoriels HNSW
- `discover_odoo()` — explore 21 modèles business, vectorise descriptions + champs + relations
- `retrieve_tool_knowledge()` — RAG injecte les schémas pertinents dans le prompt
- Bouton 🔍 Découvrir dans le panel admin sur chaque connexion Odoo

### Graphe de relations (couche 3 — cross-source)
- `entity_links` table DB — relie contacts ↔ factures ↔ mails ↔ fichiers ↔ Teams
- `entity_graph.py` : link_entity, get_entity_context, populate_from_odoo, populate_from_mail_memory
- Lookup graphe injecté dans le prompt quand un contact est mentionné
- Peuplement automatique lors du bouton Découvrir Odoo

### Synthèse auto (2ème appel LLM)
- Quand des résultats informatifs remontent (📊📋📇🗂️🔍❌), un 2ème appel LLM est lancé
- Raya voit ses propres résultats et fait la synthèse (tableaux, totaux, analyse)
- Les données brutes sont masquées quand la synthèse réussit
- aria_memory mis à jour avec la synthèse

### UX
- Bouton stop (annuler prompt en cours) + verrouillage double envoi (AbortController)
- Résultats informatifs affichés dans le chat (plus en toasts perdus)
- `_strip_action_tags` — parseur avec profondeur de crochets
- Fix panel admin : syntaxe JS askDeleteUser, try/catch loadMemoryStatus, showToast→setAlert

### Route admin DEV ONLY
- `/admin/reset-history/{username}` — archive l'historique (DEV ONLY, à supprimer en prod)

### Audits #3 #4 #5
- Actions : username injecté dans confirm, gate outlook_token supprimé
- Scheduler : _job_enabled dédupliqué, imports morts
- Frontend : XSS toast (textContent)

## Session 17/04/2026 — Audit & Sécurité (~5 commits)

### Nettoyage post-Sonnet
- 11 scripts de patch non exécutés supprimés (tous obsolètes après refactoring)
- 3 modifications utiles récupérées : prompt TRANSCRIPTION VOCALE + CORRECTIONS VIA CARTE, learned flag
- `google_contacts.py` orphelin supprimé (gmail_connector2.py fait le travail)

### Audit sécurité
- `assert_connection_tenant()` — vérifie qu'une connexion appartient au tenant avant toute opération
- Routes connexions dupliquées 2× dans `tenant_admin.py` → nettoyées
- `_build_tenants_overview()` exposée sans auth → décorateur route supprimé
- Injection credentials par tenant admin → bloquée (forcé `credentials={}`)
- 646 lignes dead code supprimées (`admin.py` + `admin_endpoints.py`)

### Panels séparés (sécurité)
- `/admin/panel` → `require_admin` uniquement (super admin)
- `/tenant/panel` → nouveau template `tenant_panel.html` (tenant admin)
- Tenant admin : 2 onglets seulement (Ma société + Mon profil), zéro accès aux fonctions super admin
- Menu chat (⋮) : routing automatique selon scope

## Session 16-17/04/2026 — Architecture unifiée (~40 commits)

### Raccourcis éditables v2
- Table `user_shortcuts`, API CRUD, modale titre+prompt+couleur, stockage DB

### Sujets intégrés sidebar
- Remplacement du drawer noir par section `<details>` dans la sidebar

### Palette couleurs
- Bleu Roi Saturé #0057b8, fond pastel #f5f9ff

### Système mail complet
- Signature email avec logo, auto-injection dans `_build_email_html`
- Action SEND_MAIL implémentée de bout en bout
- Cartes de confirmation dans le flux chat (persistées en DB)
- Carte mail éditable (De dropdown, À input, Corps textarea)
- Bouton 📁 Brouillon (Outlook Drafts + Gmail Drafts)
- Apprentissage depuis corrections (`learn_from_correction`)

### Architecture connecteurs unifiés
- `MailboxConnector` : Microsoft + Gmail, interface commune
- `DriveConnector` : SharePoint + Google Drive
- `MessagingConnector` : Teams (+ futur Slack/WhatsApp)
- `mailbox_manager.py`, `drive_manager.py`, `messaging_manager.py`
- Tags Raya unifiés : `SEND_MAIL:boite|to|sujet|corps`, `SEARCHDRIVE:drive|query`
- Calendriers unifiés : Microsoft + Google Calendar, 7j, create/update/delete

### Tokens — source unique
- `tenant_connections` = seule source de vérité
- Migration auto au démarrage (`token_migration.py`)
- `oauth_tokens` / `gmail_tokens` dépréciées (tables conservées, zéro écriture)
- Fallbacks legacy supprimés de `mailbox_manager.py`

### Audit cœur Raya (10 fixes)
- MAILBOX_BLOCK dynamique (plus hardcodé Guillaume)
- embed(query) ×1 au lieu de ×4, 5 index DB, pool 2→15
- Cache build_blocks 2-5min, FORMAT_BLOCK module-level
- Soft-delete synthèse, confiance adaptative, dédup RAG robuste

### Panel admin
- Onglet Utilisation (tokens Claude par tenant/user)
- Résumé connexions dans entête tenant
- Display name, modal Paramètres, suppression compte

### Divers
- Bandeau token expiré + bouton reconnecter
- Google contacts via People API (dans GmailConnector2)
- Scope Gmail étendu (mail.google.com + contacts + calendar + drive)
- OAuth admin pour connexions V2

## Session 16/04/2026 suite — 17h00 (Opus + Guillaume)

### Signature email — système complet ✅
- `app/connectors/outlook_calendar.py::_build_email_html` → appelle `get_email_signature(username)` (déjà en place)
- Logo `app/static/5AEA8C3F-2F59-4ED0-8AAA-3B324C3498DF.png` présent et référencé dans `_static_signature`
- `app/routes/aria_context.py::FORMAT_BLOCK` : ajout instruction "Ne jamais inclure de signature dans un mail que tu rédiges : la signature est ajoutée automatiquement par le système"
- Raya ne signe plus elle-même — chaîne complète opérationnelle

### Docs mis à jour
- `docs/raya_session_state.md` : réécriture complète (cache-bust v=36, tâches session 16/04 documentées, signature, display_name, palette, roadmap à jour)
- `docs/raya_changelog.md` : présente entrée

---

## Session 16/04/2026 matin suite — 07h00→12h54 (Opus + Guillaume — ~35 commits)

### Raccourcis éditables v2 ✅
- `529b412` — Table `user_shortcuts` + CRUD API `/shortcuts` (GET/POST/PATCH/DELETE)
- `5dd7a8f` — UI modale titre + prompt personnalisé + sélecteur 12 couleurs + delete
- `228a032` — Fix Safari : `let shortcutsEditMode` dupliqué supprimé (crash showToast)

### Sujets intégrés sidebar ✅
- `5dd7a8f` — `topicsSidebarList` dans HTML `<details open>`, `chat-topics.js` v3 miroir raccourcis
- `4e3d6be` — Design final : triangle sidebar agrandi, topics v3 aligné raccourcis

### Palette couleurs ✅
- `47e28bc` — Palette 6 "Bleu Roi Saturé" `#0057b8` appliquée (v=27)
- `53deb1d` — Fond pastel `#f5f9ff`, borders `#bdd6ff` (v=30)

### display_name ✅
- `08b1e3e` — Migration DB, `/profile/display-name`, `list_users`, `/chat` inject
- `19bcfcf` — UI modal admin, carte profil, logo italic bleu, footer sans username
- `0be7a90` — `loadUserInfo()` priorité display_name sur username

### Modal Paramètres refonte ✅
- `8a8885` — Lecture auto + display_name + email + MDP + RGPD + Valider/Annuler sticky (v=32)
- `d527f79` — Zoom viewport autorisé, modal 65vw/85vh scrollable (v=33)
- `90db119` — SVG Lucide dans Paramètres, puces modernes réponses Raya (v=34)

### Suppression compte avec validation admin ✅
- `e808ad6` — Workflow request/confirm/reject/cancel, MDP requis

### Fixes mails ✅
- `ea8026e` — Raya ne répète plus les règles après LEARN + nommage boîtes mail permanent
- `6008a6a` — Pluralisation "règles mises à jour" + interdire `__email__` dans réponses
- `a859d55` — Réponse mail : carte propre, `\n` corrigé, lookup tolérant, UX modernisée (v=36)

### Fixes UX
- `221adf3` — textarea overflow-y:hidden (supprime scrollbars vides dans la saisie)
- `64c5c87` — Ma société restauré pour super admin
- `cdc76c6` — username injecté côté serveur + page login palette bleue v2

---

## Session 16/04/2026 (Opus + Guillaume — ~10 commits)

### FIX-CRITICAL : Package admin/ shadow
- `5bd1e5c` — Routes suspension, direct-actions, seed-user, /tenant/my-overview injectées dans le package `app/routes/admin/super_admin.py`. Le fichier `admin.py` était shadowed par le dossier `admin/` depuis le 12/04.

### FIX-CRITICAL : OAuth fallback "guillaume"
- `8ef3f27` — Fallback `request.session.get("user", "guillaume")` supprimé dans les callbacks Microsoft + Gmail. Session vide → page 401.

### Migration DB prod
- Colonnes `suspended BOOLEAN` + `suspended_reason TEXT` ajoutées manuellement via psycopg2 (manquaient en prod).

### Suspension & Actions directes
- `93d97cb` — Feedback suspension : alertes vers l'onglet actif
- `65c7f0e` — `/tenant/my-overview` + `direct_actions_override` par user
- `264efb0` — Cartes sociétés restent ouvertes après suspend/toggle
- Actions directes retirées du super admin, toggle per-user cycle (hérité/ON/OFF)

### Panel admin multi-rôle
- Panel accessible aux `tenant_admin` (onglets Sociétés + Profil uniquement)
- Drawer chat filtré par scope (sections super-admin masquées)
- Bouton 🖥 Panel visible pour tenant_admin via `/profile`

### Sécurité panel
- `9241291` — Re-auth mot de passe pour accès panel (timeout 10 min)
- 2 boutons header : `🔑 Super Admin` + `⚙️ Ma société`
- Page de login admin dédiée, endpoint `POST /admin/auth`

### Fix micro
- `eaa7d00` — `SpeechRecognition.stop()` manquant, objet stocké en global `currentRecognition`

---

## Session 15/04/2026 soir (~15 commits)
- 8 fichiers morts supprimés (aria.py, raya_actions.py, etc.)
- PWA Topics : bouton 🔖 + panneau latéral `chat-topics.js`
- Split CSS (chat.css → 3 fichiers) + split admin_panel.html (CSS+JS extraits)
- Split Python batch final (13 splits Sonnet + 6 hotfixes Opus imports circulaires)
- C1+C2 : 8 profils seeding + endpoint `POST /admin/seed-user`
- Refonte panel admin : SIRET obligatoire, adresse 3 champs, ID auto, double confirmation suppression, bouton ➕ collaborateur
- Cloisonnement Drive : défauts neutres, plus de fallback vers Couffrant Solar
- Suspension comptes : users + tenants, login + API, boutons ⏸️/▶️
- Actions directes on/off par société + par user
- FIX-CRITICAL : 16 décorateurs de routes restaurés dans admin_endpoints.py

## Session 15/04/2026 matin (~70 commits)
- TOPICS 5/5 : 5 endpoints CRUD + migration DB + prompt injection + RGPD + Flutter prêt
- FIX-CLEAN + TIMESTAMP : nettoyage actions brutes + horodatage messages
- RENAME raya_chat + 3 bugs chat corrigés
- Refactoring BATCH 1+2+3 : 19 splits (tous les fichiers Python < 10KB)
- UX-TONE : style conversationnel naturel
- Bug report amélioré : commentaire optionnel + collecte auto échanges
- 👍 confirme pending actions + DELETE/ARCHIVE mutuellement exclusifs
- 3 hotfixes imports cassés

## Session 14/04/2026 (~45 commits)
- AUDIT COMPLET : inventaire de toute la codebase
- P0-1 : anti-injection prompt (GUARDRAILS, CSP)
- SAV/Bug report système complet
- Bloc A : PWA, safe-area iOS, autoSpeak off
- B1 B3 B4 : Teams ingestion, email signatures v2, scheduler
- C3 : RGPD complet (export + suppression + mentions légales)
- FIX-LEARN : pilule verte mémoire
- Split aria_context + security_users
- Lancement Flutter (app iOS simulateur)

## Session 12-13/04/2026 (~105 commits)

### Phase 5A — Sécurité & dette technique (14/14 ✅)
MDP env obligatoire, cookie 7j, rate limiter, audit log, migration llm_complete, wrappers supprimés, tools_registry source de vérité, APScheduler, 9 scripts legacy supprimés.

### Phase 5B — Optimisation prompt (5/5 ✅)
Injection dynamique actions, hot_summary 3 niveaux, cache TTL 5min, déduplication RAG, ThreadPoolExecutor.

### Phase 5C — Robustesse (4/4 ✅)
Structured logging, health check profond, timeout 30s, monitoring APScheduler.

### Sessions précédentes
Phases 1–4 : RAG, multi-tenant, rule_validator, feedback, scheduler, tests.
