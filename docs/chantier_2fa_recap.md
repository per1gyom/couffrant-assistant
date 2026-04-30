# 🔐 Chantier 2FA Niveau 2 — Récapitulatif complet

> **État** : ✅ **Production** au 30 avril 2026
> **Auteur** : Guillaume + Claude (sessions du 29-30 avril 2026)
> **Périmètre** : LOTs 0 à 6 déployés. LOT 7 = ce document. LOT 8 (WebAuthn / Face ID / Touch ID) reporté.

---

## 🎯 Pourquoi ce chantier

Avant : `/admin` et `/super_admin` accessibles avec un simple mot de passe. Risque majeur si un mot de passe est volé ou si une session est laissée ouverte.

Après : protection en plusieurs couches sans contraindre l'usage quotidien du chat.

---

## 🛡️ Modèle de sécurité — 3 niveaux

```
┌──────────────────────────────────────────────────────────────────┐
│  Niveau 1 — Connexion chat (/chat)                               │
│  → Mot de passe seul                                             │
│  → Tous les users (super_admin, tenant_admin, tenant_user)       │
│  → Aucun changement vs avant ce chantier                         │
└──────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────┐
│  Niveau 2 — Accès aux panels admin (/admin, /tenant/panel)       │
│  Réservé aux scopes super_admin et tenant_admin.                 │
│                                                                  │
│  2 vérifications cumulatives :                                   │
│                                                                  │
│  A) 2FA Authenticator hebdomadaire                              │
│     • Code TOTP à 6 chiffres (Google / Microsoft Authenticator)  │
│     • Validée 30 jours par appareil trusted (cookie + DB)        │
│     • Re-demandée si IP change de pays (GeoLite2)                │
│     • Re-demandée si cookie absent (mode privé, autre browser)   │
│                                                                  │
│  B) PIN court 4-6 chiffres                                       │
│     • Demandé à CHAQUE entrée dans le panel                      │
│     • Validité = tant que la fenêtre/onglet est ouverte          │
│     • 3 essais ratés → blocage 5min + escalade vers 2FA          │
│     • Différent du mot de passe et du code TOTP                  │
│                                                                  │
│  → Codes recovery (8 codes XXXXX-XXXXX) UNIQUEMENT super_admin   │
└──────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────┐
│  Niveau 3 — Actions critiques (LOT 5b, plus tard)                │
│  → 2FA redemandée juste avant l'action                           │
│  → Pour : purge user, suppression tenant, reset 2FA d'un autre   │
│  → Non implémenté pour l'instant                                 │
└──────────────────────────────────────────────────────────────────┘
```

---

## 🧩 Composants techniques

### Tables Postgres

| Table | Rôle | Colonnes clés |
|---|---|---|
| `users` (existante) | Stockage auth | + `totp_secret_encrypted`, `totp_enabled_at`, `recovery_codes_hashes` (jsonb), `recovery_codes_used_count`, `pin_hash`, `pin_attempts_count`, `pin_locked_until`, `pin_set_at` |
| `user_devices` (LOT 0) | Devices trusted 30j | `device_fingerprint` (UUID cookie), `country` (GeoLite2), `known_ips` (jsonb), `last_2fa_validated_at`, `expires_at` |
| `auth_events` (LOT 0) | Audit log auth | event_type, ip, user_agent, metadata jsonb |

### Modules Python

| Fichier | Rôle |
|---|---|
| `app/totp.py` | Génération secrets TOTP, vérification codes, gestion recovery codes (chiffrement Fernet) |
| `app/admin_2fa_session.py` | Helpers session 2FA admin (`needs_admin_2fa`, `mark_admin_2fa_validated`, grace period 7j) |
| `app/admin_pin.py` | Hash PIN, vérification, lockout après 3 échecs, validation format (refus PINs triviaux) |
| `app/device_fingerprint.py` | Cookie signé itsdangerous, persistance DB user_devices, check_device_trusted() |
| `app/geoip_lookup.py` | Lookup IP → pays via GeoLite2 (mode dégradé si base absente) |
| `app/auth_events.py` | Helper centralisé pour log_auth_event |

### Endpoints HTTP

