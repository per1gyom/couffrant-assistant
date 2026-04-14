# Raya Flutter — État de session & Suivi

**Dernière mise à jour : 14/04/2026 15h20** — Sonnet (exécutant Flutter)
**Conversation dédiée : développement app native iOS/Android**

---

## ⚠️ RÈGLES DE CETTE CONVERSATION

### Rôles
- **Sonnet = exécutant Flutter** : code l'app native, pousse sur `main` (dossier `flutter/`)
- **Opus = architecte backend** : sur une autre conversation, gère le backend. Ne touche PAS au Flutter.
- **Guillaume = décideur** : valide, teste, fait le pont entre les deux conversations.

### Workflow
- Commits courts (1-2 fichiers max par commit)
- Langue : français, vocabulaire "Terminal", concis
- Fin de session : mettre à jour CE document avec l'avancement
- Chaque prompt commence par lire ce fichier pour reprendre le contexte

### Documents liés
- `docs/raya_flutter_ux_specs.md` — Specs UX complètes (pour Opus + PWA)
- `docs/raya_session_state.md` — État du backend (géré par Opus)

---

## 1. PHILOSOPHIE DU PROJET

**Raya = cerveau supplémentaire pour dirigeant.**
- LLM-agnostic, tools-agnostic, channel-agnostic
- L'app Flutter est un **nouveau canal** (comme la PWA, comme WhatsApp) qui consomme la même API
- Pas de logique métier dans Flutter — tout est côté backend
- Flutter = interface native qui résout les limitations iOS de la PWA

### Ce que Flutter résout vs la PWA
| Problème PWA iOS | Solution Flutter |
|---|---|
| Autoplay audio bloqué par Safari | `just_audio` natif — autoplay sans restriction |
| Micro instable (coupures Safari) | `speech_to_text` natif — stable |
| Navigation fichiers PDF sans retour | Viewer PDF natif in-app |
| Pas de push notifications | Firebase Cloud Messaging natif |
| Pas d'icône native / splash | App Store native |

---

## 2. DESIGN UX FIGÉ (validé Guillaume 14/04/2026)

### 2.1 Principes
- **Conversation unique et continue** — pas de multi-conversations, Raya a la mémoire
- **Écran = 95% échange** — bidirectionnel, minimaliste
- **Voix en premier** — le micro est le héros de l'interface mobile

### 2.2 Écran principal
- **Header ultra-fin** : point vert santé + "Raya" + bouton signet (sujets) + menu ⋮
- **Zone de chat** : tout l'espace, scroll infini vers le haut (historique par blocs de 20)
- **Barre d'input** : 📎 pièce jointe + champ texte + **micro vert** (gros, proéminent) + envoi
- **Séparateur** "— conversation précédente —" entre les sessions

### 2.3 Bulles de message
- **Raya** : fond secondaire, avatar ✦ vert, rendu markdown, actions en dessous (🔊👍👎💡🐛)
- **Utilisateur** : fond bleu clair, avatar initiale, texte brut
- **Badge sujet** : quand un sujet est ouvert, badge violet dans la bulle utilisateur

### 2.4 Menu ⋮ (dropdown compact)
- AutoSpeak (toggle on/off)
- Vitesse voix (slider 0.5x → 2.5x)
- Thème sombre/clair
- Connecteurs (si admin)
- Backup (si admin)
- Signatures (si admin)
- Export RGPD
- Mentions légales
- Déconnexion

### 2.5 Sujets / Projets (NOUVELLE FONCTIONNALITÉ)
- **Bouton signet** dans le header → ouvre un **bottom sheet**
- **Titre de la section personnalisable** : "Mes sujets", "Mes projets", "Mes dossiers"… modifiable par l'utilisateur
- **Liste des sujets** : titre (modifiable), statut (actif/en pause/archivé), date dernier échange
- **Tap sur un sujet** → envoie automatiquement "Fais-moi un point sur le sujet [titre]" à Raya
- **Bouton "+"** pour créer un sujet
- **Création vocale** : "Raya, crée un sujet : Process de devis"
- **Backend requis** : table `user_topics` + 5 endpoints (voir `docs/raya_flutter_ux_specs.md`)
- **Dépendance** : attendre que Opus crée les endpoints avant d'implémenter côté Flutter

