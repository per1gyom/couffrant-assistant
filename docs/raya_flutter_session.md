# Raya Flutter — État de session & Suivi

**Dernière mise à jour : 14/04/2026 22h00** — Opus (exécutant Flutter)
**Conversation dédiée : développement app native iOS/Android**

---

## ⚠️ RÈGLES DE CETTE CONVERSATION

### Rôles
- **Opus = exécutant Flutter** : code l'app native, pousse sur `main` (dossier `flutter/`)
- **Opus (autre conversation) = architecte backend** : gère le backend. Ne touche PAS au Flutter.
- **Guillaume = décideur** : valide, teste, fait le pont entre les deux conversations.

### Workflow
- Commits courts (1-2 fichiers max par commit)
- Langue : français, vocabulaire "Terminal", concis
- Fin de session : mettre à jour CE document avec l'avancement
- Chaque prompt commence par lire ce fichier pour reprendre le contexte
- **Projet local** : `/Users/per1guillaume/Developer/couffrant-assistant/flutter/` (PAS Documents — iCloud cause des erreurs)

### Documents liés
- `docs/raya_flutter_ux_specs.md` — Specs UX complètes (pour Opus backend + PWA)
- `docs/raya_session_state.md` — État du backend (géré par Opus)

### Environnement technique
- macOS 26.4.1 (Tahoe), Mac Apple Silicon
- Flutter 3.41.6 canal beta
- Xcode 26.4
- CocoaPods 1.16.2
- **PATCH appliqué** sur Flutter SDK : `mac.dart` et `ios.dart` modifiés pour `xattr -cr` (fix resource fork Xcode 26)
- Simulateur : iPhone 17 (ID: 8959A543-1906-4CD8-BB21-2A4E8F814EBF)
- Packages retirés temporairement : `file_picker`, `image_picker`, `speech_to_text` (incompatibles Xcode 26)

---

## 1. PHILOSOPHIE DU PROJET

**Raya = cerveau supplémentaire pour dirigeant.**
- LLM-agnostic, tools-agnostic, channel-agnostic
- L'app Flutter est un **nouveau canal** qui consomme la même API
- Pas de logique métier dans Flutter — tout est côté backend
- **Nom de marque en cours : ELYO** (meilleur candidat INPI, libre classes 9/38/42)

---

## 2. DESIGN UX FIGÉ (validé Guillaume 14/04/2026)

(inchangé — voir version précédente pour le détail complet)

### Résumé
- Conversation unique, écran = 95% échange, voix en premier
- Header : point vert + nom + menu ⋮
- Menu ⋮ : AutoSpeak toggle, slider vitesse voix, déconnexion
- Barre input : 📎 + texte + micro vert + envoi
- Sujets : bottom sheet (DÉPEND endpoints Opus)

---

## 3. FICHIERS FLUTTER EXISTANTS

```
flutter/lib/
├── main.dart                    ✅ Splash + route guard session
├── config/
│   └── api_config.dart          ✅ Base URL + tous les endpoints
├── services/
│   ├── api_service.dart         ✅ Dio + cookie_jar + web compatible
│   ├── auth_service.dart        ✅ Login/logout + cache username
│   ├── chat_service.dart        ✅ POST /raya + historique + modèles
│   └── tts_service.dart         ✅ POST /speak + just_audio natif
└── screens/
    ├── login_screen.dart        ✅ Login + mot de passe oublié + mentions légales
    └── chat_screen.dart         ✅ Chat complet (markdown, feedback, TTS, menu ⋮, slider vitesse)
```

---

## 4. PLAN DE DÉVELOPPEMENT

### Phase 1 — Squelette & Auth ✅ TERMINÉE
- [x] F1.1 : `flutter create` + structure dossiers
- [x] F1.2 : `api_service.dart` (dio + cookie_jar + base URL)
- [x] F1.3 : `auth_service.dart` (login POST /login-app, logout)
- [x] F1.4 : `login_screen.dart` (écran login + mot de passe oublié)
- [x] F1.5 : Navigation login → chat (route guard + splash)
- [x] F1.6 : Gestion session (cache mémoire — secure storage à ajouter pour iOS natif)

