# Raya — État de session vivant

**Dernière mise à jour : 16/04/2026 17h00** — Opus (nouvelle session post-saturation)

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
- Cache-bust : `?v=36` (actuel)
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
Connectivité 5/5, Outils création (PDF, Excel, DALL-E), PWA v=36, Sécurité (anti-injection, GUARDRAILS, CSP, bcrypt, lockout), Signature email v2, SAV/Bug report, RGPD complet, Backup manuel.
**Service Worker** : DÉSACTIVÉ (cause racine des bugs d'affichage au refresh). Le HTML nettoie les anciens SW + purge les caches à chaque chargement. Anti-cache double couche (unregister + reload si `marked` absent).

## 10. UX CHAT ✅ + REDESIGN V2 ✅
Nettoyage actions brutes, horodatage messages, style conversationnel naturel (UX-TONE), 👍 confirme pending, bug report commentaire optionnel, DELETE/ARCHIVE mutuellement exclusifs, nettoyage fragments Odoo inline.

### Redesign v2 (session 16/04)
- **Typo** : Inter (Google Fonts) + JetBrains Mono pour code
- **Palette** : Bleu Roi Saturé `#0057b8`, fond pastel `#f5f9ff`, borders `#bdd6ff` (Guillaume a validé palette 6 — PLUS de violet)
- **Icônes** : TOUTES les emojis remplacées par des SVG Lucide inline (micro, attach, send, speak, feedback, bookmark, shield, settings, logout, volume, etc.)
- **Réponses Raya** : pleine page (pas de bulle), fond transparent, width 100%. Seuls les prompts user en bulle bleue.
- **Avatar Raya** : masqué (inutile en pleine page)
- **Markdown** : `marked.parse()` avec `breaks:true, gfm:true`, DOMPurify ALLOWED_URI_REGEXP élargi pour blob URLs. Tables avec header gris, code blocks sombres, headers hiérarchisés.
- **Prompt système** : instruction ABSOLUE de ne jamais montrer les codes `[ACTION:...]` ou `[SPEAK_SPEED:...]`. Erreurs user-friendly.
- **Layout sidebar** : header supprimé, sidebar gauche 220px (logo+sujets+raccourcis déroulants), menu ⋮ 3 points en bas sidebar (position:fixed z-index:9999), sidebar repliable avec bouton expand.
- **Input** : compact (padding réduit), fond transparent, auto-scroll dictée, max-height 160px, overflow-y:hidden (pas de scrollbars vides).
- **Raccourcis** : pastilles colorées arc-en-ciel (12 couleurs), fermés par défaut, boutons SVG edit/check.
- **Quick actions** : boutons pill dans sidebar, hover bleu.
- **Toasts** : backdrop-blur, transparence.
- **display_name** : migration DB, champ modal admin, carte profil, logo italic bleu, footer sans username.

## 11. RACCOURCIS ÉDITABLES v2 ✅ (session 16/04)
- Table `user_shortcuts` en DB (pas localStorage) — migration appliquée
- API CRUD : `GET/POST /shortcuts`, `PATCH/DELETE /shortcuts/{id}`
- UI modale titre + prompt personnalisé (peut être long, dictable) + sélecteur 12 couleurs
- Mode édition : bouton stylo → mode edit → croix ✕ pour supprimer, clic = éditer
- Fix Safari : `let shortcutsEditMode` dupliqué supprimé (`228a032`)
- Fichier : `app/static/chat-shortcuts.js`

## 12. SUJETS INTÉGRÉS SIDEBAR ✅ (session 16/04)
- `<details class="sidebar-details" id="topicsSidebarSection" open>` dans le HTML — section ouverte par défaut
- `chat-topics.js` v3 — miroir exact du design raccourcis (même classes, même icônes SVG)
- `initTopicsSidebar()` appelé dans `init()` de `chat-main.js`
- Drawer noir topics : supprimé. Stubs de compatibilité descendante conservés.
- Renommer topic : `prompt()` natif (à améliorer plus tard en modale)

## 13. SIGNATURE EMAIL ✅ (session 16/04)
- `app/email_signature.py` : `get_email_signature(username, from_address=None)`
  - Ordre lookup : 1) DB email_signatures (match adresse exacte) → 2) signature générique → 3) fallback statique Guillaume
  - Fallback statique : "Solairement, Guillaume Perrin, 📞 06 49 43 09 17, 🌐 couffrant-solar.fr, logo PNG"
