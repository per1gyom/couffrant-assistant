# Raya — État de session vivant

**Dernière mise à jour : 16/04/2026 20h00** — Opus

---

## ⚠️ RÈGLES IMPÉRATIVES

### Rôles
- **Opus = architecte + codeur direct** via Desktop Commander (git local) ou MCP GitHub
- **Sonnet** : exécutant pour gros refactoring via git terminal (prompts préparés par Opus)
- **Guillaume = décideur** : valide, teste. Opus explique AVANT de coder. Guillaume valide, puis Opus exécute.

### Règles techniques
- Fichiers Python < 10KB (sauf database_schema.py, database_migrations.py, tools_seed_data.py = données pures)
- Desktop Commander local path : `/Users/per1guillaume/couffrant-assistant`
- Template chat : `app/templates/raya_chat.html`
- Cache-bust : `?v=12` (actuel)
- Français, vocabulaire Terminal, concis
- Git config local : `per1guillaume@mac-1.home`
- **⚠️ ARCHITECTURE ADMIN** : Les routes admin sont dans le **package** `app/routes/admin/` (pas le fichier `admin.py` qui est shadowed). Toute nouvelle route admin doit être ajoutée dans `super_admin.py`, `tenant_admin.py` ou `profile.py`.

---

## ⭐ ÂME DU PROJET
Raya = cerveau supplémentaire pour dirigeant. LLM-agnostic, tools-agnostic, channel-agnostic.

## 1. Stack
FastAPI Python 3.13, Railway, PostgreSQL+pgvector, Anthropic 3 tiers, OpenAI embeddings.
URL : `https://app.raya-ia.fr` — Repo : `per1gyom/couffrant-assistant` branche `main`

## 2-9. INFRASTRUCTURE ✅
Connectivité 5/5, Outils création (PDF, Excel, DALL-E), PWA v=12, Sécurité (anti-injection, GUARDRAILS, CSP, bcrypt, lockout), Signature email v2, SAV/Bug report, RGPD complet, Backup manuel.

## 10. UX CHAT ✅
Nettoyage actions brutes, horodatage messages, style conversationnel naturel (UX-TONE), 👍 confirme pending, bug report commentaire optionnel, DELETE/ARCHIVE mutuellement exclusifs, nettoyage fragments Odoo inline.

## 11. TOPICS ✅
5 endpoints CRUD + PWA (bouton 🔖 dans header + panneau latéral `chat-topics.js`) + RGPD couvert + Flutter prêt (TopicsService à switcher vers API).

## 12. REFACTORING ARCHITECTURE ✅ (COMPLET)
30+ splits Python — tous les fichiers Python < 10KB. 6 hotfixes imports circulaires (HOTFIX-1 à HOTFIX-6). CSS splitté en 3 fichiers (chat-base.css + chat-components.css + chat-drawer.css). Admin panel splitté (admin-panel.css + admin-panel.js extraits). 8 fichiers morts supprimés.

