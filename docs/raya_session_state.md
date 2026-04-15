# Raya — État de session vivant

**Dernière mise à jour : 15/04/2026 15h30** — Opus

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
30+ splits Python — tous les fichiers Python < 10KB. 6 hotfixes imports circulaires (HOTFIX-1 à HOTFIX-6). CSS splitté en 3 fichiers (chat-base.css + chat-components.css + chat-drawer.css). Admin panel splitté (admin-panel.css + admin-panel.js extraits). 8 fichiers morts supprimés (aria.py, raya_actions.py, etc.).

**FIX-CRITICAL admin_endpoints.py** : Le split Sonnet avait empilé 16 décorateurs de routes sur une seule fonction `admin_memory_status`. Corrigé : chaque fonction a son propre `@router.` + `admin_endpoints.py` correctement inclus via `include_router` dans `admin.py`. Doublons `@router` nettoyés. Auto-import circulaire supprimé.

**⚠️ NETTOYAGE RESTANT** : `admin_tenants.py` contient encore 2 fonctions mortes (`admin_set_tool`, `init_db_now`) qui sont dupliquées depuis `admin_endpoints.py`. À supprimer.

## 13. MULTI-TENANT ✅
- Tenant `couffrant_solar` : Guillaume (super_admin)
- Tenant `juillet` : créé dans le panel — Charlotte à créer (tenant_admin) — Guillaume veut tester le formulaire lui-même

## 14. PANEL ADMIN — REFONTE ✅
### Création société
- Nom de la société → ID auto-généré (normalisé). L'utilisateur ne saisit pas l'ID technique.
- SIRET obligatoire (14 chiffres, validé côté JS + backend)
- Adresse structurée : 3 champs séparés (rue + code postal 5 chiffres + ville)
- Forme juridique (dropdown SAS/SARL/SASU/EURL/SA/SCI/Auto-entrepreneur/Association)
- Fournisseur email configurable

### Création utilisateur
- Formulaire avec sélecteur société (dropdown chargé dynamiquement) + sélecteur profil métier (8 profils)
- Bouton "➕ Ajouter un collaborateur" dans chaque fiche société (tenant pré-rempli et verrouillé)
- Le seeding est appelé automatiquement après création

### Double confirmation suppressions
- Suppression société : modale → champ "Tapez SUPPRIMER" → bouton grisé tant que non saisi
- Suppression utilisateur : modale → champ "Tapez le nom d'utilisateur" → bouton grisé

## 15. SUSPENSION DE COMPTES ✅
- `app/suspension.py` : check_suspension(), suspend_user(), unsuspend_user(), suspend_tenant(), unsuspend_tenant()
- Migration DB : colonnes `suspended BOOLEAN` + `suspended_reason TEXT` sur table users
- Tenants : `suspended` + `suspended_reason` dans le JSONB `settings`
- Vérification au login web (`auth.py`) : message "Votre compte/organisation est suspendu. Contactez..."
- Vérification sur tous les endpoints API (`deps.py`) : HTTP 403 → bloque aussi l'app Flutter
- Super admin : peut suspendre n'importe quel user ou tenant
- Tenant admin : peut suspendre/réactiver les utilisateurs de sa propre société (`assert_same_tenant`)
- Panel admin : boutons ⏸️ Suspendre (avec raison optionnelle) / ▶️ Réactiver par utilisateur + par société
- Badges visuels ⏸️ SUSPENDU dans les listes users et les cartes sociétés

