# Raya — État de session vivant

**Dernière mise à jour : 14/04/2026 01h30** — Opus

---

## ⚠️ RÈGLES IMPÉRATIVES (NON NÉGOCIABLES)

### Rôles
- **Opus = architecte UNIQUEMENT** : audite via GitHub MCP, conçoit, rédige des prompts pour Sonnet. NE CODE PAS. N'utilise PAS Chrome pour coder. Ne pousse PAS de code Python.
- **Sonnet = exécutant** : reçoit les prompts copiés par Guillaume, code, pousse sur `main`.
- **Guillaume = décideur** : valide, teste, copie les prompts entre Opus et Sonnet.

### Workflow des prompts Opus → Sonnet
- Opus rédige des prompts PRÉCIS avec le code exact à écrire
- **⚠️ COMMITS COURTS OBLIGATOIRES** : 1 fichier par commit max. Les gros commits (>15KB) timeout le MCP GitHub systématiquement.
- Chaque prompt doit préciser : repo, branche, nombre de commits, UN fichier par commit
- Fichiers > 15KB (raya.py, main.py, chat.css) : modifications CHIRURGICALES uniquement (quelques lignes ajoutées/modifiées, pas de réécriture complète)
- Fin de chaque prompt : « Rapport pour Opus : fichier(s) modifié(s), SHA du commit. »
- JAMAIS `push_files` pour du code Python — corrompt les `\n`.
- Opus peut pousser directement : fichiers de config, docs (.md), CSS simples, nouveaux petits fichiers (<10KB)

### Règles projet
- Cache-bust : bumper `?v=N` dans aria_chat.html à chaque modif CSS/JS (actuellement v=3)
- Aucune écriture sans ok explicite de Guillaume
- Langue : français, vocabulaire "Terminal", concis

---

## ⭐ ÂME DU PROJET
Raya = cerveau supplémentaire pour dirigeant. 8 dimensions, 3 modes.
LLM-agnostic, tools-agnostic, channel-agnostic.
Raya ne connait PAS le mot "Jarvis".
Philosophie : Raya décide librement. Le code lui donne des outils et des garde-fous.
Zéro règle métier codée en dur — tout est en base et évolue par apprentissage.

## 1. Stack
FastAPI Python 3.13, Railway, PostgreSQL+pgvector, Anthropic 3 tiers, OpenAI embeddings.
Repo `github.com/per1gyom/couffrant-assistant` branche `main`.
URL principale : `https://app.raya-ia.fr` (DNS Squarespace CNAME)
URL technique : `https://couffrant-assistant-production.up.railway.app`
Service Railway renommé "Raya" (ex "Aria").

## 2. CONNECTIVITÉ — 5/5 ✅

| Service | Statut | Détail |
|---|---|---|
| Microsoft 365 | 🟢 | Token valide, Graph API |
| Gmail | 🟢 | PKCE bypass — échange HTTP direct |
| Odoo | 🟢 | entreprisecouffrant.openfire.fr |
| Twilio/WhatsApp | 🟢 | Sandbox, webhook actif |
| ElevenLabs | 🟢 | Clé + voice_id configurés |

## 3. OUTILS DE CRÉATION — TOUS OPÉRATIONNELS ✅

| Outil | Fichier | Action LLM | Statut |
|---|---|---|---|
| Création PDF | `app/connectors/file_creator.py` | `[ACTION:CREATE_PDF:titre\|contenu]` | ✅ |
| Création Excel | `app/connectors/file_creator.py` | `[ACTION:CREATE_EXCEL:titre\|headers\|lignes]` | ✅ |
| Création images | `app/connectors/dalle_connector.py` | `[ACTION:CREATE_IMAGE:description]` | ✅ |
| Lecture PDF | `app/connectors/pdf_reader.py` | Auto sur upload PDF | ✅ |
| Téléchargement | `app/routes/downloads.py` | `GET /download/{file_id}` | ✅ |
| Capabilities | `app/capabilities.py` | Prompt LLM mis à jour | ✅ |
| Tools registry | `app/tools_registry.py` | CREATE_PDF, CREATE_EXCEL, CREATE_IMAGE | ✅ |

