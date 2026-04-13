# Raya — État de session vivant

**Dernière mise à jour : 13/04/2026 soir** — Opus

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

## 1. Stack
FastAPI Python 3.13, Railway, PostgreSQL+pgvector, Anthropic 3 tiers, OpenAI embeddings.
Repo `github.com/per1gyom/couffrant-assistant` main.
URL principale : `https://app.raya-ia.fr` (DNS en propagation)
URL technique : `https://couffrant-assistant-production.up.railway.app`
Service Railway renommé "Raya" (ex "Aria").

## 2. CONNECTIVITÉ — 5/5 SERVICES OPÉRATIONNELS

| Service | Statut |
|---|---|
| Microsoft 365 | 🟢 OK |
| Gmail | 🟢 OK (PKCE corrigé — échange direct sans Flow) |
| Odoo | 🟢 OK |
| Twilio/WhatsApp | 🟢 OK (sandbox + webhook configurés) |
| ElevenLabs | 🟢 OK |

## 3. PROMPTS EN ATTENTE

Aucun. Zéro dette.

## 4. PROCHAINES ÉTAPES

### ⭐ À faire par Guillaume (pas de code)
- [ ] Tester `https://app.raya-ia.fr` quand DNS propage (~30min)
- [ ] Mettre à jour dans Railway : GMAIL_REDIRECT_URI → `https://app.raya-ia.fr/auth/gmail/callback`
- [ ] Mettre à jour dans Railway : APP_BASE_URL → `https://app.raya-ia.fr`
- [ ] Mettre à jour webhook Twilio → `https://app.raya-ia.fr/webhook/twilio`
- [ ] Mettre à jour Google Cloud Console : redirect URI → `https://app.raya-ia.fr/auth/gmail/callback`
- [ ] Tester Gmail : tiroir admin → "Connecter Gmail"
- [ ] Tester WhatsApp bidirectionnel : envoyer texte libre → Raya répond
- [ ] Tester PWA sur iPhone : Safari → "Sur l'écran d'accueil"

### Priorité 2 — Outils de création
- DALL-E + Pillow (images)
- Excel (openpyxl), PDF (reportlab)
- Posts LinkedIn

### Priorité 3 — Beta Charlotte + Tenant DEMO
### Priorité 4 — UI ergonomie + audit performance

## 5. PRINCIPES ARCHITECTURAUX

- Intelligence collective, collaboration inter-Rayas
- Téléphone en base (colonne phone sur users)
- Login par email (authenticate accepte username OU email)
- Imports lazy, fichiers < 15k, prompts architecte

## 6. HISTORIQUE DES SESSIONS

### Session 13/04/2026 (complète)
**~20 tâches.** PWA-FIX. DIAG-ENDPOINTS. GMAIL-FIX. FORGOT-PASSWORD. HOTFIX-GMAIL-TOKENS. USER-PHONE (téléphone en base + login email). FIX-MONITOR-SPAM (seuils 60min + cooldown 6h). WHATSAPP-RAYA (réponse intelligente par WhatsApp). HOTFIX-GMAIL-PKCE v2 (bypass PKCE, échange HTTP direct). FIX-CAPABILITIES (WhatsApp + web search + suppression fausses limitations). Création compte Twilio + config sandbox. Domaine personnalisé `app.raya-ia.fr` configuré (DNS Squarespace). Service renommé Raya. Diagnostic live 5/5.

### Session 12-13/04/2026 (marathon)
~55 tâches. Phase 7+8 complètes. 5 refactorings. 9 fixes. Admin panel. Web search.

## 7. Reprise
« Bonjour Opus. Projet Raya, Guillaume. On se tutoie, en français, vocabulaire Terminal, concis. Lis `docs/raya_session_state.md` puis `docs/raya_roadmap_v2.md` sur `per1gyom/couffrant-assistant` main via GitHub MCP. Règle d'or : aucune écriture sans mon ok. Reprends où on en était. »

## 8. Variables Railway
- `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_WHATSAPP_FROM=whatsapp:+14155238886`
- `NOTIFICATION_PHONE_GUILLAUME=+33...`
- `GMAIL_CLIENT_ID`, `GMAIL_CLIENT_SECRET`
- `GMAIL_REDIRECT_URI=https://app.raya-ia.fr/auth/gmail/callback` ← à mettre à jour
- `APP_BASE_URL=https://app.raya-ia.fr` ← à mettre à jour
- `RAYA_WEB_SEARCH_ENABLED=true`, `ELEVENLABS_SPEED=1.2`
- `SCHEDULER_GMAIL_ENABLED=true`
- `SCHEDULER_ANOMALY_ENABLED=false`, `SCHEDULER_OBSERVER_ENABLED=false`
- `ODOO_URL`, `ODOO_DB`, `ODOO_LOGIN`, `ODOO_PASSWORD`
- `SMTP_HOST`, `SMTP_USER`, `SMTP_PASS`
- Webhook Twilio : `https://app.raya-ia.fr/webhook/twilio` ← à mettre à jour
