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

### Ordre suggéré
1. ✅ Finir LOT 3-7 de la 2FA (~3-4h)
2. ✅ Note UX #7 (retirer Administration menu user) (~2h)
3. ✅ 2FA externes restantes (~30min)
4. ✅ → **Déployer la version d'essai** + onboarder Pierre/Sabrina/Benoît
5. 🟡 Vérifier 1-2 semaines que ça tourne bien
6. 🟢 Attaquer ce chantier Plaud/TapeACall en mode focus 4-6j

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