### Phase 2 — Chat core ✅ TERMINÉE
- [x] F2.1 : `chat_service.dart` (POST /raya + GET /chat/history + modèles)
- [x] F2.2 : `chat_screen.dart` (liste de messages scrollable + header)
- [x] F2.3 : Rendu markdown (flutter_markdown), avatar ✦, bulles
- [x] F2.4 : Input texte + bouton envoi + micro (placeholder) + 📎 (placeholder)
- [x] F2.5 : Gestion `ask_choice` → boutons interactifs
- [x] F2.6 : Gestion `pending_actions` → zone confirmation/annulation
- [ ] F2.7 : Pièces jointes image (BLOQUÉ — `image_picker` retiré pour Xcode 26)
- [ ] F2.8 : Pièces jointes PDF (BLOQUÉ — `file_picker` retiré pour Xcode 26)
- [x] F2.9 : Historique au chargement + séparateur

### Phase 3 — Voix 🟡 EN COURS
- [x] F3.1 : `tts_service.dart` (POST /speak → audio/mpeg → lecture just_audio)
- [x] F3.2 : Bouton 🔊 Écouter fonctionnel (tap = play, re-tap = stop)
- [x] F3.3 : AutoSpeak toggle dans menu ⋮
- [x] F3.3b : Slider vitesse voix (bottom sheet, 0.5x → 2.5x)
- [ ] F3.4 : `stt_service.dart` (BLOQUÉ — `speech_to_text` retiré pour Xcode 26)
- [ ] F3.5 : Bouton micro (maintien = écoute, relâche = envoi)
- [ ] F3.6 : Indicateur visuel micro actif

### Phase 4 — Feedback & SAV ⬜ À FAIRE
- [ ] F4.1 : Boutons 👍👎 → POST /raya/feedback
- [ ] F4.2 : Dialog feedback négatif (commentaire)
- [ ] F4.3 : Bouton 🐛 → POST /raya/bug-report + dialog Bug/Amélioration
- [ ] F4.4 : Bouton 💡 → GET /raya/why/{id}
- [ ] F4.5 : `device_info_plus` pour info appareil auto

### Phase 5 — Admin, Sujets & Polish ⬜ À FAIRE
- [ ] F5.1 : Compléter menu ⋮ (thème sombre/clair, admin, RGPD, mentions légales)
- [ ] F5.2 : Actions admin (backup, signatures, diag, connecteurs)
- [ ] F5.3 : RGPD (export, suppression, mentions légales)
- [ ] F5.4 : `topics_sheet.dart` — bottom sheet sujets (DÉPEND endpoints Opus)
- [ ] F5.5 : `topics_service.dart` — CRUD sujets via API
- [ ] F5.6 : Titre section personnalisable + noms sujets éditables
- [ ] F5.7 : Thème Raya (couleurs, fonts, dark/light mode)
- [ ] F5.8 : Splash screen + icône app personnalisés
- [ ] F5.9 : Push notifications (Firebase)
- [ ] F5.10 : Onboarding
- [ ] F5.11 : Face ID / Touch ID (local_auth — package déjà installé)

### Phase 6 — Déploiement ⬜ À FAIRE
- [ ] F6.1 : Compte Apple Developer (99€/an)
- [ ] F6.2 : Test sur iPhone réel (USB)
- [ ] F6.3 : TestFlight (beta testing)
- [ ] F6.4 : Publication App Store

---

## 5. BUGS CONNUS / CONTOURNEMENTS

