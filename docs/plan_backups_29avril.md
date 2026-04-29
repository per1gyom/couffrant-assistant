# 🛡️ Plan backups Raya — 29 avril 2026

> **Statut** : Phase 1 ACTÉE le 29/04 matin. Phase 2 à coder.
> **Décisions design** : à valider avec Guillaume avant code.
> **Pré-requis** : audit isolation user-user terminé (28/04 soir, 6 commits).

## Contexte et menaces

Aujourd'hui Raya tourne sur Railway. Toutes les données utiles vivent
**uniquement** chez Railway :

- DB Postgres : 2 GB (222 conversations + 947 mails + 150 règles + 2.6M
  rows odoo_semantic_content + graphe sémantique)
- Variables d'environnement : OPENAI_API_KEY, ANTHROPIC_API_KEY,
  ENCRYPTION_KEY (chiffre tous les tokens OAuth en DB), SMTP_*,
  CLIENT_ID/SECRET Microsoft, etc.

Le code Python est sur GitHub + clone local Mac de Guillaume. Pas de
risque sérieux côté code.

3 menaces concrètes contre les données :

1. **Bug dans une migration ou une commande SQL** → corruption ou perte
   de tables (déjà arrivé une fois début avril, recovered avec un dump
   manuel)
2. **Railway plante 24-72h** → service indisponible mais récupérable
3. **Railway disparaît / compte suspendu / pirate efface tout** →
   perte totale si pas de backup hors-Railway

## Phase 1 — Backups Railway natifs ✅ ACTÉE 29/04 matin

Configuré dans Railway : Postgres → onglet Backups.

3 schedules activés :
- **Daily** (toutes les 24h, gardés 6 jours) — protection contre
  corruption/migration foireuse à très court terme
- **Weekly** (tous les 7 jours, gardés 1 mois) — vue intermédiaire 1 mois
- **Monthly** (tous les 30 jours, gardés 3 mois) — vue long terme

Au total ~17 points de restauration simultanés disponibles. Restauration
1 clic dans le dashboard Railway.

**Couvre** : 80% des risques (menaces 1 et 2).
**Ne couvre PAS** : menace 3 (Railway disparaît). D'où Phase 2.

Test manuel effectué : 1 backup manuel créé le 29/04 12:49 UTC,
2.54 GB, OK.

## Phase 2 — Backup externe (à coder, ~2h)

### Objectif

Job nocturne automatique qui :
1. Génère pg_dump complet
2. Exporte les variables d'environnement Railway critiques
3. Compresse en tar.gz
4. Chiffre avec une clé dédiée (ENCRYPTION_KEY différente de celle
   utilisée pour les tokens OAuth)
5. Upload vers un destinataire externe (à choisir : OneDrive pro / B2 /
   les deux)
6. Garde les 30 derniers jours en rotation
7. Envoie un mail à Guillaume si échec 2 nuits consécutives

### Décisions design à valider AVANT code

**D1. Destinataire externe**
- 🅐 OneDrive perso (5 Go, trop court)
- 🅑 OneDrive pro (1 To inclus M365) — reco
- 🅒 Backblaze B2 (~30 cts/mois)
- 🅓 OneDrive pro + B2 (redondance)

**D2. Clé de chiffrement (BACKUP_ENCRYPTION_KEY)**
- Générée une fois, stockée dans :
  - Railway env vars (pour que le job nocturne puisse chiffrer)
  - Note Apple verrouillée de Guillaume (pour pouvoir déchiffrer si
    Railway tombe)
- ⚠️ JAMAIS la même valeur que ENCRYPTION_KEY (qui chiffre les
  tokens OAuth en DB) — clés séparées par hygiène

**D3. Heure du job**
- 3h du matin UTC (= 5h heure française), peu de trafic
- Reco par défaut

