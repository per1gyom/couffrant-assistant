# RAYA — BRIEFING COMPLET POUR ANALYSE DE CODE
**Document de transfert de contexte — Claude Haiku 4.5**
**Date :** 9 avril 2026 | **Repo :** https://github.com/per1gyom/couffrant-assistant
**Production :** https://couffrant-assistant-production.up.railway.app

---

## 1. QU'EST-CE QUE RAYA ?

Raya est un assistant IA personnel déployé pour Guillaume Perrin, dirigeant de **Couffrant Solar** (installateur photovoltaïque, ~5 collaborateurs, Loire, France). Raya est une instance Claude Sonnet avec une mémoire persistante en PostgreSQL. Elle n'est pas un chatbot générique — c'est une assistante qui apprend, mémorise, et s'autonomise progressivement.

**Ce que Raya fait :**
- Analyse et trie les mails entrants (Outlook/Gmail) par Claude
- Répond aux questions sur les projets, chantiers, contacts
- Accède à Teams, SharePoint, calendrier, tâches Outlook
- Gère une mémoire persistante en base (règles, insights, contacts, style)
- S'auto-améliore via des actions apprises : `[ACTION:LEARN:categorie|règle]`

**Philosophie centrale :** Raya décide librement. Le code lui donne des outils et des garde-fous de sécurité. Zéro règle métier codée en dur — tout est en base et évolue par apprentissage.

---

## 2. STACK TECHNIQUE

```
Backend   : FastAPI (Python 3.12) sur Railway
Base      : PostgreSQL (Railway) + pgvector (embeddings 1536 dims)
IA        : Anthropic Claude Sonnet (conversations) + Claude Haiku (analyse mails)
           OpenAI text-embedding-3-small (vectorisation mémoire)
MS365     : OAuth2 MSAL → Graph API (mails, calendrier, Teams, OneDrive/SharePoint)
Sessions  : Starlette SessionMiddleware (cookie chiffré)
Sécurité  : PBKDF2-SHA256 (mots de passe) + Fernet (tokens OAuth)
```

---

## 3. ARCHITECTURE DES FICHIERS

```
app/
├── main.py                  ← Point d'entrée FastAPI + middlewares + startup
├── config.py                ← Variables d'environnement
├── database.py              ← Pool connexions PostgreSQL + schéma + migrations
├── crypto.py                ← Chiffrement Fernet tokens OAuth
│
├── security_auth.py         ← Hash MDP, rate limiting, lockout progressif DB
├── security_users.py        ← CRUD users, auth, must_reset_password
├── security_tools.py        ← Outils par user (drive, outlook, odoo, scopes)
├── app_security.py          ← Shim de compat + LOGIN_PAGE_HTML
│
├── ai_client.py             ← Analyse mails par Claude (prompt conditionnel)
├── rule_engine.py           ← Moteur de règles dynamique (tout vient de aria_rules)
├── embedding.py             ← Vectorisation OpenAI text-embedding-3-small
├── assistant_analyzer.py    ← Analyseur fallback sans API (par mots-clés)
│
├── memory_rules.py          ← Règles aria_rules (save/get/delete)
├── memory_contacts.py       ← Contacts aria_contacts (fiches, rebuild)
├── memory_style.py          ← Style rédactionnel (exemples, corrections)
├── memory_synthesis.py      ← Synthèse sessions + résumé chaud + vectorisation
├── memory_teams.py          ← Mémoire Teams (marqueurs, sync, résumé)
├── memory_loader.py         ← Chargeur avec fallbacks (MEMORY_OK flag)
├── memory_manager.py        ← Shim de compat re-exportant les 4 modules ci-dessus
│
├── token_manager.py         ← Tokens OAuth Microsoft/Google (chiffrés Fernet)
├── dashboard_service.py     ← Regroupement mails pour dashboard
├── feedback_store.py        ← Instructions globales par tenant
├── mail_memory_store.py     ← Helpers mail_memory
├── tenant_manager.py        ← CRUD tenants
│
├── routes/
│   ├── raya.py              ← /raya endpoint principal (conversation)
│   ├── aria_context.py      ← Construction prompt système (parallélisé)
│   ├── aria_actions.py      ← Exécution des [ACTION:xxx] de Raya
│   ├── auth.py              ← Login/logout/OAuth callbacks
│   ├── admin.py             ← Panel admin + CRUD users + déblocage
│   ├── forced_reset.py      ← Redéfinition MDP forcée (première connexion)
│   ├── reset_password.py    ← Reset MDP par email
│   ├── mail.py              ← Ingestion/analyse mails
│   ├── memory.py            ← Routes mémoire (synth, build, status)
│   ├── webhook.py           ← Webhooks Microsoft Graph (réception mails live)
│   ├── outlook.py           ← Routes Outlook spécifiques
│   └── deps.py              ← Guards d'accès (require_user, require_admin...)
│
├── connectors/
│   ├── outlook_connector.py ← Actions Outlook (reply, archive, tâches, calendrier)
│   ├── drive_connector.py   ← SharePoint/OneDrive (list, read, search, move)
│   ├── teams_connector.py   ← Teams (chats, canaux, envoi messages)
│   ├── microsoft_webhook.py ← Gestion abonnements Graph
│   ├── gmail_connector.py   ← Gmail OAuth + ingestion
│   └── odoo_connector.py    ← Odoo (optionnel, partenaires, projets)
│
└── templates/
    ├── aria_chat.html        ← Interface chat principale
    ├── admin_panel.html      ← Panel admin (users, règles, mémoire, sociétés)
    └── forced_reset.html     ← Page reset MDP avec validations live
```

