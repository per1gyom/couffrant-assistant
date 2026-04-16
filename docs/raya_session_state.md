# Raya — État de session vivant

**Dernière mise à jour : 17/04/2026 00h30**

---

## ⚠️ RÈGLES IMPÉRATIVES

### Rôles
- **Claude = architecte + codeur direct** via Desktop Commander (git local)
- **Guillaume = décideur** : valide, oriente. Claude explique AVANT de coder. Guillaume valide, Claude exécute.

### Règles techniques
- Desktop Commander local : `/Users/per1guillaume/couffrant-assistant`
- Repo GitHub : `per1gyom/couffrant-assistant` branche `main`
- URL prod : `https://app.raya-ia.fr`
- Template chat : `app/templates/raya_chat.html`
- Cache-bust : **v=61** (17/04/2026)
- **⚠️ ARCHITECTURE ADMIN** : Routes dans le **package** `app/routes/admin/` (pas le fichier `admin.py` qui est shadowed)
- **⚠️ JAMAIS** supprimer `async function init()` dans `chat-main.js`
- **⚠️ TOUJOURS** bumper `v=` lors d'une modif JS/CSS
- Français, vocabulaire Terminal, concis

---

## 🧠 PHILOSOPHIE DE DÉVELOPPEMENT — NOTE FONDAMENTALE

### La règle des trois cercles avant de coder

Avant toute modification, examiner trois niveaux :
1. **Le fichier touché** — ce que le patch change directement
2. **Tous les fichiers qui l'appellent ou qu'il appelle** — les dépendances immédiates
3. **La finalité commerciale** — est-ce que ça scale à 100 tenants, 50 boîtes, 10 providers ?

**Exemple de ce qui arrive quand on ne le fait pas** :
- On code `SEND_MAIL` pour Microsoft
- On patch `SEND_GMAIL` par-dessus
- On re-patch les contacts Gmail
- Au bout de 3 semaines on a 5 fonctions qui font la même chose différemment
→ Résultat : code fragile, impossible à maintenir, non commercialisable

**La bonne approche** :
- Se poser la question *"Qu'est-ce qui va changer ?"* avant de coder
- Identifier le point d'extension → mettre une interface derrière
- Un seul endroit pour chaque responsabilité (Single Responsibility)
- Chaque nouveau provider / boîte / tenant doit fonctionner sans modification de code

### Les 4 critères de qualité du projet Raya
1. **Stable** — zéro régression sur l'existant quand on ajoute du nouveau
2. **Sécurisé** — isolation tenants, tokens chiffrés, aucune fuite inter-comptes
3. **Adaptable** — ajouter un provider mail en 1 fichier, pas 10 modifications
4. **Commercialisable** — un client peut s'onboarder sans Guillaume coder quoi que ce soit

### Quand quelque chose est cassé
1. D'abord comprendre **pourquoi** ça s'est cassé (pas juste patcher le symptôme)
2. Vérifier si le problème n'est pas le signe d'une mauvaise architecture
3. Si oui → refactorer d'abord, patcher ensuite
4. Toujours vérifier l'impact sur les autres composants avant de commit

---

## ⭐ ÂME DU PROJET
Raya = cerveau supplémentaire pour dirigeant.
LLM-agnostic, tools-agnostic, channel-agnostic, provider-agnostic.

---

## 1. Stack
FastAPI Python 3.13, Railway, PostgreSQL, Anthropic.
URL : `https://app.raya-ia.fr` — Repo : `per1gyom/couffrant-assistant` main

---

## 2. ARCHITECTURE CONNECTEURS — NOUVEAU SYSTÈME (17/04/2026)

### 2.1 MailboxConnector — interface unifiée

**Fichiers clés :**
- `app/connectors/mailbox_connector.py` — interface abstraite (Contact, CalendarEvent, MailMessage)
- `app/connectors/microsoft_connector.py` — implémentation Microsoft Graph
- `app/connectors/gmail_connector2.py` — implémentation Gmail + Google Calendar + People API
- `app/mailbox_manager.py` — resolver central

**Principe :**
```
get_user_mailboxes(username)
  → [MicrosoftConnector(contact@couffrant.fr), GmailConnector(per1.gmail.com)]

Chaque connecteur expose :
  .search_contacts(query)    .create_contact(name, email, phone)
  .send_mail(to, subj, body) .create_draft(to, subj, body)
  .get_agenda(days)          .create_event(...) .update_event(...) .delete_event(...)
```

