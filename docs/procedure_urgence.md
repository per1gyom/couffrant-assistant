# 🚨 Procédure d'urgence Raya

> **À garder sous la main.** Document à consulter en cas d'incident
> majeur. Toutes les commandes sont validées et testées.
> 
> **Dernière mise à jour** : 29 avril 2026

## ⚡ Décision rapide selon l'incident

| Symptôme | Quoi faire | Section |
|---|---|---|
| app.raya-ia.fr ne répond plus (page blanche, 502) | Vérifier statut Railway | §1 |
| Login KO mais site charge | Logs Railway de l'app Saiyan | §2 |
| Données perdues / corrompues (un user signale un truc absurde) | Backup Railway → restore | §3 |
| Railway en panne complète plus de 2h | Plan B remontage ailleurs | §4 |
| Compte Railway / GitHub piraté | Plan C urgence absolue | §5 |
| Token de connexion (Gmail/Outlook) ne marche plus | §6 reset connexion |
| Secret leaké (ex. clé API postée publiquement) | §7 rotation secret |

## §1 — Site qui ne répond pas

1. Aller sur **railway.app** → projet Saiyan
2. Vérifier l'état du service `Saiyan` (l'app) :
   - Si **Crashed** ou **Failed Build** → onglet Deployments → cliquer
     sur le dernier déploiement → onglet Logs → lire l'erreur
   - Si **Building** ou **Deploying** depuis 5+ min → patience, sinon
     forcer un redeploy
3. Vérifier le service `Postgres` :
   - Si **Crashed** → support Railway via discord/help
4. Vérifier le statut Railway : **status.railway.app**
5. Si tout OK chez Railway et site KO → vérifier le DNS Cloudflare pour
   app.raya-ia.fr (rare)

## §2 — Login KO

1. Logs Railway service Saiyan : chercher `[Auth]`
2. Vérifier en DB si l'utilisateur existe :
   ```sql
   SELECT username, deleted_at, account_locked, login_locked_until
   FROM users WHERE username = '<login>';
   ```
3. Cas typiques :
   - `account_locked = true` → Guillaume reset via panel super_admin
   - `deleted_at IS NOT NULL` → user soft-supprimé, à restaurer si
     erreur (UPDATE users SET deleted_at=NULL WHERE username=...)
   - `login_locked_until > NOW()` → attendre la fin du timer ou reset
4. Si DB répond pas → §1

## §3 — Données perdues ou corrompues

**Procédure de restoration depuis backup Railway natif.**

1. Aller sur **railway.app** → projet Saiyan → service Postgres →
   onglet **Backups**
2. Choisir le backup à restaurer selon la date :
   - Pour un incident < 24h : Daily le plus récent
   - Pour un incident plus ancien : Weekly ou Monthly
3. ⚠️ **AVANT de cliquer Restore** : faire un backup MANUEL de l'état
   actuel (au cas où la restoration empire la situation, on pourra
   revenir en arrière)
4. Cliquer **Restore** sur la ligne du backup choisi
5. Confirmer
6. Railway crée un nouveau volume avec le contenu du backup, et
   réattache l'app dessus
7. **Vérifier après restoration** :
   - Login fonctionne (test : se connecter avec son compte)
   - Données récentes présentes (test : aria_memory récente, mails
     récents)
   - Les connexions Gmail/Outlook fonctionnent encore (sinon ré-OAuth
     via le panel admin)

🛑 La restoration coupe le service ~2-5 minutes le temps que Railway
réattache le volume.

## §4 — Railway en panne complète

Si Railway down > 2h sans communication ni ETA, plan B = remonter
ailleurs.

### Pré-requis

- Code : disponible sur **github.com/per1gyom/couffrant-assistant** →
  rien à faire, c'est intact
- DB : récupérer le **dernier backup externe chiffré** depuis
  OneDrive pro (chemin : `/Backups Raya/raya_backup_<date>.tar.gz.enc`)
