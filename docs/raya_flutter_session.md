# Raya Flutter — État de session & Suivi

**Dernière mise à jour : 19/04/2026** — Opus (exécutant Flutter)
**Conversation dédiée : développement app native iOS/Android**
**Repo :** `per1gyom/couffrant-assistant` branche `main`, dossier `flutter/`

---

## ⚠️ RÈGLES DE CETTE CONVERSATION

### Rôles
- **Opus = exécutant Flutter** : code l'app native, pousse sur `main` (dossier `flutter/`)
- **Opus (autre conversation) = architecte backend** : gère le backend FastAPI/Railway/PostgreSQL. Ne touche PAS au Flutter.
- **Guillaume Perrin = décideur** : dirige Couffrant Solar, valide, teste, fait le pont entre les deux conversations.

### Workflow
- Commits courts (1-2 fichiers max par commit)
- Langue : français, vocabulaire "Terminal", concis
- Fin de session : mettre à jour CE document avec l'avancement
- Chaque prompt commence par lire ce fichier pour reprendre le contexte
- **Ne jamais modifier les fichiers backend** (dossier `app/`) — c'est le domaine d'Opus backend
- **Accès Desktop Commander** pour exécuter des commandes sur le Mac de Guillaume
- **Accès GitHub MCP** pour lire/écrire sur le repo

### Documents liés sur le repo
- `docs/raya_flutter_ux_specs.md` — Specs UX complètes (design, sujets, endpoints attendus)
- `docs/raya_flutter_to_opus_report.md` — Rapport de coordination Flutter → Backend
- `docs/raya_session_state.md` — État du backend (géré par Opus backend)

---

## ENVIRONNEMENT TECHNIQUE (CRITIQUE POUR LA REPRISE)

### Machine de Guillaume
- **macOS 26.4.1 Tahoe** sur Mac Apple Silicon
- **Flutter 3.41.6** canal **beta** (installé via Homebrew : `/opt/homebrew/share/flutter/`)
- **Xcode 26.4** (17E192)
- **CocoaPods 1.16.2**
- **GitHub CLI** (`gh`) installé et authentifié (compte `per1gyom`, auth Google)
- **Simulateur** : iPhone 17 (ID: `8959A543-1906-4CD8-BB21-2A4E8F814EBF`)

### Chemins importants
- **Projet Flutter local** : `/Users/per1guillaume/Developer/couffrant-assistant/flutter/`
- **⚠️ PAS dans Documents** — iCloud ajoute des resource forks qui cassent Xcode
- **SDK Flutter** : `/opt/homebrew/share/flutter/`
- **Ancien emplacement** (ne plus utiliser) : `/Users/per1guillaume/Documents/couffrant-assistant/`

### PATCH SDK Flutter appliqué (⚠️ SERA PERDU SI FLUTTER EST MIS À JOUR)
Xcode 26 refuse de codesigner les binaires avec des "resource forks" (attributs étendus macOS). Le SDK Flutter ne les nettoyait que partiellement. Patch appliqué sur 2 fichiers :

**Fichier 1 :** `/opt/homebrew/share/flutter/packages/flutter_tools/lib/src/ios/mac.dart`
- Fonction `removeExtendedAttributes()` modifiée
- Avant : supprimait seulement `com.apple.FinderInfo` et `com.apple.provenance` individuellement
- Après : utilise `xattr -c -r` pour supprimer TOUS les attributs étendus récursivement

**Fichier 2 :** `/opt/homebrew/share/flutter/packages/flutter_tools/lib/src/build_system/targets/ios.dart`
- Fonction `_signFramework()` modifiée
- Ajouté nettoyage xattrs sur le dossier parent `.framework` en plus du binaire

**Pour réappliquer le patch après une mise à jour Flutter :**
```bash
# mac.dart — remplacer la boucle for/attributesToRemove par :
#   xattr -c -r projectDirectory.path
# ios.dart — ajouter removeExtendedAttributes sur binary.parent en plus de binary
```

