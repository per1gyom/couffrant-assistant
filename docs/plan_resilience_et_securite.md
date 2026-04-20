# 🛡️ Plan résilience et sécurité de Raya

**Version** : 1.0 — 20 avril 2026, nuit
**Statut** : à exécuter dans l'ordre des priorités
**Pour qui** : Guillaume (non expert technique) + Claude (dev)

---

## 🎯 Pourquoi ce document

Aujourd'hui, Raya tourne sur **un seul serveur** (Railway) avec **toutes ses données au même endroit**. Si ce serveur plante, ou si quelqu'un pirate le compte, Raya peut devenir inutilisable et les données peuvent être perdues.

Ce document liste tout ce qu'il faut faire pour que Raya soit **protégée** et **survive** à n'importe quel incident. À garder comme référence et à cocher au fur et à mesure.


## 📖 Petit glossaire français simple

| Terme | Ce que ça veut dire |
|---|---|
| **Serveur** | Ordinateur qui fait tourner Raya 24h/24, chez Railway |
| **Base de données (DB)** | Gros tableur géant où sont rangées les infos : mails vectorisés, SharePoint, clients, historiques |
| **Backup** | Copie de sauvegarde |
| **Cloud** | "Dans les nuages" = pas chez toi, sur des ordinateurs chez Amazon, Google, Microsoft, Railway... |
| **S3 AWS** | Disque dur en ligne chez Amazon. ~1€/mois pour notre volume |
| **Backblaze B2** | Équivalent moins cher que S3 AWS. ~0.50€/mois |
| **2FA** | Double authentification. Mot de passe + code envoyé sur téléphone. Comme ta banque |
| **GitHub** | Endroit où est stocké ton code. Comme un Google Drive pour programmeurs |
| **Docker / Dockerfile** | Emballage qui permet de déplacer Raya d'un serveur à un autre en 10 minutes |
| **Secret** | Clé/mot de passe que Raya utilise pour se connecter à OpenAI, Odoo, Microsoft... Doit rester secret |
| **HTTPS** | Le cadenas dans ton navigateur. Communications chiffrées |
| **Chiffrement** | Rendre des données illisibles sans la clé. Même si volées, inutilisables |
| **pg_dump** | Outil qui fait une copie complète de la base de données Postgres |
| **UptimeRobot** | Service gratuit qui vérifie toutes les 5 min que Raya répond. Alerte SMS si elle tombe |

## 🚨 Les 3 menaces à contrer

### Menace 1 — Railway plante ou disparaît
Raya ne marche plus. Le code reste en sécurité sur GitHub, mais les **données** (mémoire Raya, 3252 fichiers vectorisés, historiques) sont uniquement sur Railway. Si Railway brûle : perte totale.

### Menace 2 — Piratage de compte
Quelqu'un vole ton mot de passe Railway ou GitHub → accès à tout, vol de données clients, envoi de mails à ta place, demande de rançon possible.

### Menace 3 — Corruption des données
Un bug, une erreur, un disque qui casse. Tu peux perdre des mois de vectorisations du jour au lendemain.

## 🔐 Note importante sur GitHub vs Railway

**GitHub est toujours la source de vérité du code.** Railway récupère le code depuis GitHub à chaque déploiement. Cela veut dire :

- **GitHub peut être en avance** sur Railway (commits locaux pas encore pushés) — mais jamais problématique
- **Railway ne peut PAS être en avance** sur GitHub — si GitHub a le code, on peut toujours redéployer ailleurs

Conséquence : **protéger GitHub à tout prix**. C'est là que vit l'âme de Raya.


---

## 📋 Les 7 étapes à exécuter (validées par Guillaume le 20/04)

### 🔴 Priorité 1 — Cette semaine

#### ✅ Étape 1 — Activer 2FA sur tous les comptes critiques

**À faire par Guillaume lui-même** (impossible à déléguer, lié à son téléphone)

Télécharger une app d'authentification sur téléphone : **Google Authenticator**, **Microsoft Authenticator** ou **Authy** (Authy permet de sauvegarder, recommandé).

Puis activer 2FA sur chaque compte ci-dessous (5 min par service) :