---

## 3. BACKEND — CE QUI EXISTE (NE PAS TOUCHER)

### Auth (app/routes/auth.py)
- `POST /login-app` : form-encoded (username + password) → session cookie
- Session contient : `user`, `scope`, `tenant_id`, `last_activity`
- `require_user()` (app/routes/deps.py) vérifie `request.session["user"]`
- Scopes : `admin`, `tenant_admin`, `cs`, `user`
- Sécurité : rate limiting IP, lockout progressif, bcrypt passwords

**Décision Flutter auth :** Utiliser `dio` + `cookie_jar` pour gérer les cookies de session exactement comme la PWA. Si ça ne marche pas sur iOS natif, on demandera à Opus d'ajouter un endpoint `/auth/token` JWT.

### API Endpoints existants (base URL : https://app.raya-ia.fr)

| Endpoint | Méthode | Body | Retour | Usage |
|---|---|---|---|---|
| `/login-app` | POST | form: username, password | redirect + cookie | Login |
| `/logout` | GET | — | redirect | Déconnexion |
| `/raya` | POST | `{query, file_data?, file_type?, file_name?}` | `{answer, actions, pending_actions, aria_memory_id, model_tier, ask_choice}` | Conversation principale |
| `/speak` | POST | `{text, speed?}` | `audio/mpeg` stream | TTS ElevenLabs |
| `/raya/feedback` | POST | `{aria_memory_id, feedback_type, comment?}` | `{status, action}` | Feedback 👍👎 |
| `/raya/bug-report` | POST | `{report_type, description, aria_memory_id?, user_input?, raya_response?, device_info?}` | `{ok, id}` | Bug report 🐛 |
| `/raya/why/{id}` | GET | — | `{status, ...metadata}` | Explication 💡 |
| `/chat/history` | GET | `?limit=20` | `[{id, user, raya}]` | Historique récent |
| `/health` | GET | — | `{status}` | Santé système |
| `/token-status` | GET | — | `{warnings, ok}` | Connecteurs Microsoft |
| `/memory-status` | GET | — | `{niveau_2: {mail_memory: N}}` | Compteur mails |
| `/admin/users` | GET | — | liste users (admin only) | Détection admin |
| `/admin/backup` | GET | — | fichier backup | Backup DB |
| `/admin/extract-signatures` | POST | — | extraction signatures | Signatures email |
| `/admin/diag` | GET | — | diagnostic connecteurs | Santé connecteurs |
| `/download/{file_id}` | GET | — | fichier | Téléchargement |
| `/account/export` | GET | — | JSON complet | Export RGPD |
| `/account/delete` | DELETE | `?confirm=yes` | suppression | Suppression RGPD |
| `/legal` | GET | — | HTML | Mentions légales |
| `/onboarding/status` | GET | — | `{completed}` | État onboarding |

### API Endpoints à venir (créés par Opus)

| Endpoint | Méthode | Body | Retour | Usage |
|---|---|---|---|---|
| `GET /topics` | GET | — | `{section_title, topics: [...]}` | Liste sujets |
| `POST /topics` | POST | `{title}` | `{id, title, status}` | Créer sujet |
| `PATCH /topics/{id}` | PATCH | `{title?, status?}` | `{id, title, status}` | Modifier sujet |
| `DELETE /topics/{id}` | DELETE | — | `{ok}` | Supprimer sujet |
| `PATCH /topics/settings` | PATCH | `{section_title}` | `{section_title}` | Titre section |