| URL | Méthode | Rôle |
|---|---|---|
| `/admin/2fa/setup` | GET | Page setup 2FA + PIN (avec QR code, codes recovery, config PIN) |
| `/admin/2fa/setup/start` | POST | Génère secret TOTP + QR code |
| `/admin/2fa/setup/confirm` | POST | Valide premier code TOTP + active 2FA + génère 8 codes recovery |
| `/admin/2fa/regenerate-recovery` | POST | Régénère 8 nouveaux codes recovery (super_admin) |
| `/admin/2fa-challenge` | GET | Page de saisie code 2FA avant accès panel |
| `/admin/2fa-challenge` | POST | Valide code TOTP ou recovery, pose cookie device, redirect URL d'origine |
| `/admin/pin/status` | GET | État du PIN du user courant |
| `/admin/pin/setup` | POST | Configure ou change le PIN (4-6 chiffres) |
| `/admin/pin-challenge` | GET | Page de saisie PIN avant accès panel |
| `/admin/pin-challenge` | POST | Valide PIN, escalade vers 2FA après 3 échecs |
| `/admin/pin/unlock-via-2fa` | POST | Débloque PIN après échecs en validant 2FA + nouveau PIN |
| `/admin/users/{u}/2fa-status` | GET | État 2FA d'un autre user (super_admin uniquement) |
| `/admin/users/{u}/reset-2fa` | POST | Reset complet 2FA + PIN + devices (super_admin) |
| `/admin/users/{u}/reset-pin` | POST | Reset PIN seul (super_admin) |
| `/admin/users/{u}/reset-trusted-devices` | POST | Vide devices trusted (super_admin) |

### Guards FastAPI

| Guard | Rôle |
|---|---|
| `require_user` | Authentification basique (session) |
| `require_admin` | Scope admin/super_admin (pour API JSON) |
| `require_super_admin` | Scope super_admin uniquement |
| `require_tenant_admin` | Scope tenant_admin (ou supérieur) |
| `require_admin_2fa_validated` (LOT 3-5) | Pour pages HTML : vérifie 2FA + device + PIN. Lance HTTPException(303) → redirect via exception_handler |

---

## 📋 Workflow utilisateur

### 1ère fois après activation du chantier (cas Guillaume au 30/04)

```
1. Login normal sur /chat (mot de passe)
   → Pas de changement, accès chat OK

2. Click sur "Admin"
   → Redirect /admin/2fa/setup (grace period 7j active)
   → Setup 2FA :
     • Scan QR avec Google/Microsoft Authenticator
     • Tape un code TOTP pour valider
     • Sauvegarde des 8 codes recovery (super_admin only)
   → Setup PIN (bloc en bas de la page) :
     • Choix d'un PIN 4-6 chiffres
     • Confirmation par /admin/pin/setup

3. Retour sur /admin/panel
   → Cookie device posé (trusted 30j)
   → Session 2FA validée
   → Accès au panel
```

### Quotidien (après setup)

```
1. Login chat (mot de passe seul, comme avant)

2. Click sur "Admin"
   → check_device_trusted : cookie OK + IP/pays match → skip 2FA
   → Mais PIN demandé (à chaque entrée tant que session active)
   → Tape le PIN → accès panel

3. Tant que la fenêtre est ouverte
   → Aller-retours panel/chat sans re-saisir le PIN

4. Fermeture de l'onglet
   → Au retour : PIN redemandé
```

### Cas exceptionnels

#### Téléphone perdu (super_admin)
- Login normal
- Sur la page 2FA challenge : tape un des 8 codes recovery `XXXXX-XXXXX`
- Le code est consommé (7 restants)
- Accès au panel → opportunité de regénérer 8 nouveaux codes

#### Téléphone perdu (tenant_admin Charlotte)
- Charlotte n'a pas de codes recovery (pas configurés pour ce scope)
- Charlotte contacte Guillaume (super_admin)
- Guillaume va dans /admin → onglet Utilisateurs → bouton 🔐 sur Charlotte → "Reset COMPLET 2FA" + raison
- Charlotte se reconnecte → nouvelle grace period 7j → reactive sa 2FA

#### PIN oublié
- Tape 3 fois un mauvais PIN sur /admin/pin-challenge
- Page de déblocage 2FA s'affiche
- Tape un code TOTP + un nouveau PIN → débloqué