- Clé : `BACKUP_ENCRYPTION_KEY` stockée dans la note Apple verrouillée
  de Guillaume

### Étapes

1. Créer un compte sur un hébergeur alternatif :
   - **Render.com** (recommandé, le plus proche de Railway)
   - **Fly.io** (gratuit jusqu'à un volume)
   - **OVH Cloud** (français, plus de paramétrage)
2. Connecter le repo GitHub (deploy auto)
3. Provisionner une base Postgres
4. Récupérer le backup externe sur le Mac de Guillaume
5. Déchiffrer le backup :
   ```bash
   openssl enc -d -aes-256-cbc -pbkdf2 \
     -in raya_backup_<date>.tar.gz.enc \
     -out raya_backup_<date>.tar.gz \
     -k <BACKUP_ENCRYPTION_KEY>
   tar -xzf raya_backup_<date>.tar.gz
   ```
6. Importer la DB :
   ```bash
   psql <NOUVELLE_DATABASE_URL> < raya_backup_<date>.sql
   ```
7. Restaurer les variables d'environnement (depuis le bundle
   `secrets.env` du backup) dans le nouveau service
8. Redémarrer l'app, vérifier que ça marche
9. Mettre à jour le DNS de **app.raya-ia.fr** pour pointer vers le
   nouvel hébergeur
10. Communiquer aux users que ça marche ailleurs maintenant

🛑 Cette procédure est **À TESTER au moins une fois** avant la prod
réelle. Sinon on découvre les bugs en pleine crise.

## §5 — Compte piraté (Railway, GitHub, Microsoft, Google)

**Procédure absolue d'urgence.**

### Si compte Railway piraté
1. Aller sur Railway → Account Security → **Révoquer toutes les
   sessions actives** + changer le mot de passe immédiatement
2. Vérifier que personne d'autre n'a un accès (Members, API tokens)
3. Vérifier que les services tournent toujours (le pirate peut avoir
   tout cassé)
4. **Vérifier que les variables d'environnement n'ont pas été
   modifiées** (DATABASE_URL surtout, peut être pointé vers une DB
   pirate)
5. Si dégâts détectés → §3 restoration depuis backup

### Si compte GitHub piraté
1. github.com/settings/security → Sessions → Sign out everywhere
2. Changer le mot de passe
3. Vérifier les commits récents (le pirate peut avoir poussé du code
   malicieux)
4. Si commit suspect → revert immédiat (`git revert <commit>` puis
   push)
5. Régénérer toutes les Personal Access Tokens

### Si compte Microsoft 365 piraté (guillaume@couffrant-solar.fr)
1. mysignins.microsoft.com → terminer toutes les sessions
2. Changer le mot de passe
3. Vérifier l'activité récente (mails envoyés, fichiers modifiés)
4. Vérifier les permissions OAuth tierces données
5. Révoquer les tokens Outlook côté Raya (panel admin → Connexions →
   Outlook Guillaume → Reconnecter)

### Dans tous les cas
- Faire un backup manuel Railway IMMÉDIATEMENT
- Activer 2FA partout (si pas déjà fait)
- Régénérer les secrets sensibles (§7)

## §6 — Reset d'une connexion Gmail / Outlook / Drive / Odoo

Quand un token expire ou que l'OAuth est cassé.

1. Aller sur **app.raya-ia.fr/admin/panel** (super_admin)
2. Onglet **Connexions** ou **Tenants**
3. Trouver la connexion concernée (Gmail Guillaume, Outlook contact@,
   etc.)
4. Cliquer **Déconnecter**
5. Cliquer **Reconnecter**
6. Suivre le flow OAuth
7. Vérifier que la connexion passe en **Connected** vert

Si l'OAuth échoue à plusieurs reprises :
- Vérifier que les `CLIENT_ID` / `CLIENT_SECRET` Microsoft sont
  toujours valides dans Railway
- Pour Gmail : vérifier que l'app Google Console n'est pas en
  "test mode" (limite à 100 utilisateurs)

