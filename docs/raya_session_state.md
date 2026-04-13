# Raya — État de session vivant

**Dernière mise à jour : 13/04/2026 nuit** — Opus

---

## ⚠️ RÈGLE IMPÉRATIVE — MISE À JOUR DE CE DOCUMENT

Ce fichier est le JOURNAL DE BORD du projet Raya. À chaque session, Opus DOIT :
1. Lire ce fichier au début de la session
2. Mettre à jour à chaque jalon
3. En fin de session, résumer dans "Historique des sessions"

---

## ⭐ ÂME DU PROJET
Raya = cerveau supplémentaire pour dirigeant. 8 dimensions, 3 modes. LLM-agnostic, tools-agnostic, channel-agnostic. Raya ne connait PAS le mot "Jarvis".

## 0. CONSIGNES
- **Opus = architecte (le QUOI), Sonnet = exécutant (le CODE). Opus ne code PAS.**
- **Prompts directement dans le chat.** JAMAIS push_files pour du code Python.
- **Aucune écriture sans ok explicite de Guillaume.**
- **⚠️ COMMITS COURTS OBLIGATOIRES** : chaque prompt Sonnet DOIT découper le travail en commits séparés (1 fichier par commit max). Les gros commits timeout le MCP GitHub. Même un prompt long avec 5+ commits est OK — tant que chaque commit est petit et rapide.
- **Fichiers < 15k** : tout fichier > 20k doit être découpé en modules.

## 1. Stack
FastAPI Python 3.13, Railway, PostgreSQL+pgvector, Anthropic 3 tiers, OpenAI embeddings.
Repo `github.com/per1gyom/couffrant-assistant` main.
URL principale : `https://app.raya-ia.fr`
URL technique : `https://couffrant-assistant-production.up.railway.app`
Service Railway renommé "Raya" (ex "Aria").

## 2. CONNECTIVITÉ — 5/5 SERVICES OPÉRATIONNELS

| Service | Statut |
|---|---|
| Microsoft 365 | 🟢 OK |
| Gmail | 🟢 OK (PKCE bypass, échange HTTP direct) |
| Odoo | 🟢 OK |
| Twilio/WhatsApp | 🟢 OK |
| ElevenLabs | 🟢 OK |

## 3. PROMPTS EN ATTENTE

- FIX-MARKDOWN (en cours — redécoupé)
- TOOL-CREATE-FILES (en cours — 5 commits)
- TOOL-DALLE (à envoyer après TOOL-CREATE-FILES)

## 4. PROCHAINES ÉTAPES

### ⭐ En cours
- [ ] FIX-MARKDOWN — rendu markdown fiable
- [ ] TOOL-CREATE-FILES — PDF + Excel
- [ ] TOOL-DALLE — génération d'images
- [ ] Icône PWA personnalisée (design à faire)

### À faire par Guillaume
- [x] Domaine app.raya-ia.fr configuré
- [x] Variables Railway GMAIL_REDIRECT_URI + APP_BASE_URL mises à jour
- [x] Webhook Twilio mis à jour
- [x] Google Cloud Console redirect URI mis à jour
- [x] PWA installée sur iPhone
- [ ] Tester Gmail : tiroir admin → "Connecter Gmail"
- [ ] Tester le recadrage iPhone (safe-area fix déployé)

### Priorité 2 — Beta Charlotte + Tenant DEMO
### Priorité 3 — UI ergonomie + audit performance

## 5. PRINCIPES ARCHITECTURAUX

- Intelligence collective, collaboration inter-Rayas
- Téléphone en base, login par email
- Imports lazy, fichiers < 15k, commits courts
- Voir `docs/raya_maintenance.md` pour le plan de maintenance

## 6. HISTORIQUE DES SESSIONS

### Session 13/04/2026 (complète — nuit)
~25 tâches. TOOL-CREATE-FILES (en cours). CHAT-HISTORY (historique au chargement). PWA icon opaque + manifest fix + safe-area iPhone 16 Pro Max. Plan de maintenance créé. Règle commits courts ajoutée.

### Session 13/04/2026 (après-midi + soir)
PWA-FIX. DIAG-ENDPOINTS. GMAIL-FIX. FORGOT-PASSWORD. HOTFIX-GMAIL-TOKENS. USER-PHONE. FIX-MONITOR-SPAM. WHATSAPP-RAYA. GMAIL-PKCE v2. FIX-CAPABILITIES. Twilio. DNS app.raya-ia.fr. Diagnostic 5/5.

### Session 12-13/04/2026 (marathon)
~55 tâches. Phase 7+8 complètes. 5 refactorings. 9 fixes. Admin panel. Web search.

## 7. Reprise
« Bonjour Opus. Projet Raya, Guillaume. On se tutoie, en français, vocabulaire Terminal, concis. Lis `docs/raya_session_state.md` puis `docs/raya_roadmap_v2.md` sur `per1gyom/couffrant-assistant` main via GitHub MCP. Règle d'or : aucune écriture sans mon ok. Reprends où on en était. »

## 8. Variables Railway
- `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_WHATSAPP_FROM=whatsapp:+14155238886`
- `NOTIFICATION_PHONE_GUILLAUME=+33...`
- `GMAIL_CLIENT_ID`, `GMAIL_CLIENT_SECRET`
- `GMAIL_REDIRECT_URI=https://app.raya-ia.fr/auth/gmail/callback`
- `APP_BASE_URL=https://app.raya-ia.fr`
- `RAYA_WEB_SEARCH_ENABLED=true`, `ELEVENLABS_SPEED=1.2`
- `SCHEDULER_GMAIL_ENABLED=true`
- `SCHEDULER_ANOMALY_ENABLED=false`, `SCHEDULER_OBSERVER_ENABLED=false`
- `ODOO_URL`, `ODOO_DB`, `ODOO_LOGIN`, `ODOO_PASSWORD`
- `SMTP_HOST`, `SMTP_USER`, `SMTP_PASS`
- Webhook Twilio : `https://app.raya-ia.fr/webhook/twilio`