#### Voyage / VPN (changement de pays)
- Cookie device présent mais GeoLite2 détecte un autre pays
- check_device_trusted retourne `country_changed`
- 2FA redemandée
- Après validation : device mis à jour avec le nouveau pays

---

## 🚨 Filet d'urgence : `DISABLE_2FA_ENFORCEMENT`

Si bug bloquant après déploiement :

1. Aller sur Railway → Saiyan → Variables
2. Ajouter `DISABLE_2FA_ENFORCEMENT=true`
3. Sauvegarde → redéploiement automatique (~2 min)
4. Tous les checks 2FA + device + PIN sont bypassés
5. Login admin redevient password-only le temps de fixer le bug
6. **Une fois le bug fixé** : retirer la variable (ou mettre à `false`)

🛑 **À utiliser UNIQUEMENT en cas d'urgence**. Variable lue dynamiquement à chaque requête, pas besoin de restart manuel.

---

## 📊 Plan global du chantier

| LOT | Nom | Statut | Commit | Effort réel |
|---|---|---|---|---|
| 0 | Migrations DB + helper auth_events | ✅ | `774ddb2` | 1h30 |
| 1 | Module `app/totp.py` | ✅ | `c60f093` | 2h |
| 2 | Endpoints setup 2FA + page HTML | ✅ | `ec3a4b4` | 2h30 |
| 3 | Login flow 2 étapes (challenge) | ✅ | `90acaec` + hotfix `ba546dd` | 1h45 |
| 4 | Device trusted 30j + GeoLite2 | ✅ | `c3d13d6` | 2h |
| 5 | PIN admin 4-6 chiffres | ✅ | `4c31473` | 1h45 |
| 6 | Reset 2FA/PIN/devices par super_admin | ✅ | `435dd55` | 45min |
| 7 | Tests + documentation | ✅ | (LOT en cours) | 45min |
| 8 | WebAuthn / Face ID / Touch ID | 💡 reporté | - | 10-15h estimés |
| 5b | 2FA pour actions critiques | ⏭️ futur | - | 1h estimé |

**Total ~12h** sur 2 sessions (29 et 30 avril 2026).

---

## 🧪 Tests bout-en-bout réalisés

### Tests sur compte Guillaume (super_admin) — 30/04/2026

| Test | Résultat |
|---|---|
| Activation 2FA via Google Authenticator | ✅ |
| Génération de 8 codes recovery | ✅ |
| Première saisie code TOTP au challenge | ✅ |
| Pose du cookie device + entrée user_devices DB | ✅ |
| GeoLite2 détecte la France (FR) sur IP 109.209.101.3 | ✅ |
| Setup PIN 4-6 chiffres | ✅ |
| Refus des PINs triviaux (1234, 0000) | ✅ |
| PIN demandé à chaque entrée /admin | ✅ |
| Skip 2FA après cookie trusted (déconnexion/reconnexion) | ✅ |
| Bouton 🔐 dans onglet Utilisateurs | ✅ |
| Endpoint GET /admin/users/{u}/2fa-status | ✅ |

### Tests à faire (LOT 7 ou plus tard)

- [ ] Test code recovery (XXXXX-XXXXX) après "perte" du téléphone
- [ ] Test échec 3× PIN → blocage → déblocage via 2FA + nouveau PIN
- [ ] Test reset 2FA d'un autre user (Charlotte) par super_admin
- [ ] Test changement de pays simulé (via VPN ou modif manuelle DB)
- [ ] Test grace period 7j pour Charlotte
- [ ] Test env var DISABLE_2FA_ENFORCEMENT (mise à true puis false)

---

## 📝 Notes pour onboarder un nouveau tenant_admin

Quand tu vendras Raya à un nouveau tenant et que son tenant_admin se connectera pour la première fois :

```
J1 (création compte par toi) :
  • Tu crées le compte avec le scope tenant_admin
  • Tu lui envoies ses identifiants (login + mot de passe initial)

J2 (1ère connexion du tenant_admin) :
  • Il se connecte avec son mot de passe → forced reset password
  • Il définit son nouveau mot de passe
  • Il accède à /chat normalement (Niveau 1)

J3-7 (grace period 7 jours) :
  • S'il clique sur "Admin" : redirect vers /admin/2fa/setup
  • Page affiche un warning "configurer ta 2FA dans X jours"
  • Il a 7 jours pour activer sa 2FA
  • S'il configure sa 2FA dans cette fenêtre : tout marche
  • S'il ne fait rien dans 7 jours : grace expire → /admin/2fa/setup?required=1 bloquant

J8+ (régime normal) :
  • 2FA Google Authenticator obligatoire pour entrer dans /admin
  • PIN 4-6 chiffres demandé à chaque ouverture d'onglet admin
  • Validité 30 jours sur appareil trusted (sauf changement de pays)
```