- **Logo** : `app/static/5AEA8C3F-2F59-4ED0-8AAA-3B324C3498DF.png` (913KB) — accessible via `https://app.raya-ia.fr/static/5AEA8C3F-2F59-4ED0-8AAA-3B324C3498DF.png`
- **`_build_email_html`** (outlook_calendar.py) → appelle `get_email_signature(username)` → appende la signature automatiquement à chaque envoi
- **outlook_actions.py** → `send_reply`, `send_new_mail`, `create_reply_draft` appellent tous `_build_email_html`
- **System prompt** (aria_context.py `FORMAT_BLOCK`) : "Ne jamais inclure de signature dans un mail que tu rédiges : la signature est ajoutée automatiquement par le système"
- **Note** : `from_address` non passé pour l'instant (default None → fallback statique Guillaume). À améliorer quand d'autres boîtes seront configurées.
- Extraction auto depuis mails envoyés : endpoint `POST /admin/extract-signatures` (bouton dans tiroir admin)

## 14. CARTE DE CONFIRMATION REPLY ✅ (session 16/04)
- `mail_actions.py` : lookup tolérant (exact puis 20 premiers chars), `\n` littéral → vrai saut de ligne
- `chat-messages.js` : carte REPLY avec "À : Prénom Nom", "Sujet : Re: ...", corps formaté `white-space:pre-line`
- `chat-drawer.css` : bordure gauche bleue, boutons plats (fini les gros boutons vert/rouge)

## 15. MODAL PARAMÈTRES UTILISATEUR ✅ (session 16/04)
- Accessible via menu ⋮ → Paramètres
- Sections : lecture auto (toggle) + display_name + email + mot de passe + RGPD
- Footer sticky : boutons Annuler / Valider (sauvegarde tout en un clic)
- SVG Lucide pour chaque section

## 16. SUPPRESSION COMPTE AVEC VALIDATION ADMIN ✅ (session 16/04)
- Workflow : request → confirm (admin) → reject/cancel
- Mot de passe requis pour soumettre la demande
- Compte reste actif jusqu'à validation admin

## 17. TOPICS ✅
5 endpoints CRUD + sidebar déroulante (voir §12) + RGPD couvert + Flutter prêt.

## 18. REFACTORING ARCHITECTURE ✅ (COMPLET)
30+ splits Python — tous les fichiers Python < 10KB. 6 hotfixes imports circulaires. CSS splitté. Admin panel splitté. 8 fichiers morts supprimés.

