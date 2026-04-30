# À faire — Roadmap Raya

---

## ✅ État chantier 2FA — 30/04/2026

**Sécurité Niveau 2 100% en prod** depuis le 30/04. Détails dans [`docs/chantier_2fa_recap.md`](chantier_2fa_recap.md).

| LOT | Statut | Commit |
|---|---|---|
| 0 — Migrations DB + auth_events | ✅ | `774ddb2` |
| 1 — Module totp.py | ✅ | `c60f093` |
| 2 — Endpoints setup 2FA | ✅ | `ec3a4b4` |
| 3 — Login flow 2 étapes (challenge) | ✅ | `90acaec` + `ba546dd` |
| 4 — Device trusted 30j + GeoLite2 | ✅ | `c3d13d6` |
| 5 — PIN admin 4-6 chiffres | ✅ | `4c31473` |
| 6 — Reset par super_admin | ✅ | `435dd55` |
| 7 — Tests + doc | ✅ | (en cours) |
| 8 — WebAuthn / Face ID / Touch ID | 💡 reporté | 10-15h |
| 5b — 2FA pour actions critiques | ⏭️ futur | 1h |

**Stack actuelle** :
- Login chat : password seul (zero changement)
- Login admin : password + 2FA Authenticator (validée 30j par device) + PIN 4-6 chiffres (à chaque entrée)
- Codes recovery uniquement pour super_admin (Charlotte/users → contactent super_admin si problème)
- Filet d'urgence : `DISABLE_2FA_ENFORCEMENT=true` sur Railway

**Prochaines actions** :
- Charlotte doit activer sa 2FA avant le 7 mai 2026 (grace period 7j reset le 30/04)
- LOT 5b à faire avant les premières utilisations massives (1h)

---



Document de suivi des chantiers ouverts. Mis à jour au fil de l'eau.

**Dernière MAJ** : 28 avril 2026 fin de soirée — note ici les 3 chantiers urgents identifiés en fin de session 28/04 soir avant déploiement version d'essai.

> **📌 Doc d'état le plus à jour** : voir `docs/etat_28avril_midi.md` pour la vue synthétique des chantiers TERMINÉS / EN COURS / À FAIRE après la session 28/04 matin.

---

## 🚨 CHANTIERS URGENTS — avant déploiement version d'essai (identifiés 28/04 soir)

> **Contexte** : Guillaume veut déployer une version d'essai d'ici quelques jours
> à Charlotte (déjà créée, tenant `juillet`) + 2-3 personnes supplémentaires.
> Verdict audit fait le 28/04 soir : 3 chantiers bloquants à traiter avant.

### 🏗️ Modèle commercial — Forfait sur mesure par tenant

**Vision Guillaume (28/04 soir)** : pas d'UI self-service côté tenant pour
connecter ses outils. Le **super_admin** onboarde chaque tenant individuellement :

1. Échange initial avec le nouveau client : quels outils il a (Gmail, Outlook,
   Drive, Vesta, SolarEdge, etc.)
2. Construction d'un **forfait sur mesure** en fonction de ces besoins
3. Le super_admin connecte lui-même les outils via le panel admin
4. Création des users du tenant — **aucun user n'est créé sans au moins
   une connexion attribuée**

**Implications techniques** :

- Le chantier "UI simplifiée connexion outils tiers (panel admin tenant)"
  qui était noté en P2 n'est PAS nécessaire dans ce modèle. Le super_admin
  reste le seul à connecter via le panel super_admin existant. À déprécier
  dans la roadmap.
- En revanche, un **système de forfaits par tenant** sera nécessaire à terme
  (table `tenant_plans`, limites par plan, UI super_admin pour assigner) —
  pas urgent tant qu'on est en mode "essai gratuit", mais à concevoir avant
  de basculer en payant.
- Le panel super_admin actuel doit rester **fluide pour onboarder** un
  nouveau tenant rapidement (création tenant + users + connexions en
  quelques clics). Voir si nettoyage UX du panel admin (cf. notes UX 28/04
  point 3) facilite cet onboarding.

**Pas un chantier urgent en soi**, mais clarification du modèle qui
recadre certains autres chantiers. À noter pour la cohérence future.

### ✅ Audit isolation user↔user intra-tenant — TERMINÉ 28/04

> **STATUT** : ✅ TERMINÉ et validé en prod le 28/04 fin de soirée.
> Détails dans `docs/audit_isolation_user_user_phase3_tests.md`.
>
> | Phase | Statut |
> |---|---|
> | Phase 1 — Cartographie 53 tables | ✅ |
> | Phase 2 — Audit code 10 findings | ✅ |
> | LOT 1 — 8 fixes structurels | ✅ commit `d7f1e7d` |
> | LOT 2 — 4 migrations UNIQUE | ✅ commit `96b4c48` |
> | LOT 3 — Tests pierre_test | ✅ |
> | LOT 4 — Décisions design | ✅ commit `1b429e8` |
>
> **Raya est prête à accueillir Pierre, Sabrina, Benoît dans `couffrant_solar`
> sans risque d'isolation user↔user.**

**Contexte historique** : l'audit isolation 25/04 (33 findings tous traités) s'est
focalisé sur l'isolation **tenant↔tenant** (couffrant_solar vs juillet).
Excellent travail. Mais l'isolation **user↔user dans un même tenant**
(Guillaume vs Pierre vs Sabrina dans couffrant_solar) n'avait pas eu
d'audit dédié — fait depuis le 28/04.

**Pourquoi c'est urgent** : avant de déployer Pierre/Sabrina/Benoît dans
le tenant couffrant_solar (ou de créer un 2e user dans le tenant juillet
plus tard), il FAUT s'assurer que :