## §7 — Rotation d'un secret

Si une clé API est leakée publiquement (ex. commit accidentel,
copie/colle dans un public Slack), il faut la régénérer
**immédiatement**.

### Identifier le secret leaké
- `OPENAI_API_KEY` → console.openai.com → API Keys → révoquer +
  recréer
- `ANTHROPIC_API_KEY` → console.anthropic.com → API Keys → idem
- `CLIENT_SECRET` Microsoft → portal.azure.com → App registrations →
  Certificates & secrets → New client secret
- `ENCRYPTION_KEY` → ⚠️ **CRITIQUE** : si rotation, tous les tokens
  OAuth en DB chiffrés avec l'ancienne clé deviennent inutilisables.
  Procédure spéciale : reset toutes les connexions oauth_tokens et
  redemander OAuth à tous les users
- `SESSION_SECRET` → générer une nouvelle valeur aléatoire (32+
  caractères), poser dans Railway env vars, redéployer (déconnecte tous
  les users)
- `BACKUP_ENCRYPTION_KEY` → ⚠️ générer la nouvelle, l'ajouter dans la
  note Apple verrouillée (en gardant l'ancienne 90 jours pour pouvoir
  déchiffrer les anciens backups). Mettre à jour Railway

### Mise à jour de la valeur
1. Aller sur Railway → projet Saiyan → service Saiyan → onglet
   Variables
2. Trouver la variable concernée → cliquer le pencil → coller la
   nouvelle valeur → Save
3. Railway redéploie automatiquement (~2 min)
4. Vérifier que ça marche : log d'app + test simple

### Logger l'incident
Créer un fichier `docs/incident_<date>_<sujet>.md` avec :
- Date et heure de la fuite
- Quel secret a fuité
- Comment c'est arrivé
- Date et heure de la rotation
- Vérifications effectuées (rien d'anormal en logs ?)

## 📞 Contacts support

| Service | Lien support | Mail |
|---|---|---|
| Railway | help@railway.app + discord.gg/railway | help@railway.app |
| GitHub | support.github.com | (depuis le compte) |
| Anthropic | support@anthropic.com | support@anthropic.com |
| OpenAI | help.openai.com | (chat depuis console) |
| Microsoft 365 | admin.microsoft.com → Help & Support | (depuis admin center) |
| Google Workspace | support.google.com | (depuis admin) |
| Cloudflare (DNS) | dash.cloudflare.com → Support | (depuis dashboard) |

## 🔐 Liste des secrets critiques

À titre indicatif, voici les secrets stockés dans Railway env vars (les
**valeurs** ne sont JAMAIS dans ce doc) :

| Variable | Rôle | Si perdue... |
|---|---|---|
| `DATABASE_URL` | Connexion Postgres | App ne démarre plus, mais DB intacte |
| `ENCRYPTION_KEY` | Chiffre tokens OAuth en DB | Toutes les connexions Gmail/Outlook/Drive cassent |
| `SESSION_SECRET` | Signe cookies session | Tous les users déconnectés (pas grave) |
| `OPENAI_API_KEY` | Embeddings + GPT | Plus de vectorisation, plus d'IA |
| `ANTHROPIC_API_KEY` | Claude | Plus de chat |
| `CLIENT_ID`, `CLIENT_SECRET`, `AUTHORITY` | OAuth Microsoft | Outlook, Drive Microsoft cassent |
| `SMTP_HOST`, `SMTP_USER`, `SMTP_PASS` | Envoi mails | Pas d'alertes mail |
| `APP_USERNAME`, `APP_PASSWORD` | Boot legacy | App ne démarre pas |
| `APP_BASE_URL` | URL canonical | Liens reset password cassés |
| `BACKUP_ENCRYPTION_KEY` (à venir) | Chiffre les backups externes | Backups inutilisables sans cette clé |

## 🗒️ Historique des incidents

| Date | Type | Résolution | Doc |
|---|---|---|---|
| (à compléter au fil de l'eau) | | | |
