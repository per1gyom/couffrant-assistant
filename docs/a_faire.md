# À faire — Roadmap Raya

Document de suivi des chantiers ouverts. Mis à jour au fil de l'eau.

**Dernière MAJ** : 25 avril 2026 soir.

---

## 🆕 Récap des chantiers TERMINÉS cette semaine (22-26 avril)

### Page /settings — 6 phases déployées en prod
- Phase 1-6 : route /settings + 5 onglets (Profil, Conso, Règles, Connexions, Données)
- Mes règles : refonte UX complète (chip "À revoir" intelligente, regroupement Divers,
  sessions 5/5)
- Catégories : 2 vagues de migration (37 → 17 catégories canoniques, 0 doublon casse/slug)
- Validateur Sonnet sur [ACTION:LEARN] (be2f0b0)
- Mode parcours guidé "Faisons le point" — modale unifiée 3 modes review/edit/delete

### Lecture automatique TTS rapatriée (validée Guillaume 25/04)
- Toggle dans /settings → Profil + toggle rapide menu 3-points avec switch animé
- Persistance forte DB (settings.auto_speak)
- OFF par défaut pour tout le monde, l'utilisateur active selon son contexte

### 🎨 Design system modale (TERMINÉ 25/04)
**Source de vérité** : `docs/design_system_modal.md`
- `app/static/_modal_system.css` (288 lignes) + `_modal_system.js` (123 lignes)
- 2 tailles : `size-standard` (640px adaptative) / `size-parcours` (900×720 fixe)
- 5 tons : neutral / default(bleu) / success / warning / danger
- API `Modal.open/close/onOpen/onClose` + comportements universels (Escape, clic-fond,
  scroll lock, focus trap)
- 5 modales user migrées : requestModal, passwordModal, deleteAccountModal (tone-danger),
  modalShortcutEdit, reviewSessionModal (size-parcours)
- Panels admin/super-admin/tenant volontairement NON migrés (gardent leur thème sombre tech)
### ✍️ Éditeur signatures multi-boîtes (✅ TERMINÉ — 25 avril soir)

**État final** : fonctionnalité complète en prod. Backend, frontend et nettoyage du legacy faits. L'utilisateur peut créer/éditer/supprimer ses signatures avec un éditeur WYSIWYG sur le design system unifié, et définir une signature par défaut pour chaque boîte mail.

✅ **Étape 1 — Le moteur**

- DB : nouvelle colonne `default_for_emails TEXT[]` (commit 44cca2f)
- Endpoints `/signatures` GET/POST/PATCH adaptés (efdceb9)
- `get_email_signature(username, from_address)` : nouvelle logique de matching avec priorité au `default_for_emails` (f367e4e)
- 🐛 Fix bug Outlook : `_build_email_html` propage maintenant `from_address` au matching (avant : tjs fallback statique sur Outlook)

✅ **Étape 2.1 + 2.2 + 2.3 — L'interface**

- Nouvel onglet "Mes signatures" dans /settings avec icône dédiée (5c2e313)
- Liste des signatures sous forme de cards (preview HTML, badges boîtes "⭐ défaut" / "associée")
- Bouton suppression direct + confirmation
- Modale d'édition WYSIWYG (83332e9) en `size-parcours` :
  - Bloc Nom + Bloc Boîtes mail (checkbox associer + checkbox défaut par boîte)
  - Toolbar 13 outils : B/I/U, polices, tailles, couleurs, lien, image (par URL), listes, effacer mise en forme
  - contenteditable avec placeholder
  - Bouton Supprimer dans le footer en mode édition
- Toutes les fonctionnalités branchées sur les vrais endpoints API

✅ **Étape 2.5 + Temps 3 — Suppression du legacy** (3e51c54)

- `chat-signatures.js` supprimé (212 lignes)
- `modalUserSettings` + `modalDeleteAccount` supprimés de `raya_chat.html`
- 13 fonctions JS legacy supprimées
- `raya_chat.html` allégé de 51% (657 → 321 lignes)
- 558 lignes supprimées au total, 0 ajoutée