- [ ] **GitHub** — https://github.com/settings/security → "Two-factor authentication" → "Set up using an app"
- [ ] **Railway** — railway.app → Profile → Security → Enable 2FA
- [ ] **OpenAI** — platform.openai.com → Settings → Security → 2FA
- [ ] **Anthropic Console** — console.anthropic.com → Settings → Security → 2FA
- [ ] **Microsoft 365** (`guillaume@couffrant-solar.fr`) — https://mysignins.microsoft.com → Sécurité → Vérification en 2 étapes
- [ ] **Google** (Gmail perso `per1.guillaume@gmail.com`) — myaccount.google.com → Sécurité → Validation en 2 étapes
- [ ] **Compte admin Raya** (à coder par Claude après — voir étape 7)

**Sauvegarder les codes de récupération** pour chaque service, dans un gestionnaire de mots de passe (Bitwarden gratuit recommandé). Si téléphone perdu, ces codes permettent de récupérer l'accès.

**Temps** : ~45 min au total, une seule fois dans ta vie.

---

#### ✅ Étape 2 — Sauvegardes automatiques nocturnes externes

**À coder par Claude** (~2h de code, 1 commit)

Chaque nuit à 3h du matin, Raya :
1. Fait un `pg_dump` complet de la base de données
2. Chiffre le fichier (avec une clé dédiée stockée à part)
3. Envoie la copie chiffrée vers **3 destinations** en parallèle :
   - **Amazon S3** (~1€/mois)
   - **Backblaze B2** (~0.50€/mois)
   - **OneDrive personnel** de Guillaume (gratuit avec Microsoft 365)
4. Garde les **30 derniers jours** de backups (rotation automatique)
5. Envoie un mail d'alerte si échec 2 nuits consécutives

**Ce que Guillaume aura à faire** (15 min) :
- Créer un compte AWS S3 (carte bancaire demandée mais coût ~1€/mois)
- Créer un compte Backblaze B2 (idem)
- Donner à Claude les clés d'accès pour stocker comme secrets Railway

**Sécurité** : le chiffrement garantit que même si quelqu'un vole les fichiers S3, il ne peut rien en faire sans la clé.

---

#### ✅ Étape 3 — Document de secours

**À faire par Claude** (30 min, inclus dans ce plan)