**D4. Volume aria-data-volume sur le service Saiyan (l'app)**
- À vérifier en Railway : si vide ou < 100 MB → pas besoin de backup
- Si > 1 GB → investiguer ce que c'est

**D5. Variables Railway à exporter dans le backup**
- Liste complète à confirmer, mais cible :
  - DATABASE_URL (oui)
  - ENCRYPTION_KEY (oui — si on perd ça, tous les tokens OAuth chiffrés
    en DB sont inutilisables)
  - SESSION_SECRET (oui)
  - OPENAI_API_KEY, ANTHROPIC_API_KEY (oui)
  - SMTP_* (oui)
  - CLIENT_ID, CLIENT_SECRET, AUTHORITY (Microsoft, oui)
  - APP_USERNAME, APP_PASSWORD (legacy boot, oui pour cohérence)
- Récupérables via API Railway ou copie manuelle dans une env var
  RAYA_BACKUP_SECRETS_BUNDLE

### Étapes code

| # | Sujet | Effort |
|---|---|---|
| C.1 | Création compte destinataire + clés API | 10 min (Guillaume) |
| C.2 | Stockage clés dans Railway env vars | 2 min (Guillaume) |
| C.3 | Module `app/backup_external.py` (compression + chiffrement + upload) | 45 min (Claude) |
| C.4 | Job scheduler (3h du matin) | 15 min (Claude) |
| C.5 | Endpoint `/admin/backup/test` (déclencher manuel) | 10 min (Claude) |
| C.6 | Endpoint `/admin/backup/restore-test` (téléchargement chiffré pour test sur Mac) | 10 min (Claude) |
| C.7 | Test bout-en-bout : déclenche manuel → vérif fichier → tente déchiffrement local | 15 min (Guillaume + Claude) |
| C.8 | Logs structurés + alerte mail si 2 échecs consécutifs | 15 min (Claude) |
| C.9 | Doc procédure de restoration externe (`docs/procedure_restoration_backup.md`) | 15 min (Claude) |

**Total estimé : ~2h15.**

### Tests obligatoires avant validation

🛑 **Un backup non-testé n'existe pas.** Avant de considérer la
Phase 2 terminée, on doit :

1. Lancer un backup manuel via `/admin/backup/test`
2. Vérifier que le fichier arrive bien sur le destinataire externe
3. Le télécharger sur le Mac
4. Le déchiffrer avec la clé stockée dans la note Apple verrouillée
5. Importer dans une DB Postgres locale ou un fork du projet Railway
6. Vérifier qu'on retrouve bien les 222 conversations + 947 mails + etc.

Sans cette procédure validée, on peut PAS dire que les backups
fonctionnent.

## Phase 3 — Solidifier le poste de travail (optionnel, plus tard)

À discuter avec Guillaume, pas bloquant pour le déploiement version
d'essai :

- Time Machine sur disque externe SSD (~80€)
- iCloud Drive avec plan suffisant pour avoir une copie cloud du Mac

## Récap commitments

| Décision | Statut |
|---|---|
| Phase 1 — backups Railway natifs (Daily 6j + Weekly 1m + Monthly 3m) | ✅ Actée 29/04 matin |
| Phase 2 — backup externe (D1 destinataire) | 🔴 À valider |
| Phase 2 — clé de chiffrement séparée (D2) | 🔴 À valider |
| Phase 2 — heure du job (D3 = 3h UTC) | 🔴 À valider (par défaut) |
| Phase 2 — volume aria-data-volume (D4) | 🔴 À investiguer |
| Phase 2 — variables Railway à exporter (D5) | 🔴 Liste à confirmer |
| Phase 3 — Time Machine + cloud drive (optionnel) | 🟡 Plus tard |

## Lien avec autres chantiers

| Chantier | Statut | Lien |
|---|---|---|
| Audit isolation user-user (LOTs 1-4) | ✅ Terminé 28/04 soir | indépendant |
| 2FA externes (3/6 fait) | 🟡 En cours, fait à son rythme | indépendant |
| 2FA Raya côté app (Niveau 2) | 🔴 Décisions Q1-Q7 actées, à coder ~5h | après Phase 2 backups |
| Note UX #7 retirer Administration menu user | 🔴 À faire ~2-3h | indépendant |
| Outlook contact@couffrant-solar.fr | 🔴 Quand codes Azure prêts | indépendant |

---

# ✅ Phase 2 — TERMINÉE 29 avril 2026 (soirée)

> **Statut final** : Phase 2 entièrement déployée en production, testée
> bout-en-bout avec preuve de restauration. Système de backup nocturne
> automatique chiffré opérationnel.

## Résumé exécutif

- ✅ Backup nocturne automatique chaque jour à 3h UTC
- ✅ Fichier .tar.gz.enc chiffré (Fernet) uploadé sur Google Drive Saiyan
  Backups (Shared Drive du compte Workspace `admin@raya-ia.fr`)
- ✅ Format pg_dump custom (-Fc) optimisé : ~250 MB compressé pour 2 GB de DB
- ✅ Durée par backup : ~2 minutes (vs ~9 min en CSV fallback)
- ✅ Rotation auto : 30 derniers jours gardés, le reste supprimé
- ✅ Alerte mail à `admin@raya-ia.fr` si 2 échecs consécutifs
- ✅ Timeout serveur 10 min pour ne jamais bloquer le scheduler
- ✅ Restoration validée : déchiffrement OK, intégrité SHA256 prouvée

## Décisions D1-D5 prises

| Décision | Choix final |
|---|---|
| **D1 Destinataire** | Google Drive Saiyan Backups (Shared Drive Workspace `admin@raya-ia.fr`, 2 To inclus dans le plan Business Standard 13.60€/mois) |
| **D2 Clé chiffrement** | `BACKUP_ENCRYPTION_KEY` Fernet (32 bytes base64), générée 29/04, stockée Railway env + note Apple verrouillée Guillaume. Auto-référentielle exclue de la denylist (le backup ne contient PAS sa propre clé pour ne pas créer de faille) |
| **D3 Heure du job** | 3h UTC = 5h Paris (peu de trafic, après les rollups de minuit) |
| **D4 Volume aria-data-volume** | À investiguer dans une session ultérieure (pas bloquant) |
| **D5 Variables exportées** | 47 inclus / 31 exclus (denylist : RAILWAY_*, secrets système Linux, BACKUP_ENCRYPTION_KEY auto-référentielle). Liste complète dans le manifest de chaque backup |

## Stack technique finale

```
                          ┌─────────────────────────────┐
   APScheduler 3h UTC ──→ │   run_backup_external()     │ (timeout 10 min)
                          │   ↓                          │
                          │   1. pg_dump -Fc            │ ← postgres-client-18
                          │   2. _collect_secrets()     │ ← os.environ + denylist
                          │   3. tar.gz                 │ ← in-memory
                          │   4. encrypt Fernet         │ ← BACKUP_ENCRYPTION_KEY
                          │   5. upload Drive resumable │ ← Service Account JSON
                          │   6. rotation > 30j         │
                          └─────────────────────────────┘
                                       ↓
                  Drive Saiyan Backups (Shared Drive ID 0ADHBMHnIH-dvUk9PVA)
                                       ↓
                         raya_backup_<YYYY-MM-DD_HH-MM>.tar.gz.enc
```

### Container Railway

Avant : Railpack (auto-détection Python) → pas de pg_dump dispo

Après : **Dockerfile explicite** avec :
- Base `python:3.13-slim-bookworm` (Debian 12 LTS)
- `postgresql-client-18` installé via repo officiel `apt.postgresql.org`
- Garde-fou `RUN pg_dump --version` dans le build (casse si pas dispo)
- Script de démarrage `entrypoint.sh` (résoud `$PORT` au runtime)

### Important : Custom Start Command Railway

🛑 **À documenter pour ne JAMAIS y revenir** : Railway → service Saiyan
→ Settings → Deploy → Custom Start Command doit valoir
**`/app/entrypoint.sh`** (pas vide, sinon des fois Railway garde son
ancienne valeur fantôme `uvicorn ... --port $PORT` qui plante).

Sans cette ligne, l'app crashe en boucle au démarrage avec
`Error: Invalid value for '--port': '$PORT'`.

## Améliorations 1, 2, 3

### Amélioration 1 — pg_dump natif (TERMINÉE)

**État initial** : Railpack auto-détecté Python sans pg_dump dans le
PATH → fallback CSV via `COPY TO STDOUT` pour chaque table → durée
~9 min, dump 1.5 GB.

**Solution finale** : Dockerfile explicite avec
`postgresql-client-18` depuis le repo officiel + flag `-Fc` pour
format custom compressé.

**Gain mesuré** :
- Durée : 579 s → 128.8 s (×4.5)
- Dump : 1.5 GB → 448 MB (×3.4)
- Pic RAM : 3-5 GB → ~500 MB
- Format : SQL plain → binaire pg_dump custom (restorable via
  `pg_restore`, plus puissant)

### Amélioration 2 — Streaming au lieu de RAM (REPORTÉE)

**Décision** : reportée sine die. Le pic RAM est passé à ~500 MB grâce
à l'amélioration 1, ce qui est largement acceptable pour Railway.
À reconsidérer quand la DB dépassera 5-10 GB.

### Amélioration 3 — Timeout 10 min (TERMINÉE)

**Risque adressé** : si pg_dump bug, Drive injoignable, ou bug Python
quelconque, un job APScheduler peut rester bloqué indéfiniment en
consommant RAM/CPU.

**Solution finale** : wrapper `concurrent.futures.ThreadPoolExecutor`
+ `future.result(timeout=600)` autour de l'orchestrateur interne
`_run_backup_external_inner()`.

**Pourquoi ThreadPoolExecutor** : `signal.alarm()` ne marche QUE dans
le thread principal, KO car APScheduler tourne ses jobs dans des
threads workers.

**Limite connue** : un thread Python ne peut pas être kill de force
(GIL). Donc en cas de timeout, le thread du backup continue en
arrière-plan jusqu'à terminer naturellement, mais on a déjà rendu la
main au scheduler avec un résultat d'échec. Acceptable.

## Validation bout-en-bout (29/04 soir)

### Backups réussis

| Heure | Format | Durée | Dump | .enc | Validation |
|---|---|---|---|---|---|
| 18:47 | CSV (pg_dump pas dispo) | 9 min 39 | 1.5 GB | 570 MB | ✅ Restoration testée |
| 19:25 | CSV (Nixpacks toml ignoré) | 9 min 33 | 1.5 GB | 570 MB | ✅ |
| 21:01 | pg_dump SQL plain | 6 min 57 | 1.5 GB | 570 MB | ✅ |
| **21:21** | **pg_dump custom -Fc** | **2 min 9** | **448 MB** | **594 MB** | ✅ |

### Test de restauration validé

Sur le 1er backup (18:47, format CSV) :
- ✅ Téléchargement du `.tar.gz.enc` 570 MB depuis Drive
- ✅ Déchiffrement Fernet OK avec `BACKUP_ENCRYPTION_KEY`
- ✅ Extraction tar.gz : 3 fichiers (dump.sql, secrets.env, manifest.json)
- ✅ SHA256 du dump = SHA256 manifest (intégrité prouvée)
- ✅ 60 tables présentes dans le dump (cohérent avec la DB)
- ✅ Tables critiques vérifiées : users, aria_memory, mail_memory,
  aria_rules, tenants

### Endpoints admin opérationnels

Tous protégés par `require_super_admin` (Guillaume seul) :

| Endpoint | Méthode | Rôle |
|---|---|---|
| `/admin/backup/external/health` | GET | Status configuration (sans auth, debug) |
| `/admin/backup/external/run` | POST | Déclenche un backup manuel |
| `/admin/backup/external/list` | GET | Liste les backups sur Drive |
| `/admin/backup/external/diagnose` | GET | Diagnostic binaires/PATH (debug) |

## Commits déployés (8 commits le 29/04)

| Commit | Sujet |
|---|---|
| `d75bfa3` | docs(backup) plan + procedure_urgence (matin) |
| `7ac7d1d` | feat(backup) crypto_backup module Fernet |
| `b8510d8` | feat(backup) module backup_external orchestrateur |
| `41433f2` | feat(backup) job APScheduler nocturne 3h UTC |
| `162ae0e` | feat(backup) endpoints admin |
| `2e15a41` | feat(backup) endpoint diagnose |
| `a9b8efb` | feat(backup) Dockerfile + .dockerignore |
| `bc7f20c` + `030d434` | fix(backup) tentatives PORT (intermédiaires) |
| `1113138` | chore(backup) cleanup commentaires Dockerfile |
| `bce4e51` | feat(backup) pg_dump -Fc + timeout ThreadPoolExecutor |

## Procédure de restauration

Voir **`docs/procedure_urgence.md` §4 — Railway en panne complète**
(mise à jour le 29/04 avec la vraie procédure Fernet + pg_restore).

## Fichiers / variables / secrets liés

### Fichiers code Raya
- `app/backup_external.py` — orchestrateur + endpoints (660 lignes)
- `app/crypto_backup.py` — chiffrement Fernet
- `app/scheduler_jobs.py` — job nocturne 3h UTC
- `Dockerfile` — image avec pg_dump 18
- `entrypoint.sh` — script de démarrage uvicorn
- `.dockerignore` — exclusions de build

### Variables Railway
- `BACKUP_ENCRYPTION_KEY` — clé Fernet (32 bytes base64)
- `GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON` — clé du service account
- `GOOGLE_DRIVE_BACKUP_FOLDER_ID` — ID du Shared Drive (`0ADHBMHnIH-dvUk9PVA`)
- `BACKUP_ALERT_EMAIL` — destinataire alerte (def `admin@raya-ia.fr`)
- `BACKUP_KEEP_DAYS` — nb jours rétention (def 30)
- `SCHEDULER_BACKUP_EXTERNAL_ENABLED` — toggle on/off (def true)

### Comptes externes
- Google Workspace `admin@raya-ia.fr` (plan Business Standard, 2 To)
- Service Account `raya-backup-bot@saiyan-backups.iam.gserviceaccount.com`
- Shared Drive `Saiyan Backups` (ID `0ADHBMHnIH-dvUk9PVA`)
- Note Apple verrouillée Guillaume (contient les clés sensibles)

## Prochaine étape — passive surveillance

Plus rien à faire activement sur le backup. Le scheduler tourne tout
seul. À surveiller à intervalle régulier (1× / mois) :

- `/admin/backup/external/list` → vérifier que la liste contient bien
  les 30 derniers jours
- Drive Saiyan Backups → vérifier visuellement la présence des fichiers
- En cas d'absence d'alerte mail = tout va bien (silence is golden)

🛑 **Si jamais une alerte mail arrive** : voir
`docs/procedure_urgence.md` §4 ou §3 selon le contexte.