---

#### 🚀 Améliorations futures à prévoir pour les signatures

🔵 **AMÉLIORATION : insertion d'image en local (upload, pas URL)** — *demande Guillaume 25/04 soir*

- **Problème actuel** : le bouton 🖼 de la toolbar WYSIWYG insère une image **par URL**. L'utilisateur doit donc avoir son logo hébergé quelque part (Drive public, CDN, etc.) avant de pouvoir l'insérer. Pas pratique pour un logo perso ou une signature pro.
- **À faire** :
  - Ajouter un bouton "Importer depuis mon ordinateur" à côté du bouton URL existant
  - Drag & drop sur la zone d'édition également supporté
  - Backend : endpoint `POST /signatures/upload-image` qui accepte un fichier image (PNG/JPG/WEBP, max ~500KB), le stocke dans `app/static/signatures_uploads/` avec un nom hashé (ex: `<username>_<sha256>.png`), et retourne l'URL publique
  - Frontend : insère l'image dans le contenteditable via `<img src="/static/signatures_uploads/...">`
  - Sécurité : limiter le poids, valider le type MIME, nettoyer périodiquement les fichiers orphelins (signatures supprimées qui référençaient des images uploadées)
- **Cas d'usage type** : Guillaume veut mettre le logo Couffrant Solar dans sa signature pro, sans avoir à le re-héberger ailleurs.
- **Estimation** : ~1h30 (~30 min backend + ~45 min frontend + ~15 min tests)
- **Priorité** : moyenne — pas bloquant aujourd'hui, mais utile pour Pierre/Sabrina/Benoît quand ils seront onboardés (vrais utilisateurs métier, pas développeurs).

🔵 **AMÉLIORATION : redimensionnement des images insérées**

- Une fois insérée, une image gagne à pouvoir être redimensionnée à la souris (poignées de coin), ou via un slider de taille.
- Existait déjà dans l'ancien `chat-signatures.js` (fonction `_activateImgResize`) que nous avons supprimée — récupérable depuis l'historique git (commit `3e51c54^` ou avant).
- **Estimation** : ~30 min de portage.

🔵 **AMÉLIORATION : prévisualisation "comme dans un vrai mail"**

- Aujourd'hui la preview dans la card est un aperçu compact (max 60px de haut).
- Idée : un bouton "Aperçu" qui ouvre une mini-modale montrant la signature dans un faux mail (sujet + corps + signature) pour voir le rendu réel.
- **Estimation** : ~30 min.

🔵 **AMÉLIORATION : mécanisme "Raya demande puis apprend"** (REPORTÉ depuis le MVP)

