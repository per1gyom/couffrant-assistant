# Journal 02 mai 2026 — Drive multi-racines (Semaine 5)

## Contexte

Suite a la session du matin (Pub/Sub Gmail valide en mode TRIGGER, Semaine 4
Gmail terminee), Guillaume a souleve un besoin majeur d'architecture pour la
Semaine 5 :

> "Il faut pouvoir mettre une racine ou plusieurs racines de drive parce qu il
> peut y avoir plusieurs dossiers partages [...] et pouvoir definir [les
> exclusions] de maniere assez precise parce que chacun aura ses manieres de
> classer ses documents."

Cette demande vient de la realite Couffrant Solar :
- Drive Commun : OK pour Raya (sauf exclusions ponctuelles)
- Drive Direction : acces granulaire (RH/Salaires interdits, Comptabilite OK)
- Et future generalisation a tous tenants/providers (SharePoint, Google Drive,
  NAS, drives prives futurs).

## Decisions architecture validees ensemble

### Regle 1 : Heritage par defaut (chemin le plus long gagne)

Un dossier inclus/exclu se propage a ses sous-dossiers, **sauf override
explicite plus profond**. Logique identique a `.gitignore` ou Windows
Explorer.

```
Configuration :
  ✅ /Drive Commun                (include implicite via racine)
  ❌ /Drive Direction/RH          (exclude)
  ✅ /Drive Direction/RH/Public   (override = re-include)

Pour un fichier /Drive Direction/RH/Public/charte.pdf :
  -> 3 regles matchent : Drive Direction, /RH, /RH/Public
  -> Le path le plus long gagne : /RH/Public (include)
  -> Resultat : INDEXE
```

### Regle 2 : Nouveaux dossiers (logique Guillaume validee)

- Nouveau dossier dans un dossier ACCESSIBLE -> indexe automatiquement
  (sinon Raya ne verrait jamais les nouveaux clients).
- Nouveau dossier dans un dossier EXCLU -> non indexe.
  L'admin doit explicitement le re-inclure si besoin.

### Regle 3 : Granularite dossier uniquement

Pas de regle au niveau fichier individuel. Pour un fichier sensible
isole, on le met dans un sous-dossier blackliste.

### Permissions

- Tenant admin : configure son propre tenant (cas standard).
- Super admin Raya : peut acceder pour debug/depannage tous tenants.
- V2 future : drives prives -> configures par leur user proprietaire
  (pas par admin tenant). Anticipation via colonne `scope` (tenant/user).

## Implementation

### Phase 1 : Backend (commit a venir)

#### Migrations DB (database_migrations.py)

Section "Phase Drive multi-racines (02/05/2026 matin)" ajoutee a la fin :

- `M-DMR01` : ALTER TABLE `tenant_drive_blacklist` ADD COLUMN `rule_type`
  TEXT NOT NULL DEFAULT 'exclude' CHECK (include/exclude).
  Backward compat : les regles existantes deviennent type=exclude.
- `M-DMR02` : ADD COLUMN `scope` TEXT NOT NULL DEFAULT 'tenant'
  CHECK (tenant/user). Prepare la V2 drives prives.
- `M-DMR03` : ADD COLUMN `owner_username` TEXT (NULL si scope=tenant).
- `M-DMR04` / `M-DMR05` : index pour les requetes is_path_indexable.

#### Module drive_path_rules.py (NOUVEAU)

Fichier `app/connectors/drive_path_rules.py` (281 lignes), expose :

- `_normalize_path(path)` : strip leading/trailing slashes.
- `_is_prefix_of(prefix, full)` : matching dossier complet (pas de
  faux positif type "RH" prefixe de "RH_Confidentiel").
- `get_drive_roots(connection_id)` : lit drive_folders.
- `get_path_rules(connection_id, scope='tenant')` : lit
  tenant_drive_blacklist.
- `is_path_indexable(connection_id, path, *, roots, rules)` : decision
  principale. Args optionnels pour eviter requetes DB en boucle.
- `explain_path_decision(connection_id, path)` : explique la decision
  pour la page admin de simulation.