---

## 4. BASE DE DONNÉES — TABLES PRINCIPALES

| Table | Rôle |
|---|---|
| `users` | Comptes (username, password_hash, scope, tenant_id, account_locked...) |
| `oauth_tokens` | Tokens MS/Google **chiffrés Fernet** (provider, username, access, refresh) |
| `mail_memory` | Mails analysés (catégorie, priorité, résumé, suggested_reply...) |
| `aria_memory` | Historique conversations (user_input, aria_response) |
| `aria_rules` | **Règles de Raya** — le cœur de son intelligence (category, rule, confidence) |
| `aria_insights` | Observations de Raya sur l'utilisateur |
| `aria_contacts` | Fiches contacts (nom, email, résumé, dernière interaction) |
| `aria_hot_summary` | Résumé opérationnel chaud (~350 mots, reconstruit par Claude) |
| `aria_profile` | Profil de style rédactionnel de Guillaume |
| `aria_style_examples` | Exemples de mails envoyés pour le few-shot |
| `aria_session_digests` | Synthèses de sessions (résumé, règles apprises, topics) |
| `teams_sync_state` | Marqueurs de position dans les chats Teams (Raya pose elle-même) |
| `tenants` | Sociétés (id, name, settings JSONB dont config SharePoint) |
| `reply_learning_memory` | Corrections de réponses IA (few-shot learning) |
| `gmail_tokens` | Legacy — ne plus écrire ici (données migrées vers oauth_tokens) |

**Colonnes sécurité dans `users` :**
```sql
must_reset_password  BOOLEAN DEFAULT FALSE
account_locked       BOOLEAN DEFAULT FALSE
login_attempts_count INT DEFAULT 0
login_attempts_round INT DEFAULT 0
login_locked_until   TIMESTAMP
```

---

## 5. MÉCANIQUE CENTRALE — COMMENT RAYA APPREND

### Le cycle d'apprentissage

1. **Conversation** → Raya répond et peut émettre des actions d'apprentissage
2. **[ACTION:LEARN:catégorie|règle]** → Sauvegardée dans `aria_rules`
3. **[ACTION:INSIGHT:sujet|observation]** → Sauvegardée dans `aria_insights`
4. **[ACTION:SYNTH:]** → Déclenche la synthèse de session
5. **Synthèse** → Claude analyse les N dernières conversations, extrait règles + insights, vectorise, purge les conversations brutes

### Catégories de règles dans `aria_rules`