## 4. PWA — OPÉRATIONNELLE ✅

- **Icône** : smiley vert clin d'oeil (`app/static/5AEA8C3F-2F59-4ED0-8AAA-3B324C3498DF.png`)
- **Endpoint** : `_generate_raya_png()` dans main.py charge et resize l'image
- **Service Worker v3** : Network-First pour nos fichiers, Cache-First pour CDN uniquement
- **sw.js** servi avec `Cache-Control: no-store, no-cache, must-revalidate, max-age=0`
- **Cache-bust ?v=3** sur tous les CSS/JS dans aria_chat.html
- **`reg.update()`** forcé à chaque chargement de page
- **Safe-area iPhone 16 Pro Max** : `!important` sur header padding-top + input-zone padding-bottom
- **`100dvh`** au lieu de `100vh` pour la hauteur de l'app
- **Manifest** : PNG only (pas de SVG — iOS ne les supporte pas), purpose "any"

## 5. SIGNATURE EMAIL

### V1 actuelle (en place)
- `app/email_signature.py` : signature statique Guillaume
  - Police Helvetica, "Guillaume Perrin" en bold
  - "Solairement," → "Guillaume Perrin" (bold) → téléphone → lien site → bandeau image
  - Image bandeau : `app/static/Photo_9.jpg` (largeur ~500px)
- `app/connectors/outlook_connector.py` : `_build_email_html()` appelle `get_email_signature()`
- Tous les envois (send_reply, send_new_mail, create_reply_draft) incluent la signature

### V2 à implémenter (décision Guillaume 14/04/2026)
**Approche validée : récupération automatique des signatures existantes**
- Guillaume a déjà des signatures configurées dans chaque boîte mail (Microsoft + Gmail)
- Raya devrait les **récupérer et stocker** plutôt que d'en créer de nouvelles
- **Microsoft Graph** : l'API n'ajoute PAS la signature auto lors d'envoi programmatique → il faut la stocker
- **Gmail API** : les signatures sont accessibles via `GET /gmail/v1/users/me/settings/sendAs`
- **Approche intelligente** : analyser les 5 derniers mails envoyés de chaque boîte pour en extraire la signature (pattern récurrent en fin de mail)
- **Bouton admin** : dans le panel admin → "Récupérer mes signatures" → Raya scanne les mails envoyés, extrait les signatures, les stocke en base
- **Table DB** : `email_signatures` (username, email_address, signature_html, updated_at)
- **Fonction** : `get_email_signature(username, from_address)` → retourne la bonne signature selon l'adresse d'envoi
- **Résultat** : si Guillaume change sa signature dans Outlook, il clique "Récupérer" et Raya s'adapte

## 6. HISTORIQUE CHAT & UI

- **Chat history** : `GET /chat/history?limit=20` + `loadHistory()` dans init() + séparateur visuel
- **Markdown** : marked.js + DOMPurify, tableaux stylés, liens target="_blank"
- **Feedback** : 👍👎💡 sous chaque message Raya

## 7. PROCHAINES ÉTAPES

### Immédiat (prochaine session)
- [ ] Signature email v2 — bouton admin récupération signatures
- [ ] PDF preview mobile — ouvrir dans Safari au lieu de naviguer dans la PWA
- [ ] Audio "Écouter" sur iPhone — diagnostic bouton lecture manuelle
- [ ] Tester Gmail OAuth (PKCE corrigé)
- [ ] Tester création PDF/Excel/DALL-E en production

### Court terme
- [ ] Beta Charlotte (tenant "juillet", cloisonnement, onboarding)
- [ ] UI/Design refonte visuelle