**Ajouter un nouveau provider :**
1. Créer une classe héritant de `MailboxConnector`
2. L'enregistrer dans `PROVIDER_MAP` dans `mailbox_manager.py`
→ Rien d'autre. Zéro modification du reste du code.

**Fonctions publiques de `mailbox_manager.py` :**
- `get_user_mailboxes(username)` → liste des connecteurs actifs
- `get_mailbox_summary(username)` → string lisible pour le prompt
- `get_connector_for_mailbox(username, hint)` → résolution par email/provider/alias
- `search_contacts_all(username, query)` → recherche dans toutes les boîtes
- `create_contact_best(username, name, email, phone)` → crée dans la boîte la plus adaptée
- `load_agenda_all(username, days=7)` → agenda de toutes les boîtes, trié
- `execute_calendar_action(username, action, provider_hint, **kwargs)` → calendrier unifié

### 2.2 Tokens — Source de vérité unique

**Avant :** 3 tables parallèles (oauth_tokens, gmail_tokens, tenant_connections)
**Après :** tenant_connections = seule source de vérité

```
tenant_connections (id, tenant_id, tool_type, label, credentials JSONB, connected_email, status)
  + connection_assignments (connection_id, username, access_level, enabled)
```

**Migration auto au démarrage** : `app/token_migration.py` → `migrate_tokens_to_v2()`
- Scanne `oauth_tokens` + `gmail_tokens`
- Crée les `tenant_connections` + `connection_assignments` correspondants
- Idempotent

**OAuth callbacks** : `auth.py` écrit maintenant dans les deux (V2 + legacy pendant transition)
- `_save_ms_token_v2(username, oauth_result)`
- `_save_gmail_token_v2(username, tokens, email)`

**Ordre de résolution dans `mailbox_manager` :**
1. V2 : `tenant_connections` via `connection_assignments`
2. Legacy : `oauth_tokens` (fallback)
3. Legacy : `gmail_tokens` (fallback)

### 2.3 Actions mail unifiées

**Avant :** SEND_MAIL (Outlook) + SEND_GMAIL (Gmail) = 2 tags hardcodés
**Après :** Un seul tag universel

```
[ACTION:SEND_MAIL:boite|to|sujet|corps]
  boite = email exact | 'gmail' | 'microsoft' | 'perso' | 'pro' | '' (auto)
```

**Résolution par alias (`get_connector_for_mailbox`) :**
- gmail/google/perso/boite perso → connecteur Gmail
- microsoft/outlook/office/pro/boite pro → connecteur Microsoft
- email exact → connecteur correspondant
- '' / auto → premier disponible

**Backward compat :** ancien format 3 champs (`to|sujet|corps`) et `SEND_GMAIL` toujours supportés

### 2.4 Calendriers unifiés

**Avant :** Microsoft seulement, aujourd'hui seulement
**Après :** Microsoft + Google Calendar, 7 jours glissants

```
load_agenda_all(username, days=7)
  → fusionne tous les calendriers, trié par date
  → chaque event : source + calendar_email

Actions :
  CREATEEVENT:boite|sujet|debut|fin|lieu|participants
  UPDATE_EVENT:event_id|champ=valeur
  DELETE_EVENT:event_id
```

**Scopes Gmail requis** (reconnexion nécessaire après ajout) :
- `https://mail.google.com/`
- `https://www.googleapis.com/auth/contacts`
- `https://www.googleapis.com/auth/calendar`

### 2.5 Contacts unifiés

**Avant :** Microsoft Graph seulement
**Après :** toutes les boîtes connectées

```
SEARCH_CONTACTS:Charlotte
  → cherche dans Microsoft ET Gmail ET toute future boîte
  → retourne nom, email, source

CREATE_CONTACT:Nom|email|téléphone
  → crée dans la boîte la plus adaptée (Gmail en priorité)
```

---

## 3. ÉTAT FONCTIONNEL ✅ COMPLET

### Infrastructure
- Stack FastAPI + Railway + PostgreSQL + Anthropic ✅
- Multi-tenant (tenant_connections + connection_assignments) ✅
- Sécurité (bcrypt, lockout, CSRF partiel, cloisonnement tenants) ✅
- Panel admin complet (super admin + tenant admin + profil) ✅
- RGPD (export + suppression avec workflow admin) ✅
- Backup manuel ✅

