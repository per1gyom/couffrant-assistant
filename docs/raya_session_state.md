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
URL : `https://couffrant-assistant-production.up.railway.app`

## 2. CONNECTIVITÉ — TOUS LES SERVICES OPÉRATIONNELS

| Service | Statut | Détail |
|---|---|---|
| Microsoft 365 | 🟢 OK | Token valide pour Guillaume |
| Gmail | 🟢 OK | Tokens présents, OAuth2 complet |
| Odoo | 🟢 OK | Authentifié sur entreprisecouffrant.openfire.fr |
| Twilio/WhatsApp | 🟢 OK | Messages reçus par Guillaume |
| ElevenLabs | 🟢 OK | Clé + voice_id configurés |

## 3. PROMPTS EN ATTENTE

Aucun. Zéro dette.

## 4. PROCHAINES ÉTAPES

### ⭐ Priorité 1 — Tests utilisateur Guillaume
- [ ] Tester PWA sur iPhone : Safari → "Ajouter à l'écran d'accueil"
- [ ] Tester WhatsApp bidirectionnel : répondre "1", "rapport", texte libre
- [ ] Tester le rapport matinal (arrivera à 7h)
- [ ] Configurer webhook Twilio entrant dans console Twilio :
      URL: `https://couffrant-assistant-production.up.railway.app/webhook/twilio` (POST)
      Page: Messaging → Try it out → WhatsApp Sandbox → "When a message comes in"
- [ ] Connecter Gmail : visiter /login/gmail dans le tiroir admin
- [ ] Ajouter `SMTP_HOST`, `SMTP_USER`, `SMTP_PASS` dans Railway (pour forgot password)
- [ ] Ajouter `GMAIL_REDIRECT_URI` dans Railway

### Priorité 2 — Outils de création
- DALL-E + Pillow (images)
- Excel (openpyxl), PDF (reportlab)
- Posts LinkedIn

### Priorité 3 — Beta Charlotte + Tenant DEMO
### Priorité 4 — UI ergonomie + audit performance

## 5. PRINCIPES ARCHITECTURAUX

- **Intelligence collective** : suppression user = données privées effacées, intelligence anonymisée
- **Téléphone en base** : colonne `phone` sur users, plus de variables Railway par utilisateur
- **Login par email** : authenticate() accepte username OU email
- **Imports lazy** scheduler, fichiers < 15k, prompts architecte

## 6. HISTORIQUE DES SESSIONS

### Session 13/04/2026 soir (connectivité + architecture)
**~12 tâches.** PWA-FIX (icônes Pillow). DIAG-ENDPOINTS (diagnostic tous connecteurs). GMAIL-FIX (OAuth2 complet). FORGOT-PASSWORD (self-service). HOTFIX-GMAIL-TOKENS (colonne updated_at). USER-PHONE (téléphone en base + login par email). FIX-MONITOR-SPAM (seuils 60min + cooldown 6h + init heartbeats). Création compte Twilio. Configuration WhatsApp sandbox. Diagnostic live : 5/5 services opérationnels.

### Session 13/04/2026 après-midi
PWA-FIX, DIAG-ENDPOINTS, GMAIL-FIX, FORGOT-PASSWORD. Audit fichiers Sonnet.

### Session 12-13/04/2026 (marathon)
~55 tâches. Phase 7+8 complètes. 5 refactorings. 9 fixes. Admin panel. Web search.

## 7. Reprise
« Bonjour Opus. Projet Raya, Guillaume. On se tutoie, en français, vocabulaire Terminal, concis. Lis `docs/raya_session_state.md` puis `docs/raya_roadmap_v2.md` sur `per1gyom/couffrant-assistant` main via GitHub MCP. Règle d'or : aucune écriture sans mon ok. Reprends où on en était. »

## 8. Variables Railway
- `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_WHATSAPP_FROM=whatsapp:+14155238886`
- `NOTIFICATION_PHONE_GUILLAUME=+33...`
- `GMAIL_CLIENT_ID`, `GMAIL_CLIENT_SECRET`, `GMAIL_REDIRECT_URI`, `SCHEDULER_GMAIL_ENABLED=true`
- `RAYA_WEB_SEARCH_ENABLED=true`, `ELEVENLABS_SPEED=1.2`
- `SCHEDULER_ANOMALY_ENABLED=false`, `SCHEDULER_OBSERVER_ENABLED=false`
- `ODOO_URL`, `ODOO_DB`, `ODOO_LOGIN`, `ODOO_PASSWORD`
- `SMTP_HOST`, `SMTP_USER`, `SMTP_PASS` (pour reset password par email)
- Webhook Twilio : `https://couffrant-assistant-production.up.railway.app/webhook/twilio` (POST)
