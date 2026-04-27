# À faire — Roadmap Raya

Document de suivi des chantiers ouverts. Mis à jour au fil de l'eau.

**Dernière MAJ** : 27 avril 2026 nuit.

---

## 💡 IDEE 27/04 nuit — Auto-detection des manques par Raya

**Intuition Guillaume** : quand Raya cherche une info et ne trouve rien
dans son graphe (ex: 'l'adresse de Coullet ?' → vide), pourrait-elle se
rendre compte du manque et proposer un re-scan cible pour combler le trou ?

**Faisabilite** : oui, totalement possible. Pas dangereux si :
- Raya **propose** le re-scan (jamais auto-execute)
- Demande confirmation explicite avant toute ecriture
- Periming limite a 1 record cible (pas de re-scan global)
- Pattern aligne sur les actions Odoo existantes

**Quand** : apres stabilisation du systeme actuel. Note ici pour ne pas
oublier l'idee.

**Effort estime** : 4-6h (detecter le manque + nouvel outil Raya
'request_data_refresh' + UI confirmation + connexion au scanner).

---

## 🚨 ANOMALIE DÉCOUVERTE 27/04 — Boucle de feedback 👍/👎 inactive

**Contexte** : audit pendant la session graphage des conversations.
Guillaume a cliqué 👍 sur la conv 407 → on a vérifié en DB.

**Constat** :
- 0 entrée dans `aria_response_metadata` pour les conv 405/406/407
  (pourtant créées juste avant)
- 0 feedback positif jamais enregistré dans toute la base

**Conséquence** :
- Quand Guillaume clique 👍, le code prévoit un renforcement des règles
  utilisées (+0.05 confiance) mais **rien ne se passe** car aucune métadonnée
  n'a été stockée → pas de règle à renforcer.
- L'apprentissage par feedback est totalement inactif depuis longtemps.

**Bugs probables (à investiguer)** :
1. **Bug A** : `save_response_metadata()` n'est plus appelé dans le mode
   agent V2 (raya_agent_core.py). Probable régression lors du passage
   de V1 (raya.py legacy) à V2 (raya_agent_core.py).
2. **Bug B** : à vérifier que le bouton 👍 dans l'UI déclenche bien
   l'appel HTTP `POST /raya/feedback`.

**Code concerné** :
- `app/feedback.py` (process_positive_feedback, save_response_metadata)
- `app/routes/raya.py:287` (endpoint /raya/feedback)
- `app/routes/raya_agent_core.py` (boucle V2 — manque l'appel à
  save_response_metadata)

**Effort estimé** : 1-2h (debug + fix + test)

**Priorité** : Élevée. Sans feedback, Raya n'apprend pas des préférences
de Guillaume. C'est l'une des fonctions clés du produit.

**À faire après l'étape 1 graphage en cours.**

### Mise à jour 27/04 fin journée — Fix 1 deploye, Fix 2 reste

**Fix 1 deploye** (commit f81f5f8) : `_raya_core_agent` appelle desormais
`save_response_metadata` apres chaque echange. Confirme en DB :
conv 408 a bien sa metadata (model=sonnet-4-6, via_rag=true,
10 rule_ids_injected). 

**Fix 2 (reste a faire)** : Bug B detecte au test du 👍 sur conv 408 :
- L UI affiche '👍✅' (vert) cote utilisateur
- MAIS feedback_type reste null en DB
- Les 6 regles concernees n ont pas vu leur confidence augmenter

Hypotheses a investiguer :
1. Le POST `/raya/feedback` n est pas envoye par chat-feedback.js
2. Le POST arrive au backend mais `process_positive_feedback` plante
   silencieusement (try/except sans log)
3. La verification du return body (`d.ok || d.status === 'ok'`) du JS
   evalue mal le retour `{status: 'ok', action: 'rules_reinforced'}`

**Effort : 30 min** (debug logs + verif endpoint + fix retour API).

---

## 🎨 ANOMALIE UI 27/04 — Badge "Sonnet" superpose au texte

**Contexte** : test feedback conv 408 (planning demain).

**Symptome** (screenshot fourni par Guillaume 21:37) : le badge "Sonnet"
qui indique le tier du modele utilise s affiche en haut a droite de la
bulle de reponse, MAIS il chevauche le texte de la 1ere ligne. Effet
brouillon visuel.

**Solution** : remonter le badge au niveau de l heure (lun. 27 avr. a
21:35) ou au-dessus du texte de la reponse, jamais superpose.

**Effort : 15-30 min** (CSS dans chat-messages.js ou raya_chat.html).

**Priorite : Moyenne** (cosmetique mais visible quotidien).

---

## 🔍 ANOMALIE Odoo 27/04 — of.planning.tour sans detail des lignes

**Contexte** : Guillaume a demande son planning du 28/04. Raya repond
qu elle voit bien la tournee #449 mais sans le detail des interventions
(clients, adresses, horaires). Le modele `of.planning.tour` n expose
pas ces lignes via l API.

**Cause probable** :
- Le manifest `of.planning.tour` n inclut pas les `tour_line_ids`
- OU le manifest existe mais cassait au scan (cf checklist priorite 8
  Odoo dans `roadmap_odoo_durable.md`)

**Effort : 1-2h** (verifier manifest, regenerer si manquant, tester).

**Priorite : Importante** (planning quotidien, fonctionnalite cle).

### Audit du 27/04 23h — Le refactor est en fait trivial

**Investigation** : comparaison ancien format `odoo-partner-3795` vs nouveau
format `odoo:res.partner:3795` dans semantic_graph_nodes.

**Constat** : sur 1 894 anciens noeuds, **1 881 sont des doublons** des
nouveaux noeuds. Seulement 13 orphelins (1%), dont 12 toujours actifs
dans odoo_semantic_content (anomalie scanner ponctuelle).

**Donc** : le scanner universel a bien re-vectorise toute la base. Les
anciens noeuds sont obsoletes.

**Plan refactor pour demain (~2h propres)** :
1. (15 min) Identifier les modules qui creent encore l'ancien format
   (probablement `app/jobs/odoo_vectorize.py` qui n'a pas ete migre)
2. (30 min) Desactiver ces modules ou les pointer vers le nouveau format
3. (30 min) Regenerer les 12 partners orphelins (re-scan cible)
4. (15 min) Supprimer les 1881 anciens noeuds + 2508 edges associes
   (transaction unique)
5. (15 min) Mettre a jour `_enrich_with_graph` :
   - Format des cles : `odoo:res.partner:%s` au lieu de `odoo-partner-%s`
   - Ajouter Tour, TourStop, Task (manquants -> bug 3 planning)
6. (30 min) Tests prod

**A ce moment-la, le bug 3 (planning sans detail) est resolu** car
of.planning.tour ET of.planning.tour.line auront un mapping correct.

---

## 🆕 Récap des chantiers TERMINÉS cette semaine (22-26 avril)

### Page /settings — 6 phases déployées en prod

- Phase 1-6 : route /settings + 5 onglets (Profil, Conso, Règles, Connexions, Données)
- Mes règles : refonte UX complète (chip "À revoir" intelligente, regroupement Divers, sessions 5/5)
- Catégories : 2 vagues de migration (37 → 17 catégories canoniques, 0 doublon casse/slug)
- Validateur Sonnet sur \[ACTION:LEARN\] (be2f0b0)
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
- API `Modal.open/close/onOpen/onClose` + comportements universels (Escape, clic-fond, scroll lock, focus trap)
- 5 modales user migrées : requestModal, passwordModal, deleteAccountModal (tone-danger), modalShortcutEdit, reviewSessionModal (size-parcours)
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

✅ **TERMINÉ : insertion d'image en local (upload + redim + compression auto)** — *fait le 25/04 soir*

- **Approche choisie** : base64 inline (pas stockage serveur fichier) → pas de problème CDN, signature auto-portable, marche partout (Gmail, Outlook, Apple Mail)
- **Compression auto** : canvas + boucle qualité/taille dégressive, tient sous 100 KB peu importe la photo source (testé : photo 1920x1080 → JPEG 800x450 q=92 → \~19 KB)
- **GIF** : préservés tels quels (sinon perte d'animation), limite stricte 100 KB en entrée
- **PNG transparent** : transparence préservée tant que possible
- **Redimensionnement à la souris (presets)** : popup au clic sur l'image avec 4 presets Petite/Moyenne/Grande/Personnalisée + slider 40-500px
- **Commits** : `eacf292` (file picker) + `ea48ce9` (compression) + `4bce014` (popup redim)

🟢 **PRIORITÉ HAUTE : éditeur de mail enrichi avec apprentissage par diff** — *vision Guillaume 25/04 soir*

> Ce n'est pas une amélioration cosmétique mais une **fonctionnalité majeure** qui transforme la façon dont Raya rédige les mails. À traiter dès qu'on aura un peu de bande passante.

**Le contexte** : aujourd'hui, quand Raya rédige un mail, elle propose un texte dans le chat et l'envoie tel quel via Gmail/Outlook. Si l'utilisateur n'aime pas, il dit "modifie-le, mets X au lieu de Y, ajoute des puces…" — c'est lent, l'utilisateur doit verbaliser ses corrections, et Raya ne capitalise pas vraiment.

**La vision** :

1. **Vrai éditeur WYSIWYG** dans l'interface chat (pas juste du texte brut). Quand Raya prépare un mail, l'utilisateur peut :

   - Modifier directement le texte (typing en place)
   - Ajouter du gras / italique / souligné
   - Insérer des puces ou listes numérotées
   - Insérer des emojis (réutiliser le picker `_SIG_EMOJI_CATEGORIES` qu'on a fait pour les signatures)
   - Mettre des couleurs si pertinent
   - Insérer des images (réutiliser tout l'upload + compression + redim qu'on a fait pour les signatures)

2. **Apprentissage par diff à la validation** :

   - Au moment où l'utilisateur clique "Envoyer" (après ses modifications), Raya capture les **2 versions** :
     - V1 = ce que Raya avait initialement rédigé
     - V2 = ce que l'utilisateur a effectivement envoyé
   - Calcule la **diff** (texte + structure : ajout/retrait de puces, changement de ton, mots remplacés, formules de politesse modifiées…)
   - Génère une **règle** dans le système de règles existant (pas de nouvelle infrastructure) :
     - Ex : "Pour les mails à des clients, préférer 'Cordialement' à 'Bien à vous'"
     - Ex : "L'utilisateur préfère des phrases courtes en bullet points pour les récap de réunion"
     - Ex : "Quand le mail est court (&lt; 5 phrases), pas de formule de politesse longue"
   - Soumet la règle au validateur Sonnet (déjà en place via `rule_validator.py`) pour vérifier la pertinence avant de l'enregistrer

3. **Brouillon meilleur la fois suivante** :

   - Les règles tirées des diffs précédentes sont injectées dans le prompt système au moment où Raya rédige un nouveau mail dans le même contexte (mêmes destinataires, mêmes catégories de sujet)
   - Au fil du temps, Raya devient de plus en plus alignée sur le style de l'utilisateur

**Architecture estimée** :

- **Frontend** (\~3-4h) : composant éditeur WYSIWYG dans `chat-messages.js`, réutilise les fonctions signatures (toolbar, emoji picker, image upload). Bouton "Modifier" qui transforme le brouillon Raya en zone éditable.
- **Backend diff** (\~2-3h) : endpoint `POST /mails/log-diff` qui reçoit V1 et V2, calcule la diff (lib `difflib` Python ou équivalent), envoie au LLM (Haiku) pour transformer la diff en règle candidate, soumet au validateur Sonnet existant.
- **Branchement règles** (\~1h) : ajouter une catégorie de règles `email_drafting_style` au système de catégories canoniques. Inclure ces règles dans le prompt de rédaction de mail au runtime.

**Estimation totale** : 6-8h sur une session dédiée. Mérite sa propre session bien préparée.

**Pré-requis** :

- Nouveau composant éditeur WYSIWYG (mais on peut largement copier-coller depuis l'éditeur signatures)
- Logique de diff (lib standard Python)
- Pas d'infra nouvelle DB (on réutilise la table `rules` existante)

**Priorité** : Haute, mais pas urgent. À traiter après l'audit isolation multi-tenant (priorité 1 actuelle) et la connexion simplifiée des outils tiers (priorité 2). Ce sera **probablement la fonctionnalité phare de la v3**.

---

🔵 **AMÉLIORATION : prévisualisation "comme dans un vrai mail"**

- Aujourd'hui la preview dans la card est un aperçu compact (max 60px de haut).
- Idée : un bouton "Aperçu" qui ouvre une mini-modale montrant la signature dans un faux mail (sujet + corps + signature) pour voir le rendu réel.
- **Estimation** : \~30 min.

🔵 **AMÉLIORATION : mécanisme "Raya demande puis apprend"** (REPORTÉ depuis le MVP)

- Si plusieurs signatures matchent une boîte sans défaut → Raya demande à l'utilisateur, retient le choix comme règle pour la prochaine fois
- Décision Guillaume 25/04 : reporté à une session future, le mécanisme "tu définis toi-même la défaut depuis /settings" suffit pour le MVP
- **Estimation** : \~1h (interrompre le flow d'envoi, dialogue avec choix multiples, update `default_for_emails` côté backend après choix utilisateur)

---

## 🎯 Vision & architecture d'isolation

### Modèle d'isolation multi-tenant (clarifié 24/04)

**Un tenant = une société cliente de Raya**.Le dirigeant de la société souscrit à Raya pour son équipe.

#### Niveau tenant (société) — Isolation COMPLÈTE

Aucune fuite de données entre sociétés. Tenant A ne voit jamais les données du tenant B, et réciproquement. Respecté actuellement via `tenant_id NOT NULL` sur toutes les tables critiques.

#### Niveau utilisateur dans un tenant — Isolation QUASI-COMPLÈTE (phase actuelle)

**Décision Guillaume 24/04 matin** : on ne mutualise PAS les règles apprises entre utilisateurs d'un même tenant pour l'instant. Risque trop élevé de conflits d'un utilisateur à l'autre.

**Privé par utilisateur** :

- ❌ **Règles apprises** : privées à chaque utilisateur. Les préférences, raccourcis, conventions de Guillaume ne polluent pas celles de Pierre/Sabrina. Chacun construit sa propre base.
- ❌ **Conversations personnelles** : privées.
- ❌ **Mails consultés** : chaque utilisateur accède à SA boîte Outlook/Gmail uniquement.

**Partagé par tenant (seul point commun aujourd'hui)** :

- ✅ **Données métier externes** (Odoo, SharePoint, Drive commun) accessibles à tous les utilisateurs du tenant selon leur périmètre autorisé. C'est ce qui permet aux analyses croisées métier.

#### Évolution future — Promotion de règles tenant (pas maintenant)

Quand l'architecture aura mûri, identifier dans les règles personnelles celles qui sont **génériques à la société** vs celles **spécifiques à l'utilisateur** :

- Règles spécifiques (ex. "Guillaume préfère signer ses mails 'Perrin G.'") → restent dans `aria_rules`, filtrées par `username`.
- Règles société (ex. "Chez Couffrant, RFAC veut dire Règlement de Facture") → promues dans une 2ème base partagée (ex. `tenant_rules`ou `aria_rules_tenant`), visibles de tous les utilisateurs du tenant.

**Mécanisme de promotion** : NON-AUTOMATIQUE. La détection (heuristique ou validation admin) doit passer par une confirmation consciente, probablement via le dirigeant du tenant dans un panel admin. Jamais d'auto-promotion silencieuse pour éviter la pollution involontaire.

À traiter plus tard, quand l'architecture sera stable et qu'on aura plusieurs utilisateurs par tenant en usage réel.

---

## 🔴 Priorité 1 — Audit isolation multi-tenant et utilisateur

> ✅ **AUDIT FAIT** le 25/04 soir. Voir `docs/audit_isolation_25avril_complementaire.md` (758 lignes). Bilan : 8 trous CRITIQUES, 15 IMPORTANT, 10 ATTENTION identifiés. Checklist permanente créée : `docs/checklist_isolation_multitenant.md`.
>
> ✅ **DÉCISION TRANCHÉE** le 26/04 : modèle SaaS avec quota par tenant. couffrant_solar=5 seats, juillet=1 seat. Q1-Q4 = tenant_admin, Q5 = super_admin only (jusqu'à facturation tokens).
>
> ✅ **ÉTAPE 0 DÉPLOYÉE** le 26/04 (commit `e937dca`) : 6 migrations DB (max_users, tenant_id NOT NULL, fix default scope).
>
> ✅ **ÉTAPE A DÉPLOYÉE** le 26/04 (commits `2bdddb0` + `0f333da`) :
>
> - A.1 : isolation tokens OAuth (token_manager.py + 3 migrations oauth_tokens)
> - A.2 : logs explicites get_tenant_id (au lieu de fallback silencieux)
> - A.3 : POST/DELETE /admin/tenants → require_super_admin
> - A.4 : admin_update_user durci contre privilege escalation
>
> 🚧 **À FAIRE** : Étape B (seat counter + UI quota), C (15 IMPORTANT + 10 ATTENTION), D (tests bout en bout via plan_tests_isolation_pierre_test.md).

**Contexte** : avant d'onboarder Pierre, Sabrina, Benoît ou un 2e tenant, vérifier que le modèle d'isolation décrit ci-dessus est bien respecté partout dans le code.

### Sous-chantier 1.1 — Isolation tenant (société vs société)

Tous les SELECT sur les tables sensibles doivent filtrer sur `tenant_id`en plus de `username` quand pertinent.

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

Ce sous-chantier est NOUVEAU et distinct du 1.1. Il faut vérifier que toutes les tables sensibles filtrent à la fois sur `tenant_id` ET sur `username` :

**Privé par utilisateur** (filtrer sur `username`) :

- `aria_rules` (règles apprises) : chaque user a sa propre base de règles, pas de partage entre users du même tenant. **Attention : c'est un changement par rapport à ce qui avait été supposé initialement.** Corriger si du code existant partage les règles au niveau tenant.
- `aria_memory` (conversations) : privées à chaque user
- `mail_memory` (mails indexés) : chaque user a sa boîte
- `aria_insights` : à vérifier selon leur nature
- Préférences, historique graphe, etc.

**Partagé par tenant** (filtrer uniquement sur `tenant_id`) :

- Accès aux données métier externes : Odoo, SharePoint, Drive commun (la permission est gérée côté source, pas côté Raya)
- Connecteurs OAuth de niveau tenant : Odoo API key, Anthropic API key si BYO, etc.

### Tests de non-régression à faire ensuite

Créer un 2e user fictif dans le tenant `couffrant_solar` (ex. `pierre_test`), puis vérifier :

1. Pierre NE voit PAS les règles de Guillaume ❌ (nouveau : isolation utilisateur)
2. Pierre NE voit PAS les conversations privées de Guillaume ❌
3. Pierre NE voit PAS les mails de Guillaume ❌
4. Pierre ET Guillaume voient tous deux les données Odoo Couffrant (accès partagé métier) ✅
5. Une règle apprise par Pierre n'affecte PAS les réponses de Guillaume ❌

Puis tester l'isolation tenant :

- `charlotte_agency` / `charlotte` ne doit voir QUE ses 10 règles, jamais celles de couffrant_solar.

**Durée estimée** : 60-90 min (audit + 4-6 fichiers à corriger + tests)

---

## 🟠 Priorité 2 — Connexion simplifiée des outils tiers (panel admin tenant)

**Contexte** : aujourd'hui brancher une boîte Outlook/Gmail ou un compte Drive demande des manipulations techniques (OAuth dans la console Azure, configuration Railway, etc.). C'est acceptable pour Guillaume mais impossible à déléguer à Pierre, Sabrina ou un nouveau tenant.

### Objectif

Le panel admin d'un tenant doit proposer un **catalogue de connecteurs**avec, pour chacun, un bouton **"Connecter"** qui :

1. Ouvre une pop-up OAuth/API key
2. Guide l'utilisateur étape par étape (ex. Gmail : authentifier, autoriser, c'est fini)
3. Stocke automatiquement les tokens en DB avec le bon `tenant_id` + `username`
4. Valide la connexion (test GET) et affiche ✅ Connecté
5. Permet de déconnecter / reconnecter facilement

### Connecteurs prioritaires à ouvrir (par ordre d'impact)

#ServiceModeEffort1**Gmail** (OAuth)Semi-auto via Google OAuth flowMoyen2**Outlook / Microsoft 365** (OAuth)Déjà en place pour Guillaume, à généraliserFaible3**Google Drive** (OAuth)Même flow que GmailFaible (une fois #1 fait)4**OneDrive / SharePoint** (OAuth)Même que OutlookFaible5**Odoo OpenFire** (API key)Déjà en place, à encapsuler dans l'UIFaible6**Anthropic API key** (si BYO)Saisie manuelle simpleTrès faible7**Calendrier Google/Outlook** (OAuth)Intégré à #1 et #2Très faible

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
- Détection de contradictions → table `pending_rules_questions` avec question posée au premier message du lendemain **Durée estimée** : 2-3h de dev + 1h de tests **Prérequis** : audit multi-tenant fait (Priorité 1) pour garantir que le job nocturne respecte l'isolation.

---

## 🟣 Priorité 6 — Résilience & sécurité

Détaillé dans `docs/plan_resilience_et_securite.md` :

- **2FA** sur 6 services critiques (GitHub, Railway, Anthropic, OpenAI, Microsoft 365, Google) — 30 min
- **Backups auto nocturnes** (AWS S3 + Backblaze B2) avec chiffrement — 1h30 de config initiale
- **UptimeRobot** pour monitoring externe — 15 min

**Durée totale estimée** : 2h15

**Priorité** : haute mais pas urgente. À faire avant d'avoir un 2e utilisateur réel sur la plateforme.

---

## 🟣 Priorité 7 — Résilience pool de connexions DB (suite incident 25-26/04)

**Contexte** : un incident de saturation du pool DB a été diagnostiqué et fixé le 26/04 matin (cf. `docs/incident_pool_db_26avril.md`). Les fixes immédiats sont déployés (cast `created_at::timestamp` dans `proactivity_scan.py` + rollback défensif dans `_PooledConn.close()`).

3 actions de suivi restent à programmer pour aller au bout :

### 7.1 — 🟠 Migration progressive des 152 patterns dangereux

152 endroits dans le codebase utilisent `conn = get_pg_conn()` sans `with` block. Grâce au garde-fou rollback ajouté dans `_PooledConn`, ils ne sont plus des bombes à retardement, mais ils restent perfectibles. À convertir progressivement vers `with get_pg_conn() as conn:` au fil des sessions qui touchent aux fichiers concernés.

**Estimation** : 5-10 min par fichier × \~30 fichiers principaux = 3-5h réparties sur plusieurs sessions.

### 7.2 — 🟠 Monitoring proactif du pool

Ajouter dans `app/jobs/system_monitor.py` une vérification toutes les 10 min du nombre de connexions en état `idle in transaction (aborted)`. Au-dessus d'un seuil, créer une alerte dans `system_alerts`. Permet de détecter le problème **avant** que le pool soit saturé.

**Estimation** : 30-45 min de dev + tests.

### 7.3 — 🟡 Migration `mail_memory.created_at` en vrai timestamp

La cause profonde du bug est que `created_at` est en type `text`. Le cast `::timestamp` qu'on a ajouté est un contournement. Migrer la colonne en `TIMESTAMP` propre (et auditer les autres tables dans le même cas).

**Estimation** : 1-2h selon le nombre de tables concernées. **Précaution** : à faire APRÈS un backup propre (cf. Priorité 6).

**Priorité globale** : modérée. Le système est stable depuis le fix. À traiter en arrière-plan dans les semaines à venir, pas un blocant pour l'audit isolation ni l'onboarding de nouveaux utilisateurs.

---

## 🟠 Priorité 8 — Connexion Odoo durable (en attente OpenFire)

**Statut** : 🚧 **BLOQUÉ par retour OpenFire**, semaine du 26/04/2026.

### Contexte

Aujourd'hui Raya synchronise Odoo via un polling toutes les 2 min sur 11 modèles (`sale.order`, `crm.lead`, `of.planning.tour`, etc.). C'est un palliatif en attendant qu'OpenFire livre le module custom de webhooks temps-réel (cf. `docs/demande_openfire_webhooks_temps_reel.md`).

### En attente du retour d'OpenFire

- État du module webhooks temps-réel custom (livraison ? planning ?)
- Liste des champs/modèles qu'on n'arrivait pas à récupérer

### 3 manifests cassés à régénérer après retour OpenFire

Tous bloqués par le même bug : le manifest interroge le champ `name` qui n'existe pas sur le modèle Odoo cible (boucle d'erreur `Invalid field 'name' on model X`).

- `of.survey.answers` — désactivé le 20/04
- `of.survey.user_input.line` — désactivé le 20/04
- `mail.activity` — désactivé le 26/04 (commit `a6b33f8`)

Fix propre : régénérer les manifests en utilisant `display_name` ou `summary` au lieu de `name`.

### À faire dès qu'on a le retour OpenFire

1. Ouvrir un doc dédié `docs/roadmap_odoo_durable.md` qui :
   - Cartographie l'existant (12 modèles polled, archi tenant_id-aware)
   - Anticipe le multi-tenant Odoo (un Odoo par tenant)
   - Anticipe la migration polling → webhooks OpenFire
   - Liste les champs/modèles à enrichir
2. Régénérer les 3 manifests cassés
3. Si webhooks OpenFire dispo : prévoir le switchover sans coupure
4. Décider si dashboard santé Odoo dans le panel admin (ou logs only)

**Estimation** : impossible tant qu'on n'a pas le retour OpenFire.

---
