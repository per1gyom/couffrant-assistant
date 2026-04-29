# 🎙️ Audit — Intégration Plaud AI + TapeACall + moteur de règles événementielles

> Document écrit par Claude pendant la nuit du 29 au 30/04 (~01h30).
> À lire au réveil **avant** d'attaquer LOT 3 de la 2FA — celui-ci reste prioritaire.
> Le présent chantier est plus gros (~30-50h dev) et passera après le déploiement
> de la version d'essai.

---

## 🎯 Comprendre le besoin (reformulation)

Tu enregistres ton activité quotidienne via deux sources :
1. **Plaud AI** — RDV en présentiel, conversations avec clients/partenaires
2. **TapeACall** — appels téléphoniques (iOS)

Tu veux que Raya :

### A) Ingère automatiquement ces enregistrements
Dès qu'un fichier audio ou une transcription arrive, elle entre dans le pipeline Raya.

### B) Extrait les données pertinentes
Pas juste un blob de texte. Elle identifie :
- **Qui** : client (Mr X), partenaire (OpenFire), collègue interne
- **Quoi** : sujet (devis PV, panne onduleur, négociation contrat...)
- **Quand** : date du RDV/appel, durée
- **Données techniques** : kWc, kWh, marques (Solaredge, Enphase, Huawei), prix, dates de chantier
- **Engagements** : "Je vous envoie le devis demain", "Le client doit me rappeler vendredi"
- **Décisions** : ce qui a été tranché

### C) Dispatche selon des règles que TU définis
Exemple textuel : « À chaque fois que j'ai un RDV client dans mon calendrier ET que j'enregistre un audio à la même heure, alors :
1. Génère un compte-rendu structuré avec les données techniques
2. Envoie le résumé par mail à mon associé
3. Crée une tâche dans Odoo "envoyer devis chiffré"
4. Mémorise les engagements pris dans le graphe sémantique »

### D) Apprend de tes habitudes
Quand Raya remarque que tu fais toujours la même chose après un certain type d'enregistrement (ex: "Tu transfères toujours les CR de RDV partenaire à l'associé"), elle te propose d'en faire une règle automatique.

---


---

## 🧩 INTÉGRATION CRITIQUE — Features optionnelles par tenant + par user

> Note Guillaume du 30/04 ~01h45 : « Lorsque je vais vendre la solution
> à un tenant, il pourra ne pas avoir besoin de cet outil de captation audio.
> Ce qui permettra d'adapter son forfait selon les outils dont il va vouloir
> avoir l'utilisation. Il faudra que du panel super admin je puisse paramétrer
> un tenant avec les outils dont il va vouloir la disponibilité. Pour un, ou
> plusieurs de ces utilisateurs. »

Cette demande **dépasse largement le sujet Plaud/TapeACall**. Elle concerne
**toutes les features Raya** et constitue la fondation du modèle commercial
"forfait sur mesure par tenant" que tu as confirmé hier.

### 🎯 Modèle commercial cible

```
┌─────────────────────────────────────────────────────────────┐
│  Étape 1 (vente) : Tenant signe contrat                     │
│  → coche dans le devis les outils/features qu il veut       │
│    Outlook ✅  Gmail ❌  Drive ✅  Captation audio ❌       │
│    Moteur règles ✅  Vesta ✅  Page accueil dynamique ❌    │
│  → forfait = somme des features cochées                     │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│  Étape 2 (onboarding) : Super_admin paramètre               │
│  → Active dans Raya les features payées par le tenant       │
│  → Toi (ou collab super_admin) connecte les outils tiers    │
│    avec les credentials du tenant                           │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│  Étape 3 (granularité) : Super_admin alloue par user        │
│  → Charlotte (tenant juillet) : Outlook + Drive             │
│  → Pierre (couffrant_solar) : Outlook + Drive + Audio       │
│  → Sabrina (couffrant_solar) : Outlook seul                 │
│  → Pour chaque user : sous-ensemble des features tenant     │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│  Étape 4 (UX user) : User voit uniquement ses features      │
│  → Sabrina ne voit pas le menu "Audio" dans son chat        │
│  → Tenant juillet ne voit pas Vesta dans /admin             │
│  → Boutons grisés/cachés selon le contexte                  │
└─────────────────────────────────────────────────────────────┘
```

### 🏗️ Architecture proposée

#### Composants à créer

**1. Table `feature_registry`** (catalogue de toutes les features Raya)

