# LOT 2 du chantier 2FA — Récap nocturne (30 avril 2026, ~01h00)

> Document écrit pour Guillaume **pendant qu'il dort**, à lire au réveil
> avant d'attaquer le LOT 3.

---

## ✅ Ce qui a été fait pendant la nuit

### Commits poussés (3 commits dans la nuit du 29→30/04)

| Commit | Sujet | Fichiers | Lignes |
|---|---|---|---|
| `774ddb2` | LOT 0 — deps + migration DB | requirements.txt + database_migrations.py | +73 |
| `c60f093` | LOT 1 — module `app/totp.py` | app/totp.py | +238 |
| `ec3a4b4` | LOT 2 — endpoints setup 2FA | auth_events.py + routes/two_factor.py + main.py | +837 |

### Etat actuel en prod

🟢 App online, /health = 200 (0,1s)
🟢 6 nouveaux endpoints enregistrés sous `/admin/2fa/`
🟢 4 nouvelles colonnes 2FA sur table `users` (vides pour tous les users)
🟢 Tables `user_devices` et `auth_events` créées (vides)
🟢 Aucun user n'est forcé à activer la 2FA pour l'instant — c'est LOT 3

---

## 🧪 Comment tester ce qui a été fait (5 min, optionnel)

### 1. Aller sur la page de setup

🌐 https://app.raya-ia.fr/admin/2fa/setup

Tu seras connecté automatiquement (cookie session). La page affiche :
- Ton statut 2FA actuel (non activée)
- Un bouton "Démarrer l'activation"

### 2. Cliquer sur "Démarrer l'activation"

→ génère un secret TOTP, affiche un QR code + le secret en texte

### 3. Scanner le QR avec Microsoft Authenticator (ou autre)

Tu dois déjà avoir l'app installée pour les 2FA externes (GitHub, Railway, Google).

→ l'app affiche un code à 6 chiffres qui change toutes les 30s

### 4. Taper le code → "Valider"

→ Si OK, **8 codes de récupération** s'affichent UNE SEULE FOIS dans une grille
→ Bouton "Copier les 8 codes" → les coller dans **Bitwarden** ou ta note Apple verrouillée

### 5. Vérification en DB

```sql
SELECT username, totp_enabled_at, recovery_codes_used_count
FROM users WHERE username = 'guillaume';
```

Tu devrais voir `totp_enabled_at = <timestamp>` et `recovery_codes_used_count = 0`.

### ⚠️ Important si tu testes maintenant

🛑 **Si tu actives la 2FA maintenant, ça n'aura AUCUN effet sur ton login** —
tant que LOT 3 n'est pas fait, le login reste password seul.

🛑 **Mais** : tu auras quand même tes 8 codes recovery sauvegardés et la 2FA
prête à s'activer dès que LOT 3 sera déployé.

---

## 🛡️ Sécurité — vérifs qu'on a faites

### Pendant le setup

- ✅ Secret base32 stocké en **session uniquement** pendant 10 min max
  - Si abandon ou expiration : secret part avec la session, jamais en DB
- ✅ Session signée + chiffrée par starlette via `SESSION_SECRET`
- ✅ Validation du 1er code TOTP avant activation définitive (anti-typo)
- ✅ Refus dur si `TOKEN_ENCRYPTION_KEY` absente (durcissement 2FA spécifique)

### Stockage final

- ✅ Secret TOTP chiffré avec **Fernet** (TOKEN_ENCRYPTION_KEY déjà en prod)
- ✅ 8 codes recovery hashés avec **pbkdf2-sha256 100k iter + salt 16 bytes**
  (même pattern que les passwords)
- ✅ Comparaison via `hmac.compare_digest` (résistant timing)
- ✅ Codes recovery **uniquement affichés à la création** — jamais relus en clair

### Audit log

Chaque action écrit dans la table `auth_events` :
- `2fa_setup_started`
- `2fa_setup_completed`
- `2fa_setup_failed` (avec metadata `{reason: "invalid_code"}`)
- `recovery_codes_regenerated`

Pour voir l'historique :
```sql
SELECT event_type, ip, created_at FROM auth_events
WHERE username = 'guillaume' ORDER BY created_at DESC LIMIT 20;
```

---

## 📋 Endpoints créés (récap)

| Méthode | URL | Auth | Rôle |
|---|---|---|---|
| GET | `/admin/2fa/status` | require_user | État 2FA + grace period |
| GET | `/admin/2fa/setup` | require_admin | Page HTML d'activation |
| POST | `/admin/2fa/setup/start` | require_admin | Génère QR code |
| POST | `/admin/2fa/setup/verify` | require_admin | Valide + active 2FA |
| POST | `/admin/2fa/setup/cancel` | require_admin | Annule setup en cours |
| POST | `/admin/2fa/recovery-codes/regenerate` | require_admin | Régénère 8 codes |

🛑 `require_admin` = super_admin OU admin OU tenant_admin (donc Guillaume + Charlotte y ont accès, mais pas Pierre/Sabrina/Benoît/Arlène).

🛑 `require_user` = tout user connecté (donc tout le monde peut voir son propre `status`).

