# Raya — État de session vivant

**Dernière mise à jour : 18/04/2026 — refonte intelligence, auto-découverte, graphe de relations, Opus 4.7**

---

## ⚠️ RÈGLES IMPÉRATIVES

### Rôles
- **Claude = architecte + codeur direct** via Desktop Commander (git local)
- **Guillaume = décideur** : valide, oriente. Claude explique si besoin, execute sinon.

### Règles techniques
- Desktop Commander local : `/Users/per1guillaume/couffrant-assistant`
- Repo GitHub : `per1gyom/couffrant-assistant` branche `main`
- URL prod : `https://app.raya-ia.fr`
- Cache-bust JS/CSS : **v=29** (admin-panel.js) / **v=65** (chat)
- **⚠️ PANELS SÉPARÉS** : `/admin/panel` → super admin only / `/tenant/panel` → tenant admin only
- **⚠️ ARCHITECTURE ADMIN** : Routes dans le **package** `app/routes/admin/`
- **⚠️ JAMAIS** supprimer `async function init()` dans `chat-main.js`
- **⚠️ TOUJOURS** bumper `v=` lors d'une modif JS/CSS

---

## 🧠 PHILOSOPHIE DE DÉVELOPPEMENT

### Règle des 3 cercles avant de coder
1. Quel fichier est touché ?
2. Quels fichiers l'appellent ou sont appelés ?
3. Est-ce que ça scale ? Est-ce commercial ?

**Si la réponse à une de ces questions impose un refactoring → refactorer d'abord.**

### 4 critères qualité
1. **Stable** — zéro régression sur l'existant
2. **Sécurisé** — isolation tenants, tokens chiffrés
3. **Adaptable** — ajouter un provider = 1 fichier
4. **Commercialisable** — un client s'onboarde sans code

---

## ⭐ ÂME DU PROJET
Raya = cerveau supplémentaire pour dirigeant.
LLM-agnostic, tools-agnostic, channel-agnostic, provider-agnostic.

---

## ARCHITECTURE CONNECTEURS — SYSTÈME UNIFIÉ ✅

### Pattern universel (mail, drive, messagerie)
```
get_user_XXXX(username) → liste connecteurs actifs
  → Chaque connecteur expose une interface commune
  → Ajouter un provider = 1 fichier + 1 ligne PROVIDER_MAP
  → Zéro modification du reste du code
```

### MailboxConnector
- `app/connectors/mailbox_connector.py` — interface abstraite
- `app/connectors/microsoft_connector.py` — Microsoft Graph
- `app/connectors/gmail_connector2.py` — Gmail + Calendar + Contacts
- `app/mailbox_manager.py` — resolver + get_connector_for_mailbox(username, hint)
- Hints reconnus : 'gmail'/'perso'/'google' → Gmail | 'microsoft'/'outlook'/'pro' → MS

### DriveConnector
- `app/connectors/drive_connector_base.py` — interface abstraite
- `app/connectors/sharepoint_connector.py` — wraps drive_read.py
- `app/connectors/google_drive_connector.py` — Google Drive API v3
- `app/drive_manager.py` — resolver

### MessagingConnector
- `app/connectors/messaging_connector.py` — interface abstraite
- `app/connectors/teams_connector2.py` — wraps teams_connector.py + teams_actions.py
- `app/messaging_manager.py` — resolver

### Tags Raya unifiés
```
[ACTION:SEND_MAIL:boite|to|sujet|corps]     ← boite = 'gmail'|'microsoft'|email|''
[ACTION:SEARCHDRIVE:drive|query]             ← drive = 'google'|'sharepoint'|''
[ACTION:CREATEEVENT:boite|sujet|debut|fin|lieu|participants]
[ACTION:UPDATE_EVENT:id|champ=valeur]
[ACTION:DELETE_EVENT:id]
```

---

## TOKENS — SOURCE DE VÉRITÉ UNIQUE ✅

`tenant_connections` = seule source.
`oauth_tokens` / `gmail_tokens` = DEPRECATED (tables gardées en DB, aucune écriture).

- Migration auto au démarrage : `app/token_migration.py` → `migrate_tokens_to_v2()`
- OAuth callbacks : écrivent uniquement dans `tenant_connections`
- `mailbox_manager` : V2 uniquement (fallbacks supprimés)
- `get_all_users_with_tool_connections(tool_type)` dans `connection_token_manager.py`