- `tri_mails` — classification des mails (catégorie, priorité)
- `urgence` — critères de priorité haute
- `anti_spam` — filtres expéditeurs/sujets
- `style_reponse` — style des réponses Raya
- `regroupement` — logique dashboard
- `contacts_cles` — contacts à surveiller
- `categories_mail` — catégories de mail (Raya les crée/supprime librement)
- `memoire` — paramètres numériques (synth_threshold, keep_recent, purge_days)
- `mail_filter` — whitelist/blacklist webhooks
- `comportement` — comportement général

### Paramètres mémorisés par Raya

```
synth_threshold:15   → synthèse tous les 15 échanges
keep_recent:5        → conserve 5 conversations brutes après synthèse
purge_days:90        → purge les mails de plus de 90 jours
```

---

## 6. CONSTRUCTION DU PROMPT SYSTÈME (aria_context.py)

```python
# PARALLÈLE (ThreadPoolExecutor x4) — gain ~350ms
load_live_mails(outlook_token, username)
load_agenda(outlook_token)
load_teams_context(username)
load_mail_filter_summary(username)

# SÉQUENTIEL (DB rapide)
get_hot_summary(username)
get_aria_rules(username)
get_aria_insights(username)
get_contact_card(name)       # si contact mentionné
get_style_examples(context)  # si mail de réponse probable
```

**Garde-fous absolus (immuables dans le prompt) :**
- Ne jamais supprimer définitivement sans confirmation
- Ne jamais envoyer mail/message Teams sans approbation explicite
- Ne jamais exécuter une action irréversible sans accord clair
- En cas de doute : demander, ne pas agir

---

## 7. ANALYSE DES MAILS — PROMPT CONDITIONNEL (ai_client.py)

```python
# Odoo : uniquement si expéditeur dans la base
include_odoo = odoo_context.get("client_trouve", False)

# Style : uniquement si réponse probable (?, merci de, pouvez-vous...)
style_profile = get_style_profile(username) if needs_reply_hint else ""

# Exemples few-shot : uniquement si catégorie détectée (!= "autre")
learning_examples = get_learning_examples(hint_cat, username) if hint_cat != "autre" else []

# Catégories : dynamiques depuis aria_rules/categories_mail
mail_categories = get_mail_categories(username)
```

Gain : 20-30% de tokens par analyse mail.

---

## 8. SÉCURITÉ EN PLACE

- **MDP** : PBKDF2-SHA256, 12 chars min + maj + min + chiffre + spécial
- **Lockout progressif DB** : 3→5min, 6→30min, 9→blocage définitif + email admin
- **Tokens OAuth** : chiffrés Fernet (`TOKEN_ENCRYPTION_KEY` Railway)
- **Headers HTTP** : CSP, X-Frame-Options, X-Content-Type-Options, X-XSS-Protection
- **Multi-tenants** : isolation complète par `tenant_id`

---

## 9. PERFORMANCE EN PLACE

- **Pool PostgreSQL** : `ThreadedConnectionPool(2, 8)` + wrapper `_PooledConn`
- **Appels MS Graph parallèles** : `ThreadPoolExecutor(max_workers=4)` dans raya.py
- **Cache SharePoint** : `_drive_cache` dict mémoire, TTL 30 min

---

## 10. POINTS DE VIGILANCE CRITIQUES

1. **Deux `get_memoire_param`** avec signatures différentes :
   - `memory_rules.py` → `(param, default, username='guillaume')`
   - `rule_engine.py` → `(username, param, default)`

2. **Imports circulaires** : `security_auth.py` utilise des imports différés à l'intérieur des fonctions. Maintenir ce pattern.

3. **Shim `memory_manager.py`** : toute nouvelle fonction dans les modules mémoire doit être ajoutée ici.

4. **Règle d'or** : toute règle métier → en base, pas dans le code.

5. **`gmail_tokens`** : table en base mais plus alimentée. Peut être droppée manuellement.

---

## 11. SHA FINAL : `8023dd5` (9 avril 2026)

Serveur stable. Log propre. Toutes les migrations appliquées.
