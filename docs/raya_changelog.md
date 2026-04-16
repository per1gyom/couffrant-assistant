# Raya — Changelog

*Archive des modifications par session. Mis à jour par Opus à chaque jalon.*

---

## Session 16/04/2026 suite — 17h00 (Opus + Guillaume)

### Signature email — système complet ✅
- `app/connectors/outlook_calendar.py::_build_email_html` → appelle `get_email_signature(username)` (déjà en place)
- Logo `app/static/5AEA8C3F-2F59-4ED0-8AAA-3B324C3498DF.png` présent et référencé dans `_static_signature`
- `app/routes/aria_context.py::FORMAT_BLOCK` : ajout instruction "Ne jamais inclure de signature dans un mail que tu rédiges : la signature est ajoutée automatiquement par le système"
- Raya ne signe plus elle-même — chaîne complète opérationnelle

### Docs mis à jour
- `docs/raya_session_state.md` : réécriture complète (cache-bust v=36, tâches session 16/04 documentées, signature, display_name, palette, roadmap à jour)
- `docs/raya_changelog.md` : présente entrée

---

## Session 16/04/2026 matin suite — 07h00→12h54 (Opus + Guillaume — ~35 commits)

### Raccourcis éditables v2 ✅
- `529b412` — Table `user_shortcuts` + CRUD API `/shortcuts` (GET/POST/PATCH/DELETE)
- `5dd7a8f` — UI modale titre + prompt personnalisé + sélecteur 12 couleurs + delete
- `228a032` — Fix Safari : `let shortcutsEditMode` dupliqué supprimé (crash showToast)

### Sujets intégrés sidebar ✅
- `5dd7a8f` — `topicsSidebarList` dans HTML `<details open>`, `chat-topics.js` v3 miroir raccourcis
- `4e3d6be` — Design final : triangle sidebar agrandi, topics v3 aligné raccourcis

### Palette couleurs ✅
- `47e28bc` — Palette 6 "Bleu Roi Saturé" `#0057b8` appliquée (v=27)
- `53deb1d` — Fond pastel `#f5f9ff`, borders `#bdd6ff` (v=30)

### display_name ✅
- `08b1e3e` — Migration DB, `/profile/display-name`, `list_users`, `/chat` inject
- `19bcfcf` — UI modal admin, carte profil, logo italic bleu, footer sans username
- `0be7a90` — `loadUserInfo()` priorité display_name sur username

### Modal Paramètres refonte ✅
- `8a8885` — Lecture auto + display_name + email + MDP + RGPD + Valider/Annuler sticky (v=32)
- `d527f79` — Zoom viewport autorisé, modal 65vw/85vh scrollable (v=33)
- `90db119` — SVG Lucide dans Paramètres, puces modernes réponses Raya (v=34)

### Suppression compte avec validation admin ✅
- `e808ad6` — Workflow request/confirm/reject/cancel, MDP requis

### Fixes mails ✅
- `ea8026e` — Raya ne répète plus les règles après LEARN + nommage boîtes mail permanent
- `6008a6a` — Pluralisation "règles mises à jour" + interdire `__email__` dans réponses
- `a859d55` — Réponse mail : carte propre, `\n` corrigé, lookup tolérant, UX modernisée (v=36)

### Fixes UX
- `221adf3` — textarea overflow-y:hidden (supprime scrollbars vides dans la saisie)
- `64c5c87` — Ma société restauré pour super admin
- `cdc76c6` — username injecté côté serveur + page login palette bleue v2

---

## Session 16/04/2026 (Opus + Guillaume — ~10 commits)

### FIX-CRITICAL : Package admin/ shadow
- `5bd1e5c` — Routes suspension, direct-actions, seed-user, /tenant/my-overview injectées dans le package `app/routes/admin/super_admin.py`. Le fichier `admin.py` était shadowed par le dossier `admin/` depuis le 12/04.

### FIX-CRITICAL : OAuth fallback "guillaume"
- `8ef3f27` — Fallback `request.session.get("user", "guillaume")` supprimé dans les callbacks Microsoft + Gmail. Session vide → page 401.