```sql
CREATE TABLE feature_registry (
  code TEXT PRIMARY KEY,           -- ex: "audio_capture", "event_rules"
  label TEXT NOT NULL,             -- "Captation audio (Plaud + TapeACall)"
  description TEXT,
  category TEXT NOT NULL,          -- "connector", "ai_feature", "ui_feature"
  default_in_starter BOOLEAN,      -- inclus dans le forfait de base ?
  default_in_pro BOOLEAN,          -- inclus dans le forfait pro ?
  monthly_price_eur NUMERIC(10,2), -- prix indicatif mensuel
  requires_features TEXT[],        -- dépendances (ex: event_rules requires audio_capture)
  created_at TIMESTAMP DEFAULT NOW()
);
```

**2. Table `tenant_features`** (features activées par tenant)

```sql
CREATE TABLE tenant_features (
  id SERIAL PRIMARY KEY,
  tenant_id TEXT NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
  feature_code TEXT NOT NULL REFERENCES feature_registry(code),
  enabled BOOLEAN DEFAULT true,
  enabled_for_all_users BOOLEAN DEFAULT true,  -- si false → granularité per-user
  enabled_at TIMESTAMP DEFAULT NOW(),
  enabled_by TEXT,                              -- super_admin qui a activé
  contract_reference TEXT,                       -- ref contrat/avenant
  notes TEXT,
  UNIQUE (tenant_id, feature_code)
);
```

**3. Table `user_feature_overrides`** (granularité user dans un tenant)

```sql
CREATE TABLE user_feature_overrides (
  id SERIAL PRIMARY KEY,
  username TEXT NOT NULL,
  tenant_id TEXT NOT NULL,
  feature_code TEXT NOT NULL REFERENCES feature_registry(code),
  enabled BOOLEAN NOT NULL,        -- true=force on, false=force off
  set_by TEXT,                     -- super_admin OU tenant_admin
  set_at TIMESTAMP DEFAULT NOW(),
  reason TEXT,
  UNIQUE (username, tenant_id, feature_code)
);
```

**4. Helper Python `is_feature_enabled()`**

```python
def is_feature_enabled(
    feature_code: str,
    username: str,
    tenant_id: str,
) -> bool:
    """
    Logique en cascade :
    1. Si user_feature_overrides existe pour (user, tenant, feature) → applique
    2. Sinon, si tenant_features.enabled_for_all_users=true → enabled
    3. Sinon, si tenant_features absent → désactivé
    
    Cache LRU 60s pour perf (la plupart des appels sont en hot path).
    """
```

**5. UI super_admin** : page `/super_admin/tenant/<id>/features`

- Liste des features de `feature_registry`
- Toggle on/off par feature pour ce tenant
- Si toggle ON : option "tous les users" OU "sélectionner les users"
- Affichage des dépendances (cocher event_rules → coche aussi audio_capture)
- Calcul du prix mensuel cumulé en bas de page (indicatif)
- Bouton "Sauvegarder" + log dans `tenant_events`

**6. Décorateur FastAPI `require_feature()`**

```python
@router.post("/admin/2fa/setup/start")
def start_2fa_setup(
    request: Request,
    user: dict = Depends(require_admin),
    _: bool = Depends(require_feature("two_factor_auth")),
):
    ...
```

Renvoie 403 + JSON explicite si la feature n'est pas activée pour ce user.

**7. Filtrage UI côté front**

- Endpoint `GET /me/features` retourne la liste des feature_code activées pour
  l'user courant
- Le menu chat / panel admin masque les boutons des features désactivées

### 📋 Catalogue initial de features à toggler

Listing des features actuelles + futures qui devraient passer par ce système :

