# Raya — État de session vivant

**Dernière mise à jour : 13/04/2026 nuit** — Opus

---

## ⚠️ RÈGLE IMPÉRATIVE — MISE À JOUR DE CE DOCUMENT

Ce fichier est le JOURNAL DE BORD du projet Raya. Il sert à la fois d'historique
de ce qui a été fait ET d'objectif pour la suite.

**À chaque session, Opus DOIT :**
1. Lire ce fichier au début de la session pour comprendre l'état du projet
2. Mettre à jour ce fichier à chaque jalon significatif (tâche complétée, fix, refactoring)
3. En fin de session, mettre à jour la section "Historique des sessions" avec un résumé
4. Mettre à jour les prochaines étapes et les prompts en attente

**C'est non négociable.** Sans ce document à jour, la prochaine session ne sait pas
où on en est et perd du temps à redécouvrir ce qui a déjà été fait.

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

## 3. PROMPTS EN ATTENTE

Aucun. Zéro dette.

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

## 5. PRINCIPES ARCHITECTURAUX

- **Intelligence collective** : suppression user = données privées effacées, intelligence (règles, insights, patterns, narratives) anonymisée et conservée pour le collectif.
- **Imports lazy** dans scheduler.py : un module cassé ne bloque pas le démarrage.
- **Fichiers < 15k** : tout fichier > 20k doit être découpé. Sonnet travaille mieux sur des petits fichiers.
- **Prompts architecte** : Opus donne le QUOI/OÙ/POURQUOI/CONTRAINTES. Sonnet code.

## 6. HISTORIQUE DES SESSIONS

### Session 12-13/04/2026 (marathon)
**~50 tâches.** Phase 5D-2 à 5G complètes. Phase 7 (16 tâches Jarvis). Phase 8 (4 tâches intelligence avancée). 5 refactorings majeurs. 9 fixes. Admin panel CRUD tenants. Web search activé. Vision produit documentée (8 dimensions, 3 modes, 4 piliers). Discussion modèle commercial (packs Essentiel/Pro/Dirigeant). Principe intelligence collective établi.

Commits clés : `af3e7762` (Gmail), `cc75f24f` (monitoring+WhatsApp), `b15f928f` (refactor scheduler), `ba6da00f` (anomalies), `ba5602ad` (observer).

## 7. Reprise
« Bonjour Opus. Projet Raya, Guillaume. On se tutoie, en français, vocabulaire Terminal, concis. Lis `docs/raya_session_state.md` puis `docs/raya_roadmap_v2.md` sur `per1gyom/couffrant-assistant` main via GitHub MCP. Règle d'or : aucune écriture sans mon ok. Reprends où on en était. »

## 8. Variables Railway
- `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_WHATSAPP_FROM`
- `NOTIFICATION_PHONE_GUILLAUME`, `NOTIFICATION_PHONE_ADMIN`
- `GMAIL_CLIENT_ID`, `GMAIL_CLIENT_SECRET`, `SCHEDULER_GMAIL_ENABLED=true`
- `RAYA_WEB_SEARCH_ENABLED=true`, `ELEVENLABS_SPEED=1.2`
- `SCHEDULER_ANOMALY_ENABLED=false`, `SCHEDULER_OBSERVER_ENABLED=false`
- URL webhook Twilio : `https://[domaine].railway.app/webhook/twilio` (POST)