**⚠️ Package admin/** : Le refactoring du 12/04 a créé `app/routes/admin/` (package) qui shadow `app/routes/admin.py` (fichier). Les routes ajoutées dans `admin.py` après le 12/04 étaient mortes en prod jusqu'au fix du 16/04. Toutes les routes sont maintenant dans le package : `super_admin.py`, `super_admin_users.py`, `super_admin_system.py`, `tenant_admin.py`, `profile.py`.

## 13. MULTI-TENANT ✅
- Tenant `couffrant_solar` : Guillaume (super_admin) — 5 utilisateurs
- Tenant `juillet` : Charlotte (tenant_admin) — créé le 15/04, testable

## 14. PANEL ADMIN — REFONTE ✅
### Création société
- Nom → ID auto-généré (normalisé), SIRET obligatoire (14 chiffres), adresse 3 champs (rue/CP/ville), forme juridique (dropdown), fournisseur email configurable.

### Création utilisateur
- Formulaire avec sélecteur société + profil métier (8 profils). Bouton "➕ Ajouter un collaborateur" dans chaque fiche. Seeding auto après création.

### Double confirmation suppressions
- Société : modale → champ "Tapez SUPPRIMER" → bouton grisé. User : modale → champ "Tapez le nom".

### Accès panel par rôle
- Super admin : voit tous les onglets (Mémoire, Utilisateurs, Règles, Insights, Actions, Sociétés, Profil)
- Tenant admin : voit seulement Sociétés (sa société) + Mon profil. Onglets super-admin masqués.
- 2 boutons dans le header du chat : `🔑 Super Admin` (super admin uniquement) + `⚙️ Ma société` (admin + tenant_admin)

### Re-authentification admin (SECURITY) ✅
- Accès au panel protégé par **re-saisie du mot de passe** même si la session web est active
- Timeout : **10 minutes** (`ADMIN_AUTH_TIMEOUT = 600`). Après expiration → re-saisie obligatoire
- Page de login admin dédiée (design dark, formulaire simple)
- Endpoint `POST /admin/auth` : vérifie le mot de passe, écrit `admin_auth_at` en session
- Protection contre les sessions laissées ouvertes : personne ne peut accéder au panel sans le mot de passe

## 15. SUSPENSION DE COMPTES ✅
- `app/suspension.py` : check_suspension(), suspend_user(), unsuspend_user(), suspend_tenant(), unsuspend_tenant()
- **Migration DB exécutée le 16/04** : colonnes `suspended BOOLEAN` + `suspended_reason TEXT` sur table users
- Tenants : `suspended` + `suspended_reason` dans le JSONB `settings`
- Vérification au login web (`auth.py`) + tous les endpoints API (`deps.py`) : HTTP 403
- Super admin : suspend n'importe quel user ou tenant. Tenant admin : suspend users de sa société.
- Panel admin : boutons ⏸️ / ▶️ par utilisateur + par société. Badges ⏸️ SUSPENDU.
- **Feedback** : alertes dirigées vers l'onglet actif (companies-alert ou user-alert). Cartes sociétés restent ouvertes après action.

## 16. ACTIONS DIRECTES (FICHIERS) ✅
- `app/direct_actions.py` : priorité user override > tenant setting > défaut (False)
- Par défaut OFF. Corbeille mail reste en action directe (récupérable).
- **Changement de spec (16/04)** : cette fonction est réservée au **tenant_admin** (pas au super admin)
- Toggle par société : 🟢 ON / 🔴 OFF visible dans la fiche société (uniquement pour tenant admin)
- Toggle par utilisateur : bouton 📂 ON / 📂 OFF / 📂 = (hérité) avec cycle au clic (`cycleUserDirectActions`)
- Le super admin ne voit **plus** le toggle actions directes dans sa vue sociétés

## 17. CLOISONNEMENT ✅
### Drive
- `drive_connector.py` : défauts neutres, plus de fallback vers Couffrant Solar. Lazy `__getattr__` (HOTFIX-5).

### OAuth (FIX-CRITICAL 16/04)
- **Avant** : `request.session.get("user", "guillaume")` dans les callbacks OAuth Microsoft ET Gmail → si session vide, token sauvé sous Guillaume
- **Après** : Session vide → page d'erreur 401 "Session expirée" avec lien de reconnexion. Aucun fallback.
- Charlotte confirmée : aucun `oauth_token` hérité en DB. Ses connexions Microsoft/Gmail sont vierges (à configurer).

## 18. SEEDING PROFILS (DEMO uniquement)
8 profils dans `app/seeding.py`. Endpoint `POST /admin/seed-user`. Bouton 🌱 par utilisateur.
DÉCISION : seeding = DEMO. Vrais clients → questionnaire admin + questionnaire utilisateur (à coder).

## 19. MATRICE DES DROITS (MISE À JOUR 16/04)
| Fonctionnalité | Super Admin | Admin Tenant | Utilisateur |
|---|---|---|---|
| Voir toutes les sociétés | ✅ | ❌ (que la sienne) | ❌ |
| Créer/Supprimer société | ✅ | ❌ | ❌ |
| Suspendre société | ✅ | ❌ | ❌ |
| Suspendre utilisateur | ✅ (tous) | ✅ (sa société) | ❌ |
| Créer/Supprimer utilisateur | ✅ (tous) | ✅ (sa société) | ❌ |
| Toggle actions directes | ❌ (retiré) | ✅ (sa société) | ❌ |
| Seeder un profil | ✅ | ✅ (sa société) | ❌ |
| Chat Raya | ✅ | ✅ | ✅ |
| Tiroir admin chat | ✅ (complet) | ✅ (connexions + onboarding) | ❌ (masqué) |
| Panel admin (🔑 Super Admin) | ✅ (tous les onglets) | ❌ | ❌ |
| Panel admin (⚙️ Ma société) | ✅ (sa société) | ✅ (sa société) | ❌ |
| Accès panel | 🔒 Re-auth MDP (10 min) | 🔒 Re-auth MDP (10 min) | ❌ |

## 20. BUGS CONNUS / REPORTÉS
- **Bug report #3 (Charlotte, 15/04)** : "Le micro reste ouvert" → FIX `eaa7d00` : `SpeechRecognition.stop()` manquant, objet rec stocké en global `currentRecognition`.
- **Bug report #2 (Guillaume, 14/04)** : Erreur 404 archivage mail (MS Graph) → non investigué.
- **Bug report #1 (Guillaume, 14/04)** : Erreur archivage mail (iPhone) → non investigué.

## 21. FLUTTER — EN PARALLÈLE
App iOS fonctionnelle sur simulateur (login, chat, TTS, feedback). Specs dans `docs/raya_flutter_ux_specs.md`. Ne pas toucher au dossier `flutter/`.

## 22. ROADMAP

### Priorité immédiate (prochaine session)
- [x] Créer compte Charlotte (tenant `juillet`, `tenant_admin`) ✅
- [x] Tester bouton actions directes ON/OFF en prod ✅
- [x] Suspension feedback + badges ✅
- [x] Nettoyer dead code `admin_tenants.py` ✅
- [ ] Tester les 3 niveaux d'accès complets (super admin / tenant admin / user)
- [ ] Investiguer bug reports #1 et #2 (archivage mail 404)
- [ ] Tester Gmail OAuth + outils en prod
- [ ] Tester 💌 signatures en prod
- [ ] UX admin : repenser le drawer admin (trop de fonctions, certaines inutiles pour les non-super-admin)
- [ ] Vérifier que Charlotte voit bien sa société dans le panel admin

### Commercial (Bloc C)
- [ ] **Connecteurs v2** — spec validée (`docs/spec_connecteurs_v2.md`) — 3 phases :
  - Phase A : Schema DB `tenant_connections` + `connection_assignments` + migration + CRUD
  - Phase B : Panel admin UI — créer/assigner/révoquer connexions par user
  - Phase C : Intégration Raya Core — multi-connexions par user dans le chat
- [ ] C4 : WhatsApp production (sortir sandbox Twilio)
- [ ] C5 : Facturation Stripe
- [ ] Onboarding amélioré (questionnaire admin + questionnaire utilisateur)
- [ ] CSRF tokens sur les POST
- [ ] Audit performance (délai de réponse)
- [ ] Backup auto S3 (Scaleway)
- **Objectif : premier client payant juillet 2026**

## 23. DÉCISIONS CLÉS
- Seeding = DEMO uniquement. Vrais clients → questionnaire admin + questionnaire utilisateur.
- Actions directes fichiers OFF par défaut. **Tenant admin toggle** (pas super admin).
- Corbeille mail reste en action directe (récupérable + données personnelles).
- Panel admin protégé par re-auth mot de passe (10 min timeout).
- 2 boutons : 🔑 Super Admin (tous les onglets) + ⚙️ Ma société (vue société).
- Fichiers > 10KB = risque timeout MCP. Cible < 10KB pour tous les fichiers Python.
- **Routes admin** : toujours dans le package `app/routes/admin/`, jamais dans le fichier `admin.py`.
- **Connecteurs v2** (validé 16/04) : chaque connexion (OAuth, API, SharePoint) est une instance partageable, assignable/révocable dynamiquement à 1-N users par l'admin. Spec dans `docs/spec_connecteurs_v2.md`.

## 24. HISTORIQUE

### Session 16/04/2026 (~10 commits)
**FIX-CRITICAL : package `admin/` shadowait `admin.py`** — les routes suspension, actions directes, seed-user et /tenant/my-overview étaient mortes en prod depuis le 12/04. Toutes les routes injectées dans le package (`super_admin.py`). **FIX-CRITICAL : fallback OAuth `"guillaume"`** supprimé dans les callbacks Microsoft + Gmail — session vide → page erreur 401 au lieu de sauver le token sous Guillaume. **Migration DB** : colonnes `suspended` + `suspended_reason` ajoutées en prod (manquantes). **Fix micro** : `rec.stop()` manquant dans `chat-voice.js`. **Suspension feedback** : alertes vers l'onglet actif + cartes sociétés restent ouvertes. **Actions directes** : retirées du super admin, toggle per-user avec cycle (hérité/ON/OFF). **Panel admin tenant_admin** : `require_tenant_admin` au lieu de `require_admin`, onglets super-admin masqués. **Drawer filtré** : sections Mémoire/État/Actions sensibles/Debug masquées pour tenant_admin. **Bouton Panel** : `loadUserInfo()` utilise `/profile` → visible pour tenant_admin. **2 boutons** : 🔑 Super Admin + ⚙️ Ma société. **Re-auth MDP** : page de login admin dédiée, timeout 10 min. Charlotte créée et testée.

### Session 15/04/2026 soir (~15 commits)
8 fichiers morts supprimés. PWA Topics (bouton 🔖 + panneau latéral). Split CSS + admin_panel.html. Split Python batch final (13 splits Sonnet + 6 hotfixes Opus). Seeding 8 profils + endpoint seed-user. Refonte panel admin (SIRET, adresse, ID auto, double confirmation, bouton collaborateur). Cloisonnement Drive. Suspension comptes. Actions directes on/off. FIX-CRITICAL 16 décorateurs admin_endpoints.py.

### Session 15/04/2026 matin (~70 commits)
TOPICS 5/5. FIX-CLEAN + TIMESTAMP. RENAME raya_chat. 3 bugs chat. Refactoring BATCH 1+2+3 (19 splits). UX-TONE. Bug report amélioré. 👍 confirme pending. 3 hotfixes imports.

### Session 14/04/2026 (~45 commits)
AUDIT COMPLET. P0-1 anti-injection. SAV. Bloc A. B1 B3 B4. C3 RGPD. FIX-LEARN. Split aria_context + security_users. Lancement Flutter.

### Sessions précédentes
13-14/04 nuit : ~50 commits. 13/04 : Connectivité 5/5. 12-13/04 : ~55 tâches. 12/04 : Refactor admin en package.

## 25. REPRISE
« Bonjour Opus. Projet Raya, Guillaume Perrin (Couffrant Solar). On se tutoie, en français, vocabulaire Terminal, concis. Lis `docs/raya_session_state.md` sur `per1gyom/couffrant-assistant` main. Reprends où on en était. »