| Code | Label | Catégorie | État actuel |
|---|---|---|---|
| `outlook` | Connecteur Outlook | connector | Existant (via tenant_connections) |
| `gmail` | Connecteur Gmail | connector | Existant |
| `drive_sharepoint` | Connecteur Drive/SharePoint | connector | Existant |
| `odoo` | Connecteur Odoo | connector | Existant |
| `vesta` | Connecteur Vesta | connector | À venir |
| `teams` | Connecteur Teams | connector | Partiel |
| `audio_capture_plaud` | Captation audio Plaud AI | ai_feature | **À créer (chantier)** |
| `audio_capture_tapeacall` | Captation appels TapeACall | ai_feature | **À créer** |
| `transcription` | Transcription audio Whisper | ai_feature | **À créer** |
| `event_rules` | Moteur de règles événementielles | ai_feature | **À créer** |
| `homepage_dynamic` | Page accueil dynamique | ui_feature | À venir |
| `tts_voice_reading` | Lecture audio TTS (ElevenLabs) | ai_feature | Existant |
| `proactive_alerts` | Alertes proactives | ai_feature | Existant |
| `signatures_multi_mailbox` | Signatures multi-boîtes | ui_feature | Existant |
| `rules_optimizer` | Optimiseur de règles hebdo | ai_feature | Existant |
| `daily_reports` | Rapport matinal automatique | ai_feature | Existant |
| `scanner_universel` | Scanner Drive/Odoo | ai_feature | Existant |
| `agent_mode` | Mode agentique multi-tour | ai_feature | Existant (feature flag global pour l'instant) |
| `web_search` | Recherche web Anthropic | ai_feature | Existant |
| `bug_reports_ui` | Bouton bug reports | ui_feature | Existant |
| `account_export_rgpd` | Export RGPD | ui_feature | Existant |

### 🎯 Mode de migration progressive

Le système doit être **rétro-compatible** avec l'existant :

- Phase 1 : Créer les 3 tables + le helper + le décorateur (sans appliquer)
- Phase 2 : Seed `feature_registry` avec ~20 features actuelles
- Phase 3 : Backfill `tenant_features` : toutes les features activées pour tous les
  tenants existants (= état actuel = "tout est inclus")
- Phase 4 : Ajouter le décorateur `require_feature()` aux endpoints sensibles,
  un par un (chantier de migration douce sur 2-3 semaines)
- Phase 5 : UI super_admin pour configurer
- Phase 6 : Ajout des nouvelles features (Plaud, event_rules) directement avec
  le système

Avantage : zero downtime, zero régression, on peut désactiver le système si
problème (env var `FEATURE_FLAGS_ENFORCEMENT=false`).

### 🔒 Sécurité

- **Modification** : `tenant_features` modifiable uniquement par super_admin
- **Modification** : `user_feature_overrides` modifiable par super_admin OU tenant_admin (mais le tenant_admin ne peut pas créer un override pour une feature désactivée au niveau tenant)
- **Audit** : chaque modification écrit dans `tenant_events` (table existante)
- **Cache** : 60s pour ne pas surcharger la DB
- **Fallback** : si erreur de lecture des flags, on default à "désactivé" (fail-safe)

### 💰 Logique de tarification (indicatif)

Le prix mensuel `monthly_price_eur` dans `feature_registry` permet de calculer
automatiquement le forfait d'un tenant :

```
forfait_couffrant_solar = somme des prix des features tenant_features actives
                        = outlook (5€) + gmail (5€) + drive (10€) + odoo (15€)
                        + audio_capture_plaud (20€) + event_rules (15€)
                        + transcription (10€) + ... (etc)
                        = 80€/mois
```

Cet affichage dans `/super_admin/tenant/<id>/billing` aide à la conversation
commerciale : tu peux montrer au tenant "votre forfait actuel = 80€, si vous
voulez ajouter Vesta c'est +25€".

### 📊 Effort estimé pour ce système

| Composant | Effort | Bloquant ? |
|---|---|---|
| 3 tables + migrations | 1h | Non, additif |
| Helper `is_feature_enabled` + cache | 2h | Non |
| Décorateur `require_feature` | 1h | Non |
| Endpoint `/me/features` | 30min | Non |
| Seed `feature_registry` (~20 features) | 1h | Non |
| Backfill `tenant_features` (rétro-compat) | 1h | Non |
| UI super_admin paramétrage | 4-6h | Oui pour la vente |
| UI super_admin facturation indicative | 2h | Non |
| Migration progressive endpoints (require_feature partout) | 4-6h | Étalé |
| Filtrage UI côté front (menus, boutons) | 3-5h | Oui pour UX |
| Tests + doc | 2h | Non |
| **Total** | **22-30h** | **3-4 jours** |

### ⚠️ Cohérence avec le reste

🟢 Cohérent avec ton modèle commercial confirmé hier
🟢 Cohérent avec la philosophie "super_admin connecte les outils"
🟢 Cohérent avec `tenant_connections` + `connection_assignments` qui font déjà
   du toggle au niveau **outils tiers** — on étend juste au niveau **features**
🟢 Cohérent avec `max_users` (quota) et `super_admin_permission_level`
   (permissions outils) déjà sur `tenants`

🟡 À discuter : faut-il aussi un système de **plans** (Starter, Pro, Enterprise)
   qui regroupe automatiquement des features, ou reste-t-on en pur à la carte ?
   Mon avis : à la carte est plus flexible pour démarrer, on pourra packager en
   plans plus tard si l'offre se simplifie.

🟡 À discuter : ce système vaut aussi pour les **outils tiers** (Outlook,
   Gmail, Drive). Est-ce qu'on harmonise tout dans `feature_registry` +
   `tenant_features`, ou est-ce qu'on garde `tenant_connections` séparé
   pour les outils tiers et `tenant_features` pour les features produit ?
   Mon avis : harmoniser. Un connecteur est juste une feature qui a aussi
   une connexion technique. Le découplage est une dette technique inutile.

### 🎯 Recommandation

**Faire ce système AVANT le chantier Plaud/TapeACall.** Pour deux raisons :

1. C'est la **fondation du modèle commercial**. Sans ça, tu ne peux pas vendre
   la version d'essai à des tenants qui veulent des forfaits différents.

2. La feature `audio_capture_plaud` (et ses dépendances `transcription` +
   `event_rules`) seront **immédiatement toggleables** dès leur création.
   Pas de retrofit douloureux.

**Quand le faire ?**

Pendant la "fenêtre de stabilisation" entre la 2FA terminée et le déploiement
de la version d'essai. Ce système (~3-4j) est le pré-requis #1 pour que tu
puisses commencer à vendre des forfaits différenciés.

### Mise à jour de la priorisation roadmap

Avant cette précision, la roadmap était :
1. 2FA (LOTs 3-7) → 2. Note UX #7 → 3. 2FA externes → 4. Version d'essai → 5. Plaud/TapeACall

Avec cette précision, ça devient :
1. 2FA (LOTs 3-7) → 2. Note UX #7 → 3. 2FA externes → **4. Système feature flags (~3-4j)** → 5. Version d'essai → 6. Plaud/TapeACall (qui s'intégrera nativement au système feature flags)

---


## 📋 Ce qui existe déjà dans Raya (briques réutilisables)

Excellente nouvelle : **70% de la plomberie est déjà là**.

| Brique existante | Rôle pour ce projet |
|---|---|
| `pending_actions` (15 col) | Workflow de validation des actions auto avant exécution. **Réutilisable tel quel** — on ajoute juste de nouveaux `action_type` (RECORDING_SUMMARIZE, MEETING_DISPATCH, etc.) |
| `aria_rules` (15 col) | Règles déjà stockées et apprises. **À étendre** avec un nouveau `level='trigger'` ou une nouvelle table `event_rules` (à trancher) |
| `vectorization_queue` | Queue async qui dépile toutes les 5s. **Réutilisable** pour traiter les transcriptions hors flux user |
| `semantic_graph_nodes/edges` | Graphe entités. **Idéal** pour lier transcript → client → RDV → tâche |
| `mail_memory` + `webhook_subscriptions` | Réception emails Microsoft. **Réutilisable** si Plaud envoie son CR par mail |
| `drive_semantic_content` | Indexation Drive. **Réutilisable** si Plaud sync ses transcripts vers OneDrive/Drive |
| Tableau `aria_rules` actuel | 138 règles actives Guillaume — déjà la base de "comment Guillaume travaille" |
| `rules_pending_decisions` | Workflow questions Raya → user. **Réutilisable** pour proposer des règles |
| Connecteurs Outlook / Gmail | Pour envoyer les CR auto |
| `actions/SEND_MAIL/SEND_GMAIL/REPLY` | Pattern d'action validable. **À enrichir** avec MEETING_SUMMARY |

**Ce qui manque** :
- Table pour stocker les enregistrements bruts (`recordings`)
- Table pour stocker les transcriptions (`transcripts`)
- Service de transcription audio → texte (Whisper / AssemblyAI / Deepgram)
- Endpoints d'ingestion (upload manuel + webhook auto)
- Moteur de matching transcript ↔ entités du graphe
- Système de règles **événementielles** (When/If/Then) — différent des règles `aria_rules` actuelles qui sont du texte libre injecté au prompt
- UI de configuration des règles

---

## 🔌 Sources audio — méthodes d'ingestion possibles

### Plaud AI

D'après ce que je sais (à confirmer demain) :

| Méthode | Faisabilité | Effort | Recommandation |
|---|---|---|---|
| **Email forwarding** | 🟢 Simple | 1h | Plaud envoie le CR par mail → Raya intercepte via webhook Outlook |
| **Sync OneDrive/Drive** | 🟡 Si Plaud le fait | 2-3h | Raya scanne le folder, ingère les .txt qui arrivent |
| **API Plaud** | 🔴 Pas sûr qu'elle existe | ? | À vérifier sur leur doc |
| **Upload manuel via UI Raya** | 🟢 Toujours possible | 2h | Bouton "Importer un CR Plaud" dans le chat |

🛑 **Question pour toi** : tu as quel modèle de Plaud (NotePin, Note Pro, ou la version logicielle) ? Est-ce qu'il envoie les CR par mail automatiquement ?

### TapeACall

| Méthode | Faisabilité | Effort | Recommandation |
|---|---|---|---|
| **Email forwarding** | 🟢 Natif TapeACall | 1h | Tu partages l'audio par mail → Raya transcrit et traite |
| **Sync iCloud Drive** | 🔴 iCloud sans API | - | Pas viable |
| **OneDrive sync** | 🟡 Si l'app le supporte | 2-3h | Idéal mais à vérifier |
| **Upload manuel** | 🟢 Toujours possible | 2h | Idem Plaud |

🛑 **Question pour toi** : tu utilises TapeACall Pro ? Tu as déjà configuré un export auto vers un cloud ?

### Recommandation synthèse

Pour démarrer vite : **email forwarding** comme méthode principale.
Tu envoies (manuellement ou auto via une règle Outlook) tes enregistrements à `recordings@raya-ia.fr` (ou un alias dédié), et Raya intercepte.

Avantages :
- Zéro friction utilisateur
- Réutilise tout le webhook Outlook qu'on a déjà
- Trace mail = audit naturel
- Marche pour Plaud ET TapeACall ET tout autre outil futur

---

## 🎤 Transcription audio (pour TapeACall)

Plaud fait déjà la transcription. Pour TapeACall, on a 4 options :

| Service | Qualité FR | Diarisation | Prix | Vitesse | Recommandation |
|---|---|---|---|---|---|
| **Whisper API (OpenAI)** | 🟢 Très bonne | ❌ Non native | 0,006€/min ≈ 0,36€/h | 🟡 Moyen | 🥇 **Choix par défaut** : on a déjà OPENAI_API_KEY |
| **AssemblyAI** | 🟢 Excellente FR | 🟢 Native | 0,37€/h | 🟢 Rapide | 🥈 Si besoin de "qui parle" |
| **Deepgram** | 🟢 Bonne | 🟢 Native | 0,43€/h | 🟢 Très rapide | Alternatif |
| **Whisper local** | 🟢 Identique API | ❌ | 0€ mais GPU obligatoire | 🔴 Lent sur CPU | Pas viable Railway |

**Reco** : démarrer avec **Whisper API**. Coût estimé < 5€/mois pour ton volume.
Si tu veux savoir QUI dit quoi (toi vs client), upgrade vers AssemblyAI plus tard.

---

## 🏗️ Architecture cible — 4 couches

```
┌─────────────────────────────────────────────────────────────┐
│  COUCHE 1 : INGESTION                                       │
│  Email webhook | Drive sync | Upload UI                     │
│  → table `recordings` (audio brut + métadonnées)            │
└──────────────────┬──────────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────────┐
│  COUCHE 2 : TRANSCRIPTION (pour audio)                      │
│  Whisper API → texte brut                                   │
│  → table `transcripts` (texte + horodatage + speakers)      │
└──────────────────┬──────────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────────┐
│  COUCHE 3 : EXTRACTION & LIAISON                            │
│  LLM extrait : client, RDV, sujet, données tech, action items│
│  Matching auto : transcript ↔ calendar.event ↔ partner Odoo │
│  → graphe sémantique enrichi                                │
└──────────────────┬──────────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────────┐
│  COUCHE 4 : MOTEUR DE RÈGLES ÉVÉNEMENTIELLES                │
│  Trigger (recording_processed)                              │
│  + Conditions (matching RDV ? client connu ? etc.)          │
│  → Actions (générer CR, envoyer mail, créer tâche)          │
│  → pending_actions (avec confirmation user si voulu)        │
└─────────────────────────────────────────────────────────────┘
```

---

## 🧠 Moteur de règles événementielles (cœur du sujet)

C'est la partie la plus innovante. Concept inspiré de Zapier/IFTTT, mais profondément intégré au modèle Raya.

### Schéma d'une règle

```yaml
# Exemple : la règle que tu as donnée
nom: "CR auto RDV client → associé"
trigger:
  type: recording_processed
  filtres:
    - type: client_meeting   # vs phone_call, internal_meeting
    - duree_min: 5_minutes
conditions:
  # Toutes les conditions ci-dessous doivent matcher
  - type: matches_calendar_event
    fenetre_temporelle: ±15min
    event_match_type: "client"   # filtre les RDV taggés client
  - type: client_identified
    field: graphe.client_id
actions:
  # Exécutées dans l'ordre, certaines en parallèle
  - type: generate_meeting_summary
    template: "rdv_client_pv"   # template CR avec sections : objet, données techniques, décisions, prochaines étapes
    save_to: drive
  - type: send_mail
    to: "{associe.email}"   # variable résolue depuis le graphe
    subject: "CR RDV {client.nom} - {date}"
    body: "{summary}"
    confirmation: false    # auto, sans confirmation
  - type: extract_engagements
    save_to: graphe
  - type: create_pending_action
    action_type: "FOLLOWUP_DEVIS"
    payload: {client: "{client.id}", deadline: "{date+3j}"}
    confirmation: true   # demande confirmation user

apprentissage:
  - source: user_explicit   # tu l'as créée explicitement
  - confidence: 1.0
  - reinforcements: 0
```

### Storage : nouvelle table `event_rules`

Pas réutilisable tel quel `aria_rules` car ces règles sont **structurées (YAML/JSON)** alors que `aria_rules.rule` est du **texte libre injecté au prompt**.

```sql
CREATE TABLE event_rules (
  id SERIAL PRIMARY KEY,
  username TEXT NOT NULL,
  tenant_id TEXT NOT NULL,
  name TEXT NOT NULL,
  description TEXT,
  trigger_type TEXT NOT NULL,    -- recording_processed, mail_received, etc.
  trigger_filters JSONB,
  conditions JSONB,
  actions JSONB,
  enabled BOOLEAN DEFAULT true,
  source TEXT DEFAULT 'user_explicit',  -- vs 'pattern_detected'
  confidence REAL DEFAULT 1.0,
  reinforcements INT DEFAULT 0,
  last_triggered_at TIMESTAMP,
  trigger_count INT DEFAULT 0,
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW()
);
```

### Bibliothèque d'actions (pour démarrer)

Une douzaine de blocs d'actions élémentaires que les règles assemblent :

| Action | Description | Effort impl. |
|---|---|---|
| `generate_meeting_summary` | LLM crée un CR structuré selon template | 3h |
| `send_mail` | Réutilise le SEND_MAIL existant | 0h ✅ |
| `send_gmail` | Idem Gmail | 0h ✅ |
| `create_pending_action` | Met une tâche dans le pending queue | 0h ✅ |
| `save_to_drive` | Crée doc dans SharePoint/OneDrive | 2h |
| `extract_engagements` | LLM identifie les promesses faites | 2h |
| `create_odoo_task` | Crée crm.lead ou project.task | 3h (déjà 70% via search_odoo) |
| `tag_in_graph` | Lie au graphe sémantique | 1h |
| `notify_user` | Push proactive_alerts | 0h ✅ |
| `create_calendar_event` | Suite RDV | 2h |
| `update_partner_summary` | Met à jour `aria_contacts` | 1h |

### Templates de comptes-rendus

Pour que les CR soient consistants, on définit des templates :

- `rdv_client_pv` : RDV client photovoltaïque (sections : besoin, dimensionnement, prix, prochaines étapes)
- `rdv_partenaire_technique` : RDV partenaire (sections : sujet, accords, suivi)
- `appel_sav` : Appel service après-vente (sections : motif, diagnostic, action menée)
- `appel_prospection` : Appel prospect (sections : intérêt, budget, calendrier)

L'utilisateur peut créer ses propres templates.

---

## 🤖 Apprentissage automatique des règles

C'est ce qui rend Raya intelligente vs une simple règle Zapier.

### Détection de patterns

Toutes les semaines, Raya analyse les `event_rules` triggerées + les actions exécutées + les corrections user, et propose :

> "J'ai remarqué : tu transfères systématiquement les CR de RDV avec OpenFire à Charlotte (5 fois en 3 semaines). Veux-tu que je crée une règle automatique ?"

### Workflow de validation

1. Pattern détecté → `rules_pending_decisions` (table existante !)
2. Question posée à Guillaume au prochain login
3. Si OK → règle créée avec `source='pattern_detected'`, `confidence=0.7`
4. À chaque déclenchement réussi : `reinforcements += 1, confidence += 0.05`
5. Si Guillaume corrige une règle 3 fois → re-question : "Faut-il l'ajuster ?"

---

## 💸 Coûts récurrents estimés

| Poste | Volume estimé | Coût/mois |
|---|---|---|
| Whisper API (transcription) | ~30h audio/mois | ~10€ |
| LLM Claude pour extraction + CR | ~500 enregistrements/mois | ~30-50€ |
| Stockage Drive (audios) | ~10 Go/mois | déjà inclus M365 |
| **Total** | | **~40-60€/mois** |

À mettre en regard du temps gagné : **2-3h/jour de moins en notes manuelles** = ~60h/mois. Le ROI est massif.

---

## 📅 Plan d'attaque proposé en 4 phases

### 🟢 Phase A — Ingestion + transcription (5-8h)
- A1. Table `recordings` + `transcripts`
- A2. Endpoint upload manuel `/admin/recordings/upload` (UI + API)
- A3. Webhook email parser : extraction des PJ audio des mails
- A4. Service `app/transcription.py` avec Whisper API
- A5. Job APScheduler `process_pending_transcriptions` toutes les 30s

**Livrable** : tu envoies un audio par mail à `recordings@raya-ia.fr`, dans 30s tu vois la transcription dans `/admin/recordings`.

### 🟡 Phase B — Extraction + matching (5-7h)
- B1. Pipeline LLM d'extraction (client, RDV, sujet, données tech, engagements)
- B2. Matching transcript ↔ calendar.event (fenêtre ±15min)
- B3. Matching transcript ↔ partner Odoo (via nom client)
- B4. Création de noeuds + arêtes dans le graphe sémantique
- B5. UI de visualisation transcript enrichi

**Livrable** : tu vois pour chaque transcript le client/RDV/données techniques détectés, et la possibilité de corriger.

### 🟠 Phase C — Moteur de règles (10-15h)
- C1. Table `event_rules` + migrations
- C2. Schema YAML/JSON des règles + validation Pydantic
- C3. Moteur d'évaluation conditions
- C4. Bibliothèque d'actions (12 blocs)
- C5. Worker async de déclenchement
- C6. UI configuration des règles (page `/admin/rules/events`)
- C7. Logs déclenchements + journal d'exécution

**Livrable** : tu peux créer ta règle "CR RDV client → associé" via l'UI, elle se déclenche auto.

### 🔵 Phase D — Apprentissage (6-10h)
- D1. Job hebdo `detect_recurring_patterns`
- D2. Génération propositions de règles
- D3. UI questions au login pour validation user
- D4. Reinforcement learning sur les règles existantes
- D5. Détection de règles obsolètes

**Livrable** : Raya te propose proactivement des règles que tu n'as pas pensé à créer.

### Total estimé
**26-40h** soit **4-6 jours** en mode focus.

---

## ❓ Questions pour toi (à répondre demain)

### Sources
1. Plaud AI — quel modèle ? Export auto par mail ? Sync Drive ?
2. TapeACall — version Pro ? Export auto vers OneDrive ?
3. D'autres sources audio à prévoir (Teams calls, Zoom recordings) ?

### Volume
4. Combien d'enregistrements par jour en moyenne ? (10 ? 30 ?)
5. Durée moyenne d'un enregistrement ? (2 min appel, 30 min RDV ?)

### Multi-utilisateurs
6. Que toi pour l'instant, ou Charlotte aussi ?
7. Plus tard Pierre/Sabrina/Benoît ?

### Consentement / RGPD
8. Tu fais comment actuellement pour le consentement à l'enregistrement ? (mention au début de l'appel ?)
9. OK avec stockage des transcripts en base + Drive ? Période de rétention ?