- Les règles apprises par Guillaume ne polluent pas les réponses à Pierre
- Pierre ne voit pas les conversations privées de Guillaume
- Pierre ne voit pas les mails de Guillaume (sa boîte Outlook/Gmail)
- Le feedback 👍/👎 de Pierre n'affecte pas les règles de Guillaume
- Etc.

**Décision Guillaume 24/04** déjà prise : pas de mutualisation des
règles/conversations/mails entre users d'un même tenant. Reste à valider
en code que cette décision est bien implémentée partout.

**Plan d'audit en 4 phases** :

- **Phase 1 — Cartographie** (~1h) : lister toutes les tables sensibles,
  classer "filtrage sur username obligatoire" vs "partagé tenant" vs
  "ambigu, à décider". Identifier les fichiers Python qui touchent à ces
  tables.
- **Phase 2 — Audit code** (~2-3h) : passer en revue les 10-15 fichiers
  les plus critiques. Pour chaque SELECT/INSERT/UPDATE qui touche les
  tables "username obligatoire", vérifier que le filtre est bien posé.
  Documenter chaque finding (CRITIQUE / IMPORTANT / ATTENTION) comme
  pour l'audit du 25/04.
- **Phase 3 — Remédiation** (~1-3h selon findings) : fixer les trous
  trouvés en LOTs commitables séparément.
- **Phase 4 — Tests bout-en-bout `pierre_test`** (~1h) : créer un user
  fictif Pierre dans couffrant_solar, simuler des actions, vérifier
  qu'il ne voit pas les données de Guillaume. Plan déjà rédigé dans
  `docs/plan_tests_isolation_pierre_test.md`.

**Estimation totale** : 5-8h, étalé sur 1-2 sessions dédiées.

**Démarrage** : Phase 1 lancée le 28/04 fin de soirée. Phases 2-4 dans
les jours qui viennent.

### 🛡️ Plan résilience & sécurité — PROMOTION en priorité haute

**Existait déjà en Priorité 6** mais devient maintenant priorité 1 avant
tout déploiement version d'essai.

**Détaillé dans** `docs/plan_resilience_et_securite.md`.

3 actions :
- 2FA sur 6 services critiques (GitHub, Railway, Anthropic, OpenAI,
  Microsoft 365, Google) — 30 min
- Backups auto nocturnes (AWS S3 + Backblaze B2) avec chiffrement —
  1h30
- UptimeRobot pour monitoring externe — 15 min

**Estimation totale** : 2h15.

**Pourquoi maintenant** : si la DB Railway plante avant que Charlotte ou
les versions d'essai aient été backupées, on perd irrémédiablement leurs
conversations + règles + mémoires. Coût d'un soir de panne = mois de
travail utilisateur perdu.

### 📋 Récap des bloquants avant déploiement version d'essai

| Bloquant | Effort | Statut | Note |
|---|---|---|---|
| Audit isolation user↔user intra-tenant | 5-8h | ✅ TERMINÉ 28/04 | Phase 1+2+3+LOTs 1-4 OK |
| 2FA Raya app (LOT 0-7 + 5b) | ~12h | ✅ TERMINÉ 29-30/04 | Niveau 2+3 complet |
| Restriction tenant_admin sur connexions | 30 min | ✅ TERMINÉ 30/04 | LOT B commit `ac5f8fd` |
| 2FA externes (GitHub, Railway, Anthropic, OpenAI, M365, Google) | 30 min | 🔴 À faire | Hors app Raya |
| Backups auto nocturnes externes | 1h30 | 🟡 À vérifier | Plan défini, vérifier statut |
| UptimeRobot monitoring | 15 min | 🔴 À faire | |
| Système feature flags par tenant | ~2h Phase 1 | 🔴 À faire | Vrai bloquant business |
| Note UX #7 (retirer "Administration" menu user) | 2-3h | 🔴 À faire | Cf. section UX 28/04 soir |
| Outlook contact@couffrant-solar.fr | 15 min | 🟡 Attente codes Azure | |

**Total estimé** : 10-14h sur 2-3 sessions dédiées dans les jours qui
viennent. Faisable d'ici fin de semaine.

---

## 🏠 CHANTIER (validé 28/04 après-midi) — Page d'accueil dynamique

> **Vitrine quotidienne de Raya, personnalisable par chaque utilisateur.** Affichée à la 1ère connexion de chaque journée. Brief précis ci-dessous, prêt à être implémenté.

### Objectif
Quand un utilisateur revient sur Raya pour la 1ère fois d'une journée, au lieu de tomber directement sur la dernière réponse de la conversation continue, il voit une **page d'accueil** soignée qui le salue, donne le contexte du jour (heure, météo, planning léger, résumé de la veille) et l'invite à commencer.

### Comportement attendu

1. **Détection** : `users.last_login_date != aujourd'hui` → on affiche la page. Sinon on garde le scroll classique.
2. **Affichage** : overlay pleine page **par-dessus** la conversation. L'historique est au-dessus, hors cadre, scrollable.
3. **Coupure visuelle datée** : entre la page d'accueil et l'historique, un séparateur avec la date du jour. Permet de retrouver facilement "ce qu'on faisait il y a 3 jours".
4. **Disparition** : dès que l'utilisateur tape un message, l'overlay se ferme et le chat reprend normalement.
5. **Rappel** : bouton 🏠 dans la barre d'en-tête + commande naturelle ("rebonjour", "affiche-moi l'accueil"). La page n'est jamais stockée dans `aria_memory`.

### Blocs par défaut au lancement