### Format de la réponse `/raya`
```json
{
  "answer": "Texte markdown avec liens, tableaux, etc.",
  "actions": ["✅ Mail envoyé à X", "⏸️ Action en attente"],
  "pending_actions": [{"id": 1, "action_type": "...", "label": "...", "payload": {...}}],
  "aria_memory_id": 42,
  "model_tier": "smart",
  "ask_choice": {"question": "...", "options": ["A", "B", "C"]}
}
```

### Particularités du frontend actuel (chat.js)
- Markdown rendu avec `marked.js` + `DOMPurify`
- Notifications mémoire 🧠 filtrées → pilule verte discrète
- Balises `[ACTION:...]` retirées du texte affiché
- `[SPEAK_SPEED:X]` extrait de la réponse pour ajuster la vitesse TTS
- Ask_choice → boutons interactifs
- Pending_actions → zone de confirmation/annulation
- Fichiers : image (base64 preview), PDF (badge 📎), max 10 Mo
- Historique : séparateur "— conversation précédente —"

---

## 4. STACK FLUTTER

### Packages prévus
| Package | Usage | Version cible |
|---|---|---|
| `dio` | HTTP client | ^5.x |
| `cookie_jar` + `dio_cookie_manager` | Gestion cookies session | latest |
| `flutter_secure_storage` | Stockage sécurisé credentials | latest |
| `riverpod` / `flutter_riverpod` | State management | ^2.x |
| `flutter_markdown` | Rendu markdown réponses | latest |
| `just_audio` | Lecture TTS ElevenLabs | latest |
| `speech_to_text` | Reconnaissance vocale native | latest |
| `image_picker` | Sélection images | latest |
| `file_picker` | Sélection PDF/fichiers | latest |
| `device_info_plus` | Info appareil (bug reports) | latest |
| `firebase_messaging` | Push notifications (futur) | latest |
| `url_launcher` | Ouverture liens externes | latest |

### Structure du projet
```
flutter/
├── lib/
│   ├── main.dart
│   ├── config/
│   │   └── api_config.dart         # Base URL, constantes
│   ├── models/
│   │   ├── message.dart            # Message chat
│   │   ├── user.dart               # User + session
│   │   ├── feedback.dart           # Feedback payload
│   │   ├── pending_action.dart     # Action en attente
│   │   ├── ask_choice.dart         # Choix interactif
│   │   └── topic.dart              # Sujet utilisateur
│   ├── services/
│   │   ├── api_service.dart        # Client HTTP + cookies
│   │   ├── auth_service.dart       # Login/logout
│   │   ├── chat_service.dart       # POST /raya + historique
│   │   ├── tts_service.dart        # POST /speak + lecture audio
│   │   ├── stt_service.dart        # Reconnaissance vocale
│   │   ├── feedback_service.dart   # Feedback + bug report
│   │   └── topics_service.dart     # CRUD sujets
│   ├── providers/
│   │   ├── auth_provider.dart
│   │   ├── chat_provider.dart
│   │   ├── voice_provider.dart
│   │   └── topics_provider.dart
│   └── screens/
│       ├── login_screen.dart
│       ├── chat_screen.dart
│       └── widgets/
│           ├── message_bubble.dart
│           ├── chat_input.dart
│           ├── pending_actions_bar.dart
│           ├── ask_choice_buttons.dart
│           ├── feedback_buttons.dart
│           ├── settings_menu.dart      # Menu ⋮
│           └── topics_sheet.dart       # Bottom sheet sujets
├── pubspec.yaml
├── ios/
└── android/
```

---

## 5. PLAN DE DÉVELOPPEMENT

### Phase 1 — Squelette & Auth ⬜ (EN ATTENTE)
- [ ] F1.1 : `flutter create` + structure dossiers
- [ ] F1.2 : `api_service.dart` (dio + cookie_jar + base URL)
- [ ] F1.3 : `auth_service.dart` (login POST /login-app, logout)
- [ ] F1.4 : `login_screen.dart` (écran login username/password)
- [ ] F1.5 : Navigation login → chat (route guard)
- [ ] F1.6 : Stockage sécurisé de la session

