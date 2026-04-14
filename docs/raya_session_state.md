# Raya — État de session vivant

**Dernière mise à jour : 14/04/2026 18h00** — Opus

---

## ⚠️ RÈGLES IMPÉRATIVES (NON NÉGOCIABLES)

### Rôles
- **Opus = architecte UNIQUEMENT** : audite via GitHub MCP, conçoit, rédige des prompts pour Sonnet. NE CODE PAS. N'utilise PAS Chrome pour coder.
- **Sonnet = exécutant** : reçoit les prompts copiés par Guillaume, code, pousse sur `main`.
- **Guillaume = décideur** : valide, teste, copie les prompts entre Opus et Sonnet.

### Workflow des prompts Opus → Sonnet
- Opus rédige des prompts avec les specs, Sonnet écrit le code
- **⚠️ COMMITS COURTS OBLIGATOIRES** : 1 fichier par commit max. Fichiers >15KB timeout MCP.
- Fichiers volumineux (raya.py, main.py, chat.css) : modifications CHIRURGICALES uniquement
- Fin de chaque prompt : « Rapport pour Opus : fichier(s) modifié(s), SHA du commit. »
- JAMAIS `push_files` pour du code Python — corrompt les `\n`.
- Opus peut pousser directement : docs, config, CSS simples, nouveaux petits fichiers (<10KB)

### Règles projet
- Cache-bust : bumper `?v=N` dans aria_chat.html à chaque modif CSS/JS (actuellement **v=4**)
- Aucune écriture sans ok explicite de Guillaume
- Langue : français, vocabulaire "Terminal", concis

---

## ⭐ ÂME DU PROJET
Raya = cerveau supplémentaire pour dirigeant. LLM-agnostic, tools-agnostic, channel-agnostic.
Raya ne connait PAS le mot "Jarvis".

## 1. Stack
FastAPI Python 3.13, Railway, PostgreSQL+pgvector, Anthropic 3 tiers, OpenAI embeddings.
Repo `github.com/per1gyom/couffrant-assistant` branche `main`.
URL : `https://app.raya-ia.fr` | Technique : `https://couffrant-assistant-production.up.railway.app`

## 2. CONNECTIVITÉ — 5/5 ✅
Microsoft 365, Gmail, Odoo, Twilio/WhatsApp, ElevenLabs.

## 3. OUTILS DE CRÉATION ✅
- Création PDF (reportlab) — [ACTION:CREATE_PDF]
- Création Excel (openpyxl) — [ACTION:CREATE_EXCEL]
- Création images (DALL-E 3) — [ACTION:CREATE_IMAGE]
- Lecture PDF uploadé (pdfplumber) — texte injecté dans contexte LLM
- Téléchargement — GET /download/{file_id}

## 4. PWA ✅
- Icône smiley vert clin d'oeil, SW v3 Network-First, cache-bust ?v=4
- Safe-area iPhone 16 Pro Max, 100dvh, sw.js no-store

## 5. SÉCURITÉ
### Anti-injection (P0-1) ✅
- `GUARDRAILS` dans `aria_context.py` : bloc SECURITE ANTI-INJECTION
- Données externes (mails, Teams, agenda) enveloppées dans `<donnees_externes>...</donnees_externes>`
- Raya refuse d'exécuter des instructions trouvées dans le contenu des mails

### En place
- CSP headers, X-Frame-Options DENY, session inactivity timeout
- Bcrypt passwords, account lockout, rate limiting
- SESSION_SECRET overridé dans Railway ✅

### À faire (Phase 2 solidification)
- [ ] CSRF tokens sur les POST
- [ ] Sécuriser les connexions DB (try/finally systématique)

## 6. SIGNATURE EMAIL
### V1 en place
- `app/email_signature.py` : signature statique Guillaume (Helvetica + bandeau Photo_9.jpg)
- Outlook connector appelle `get_email_signature()` automatiquement

### V2 à faire
- Bouton admin "Récupérer mes signatures" → analyse derniers mails envoyés
- Table `email_signatures` (username, email_address, signature_html)
- `get_email_signature(username, from_address)` → signature selon l'adresse

## 7. BOUTON SAV / BUG REPORT ✅ (P1-1 à P1-5)
**Statut : DÉPLOYÉ** — provisoire, outil de développement beta.

### Composants
- `app/bug_reports.py` : 3 endpoints (POST /raya/bug-report, GET /admin/bug-reports, PATCH /admin/bug-reports/{id})
- Table `bug_reports` : id, username, tenant_id, report_type, description, aria_memory_id, user_input, raya_response, device_info, status, created_at
- Bouton 🐛 dans `chat.js` après 💡, séparateur visuel, dialog inline Bug/Amélioration
- Accessible à tous les users connectés

### Flux
1. User clique 🐛 sous une réponse Raya
2. Choix Bug ou Amélioration + description texte
3. POST /raya/bug-report avec contexte automatique (user_input, raya_response, device_info)
4. Toast confirmation avec ID du rapport
5. Admin consulte via GET /admin/bug-reports
6. Opus peut lire les rapports et traiter les bugs

## 8. VISION PRODUIT & ROADMAP