### Modèle business
10. Cette feature est dans le forfait standard de tous les tenants, ou c'est un upsell facturé en plus ?

### Préférences techniques
11. Diarisation (qui parle) : utile pour toi ?
12. Confirmation systématique avant envoi de mail auto, ou full auto pour les actions "safe" ?
13. Format CR : Markdown structuré ? PDF ? Word ?
14. Stockage audio : on garde l'audio brut ou on supprime après transcription ?

### Priorité dans la roadmap
15. Avant ou après la version d'essai (qui dépend de la 2FA + onboarding outils) ?

### Modèle commercial / facturation (ajout 30/04 ~01h45)
16. Tu préfères vendre les features **à la carte** (chaque feature = ligne de devis)
    ou en **plans packagés** (Starter / Pro / Enterprise) ?
17. Tu as déjà des prix indicatifs en tête pour les principales features ?
    (ex: Outlook = X€/user/mois, Audio capture = Y€/user/mois...)
18. Granularité : tu veux pouvoir activer une feature pour **certains users d'un tenant
    seulement** (ex: chez Couffrant, Pierre a Audio mais pas Sabrina), ou c'est toujours
    "tout le tenant ou rien" ?
19. Le `tenant_admin` (Charlotte chez juillet, ou ses futurs équivalents) doit-il pouvoir
    **désactiver** une feature pour un de ses users (override down), ou seul le super_admin
    a la main sur la liste des features ?