🛑 **Charlotte (juillet)** : sa grace period a été reset au 30/04. Elle a jusqu'au **7 mai 2026** pour activer sa 2FA si elle veut accéder au panel admin.

---

## 🔮 Évolutions futures envisageables

### LOT 8 — WebAuthn (Face ID / Touch ID / Windows Hello)
- Remplace le PIN par la biométrie quand l'appareil supporte
- Plus rapide (1 sec au lieu de saisir 4-6 chiffres)
- Plus sécurisé (biométrie non clonable à distance)
- ⚠️ Conserve le PIN en backup obligatoire
- Effort estimé : 10-15h

### LOT 5b — 2FA pour actions critiques
- Re-demande un code 2FA juste avant les actions irréversibles :
  - Purge définitive d'un user
  - Suppression d'un tenant
  - Reset 2FA d'un autre user (déjà demandé par les endpoints, on rajoute une re-validation)
  - Changement de mot de passe
- Pattern : décorateur `@require_recent_2fa_step_up(max_age_seconds=300)`
- Effort estimé : 1h

### Audit / monitoring
- Dashboard `/admin/auth-events` pour visualiser les événements d'auth (échecs, succès, devices)
- Alerte par mail au super_admin en cas de 5+ échecs 2FA en 1h pour un user
- Effort estimé : 2-3h

### Notification au reset
- Quand un super_admin reset la 2FA d'un user, envoyer un email à ce user pour l'informer
- Même pattern que les notifs de password reset
- Effort estimé : 30 min

---

## 🧠 Décisions structurelles prises

### Pourquoi 2FA Authenticator + PIN (et pas juste l'un ou l'autre)

- **2FA seule** : trop contraignant à chaque entrée admin, mais top sécurité initiale
- **PIN seul** : trop faible (4-6 chiffres = 10 000 combinaisons max), peut être brute-forcé
- **2FA + PIN** : l'union des deux donne une sécurité élevée + une UX confortable
  - 2FA bloque les attaques distantes (compte volé)
  - PIN bloque les sessions laissées ouvertes (attaque locale)

### Pourquoi 30 jours de validité device

- Standard SaaS (Google, GitHub, Microsoft = 30 jours)
- Compromis sécurité/UX : assez long pour pas être chiant, assez court pour limiter l'exposition
- Reset automatique si pays change (GeoLite2)

### Pourquoi GeoLite2 plutôt qu'API externe

- Pas de dépendance réseau au login (latence + risque de panne)
- Gratuit, illimité, hors-ligne
- Compromis : ~70 MB dans l'image Docker
- Mode dégradé si la base n'est pas téléchargée (l'app marche sans détection pays)

### Pourquoi pas de codes recovery pour tenant_admin

- Décision Guillaume : un tenant_admin perd son téléphone → contacte le super_admin → reset
- Évite la complexité de devoir gérer/retrouver les codes pour des dizaines de tenant_admins
- Le super_admin (toi) reste le point de récupération unique pour tous les tenants

### Pourquoi le PIN est validé tant que la fenêtre est ouverte

