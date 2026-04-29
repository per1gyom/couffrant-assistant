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