- ☀️ **Salutation** : "Bonjour [prénom]" + date complète + heure + ville + **icône météo dynamique** (soleil/nuageux/pluie/neige)
- 📅 **Planning léger** : 3-5 lignes max sur ce qui est prévu aujourd'hui (rendez-vous filtrés par `of_employees_names` cf. règle 230 pour Guillaume)
- 📝 **Résumé conversation précédente** : "La dernière fois, on a travaillé sur X et Y. Tu en étais à..."
- 💡 **Suggestion proactive** (optionnel) : 1 alerte ou 1 idée du jour (lien avec `proactive_alerts` existant)

### Personnalisation

- Accessible via **Settings → Page d'accueil**
- Ouvre une fenêtre de configuration avec **aperçu en direct** + **éditeur conversationnel** avec Raya
- L'utilisateur peut **activer/désactiver** des blocs, en **ajouter** depuis un catalogue, **réorganiser** l'ordre
- Validation → ferme la fenêtre, applique les changements
- Chaque utilisateur a sa propre config (table `homepage_config`)

### Architecture technique

- Nouvelle table `homepage_config(username, tenant_id, blocks_json, updated_at)` — un user, une config
- API météo : OpenWeatherMap gratuit (60 req/min suffit largement) ou équivalent
- Catalogue de blocs initialement codé en dur (10-12 blocs), extensible plus tard
- Frontend : nouveau composant overlay HTML inline dans le chat, animé en CSS pure
- Detection 1ère connexion : query simple sur `users.last_login_date` au load de la page

### Animation visuelle (cf. mockup `docs/mockups/homepage_animations_A_B_C.html`)

- **Choix retenu : Option A** — gradient animé + particules CSS + fadeUp + typo soignée
- Léger (~1 KB), 0 dépendance, modifiable facilement
- **Évolution future possible** : Option C (personnage Raya animé Lottie) si la feature s'avère stratégique pour l'identité produit. Coût : 2-3j de design + intégration. À évaluer après usage réel.

### Étapes proposées

1. **Backend** (3-4h) : table `homepage_config`, endpoint GET/POST `/homepage/config`, query météo, query `last_login_date`
2. **Composant accueil** (3-4h) : overlay HTML/CSS animé, 4 blocs par défaut codés
3. **Détection 1ère connexion** (1-2h) : trigger au load + bouton 🏠 + commande naturelle
4. **Panneau Settings** (3-4h) : modal de personnalisation avec aperçu + éditeur conversationnel
5. **Tests + finition** (2h)

**Estimation totale** : ~12-15h sur une session dédiée (1 journée complète).

### Liens

- Mockup visuel : `docs/mockups/homepage_animations_A_B_C.html`
- Lié à : `onboarding_decouverte_outils.md` (pour la suggestion proactive)
- Lié à : règle 230 `aria_rules` (filtre planning par employee — pour le bloc planning)

---

## 🎨 NOTES UX 28/04 soir — Panel super admin + finitions connecteurs

Notes remontées par Guillaume pendant l'onboarding de 4 nouvelles boîtes
Gmail (SCI Romagui, SCI Gaucherie, SCI MTBR, SAS GPLH) + tentative
Outlook contact@couffrant-solar.fr le 28/04 19h.

Le panel admin actuel est dense, hérité de la phase test/dev. Plusieurs
boutons et flux pourraient être simplifiés maintenant que le produit
arrive à maturité.

### 1. Rester sur la page après validation d'une connexion

**Symptôme** : quand Guillaume clique "✉️ Connecter Gmail" sur une ligne
de connexion, il fait l'OAuth Google, et au retour sur Raya il atterrit
sur le menu principal de l'admin (vue "sociétés"). Il doit re-cliquer sur
"Couffrant Solar" pour revenir à la page connexions et continuer ses
assignations.

**Attendu** : retour direct sur la page société avec la connexion
mise en évidence (scroll auto + flash visuel).

**Fichier impliqué** : probablement la route de callback OAuth
(`/admin/connections/{tenant_id}/oauth/{provider}/callback`) qui redirige
vers `/admin/panel` sans paramètre de retour. Idée : passer un
`?return_to=companies&tenant_id=X&conn_id=Y` au moment du start, le
récupérer au callback, rediriger vers la bonne vue.

**Estimation** : 30 min.

### 2. Boutons inutiles à épurer dans le panel

Plusieurs boutons sont des reliques de la phase test/dev qui ne servent
plus en usage normal :

- **"🔍 Découvrir"** sur les lignes Gmail/Microsoft : appelle
  `/admin/discover/{tenant_id}/gmail` qui retourne `error: Type 'gmail'
  non supporté`. À transformer en "📥 Backfill" quand on aura la
  Phase B des connecteurs (vectorisation historique mode lite).
- **"🔍 Découverte des connecteurs"** dans le menu Setup d'Odoo : peuple
  l'ancienne table `entity_links` (legacy pré-V2). Sert "une fois à la
  mise en place" puis devient inutile. Probablement à retirer.
- **Onglet "Découvrir"** général dans la barre supérieure si présent.

**Action** : audit rapide à faire et purge sans pitié des boutons morts.
**Estimation** : 1-2h.

### 3. Panel super admin trop chargé

Le panel a accumulé des onglets et sections au fil des chantiers. Vu
d'ensemble : **Mémoire / Utilisateurs / Règles / Insights / Actions /
Sociétés / Profil + barre d'alertes système + Connexions par société
(elle-même dense)**.

**Idée** : faire un audit UX du panel, regrouper les sections proches,
enlever les vues qui ne servent plus à l'usage quotidien (cartographies
type Profil sont accessibles via /settings côté user).

**Estimation** : 4-6h de design + intégration. À traiter dans une session
dédiée "refonte panel admin".