### Packages Flutter actifs (pubspec.yaml)
```yaml
dependencies:
  dio: ^5.4.0
  dio_cookie_manager: ^3.1.1
  cookie_jar: ^4.0.8
  flutter_secure_storage: ^9.0.0
  flutter_riverpod: ^2.4.9
  flutter_markdown: ^0.6.18
  just_audio: ^0.9.36
  device_info_plus: ^9.1.1
  url_launcher: ^6.2.2
  path_provider: ^2.1.1
  local_auth: ^2.1.8
```

### Packages retirés temporairement (incompatibles Xcode 26)
```yaml
# image_picker: ^1.0.7      # Cause : DKImagePickerController/SDWebImage erreurs build
# file_picker: ^6.1.1       # Cause : mêmes dépendances
# speech_to_text: ^6.6.0    # Cause : warnings deprecated, à retester
```

### Commandes de lancement rapide
```bash
# Ouvrir simulateur + lancer app
open -a Simulator && sleep 3 && xcrun simctl boot 8959A543-1906-4CD8-BB21-2A4E8F814EBF 2>/dev/null
cd /Users/per1guillaume/Developer/couffrant-assistant/flutter && flutter run -d 8959A543-1906-4CD8-BB21-2A4E8F814EBF

# Hot reload (si app déjà lancée, taper dans le Terminal flutter)
r

# Pull + relance
cd /Users/per1guillaume/Developer/couffrant-assistant && git pull && cd flutter && flutter run -d 8959A543-1906-4CD8-BB21-2A4E8F814EBF
```

---

## ARCHITECTURE DE L'APP FLUTTER (1409 lignes total)

```
flutter/lib/
├── main.dart                       (111 lignes) Splash screen vert + route guard session + timeout 5s
├── config/
│   └── api_config.dart              (24 lignes) Base URL https://app.raya-ia.fr + tous endpoints
├── services/
│   ├── api_service.dart             (84 lignes) Singleton Dio + cookie_jar (mobile) / withCredentials (web)
│   ├── auth_service.dart            (98 lignes) POST /login-app (form-encoded), gère redirect 302/303 + 200, cache username
│   ├── chat_service.dart           (148 lignes) POST /raya + GET /chat/history + modèles (ChatMessage, RayaResponse, AskChoice, PendingAction)
│   ├── tts_service.dart             (90 lignes) POST /speak → bytes audio/mpeg → just_audio natif (BytesAudioSource)
│   ├── feedback_service.dart        (85 lignes) POST /raya/feedback, GET /raya/why/{id}, POST /raya/bug-report + device_info_plus
│   └── topics_service.dart          (91 lignes) GET/POST/PATCH/DELETE /topics — CRUD sujets via API backend
└── screens/
    ├── login_screen.dart            (?? lignes) Login complet : identifiant, mdp, oeil show/hide, "Mot de passe oublié ?", mentions légales
    ├── chat_screen.dart            (506 lignes) Écran principal — tout le chat + feedback + TTS + sujets + menu
    └── topics_sheet.dart           (172 lignes) Bottom sheet sujets : liste, créer, modifier, supprimer, titre personnalisable
```

### Détail chat_screen.dart (fichier principal, 506 lignes)
- **Imports** : material, flutter_markdown, url_launcher, auth_service, chat_service, tts_service, feedback_service, topics_service, login_screen, topics_sheet
- **État** : messages, pendingActions, askChoice, loading, historyLoaded, autoSpeak, username, likedIds, dislikedIds
- **Header** : point vert santé + "Raya" + bouton 🔖 sujets + menu ⋮
- **Menu ⋮** : Connecté : username, AutoSpeak ON/OFF, Vitesse (ouvre bottom sheet slider), Mentions légales (ouvre /legal), Déconnexion
- **Messages** : ListView avec séparateur historique, bulles user (bleu) / raya (gris), rendu markdown, avatar ✦
- **Feedback sous chaque message Raya** : 🔊 (TTS play/stop), 👍 (feedback positif, s'allume vert), 👎 (dialog commentaire, s'allume rouge), 💡 (dialog métadonnées), 🐛 (dialog bug/amélioration)
- **AutoSpeak** : lit automatiquement chaque réponse de Raya via TTS
- **Slider vitesse** : bottom sheet avec slider 0.5x→2.5x + bouton réinitialiser
- **Sujets** : bouton bookmark_outline dans header → ouvre TopicsSheet
- **Auto-création topic** : détecte `[ACTION:CREATE_TOPIC:titre]` dans les réponses de Raya
- **Input bar** : 📎 (placeholder), champ texte, micro vert (placeholder), bouton envoi
- **Nettoyage réponses** : retire `[ACTION:...]` et `[SPEAK_SPEED:...]` avant affichage