### Bloc A — Nettoyage (en cours)
- [x] P0-1 : Anti-injection mails piégés
- [x] P1-1 à P1-5 : Bouton SAV complet
- [x] A1 : Mise à jour session_state
- [ ] A2 : Nettoyage fichiers morts (7 fichiers)
- [ ] A3 : AutoSpeak off sur iPhone
- [ ] A4 : Logging propre (remplacer print par logger)
- [ ] A5 : Sécuriser connexions DB (try/finally)

### Bloc B — Fonctionnalités (mai 2026)
- [ ] B1 : PDF preview mobile (liens bloquent PWA iOS)
- [ ] B2 : Tests Gmail OAuth + outils création en prod
- [ ] B3 : Signature email v2 (extraction auto)
- [ ] B4 : Backup DB automatique

### Bloc C — Préparation commerciale (juin 2026)
- [ ] C1 : Beta Charlotte (valider multi-tenant)
- [ ] C2 : Tenant DEMO (5 profils sectoriels)
- [ ] C3 : RGPD + CGV
- [ ] C4 : WhatsApp production (sortir sandbox)
- [ ] C5 : Facturation Stripe
- **Objectif : premier client payant juillet 2026**

### Phase 2 — App native iOS (août-septembre 2026)
- **Technologie : Flutter** (choix validé par Guillaume)
- iOS uniquement en premier
- **Objectif : App Store octobre 2026**

### Phase 3 — App native Android (fin 2026)
### Phase 4 — Maturité (2027)

## 9. AUDIT CODE (14/04/2026)
### Points forts identifiés
- Architecture LLM-agnostic (`llm_client.py`) — changement de provider en ~20 lignes
- Routage 3-tiers avec garde-fou économique Opus
- Multi-tenant préparé dès le départ
- Feedback loop 👍👎 → règle → confirmation → mémoire
- Phases relationnelles Découverte → Consolidation → Maturité
- RAG pgvector avec fallback

### Problèmes identifiés
- Fuites connexions DB (try/finally manquants) → A5
- Logging incohérent (print vs logger) → A4
- AutoSpeak muet sur iPhone (politique Apple) → A3
- Fichiers morts (shims deprecated + .tmp) → A2
- Pas de tests automatisés → Bloc B
- Pas de backup DB → B4
- Pas de CSRF → Bloc C
- Images lourdes dans le repo (1.2MB) → plus tard

### Fichiers à nettoyer (A2)
- `app/routes/aria.py` (shim deprecated)
- `app/routes/raya_actions.py` (shim deprecated)
- `app/routes/raya_context.py` (shim deprecated)
- `app/routes/aria_actions.py` (shim deprecated → routes/actions/)
- `app/database_migrations_patch_gmail.tmp` (fichier temp)
- `app/database_patch_jarvis.tmp` (fichier temp)
- `app/static/chat-markdown.css` (non chargé dans HTML)

## 10. DOCUMENTS DE RÉFÉRENCE
| Document | Contenu |
|---|---|
| `docs/raya_session_state.md` | CE FICHIER — état vivant |
| `docs/raya_maintenance.md` | Plan maintenance |
| `docs/raya_roadmap_demo.md` | Roadmap démo 5 profils + roadmap fichiers |
| `docs/raya_roadmap_v2.md` | Roadmap originale (phases 5A→7) |

## 11. VARIABLES RAILWAY
```
TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_WHATSAPP_FROM=whatsapp:+14155238886
GMAIL_CLIENT_ID, GMAIL_CLIENT_SECRET
GMAIL_REDIRECT_URI=https://app.raya-ia.fr/auth/gmail/callback
APP_BASE_URL=https://app.raya-ia.fr
RAYA_WEB_SEARCH_ENABLED=true, ELEVENLABS_SPEED=1.2
OPENAI_API_KEY (embeddings + DALL-E)
Webhook Twilio : https://app.raya-ia.fr/webhook/twilio
```

## 12. HISTORIQUE DES SESSIONS

### Session 14/04/2026 (après-midi — audit + sécurité + SAV)
AUDIT COMPLET (~35 fichiers lus). P0-1 anti-injection (GUARDRAILS + balises données externes). P1-1 à P1-5 bouton SAV complet (backend + migration + UI + cache-bust v=4). Bloc A nettoyage en cours.

### Session 13-14/04/2026 (marathon nuit — ~50 commits)
TOOL-CREATE-FILES (PDF+Excel). TOOL-DALLE. TOOL-READ-PDF (3/3). Capabilities. CHAT-HISTORY. FIX-SAFE-AREA. SW v3. Cache-bust. FIX-SW-CACHE. PWA icon smiley. EMAIL-SIGNATURE v1. Plan maintenance. Roadmap démo 5 profils. Roadmap fichiers. Décision app native Flutter iOS. Décision bouton SAV/bug report provisoire.

### Sessions précédentes
13/04 : Connectivité 5/5, Gmail PKCE, WhatsApp, DNS.
12-13/04 : ~55 tâches, Phase 7+8, Admin panel, Web search.

## 13. REPRISE
« Bonjour Opus. Projet Raya, Guillaume Perrin (Couffrant Solar). On se tutoie, en français, vocabulaire Terminal, concis. Tu es l'ARCHITECTE du projet. Tu ne codes JAMAIS. Tu rédiges des prompts pour Sonnet (l'exécutant). Lis `docs/raya_session_state.md` sur `per1gyom/couffrant-assistant` main via GitHub MCP. Règle d'or : aucune écriture sans mon ok. Reprends où on en était. »