### Migration DB prod
- Colonnes `suspended BOOLEAN` + `suspended_reason TEXT` ajoutées manuellement via psycopg2 (manquaient en prod).

### Suspension & Actions directes
- `93d97cb` — Feedback suspension : alertes vers l'onglet actif
- `65c7f0e` — `/tenant/my-overview` + `direct_actions_override` par user
- `264efb0` — Cartes sociétés restent ouvertes après suspend/toggle
- Actions directes retirées du super admin, toggle per-user cycle (hérité/ON/OFF)

### Panel admin multi-rôle
- Panel accessible aux `tenant_admin` (onglets Sociétés + Profil uniquement)
- Drawer chat filtré par scope (sections super-admin masquées)
- Bouton 🖥 Panel visible pour tenant_admin via `/profile`

### Sécurité panel
- `9241291` — Re-auth mot de passe pour accès panel (timeout 10 min)
- 2 boutons header : `🔑 Super Admin` + `⚙️ Ma société`
- Page de login admin dédiée, endpoint `POST /admin/auth`

### Fix micro
- `eaa7d00` — `SpeechRecognition.stop()` manquant, objet stocké en global `currentRecognition`

---

## Session 15/04/2026 soir (~15 commits)
- 8 fichiers morts supprimés (aria.py, raya_actions.py, etc.)
- PWA Topics : bouton 🔖 + panneau latéral `chat-topics.js`
- Split CSS (chat.css → 3 fichiers) + split admin_panel.html (CSS+JS extraits)
- Split Python batch final (13 splits Sonnet + 6 hotfixes Opus imports circulaires)
- C1+C2 : 8 profils seeding + endpoint `POST /admin/seed-user`
- Refonte panel admin : SIRET obligatoire, adresse 3 champs, ID auto, double confirmation suppression, bouton ➕ collaborateur
- Cloisonnement Drive : défauts neutres, plus de fallback vers Couffrant Solar
- Suspension comptes : users + tenants, login + API, boutons ⏸️/▶️
- Actions directes on/off par société + par user
- FIX-CRITICAL : 16 décorateurs de routes restaurés dans admin_endpoints.py

## Session 15/04/2026 matin (~70 commits)
- TOPICS 5/5 : 5 endpoints CRUD + migration DB + prompt injection + RGPD + Flutter prêt
- FIX-CLEAN + TIMESTAMP : nettoyage actions brutes + horodatage messages
- RENAME raya_chat + 3 bugs chat corrigés
- Refactoring BATCH 1+2+3 : 19 splits (tous les fichiers Python < 10KB)
- UX-TONE : style conversationnel naturel
- Bug report amélioré : commentaire optionnel + collecte auto échanges
- 👍 confirme pending actions + DELETE/ARCHIVE mutuellement exclusifs
- 3 hotfixes imports cassés

## Session 14/04/2026 (~45 commits)
- AUDIT COMPLET : inventaire de toute la codebase
- P0-1 : anti-injection prompt (GUARDRAILS, CSP)
- SAV/Bug report système complet
- Bloc A : PWA, safe-area iOS, autoSpeak off
- B1 B3 B4 : Teams ingestion, email signatures v2, scheduler
- C3 : RGPD complet (export + suppression + mentions légales)
- FIX-LEARN : pilule verte mémoire
- Split aria_context + security_users
- Lancement Flutter (app iOS simulateur)

## Session 12-13/04/2026 (~105 commits)

### Phase 5A — Sécurité & dette technique (14/14 ✅)
MDP env obligatoire, cookie 7j, rate limiter, audit log, migration llm_complete, wrappers supprimés, tools_registry source de vérité, APScheduler, 9 scripts legacy supprimés.

### Phase 5B — Optimisation prompt (5/5 ✅)
Injection dynamique actions, hot_summary 3 niveaux, cache TTL 5min, déduplication RAG, ThreadPoolExecutor.

### Phase 5C — Robustesse (4/4 ✅)
Structured logging, health check profond, timeout 30s, monitoring APScheduler.

### Sessions précédentes
Phases 1–4 : RAG, multi-tenant, rule_validator, feedback, scheduler, tests.