**⚠️ Package admin/** : `app/routes/admin/` (package) shadow `app/routes/admin.py` (fichier). Toutes les routes sont dans le package : `super_admin.py`, `super_admin_users.py`, `super_admin_system.py`, `tenant_admin.py`, `profile.py`.

## 19. MULTI-TENANT ✅
- Tenant `couffrant_solar` : Guillaume (super_admin) — 5 utilisateurs
- Tenant `juillet` : Charlotte (tenant_admin) — créé le 15/04, testable

## 20. PANEL ADMIN — REFONTE ✅
### Création société + utilisateur + double confirmation + accès par rôle ✅
### Re-authentification admin (SECURITY) ✅ — timeout 10 min
### Layout v3 : sidebar gauche, menu ⋮ en bas

## 21. SUSPENSION DE COMPTES ✅
Migration DB 16/04, check login + API, boutons panel admin, badges ⏸️.

## 22. ACTIONS DIRECTES (FICHIERS) ✅
Par défaut OFF. Toggle tenant_admin. Corbeille = action directe (récupérable).

## 23. CLOISONNEMENT ✅
Drive défauts neutres. OAuth : session vide → erreur 401 (plus de fallback Guillaume).

## 24. CONNECTEURS V2 ✅ (Phase A+B)
- `tenant_connections` + `connection_assignments`
- `app/connections.py` : create/update/delete/list/assign/unassign/get_user_connections
- 14 endpoints API, UI panel admin
- **Phase C restante** : `get_user_connections()` dans `_raya_core()` remplace `load_user_tools()`

## 25. BUGS CONNUS / REPORTÉS
- Bug report #2 (Guillaume, 14/04) : Erreur 404 archivage mail (MS Graph) → non investigué
- Bug report #1 (Guillaume, 14/04) : Erreur archivage mail (iPhone) → non investigué

## 26. FLUTTER — EN PARALLÈLE
App iOS fonctionnelle sur simulateur. Ne pas toucher au dossier `flutter/`.

## 27. ROADMAP

### Priorité immédiate
- [ ] **Connecteurs v2 Phase C** — `get_user_connections()` dans `_raya_core()`, remplace `load_user_tools()`
- [ ] **Panel admin — onglet Signatures par utilisateur** : depuis la fiche admin d'un utilisateur, pouvoir éditer ses signatures selon ses boîtes mail connectées (même éditeur WYSIWYG que côté user)
- [ ] Investiguer bug reports #1 et #2 (archivage mail 404)
- [ ] Tester les 3 niveaux d'accès complets (super admin / tenant admin / user)

### Commercial (Bloc C)
- [ ] C4 : WhatsApp production (sortir sandbox Twilio)
- [ ] C5 : Facturation Stripe
- [ ] Onboarding amélioré (questionnaire admin + questionnaire utilisateur)
- [ ] CSRF tokens sur les POST
- [ ] Audit performance (délai de réponse)
- [ ] Backup auto S3 (Scaleway)
- **Objectif : premier client payant juillet 2026**

## 28. DÉCISIONS CLÉS
- Seeding = DEMO uniquement. Vrais clients → questionnaire.
- Actions directes OFF par défaut. Tenant admin toggle.
- Panel admin protégé par re-auth MDP (10 min timeout).
- Palette validée : Bleu Roi Saturé `#0057b8` (PLUS de violet).
- Signature email : injected automatiquement via `_build_email_html` → `get_email_signature`. Raya ne signe JAMAIS elle-même.
- Service Worker : DÉSACTIVÉ définitivement.
- Routes admin : toujours dans le package `app/routes/admin/`.
- display_name : champ séparé de username, affiché dans logo et modal.

## 29. HISTORIQUE

### Session 16/04/2026 (~50+ commits)
**Rappel session précédente (16/04 matin, ~40 commits)** : Connecteurs v2 Phase A+B, redesign complet UI (palette indigo→bleu, sidebar, SVG icons, markdown, SW désactivé).

**Session 16/04 suite** (commits à partir de 07:08) :
- Raccourcis éditables v2 complets (table DB, CRUD API, modale, fix Safari)
- Sujets intégrés sidebar (topicsSidebarList, chat-topics.js v3)
- Palette bleu roi saturé `#0057b8` appliquée (palette 6 validée)
- display_name : migration DB, API, UI admin, logo
- Modal Paramètres refonte (lecture auto + display_name + email + MDP + RGPD + Valider sticky)
- Suppression compte avec validation admin (request/confirm/reject/cancel)
- Fix réponse mail : carte propre, lookup tolérant, `\n` normalisé, UX modernisée
- Fix Raya ne répète plus les règles après LEARN
- Fix boîtes mail nommées (Couffrant Solar / perso)
- Fix textarea overflow-y:hidden
- Système signature email : logo uploadé, `_build_email_html` → `get_email_signature`, instruction system prompt
- Cache-bust final : **v=36**

### Sessions précédentes
16/04 matin, 15/04 soir+matin, 14/04 — voir historique complet dans `raya_changelog.md`.

## 30. REPRISE
« Bonjour Opus. Projet Raya, Guillaume Perrin (Couffrant Solar). On se tutoie, en français, vocabulaire Terminal, concis. Lis `docs/raya_session_state.md` sur `per1gyom/couffrant-assistant` main. Reprends où on en était. »