### 4. ✅ Bug bouton "Connecter Microsoft" pour tool_type=outlook — FIX 28/04 soir

**Symptôme** : Guillaume crée la connexion "Contact Couffrant Solar" en
choisissant le type `outlook`. Sur la ligne, **aucun bouton** n'apparaît
pour lancer l'OAuth Microsoft.

**Cause** : dans `app/static/admin-panel.js`, la condition de rendu du
bouton OAuth était strictement `c.tool_type === 'microsoft'` alors que
le backend (mailbox_manager.py) traite déjà `microsoft` et `outlook`
comme synonymes (mêmes credentials Graph, même MicrosoftConnector).

**Fix** : étendre les conditions à `microsoft || outlook` aux 5
endroits du JS :
- Groupage `mail` dans le résumé d'entête
- Bouton "🔵 Connecter Microsoft" (status non-connecté)
- Bouton "🔄 Reconnecter" (status connecté)
- Bouton "🔍 Découvrir" (cosmétique, en attendant fix #2)
- `renderMicrosoftActions(tenantId, connId)`

**Statut** : ✅ Fixé en local, push prévu dans le commit Phase A finition.

### 5. Filtrer le job `webhook_night_patrol` par deactivated_models

**Symptôme** : alerte récurrente chaque nuit "Ronde de nuit : 80 records
manquants détectés, 80 rattrapages enqueues" qui revient en warning
malgré qu'elle soit fausse.

**Diagnostic** : décomposition des 80 records :
- `of.survey.answers` : 62 (déjà dans `deactivated_models`)
- `of.survey.user_input.line` : 17 (déjà dans `deactivated_models`)
- `mail.activity` : 1 (rattrapé sans souci)

Le job de nuit `webhook_night_patrol` ne consulte pas
`deactivated_models` avant de compter les manquants. Il alerte donc en
warning sur des modèles qu'on sait pertinent KO (manifests cassés en
attente OpenFire).

**Fix** : ajouter une jointure ou un filtre sur la table
`deactivated_models` dans la requête qui détecte les manquants. Les
modèles documentés comme désactivés sont attendus à 0%, ce n'est pas
une anomalie.

**Estimation** : 30 min (audit du job nocturne + ajout du filtre +
acquittement des alertes existantes en DB).

### 6. "Mes sujets" — reprise contextuelle au lieu de "fais le point"

**Symptôme actuel** : quand l'utilisateur clique sur un sujet dans la
sidebar gauche "Mes sujets", l'action déclenchée envoie automatiquement
un prompt à Raya équivalent à "fais le point sur ce sujet". Raya répond
par un topo / récap externe du sujet.

**Comportement voulu** : "Mes sujets" sont des **pense-bêtes** que
l'utilisateur crée volontairement pour repérer des fils de pensée
parallèles. Le clic doit déclencher une **reprise contextuelle fluide**,
pas un topo. Comme rouvrir une discussion mise en pause :

- Au moment de la **création** du sujet : Raya prend conscience du sujet
  (objet identifié dans son contexte, lié à la conversation en cours).
- Au moment du **clic** : Raya recharge l'historique et l'état d'avancement
  de ce fil, puis enchaîne naturellement ("on en était à X, tu veux qu'on
  continue dans cette direction ou tu ajoutes quelque chose ?").

**Différence clé** :
- Topo / fais-le-point = vue extérieure imposée, casse la continuité.
- Reprise contextuelle = continuité interne, comme avoir plusieurs
  conversations parallèles dans la même session.

**Reformulation simple** : "Mes sujets" = fils de conversation parallèles
créés volontairement comme repères. Click = "reprends ce fil là où on
l'avait laissé".

**Fichiers concernés** : probablement `app/static/chat-topics.js` (logique
de click sur un topic) + endpoint backend qui charge le contexte du
sujet avant injection dans le prompt.

**Estimation** : 1-2h (revoir le mécanisme de click + adapter le prompt
système pour que Raya reprenne le fil au lieu de faire un topo +
quelques tests).

### 7. Menu 3-points côté user — audit & nettoyage

**Audit du fichier `app/templates/raya_chat.html`** (lignes 60-80) : le
menu 3-points contient 6 entrées dont 2 problématiques pour un user
lambda.

**Bug visuel** : "Paramètres" (`/settings`) et "Administration" (drawer
latéral) utilisent **la même icône engrenage** (le SVG path `M19.4 15...`
est identique aux 2 entrées). D'où la perception de "2 sigles
identiques" et la confusion utilisateur.

**Bug de scope** : "Administration" est visible pour TOUS les users (pas
de `display:none` ni de filtrage par scope), alors qu'elle ouvre un
drawer rempli d'actions techniques inadaptées :
- 🧠 Mémoire & apprentissage : Reconstruire contexte, Synthèse,
  Analyser mails non traités, Reconstruire profil de style
- 📊 État du système : Compteurs, règles actives, bug reports
- ⚠️ Actions sensibles : Purger vieux mails, **Vider l'historique
  mails** (destructif !)
- 🔧 Urgence / Debug : Forcer ingestion inbox/sent, Vérifier base de
  données, Télécharger backup

Aucune de ces actions ne devrait être accessible à un user normal.

**Bug de redondance** : le drawer mélange les actions techniques
ci-dessus avec des actions user (Connexions Gmail/Microsoft, Export
données, Suppression compte, Mentions légales) qui doublonnent déjà
avec `/settings`.

**Action attendue (4 étapes)** :

1. **Retirer l'entrée "Administration"** du menu user lambda (filtrer
   par scope pour qu'elle ne s'affiche pas pour `tenant_user`).