### Moyen terme
- [ ] Tenant DEMO (5 profils sectoriels — voir `docs/raya_roadmap_demo.md`)
- [ ] WhatsApp production (sortir du sandbox Twilio)
- [ ] RGPD, facturation Stripe
- [ ] Manipulation fichiers avancée (voir `docs/raya_roadmap_demo.md` section fichiers)

## 8. DOCUMENTS DE RÉFÉRENCE

| Document | Contenu |
|---|---|
| `docs/raya_session_state.md` | CE FICHIER — état vivant du projet |
| `docs/raya_maintenance.md` | Plan de maintenance (trimestriel/mensuel/hebdo) |
| `docs/raya_roadmap_demo.md` | Roadmap démo 5 profils + roadmap fichiers |
| `docs/raya_roadmap_v2.md` | Roadmap originale (phases 5A→7) |

## 9. VARIABLES RAILWAY

```
TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_WHATSAPP_FROM=whatsapp:+14155238886
NOTIFICATION_PHONE_GUILLAUME=+33...
GMAIL_CLIENT_ID, GMAIL_CLIENT_SECRET
GMAIL_REDIRECT_URI=https://app.raya-ia.fr/auth/gmail/callback
APP_BASE_URL=https://app.raya-ia.fr
RAYA_WEB_SEARCH_ENABLED=true, ELEVENLABS_SPEED=1.2
SCHEDULER_GMAIL_ENABLED=true
SCHEDULER_ANOMALY_ENABLED=false, SCHEDULER_OBSERVER_ENABLED=false
ODOO_URL, ODOO_DB, ODOO_LOGIN, ODOO_PASSWORD
SMTP_HOST, SMTP_USER, SMTP_PASS
OPENAI_API_KEY (embeddings + DALL-E)
Webhook Twilio : https://app.raya-ia.fr/webhook/twilio (POST)
```

## 10. HISTORIQUE DES SESSIONS

### Session 13-14/04/2026 (marathon nuit — ~50 commits)
TOOL-CREATE-FILES (PDF+Excel complets). TOOL-DALLE (images DALL-E 3). TOOL-READ-PDF (3/3 — pdfplumber). Capabilities PDF/Excel/DALL-E mises à jour. CHAT-HISTORY (historique au chargement). FIX-SAFE-AREA (iPhone 16 Pro Max Dynamic Island + barre home). Service Worker v3 (Network-First). Cache-bust ?v=3 tous assets. FIX-SW-CACHE (no-store sur sw.js). PWA icon smiley vert clin d'oeil. EMAIL-SIGNATURE v1 (Helvetica + bandeau Couffrant Solar). FIX-MARKDOWN (était le SW cache). Plan maintenance créé. Roadmap démo 5 profils sectoriels documentée. Roadmap fichiers (lecture/modification PDF, édition images). Logo design : smiley vert clin d'oeil sur fond bleu ciel #1D6FD9 validé. Décision signature v2 : récupération auto depuis boîtes mail + bouton admin.

### Session 13/04/2026 (après-midi + soir)
~20 tâches. Connectivité 5/5. Gmail PKCE bypass. WhatsApp bidirectionnel intelligent. Twilio sandbox. DNS app.raya-ia.fr. USER-PHONE. FIX-MONITOR-SPAM. FORGOT-PASSWORD. FIX-CAPABILITIES.

### Session 12-13/04/2026 (marathon)
~55 tâches. Phase 7+8 complètes. 5 refactorings. 9 fixes. Admin panel. Web search.

## 11. REPRISE NOUVELLE CONVERSATION

« Bonjour Opus. Projet Raya, Guillaume. On se tutoie, en français, vocabulaire Terminal, concis. Lis `docs/raya_session_state.md` sur `per1gyom/couffrant-assistant` main via GitHub MCP. Règle d'or : aucune écriture sans mon ok. Reprends où on en était. »