### Flutter + Xcode 26 (macOS Tahoe) — resource fork
- **Problème** : Xcode 26 refuse de codesigner les binaires avec des "resource forks" (attributs étendus macOS)
- **Cause** : Flutter SDK installé via Homebrew a des attributs `com.apple.provenance`/`com.apple.FinderInfo`
- **Fix appliqué** : patch de `mac.dart` et `ios.dart` dans le SDK Flutter pour utiliser `xattr -cr` au lieu de supprimer des attributs individuels
- **Fichiers patchés** :
  - `/opt/homebrew/share/flutter/packages/flutter_tools/lib/src/ios/mac.dart`
  - `/opt/homebrew/share/flutter/packages/flutter_tools/lib/src/build_system/targets/ios.dart`
- **⚠️ ATTENTION** : ce patch sera perdu si Flutter est mis à jour. Il faudra le réappliquer.

### iCloud + Flutter build
- **Problème** : le dossier Documents est synchronisé iCloud, qui ajoute des resource forks aux fichiers
- **Fix** : projet déplacé vers `/Users/per1guillaume/Developer/couffrant-assistant/`

### Packages incompatibles Xcode 26
- `file_picker` (via DKImagePickerController/SDWebImage) — erreurs de build
- `image_picker` (même dépendances) — erreurs de build
- `speech_to_text` — warnings deprecated mais devrait fonctionner (à retester)
- **À retester** quand Flutter stable intègre le fix Xcode 26

---

## 6. RECHERCHE DE MARQUE — ELYO

11 recherches INPI effectuées. Résultat :

| Nom testé | Cl. 9 | Cl. 42 | Verdict |
|---|---|---|---|
| Raya | ❌ | ❌ | Déjà déposé |
| NOÏA | ❌ | ❌ | Bloqué |
| AXIO | ❌ | ❌ | Bloqué |
| ELYA | ❌ | ❌ | Bloqué |
| EYA | ❌ | ❌ | Bloqué |
| LISIA | — | ❌ | Bloqué |
| ELISIA | ❌ | ❌ | Bloqué |
| ELIS/ELISA | ❌ | ❌ | 130 résultats |
| BOBI | ⚠️ | ✅ | Possible mais pas premium |
| **ELYO** | **✅** | **✅** | **Meilleur candidat** |

Classes nécessaires pour le dépôt : **9** (logiciels), **35** (gestion commerciale), **38** (télécommunications), **42** (SaaS/IA), **45** (assistant personnel).
Coût estimé : ~310€ INPI. Prochaine étape : consulter un conseil en propriété intellectuelle.

---

## 7. HISTORIQUE DES SESSIONS

### Session 14/04/2026 — Marathon initial (Opus)
**Durée : ~5h | ~20 commits Flutter**

**Infrastructure :**
- Installation Flutter, Xcode, CocoaPods sur Mac Guillaume
- Résolution bug resource fork (patch SDK Flutter)
- Résolution bug iCloud (déplacement projet)
- App compilée et fonctionnelle sur simulateur iPhone 17

**Code produit :**
- Phase 1 complète (auth, login, splash, navigation)
- Phase 2 complète (chat, markdown, historique, ask_choice, pending_actions)
- Phase 3 partielle (TTS ElevenLabs, AutoSpeak, slider vitesse)

**Design & Documentation :**
- UX figé (conversation unique, menu ⋮, micro héros, sujets)
- `raya_flutter_ux_specs.md` créé pour Opus backend
- `raya_flutter_session.md` créé et mis à jour
- 11 recherches INPI → candidat ELYO identifié

**Prochaines priorités (session suivante) :**
1. Phase 4 : feedback 👍👎💡🐛 (brancher sur les vrais endpoints)
2. Tester sur iPhone réel (USB)
3. Re-ajouter `speech_to_text` pour le micro natif
4. Sujets (quand Opus aura créé les endpoints)

---

## 8. REPRISE
« Bonjour. Projet Raya, conversation Flutter. Guillaume Perrin (Couffrant Solar). En français, vocabulaire Terminal, concis. Tu es l'EXÉCUTANT Flutter. Lis `docs/raya_flutter_session.md` sur `per1gyom/couffrant-assistant` branche `main` via GitHub MCP. Reprends où on en était. »