---

## AUDIT CŒUR RAYA — CORRIGÉ ✅ (17/04/2026)

| # | Problème | Fix appliqué |
|---|---|---|
| 1 | MAILBOX_BLOCK hardcodé Guillaume | `_build_mailbox_block()` dynamique depuis connexions réelles |
| 2 | /token-status lisait oauth_tokens/gmail_tokens | V2 pur |
| 3 | Import `_legacy_ms_token` mort | Supprimé de raya.py + raya_helpers.py |
| 4 | 3 appels DB à chaque message | Cachés 5 min |
| 5 | `if True:` + pool réassigné 2× | Nettoyés |
| 6 | 2 ThreadPoolExecutor parallèles | Un seul pool dans raya_helpers.py |
| 7 | 6 regex redondantes pour clean_response | Réduit à 2 |
| 8 | DELETE irréversible dans synthesize_session | Soft-delete (archived=true) avec fallback |
| 9 | Confiance synthèse fixe à 0.6 | 0.5 initial + reinforcement naturel |
| 10 | Cache hot_summary sans TTL, dédup RAG fragile | TTL 30min + invalidation sur rebuild + dédup robuste |

---

## CHANTIERS ARCHITECTURE — TOUS COMPLÉTÉS ✅

| # | Chantier |
|---|---|
| 1 | SEND_MAIL unifié multi-boîtes |
| 2 | Calendriers unifiés Microsoft + Google |
| 3 | Tokens → tenant_connections source unique |
| 4 | Drive unifié SharePoint + Google Drive |
| 5 | Messagerie unifiée Teams → MessagingConnector |
| 6 | Legacy tokens nettoyés |
| 7 | Webhooks + polling branchés sur V2 |

---

## REFONTE INTELLIGENCE (18/04/2026) ✅

### Prompt restructuré
- Identité : "Tu es Claude, modèle d'Anthropic" → intelligence native libérée
- Ordre : CONTEXTE d'abord (qui est l'utilisateur, ses données) → RÈGLES à la fin
- GUARDRAILS condensés : 370 lignes → 30 lignes (sécurité uniquement)
- Moins de hardcode, plus d'intelligence naturelle

### Paramètres
- Historique : 6 → **30 échanges** (continuité conversation)
- max_tokens : 2048 → **8192** (réponses complètes)
- Routeur : seuils assouplis, quota Opus 20 → **50/jour**
- Rate limiter : 60 → **120 requêtes/heure**

### Anti-bluff
- CORE_RULES : "Ne promets jamais de faire quelque chose si tu n'as pas la syntaxe d'action"

---

## AUTO-DÉCOUVERTE DES OUTILS (18/04/2026) ✅

### Principe
Les outils connectés ne sont plus décrits par des listes hardcodées.
Raya explore l'outil, vectorise sa structure, et retrouve la connaissance
pertinente via RAG à chaque conversation.

### Architecture
```
tool_schemas (table DB + embeddings vectoriels)
  → tenant_id, tool_type, entity_key, description, fields_json, embedding
  → Index HNSW pour recherche par similarité

discover_odoo(tenant_id)
  → Explore les modèles business Odoo (contacts, devis, factures, projets...)
  → Pour chaque modèle : champs, relations, description naturelle
  → Vectorise et stocke dans tool_schemas

retrieve_tool_knowledge(query, tenant_id)
  → Appelé automatiquement dans build_system_prompt
  → Retourne les schémas pertinents pour la question de l'utilisateur
```

### Routes admin
- `POST /admin/discover/{tenant_id}/odoo` → lance la découverte
- `GET /admin/discovery-status/{tenant_id}` → état de la découverte
- `GET /admin/reset-history/{username}` → archive l'historique conversation (DEV ONLY — à supprimer en production, la mémoire continue doit être préservée)

### Roadmap connaissance vectorisée
- [x] Schémas Odoo (auto-découverte)
- [x] Dossiers + fichiers récents Drive (SharePoint + Google Drive)
- [x] Événements calendrier (Microsoft + Google) + participants
- [x] Contacts fréquents (depuis mail_memory, ≥2 échanges)
- [ ] Vocabulaire métier (termes extraits des conversations)
- [ ] Blueprints connecteurs (templates réutilisables Odoo, Salesforce...)

