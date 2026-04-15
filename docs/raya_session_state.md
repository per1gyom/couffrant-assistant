# Raya — État de session vivant

**Dernière mise à jour : 15/04/2026 10h00** — Opus

---

## ⚠️ RÈGLES IMPÉRATIVES

### Rôles
- **Opus = architecte + codeur direct** via MCP GitHub ou git terminal
- **Sonnet Flutter** : conversation parallèle dédiée à l'app native iOS
- **Guillaume = décideur** : valide, teste

### Règles techniques
- 1 fichier par commit max. Fichiers >10KB = risque timeout MCP
- JAMAIS `push_files` pour du code Python
- Template chat : `app/templates/raya_chat.html`
- Cache-bust : `?v=10` (actuel)
- Français, vocabulaire Terminal, concis

---

## ⭐ ÂME DU PROJET
Raya = cerveau supplémentaire pour dirigeant. LLM-agnostic, tools-agnostic, channel-agnostic.

## 1. Stack
FastAPI Python 3.13, Railway, PostgreSQL+pgvector, Anthropic 3 tiers, OpenAI embeddings.
URL : `https://app.raya-ia.fr`

## 2. CONNECTIVITÉ — 5/5 ✅
## 3. OUTILS DE CRÉATION ✅ (PDF, Excel, DALL-E, lecture PDF)
## 4. PWA ✅ (v=10, iOS autoSpeak off, safe-area)
## 5. SÉCURITÉ ✅ (anti-injection, GUARDRAILS, CSP, bcrypt, lockout)
## 6. SIGNATURE EMAIL ✅ (v2 extraction LLM)
## 7. SAV / BUG REPORT ✅ (🐛 + lien drawer admin)
## 8. RGPD ✅ (export, suppression, mentions légales)
## 9. BACKUP DB ✅ (manuel — auto S3 à compléter)

## 10. UX CHAT ✅
- Nettoyage actions brutes (FIX-CLEAN) ✅
- Déduplication confirmations corbeille/archive ✅
- Horodatage des messages (TIMESTAMP) ✅
- Pilule verte mémoire (FIX-LEARN-UI) ✅
- Guardrail narration verbatim ✅
- Style conversationnel naturel (UX-TONE) ✅
- 👍 confirme aussi les actions en attente ✅
- Bug report : commentaire optionnel + collecte auto échanges ✅
- DELETE/ARCHIVE mutuellement exclusifs (code + prompt) ✅
- Nettoyage fragments Odoo inline ✅

## 11. TOPICS ✅ (5/5)
- `app/topics.py` : 5 endpoints CRUD
- Migration : table user_topics + users.settings JSONB
- RGPD : export + delete couverts
- Prompt : topics actifs injectés + action CREATE_TOPIC
- Flutter : endpoints prêts, TopicsService à switcher vers API

## 12. REFACTORING ARCHITECTURE ✅
### BATCH 1 — Python core (8 splits)
- database.py → database_schema.py
- memory_synthesis.py → synthesis_engine.py
- tools_registry.py → tools_seed_data.py
- router.py → file_creator.py
- elicitation.py → elicitation_questions.py
- security_auth.py → lockout.py
- dashboard_service.py → dashboard_queries.py
- scheduler.py → scheduler_jobs.py

### BATCH 2 — Routes + Connectors (8 splits)
- raya.py → raya_helpers.py
- admin.py → admin_endpoints.py
- webhook.py → webhook_microsoft.py + webhook_gmail.py
- reset_password.py → reset_password_templates.py
- drive_connector.py → drive_actions.py
- teams_connector.py → teams_actions.py
- outlook_connector.py → outlook_actions.py
- gmail_connector.py → gmail_auth.py

### BATCH 3 — Frontend (1 split)
- chat.js → chat-core.js + chat-messages.js + chat-main.js

### Ancien split (session précédente)
- aria_context.py → prompt_guardrails.py + prompt_actions.py + prompt_blocks.py
- security_users.py → password_reset.py + user_crud.py

## 13. MULTI-TENANT
- Tenant `couffrant_solar` : Guillaume (admin)
- Tenant `juillet` : Charlotte (beta) — compte à créer

## 14. FLUTTER — EN PARALLÈLE
- App iOS fonctionnelle sur simulateur (login, chat, TTS, feedback)
- Specs dans `docs/raya_flutter_ux_specs.md`
- Endpoints TOPICS prêts, Flutter doit switcher TopicsService vers API
- Ne pas toucher au dossier `flutter/`

## 15. ROADMAP

### Prochaines tâches immédiates
- [ ] Suppression 8 fichiers morts (git rm — voir liste ci-dessous)
- [ ] B2 : Tester Gmail OAuth + outils en prod
- [ ] B4+ : Créer compte Scaleway pour backup auto
- [ ] Tester 💌 signatures
- [ ] Créer compte Charlotte tenant juillet
- [ ] Audit performance (délai de réponse)
- [ ] PWA Topics (bouton signet dans header)

### Fichiers à supprimer (git rm)
```
app/routes/aria.py
app/routes/raya_actions.py
app/routes/raya_context.py
app/routes/aria_actions.py
app/database_migrations_patch_gmail.tmp
app/database_patch_jarvis.tmp
app/static/chat-markdown.css
app/templates/aria_chat.html
```

### Bloc C restant
- [ ] C1 : Beta Charlotte
- [ ] C2 : Tenant DEMO
- [ ] C4 : WhatsApp production
- [ ] C5 : Facturation Stripe
- **Objectif : premier client payant juillet 2026**

## 16. HISTORIQUE

### Session 15/04/2026 (~60 commits)
TOPICS 5/5. FIX-CLEAN + TIMESTAMP. RENAME raya_chat. 3 bugs chat. Refactoring BATCH 1+2+3 (19 splits). UX-TONE style conversationnel. UX bug report amélioré. UX 👍 confirme pending. 3 hotfixes imports cassés.

### Session 14/04/2026 (~45 commits)
AUDIT COMPLET. P0-1 anti-injection. SAV. Bloc A. B1 B3 B4. C3 RGPD. FIX-LEARN. Split aria_context + security_users. Lancement Flutter.

### Sessions précédentes
13-14/04 nuit : ~50 commits. 13/04 : Connectivité 5/5. 12-13/04 : ~55 tâches.

## 17. REPRISE
« Bonjour Opus. Projet Raya, Guillaume Perrin (Couffrant Solar). On se tutoie, en français, vocabulaire Terminal, concis. Lis `docs/raya_session_state.md` sur `per1gyom/couffrant-assistant` main. Reprends où on en était. »