---

## BACKEND — ENDPOINTS CONSOMMÉS

**Base URL** : `https://app.raya-ia.fr`
**Auth** : cookies de session (pas JWT) via `dio_cookie_manager`

| Endpoint | Méthode | Usage | État Flutter |
|---|---|---|---|
| `/login-app` | POST form | Login (username + password) | ✅ Fonctionne |
| `/logout` | GET | Déconnexion | ✅ Fonctionne |
| `/health` | GET | Vérification session | ✅ Fonctionne |
| `/raya` | POST JSON | Conversation principale | ✅ Fonctionne |
| `/chat/history` | GET | Historique messages | ✅ Fonctionne |
| `/speak` | POST JSON | TTS ElevenLabs → audio/mpeg | ✅ Fonctionne |
| `/raya/feedback` | POST JSON | Feedback 👍👎 | ✅ Branché |
| `/raya/why/{id}` | GET | Métadonnées réponse 💡 | ✅ Branché |
| `/raya/bug-report` | POST JSON | Bug report 🐛 | ✅ Branché |
| `/topics` | GET | Liste sujets utilisateur | ✅ Branché |
| `/topics` | POST JSON | Créer sujet | ✅ Branché |
| `/topics/{id}` | PATCH JSON | Modifier sujet | ✅ Branché |
| `/topics/{id}` | DELETE | Supprimer sujet | ✅ Branché |
| `/topics/settings` | PATCH JSON | Titre section personnalisable | ✅ Branché |
| `/legal` | GET | Mentions légales (lien externe) | ✅ Lien |

### Format réponse `/raya`
```json
{
  "answer": "Texte markdown...",
  "actions": ["✅ Mail envoyé", "⏸️ Action en attente"],
  "pending_actions": [{"id": 1, "action_type": "...", "label": "...", "payload": {...}}],
  "aria_memory_id": 42,
  "model_tier": "smart",
  "ask_choice": {"question": "...", "options": ["A", "B", "C"]}
}
```

Balises spéciales dans `answer` (nettoyées par Flutter avant affichage) :
- `[ACTION:CREATE_TOPIC:titre]` → auto-crée le sujet dans la liste
- `[ACTION:TYPE:payload]` → retiré du texte
- `[SPEAK_SPEED:1.5]` → ajuste la vitesse TTS

---

## PLAN DE DÉVELOPPEMENT — ÉTAT ACTUEL

### Phase 1 — Auth ✅ TERMINÉE
### Phase 2 — Chat ✅ TERMINÉE (sauf pièces jointes — packages retirés)
### Phase 3 — Voix 🟡 PARTIELLE (TTS OK, micro STT bloqué)
### Phase 4 — Feedback ✅ TERMINÉE (👍👎💡🐛 branchés)
### Phase 5 — Sujets & Menu ✅ PARTIELLE

**Fait :**
- [x] TopicsService (CRUD via API backend)
- [x] TopicsSheet (bottom sheet : liste, créer, modifier, supprimer, titre personnalisable)
- [x] Bouton 🔖 dans le header
- [x] Auto-création topic depuis ACTION:CREATE_TOPIC
- [x] Mentions légales dans le menu
- [x] Slider vitesse voix (bottom sheet)
- [x] AutoSpeak toggle

**Reste à faire :**
- [ ] Thème sombre/clair
- [ ] Actions admin (backup, signatures, diag)
- [ ] RGPD (export, suppression)
- [ ] Face ID / Touch ID (local_auth installé)
- [ ] Splash screen + icône personnalisés
- [ ] Push notifications (Firebase)
- [ ] Onboarding

