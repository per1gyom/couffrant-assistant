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

### Phase 7 — 16 tâches ✅ (COMPLÈTE)
### Phase 8 — 5/5 tâches ✅ (COMPLÈTE)
### Refactorings — 5 ✅ | Fixes — 9 ✅ | Admin panel ✅ | Web search ✅

Détails : voir section 6 (Historique).

## 3. PROMPTS EN ATTENTE

Aucun. Zéro dette.

## 4. PROCHAINES ÉTAPES (décision Guillaume 13/04/2026)

### ⭐ Priorité 1 — Compte Guillaume 100% opérationnel + mobile
Avant Charlotte, il faut que le compte de Guillaume fonctionne sur TOUS les outils
et soit utilisable sur TÉLÉPHONE (usage principal).

**Usage mobile (CRITIQUE — Guillaume utilise Raya principalement sur téléphone) :**
- PWA (Progressive Web App) — le sw.js et manifest.json existent déjà.
  Finaliser : icônes, splash screen, meta viewport, "Add to Home Screen" fonctionnel.
  Tester sur Safari iPhone : affichage, micro, lecture vocale, scroll, raccourcis.
- Responsive : vérifier que le chat, le panel admin, le login s'adaptent à l'écran mobile.
- Si la PWA ne suffit pas (push notifications, micro en background), évaluer app native.

**Connectivité outils :**
- Gmail bidirectionnel — le code existe (7-1a/b) mais ne fonctionne pas en pratique.
  Diagnostiquer : OAuth2 ? Tokens ? Polling actif ? Mails reçus ?
- Odoo — API key rentrée dans Railway mais Raya ne voit rien.
  Diagnostiquer : ODOO_URL/ODOO_API_KEY/ODOO_DB/ODOO_LOGIN corrects ? Test endpoint ?
- Identifier d'autres outils de Guillaume à connecter.

**Notifications mobiles (Twilio) :**
- Tester le rapport matinal → ping WhatsApp sur le téléphone de Guillaume
- Tester les alertes proactives → notification WhatsApp
- Tester le WhatsApp bidirectionnel (répondre "1", "rapport", etc.)
- Configurer l'URL webhook Twilio dans la console Twilio

**Outils de création :**
- DALL-E + Pillow (images)
- Excel (openpyxl), PDF (reportlab)
- Posts LinkedIn

### Priorité 2 — Beta Charlotte (tenant "juillet")
- Créer un user Charlotte dans le tenant "juillet"
- Connexion → onboarding → premières conversations
- Vérifier le cloisonnement tenant (Charlotte ne voit pas Couffrant Solar)
- Tester 8-COLLAB (événements visibles par l'admin Guillaume)
- Charlotte sert aussi de version test

### Priorité 3 — Tenant DEMO (prospection commerciale)
Créer un tenant "demo" spécial pour démarcher des clients :

**Pré-chargé avec de l'intelligence :**
- Jeu de règles de base couvrant des cas d'usage courants
- Patterns et habitudes pré-enregistrés
- Narratives de dossiers fictifs mais réalistes
- Hot_summary cohérent (impression que Raya connaît déjà l'utilisateur)
→ Le prospect voit Raya "en action", pas une coquille vide.

**Bouton de PURGE :**
- Endpoint admin qui remet le tenant demo à son état initial
- Supprime toutes les modifications faites pendant la démo
- Recharge les données de démo pré-définies
- Prêt pour le prochain prospect en un clic
→ POST /admin/tenants/demo/reset ou bouton dans le panel admin.

**Scénario de démo guidé :**
- Parcours type à suivre pendant la démo
- Montrer : mémoire, apprentissage, proactivité, multi-outils, rapport

### Priorité 4 — UI & Performance
- Volet B — Ergonomie UI (largeur chat, design épuré)
- Audit performance (profiler temps de réponse)

## 5. PRINCIPES ARCHITECTURAUX

- **Intelligence collective** : suppression user = données privées effacées, intelligence anonymisée et conservée.
- **Collaboration inter-Rayas** : tenant_events + SHARE_EVENT + injection prompt "Activité de l'équipe".
- **Imports lazy** dans scheduler.py : un module cassé ne bloque pas le démarrage.
- **Fichiers < 15k** : tout fichier > 20k doit être découpé.
- **Prompts architecte** : Opus donne le QUOI/OÙ/POURQUOI/CONTRAINTES. Sonnet code.

## 6. HISTORIQUE DES SESSIONS

### Session 12-13/04/2026 (marathon)
**~55 tâches.** Phase 5D-2 à 5G complètes. Phase 7 complète (16 tâches). Phase 8 complète (5 tâches). 5 refactorings majeurs. 9 fixes. Admin panel CRUD tenants. Web search activé. Vision produit documentée (8 dimensions, 3 modes, 4 piliers). Discussion modèle commercial (packs). Principes intelligence collective + collaboration inter-Rayas établis.

Décision fin de session : priorité au compte Guillaume opérationnel + mobile (PWA) avant Charlotte. Tenant demo pour la prospection. Outils de création en priorité 1.

Commits clés : `af3e7762` (Gmail), `cc75f24f` (monitoring+WhatsApp), `b15f928f` (refactor scheduler), `ba6da00f` (anomalies), `ba5602ad` (observer), `712c83a3` (collab inter-Rayas).

## 7. Reprise
« Bonjour Opus. Projet Raya, Guillaume. On se tutoie, en français, vocabulaire Terminal, concis. Lis `docs/raya_session_state.md` puis `docs/raya_roadmap_v2.md` sur `per1gyom/couffrant-assistant` main via GitHub MCP. Règle d'or : aucune écriture sans mon ok. Reprends où on en était. »

## 8. Variables Railway
- `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_WHATSAPP_FROM`
- `NOTIFICATION_PHONE_GUILLAUME`, `NOTIFICATION_PHONE_ADMIN`
- `GMAIL_CLIENT_ID`, `GMAIL_CLIENT_SECRET`, `SCHEDULER_GMAIL_ENABLED=true`
- `RAYA_WEB_SEARCH_ENABLED=true`, `ELEVENLABS_SPEED=1.2`
- `SCHEDULER_ANOMALY_ENABLED=false`, `SCHEDULER_OBSERVER_ENABLED=false`
- `ODOO_URL`, `ODOO_API_KEY`, `ODOO_DB`, `ODOO_LOGIN`, `ODOO_PASSWORD`
- URL webhook Twilio : `https://[domaine].railway.app/webhook/twilio` (POST)