### Chat & UX
- Redesign complet v2 (palette bleu #0057b8, sidebar, SVG icons, markdown) ✅
- Raccourcis éditables (DB, CRUD, modale, 12 couleurs) ✅
- Sujets sidebar ✅
- Historique chat persistant avec action cards ✅
- Carte mail éditable (De dropdown, À input, Corps textarea) ✅
- Payload override sur confirm ✅

### Mail
- Envoi Outlook + Gmail via MailboxConnector ✅
- SEND_MAIL unifié (résolution automatique provider) ✅
- Brouillons Outlook + Gmail ✅
- Signatures email WYSIWYG (multi-boîtes, défaut) ✅
- SEARCH_CONTACTS toutes boîtes ✅
- CREATE_CONTACT (Gmail en priorité) ✅

### Calendriers
- Microsoft Calendar 7j glissants ✅
- Google Calendar 7j glissants ✅
- CREATEEVENT / UPDATE_EVENT / DELETE_EVENT multi-provider ✅

### Admin panel
- Onglets : Mémoire, Règles, Insights, Actions, Sociétés, Mon profil ✅
- Connexions V2 : créer, assigner, OAuth Microsoft/Gmail depuis panel ✅
- Toutes les actions quick (build-memory, synth, analyze, etc.) fonctionnelles ✅
- adminConfirmDelete / adminRejectDelete définis ✅
- Routes /tenant/connections CRUD ✅

### Tokens & Connexions
- tenant_connections = source de vérité unique ✅
- Migration auto au démarrage (idempotent) ✅
- OAuth callbacks écrivent en V2 + legacy ✅

---

## 4. CHANTIERS RESTANTS (PAR PRIORITÉ)

### #4 — Drive unifié (NEXT)
SharePoint + Google Drive via `DriveConnector`. Même architecture que MailboxConnector.
Fichiers à créer : `app/connectors/drive_connector2.py` (GoogleDriveConnector + SharePointConnector), `app/drive_manager.py`
Actions : SEARCHDRIVE, READDRIVE, LISTDRIVE, MOVEDRIVE, COPYFILE

### #5 — Messagerie unifiée
Teams (actuel) + Slack + WhatsApp Business. `MessagingConnector` abstrait.

### #6 — Nettoyer legacy
Quand migration V2 confirmée en prod → supprimer fallbacks `oauth_tokens`/`gmail_tokens` dans `mailbox_manager.py`, puis supprimer les tables.

### #7 — Notifications temps réel
Webhooks Microsoft + Google Pub/Sub → Raya réagit sans polling.

### #8 — Google OAuth vérification
Passer le projet OAuth en mode "Externe" + soumettre vérification Google pour tokens permanents (obligatoire avant commercialisation).

### #9 — Tests et robustesse
Tests d'intégration connecteurs, monitoring, alertes Railway.

---

## 5. BUGS CONNUS

| # | Signalé par | Description | Priorité |
|---|---|---|---|
| 1 | Guillaume | Archivage mail 404 MS Graph (iPhone) | Moyen |
| 2 | Guillaume | Archivage mail 404 MS Graph (bureau) | Moyen |
| - | - | Bandeau Gmail "Connexion expirée" faux positifs → désactivé temporairement | Bas |

---

## 6. ARCHITECTURE FICHIERS CLÉS

```
app/
├── connectors/
│   ├── mailbox_connector.py     # Interface abstraite + modèles (Contact, CalendarEvent, MailMessage)
│   ├── microsoft_connector.py   # Microsoft Graph (mail, contacts, calendrier)
│   ├── gmail_connector2.py      # Gmail + People API + Google Calendar
│   ├── gmail_connector.py       # Legacy (get_gmail_service, send_gmail_message) — garder
│   ├── gmail_auth.py            # OAuth Google (scopes: mail + contacts + calendar)
│   ├── outlook_connector.py     # Legacy Outlook — garder
│   └── google_contacts.py       # Legacy — à supprimer quand gmail_connector2 stable
│
├── mailbox_manager.py           # Resolver central : get_user_mailboxes(), get_connector_for_mailbox()
├── connection_token_manager.py  # V2 tokens : get_connection_token(), save_connection_oauth_token()
├── token_migration.py           # Migration auto oauth_tokens+gmail_tokens → tenant_connections
├── connections.py               # CRUD tenant_connections
│
├── routes/
│   ├── auth.py                  # OAuth callbacks (écrit en V2 + legacy)
│   ├── admin_oauth.py           # OAuth super admin par connexion tenant
│   ├── raya.py                  # Endpoints /raya, /token-status, /raya/confirm (avec payload_override)
│   ├── raya_helpers.py          # _raya_core() + _get_microsoft_token() V2
│   ├── actions/
│   │   ├── mail_actions.py      # SEND_MAIL unifié + SEARCH_CONTACTS + CREATE_CONTACT
│   │   └── confirmations.py     # _execute_confirmed_action() avec username extrait
│   ├── aria_context.py          # build_system_prompt() + résumé boîtes connectées
│   ├── aria_loaders.py          # load_agenda() → load_agenda_all()
│   └── prompt_actions.py        # Tags Raya (SEND_MAIL unifié, SEARCH_CONTACTS, calendriers)
│
└── templates/
    ├── raya_chat.html           # v=61, carte mail éditable
    └── admin_panel.html         # Panel admin (sans onglet Utilisateurs doublon)

app/static/
├── chat-main.js                 # init() + loadHistory() + sendMessage()
├── chat-messages.js             # appendPendingActionToChat() avec champs éditables
├── chat-core.js                 # loadUserInfo() (scope élargi admin/super_admin/couffrant_solar)
├── chat-admin.js                # drawerAction() + drawerActionPost()
└── admin-panel.js               # adminConfirmDelete() + adminRejectDelete()
```

---

## 7. DÉCISIONS CLÉS ET RATIONALE

| Décision | Raison |
|---|---|
| MailboxConnector abstrait | Ajout provider = 1 fichier, 0 autre modif |
| tenant_connections = source unique | Fin des 3 tables parallèles, isolation tenants garantie |
| SEND_MAIL unifié | Scalable à N boîtes, résolution automatique par alias |
| load_agenda_all() | Microsoft + Google Calendar dans une seule vue |
| Carte mail éditable | Raya propose, Guillaume valide et corrige avant envoi |
| payload_override sur confirm | Modifications de dernière minute sans re-générer |
| Migration auto idempotente | Zéro intervention manuelle en prod |
| Bandeau token désactivé | Trop de faux positifs → refaire proprement plus tard |
| Route /admin/panel sans re-auth | La re-auth toutes les 10 min bloquait l'accès |
| Scope contacts+calendar Gmail | Reconnexion Gmail nécessaire pour les activer |

---

## 8. HISTORIQUE SESSIONS

### Session 17/04/2026 (commits 526dab8 → b193ceb)
**Connecteurs V2 Phase C complets + Architecture multi-boîtes**

Commits principaux :
- `526dab8` — Connecteurs V2 Phase C : token resolver, OAuth super admin, UI admin
- `d052ebd` — gmail_service V2, get_mailboxes V2, _get_user_email V2, token-status V2
- `e701c6b` — HOTFIX : async function init() manquante (tout cassait)
- `8375817` — bandeau token : Connexion expirée + adresse compte
- `1dd33fc` — Audit admin : POST extract-signatures+onboarding, adminConfirmDelete, routes /tenant/connections
- `c741e55` — Carte mail éditable (De dropdown, À input, Corps textarea)
- `5896520` — MailboxConnector unifié : architecture multi-boîtes
- `21c3ba4` — Calendriers unifiés Microsoft + Google Calendar
- `c500e09` — SEND_MAIL unifié multi-boîtes
- `b193ceb` — Migration tokens V2 auto au démarrage

**Bugs introduits et corrigés dans cette session :**
- `async function init()` supprimée accidentellement → tout plantait (raccourcis, sujets, historique, admin)
- `username` non défini dans endpoint confirm async → ❌ sur tous les envois
- `username` non défini dans `_execute_confirmed_action` → même bug
- Décorateur `@router.get('/init-db')` supprimé → 404 sur routes admin
- `conversation_id` absent de `pending_actions` en DB → historique vide

**Leçons apprises :**
→ Toujours vérifier la syntaxe JS avant commit : `node --check fichier.js`
→ Toujours bumper le cache-bust `v=` après toute modif JS
→ Ne jamais supprimer `async function init()` de chat-main.js
→ Les modifications par `str_replace` doivent vérifier le contexte complet

---

## 9. REPRISE DE SESSION

Pour reprendre :
```
Bonjour Claude. Projet Raya, Guillaume Perrin (Couffrant Solar).
On se tutoie, en français, vocabulaire Terminal, concis.
Lis docs/raya_session_state.md sur per1gyom/couffrant-assistant main.
Reprends où on en était.
```

**Avant de coder quoi que ce soit**, appliquer la règle des 3 cercles :
1. Quel fichier est touché ?
2. Quels fichiers l'appellent ou sont appelés ?
3. Est-ce que ça scale ? Est-ce commercial ?

Si la réponse à une de ces questions impose un refactoring → refactorer d'abord.