---

## 🎨 Décisions actées dans le code (Q1-Q7)

| Q | Décision | Implémentation LOT 2 |
|---|---|---|
| Q1 | super_admin + tenant_admin | `SCOPES_REQUIRING_2FA = ('super_admin', 'admin', 'tenant_admin')` |
| Q2 | 8 codes recovery | `generate_recovery_codes(8)` |
| Q3 | 7j période de grâce | `GRACE_PERIOD_DAYS = 7` (calculée mais pas encore appliquée) |
| Q5 | Fenêtre TOTP ±1 cycle = ±90s | `TOTP_VERIFY_WINDOW = 1` dans `app/totp.py` |
| Q6 | 4h /admin, 1h /super_admin | À implémenter au LOT 5 (step-up) |
| Q7 | 4 déclencheurs re-2FA | À implémenter aux LOTs 4-5 |

---

## ⏭️ Ce qu'il reste à faire (LOTs 3-7)

### 🔴 LOT 3 — Le plus sensible (~1h)

Modifier `/login-app` pour qu'il devienne un flow en 2 étapes :
1. Étape 1 : password (déjà OK)
2. Étape 2 : si user a `totp_enabled_at IS NOT NULL` ET (pas de device trusted OU IP nouvelle), demander un code TOTP avant de créer la session.

**Pourquoi sensible** : ça touche le login, donc TOUS les users. Si bug → lock-out.

**Stratégie** : tester d'abord sur **pierre_test** (créer un compte dédié avec 2FA activée), valider le flow bout-en-bout, puis seulement ensuite tu actives ta propre 2FA.

### 🟡 LOT 4 — Device fingerprinting (~1h)

Cookie persistant `raya_device_id` (UUID signé). Si l'appareil + IP sont connus depuis < 30j, on skippe la 2FA au login (Q3=B `last_2fa_validated_at`).

### 🟡 LOT 5 — Step-up auth (~1h)

Décorateur `require_recent_2fa(window_minutes=5)` à appliquer sur les actions sensibles : delete user, promote, delete connection, force-purge, etc. Ces actions redemandent un code TOTP même si le user est connecté.

Aussi : durée de session différenciée (4h sur /admin, 1h sur /super_admin) — Q6=B.

### 🟢 LOT 6 — Reset 2FA par super_admin (~30 min)

Endpoint `POST /admin/2fa/disable/<username>` (super_admin only). Permet de désactiver la 2FA d'un user qui a perdu son téléphone ET ses codes recovery.

### 🟢 LOT 7 — Tests + doc (~45 min)

Plan de tests bout-en-bout sur **pierre_test** :
1. pierre_test active sa 2FA depuis device A
2. pierre_test se déconnecte → reconnecte depuis device A → skip 2FA (device trusted)
3. pierre_test se reconnecte depuis device B → demande 2FA
4. pierre_test perd son téléphone → utilise un code recovery
5. pierre_test demande un reset à guillaume → guillaume désactive sa 2FA

---

## ⚠️ Points d'attention pour LOT 3 (à faire frais)

### 1. Pas de lock-out

Avant de toucher au login, garder une route alternative pour récupérer un compte si la 2FA bug. **Suggestion** : laisser une env var `DISABLE_2FA_ENFORCEMENT=true` qui désactive temporairement la vérif 2FA. À supprimer une fois LOT 3 stabilisé.

### 2. Tester sur pierre_test, PAS sur ton compte

D'abord créer un compte test dédié avec 2FA, valider tout, et seulement après activer sur ton compte.

### 3. Période de grâce

Le code calcule déjà `grace_active`. Décision à confirmer : pendant la grâce, soit
(A) on demande pas de 2FA mais on affiche un warning à chaque login,
(B) on demande pas et on ignore tout,
(C) on demande mais on tolère le skip.

Mon avis : **A** — warning à chaque login pendant les 7j, puis blocage. Modèle SaaS classique.

### 4. Charlotte (juillet, tenant_admin) a un compte ancien

`Charlotte` a été créée le ~25/04 ou avant. Sa période de grâce est probablement déjà expirée. Si le LOT 3 force la 2FA brutalement, elle se retrouve lockée. **Suggestion** : faire un **reset de la grace period** pour les comptes existants au moment du déploiement LOT 3, en mettant `users.created_at` artificiellement à NOW() pour les tenant_admin existants.

### 5. La page setup est volontairement minimaliste

Pas de styling Raya, pas de logo, pas de menu. C'est juste la page fonctionnelle. Si tu veux qu'elle ait l'apparence du reste du panel, c'est facile à faire en LOT 7.

---

## 🛌 Repose-toi bien

Tu as fait du bon boulot ce soir :
- ✅ 13 commits backups + Phase 2 Drive validée bout-en-bout
- ✅ 3 commits LOTs 0-2 du chantier 2FA
- ✅ Procédure d'urgence documentée
- ✅ Reclarification du modèle commercial (économise ~4j de roadmap)

À demain pour LOT 3 (le plus délicat). 🌙

---

*Document écrit par Claude pendant la nuit du 29 au 30 avril 2026 (~01h00 UTC).*