### Phase 2 — Chat core ⬜
- [ ] F2.1 : `chat_service.dart` (POST /raya + GET /chat/history)
- [ ] F2.2 : `chat_screen.dart` (liste de messages scrollable + header)
- [ ] F2.3 : `message_bubble.dart` (rendu markdown, avatar, actions)
- [ ] F2.4 : `chat_input.dart` (input texte + bouton envoi + micro + 📎)
- [ ] F2.5 : Gestion `ask_choice` → boutons interactifs
- [ ] F2.6 : Gestion `pending_actions` → zone confirmation
- [ ] F2.7 : Pièces jointes image (picker + base64 + preview)
- [ ] F2.8 : Pièces jointes PDF (picker + base64 + badge)
- [ ] F2.9 : Historique au chargement + séparateur + scroll infini

### Phase 3 — Voix (GAIN PRINCIPAL) ⬜
- [ ] F3.1 : `tts_service.dart` (POST /speak → audio/mpeg → lecture just_audio)
- [ ] F3.2 : Bouton "🔊 Écouter" sur chaque bulle Raya
- [ ] F3.3 : AutoSpeak toggle (lecture auto des réponses)
- [ ] F3.4 : `stt_service.dart` (speech_to_text natif)
- [ ] F3.5 : Bouton micro (maintien = écoute, relâche = envoi)
- [ ] F3.6 : Indicateur visuel micro actif

### Phase 4 — Feedback & SAV ⬜
- [ ] F4.1 : Boutons 👍👎💡 sur chaque réponse
- [ ] F4.2 : Dialog feedback négatif (commentaire)
- [ ] F4.3 : Bouton 🐛 bug report + dialog Bug/Amélioration
- [ ] F4.4 : `device_info_plus` pour info appareil auto

### Phase 5 — Admin, Sujets & Polish ⬜
- [ ] F5.1 : `settings_menu.dart` — menu ⋮ (AutoSpeak, vitesse, thème, admin, RGPD, déconnexion)
- [ ] F5.2 : Actions admin (backup, signatures, diag, connecteurs)
- [ ] F5.3 : RGPD (export, suppression, mentions légales)
- [ ] F5.4 : `topics_sheet.dart` — bottom sheet sujets (DÉPEND endpoints Opus)
- [ ] F5.5 : `topics_service.dart` — CRUD sujets via API
- [ ] F5.6 : Titre section personnalisable + noms sujets éditables
- [ ] F5.7 : Thème Raya (couleurs, fonts, dark mode)
- [ ] F5.8 : Splash screen + icône app
- [ ] F5.9 : Push notifications (Firebase — préparation)
- [ ] F5.10 : Onboarding (si pas complété)

---

## 6. HISTORIQUE DES SESSIONS

### Session 14/04/2026 — Initialisation + Design UX
- Lecture complète du projet : `raya_session_state.md`, `raya_roadmap_demo.md`, `raya_maintenance.md`
- Lecture code : `raya.py`, `deps.py`, `auth.py`, `chat.js`
- Compréhension de l'API complète et du frontend actuel
- Création de ce document de suivi
- Décision : cookies de session (pas JWT pour l'instant)
- Plan de développement en 5 phases établi
- **Design UX figé avec Guillaume** : écran minimaliste, conversation unique, menu ⋮, micro héros
- **Fonctionnalité "Sujets"** validée : bottom sheet, titre section personnalisable, noms éditables
- Création de `docs/raya_flutter_ux_specs.md` (rapport complet pour Opus)

---

## 7. REPRISE
« Bonjour. Projet Raya, conversation Flutter. Guillaume Perrin (Couffrant Solar). En français, vocabulaire Terminal, concis. Tu es l'EXÉCUTANT Flutter. Lis `docs/raya_flutter_session.md` sur `per1gyom/couffrant-assistant` branche `main` via GitHub MCP. Reprends où on en était. »