- Cookie de session starlette = max 24h (configuré dans main.py)
- Cas réel visé : "ferme l'onglet sans déconnexion" → PIN redemandé
- Plus strict que les bancaires (qui valident 5-15 min) car le compromis pour Raya est différent (pas d'argent direct, mais accès admin)

---

## 🏗️ Architecture des dépendances

```
require_admin_2fa_validated() — guard FastAPI

  ├─ require_user() ─────────────────────── 401 si pas connecté
  │
  ├─ scope check ────────────────────────── 403 si pas admin/super_admin/tenant_admin
  │
  ├─ DISABLE_2FA_ENFORCEMENT? ──────── BYPASS si env var = true
  │
  ├─ has_user_activated_2fa()
  │   ├─ Non + grace 7j active ─────────── pass through (warning UI)
  │   └─ Non + grace expirée ───────────── redirect /admin/2fa/setup?required=1
  │
  ├─ needs_admin_2fa() (validation < 7j ?)
  │   ├─ check_device_trusted() ────────── trusted_match → skip 2FA
  │   │                                    country_changed → redirect /2fa-challenge
  │   │                                    no_cookie → redirect /2fa-challenge
  │   └─ session.admin_2fa_validated_at < 7j → skip
  │
  └─ has_pin_set()
      ├─ Non ───────────────────────────── redirect /admin/2fa/setup?need_pin=1
      └─ Oui + is_pin_validated_in_session()? Non → redirect /admin/pin-challenge
```

---

## 📂 Fichiers clés du chantier (récap)

| Fichier | Lignes | Rôle |
|---|---|---|
| `app/totp.py` | 238 | TOTP RFC 6238 + recovery codes |
| `app/admin_2fa_session.py` | 190 | Helpers session 2FA admin |
| `app/admin_pin.py` | 369 | Module PIN 4-6 chiffres |
| `app/auth_events.py` | 147 | Helper log auth_events |
| `app/crypto_backup.py` | - | Module Fernet pour backups |
| `app/device_fingerprint.py` | 396 | Cookie + DB device trusted 30j |
| `app/geoip_lookup.py` | 130 | Lookup IP → pays GeoLite2 |
| `app/routes/two_factor.py` | ~700 | Endpoints setup 2FA + page HTML |
| `app/routes/admin_2fa_challenge.py` | ~390 | Challenge 2FA |
| `app/routes/admin_pin_routes.py` | 491 | Endpoints PIN |
| `app/routes/admin_2fa_management.py` | 410 | Endpoints reset par super_admin |
| `app/static/admin-2fa-mgmt.js` | 200 | UI gestion 2FA d'autres users |
| `app/routes/deps.py` | ~225 | Guards FastAPI |
| `app/main.py` | - | exception_handler 303 + routers |
| `Dockerfile` | 117 | + étape GeoLite2 download |
| `requirements.txt` | - | + pyotp, qrcode[pil], geoip2 |

---

## 🔑 Variables Railway critiques

| Variable | Rôle |
|---|---|
| `DATABASE_URL` | Postgres prod |
| `SESSION_SECRET` | Sign cookies starlette + device fingerprint |
| `TOKEN_ENCRYPTION_KEY` | Fernet pour OAuth tokens + secrets TOTP |
| `BACKUP_ENCRYPTION_KEY` | Fernet backups Drive |
| `MAXMIND_LICENSE_KEY` | Clé GeoLite2 (téléchargement au build) |
| `DISABLE_2FA_ENFORCEMENT` | Filet d'urgence (NE PAS DÉFINIR sauf bug bloquant) |

---

## 📞 Procédure d'urgence

### Tu es bloqué hors du panel admin
1. Si tu as encore tes 8 codes recovery → utilise-les sur la page challenge
2. Si tu as perdu codes + téléphone → SSH/Railway shell + SQL :
   ```sql
   UPDATE users SET totp_enabled_at = NULL, totp_secret_encrypted = NULL,
                    pin_hash = NULL, pin_attempts_count = 0, pin_locked_until = NULL
   WHERE username = 'guillaume';
   DELETE FROM user_devices WHERE username = 'guillaume';
   ```
3. Reconnexion → grace period te laisse passer → reactive ta 2FA

### Bug bloquant après déploiement
1. Railway → Saiyan → Variables
2. Ajout `DISABLE_2FA_ENFORCEMENT=true`
3. Save → redéploie en ~2 min
4. Login admin redevient password-only
5. Une fois le bug fixé : retire la variable

### Pour Charlotte (ou autre tenant_admin) qui perd son téléphone
1. Toi (super_admin) → /admin → onglet Utilisateurs
2. Click bouton 🔐 sur sa ligne → modal "Gérer 2FA"
3. Click "🔥 Reset COMPLET 2FA"
4. Saisis la raison (ex: "telephone perdu - Charlotte 30/04")
5. Confirme → sa 2FA est reset, ses devices sont vidés
6. Charlotte se reconnecte → grace 7j → reactive sa 2FA depuis zéro

---

*Document maintenu par Guillaume + Claude. Dernière mise à jour : 30 avril 2026, 20h.*