Créer un document `docs/procedure_urgence.md` qui liste :
- Les noms des secrets critiques (pas les valeurs, juste la liste : `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `TOKEN_ENCRYPTION_KEY`, etc.)
- La procédure si un secret a fuité (comment le révoquer et en générer un nouveau, service par service)
- Les contacts support de chaque service (liens et mails)
- La procédure complète "remonter Raya ailleurs si Railway tombe"


---

### 🟡 Priorité 2 — Ce mois-ci

#### ✅ Étape 4 — Préparer la bascule d'urgence (Dockerfile)

**À faire par Claude** (~3h de code)

Créer un **Dockerfile** — un emballage standard qui permet de déployer Raya sur **n'importe quel hébergeur** en 30 minutes :
- Render.com (alternative proche de Railway)
- Fly.io (gratuit jusqu'à un certain volume)
- OVH Cloud (français)
- AWS, Google Cloud, etc.

**Test obligatoire** : déployer Raya sur un 2e hébergeur (compte gratuit Render) au moins une fois, pour valider que ça marche vraiment. Sans ce test, le Dockerfile est juste du texte.

---

#### ✅ Étape 5 — Surveillance automatique (UptimeRobot)

**À faire par Guillaume** (10 min, inscription sur uptimerobot.com)

- Créer un compte **UptimeRobot** (gratuit)
- Ajouter un moniteur sur `https://app.raya-ia.fr/health` toutes les 5 min
- Configurer les alertes : SMS + email si Raya ne répond pas 2 fois de suite
- Ajouter le numéro de téléphone de Guillaume

Bonus : ajouter aussi un moniteur sur l'endpoint admin du tenant principal pour détecter les pannes applicatives (pas juste le serveur).

---

#### ✅ Étape 6 — Journal des actions admin renforcé

**À faire par Claude** (~2h de code)

Chaque action super-admin déjà loguée aujourd'hui. À enrichir avec :
- IP source de l'action
- User agent (type de navigateur)
- Géolocalisation approximative (ville/pays)
- Alerte immédiate (email + push dans Raya) si action admin vient d'une IP jamais vue OU d'un pays différent de la France

Exemple : si quelqu'un se connecte au compte admin Raya depuis Shanghai à 3h du matin → alerte Guillaume sur son téléphone immédiatement.

---

### 🟢 Priorité 3 — Plus tard

#### ✅ Étape 7 — Instance Raya de test (staging)

**À faire par Claude + Guillaume** (~2h)

Déployer une 2e copie de Raya sur Railway en environnement "dev". Cette instance sert à tester les grosses nouveautés **avant** de les pousser en production. Si une nouveauté casse quelque chose, elle casse le Raya de test, pas le vrai.

Base de données séparée, secrets séparés, URL séparée (`dev.raya-ia.fr` par exemple).

---

## 💰 Coûts mensuels totaux

| Poste | Coût |
|---|---|
| Amazon S3 (backups) | ~1€ |
| Backblaze B2 (backups redondance) | ~0.50€ |
| UptimeRobot (monitoring) | gratuit |
| OneDrive (3e backup) | gratuit (inclus M365) |
| Bitwarden (gestionnaire mots de passe) | gratuit |
| Authy (2FA) | gratuit |
| Render.com (secours) | gratuit jusqu'à un volume |
| Instance staging Railway | ~5€ |
| **TOTAL** | **~6.50€/mois** |

Pour protéger un outil qui vaut des milliers d'euros de travail + données clients + données société, c'est rien.


---

## 📋 Check-list globale à cocher au fur et à mesure

### Par Guillaume (doit être fait de ses mains)
- [ ] Installer Authy (ou équivalent) sur téléphone
- [ ] Installer Bitwarden sur téléphone et ordi
- [ ] Activer 2FA sur GitHub
- [ ] Activer 2FA sur Railway
- [ ] Activer 2FA sur OpenAI
- [ ] Activer 2FA sur Anthropic Console
- [ ] Activer 2FA sur Microsoft 365
- [ ] Activer 2FA sur Google (Gmail perso)
- [ ] Sauvegarder tous les codes de récupération dans Bitwarden
- [ ] Créer compte AWS S3 (donner clés à Claude)
- [ ] Créer compte Backblaze B2 (donner clés à Claude)
- [ ] Créer compte UptimeRobot + configurer moniteurs
- [ ] Tester une fois la bascule Dockerfile (avec Claude)

### Par Claude (code à livrer)
- [ ] Étape 2 — Code des sauvegardes automatiques vers S3 + B2 + OneDrive
- [ ] Étape 3 — `docs/procedure_urgence.md` avec la liste des secrets et procédures
- [ ] Étape 4 — Dockerfile standalone + doc de bascule
- [ ] Étape 6 — Audit logs renforcés (IP, user agent, géo, alertes)
- [ ] Étape 7 — 2FA sur compte admin Raya (TOTP)
- [ ] Étape 7 — Instance staging Raya

---

## 🎯 Ordre d'exécution recommandé

**Nuit du 20/04 (maintenant)** : ce document est créé et pushé. Rien d'autre ce soir.

**Matin 21/04** :
1. Guillaume active 2FA sur les 6 services (~45 min)
2. Guillaume crée comptes AWS S3 et Backblaze B2 (~15 min)
3. Guillaume donne les clés à Claude via le système de secrets Railway

**Après-midi 21/04** :
4. Claude code l'étape 2 (sauvegardes automatiques) — ~2h
5. Claude crée `docs/procedure_urgence.md` — ~30 min
6. Test de la première sauvegarde nocturne prévue pour la nuit suivante

**Semaine suivante** :
7. Claude livre le Dockerfile + test de bascule sur Render
8. Guillaume configure UptimeRobot
9. Claude livre audit logs renforcés

**Plus tard (au calme)** :
10. Instance staging + 2FA Raya admin

---

## 🔗 Docs liés

- `docs/vision_architecture_raya.md` — vision architecturale (ce qu'on veut construire)
- `docs/architecture_connexions.md` — modèle mental connexions
- `docs/procedure_urgence.md` — à créer en étape 3

## 📝 Historique des mises à jour

| Date | Modification |
|---|---|
| 20/04/2026 nuit | Création du document, validation du plan par Guillaume |