2. **Pour les admin/super_admin** : garder un accès aux actions
   techniques mais sous un nom plus clair ("Outils admin",
   "Maintenance" ou similaire) avec une icône différente de Paramètres
   (pas un engrenage).
3. **Auditer le drawer** : supprimer toutes les actions doublonnées
   avec `/settings` (Connexions, Export données, Suppression compte).
4. **Garder dans `/settings` côté user** : ce qui est utile à un user
   final (connexions, données personnelles, mentions légales,
   déconnexion).

**Estimation** : 2-3h (tri du contenu drawer + filtrage scope dans
template + déplacement éventuel des actions vers /settings + tests).

---

## 🌞 CHANTIER VESTA — analyse 28/04 soir + roadmap multi-phases

> **Contexte** : tour d'horizon de l'API publique Vesta + webhooks le 28/04 soir.
> Mail envoyé à Maxime (dev Vesta) le 28/04 ~21h30 pour demander la liste
> des endpoints internes existants. **En attente de sa réponse** avant
> d'attaquer le code. Sans réponse de Maxime sous 7-10 jours, relancer.

### Vision globale : "single source of truth" Couffrant

Idéalement, les collaborateurs ne saisissent une donnée qu'**une seule
fois**, et Raya la propage entre Vesta ↔ Odoo ↔ Excel SharePoint ↔ fiches
de suivi internes. Plus de double saisie, fiabilisation par contrôle
croisé automatique. Raya joue le rôle de couche de référence + vérification.

C'est le bon framing pour TOUTE intégration future de logiciels métier
chez Couffrant (Vesta, SolarEdge, Tayl0r/Fox ESS, Excel suivi chantiers).

### Inventaire API publique Vesta — état au 28/04

**6 endpoints REST** (auth par clé API à générer dans `app.vesta.eco/integration`) :

| Méthode | Endpoint | Usage |
|---|---|---|
| GET | `/api_v1/users` | Liste collaborateurs orga |
| **PUT** | `/api_v1/customer` | Créer/maj client (idempotent par `customer_id`) |
| GET | `/api_v1/customer/{id}` | Lire client (avec `project_ids[]`) |
| GET | `/api_v1/project/{id}/offers` | Lister offres d'un projet |
| GET | `/api_v1/estimate/{id}` | Lire devis (montants HT/TTC + `signed_file` URL PDF) |
| GET | `/api_v1/estimate/{id}/items` | Lignes devis (avec `unit_price` ET `unit_purchase_price` = **calcul de marge possible**) |

**3 webhooks** (POST, réponse <5s, code 2XX, retry 3 fois automatique) :

| Event | Quand | Données clés |
|---|---|---|
| `offer.proposal_shared` | Proposition partagée au client | `customer_id`, `project_id`, `proposal_public_url`, `photovoltaic_power_kwc` |
| `estimate.sent_for_signature` | Devis envoyé en signature | `estimate_id`, `accounting_number`, montants |
| `estimate.signed` | **Devis signé** ⭐ | tout + `signed_at` + `signed_file` (URL PDF) |

### Limitations identifiées (publique seule)