### Roadmap proactivité (VISION PRIORITAIRE)
Principe : Raya ne doit PAS attendre qu'on l'interroge. Elle analyse en continu
et alerte quand c'est pertinent. Elle croise TOUTES ses sources à chaque événement.

**Niveau 1 — Proactivité événementielle (prochaine étape)**
Architecture : ÉVÉNEMENT → GRAPHE DE RELATIONS → RÈGLES UTILISATEUR → ACTION
- Graphe d'entités en PostgreSQL (table entity_links) — relie contacts, factures,
  mails, fichiers, échanges Teams entre eux par entité (nom, email, société)
- Se met à jour en continu via webhooks + polls sur CHAQUE outil connecté
  (Odoo, Gmail, Outlook, Teams, Drive, calendrier, tout futur outil)
- Quand un événement arrive → lookup graphe → contexte complet en 2ms
- Évaluation des règles utilisateur → action automatique si pertinent
- Canaux d'alerte : chat, WhatsApp, app mobile (push), mail proactif

**Niveau 2 — Supervision contextuelle (moyen terme)**
- Raya voit ce que l'utilisateur fait dans ses outils connectés
  (quel mail il lit, quel dossier il ouvre, quel contact il consulte)
- Anticipe et enrichit : "Tu lis le mail de X — note : facture impayée 81k€"
- Nécessite des webhooks plus fins (lecture mail, navigation Drive)

**Niveau 3 — Copilote poste de travail (vision long terme)**
- Agent local (extension navigateur ou app desktop native — OBLIGATOIRE pour perf)
- Raya voit l'écran, comprend le contexte de travail
- "Mode travail" activable par l'utilisateur
- NE SE CONTENTE PAS d'observer : PROPOSE DE FAIRE
  ("Tu commences un devis → je te le rédige, tu vérifies et on valide")
  ("Ce formulaire → je pré-remplis les champs, tu corriges si besoin")
- Apprentissage progressif : détecte les patterns de travail, propose des optimisations
  ("La dernière fois cette étape t'a pris 20 min, je peux la faire en 30 secondes")
- Toujours avec validation — suggestions + pré-actions, jamais d'autonomie non approuvée
- Vision "Jarvis" : assistant omniscient, proactif, qui agit
- PISTE PARTENARIAT : contacter Anthropic quand le produit est stable + clients payants
  → solution verticale PME sur API Claude = cas d'usage que Anthropic recherche

Règles utilisateur : "si facture impayée > 10k€ + mail paiement → préviens Arlène"
→ stockées dans aria_rules, évaluées à chaque événement

### Audits périodiques (PROCESS CONTINU)
À chaque session de développement majeure, faire un audit vision d'ensemble :
- Le projet va-t-il dans la direction du but final (copilote proactif) ?
- A-t-on oublié des améliorations possibles ?
- Les choix techniques sont-ils toujours les bons ?
- Les 4 couches (temps réel, vectorisation, graphe, proactivité) progressent-elles ?
Fréquence recommandée : tous les 5-10 sessions ou avant chaque milestone majeur.

NOTE DEV : /admin/reset-history est DEV ONLY — en production, mémoire préservée.

---

## PANEL ADMIN ✅

- Onglet **Utilisation** : tokens Claude par tenant + par user (appels, tokens in/out)
- Onglet **Sociétés** : résumé connexions dans entête `📧 2/2 · 📁 1/1 · 🔧 0/1`
- Option A : super admin crée toutes les connexions OAuth, tenant admin assigne
- Vue facturation : comptage connexions actives par tenant

---

## FICHIERS CLÉS

```
app/
├── connectors/
│   ├── mailbox_connector.py / microsoft_connector.py / gmail_connector2.py
│   ├── drive_connector_base.py / sharepoint_connector.py / google_drive_connector.py
│   └── messaging_connector.py / teams_connector2.py
├── mailbox_manager.py / drive_manager.py / messaging_manager.py
├── connection_token_manager.py   # V2 tokens — source de vérité
├── token_migration.py            # migration auto idempotente
├── routes/
│   ├── raya.py + raya_helpers.py # flux principal — pool unique, imports propres
│   ├── aria_context.py           # build_system_prompt — MAILBOX_BLOCK dynamique
│   ├── aria_loaders.py           # load_agenda_all
│   ├── prompt_actions.py         # tags Raya unifiés
│   └── actions/
│       ├── mail_actions.py       # SEND_MAIL unifié + _queue_send_mail
│       └── confirmations.py      # SEND_MAIL/TEAMS/DRIVE via managers
├── memory_synthesis.py           # synthesize_session — soft-delete
├── synthesis_engine.py           # rebuild_hot_summary — invalide cache
├── rag.py                        # RAG — retrieve_context
└── templates/admin_panel.html    # super admin — onglet Utilisation
└── templates/tenant_panel.html   # tenant admin — Ma société + Profil uniquement
```