#### Integration drive_scanner.py

Pre-charge roots+rules une fois par scan, puis check chaque fichier
avant `_process_file`. Stat `filtered_by_rules` ajoutee. Failsafe : si
chargement plante, comportement actuel preserve (tout indexer).

Variable d'env `DRIVE_PATH_RULES_ENABLED` (defaut true) pour bypass
en cas de probleme.

#### Integration drive_delta_sync.py

- Nouvelle fonction `_is_path_filtered(connection_id, path, roots, rules)`
  qui wrap `is_path_indexable`.
- L'ancienne `_is_blacklisted` reste comme failsafe.
- `_process_change_shadow` et `_process_change_write` acceptent
  desormais `connection_id`, `path_roots`, `path_rules`.
- Au tick principal, on charge roots+rules une fois et on les passe
  a chaque appel.

### Phase 2 : UI Admin (commit a venir)

#### admin_drive_config.py (NOUVEAU)

Fichier `app/routes/admin_drive_config.py` (737 lignes), expose :

**Endpoints API (JSON) :**
- `GET  /admin/drive_config/drives/{tenant_id}` : liste connexions + roots.
- `GET  /admin/drive_config/rules/{connection_id}` : regles configurees.
- `POST /admin/drive_config/rules/{connection_id}` : ajoute/maj une regle
  (UPSERT sur connection_id+folder_path).
- `DELETE /admin/drive_config/rules/{rule_id}` : supprime une regle.
- `GET  /admin/drive_config/preview/{connection_id}?path=...` : simule
  la decision is_path_indexable + explication.

**Pages HTML :**
- `GET /admin/drive_config` : vue d'ensemble (connexions, racines,
  nb regles).
- `GET /admin/drive_config/configure/{connection_id}` : page detaillee
  avec :
  - Liste des regles existantes (path, type, scope, raison, action delete).
  - Formulaire ajout regle (path + type include/exclude + raison).
  - Outil "Tester un chemin" qui appelle `/preview/` et explique.

Permission : `require_admin` qui accepte super_admin ET admin tenant.
Verification du tenant_id via `_can_access_tenant` (super_admin acces
tous tenants, admin tenant uniquement le sien).

#### Enregistrement router (main.py)

Bloc try/except dans main.py apres admin_jobs_trigger, pattern identique.

## Tests

- `python3 -m py_compile` sur tous les fichiers modifies : OK.
- Pas de test unitaire automatise (a faire dans phase 3).

## A faire en Phase 3 (avec Guillaume)

1. Commit + push (declenche redeploiement Railway et applique migrations).
2. Verification : visite de `/admin/drive_config` pour voir l'UI.
3. Configuration ensemble :
   - Drive Commun : ajouter dossiers indexes hors /1_Photovoltaique.
   - Drive Direction : connecter (si pas deja fait), exclure RH/Salaires,
     RH/Recrutement, Negociations Confidentielles ; inclure
     Comptabilite/2024+, Strategie Commerciale, Politiques RH publiques.
4. Lancer scan complet (drive_scanner sur les nouvelles racines).
5. Validation : poser questions a Raya sur les nouveaux dossiers.

## Hors chantier (a reprendre plus tard)

- Nettoyage technique : suppression gmail_polling.py et outlook_polling.py
  (deja note Semaine 4).
- Semaine 6 WhatsApp : a faire en dernier.

## Etat de la branche au moment du commit

- Branche : `drive-multi-roots`
- Fichiers modifies :
  - `app/database_migrations.py` (5 nouvelles migrations en bas)
  - `app/jobs/drive_scanner.py` (pre-charge roots+rules + check par fichier)
  - `app/jobs/drive_delta_sync.py` (nouvelle fonction + passage params)
  - `app/main.py` (registration router admin_drive_config)
- Fichiers nouveaux :
  - `app/connectors/drive_path_rules.py` (281L, logique pure)
  - `app/routes/admin_drive_config.py` (737L, UI + API)
  - `docs/journal_02mai_2026_drive_multi_racines.md` (ce fichier)

Total : ~1100 lignes de code propre, idempotent, retro-compatible.