20. Quand un tenant ne paie plus (impayé), tu veux **désactiver toutes ses features** d'un
    coup (mode urgence) ou juste suspendre l'accès au login (existant via `users.suspended`) ?

---

## 🎯 Mon avis perso

C'est une **excellente idée**. Vraiment. Pour 3 raisons :

1. **C'est ce qui transforme Raya en assistant indispensable**.
   Aujourd'hui Raya réagit à tes questions. Avec ça elle agit en arrière-plan.

2. **Le ROI métier est énorme**.
   Économise 2-3h/jour à un commercial/dirigeant. Pour 50€/mois.

3. **C'est le différenciateur SaaS**.
   Aucun concurrent ne fait ça aussi bien intégré. Plaud transcrit. Zapier orchestre.
   Raya fait les deux + apprend.

**MAIS** :

🟡 Ce chantier est **gros** (4-6j) et **arrive après** la version d'essai. La 2FA + l'onboarding outils restent prioritaires pour pouvoir onboarder Pierre/Sabrina/Benoît.

🟡 La phase Plaud/TapeACall doit attendre **les retours utilisateurs réels**.
Sinon on construit en aveugle. Tu te connais toi, mais Charlotte n'enregistre peut-être pas pareil.

🟡 Le moteur de règles événementielles est un **petit produit en soi**.
Il mérite d'être conçu en pensant qu'il servira aussi pour d'autres déclencheurs : nouveau mail, nouveau lead Odoo, nouvelle pièce SharePoint, nouvelle facture, etc.
Donc autant le faire bien dès le départ — il sera la fondation de tous les automatismes futurs de Raya.