### Phase 6 — Déploiement ⬜ À FAIRE
- [ ] Compte Apple Developer (99€/an)
- [ ] Test sur iPhone réel (USB)
- [ ] TestFlight (beta)
- [ ] App Store

---

## BUG CONNU À CORRIGER

### ~~Regex CREATE_TOPIC double-escaped~~ ✅ FIX 19/04 (commit d6ec52f)
Ligne 70 de `chat_screen.dart` : le regex utilisait `\\[` (double backslash) au lieu de `\[` (simple). Corrigé. Bonus : caractère U+FFFD (replacement char) dans "Mentions légales" ligne 331 remplacé par vrai `é` UTF-8.

---

## RECHERCHE DE MARQUE — ELYO

**Meilleur candidat** après 11 recherches INPI. Libre en classes 9 (logiciels), 38 (télécom), 42 (SaaS/IA). Zone grise en classe 35 (sous-catégorie différente).
Classes à déposer : 9, 35, 38, 42, 45. Coût ~310€ INPI.

**Avocats recommandés pour protéger Raya/ELYO :**
1. **Éris Avocat** (Paris, 4.9/5) — spécialisé PI, Marques, Numérique, RGPD, INPI — Tél : 06 95 59 57 68
2. **Sophie Mongis** (Tours, 4.9/5) — PI, proximité — Tél : 02 47 40 98 02
3. **Ipolit** (Lyon, 5.0/5) — PI & SaaS startups — Tél : 07 56 90 76 06

---

## HISTORIQUE DES SESSIONS

### Session 14-15/04/2026 — Marathon initial (Opus 4.6)
**Durée : ~7h | ~25 commits**

- Installation complète toolchain (Flutter, Xcode, CocoaPods, iOS Simulator)
- Résolution bug resource fork Xcode 26 (patch SDK Flutter)
- Résolution bug iCloud (déplacement projet vers /Developer)
- Installation et auth GitHub CLI (`gh`)
- Phases 1-4 complètes + Phase 5 partielle
- App fonctionnelle sur simulateur iPhone 17 avec chat, TTS, feedback, sujets
- Coordination avec Opus backend (endpoints topics créés et intégrés)
- 11 recherches INPI → candidat ELYO
- 3 cabinets d'avocats PI identifiés
- UX figé, documentation complète

### Priorités prochaine session
1. ~~Corriger bug regex CREATE_TOPIC~~ ✅ 19/04 (d6ec52f)
2. **Re-ajouter speech_to_text** pour le micro natif STT (héros UX bouton vert)
3. **Re-ajouter file_picker/image_picker** pour les pièces jointes (tester compat Xcode 26)
4. **Thème personnalisé ELYO** (couleurs, fonts, dark/light, splash, icône)
5. **Tester sur iPhone réel** (brancher USB, configurer Apple ID dans Xcode Signing)
6. **Préparer TestFlight** (compte Apple Developer 99€/an)

### Session 19/04/2026 — Reprise (Opus 4.7)
**Contexte :** entre le 15/04 et le 19/04, seuls des commits backend/PWA (permissions, scanner, connecteurs) ont eu lieu. Flutter resté en l'état.

**Commits :**
- `d6ec52f` — fix regex CREATE_TOPIC + encoding Mentions légales

**À venir :** audit projet complet + micro STT natif

---

## PROMPT DE REPRISE

Copier-coller ce message pour démarrer une nouvelle session :

---

Bonjour. Projet Raya, conversation Flutter. Guillaume Perrin (Couffrant Solar). En français, vocabulaire Terminal, concis.

Tu es l'EXÉCUTANT Flutter pour l'app native iOS Raya (assistant IA pour dirigeants).

Lis `docs/raya_flutter_session.md` sur `per1gyom/couffrant-assistant` branche `main` via GitHub MCP. Ce document contient tout le contexte : architecture, fichiers, bugs, environnement technique, prochaines priorités.

Le projet local est dans `/Users/per1guillaume/Developer/couffrant-assistant/flutter/`. Tu as accès au Desktop Commander pour exécuter des commandes sur mon Mac et au GitHub MCP pour lire/écrire sur le repo.

Reprends où on en était. Les priorités sont listées dans le document.

---