---

## AUDITS PLANIFIÉS — DANS L'ORDRE

1. **Performance** ✅ FAIT (17/04)
2. **Sécurité** ✅ FAIT (17/04)
3. **Système d'actions** ✅ FAIT (18/04) — username confirm, gate token supprimé, CREATEFOLDER V2, cleanup stuck
4. **Scheduler/jobs** ✅ FAIT (18/04) — architecture propre, _job_enabled dédupliqué
5. **Frontend** ✅ FAIT (18/04) — XSS toast fixé, code mort nettoyé

---

## AUDIT SÉCURITÉ — RÉSULTATS (17/04/2026)

### Corrigé
| # | Faille | Fix |
|---|--------|-----|
| 1 | Routes connexions dupliquées 2× dans tenant_admin.py | Doublon supprimé |
| 2 | Aucune vérification tenant sur connection_id | `assert_connection_tenant()` ajouté partout |
| 3 | `_build_tenants_overview()` accessible sans auth | Décorateur route supprimé |
| 4 | Tenant admin pouvait injecter credentials | Forcé `credentials={}` |
| 5 | `/admin/panel` accessible aux tenant admins | Verrouillé `require_admin`, redirect vers `/tenant/panel` |
| 6 | Fonctions masquées côté JS pour tenant admin | **Panels séparés** : `admin_panel.html` (super admin) / `tenant_panel.html` (tenant admin) |
| 7 | 646 lignes dead code (admin.py + admin_endpoints.py) | Supprimées |

### Vérifié OK (pas d'intervention)
- Isolation données : toutes les requêtes filtrent par username/tenant_id ✅
- RAG : scoped par username + tenant_id ✅
- Pending actions : vérifie username + tenant_id ✅
- `list_users()` : derrière `require_admin` only ✅
- `/profile` : propres données uniquement ✅

---

### Priorité haute (avant commercialisation)
- [ ] Google OAuth → passer en mode "Externe" + vérification Google
- [ ] Reconnexion Gmail requise (scopes contacts + calendar + drive ajoutés)

### Panel admin
- [ ] Création tenant : étape "Outils" pour définir les connexions souhaitées
- [ ] Configuration Drive dans tenant_connections.config (remplace tenants.settings)

### Commercial
- [ ] C4 WhatsApp production
- [ ] C5 Facturation Stripe
- **Objectif : premier client payant juillet 2026**

---

## 🔮 Évolutions optionnelles (nice-to-have, non bloquantes)

### UX chat
- **Loader contextuel** : détecter les mots-clés du prompt utilisateur pour afficher
  un texte italique adapté pendant la réflexion (ex: "Interrogation Odoo…" si la
  question parle de devis, "Lecture de tes mails…" si elle parle de mails,
  "Croisement de tes sources…" pour les synthèses cross-source).
  Code à modifier : `addLoading()` dans `chat-messages.js`. Ajouter un paramètre
  `queryHints` passé depuis `sendMessage()` après analyse simple du texte.

### Tests automatisés
- Protocole de tests via Claude in Chrome → voir `docs/raya_test_protocol.md`.
  Permet à Claude de piloter le navigateur et d'exécuter des batteries de tests
  (CHAT-BASELINE, CARTES-MAIL, GRAPHE, ODOO-ACTIONS, UX-SCROLL) pour détecter
  les régressions après chaque déploiement. Validation humaine pour actions sensibles.

---

## REPRISE

```
Bonjour Claude. Projet Raya, Guillaume Perrin (Couffrant Solar).
Tutoiement, français, Terminal, concis.
Lis docs/raya_session_state.md sur per1gyom/couffrant-assistant main.
Lis aussi docs/raya_changelog.md et docs/raya_test_protocol.md si pertinent.
```