- ❌ Pas d'endpoint "list all customers" → on dépend des webhooks pour découvrir les clients
- ❌ Pas d'endpoint create/list project → projet créé implicitement avec customer
- ❌ **Champs visite technique pas exposés** (pente toit, type de couverture, distances compteur/toit/tableau, type compteur mono/tri, puissance abonnement, nb panneaux planifiés, etc. — ~25-30 champs métier critiques pour Couffrant)
- ❌ Pas de webhook `customer.created` (sans proposition commerciale, on ne sait pas qu'un client a été créé)
- ❌ Pas d'accès aux notes client ni aux paramètres d'étude
- ❌ Pas d'accès aux modèles de documents

### V.1 — Mail envoyé à Maxime (28/04 ~21h30)

**Statut** : ✅ envoyé. Demande de la liste des endpoints internes existants
+ webhooks supplémentaires possibles. Relance prévue à J+10 si pas de réponse.

**Texte du mail conservé pour traçabilité** :

> Salut Maxime,
> J'espère que tu vas bien. On a connecté l'API publique de Vesta à notre
> outil interne d'assistance (les 6 endpoints + 3 webhooks documentés). La
> lecture clients/devis et les events de signature remontent bien, ça nous
> est déjà utile.
> On voudrait aller plus loin pour centraliser nos données chantiers entre
> Vesta, Odoo et nos fiches de suivi internes — éviter à nos collaborateurs
> de saisir les mêmes infos plusieurs fois et fiabiliser le contrôle croisé.
> Côté écriture, on aimerait surtout pouvoir alimenter les fiches de visite
> technique (pente toit, type de couverture, distances compteur/toit/
> tableau, type de compteur mono/tri, puissance… etc).
> Côté lecture, on aurait besoin de :
> - lister l'ensemble des projets (pas uniquement par customer_id)
> - accéder aux paramètres d'étude
> - accéder aux notes client
> Ma question concrète : est-ce que tu peux nous partager la liste des
> endpoints internes que Vesta utilise déjà pour sa propre interface ? On
> préfère adapter nos demandes à ce qui existe déjà chez vous plutôt que
> te demander de développer from scratch. Si certains sont accessibles en
> l'état moyennant authentification, ça nous irait très bien.
> Dispo pour un call si c'est plus simple à expliquer de vive voix.
> Merci d'avance, Guillaume Perrin / Couffrant Solar

### V.2 — Connecteur Vesta lecture (~3h, à coder après réponse Maxime)

**Pré-requis** : clé API Vesta générée par Guillaume + stockée dans
`tenant_connections.credentials` chiffré (pas en variable env Railway, par
cohérence multi-tenant comme Odoo).

**Étapes** :
- V.2a — Migration DB : nouveau `tool_type='vesta'` accepté, structure
  credentials = `{api_key: "..."}`. (15 min)
- V.2b — `app/connectors/vesta_connector.py` : 6 méthodes mappées sur les
  endpoints REST + helper `upsert_customer(payload)`. Auth header
  `X-API-Key: {key}`. Tests basiques avec mocks. (1h30)
- V.2c — UI panel : ajouter Vesta dans le catalogue de connexions. Bouton
  "Ajouter clé API" + champ saisie + test bouton "Tester la connexion"
  (appel `GET /users`). (1h)
- V.2d — Tour de découverte (cf. `docs/onboarding_decouverte_outils.md`) :
  scanner les clients/projets pour vectoriser les noms et permettre à
  Raya de les retrouver sémantiquement. (30 min)

**Sortie** : Raya peut interroger sa base Vesta via langage naturel
("Combien j'ai signé en mars sur Vesta ?", "Quelle marge sur le devis
Dupont ?").

### V.3 — Webhook receiver Vesta (~2h)

**Étapes** :
- V.3a — Endpoint `POST /webhook/vesta` avec validation client_state (similaire
  à microsoft_webhook). Stockage event dans nouvelle table `vesta_events` ou
  réutilisation `vectorization_queue` pour intégration au pipeline existant.
  Réponse 2XX rapide (<5s) garantie. (1h)
- V.3b — UI configurer URL webhook côté Vesta + bouton "Tester" depuis
  Vesta marche en bout-en-bout. (30 min)
- V.3c — Idempotence : un même `estimate_id` reçu 2 fois ne déclenche pas
  2 actions Raya. (30 min)

**Sortie** : Vesta peut notifier Raya en temps-réel des 3 events.

### V.4 — Logique métier sur events Vesta (~2-3h)

**Décision Guillaume** : pour le MVP, **mode passif** = Raya stocke
l'event et c'est Guillaume qui lui demande conversationnellement
("qu'est-ce qui s'est passé sur Vesta cette semaine ?"). Pas
d'automatisme prédéfini qui ratera les vrais besoins.

**Évolutions possibles à éprouver après usage réel** :
- Sur `estimate.signed` → notification Teams aux collaborateurs concernés
- Sur `estimate.signed` → création automatique du lead Odoo correspondant
- Sur `estimate.signed` → création événement calendrier "Démarrer
  chantier X"
- Comparaison Vesta ↔ Odoo périodique : Raya alerte si un devis est signé
  côté Vesta sans avoir de lead correspondant dans Odoo

À implémenter au cas par cas selon ce que demandera Guillaume après
quelques semaines d'usage du V.3.

### V.5 — Playwright pour saisie auto visite technique (~10-15h, chantier dédié)

**Le besoin réel** identifié le 28/04 : éviter la double saisie pour les
fiches de visite technique (~25-30 champs : pente, type tuiles, distances
compteur, etc.) qui ne sont **pas exposées dans l'API Vesta**. Si Maxime
n'ouvre pas ces endpoints, Playwright (RPA) est le plan B.

**Workflow envisagé** (vision Guillaume) :
1. Sur le terrain, Guillaume parle à Raya en mode vocal : *"Visite tech
   chez Dupont, pente 35°, exposition sud, tuiles canal, distance
   compteur-toit 12m..."*
2. Raya structure dans une fiche standardisée (format JSON défini avec
   Guillaume), lui lit le récap pour validation
3. Guillaume valide → Raya appelle son module Playwright en arrière-plan
4. Playwright se logge à Vesta (credentials chiffrés en DB), navigue
   jusqu'au client Dupont (déjà créé via `PUT /customer`), trouve le
   formulaire visite technique, remplit chaque champ, sauvegarde
5. Confirmation visuelle : Raya prend une capture d'écran de la fiche
   remplie et l'envoie à Guillaume pour vérification

**Pour Guillaume : 30 secondes de dictée** au lieu de 20 minutes de saisie
manuelle. Énorme gain de productivité.

**Avantages vs reverse engineering API privée** :
- ✅ Compatible CGU Vesta (juste un browser qui clique, pas
  d'exploitation API non documentée)
- ✅ Couvre 100% des champs visibles dans l'UI
- ✅ Permet aussi upload de photos (PV de visite, schémas)

**Inconvénients** :
- 🟠 Plus lent que API : 15-30s par formulaire vs 200ms
- 🟠 Fragile aux changements UI Vesta : 30 min de fix si refonte CSS
- 🟠 Demande stockage chiffré identifiants Vesta

**Pré-requis architecture** :
- Module `app/automation/playwright_runner.py` (lance browser headless,
  gère sessions, screenshots, retry)
- Stockage credentials user/password chiffrés dans
  `tenant_connections.credentials` (en plus de la clé API)
- Mécanisme de définition des "scripts" Playwright en JSON (sélecteurs +
  ordre d'actions) pour qu'on puisse ajuster sans redéploiement

**Effort réaliste** : 10-15h pour un questionnaire complet (auth +
navigation + remplissage + gestion erreurs + tests). Chantier dédié à
faire d'une traite, pas en bout de session.

**Lien** : voir aussi le chantier "pilotage navigateur" déjà noté pour
Consuel/Enedis. Mêmes briques techniques, on peut mutualiser.

### V.6 — Transcription audio RDV/visites (~1-2 jours, vision long terme)

**Idée Guillaume 28/04 soir** : utiliser un capteur audio ambient
(téléphone ou enregistreur dédié) pendant les RDV clients ou visites
techniques. Transcription auto via Whisper, puis Raya extrait les données
structurées (info compteur, dimensions toit, attentes client...) et les
propage automatiquement dans les bons logiciels.

**Outils dispo aujourd'hui** :
- **Whisper d'OpenAI** : transcription quasi parfaite en français, coût
  ~0.006€/min (1h d'audio = 36 centimes). API documentée.
- **Anthropic Claude (Sonnet)** : très bon en extraction de données
  structurées depuis transcription brute.

**Pipeline complet à coder** :
1. Endpoint `POST /audio/upload` qui reçoit un fichier audio (mp3/m4a/wav)
2. Whisper API → transcription brute texte
3. Sonnet API avec prompt d'extraction sur fiche standardisée
4. Étape de validation : Raya lit ce qu'elle a compris, Guillaume
   corrige les 2-3 erreurs (Whisper se trompe parfois sur les chiffres :
   "9 kVA" peut devenir "neuf kVA" puis "9000 V")
5. Validation OK → propagation Vesta + Odoo + autres via les V.2/V.5

**Effort estimé** : 1-2 jours dev + tests. **Précision honnête** : c'est
une vision à moyen terme, à attaquer après V.2/V.3 stables et après
décision sur Playwright (V.5). Pas un MVP.

### Plan de bataille global Vesta

| Phase | Statut | Pré-requis | Effort |
|---|---|---|---|
| V.1 — Mail Maxime | ✅ Envoyé 28/04 | — | — |
| V.2 — Connecteur lecture | ⏳ Attente clé API + Maxime | clé API Vesta | ~3h |
| V.3 — Webhook receiver | ⏳ Après V.2 | URL publique Raya | ~2h |
| V.4 — Logique métier | ⏳ Mode passif d'abord | V.3 stable + 2 semaines d'usage | ~2-3h |
| V.5 — Playwright visite tech | ⏳ Si Maxime n'ouvre pas API | Réponse négative Maxime | ~10-15h |
| V.6 — Transcription audio | ⏳ Vision moyen terme | V.2 + V.3 stables | ~1-2j |

**Démarrage probable** : dès retour Maxime (J+1 à J+10). En attendant,
chantier en pause.

---

## 💡 IDEE 27/04 nuit — Auto-detection des manques par Raya

**Intuition Guillaume** : quand Raya cherche une info et ne trouve rien dans son graphe (ex: 'l'adresse de Coullet ?' → vide), pourrait-elle se rendre compte du manque et proposer un re-scan cible pour combler le trou ?

**Faisabilite** : oui, totalement possible. Pas dangereux si :

- Raya **propose** le re-scan (jamais auto-execute)
- Demande confirmation explicite avant toute ecriture
- Periming limite a 1 record cible (pas de re-scan global)
- Pattern aligne sur les actions Odoo existantes

**Quand** : apres stabilisation du systeme actuel. Note ici pour ne pas oublier l'idee.

**Effort estime** : 4-6h (detecter le manque + nouvel outil Raya 'request_data_refresh' + UI confirmation + connexion au scanner).

---

## 🧠 IDEE 27/04 nuit (2) — Comportement agentique multi-tour

**Intuition Guillaume** (apres test sur la tournee #449) : Raya voit 3 stops dans la tournee mais ne fait pas de 2e search pour avoir le detail des clients/taches a visiter. Question : ne l a-t-on pas bridee a force de couches de prompts ?

**Diagnostic preliminaire (audit code raya_agent_core.py + [retrieval.py](http://retrieval.py))** :

- Le prompt systeme V2 est plutot court (1200 chars) et encourage le multi-tour (regle 2 'cherche spontanement', regle 3 'plusieurs outils si besoin').
- La detection de boucle (lignes 615-643) injecte des warnings des le 2eme appel identique ou 4eme appel au meme tool. Possible bridage leger pour les enchainements legitimes.
- Surtout : le format des resultats expose des labels TECHNIQUES (\[of.planning.tour#449\] puis 🔗 TourStop: of.planning.tour.line#4647). Pas une invitation naturelle a creuser. Raya doit decoder pour comprendre qu il y a du contenu vectorise derriere.

**Plan de validation** (pas de modif tant qu on n a pas observe) : Mini-test sur 3-4 questions variant le niveau de detail demande :

- 'J ai quoi demain ?' -&gt; 1 search suffit
- 'Qui je vais voir demain dans ma tournee ?' -&gt; doit creuser
- 'Quels documents emmener demain ?' -&gt; doit creuser Selon les resultats observes :
- Si elle creuse spontanement (cas 2 et 3) -&gt; ne rien toucher
- Si elle ne creuse jamais -&gt; retoucher prompt OU formatage
- Si elle creuse parfois -&gt; noter le pattern, traiter cible

**Pistes si modification necessaire** :

1. Renommer les labels techniques en termes parlants ('of.planning.tour' -&gt; 'Tournee chantier', 'of.planning.tour.line' -&gt; 'Etape de tournee')
2. Ajouter une regle de raisonnement generique au prompt
   ('si tu vois des entites liees avec labels techniques et que la
   question appelle des details, fais une 2e recherche ciblee')
3. Adoucir la detection de boucle (warning au 3eme appel identique
   au lieu du 2eme)

**Effort si modif** : 1-2h selon piste retenue.

**A faire** : observer demain a frais, decider apres.

---

## ✅ ANOMALIE 27/04 — Boucle de feedback 👍/👎 inactive — RÉSOLU 27/04 nuit

> **STATUT : ✅ TERMINÉ et déployé en prod.**
> - Fix 1 (commit `f81f5f8`) : `_raya_core_agent` appelle `save_response_metadata` après chaque échange. Validé en DB sur conv 408.
> - Fix 2 (commit `7f4e28a`) : TypeError silencieux résolu — `rule_ids_injected` était stocké comme `list` par psycopg2 (pas `str`). `json.loads(list)` plantait dans le thread daemon. Fix `isinstance` dans 3 fonctions.
> - **Validation prod** : metadata stockée à chaque conversation, 👍 fonctionnel et renforce les règles utilisées.
> - Section conservée pour traçabilité historique.

---

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

## ✅ ANOMALIE UI 27/04 — Badge "Sonnet" superposé au texte — RÉSOLU 27/04 nuit

> **STATUT : ✅ TERMINÉ et déployé en prod (commit `3977980`).**
> - CSS : padding-top 22px sur la bulle de réponse + cache busting v=79→v=80.
> - Section conservée pour traçabilité historique.

---

**Contexte** : test feedback conv 408 (planning demain).

**Symptome** (screenshot fourni par Guillaume 21:37) : le badge "Sonnet"
qui indique le tier du modele utilise s affiche en haut a droite de la
bulle de reponse, MAIS il chevauche le texte de la 1ere ligne. Effet
brouillon visuel.
**Solution** : remonter le badge au niveau de l heure (lun. 27 avr. a 21:35) ou au-dessus du texte de la reponse, jamais superpose.

**Effort : 15-30 min** (CSS dans chat-messages.js ou raya_chat.html).

**Priorite : Moyenne** (cosmetique mais visible quotidien).

---

## ✅ ANOMALIE Odoo 27/04 — of.planning.tour sans détail des lignes — RÉSOLU 27/04 nuit

> **STATUT : ✅ TERMINÉ et déployé en prod (commits** `af50b16` **+** `f581f58`**).**
>
> - Refactor `_enrich_with_graph` au nouveau format de clés `odoo:res.partner:3795` (au lieu de `odoo-partner-3795`).
> - 17 modèles mappés (vs 7 avant) : ajout Tour, TourStop, Task, sale.order.line, etc.
> - Suppression du fichier legacy `app/jobs/odoo_vectorize.py` (797 lignes).
> - Migration DB : DELETE 1 894 anciens noeuds doublons + 2 517 edges en transaction.
> - **Validation prod** : Raya voit maintenant correctement la structure des tournées + détail des stops.
> - Section conservée pour traçabilité historique.

---

**Contexte** : Guillaume a demande son planning du 28/04. Raya repond qu elle voit bien la tournee #449 mais sans le detail des interventions (clients, adresses, horaires). Le modele `of.planning.tour` n expose pas ces lignes via l API.

**Cause probable** :

- Le manifest `of.planning.tour` n inclut pas les `tour_line_ids`
- OU le manifest existe mais cassait au scan (cf checklist priorite 8 Odoo dans `roadmap_odoo_durable.md`)

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

## ✅ Priorité 1 — Audit isolation multi-tenant — TERMINÉ 28/04 matin

> **STATUT : ✅ TERMINÉ. 8 commits déployés en prod ce matin.**
>
> Bilan complet :
>
> - ✅ Étape 0 : migrations DB (commit `e937dca`, 26/04)
> - ✅ Étape A : isolation OAuth + endpoints admin (`2bdddb0`, `0f333da`, 26/04)
> - ✅ Étape B : seat counter + UI quota (commits 26/04)
> - ✅ Étape 0bis : normalisation tenant `couffrant` → `couffrant_solar` (`02019e1`, 27/04)
> - ✅ Étape C complète (28/04 matin) :
>   - LOT 2 (`3f3e1c2`) : bug logique scope I.15 + bonus admin/costs
>   - LOT 3a (`085542b`) : [profile.py](http://profile.py) + synthesis_engine.py + report_actions.py
>   - LOT 3b (`db2d720`) : memory_teams (5 fonctions)
>   - LOT 3c (`5f4283f`) : connection_token_manager (6 fonctions)
>   - LOT 4 (`e79bb75`) : ATTENTION super_admin + outlook anti-pattern A.5
>   - LOT 5 (`516b4e4`) : nettoyage hardcoded_permissions.py
>   - LOT 6a (`68fbaad`) : renommage backend SCOPE_USER → SCOPE_TENANT_USER + suppression SCOPE_CS
>   - LOT 6b (`a4bb50b`) : renommage frontend
> ****Bilan findings audit 25/04** :
>
> - 🔴 8 CRITIQUE : tous fixés
> - 🟠 15 IMPORTANT : 14/14 actifs fixés (I.12/I.13 = features intentionnelles confirmées)
> - 🟡 10 ATTENTION : 9/10 fixés (A.4 = volontairement cross-tenant pour debug super_admin)
> ****Reste mineur** :
>
> - Followup A.5 : propagation `username` dans 4 call-sites de `perform_outlook_action` (\~30 min)
> - Tests bout-en-bout `pierre_test` (à faire par Guillaume plus tard)
> ****Modèle de rôles tranché 28/04** : 4 scopes (super_admin / admin / tenant_admin / tenant_user). Doc archivé : `docs/archive/decision_roles_utilisateurs_a_trancher_RESOLU_28avril.md`.
>
> Section conservée pour traçabilité historique.

---

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

> 💡 **Sujet voisin (28/04)** : voir `docs/onboarding_decouverte_outils.md` — quand Raya est connectée à un nouvel outil, elle a besoin d'un **tour de découverte guidée** avec le super_admin pour apprendre les conventions métier propres à l'entreprise. Cas réel : confusion planning équipe vs planning Guillaume le 28/04. À traiter dans la même session que les connecteurs.

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
