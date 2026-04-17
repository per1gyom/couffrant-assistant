# Raya — Changelog

*Archive des modifications par session. Mis à jour par Opus à chaque jalon.*

---

## Session 17/04/2026 soir (22h-23h) — Mermaid : schémas graphiques SVG

**Objectif** : remplacer l'art ASCII illisible par de vrais schémas
rendus graphiquement (organigrammes, flux, hiérarchies, timelines).

**Approche validée avec Guillaume** : minimaliste côté prompt (~20 tokens),
robuste côté frontend. Pas de template imposé — l'utilisateur personnalise
par feedback et Raya apprend via `aria_rules`.

**4 commits successifs de mise en place puis debug** :

- `5b17771` — Ajout Mermaid.js 11.4.0 via CDN + init + `renderMermaidBlocks`
  + règle minimaliste dans `aria_context.py` + CSS `.mermaid-wrapper`
- `3a3bfd1` — Ajout `normalizeMermaidSyntax` (backticks simples → triple)
  + `tagMermaidCodeBlocks` (détection heuristique des code blocks sans tag)
- `67b5841` — Enrichissement `normalizeMermaidSyntax` pour gérer le cas
  où Raya ferme avec un `` ` `` simple + ajout `mermaid.parse()` avant
  `mermaid.render()` pour valider la syntaxe et éviter les SVG-bombes
  que Mermaid 11.x affiche au lieu de thrower
- `256bd49` — **Fix du vrai bug** : race condition DOM. `renderMermaidBlocks`
  était appelé en async fire-and-forget AVANT les `innerHTML = innerHTML.replace`
  qui réécrivaient le DOM. Le `<pre>` référencé devenait orphelin →
  `replaceChild` échouait silencieusement → rendu Mermaid fonctionnait
  mais écrivait dans le vide. Déplacement de l'appel à la FIN de `finalize()`.

**Cache-bust** : v=74 → v=78 (4 bumps successifs).

**Leçon** : Guillaume a insisté pour que je diagnostique via le texte
brut de la DB plutôt que de patcher à l'aveugle. Sans sa directive,
j'aurais continué à ajouter des regex au lieu de regarder l'ordre
d'exécution. Bon réflexe à retenir : quand « tout marche mais rien ne
s'affiche », scruter l'ordre d'exécution DOM avant de supposer un
problème de parsing.

**Résultat** : 3 schémas successifs de test (organigramme patrimonial,
version avec couleurs pastel sur demande) rendus correctement au
rechargement de page.

### Nouveau chantier identifié (🟡 priorité moyenne, après capabilities)

**Analyse complète des outils visuels/interactifs à intégrer.**

Mermaid a ouvert un nouveau registre pour Raya (visuel, pas seulement
textuel). Question ouverte : quels autres outils pourraient être ajoutés ?
Pistes : Chart.js/Plotly (graphiques de données), KaTeX (formules
financières), Excalidraw (croquis whiteboard), Leaflet/Mapbox (cartes
chantiers), timelines interactifs, tableaux triables/filtrables, code
sandbox, widgets formulaires.

Détails dans `raya_session_state.md` section « NOUVEAU CHANTIER À OUVRIR ».

---

## Session 17/04/2026 soir — Chat solide + Auto-découverte élargie + Architecture capabilities

### Fixes chat (solidification)
- `13ef8a5` — Cartes mail insérées au bon endroit : colonne `conversation_id`
  exposée par `pending_actions.get_pending` + `chat_history`, côté frontend
  `addMessage` pose `data-aria-memory-id` et `appendPendingActionToChat`
  utilise `insertAdjacentElement('afterend')` avec smart fallback.
- `5e63167` — Chat solide :
  - Backend timeout 30 → 90 s (résout le bug fantôme Opus 4.7 + 8192 tokens)
  - Polling côté client si timeout : surveille `/chat/history` 90 s et
    remplace l'erreur par la vraie réponse si elle arrive.
  - UX : scroll auto, question remonte en haut du viewport dès que Raya réfléchit.
  - Nouveau loader : sigle ✦ pulsé + texte italique rotatif (6 phrases).
  - Timezone fix : `parseServerTimestamp` + toLocaleString Europe/Paris.
  - Flag `is_error` + `error_type` sur les réponses d'erreur.

### Tests automatisés (doc)
- `51e24c8` — Création `docs/raya_test_protocol.md` : 5 batteries de tests
  via Claude in Chrome (CHAT-BASELINE, CARTES-MAIL, GRAPHE, ODOO-ACTIONS,
  UX-SCROLL) avec règles validation humaine + rate limit respecté.

### Scheduler
- `e041e5d` — Ajout du wrapper `_job_confidence_decay` manquant (import
  échoué silencieusement au démarrage du scheduler Railway).

### Auto-découverte élargie Drive / Calendar / Contacts
- `d3bb5cf` — 3 nouvelles fonctions `discover_*` dans `tool_discovery.py` +
  3 `populate_from_*` dans `entity_graph.py`. Route admin
  `/admin/discover/{tenant_id}/{tool_type}` étendue à drive / calendar /
  contacts. Bouton 🔍 Découvrir étendu aux connexions Microsoft / Gmail
  (enchaîne drive → calendar → contacts automatiquement).
- Détection dynamique des modèles Odoo (planning.slot, hr.leave, etc.)
  au lieu de la liste hardcodée.

### Architecture — Matrice de capabilities (doc de design)
- Nouveau `docs/raya_capabilities_matrix.md` — socle d'autorisation à
  3 niveaux (default → admin → user) avec verrouillage, stratégie prompt
  "ultra-minimaliste actionnable" (Stratégie 4), tests de non-régression,
  plan d'implémentation par étapes A-F.
- Mise à jour `session_state.md` : section CONTEXTE MÉTIER COUFFRANT SOLAR
  (OpenFire vs Odoo, ressources planning, couleurs chantiers) +
  philosophie découverte 360°.
- Chantiers A (`populate` planning Odoo) + B (instruction prompt) + C
  (calendar 360°) en attente du socle capabilities.

---

## Session 18/04/2026 — Refonte intelligence + Graphe de relations (~20 commits)

### Refonte intelligence Raya
- Identité : "Tu es Claude, modèle d'Anthropic" → intelligence native libérée
- Prompt restructuré : contexte d'abord (utilisateur, données), règles CORE_RULES à la fin (30 lignes)
- Historique 6 → 30 échanges, max_tokens 2048 → 8192
- Routeur assoupli, quota Opus 20 → 50/jour, rate limiter 60 → 120/h
- Anti-bluff + anti-censure : "GÉNÈRE les tags ACTION, ne décris pas ce que tu vas faire — fais-le"
- Upgrade Claude Opus 4.6 → **4.7** (meilleur suivi instructions, auto-vérification)

### Actions Odoo (complètes)
- ODOO_SEARCH, ODOO_MODELS, ODOO_CREATE, ODOO_UPDATE, ODOO_NOTE
- Parseur `_extract_action_tags` — gère les crochets imbriqués (JSON Odoo)
- `_safe_parse_domain` — parse robuste des domaines Odoo
- Retry automatique sur KeyError (champs inconnus → fallback `name`)

### Auto-découverte outils (couche 2 — vectorisation)
- `tool_schemas` table DB avec embeddings vectoriels HNSW
- `discover_odoo()` — explore 21 modèles business, vectorise descriptions + champs + relations
- `retrieve_tool_knowledge()` — RAG injecte les schémas pertinents dans le prompt
- Bouton 🔍 Découvrir dans le panel admin sur chaque connexion Odoo

### Graphe de relations (couche 3 — cross-source)
- `entity_links` table DB — relie contacts ↔ factures ↔ mails ↔ fichiers ↔ Teams
- `entity_graph.py` : link_entity, get_entity_context, populate_from_odoo, populate_from_mail_memory
- Lookup graphe injecté dans le prompt quand un contact est mentionné
- Peuplement automatique lors du bouton Découvrir Odoo

### Synthèse auto (2ème appel LLM)
- Quand des résultats informatifs remontent (📊📋📇🗂️🔍❌), un 2ème appel LLM est lancé
- Raya voit ses propres résultats et fait la synthèse (tableaux, totaux, analyse)
- Les données brutes sont masquées quand la synthèse réussit
- aria_memory mis à jour avec la synthèse

### UX
- Bouton stop (annuler prompt en cours) + verrouillage double envoi (AbortController)
- Résultats informatifs affichés dans le chat (plus en toasts perdus)
- `_strip_action_tags` — parseur avec profondeur de crochets
- Fix panel admin : syntaxe JS askDeleteUser, try/catch loadMemoryStatus, showToast→setAlert

### Route admin DEV ONLY
- `/admin/reset-history/{username}` — archive l'historique (DEV ONLY, à supprimer en prod)

### Audits #3 #4 #5
- Actions : username injecté dans confirm, gate outlook_token supprimé
- Scheduler : _job_enabled dédupliqué, imports morts
- Frontend : XSS toast (textContent)

## Session 17/04/2026 — Audit & Sécurité (~5 commits)

### Nettoyage post-Sonnet
- 11 scripts de patch non exécutés supprimés (tous obsolètes après refactoring)
- 3 modifications utiles récupérées : prompt TRANSCRIPTION VOCALE + CORRECTIONS VIA CARTE, learned flag
- `google_contacts.py` orphelin supprimé (gmail_connector2.py fait le travail)

### Audit sécurité
- `assert_connection_tenant()` — vérifie qu'une connexion appartient au tenant avant toute opération
- Routes connexions dupliquées 2× dans `tenant_admin.py` → nettoyées
- `_build_tenants_overview()` exposée sans auth → décorateur route supprimé
- Injection credentials par tenant admin → bloquée (forcé `credentials={}`)
- 646 lignes dead code supprimées (`admin.py` + `admin_endpoints.py`)

### Panels séparés (sécurité)
- `/admin/panel` → `require_admin` uniquement (super admin)
- `/tenant/panel` → nouveau template `tenant_panel.html` (tenant admin)
- Tenant admin : 2 onglets seulement (Ma société + Mon profil), zéro accès aux fonctions super admin
- Menu chat (⋮) : routing automatique selon scope

## Session 16-17/04/2026 — Architecture unifiée (~40 commits)

### Raccourcis éditables v2
- Table `user_shortcuts`, API CRUD, modale titre+prompt+couleur, stockage DB

### Sujets intégrés sidebar
- Remplacement du drawer noir par section `<details>` dans la sidebar

### Palette couleurs
- Bleu Roi Saturé #0057b8, fond pastel #f5f9ff

### Système mail complet
- Signature email avec logo, auto-injection dans `_build_email_html`
- Action SEND_MAIL implémentée de bout en bout
- Cartes de confirmation dans le flux chat (persistées en DB)
- Carte mail éditable (De dropdown, À input, Corps textarea)
- Bouton 📁 Brouillon (Outlook Drafts + Gmail Drafts)
- Apprentissage depuis corrections (`learn_from_correction`)

### Architecture connecteurs unifiés
- `MailboxConnector` : Microsoft + Gmail, interface commune
- `DriveConnector` : SharePoint + Google Drive
- `MessagingConnector` : Teams (+ futur Slack/WhatsApp)
- `mailbox_manager.py`, `drive_manager.py`, `messaging_manager.py`
- Tags Raya unifiés : `SEND_MAIL:boite|to|sujet|corps`, `SEARCHDRIVE:drive|query`
- Calendriers unifiés : Microsoft + Google Calendar, 7j, create/update/delete

### Tokens — source unique
- `tenant_connections` = seule source de vérité
- Migration auto au démarrage (`token_migration.py`)
- `oauth_tokens` / `gmail_tokens` dépréciées (tables conservées, zéro écriture)
- Fallbacks legacy supprimés de `mailbox_manager.py`

### Audit cœur Raya (10 fixes)
- MAILBOX_BLOCK dynamique (plus hardcodé Guillaume)
- embed(query) ×1 au lieu de ×4, 5 index DB, pool 2→15
- Cache build_blocks 2-5min, FORMAT_BLOCK module-level
- Soft-delete synthèse, confiance adaptative, dédup RAG robuste

### Panel admin
- Onglet Utilisation (tokens Claude par tenant/user)
- Résumé connexions dans entête tenant
- Display name, modal Paramètres, suppression compte

### Divers
- Bandeau token expiré + bouton reconnecter
- Google contacts via People API (dans GmailConnector2)
- Scope Gmail étendu (mail.google.com + contacts + calendar + drive)
- OAuth admin pour connexions V2

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