## 16. ACTIONS DIRECTES (FICHIERS) ✅
- `app/direct_actions.py` : `can_do_direct_actions(username, tenant_id)` — priorité : user override > tenant setting > défaut (False)
- Par défaut OFF : CREATEFOLDER passe en queue de confirmation si `direct_actions` est off
- MOVEDRIVE/COPYFILE : déjà en queue (confirmation requise)
- Corbeille mail : reste en action directe (récupérable + données personnelles de l'utilisateur)
- Panel admin : toggle 🟢 ON / 🔴 OFF au niveau société, visible dans chaque fiche société
- Tenant admin peut toggler pour sa société + pour chaque utilisateur individuellement
- Super admin peut toggler pour n'importe quel tenant/user
- **BUG FIXÉ** : `Body(...)` → `Body(default={})` sur les endpoints — à vérifier en prod

## 17. CLOISONNEMENT DRIVE ✅
- `drive_connector.py` : défauts neutres (site_name="", folder_name=""). Plus de fallback vers Couffrant Solar.
- `get_drive_config()` retourne `configured: False` si le tenant n'a pas de SharePoint configuré
- Migration : `sharepoint_site: "Commun"` ajouté au tenant `couffrant_solar`
- Lazy `__getattr__` dans drive_connector.py pour réexport sans import circulaire (HOTFIX-5)

## 18. SEEDING PROFILS (DEMO uniquement)
8 profils dans `app/seeding.py` : pv_french, event_planner, generic, artisan, immobilier, conseil, commerce, medical.
Endpoint : `POST /admin/seed-user` avec body `{"username": "xxx", "profile": "generic"}`.
Bouton 🌱 par utilisateur dans la liste du panel admin.
**DÉCISION** : Les profils de seeding sont réservés aux comptes DEMO. Les vrais clients apprennent via questionnaire admin (création société) + questionnaire utilisateur (1ère connexion). Cet onboarding amélioré est planifié mais pas encore codé.

## 19. MATRICE DES DROITS (VALIDÉE)
| Fonctionnalité | Super Admin | Admin Tenant | Utilisateur |
|---|---|---|---|
| Voir toutes les sociétés | ✅ | ❌ (que la sienne) | ❌ |
| Créer/Supprimer société | ✅ | ❌ | ❌ |
| Suspendre société | ✅ | ❌ | ❌ |
| Suspendre utilisateur | ✅ (tous) | ✅ (sa société) | ❌ |
| Créer/Supprimer utilisateur | ✅ (tous) | ✅ (sa société) | ❌ |
| Toggle actions directes | ✅ (tous) | ✅ (sa société) | ❌ |
| Seeder un profil | ✅ | ✅ (sa société) | ❌ |
| Chat Raya | ✅ | ✅ | ✅ |
| Tiroir admin chat | ✅ (complet) | ✅ (partiel) | ❌ (masqué) |
| Panel admin | ✅ (complet) | ✅ (sa société) | ❌ |

## 20. FLUTTER — EN PARALLÈLE
App iOS fonctionnelle sur simulateur (login, chat, TTS, feedback). Specs dans `docs/raya_flutter_ux_specs.md`. Ne pas toucher au dossier `flutter/`.

## 21. ROADMAP

### Priorité immédiate (prochaine session)
- [ ] Créer compte Charlotte (tenant `juillet`, `tenant_admin`) — Guillaume teste le formulaire lui-même
- [ ] Tester bouton actions directes ON/OFF en prod (erreur Body fixée commit `0dbe735`)
- [ ] Vérifier les 3 niveaux d'accès : super admin (Guillaume), tenant admin (Charlotte), utilisateur simple
- [ ] Nettoyer fonctions mortes dans `admin_tenants.py` (admin_set_tool, init_db_now dupliquées)
- [ ] Tester Gmail OAuth + outils en prod
- [ ] Tester 💌 signatures en prod

### Commercial (Bloc C)
- [ ] C4 : WhatsApp production (sortir sandbox Twilio)
- [ ] C5 : Facturation Stripe
- [ ] Onboarding amélioré (questionnaire admin + questionnaire utilisateur — planifié, pas codé)
- [ ] CSRF tokens sur les POST
- [ ] Audit performance (délai de réponse)
- [ ] Backup auto S3 (Scaleway)
- **Objectif : premier client payant juillet 2026**

## 22. DÉCISIONS CLÉS
- Seeding = DEMO uniquement. Vrais clients apprennent via questionnaire admin + questionnaire utilisateur.
- Actions directes fichiers OFF par défaut. Admin tenant toggle ON/OFF par société + par user.
- Corbeille mail reste en action directe (récupérable + données personnelles).
- Toujours expliquer la solution avant de coder. Guillaume valide, puis Opus exécute.
- Fichiers > 10KB = risque timeout MCP. Cible < 10KB pour tous les fichiers Python.

## 23. HISTORIQUE

### Session 15/04/2026 soir (~15 commits)
8 fichiers morts supprimés. PWA Topics (bouton 🔖 + panneau latéral). Split CSS (chat.css → 3 fichiers) + split admin_panel.html (CSS+JS extraits). Split Python batch final (13 splits Sonnet + 6 hotfixes Opus). C1+C2 : 8 profils seeding + endpoint seed-user. Refonte panel admin (SIRET obligatoire, adresse 3 champs, ID auto, double confirmation suppression, bouton ajout collaborateur). Sécurité cloisonnement Drive. Suspension comptes (users + tenants). Actions directes on/off. FIX-CRITICAL 16 décorateurs admin_endpoints.py restaurés.

### Session 15/04/2026 matin (~70 commits)
TOPICS 5/5. FIX-CLEAN + TIMESTAMP. RENAME raya_chat. 3 bugs chat. Refactoring BATCH 1+2+3 (19 splits). UX-TONE style conversationnel. UX bug report amélioré. UX 👍 confirme pending. 3 hotfixes imports cassés.

### Session 14/04/2026 (~45 commits)
AUDIT COMPLET. P0-1 anti-injection. SAV. Bloc A. B1 B3 B4. C3 RGPD. FIX-LEARN. Split aria_context + security_users. Lancement Flutter.

### Sessions précédentes
13-14/04 nuit : ~50 commits. 13/04 : Connectivité 5/5. 12-13/04 : ~55 tâches.

## 24. REPRISE
« Bonjour Opus. Projet Raya, Guillaume Perrin (Couffrant Solar). On se tutoie, en français, vocabulaire Terminal, concis. Lis `docs/raya_session_state.md` sur `per1gyom/couffrant-assistant` main. Reprends où on en était. »
