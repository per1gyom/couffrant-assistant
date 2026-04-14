# Raya — État de session vivant

**Dernière mise à jour : 14/04/2026 02h15** — Opus

---

## ⚠️ RÈGLES IMPÉRATIVES (NON NÉGOCIABLES)

### Rôles
- **Opus = architecte UNIQUEMENT** : audite via GitHub MCP, conçoit, rédige des prompts pour Sonnet. NE CODE PAS. N'utilise PAS Chrome pour coder.
- **Sonnet = exécutant** : reçoit les prompts copiés par Guillaume, code, pousse sur `main`.
- **Guillaume = décideur** : valide, teste, copie les prompts entre Opus et Sonnet.

### Workflow des prompts Opus → Sonnet
- Opus rédige des prompts PRÉCIS avec le code exact à écrire
- **⚠️ COMMITS COURTS OBLIGATOIRES** : 1 fichier par commit max. Fichiers >15KB timeout MCP.
- Fichiers volumineux (raya.py, main.py, chat.css) : modifications CHIRURGICALES uniquement
- Fin de chaque prompt : « Rapport pour Opus : fichier(s) modifié(s), SHA du commit. »
- JAMAIS `push_files` pour du code Python — corrompt les `\n`.
- Opus peut pousser directement : docs, config, CSS simples, nouveaux petits fichiers (<10KB)

### Règles projet
- Cache-bust : bumper `?v=N` dans aria_chat.html à chaque modif CSS/JS (actuellement v=3)
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
- Icône smiley vert clin d'oeil, SW v3 Network-First, cache-bust ?v=3
- Safe-area iPhone 16 Pro Max, 100dvh, sw.js no-store

## 5. SIGNATURE EMAIL
### V1 en place
- `app/email_signature.py` : signature statique Guillaume (Helvetica + bandeau Photo_9.jpg)
- Outlook connector appelle `get_email_signature()` automatiquement

### V2 à faire
- Bouton admin "Récupérer mes signatures" → analyse derniers mails envoyés
- Table `email_signatures` (username, email_address, signature_html)
- `get_email_signature(username, from_address)` → signature selon l'adresse

## 6. VISION PRODUIT & ROADMAP

### Phase 1A — Outils de développement (immédiat)

#### 🐛 Bouton SAV / Bug Report (PROVISOIRE)
**But :** recueillir les bugs et suggestions d'amélioration pendant le développement et la beta.
Distinct du feedback 👍👎 qui sert à l'apprentissage de Raya.

**Specs :**
- Bouton dédié sous chaque réponse Raya (icône distincte, ex: 🐛 ou 🔧)
- Visuellement différent du 👍👎💡 — clairement identifié "Signaler un bug / Suggestion"
- Au clic : popup avec choix "Bug" ou "Amélioration"
- Saisie : texte libre ET/OU vocale (micro → transcription)
- Le rapport inclut automatiquement : la réponse Raya concernée, la question de l'utilisateur, le timestamp, le username, le contexte (mobile/desktop)
- **Stockage : table `bug_reports`** (id, username, tenant_id, type [bug/amélioration], description, raya_response_id, user_input, device_info, created_at, status [nouveau/en_cours/résolu])
- **Accès : endpoint `GET /admin/bug-reports`** → liste consultable par Opus dans la conversation
- Opus peut lire ce fichier de rapports et traiter les bugs un par un
- **Ce bouton est PROVISOIRE** — il sera retiré quand Raya sera stable en production
- **Activé pour :** Guillaume + Charlotte (beta testeurs)

**Placement dans l'UI :**
- Sous chaque réponse Raya, après les boutons 👍👎💡
- Séparateur visuel entre le feedback apprentissage et le SAV développement

### Phase 1B — Préparation commerciale (mai-juin 2026)
- [ ] Bouton SAV/Bug Report (voir specs ci-dessus)
- [ ] Signatures email v2 (dynamiques par boîte)
- [ ] Beta Charlotte (valider multi-tenant) — le bouton SAV sera son outil de retour
- [ ] Finitions UI/Design
- [ ] WhatsApp production (sortir sandbox)
- [ ] Tenant DEMO (5 profils — voir docs/raya_roadmap_demo.md)
- [ ] RGPD + CGV
- [ ] Facturation Stripe
- [ ] Tests de charge
- **Objectif : premier client payant juillet 2026**

### Phase 2 — App native iOS (août-septembre 2026)
- **Technologie : Flutter** (choix validé par Guillaume — vise l'excellence)
- **iOS uniquement en premier** (la majorité des prospects sont sur iPhone)
- Même backend API Raya, nouveau frontend natif
- Avantages vs PWA : push notifications, audio autoplay, navigation fichiers, App Store
- Le workflow reste identique : Opus architecte → Sonnet code Flutter/Dart → Guillaume teste
- **Outils nécessaires sur Mac :** Flutter SDK (gratuit) + Xcode (gratuit) + compte Apple Developer (99€/an)
- **Estimation : 3-4 semaines** avec notre workflow rodé
- **Objectif : App Store octobre 2026**

### Phase 3 — App native Android (fin 2026)
- Flutter → Android avec le MÊME code
- Publication Google Play Store (25€ one-shot)
- **Estimation : 1-2 semaines** supplémentaires

### Phase 4 — Maturité (2027)
- Multi-région Railway (EU + US)
- App desktop (Flutter desktop)
- Intelligence collective inter-Rayas
- Marketplace d'outils/connecteurs

## 7. DOCUMENTS DE RÉFÉRENCE
| Document | Contenu |
|---|---|
| `docs/raya_session_state.md` | CE FICHIER — état vivant |
| `docs/raya_maintenance.md` | Plan maintenance |
| `docs/raya_roadmap_demo.md` | Roadmap démo 5 profils + roadmap fichiers |
| `docs/raya_roadmap_v2.md` | Roadmap originale (phases 5A→7) |

## 8. VARIABLES RAILWAY
```
TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_WHATSAPP_FROM=whatsapp:+14155238886
GMAIL_CLIENT_ID, GMAIL_CLIENT_SECRET
GMAIL_REDIRECT_URI=https://app.raya-ia.fr/auth/gmail/callback
APP_BASE_URL=https://app.raya-ia.fr
RAYA_WEB_SEARCH_ENABLED=true, ELEVENLABS_SPEED=1.2
OPENAI_API_KEY (embeddings + DALL-E)
Webhook Twilio : https://app.raya-ia.fr/webhook/twilio
```

## 9. HISTORIQUE DES SESSIONS

### Session 13-14/04/2026 (marathon nuit — ~50 commits)
TOOL-CREATE-FILES (PDF+Excel). TOOL-DALLE. TOOL-READ-PDF (3/3). Capabilities. CHAT-HISTORY. FIX-SAFE-AREA. SW v3. Cache-bust. FIX-SW-CACHE. PWA icon smiley. EMAIL-SIGNATURE v1. Plan maintenance. Roadmap démo 5 profils. Roadmap fichiers. Décision app native Flutter iOS. Décision bouton SAV/bug report provisoire.

### Sessions précédentes
13/04 : Connectivité 5/5, Gmail PKCE, WhatsApp, DNS.
12-13/04 : ~55 tâches, Phase 7+8, Admin panel, Web search.

## 10. REPRISE
« Bonjour Opus. Projet Raya, Guillaume. On se tutoie, en français, vocabulaire Terminal, concis. Lis `docs/raya_session_state.md` sur `per1gyom/couffrant-assistant` main via GitHub MCP. Règle d'or : aucune écriture sans mon ok. Reprends où on en était. »