- Si plusieurs signatures matchent une boîte sans défaut → Raya demande à l'utilisateur, retient le choix comme règle pour la prochaine fois
- Décision Guillaume 25/04 : reporté à une session future, le mécanisme "tu définis toi-même la défaut depuis /settings" suffit pour le MVP
- **Estimation** : ~1h (interrompre le flow d'envoi, dialogue avec choix multiples, update `default_for_emails` côté backend après choix utilisateur)

---

## 🎯 Vision & architecture d'isolation

### Modèle d'isolation multi-tenant (clarifié 24/04)

**Un tenant = une société cliente de Raya.**
Le dirigeant de la société souscrit à Raya pour son équipe.

#### Niveau tenant (société) — Isolation COMPLÈTE

Aucune fuite de données entre sociétés. Tenant A ne voit jamais les
données du tenant B, et réciproquement. Respecté actuellement via
`tenant_id NOT NULL` sur toutes les tables critiques.

#### Niveau utilisateur dans un tenant — Isolation QUASI-COMPLÈTE (phase actuelle)

**Décision Guillaume 24/04 matin** : on ne mutualise PAS les règles
apprises entre utilisateurs d'un même tenant pour l'instant. Risque
trop élevé de conflits d'un utilisateur à l'autre.

**Privé par utilisateur** :
- ❌ **Règles apprises** : privées à chaque utilisateur. Les
  préférences, raccourcis, conventions de Guillaume ne polluent pas
  celles de Pierre/Sabrina. Chacun construit sa propre base.
- ❌ **Conversations personnelles** : privées.
- ❌ **Mails consultés** : chaque utilisateur accède à SA boîte
  Outlook/Gmail uniquement.

**Partagé par tenant (seul point commun aujourd'hui)** :
- ✅ **Données métier externes** (Odoo, SharePoint, Drive commun)
  accessibles à tous les utilisateurs du tenant selon leur périmètre
  autorisé. C'est ce qui permet aux analyses croisées métier.

#### Évolution future — Promotion de règles tenant (pas maintenant)

Quand l'architecture aura mûri, identifier dans les règles personnelles
celles qui sont **génériques à la société** vs celles **spécifiques à
l'utilisateur** :

- Règles spécifiques (ex. "Guillaume préfère signer ses mails 'Perrin G.'")
  → restent dans `aria_rules`, filtrées par `username`.
- Règles société (ex. "Chez Couffrant, RFAC veut dire Règlement de
  Facture") → promues dans une 2ème base partagée (ex. `tenant_rules`
  ou `aria_rules_tenant`), visibles de tous les utilisateurs du tenant.

**Mécanisme de promotion** : NON-AUTOMATIQUE. La détection
(heuristique ou validation admin) doit passer par une confirmation
consciente, probablement via le dirigeant du tenant dans un panel
admin. Jamais d'auto-promotion silencieuse pour éviter la pollution
involontaire.

À traiter plus tard, quand l'architecture sera stable et qu'on aura
plusieurs utilisateurs par tenant en usage réel.

---

## 🔴 Priorité 1 — Audit isolation multi-tenant et utilisateur

**Contexte** : avant d'onboarder Pierre, Sabrina, Benoît ou un 2e tenant,
vérifier que le modèle d'isolation décrit ci-dessus est bien respecté
partout dans le code.

### Sous-chantier 1.1 — Isolation tenant (société vs société)

Tous les SELECT sur les tables sensibles doivent filtrer sur `tenant_id`
en plus de `username` quand pertinent.

Fichiers à auditer en priorité :
- `app/memory_rules.py` — save_rule, get_active_rules, lecture règles
- `app/routes/aria_context.py` — injection règles dans prompt v1
- `app/routes/raya_agent_core.py` — injection règles dans prompt v2
- `app/routes/memory.py` — endpoints admin (liste, archive, édition)
- `app/maturity.py` — calcul maturité basé sur les règles
- `app/rag.py` — retrieval semantique
- `app/embedding.py` — search_similar (vérifier filtres tenant)
- `app/graph_indexer.py` — indexation du graphe de conversations
- `app/memory_synthesis.py` — synthèse insights

### Sous-chantier 1.2 — Isolation utilisateur DANS un tenant

**Phase actuelle : isolation quasi-complète** (voir section Vision).

Ce sous-chantier est NOUVEAU et distinct du 1.1. Il faut vérifier que
toutes les tables sensibles filtrent à la fois sur `tenant_id` ET
sur `username` :

**Privé par utilisateur** (filtrer sur `username`) :
- `aria_rules` (règles apprises) : chaque user a sa propre base de
  règles, pas de partage entre users du même tenant. **Attention :
  c'est un changement par rapport à ce qui avait été supposé
  initialement.** Corriger si du code existant partage les règles au
  niveau tenant.
- `aria_memory` (conversations) : privées à chaque user
- `mail_memory` (mails indexés) : chaque user a sa boîte
- `aria_insights` : à vérifier selon leur nature
- Préférences, historique graphe, etc.

**Partagé par tenant** (filtrer uniquement sur `tenant_id`) :
- Accès aux données métier externes : Odoo, SharePoint, Drive commun
  (la permission est gérée côté source, pas côté Raya)
- Connecteurs OAuth de niveau tenant : Odoo API key, Anthropic API
  key si BYO, etc.

### Tests de non-régression à faire ensuite

Créer un 2e user fictif dans le tenant `couffrant_solar` (ex. `pierre_test`),
puis vérifier :

1. Pierre NE voit PAS les règles de Guillaume ❌ (nouveau : isolation
   utilisateur)
2. Pierre NE voit PAS les conversations privées de Guillaume ❌
3. Pierre NE voit PAS les mails de Guillaume ❌
4. Pierre ET Guillaume voient tous deux les données Odoo Couffrant
   (accès partagé métier) ✅
5. Une règle apprise par Pierre n'affecte PAS les réponses de Guillaume ❌

Puis tester l'isolation tenant :
- `charlotte_agency` / `charlotte` ne doit voir QUE ses 10 règles, jamais
  celles de couffrant_solar.

**Durée estimée** : 60-90 min (audit + 4-6 fichiers à corriger + tests)

---

## 🟠 Priorité 2 — Connexion simplifiée des outils tiers (panel admin tenant)

**Contexte** : aujourd'hui brancher une boîte Outlook/Gmail ou un compte
Drive demande des manipulations techniques (OAuth dans la console Azure,
configuration Railway, etc.). C'est acceptable pour Guillaume mais
impossible à déléguer à Pierre, Sabrina ou un nouveau tenant.

### Objectif

Le panel admin d'un tenant doit proposer un **catalogue de connecteurs**
avec, pour chacun, un bouton **"Connecter"** qui :

1. Ouvre une pop-up OAuth/API key
2. Guide l'utilisateur étape par étape (ex. Gmail : authentifier,
   autoriser, c'est fini)
3. Stocke automatiquement les tokens en DB avec le bon `tenant_id` +
   `username`
4. Valide la connexion (test GET) et affiche ✅ Connecté
5. Permet de déconnecter / reconnecter facilement

### Connecteurs prioritaires à ouvrir (par ordre d'impact)

| # | Service | Mode | Effort |
|---|---|---|---|
| 1 | **Gmail** (OAuth) | Semi-auto via Google OAuth flow | Moyen |
| 2 | **Outlook / Microsoft 365** (OAuth) | Déjà en place pour Guillaume, à généraliser | Faible |
| 3 | **Google Drive** (OAuth) | Même flow que Gmail | Faible (une fois #1 fait) |
| 4 | **OneDrive / SharePoint** (OAuth) | Même que Outlook | Faible |
| 5 | **Odoo OpenFire** (API key) | Déjà en place, à encapsuler dans l'UI | Faible |
| 6 | **Anthropic API key** (si BYO) | Saisie manuelle simple | Très faible |
| 7 | **Calendrier Google/Outlook** (OAuth) | Intégré à #1 et #2 | Très faible |

### Architecture technique cible

**Ne PAS stocker en clair** les tokens/clés API dans la DB :

- Chiffrement au repos (encryption key Railway)
- Rotation automatique des refresh tokens
- Mécanisme de révocation si un user quitte le tenant

**Niveau utilisateur vs tenant** :

- Boîtes mail perso : **par utilisateur** (chacun sa Gmail/Outlook)
- Odoo, Drive commun, Anthropic API key : **par tenant** (tous les users du tenant partagent la connexion)

### Sous-chantiers

1. **Architecture encapsulation** : créer `app/connectors/` avec une interface standard (`connect()`, `test()`, `disconnect()`, `list_scopes()`)
2. **UI panel admin** : nouvelle page `/admin/connectors` avec liste des connecteurs + statut + bouton action
3. **OAuth flows génériques** : module réutilisable pour Google et Microsoft (déjà partiellement présent, à refactoriser)
4. **Stockage sécurisé** : table `tenant_connectors` + chiffrement
5. **Interface utilisateur** : onboarding guidé quand un nouvel user rejoint, propose de connecter ses comptes en 3 clics

**Durée estimée** : 3-5 jours de dev (plusieurs sessions)

**Priorité** : moyenne-haute. Prérequis à l'onboarding de vrais utilisateurs au-delà de Guillaume.

---

## 🟡 Priorité 3 — Tests utilisateur bout-en-bout v2.x

**Contexte** : 13 commits pushés sur 22/04 (Sonnet défaut, pastille modèle, bouton Approfondir, continuation P2/P3, fix deepen, etc.) sans validation complète. Le dernier test validé fut le deepen sur la question Yomatec.

### Batterie de tests à dérouler

1. **Question simple** ("Bonjour Raya") → vérifier pastille Sonnet, vitesse
2. **Question métier moyenne** ("Point sur Coullet") → Sonnet répond avec règles RAG, bouton Approfondir visible
3. **Clic Approfondir** → Opus reprend le contexte complet (règles, historique, tools), pastille dorée sur la nouvelle bulle
4. **Question volontairement complexe** → atteint P1 → bouton Étendre
5. **Clic Étendre** → Opus reprend la boucle, pastille Opus
6. **Question piège** type "on a bien avancé aujourd'hui" → revalider le fix deepen (plus d'accusation d'hallucination)

**Durée estimée** : 15-30 min

**État** : non urgent (le fix principal a déjà été validé hier soir)

---

## 🟢 Priorité 4 — Nettoyage doublons règles

**Contexte** : \~20 doublons identifiés lors de l'audit du 22/04 matin (Simon Ducasse ×4, Consuel ×3, équipe ×3, etc.). Maintenant que le RAG sémantique fonctionne, l'impact négatif est atténué (retrieval top 10 par similarité au lieu de dump des 50 premières), mais la base reste plus propre avec nettoyage.

**Deux approches possibles** :

### Option A — En conversation avec Raya (naturel, 20 min)

Demander à Raya de lister ses règles sur un sujet donné, repérer les doublons, lui demander de fusionner ou archiver. Approche conversationnelle, cohérente avec la philosophie 100% conversationnelle.

### Option B — Via `/admin/rules/cleanup-ui` (batch, 10 min)

Passer un lot 3 ou 4 à l'endpoint d'archivage groupé qu'on a codé hier (commit `dd123c1`). Plus rapide mais moins éducatif.

**Recommandation** : Option A pour valider en même temps que le RAG retrouve les règles similaires par embedding.

---

## 🔵 Priorité 5 — Job nocturne rules_optimizer

**Contexte** : phase 4 de l'architecture règles v2 (conçue 22/04). Automatisation de la maintenance des règles :

- Auto-fusion des doublons par similarité cosine ≥ 0.95
- Auto-calibration des seuils par feedback utilisateur
- Décroissance automatique : -0.1 de confidence tous les 40j sans reinforcement
- Auto-normalisation des catégories
- Détection de contradictions → table `pending_rules_questions` avec question posée au premier message du lendemain

**Durée estimée** : 2-3h de dev + 1h de tests

**Prérequis** : audit multi-tenant fait (Priorité 1) pour garantir que le job nocturne respecte l'isolation.

---

## 🟣 Priorité 6 — Résilience & sécurité

Détaillé dans `docs/plan_resilience_et_securite.md` :

- **2FA** sur 6 services critiques (GitHub, Railway, Anthropic, OpenAI, Microsoft 365, Google) — 30 min
- **Backups auto nocturnes** (AWS S3 + Backblaze B2) avec chiffrement — 1h30 de config initiale
- **UptimeRobot** pour monitoring externe — 15 min

**Durée totale estimée** : 2h15

**Priorité** : haute mais pas urgente. À faire avant d'avoir un 2e utilisateur réel sur la plateforme.

---
