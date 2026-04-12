# Raya — État de session vivant

**Dernière mise à jour : 13/04/2026 nuit** — Opus

---

## ⭐ ÂME DU PROJET
Raya = cerveau supplémentaire pour dirigeant. 8 dimensions, 3 modes, supervision managériale. LLM-agnostic, tools-agnostic, channel-agnostic. Raya ne connait PAS le mot "Jarvis".

## 0. CONSIGNES
- **Opus = architecte (le QUOI), Sonnet = exécutant (le CODE). Opus ne code PAS.**
- **Prompts directement dans le chat, entre barres de code.**
- **JAMAIS push_files pour du code Python.**
- **Aucune écriture sans ok explicite de Guillaume.**

## 1. Stack
FastAPI Python 3.13, Railway, PostgreSQL+pgvector, Anthropic 3 tiers, OpenAI embeddings.
Repo `github.com/per1gyom/couffrant-assistant` main.

## 2. État complet

### Phase 7 — 16 tâches ✅
urgency_model, shadow mode, notification prefs, WhatsApp structuré, activity log, mémoire narrative, briefings réunions, rapport stocké+ping+livraison, workflow intelligence, Gmail connector+pipeline+polling, monitoring système, fallback SMS, WhatsApp bidirectionnel, vitesse lecture dynamique.

### Phase 8 — 4/5 tâches ✅
8-CYCLES (patterns cycliques), 8-TON (ton adaptatif), 8-ANOMALIES (Odoo vs mails), 8-OBSERVE (observation externe Drive/mail/calendar). Reste 8-COLLAB (Phase commercialisation).

### Refactorings — 5 ✅
scheduler.py (43k→5k+8 modules), database.py (31k→9k+migrations), admin.py (20k→3 modules), aria_context.py (25k→13k+loaders), chat.js (40k→10k+6 modules).

### Fixes — 9 ✅
Purge Jarvis, security timeout 2h, ElevenLabs speed dynamique, toast feedback, hotfix scheduler lazy imports, tenant form auto-lowercase, tenant creation (infos légales), 5 bugs critiques (user_tenant_access + delete + defaults), intelligence collective préservée sur suppression user.

### Admin panel ✅
Gestion tenants (CRUD), formulaire simplifié (forme juridique, SIRET, adresse), SharePoint optionnel après création.

### Web search ✅
Accès internet via web_search Anthropic activé.

## 3. RIEN EN ATTENTE

Tous les prompts ont été envoyés et exécutés. Zéro dette.

## 4. PROCHAINES ÉTAPES

### Priorité 1 — Beta Charlotte (mi-juin)
- Tester le parcours complet : création tenant + users + connexion + conversations
- Volet B — Ergonomie UI (largeur chat, design épuré, responsive)

### Priorité 2 — Outils de création
- DALL-E + Pillow (création/modification images)
- Excel (openpyxl), PDF (reportlab)
- Posts LinkedIn + publication

### Priorité 3 — Futur
- 8-COLLAB (collaboration inter-Rayas)
- Application mobile (PWA ou native)
- Audit performance (profiler temps de réponse)

## 5. PRINCIPE : Intelligence collective
Quand un utilisateur est supprimé, ses données personnelles sont effacées mais l'intelligence (règles, insights, patterns, narratives, mails, activity_log) est anonymisée et conservée pour le collectif.

## 6. Reprise
« Bonjour Opus. Projet Raya, Guillaume. On se tutoie, en français, vocabulaire Terminal, concis. Lis `docs/raya_session_state.md` puis `docs/raya_roadmap_v2.md` sur `per1gyom/couffrant-assistant` main via GitHub MCP. Règle d'or : aucune écriture sans mon ok. Reprends où on en était. »

## 7. Variables Railway
- `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_WHATSAPP_FROM`
- `NOTIFICATION_PHONE_GUILLAUME`, `NOTIFICATION_PHONE_ADMIN`
- `GMAIL_CLIENT_ID`, `GMAIL_CLIENT_SECRET`, `SCHEDULER_GMAIL_ENABLED=true`
- `RAYA_WEB_SEARCH_ENABLED=true`, `ELEVENLABS_SPEED=1.2`
- `SCHEDULER_ANOMALY_ENABLED=false`, `SCHEDULER_OBSERVER_ENABLED=false`
- URL webhook Twilio : `https://[domaine].railway.app/webhook/twilio` (POST)