---

## ⏭️ Recommandation pour la suite

### Ordre suggéré (révisé après précision modèle commercial du 30/04 ~01h45)
1. ✅ Finir LOT 3-7 de la 2FA (~3-4h)
2. ✅ Note UX #7 (retirer Administration menu user) (~2h)
3. ✅ 2FA externes restantes (~30min)
4. 🟢 **Système feature flags par tenant + par user (~3-4j)** ← AJOUT
5. ✅ → **Déployer la version d'essai** + onboarder Pierre/Sabrina/Benoît
6. 🟡 Vérifier 1-2 semaines que ça tourne bien
7. 🟢 Attaquer ce chantier Plaud/TapeACall en mode focus 4-6j
   (la captation audio sera nativement toggleable grâce au système feature flags)

### En attendant
- Tu peux commencer à utiliser Plaud + TapeACall normalement (comme aujourd'hui)
- Tu peux noter les patterns récurrents que tu remarques (ça nourrira la phase D)
- On pourra aussi commencer par juste la **Phase A** (ingestion+transcription) sans le moteur de règles : tu auras déjà de la valeur avec un simple "tous mes audios sont transcrits et cherchables dans Raya"

---

## 📂 Documents liés

- `docs/raya_capabilities_matrix.md` : matrice des capacités actuelles
- `docs/architecture_connexions.md` : modèle mental des connecteurs
- `docs/raya_memory_architecture.md` : 3 niveaux de mémoire Raya
- `docs/lot2_2fa_29avril_nuit.md` : récap LOT 2 2FA
- `docs/a_faire.md` : roadmap principale (à enrichir avec ce chantier)

---

*Document écrit par Claude pendant la nuit du 29 au 30 avril 2026 (~01h30 UTC).*
*À discuter avec Guillaume au réveil avant tout démarrage.*
