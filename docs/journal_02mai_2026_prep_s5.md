# Journal session 02 mai 2026 - Preparation Semaine 5 (nuit autonome)

## Contexte

Apres la session du 01/05 soir qui a termine la Semaine 4 Gmail (etapes
4.3 a 4.8 + bug ROOT refresh_gmail_token), Guillaume est alle dormir vers
23h45 en demandant a Claude de preparer en autonomie ce qui pouvait
l etre pour la Semaine 5 (Drive/SharePoint).

Lecon retenue de la session precedente : **bosser sur une branche dediee
et auditer AVANT de commit**, contrairement a ce qui a ete fait sur main
hier soir.

## Branche

```
git checkout -b connections-refonte-s5-prep
```

Aucun merge sur main sans validation Guillaume au reveil.

## Travail realise (sans commit, audit prealable obligatoire)

### Module 1 : `app/jobs/drive_delta_sync.py` (771 lignes)

Polling delta Microsoft Graph toutes les 5 min sur `/drives/{id}/root/delta`.

Pattern identique au template `mail_outlook_delta_sync.py` :

  - Stockage du delta_link dans `connection_health.metadata` (JSONB)
  - Initialisation avec `?token=latest` pour eviter le rapatriement
    historique (drive_scanner s en occupe deja)
  - Pagination via `@odata.nextLink` jusqu au `@odata.deltaLink` final
  - Gestion HTTP 410 (delta expire) -> drop le delta_link, re-init au
    prochain tick
  - 2 modes : SHADOW (defaut, log seulement) et WRITE (delegate a
    drive_scanner._process_file pour vectoriser)

Variables Railway prevues :

  - `SCHEDULER_DRIVE_DELTA_SYNC_ENABLED` (defaut false)
  - `DRIVE_DELTA_SYNC_WRITE_MODE` (defaut false, mode shadow)

Soft delete : marque `deleted_at` dans `drive_semantic_content` pour les
fichiers detectes comme supprimes cote Microsoft (permet la restauration
si re-creation).

Blacklist : lecture systematique de `tenant_drive_blacklist` pour
exclure les chemins parametres par tenant.

### Module 2 : `app/jobs/drive_reconciliation.py` (332 lignes)

Job nocturne 5h30 : compare le count Microsoft (recursive) avec le count
Raya (drive_semantic_content level=1).

Seuils choisis :

  - Alerte WARNING si delta > 5% (vs 1% pour les mails)
  - ET delta absolu >= 50 fichiers
  - On n alerte QUE si Raya a moins que Microsoft (perte) - pas l inverse

Pourquoi 5% (vs 1% mails) :
  - Fichiers en cours d upload SharePoint
  - drive_scanner skip > 50 Mo et .doc legacy par design
  - Sensitivity Labels Microsoft Purview peuvent masquer
  - Blacklist evolue dans le temps

Creneau 5h30 choisi pour ne pas saturer Railway :
  - 4h00 Odoo recon
  - 4h30 Outlook recon
  - 5h30 Drive recon (potentiellement long, 3000+ fichiers a lister)
  - 6h00 Gmail watch renewal
  - 6h30 creneau libre

Variable Railway : `SCHEDULER_DRIVE_RECONCILIATION_ENABLED` (defaut false).

### Module 3 : Modifications `app/scheduler_jobs.py`

Ajout de 38 lignes a la fin de `_register_jobs` :

  - Branchement drive_delta_sync (IntervalTrigger 5 min)
  - Branchement drive_reconciliation (CronTrigger 5h30)
  - Tous deux DESACTIVES par defaut (defaut=False explicite)
  - Try/except autour de chaque import (lazy + protection)

## Audit prealable au commit (au reveil de Guillaume)

### POINT 1 - Verification signatures fonctions externes
✅ register_connection (connection_health) : signature OK
✅ record_poll_attempt (connection_health) : signature OK
✅ get_drive_config / _find_sharepoint_site_and_drive / _find_folder_root
   (drive_connector) : signatures OK
✅ get_valid_microsoft_token (token_manager) : signature OK
✅ alert_dispatcher.send : signature OK

### POINT 2 - Verification existence table tenant_drive_blacklist
✅ Table EXISTE deja en DB avec les bonnes colonnes (tenant_id, connection_id,
   folder_path, reason, created_by, created_at). Pas besoin de migration.

### POINT 3 - BUG TROUVE : tool_type filter
🚨 Premier code filtrait sur `tool_type IN ('sharepoint', 'google_drive')`
   Mais en base la connexion SharePoint est stockee comme `tool_type='drive'`
   (heritage historique).
✅ Corrige : filtre maintenant `IN ('drive', 'sharepoint', 'google_drive')`
✅ Normalisation pour le monitoring : `health_type = 'sharepoint' if 'drive'`
   (eviter `connection_type='drive_drive'` moche)

### POINT 4 - Test final requete _get_drive_connections
✅ Requete validee en DB : retourne bien la connexion 1 de couffrant_solar
   (label "SharePoint Commun")

### POINT 5 - Coherence avec template mail_outlook_delta_sync.py
✅ Memes patterns : delta_link en metadata jsonb, idempotent,
   record_poll_attempt a chaque tick

### POINT 6 - Risque parallele drive_scanner / drive_delta_sync
⚠️ Si delta_sync write_mode tourne pendant un scan complet : double quota
   OpenAI embed possible. Pas bloquant car write_mode demarre desactive.
   `_store_chunk` utilise ON CONFLICT donc pas de crash en concurrence.

### POINT 7 - Compilation finale
✅ `python3 -m py_compile` OK sur les 3 fichiers

## Ce qu il RESTE a faire (apres validation Guillaume)

1. **Commit + push sur la branche** `connections-refonte-s5-prep` (pas main)
2. **Decision Guillaume** : merger sur main maintenant en mode tout-disabled,
   ou laisser sur la branche jusqu a la prochaine session ?
3. **Pipeline comprehension contenu** : pour le moment, drive_delta_sync
   delegue a `drive_scanner._process_file` qui utilise deja la couche
   `app.scanner.document_extractors`. Le pipeline N1+N2 d embedding est
   donc deja la ; pas besoin de le reimplementer dans S5.
4. **UI blacklist** : panel admin pour gerer
   `tenant_drive_blacklist` - prochaine session avec Guillaume
5. **Re-onboarding historique Couffrant** : decision avec Guillaume,
   touche la prod, doit etre planifie

## Etat repo au moment de l ecriture du journal

```
Branche : connections-refonte-s5-prep
Modifies : app/scheduler_jobs.py (38 lignes ajoutees)
Nouveaux : app/jobs/drive_delta_sync.py (771 lignes)
           app/jobs/drive_reconciliation.py (332 lignes)
Pas encore commit, en attente du retour Guillaume.
```

## Variables Railway prevues (toutes desactivees par defaut)

```
SCHEDULER_DRIVE_DELTA_SYNC_ENABLED=false   (true plus tard)
DRIVE_DELTA_SYNC_WRITE_MODE=false           (mode shadow d abord)
SCHEDULER_DRIVE_RECONCILIATION_ENABLED=false  (true apres validation)
```

## Etat prod (au moment de l audit)

5 Gmail healthy, 2 Outlook healthy, 1 Odoo healthy, 1 Drive (scanner
existant) sans monitoring delta. Aucun risque d impact sur la prod
puisque rien n est merge.
