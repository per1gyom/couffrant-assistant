# Vision Connexions Universelles Raya (1er mai 2026)

**Statut :** Vision documentée — pas encore implémentée
**Auteurs :** Guillaume + Claude (échange du 01/05 matin, après audit
complet et fix de 4 bugs critiques sur le webhook Outlook)
**Objectif :** Définir une fois pour toutes l'ARCHITECTURE COMMUNE de
toutes les connexions Raya (mails, pièces jointes, Drive, Odoo, Vesta,
WhatsApp, Teams, et toute future intégration), avec les MÊMES garanties
de stabilité, de complétude et de monitoring partout.

**Décisions tracées :** 18 questions (Q1-Q18) tranchées par Guillaume
+ 9 enrichissements techniques issus de l'audit standards industriels.

---

## 🎯 Pourquoi ce document existe

### Le déclencheur

Le 01/05/2026 au matin, audit complet des connexions Raya. Découverte
d'un silence de 17 jours sur l'ingestion Outlook (du 14 avril au 1er
mai). Diagnostic : 4 bugs imbriqués qui ont cassé le webhook Microsoft
Graph silencieusement.

Les 4 bugs ont été corrigés (commits 0f371ef, 19b0ac4, 063bd47), mais
Guillaume a stoppé l'enchaînement de patches :

> "On est en train de faire exactement ce que je ne voulais pas, à
> savoir des patches sur des patches. On réessaye, on regarde, on
> reteste, on refait, refait un nouveau patch. C'est exactement ce
> que je ne voulais pas. Donc là, stop. Repart de la vision globale."

### Le constat

L'architecture initiale (webhook Microsoft + polling Gmail simple) **ne
peut pas tenir les promesses** que Raya doit faire à ses utilisateurs :

```
PROMESSES NÉCESSAIRES                    ARCHITECTURE INITIALE
─────────────────────                    ────────────────────────
Tous les mails entrants vus              ❌ Inbox seul, pas Junk, pas dossiers
Tous les mails sortants vus              ❌ Pas couvert
Modifications (lu/déplacé) vues          ❌ Pas couvert
Stable sans intervention                 ❌ Sub expire 3j, 17j de silence
Onboarding historique propre             ❌ Manuel via /learn-inbox-mails
Détection de silence + alerte           ❌ Aucune
```

### La conclusion

> "Il faut que ce soit stable, automatique, sans intervention humaine
> récurrente, avec alerte en cas de problème. Et il faut absolument
> que toutes les prochaines connexions qu'on établisse soient basées
> sur ce même principe. Connexion stable, précise, sans loupé possible.
> Ou alerte en cas de problème."

→ Ce qu'on doit construire : pas un patch sur l'existant, mais une
**architecture commune** pour toutes les connexions présentes et
futures.

---

## 📐 PARTIE 1 — Vision et principes

### Les 7 piliers communs à toute connexion Raya

```
1. INGESTION COMPLÈTE
   Tout ce qui rentre, sort, ou se modifie dans la source connectée
   est vu, vectorisé et mis en graphe. Aucun angle mort.

2. ONBOARDING HISTORIQUE
   À la connexion d'une nouvelle source, choix de la profondeur
   d'historique à ingérer (3 mois, 6 mois, 12 mois, tout). Pour
   Guillaume = TOUT par défaut, pour les futurs clients = 12 mois.

3. STABILITÉ ABSOLUE
   Zéro intervention humaine récurrente. Pas de "tous les 3 jours
   il faut renouveler", pas de "toutes les semaines il y a un truc
   à cliquer". Auto-récupération sur les erreurs courantes.

4. COMPRÉHENSION DU CONTENU
   Pas juste "voir" un fichier ou un mail. VRAIMENT comprendre :
   extraire le texte, identifier les entités (montants, dates,
   contacts), résumer, taguer. La donnée doit être exploitable.

5. ROUTAGE INTELLIGENT
   Le module connexion EXPOSE l'information structurée ("ceci est
   une facture, montant X, fournisseur Y"). Le module métier (compta,
   CRM, etc.) DÉCIDE où ça va selon le paramétrage du tenant.
   Séparation stricte des responsabilités.

6. BIDIRECTIONNALITÉ MAÎTRISÉE
   Quand pertinent (WhatsApp, Vesta), Raya peut aussi ÉCRIRE.
   Mais TOUJOURS avec validation humaine (suggestions + 1 clic).
   Pas d'auto-écriture sans contrôle utilisateur.

7. MONITORING + ALERTES UNIVERSELS
   Toute connexion est surveillée par les MÊMES règles. Si quoi
   que ce soit cloche, l'utilisateur est prévenu via les MÊMES
   canaux. Filet de sécurité homogène et systématique.
```

### Principe directeur sous-jacent

> "Toutes les données auxquelles Raya a accès doivent être en graphe
> vectorisé. Pas d'exception. Une donnée non graphée = invisible.
> Le graphe doit être ultra complet, ultra précis, performant."
> — Guillaume, principe énoncé dans les sessions des 28-30/04.

Conséquence : les 7 piliers ne sont pas négociables. Une connexion
qui ne respecterait pas l'un d'eux serait une **connexion incomplète**
qui crée des angles morts dans la conscience de Raya.

### Principes transverses captés pendant le questionnaire

```
SOUVERAINETÉ UTILISATEUR
  L'utilisateur garde TOUJOURS la maîtrise de ce que Raya voit.
  • Liste blanche pour WhatsApp (pas tout indexé par défaut)
  • Blacklist pour Drive/SharePoint (tout par défaut, exclusions possibles)
  • Validation humaine pour toute écriture sortante
  • Respect des Sensitivity Labels Microsoft Purview
  → Aucun cas où Raya passerait outre la volonté utilisateur.

VALIDATION HUMAINE EN PHASE D'APPRENTISSAGE
  Pendant les premières semaines de vie d'une connexion, Raya tague
  automatiquement mais demande validation sur les cas à faible
  confiance. Une fois calibrée → mode autonome. Voir Active Learning
  (Q4) pour le mécanisme technique.

PAS DE FUTUR, ON FAIT BIEN DÈS LE DÉBUT
  Toutes les optimisations techniques identifiées (lifecycle
  notifications, files API, pré-filtrage embeddings, etc.) sont
  intégrées au chantier de départ. Pas de "on verra plus tard"
  qui crée du patch-sur-patch ensuite.

RÈGLES GÉNÉRIQUES, PAS SPÉCIFIQUES MÉTIER
  Le module connexion ne contient AUCUNE règle codée pour le solaire,
  le BTP ou Couffrant Solar. Tout ce qui est métier est paramétrable
  par tenant. Charlotte (juillet) et un futur commerçant doivent
  pouvoir utiliser le même module connexion.

MODULES COMMUNS RÉUTILISABLES
  Trois modules transversaux écrits UNE FOIS, utilisés par TOUTES
  les connexions : connection_health, alert_dispatcher,
  connection_resilience. Voir Partie 2.

LE LLM EST CONSOMMABLE, LE GRAPHE EST L'ACTIF
  Cohérent avec la vision long terme déjà documentée dans
  vision_proactivite_30avril.md. Le code de connexion doit être
  agnostique au LLM précis (abstraction provider). Le graphe enrichi
  par les connexions est ce qui se valorise dans le temps.
```

---

## 🏗️ PARTIE 2 — Architecture cible commune

### Vue d'ensemble en 1 schéma

```
┌─────────────────────────────────────────────────────────────────┐
│                       SOURCES EXTERNES                           │
│  Outlook │ Gmail │ SharePoint │ Google Drive │ Odoo │ Vesta │ WhatsApp │ Teams │
└──────────────────────────────┬──────────────────────────────────┘
                               │
                ┌──────────────┴──────────────┐
                │   COUCHE CONNECTEURS        │
                │   (1 par source)            │
                │   - mail_outlook            │
                │   - mail_gmail              │
                │   - drive_sharepoint        │
                │   - odoo                    │
                │   - whatsapp                │
                │   - vesta (futur)           │
                │   - teams (futur)           │
                └──────────────┬──────────────┘
                               │
                ┌──────────────┴──────────────┐
                │   3 MODULES COMMUNS         │
                │   (HÉRITÉS PAR TOUTES LES CONNEXIONS)│
                │                             │
                │   ★ connection_health       │
                │     (liveness, statut, monitoring)│
                │                             │
                │   ★ connection_resilience   │
                │     (self-healing 4 étapes, │
                │      circuit breaker)       │
                │                             │
                │   ★ alert_dispatcher        │
                │     (5 niveaux, multi-canaux)│
                └──────────────┬──────────────┘
                               │
                ┌──────────────┴──────────────┐
                │   COUCHE COMPRÉHENSION       │
                │   (1 module commun)         │
                │   - extraction texte        │
                │   - vision IA conditionnelle│
                │   - tagging structuré       │
                │   - pré-filtrage embeddings │
                └──────────────┬──────────────┘
                               │
                ┌──────────────┴──────────────┐
                │   GRAPHE + VECTORISATION    │
                │   - semantic_graph          │
                │   - mail_memory             │
                │   - drive_semantic_content  │
                │   - odoo_semantic_content   │
                │   - attachment_index (NEW)  │
                └─────────────────────────────┘
```

### Module commun n°1 — `connection_health`

**Rôle :** surveiller la santé de chaque connexion via le pattern
**liveness check** (décision Q15). Différencier "tout va bien et il
n'y a juste rien de neuf" vs "vraie panne technique".

**Principe technique :**

```
À CHAQUE TENTATIVE de poll/sync, on log dans une table dédiée :
  • timestamp_poll_start
  • timestamp_poll_end
  • status   = "ok" / "auth_error" / "network_error" / "rate_limit" / 
                "subscription_dead" / "quota_exceeded"
  • items_seen      = nb d'éléments retournés (peut être 0)
  • items_new       = nb d'éléments réellement nouveaux (peut être 0)
  • next_delta_token = token Microsoft/Google retourné (preuve de succès)
  • duration_ms     = temps de la requête

→ Le SUCCÈS est tracé même quand items_new = 0.
→ Le SILENCE = absence de ligne récente = vraie panne.
```

**Règle d'alerte universelle :**

```
"Alerte SI le dernier poll réussi (status='ok') date de plus de
N × interval_polling, où N = 3."

Exemple Outlook (poll toutes les 5 min)
  → alerte si pas de 'ok' depuis 15 min

Exemple Drive (poll toutes les 5 min)
  → alerte si pas de 'ok' depuis 15 min

Exemple Odoo (poll toutes les 2 min)
  → alerte si pas de 'ok' depuis 6 min

Exemple WhatsApp (réception via webhook Twilio + ping outbound)
  → ping toutes les 15 min, alerte si pas de pong depuis 30 min

UNE SEULE LOGIQUE, applicable partout.
ZÉRO faux positif (indépendant des horaires métier).
ZÉRO connaissance des habitudes utilisateur nécessaire.
```

**Tables de support :**

```sql
CREATE TABLE connection_health (
  id SERIAL PRIMARY KEY,
  connection_id INT NOT NULL,         -- réf vers tenant_connections
  tenant_id TEXT NOT NULL,
  username TEXT NOT NULL,
  connection_type TEXT NOT NULL,      -- 'mail_outlook', 'drive', 'odoo', etc.
  status TEXT NOT NULL,               -- 'healthy' / 'degraded' / 'down'
  last_successful_poll_at TIMESTAMP,
  last_poll_attempt_at TIMESTAMP,
  consecutive_failures INT DEFAULT 0,
  current_delta_token TEXT,           -- delta_link Microsoft / historyId Gmail
  expected_poll_interval_seconds INT, -- 300 pour mails, 120 pour Odoo, etc.
  alert_threshold_seconds INT,        -- = 3 × expected_poll_interval_seconds
  metadata JSONB,
  updated_at TIMESTAMP DEFAULT NOW(),
  UNIQUE(connection_id)
);

CREATE TABLE connection_health_events (
  id SERIAL PRIMARY KEY,
  connection_id INT NOT NULL,
  poll_started_at TIMESTAMP NOT NULL,
  poll_ended_at TIMESTAMP,
  status TEXT NOT NULL,               -- 'ok' / 'auth_error' / 'network_error' / etc.
  items_seen INT DEFAULT 0,
  items_new INT DEFAULT 0,
  next_delta_token TEXT,
  duration_ms INT,
  error_detail TEXT,                  -- pour debug si status != 'ok'
  created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_health_events_conn_time
  ON connection_health_events(connection_id, created_at DESC);
```

**API exposée par le module :**

```python
# Appelé à chaque tentative de poll par n'importe quel connecteur
connection_health.record_poll_attempt(
    connection_id, status, items_seen, items_new,
    next_delta_token, duration_ms, error_detail
)

# Appelé par le job de monitoring (toutes les 1 min)
connection_health.check_all_connections()
  → liste des connexions en alerte → alert_dispatcher

# Appelé par l'UI /admin/health
connection_health.get_status_summary(tenant_id)
  → état couleur de chaque connexion (vert/jaune/rouge)
```

### Module commun n°2 — `connection_resilience`

**Rôle :** auto-récupération sur les erreurs courantes (décision Q17).
Pattern **self-healing 4 étapes + circuit breaker**.

**Les 4 étapes de récupération automatique :**

```
ÉTAPE 1 — Retry immédiat (3 tentatives sur 30 secondes)
  Couvre   : micro-coupure réseau, latence Microsoft, race condition
  Résout   : 95% des erreurs
  Alerte   : aucune (transparent pour l'utilisateur)

ÉTAPE 2 — Backoff exponentiel (3 retries sur 5 min)
  Couvre   : rate limiting Microsoft, surcharge temporaire, 429/503
  Résout   : 4% supplémentaires
  Alerte   : INFO interne (visible dans /admin/health, pas notif user)

ÉTAPE 3 — Auto-réparation contextuelle (selon type d'erreur)
  → auth_error          : tentative refresh token automatique
  → subscription_dead   : tentative recréation subscription automatique
  → rate_limit_persistent : pause prolongée (1h) + reprise auto
  → quota_exceeded      : pause jusqu'au lendemain
  Résout   : 0.9% supplémentaires
  Alerte   : WARNING (l'utilisateur est informé qu'il y a eu un incident
             auto-résolu, par email récap du soir, pas en temps réel)

ÉTAPE 4 — Circuit breaker ouvert + alerte CRITICAL
  Si tout ce qui précède a échoué, on ARRÊTE de tenter pour ne pas
  saturer le service externe (ce qui pourrait nous faire bannir).
  La connexion est marquée "down". L'utilisateur reçoit une alerte
  CRITICAL avec actions concrètes proposées :
    • "Reconnecte ton compte Microsoft"
    • "Vérifie les permissions OAuth"
    • "Le service externe est peut-être en panne"
  Résout   : 0.1% des cas, intervention humaine
```

**Pattern circuit breaker :**

```
État FERMÉ (fonctionnement normal)
  → tous les polls fonctionnent
  → pas d'alerte

État DEMI-OUVERT (1 retry test toutes les 5 min)
  → atteint après l'étape 4
  → on tente UNE seule requête tous les 5 min pour voir si ça remarche
  → ça évite de bombarder le service externe pendant qu'il est down
  → si ça remarche → état FERMÉ + alerte de récupération

État OUVERT (pause totale)
  → atteint si trop de retries en demi-ouvert échouent
  → pause jusqu'à intervention manuelle de l'utilisateur
```

**Why this matters :** c'est exactement ce qui nous a fait bannir
notre subscription Microsoft entre le 14 avril et le 1er mai. Microsoft
recevait 4 erreurs 500 en cascade, et a probablement désactivé la
subscription en mode silencieux. Avec circuit breaker, après 4 erreurs
on aurait paused la connexion → recréation propre → silence évité.

**API exposée :**

```python
# Wrap autour de toute opération qui peut échouer
@connection_resilience.protected(connection_id, max_retries=3)
def fetch_mail_delta(token, delta_link):
    return graph_get(token, delta_link)

# Le décorateur gère :
#  - Retry immédiat sur erreurs transitoires
#  - Backoff exponentiel sur 429
#  - Auto-refresh sur 401
#  - Circuit breaker sur échec persistant
#  - Logging dans connection_health_events
```

### Module commun n°3 — `alert_dispatcher`

**Rôle :** envoyer les alertes aux bons canaux selon la gravité
(décision Q16). Système **5 niveaux multi-canaux**.

**Les 5 niveaux de gravité :**

```
🟢 INFO          
   Aucune notification active.
   Visible uniquement dans /admin/health (ligne dans le dashboard).
   Exemple : "Drive a fait 3 micro-coupures auto-récupérées"

🟡 WARNING       
   Notification IN-APP (badge dans Raya).
   + email du soir récapitulatif (groupé, pas urgent).
   Exemple : "Le polling Drive est lent depuis 2h"

🟠 ATTENTION     
   Push mobile + email immédiat.
   Pas de SMS (réservé au CRITICAL).
   Exemple : "Token Microsoft expire dans 24h"

🔴 CRITICAL      
   SMS + Push + email + chat (TOUS canaux en parallèle).
   Exemple : "Aucune ingestion Outlook depuis 1h, vraie panne"

🚨 BLOCKING      
   SMS répété toutes les 15 min jusqu'à acquittement.
   + appel téléphonique automatique.
   + tous les canaux du CRITICAL.
   Réservé aux pannes massives (ex: tous les tokens HS d'un tenant).
```

**Configuration par tenant et par utilisateur :**

```
VALEURS PAR DÉFAUT INTELLIGENTES
  Codées dans le système, conviennent à 95% des utilisateurs.

PARAMÉTRAGE UTILISATEUR AVANCÉ
  UI dans Raya pour les 5% qui veulent ajuster :
    • "Moi je veux SMS dès WARNING"
    • "Pas de push, juste email pour tout sauf CRITICAL"
    • "Pour BLOCKING j'autorise l'appel à 4h du matin"
  
  Stocké dans user.settings.alert_preferences (JSONB)
  Override possible par tenant_id sur le plan global
```

**Infrastructure technique disponible :**

```
✅ Twilio (SMS + appels)        — déjà configuré dans Railway
✅ Email SMTP                   — déjà dans le code Raya
✅ Push Mobile                  — Flutter app, à activer
✅ Chat in-app                  — déjà dans le code Raya
✅ Webhook Teams                — déjà connecté via Microsoft Graph
```

**API exposée :**

```python
alert_dispatcher.send(
    tenant_id="couffrant_solar",
    username="guillaume",
    severity="critical",                    # info / warning / attention / critical / blocking
    title="Connexion Outlook en panne",
    message="Aucune ingestion depuis 65 min. Token possiblement révoqué.",
    actions=[                              # actions concrètes proposées
        {"label": "Reconnecter Outlook", "url": "/login?provider=microsoft"},
        {"label": "Voir détails", "url": "/admin/health/connection/6"},
    ],
    source_type="connection_health",
    source_id="connection_6",
    auto_escalate_after_minutes=30,        # passe à BLOCKING si pas acquitté
)
```

### Pattern delta sync universel

**Décision Q1 :** polling delta + webhook accélérateur. Appliqué de
manière identique à toutes les connexions qui le supportent.

**Niveau 1 — Polling delta (la base, toujours actif)**

```
Toutes les 2-5 minutes selon la connexion :

1. Lire le delta_token stocké pour cette connexion
   (delta_link Microsoft Graph, historyId Gmail, write_date Odoo, etc.)

2. Appeler l'API de la source : "donne-moi tout ce qui a changé
   depuis ce token"

3. Recevoir la liste COMPLÈTE des changements :
   • items ajoutés (entrants ET sortants pour les mails)
   • items modifiés (lu/non lu, déplacé, drapeau, contenu modifié)
   • items supprimés

4. Pour chaque change, traiter dans la couche Compréhension :
   - Extraction de contenu
   - Tagging
   - Vectorisation
   - Mise à jour du graphe

5. Stocker le NOUVEAU delta_token pour le prochain cycle.

6. Logger dans connection_health_events (status='ok', items_new=N).
```

**Caractéristiques garanties :**

```
✅ Stable    : pas d'expiration, pas de subscription à maintenir
✅ Complet   : couvre TOUS les dossiers, TOUS les types de changement
✅ Reprise   : si Railway redémarre, le delta_token reprend où on était
✅ Idempotent : peut tourner 2x sans poser de problème (delta_token
                ne re-livre que ce qui a changé)
✅ Garanti   : Microsoft et Google promettent qu'aucune donnée n'est
                ratée par leur API delta (contractuel)
```

**Niveau 2 — Webhook (accélérateur optionnel)**

```
Quand une notification arrive de la source :
  → ne fait QUE déclencher un poll delta immédiat
  → AUCUNE logique métier dans le webhook
  → AUCUN refetch direct du contenu
  → on déclenche juste "fait tourner le polling delta maintenant
    au lieu d'attendre le prochain cycle"

Bénéfices :
  ✅ Si webhook plante → polling régulier rattrape (max 2-5 min)
  ✅ Si webhook marche → temps réel (~30 sec)
  ✅ Si Microsoft désactive la sub → polling continue tout seul
  ✅ Le webhook devient un "bonus", plus un "point de défaillance critique"
```

**Niveau 3 — Lifecycle Notifications (NOUVEAU, ENRICHISSEMENT Q1)**

```
Microsoft Graph envoie des événements SPÉCIAUX quand une subscription
va mourir : subscriptionRemoved, missed, reauthorizationRequired.

On s'abonne à ces événements EN PLUS des notifications mail.

Quand un événement lifecycle arrive :
  → recréation automatique de la subscription
  → déclenchement d'un poll delta (au cas où on aurait raté des notifs)
  → log WARNING dans connection_health
  
→ AURAIT ÉVITÉ les 17 jours de silence du mois d'avril.
→ 0 ligne de code en plus côté logique métier, juste un événement à
   écouter dans le webhook handler.
```

**Niveau 4 — Réconciliation quotidienne**

```
Toutes les nuits à 4h pour chaque connexion :

1. count_serveur = appel API "combien d'items au total" 
   (ex: GET /me/messages?$count=true pour Outlook)

2. count_local = SELECT COUNT(*) FROM mail_memory WHERE ...

3. Si delta > seuil (1% par exemple) :
   → re-sync forcé sans delta_token (récupère TOUT)
   → alerte WARNING ("on avait raté X items, rattrapés cette nuit")

→ Filet ULTIME : on est prévenu en moins de 24h si on rate quoi que
  ce soit. Ce filet n'est PAS censé se déclencher en pratique (les
  3 niveaux précédents devraient suffire), mais c'est notre garantie
  de complétude absolue.
```

### Couche compréhension de contenu

**Décisions Q2, Q10, Q13, Q14 :** stratégie unifiée pour comprendre
le contenu des fichiers/pièces jointes/photos.

**Pipeline de compréhension en 3 étapes :**

```
ÉTAPE 1 — Extraction texte (toujours, peu cher)
  • PDF natif        → pdftotext
  • PDF scanné       → OCR Tesseract (rapide)
  • Word/Excel       → librairies Python natives (python-docx, openpyxl)
  • Images           → métadonnées EXIF + nom de fichier
  • Email body       → BeautifulSoup (HTML→texte)
  Coût : ~0.0001€ par document

ÉTAPE 2 — Triage : a-t-on besoin de Vision IA ?
  Approche en cascade (cheap → expensive) :
  
  2a. Règles génériques (gratuites, instantanées)
      Si nom contient {facture, devis, contrat, BL, AR, ...}
        → Vision recommandée
      Si extension {.pdf, .jpg, .png} ET texte extrait < 100 chars
        → c'est probablement un scan → Vision recommandée
      Si type MIME = image
        → Vision recommandée (sauf images de signatures email = exclues)
      
  2b. Pré-filtrage par embeddings (cheap, ~0.0001€)
      Calculer l'embedding du texte extrait + nom + métadonnées.
      Comparer aux "vecteurs de référence" des catégories pertinentes
      pour ce tenant (factures, contrats, documents techniques).
      Si proximité élevée avec une catégorie "à comprendre"
        → Vision recommandée.
      → C'EST CE QU'ENRICHISSEMENT Q13 APPORTE : décision rapide et
         bon marché AVANT de payer le LLM.
  
  2c. Triage Haiku (~0.001€)
      Si les 2a et 2b sont indécis, on pose la question à Haiku :
      "Ce document mérite-t-il une analyse approfondie ? Réponds
       par OUI ou NON."

ÉTAPE 3 — Vision IA (sur les cas qui méritent vraiment, ~0.05€)
  • Modèle : Claude Sonnet 4 Vision (ou next gen quand dispo)
  • Anthropic Files API (ENRICHISSEMENT Q2) : upload une fois,
    analyse plusieurs fois (texte + résumé + tags). Économise ~30%
    par rapport à 3 appels séparés.
  
  Sortie structurée multi-niveaux (décision Q14 + ENRICHISSEMENT Q14) :
    1. Texte brut extrait (recherche fine)
    2. Résumé synthétique (recherche rapide)
    3. Tags structurés :
       - type_document  ('facture', 'devis', 'contrat', 'photo_chantier'...)
       - entites        ({montants:[...], dates:[...], contacts:[...], 
                           ref_dossier:[...]})
       - confidence     (0-1)
    4. EMBEDDINGS À 2 NIVEAUX :
       - embedding par chunk/paragraphe (recherche fine "trouve la
         phrase qui mentionne 9 kWc")
       - embedding global du document (recherche large "trouve
         tous les devis solaires")
```

**Stockage du résultat :**

```
Tout va dans la table attachment_index (NEW) :
  - source_type        ('mail_attachment', 'drive_file', etc.)
  - source_ref         (ID du mail ou du fichier)
  - file_name, file_size, mime_type
  - text_content       (extraction étape 1)
  - summary_content    (résumé étape 3, peut être NULL si pas de Vision)
  - tags               (JSONB structuré, peut être NULL)
  - embedding_global   (pgvector, dimension 1536)
  - chunks             (référence vers attachment_chunks pour les chunks)
  - vision_processed   (bool, pour distinguer "Vision faite" vs "pas faite")
  - tenant_id, username
  - created_at, updated_at

Et dans le graphe sémantique :
  Nœud : attachment_<id> avec node_type = 'attachment'
  Arêtes vers :
    - le mail/fichier source
    - les contacts identifiés (via tags.entites.contacts)
    - les projets identifiés (via tags.entites.ref_dossier)
    - les montants si > seuil (entité financière)
```

**Important — règles génériques multi-tenant (note Guillaume Q13) :**

```
Les règles 2a doivent être GÉNÉRIQUES, pas codées pour le solaire.

✗ MAUVAIS (trop spécifique Couffrant) :
  - "factures_enedis, devis_solaires, photos_panneaux" → Vision

✓ BON (générique multi-métier) :
  - Tout document COMMERCIAL/CONTRACTUEL → Vision
  - Toute IMAGE associée à un contexte métier → Vision
  - Toute pièce jointe avec nom CODÉ → Vision

Chaque tenant peut ÉTENDRE ces règles via paramétrage métier
(table tenant_attachment_rules), mais le module reste universel.
```

---

## 🔌 PARTIE 3 — Application par connecteur

Cette partie décrit comment l'architecture commune (Partie 2) s'applique
concrètement à chaque connexion. Toutes les connexions héritent des
3 modules communs. Les particularités sont précisées ci-dessous.

### 3.1 — Mails Outlook

**Décisions actées :**

```
Q1  = Polling delta + webhook accélérateur (réactivité indispensable)
Q2  = Pièces jointes : texte par défaut + Vision IA si pertinent
Q4  = Tags auto + validation premières semaines + autonome ensuite
ENRICHISSEMENT Q1 : Lifecycle Notifications Microsoft (anti-silence)
```

**Architecture :**

```
NIVEAU 1 — Polling delta toutes les 5 min
  API : Microsoft Graph Delta Query
  Endpoint : /me/mailFolders/{folder}/messages/delta
  Folders surveillés :
    • Inbox (entrants)
    • Sent Items (sortants)
    • Junk Email (rattrapage spam mal classé)
    • Custom folders identifiés par l'utilisateur (auto-discovery)
  
  Stocké : delta_link par folder dans connection_health.current_delta_token

NIVEAU 2 — Webhook Microsoft Graph (accélérateur)
  Subscription : /subscriptions
  Resource : me/mailFolders/inbox/messages
  Event : created
  Action : déclencher poll delta immédiat (PAS de fetch direct)

NIVEAU 3 — Lifecycle Notifications (NOUVEAU)
  Subscription : ajouter lifecycleNotificationUrl à la subscription
  Events surveillés :
    • subscriptionRemoved   → recréer la subscription + re-sync
    • missed                → forcer un poll delta (notif perdue)
    • reauthorizationRequired → refresh token + renew

NIVEAU 4 — Réconciliation nocturne
  À 4h : count Microsoft vs count mail_memory pour cette boîte.
  Si delta > 1% → re-sync forcé sans delta_link + alerte WARNING.
```

**Pièces jointes (cas particulier mail) :**

```
Au moment où un mail est ingéré et contient des pièces jointes :
  1. Pour chaque pièce jointe : passage dans la couche Compréhension
  2. Création d'un record dans attachment_index
  3. Liaison dans le graphe : mail → attachment + arêtes contextuelles
  4. Si tags.type_document = 'facture' :
     → exposition d'un événement structuré au module métier 
       (ex: accounting_engine peut s'y abonner)
     → AUCUN routage automatique côté connexion mail
       (séparation des responsabilités, décision Q3)
```

**Spécificités Outlook :**

```
✅ Couvre tous les dossiers (vs subscription qui ne couvre que inbox)
✅ Capture les modifications (lu/non lu, déplacement, suppression)
✅ Capture les sortants (Sent Items, indispensable pour Raya)
✅ Anti-silence Lifecycle Notifications (le bug 17 jours ne peut plus 
   se produire)
```

### 3.2 — Mails Gmail

**Décisions actées :** mêmes que Outlook (cohérence architecturale).

**Architecture :**

```
NIVEAU 1 — Polling history toutes les 5 min
  API : Gmail History API
  Endpoint : users.history.list
  Stocké : startHistoryId par boîte dans connection_health.current_delta_token
  
  Couvre : entrants, sortants, modifications (labels, suppressions)
  → équivalent du delta query Outlook, garanti complet par Google.

NIVEAU 2 — Webhook (Gmail Pub/Sub Watch)
  API : Gmail watch + Google Cloud Pub/Sub
  Push notification quand boîte change → poll history immédiat
  
  Note : nécessite un projet Google Cloud + Pub/Sub topic.
  À configurer dans la phase d'implémentation.

NIVEAU 3 — Watch expiration (équivalent Lifecycle Notifications)
  Gmail watch expire au bout de 7 jours.
  Job nocturne qui renouvelle les watches J-1.
  Si renew échoue → poll history immédiat + alerte WARNING + retry.

NIVEAU 4 — Réconciliation nocturne
  À 4h : count Gmail vs count mail_memory pour cette boîte.
  Mêmes règles que Outlook.
```

**Spécificités Gmail :**

```
✅ History API garantit zéro perte (limite : startHistoryId valide
   pendant ~7 jours, donc renew obligatoire)
✅ Pub/Sub Watch = équivalent webhook Microsoft mais via Google Cloud
✅ Multi-boîtes (Guillaume a 6 boîtes Gmail) : un connector + delta_token
   par boîte, géré par connection_id distinct
```

### 3.3 — Pièces jointes mail (transverse)

Voir Partie 2 — Couche compréhension de contenu pour le pipeline complet.

**Particularité :** les pièces jointes héritent de la connexion mail
qui les a apportées. Elles sont logées dans `attachment_index` mais
référencent leur mail source. Si le mail est supprimé, la pièce jointe
est marquée `deleted_at` (soft delete pour conserver l'historique du
graphe).

### 3.4 — Drive / SharePoint

**Décisions actées :**

```
Q8  = Tout par défaut + blacklist par dossiers
Q9  = Delta query toutes les 5 min (cohérent avec mails)
Q10 = Compréhension de contenu identique aux pièces jointes
ENRICHISSEMENT Q8 : Respect Sensitivity Labels Microsoft Purview
ENRICHISSEMENT Q9 : Webhook accélérateur Drive (pas que polling)
```

**Architecture :**

```
NIVEAU 1 — Polling delta toutes les 5 min
  API : Microsoft Graph Drive Delta
  Endpoint : /drives/{drive-id}/root/delta
  Stocké : delta_link dans connection_health.current_delta_token
  
  Capture : ajouts, modifications, suppressions, déplacements
  → garanti complet par Microsoft.

NIVEAU 2 — Webhook accélérateur (NOUVEAU - ENRICHISSEMENT Q9)
  Subscription : /subscriptions sur la ressource /drives/{id}/root
  Event : updated
  Action : déclencher poll delta immédiat
  → "Devis modifié à 14h pour réunion à 16h" capté immédiatement.

NIVEAU 3 — Lifecycle Notifications
  Mêmes principes que pour les mails.

NIVEAU 4 — Réconciliation nocturne
  À 4h : count files Microsoft vs count drive_semantic_content.
```

**Filtrage et exclusions :**

```
PAR DÉFAUT : tout le drive est indexé (décision Q8).

EXCLUSIONS UTILISATEUR (UI dans /admin/panel) :
  Liste de chemins de dossiers à exclure :
    /Personnel
    /RH/Confidentiel
    /Direction/Stratégie
  Stockage : tenant_drive_blacklist (table)

EXCLUSIONS AUTOMATIQUES (NOUVEAU - ENRICHISSEMENT Q8) :
  Microsoft Purview Sensitivity Labels :
    • Si un fichier ou dossier porte le label "Confidentiel" ou
      "Restreint" → exclu automatiquement
    • Si un fichier porte le label "Personnel" → exclu
  
  Récupération via Microsoft Graph :
    GET /drives/{id}/items/{item-id}?$expand=labels
  
  Filet de sécurité automatique : même si l'utilisateur oublie de
  blacklister un dossier RH, les Sensitivity Labels le protègent.
```

**Pour Couffrant Solar (action à mener post-implémentation) :**

```
État actuel : connexion SharePoint limitée au dossier 'photovoltaïque'
              (test Guillaume).
Action : reprendre la connexion à la racine + définir la blacklist
        des dossiers hors-périmètre Raya.
À faire : une fois le système universel en place, dans le cadre
         d'un onboarding propre.
```

### 3.5 — Odoo

**Statut au 01/05/2026 (Semaine 2 implémentée)** :

```
✅ Polling delta toutes les 2 min via write_date (Niveau 1)     - DEPUIS 20/04
✅ Inscription dans connection_health (Etape 2.3)                - 01/05
✅ Logging events dans connection_health_events (Etape 2.3)      - 01/05
✅ Resilience XML-RPC via @protected (Etape 2.4)                 - 01/05
✅ Reconciliation nocturne 4h (Niveau 4, Etape 2.5)              - 01/05
⏳ Webhooks natifs (Niveau 2) - en attente module OpenFire
   (Demande #2 envoyee 20/04, voir suivis_demandes_openfire.md)
🔵 Lifecycle Notifications (Niveau 3) : pas applicable Odoo
```

**Décisions actées :**

```
Q12 = On garde le polling existant + couche monitoring/réconciliation
Q12bis Odoo Community vs Enterprise = COMMUNITY confirme
  (sandbox safe_eval Odoo 16 Community bloque les imports Python
   dans base_automation, voir docs/demande_openfire_webhooks_temps_reel.md)
```

**Architecture implémentée Semaine 2 :**

```
NIVEAU 1 — Polling delta toutes les 2 min (DEJA EN PLACE depuis 20/04)
  API : XML-RPC Odoo
  Curseur : write_date par modele Odoo (stocke dans system_alerts)
  Couverture : 12 modeles actifs (sale.order, res.partner, etc.)
  62k records vectorises sans incident.

  AJOUT SEMAINE 2 :
    - register_connection() en debut de cycle (idempotent)
    - record_poll_attempt() en fin de cycle (status, items_seen, items_new)
    - @protected sur l appel XML-RPC (retry immediat sur micro-coupure)
    - status='ok' si <50% des modeles en erreur
    - status='internal_error' sinon

NIVEAU 2 — Webhooks natifs Odoo (CONDITIONNEL, en attente)
  Si OpenFire livre le module custom (Demande #2) :
    Configuration base.automation -> POST sur /webhook/odoo
    Reactivite ~30 sec au lieu de 2 min
    Activation : SCHEDULER_ODOO_POLLING_ENABLED=false dans Railway
    Pas de modif de code Raya supplementaire (endpoint deja pret)
  Sinon : on reste sur le polling pur (qui marche).

NIVEAU 3 — Lifecycle (PAS APPLICABLE)
  Pas de concept de subscription cote Odoo, donc rien a faire.

NIVEAU 4 — Reconciliation nocturne (NOUVEAU SEMAINE 2)
  Job a 4h du matin :
    Pour chaque modele POLLED_MODELS :
      count_odoo = search_count via API
      count_raya = COUNT DISTINCT(source_record_id) dans odoo_semantic_content
      Si delta_pct > 1% : alerte WARNING via alert_dispatcher
  Garantie de completude absolue : on detecte une fuite en max 24h.
```

**Couche monitoring/alerte ajoutée :**

```
Odoo apparait maintenant dans /admin/health/page comme les autres
connexions :
  - Pastille de couleur (vert healthy / rouge down / etc.)
  - last_successful_poll_at visible
  - silence en minutes
  - bouton Detail vers les 50 derniers events
  - alerte automatique si silence > 6 min
```

**Bénéfice immédiat :** si demain le polling Odoo plante (token, réseau,
crash), Guillaume sera prévenu pareil que pour les mails. Avant
Semaine 2, les pannes Odoo n etaient detectees que par hasard.

### 3.6 — WhatsApp (NOUVEAU PÉRIMÈTRE)

**Décisions actées :**

```
Q5 = Twilio WhatsApp (officiel Meta, multi-tenant, cohérent infra existante)
Q6 = Liste blanche manuelle (souveraineté utilisateur)
Q7 = Suggestions de réponses + validation manuelle TOUJOURS
ENRICHISSEMENT Q5 : abstraction provider (futur switch facile vers
                     MessageBird ou WhatsApp Cloud API direct)
ENRICHISSEMENT Q7 : la suggestion s'accompagne du raisonnement IA
```

**Architecture :**

```
NIVEAU 1 — Réception via webhook Twilio (pas de polling)
  Endpoint Raya : /webhook/twilio/whatsapp (déjà partiellement existant)
  Twilio envoie un webhook à chaque message reçu sur le numéro Raya.
  → Latence ~30 sec.

NIVEAU 2 — Liveness check par ping outbound
  Toutes les 15 min, Raya envoie un ping interne au numéro Raya
  (un message technique vers un compte test).
  Si pong reçu → connexion OK.
  Si pas de pong → alerte WARNING.

NIVEAU 3 — Pas de Lifecycle (Twilio n'a pas ce concept).
  À la place : monitoring du compte Twilio (solde, état de santé)
  via leur API quotidiennement.

NIVEAU 4 — Pas de réconciliation classique (pas d'API "donne-moi
  l'historique complet" côté Twilio). En revanche :
  • Tous les messages traités sont loggés
  • Si l'utilisateur signale "j'ai reçu un message que Raya n'a pas vu"
    → inspection manuelle du log Twilio
```

**Sélectivité (souveraineté utilisateur) :**

```
LISTE BLANCHE par contact ou groupe :
  L'utilisateur indique dans une UI Raya :
    "Indexer les messages de [Pierre Dupont]"
    "Indexer le groupe [Chantier Marseille]"
    "Ne PAS indexer les messages de [famille]"
  
  Stockage : tenant_whatsapp_whitelist (table)
  
  À la réception d'un message :
    Si expéditeur dans whitelist → indexer normalement
    Si expéditeur PAS dans whitelist → message reçu mais NON indexé,
      log technique seulement (pour le liveness check)
```

**Bidirectionnalité (écriture WhatsApp) :**

```
PRINCIPE : suggestion + validation manuelle TOUJOURS.

QUAND RAYA PROPOSE UNE RÉPONSE :
  Raya rédige la réponse complète + montre le RAISONNEMENT court :
    "Je propose : 'Bien noté, je passe demain matin vers 9h'
     Raisonnement : Pierre demande confirmation du RDV. Ton agenda
     a un créneau libre à 9h-11h demain matin (mardi)."
  
  L'utilisateur voit l'aperçu + raisonnement.
  3 actions possibles :
    • Envoyer en l'état (1 clic)
    • Modifier puis envoyer
    • Annuler

→ AUCUNE auto-réponse même pour les cas évidents.
→ Cohérent avec le principe de souveraineté.
```

**Abstraction provider (NOUVEAU - ENRICHISSEMENT Q5) :**

```
Le module WhatsApp expose une INTERFACE générique :

class WhatsAppProvider(ABC):
    def send_message(self, to, content) -> str
    def list_conversations(self) -> list
    def fetch_history(self, conversation_id, since) -> list
    def setup_webhook(self, callback_url) -> bool

Implémentations possibles (interchangeables) :
  • TwilioWhatsAppProvider     — choix actuel (Q5 = C)
  • MessageBirdWhatsAppProvider  — alternative ~50% moins cher
  • CloudAPIDirectProvider      — alternative gratuite (frais Meta seuls)

→ Permet de switcher de provider en changeant 1 ligne de config,
   sans réécrire le module WhatsApp.
→ Anti-lock-in technique.
```

### 3.7 — Vesta

**Statut actuel :** EN ATTENTE retour développeurs Vesta (Q11).

**Contexte (info Guillaume) :**

```
Vesta = outil de simulation photovoltaïque connecté il y a ~2 jours.

Cas d'usage cible (combine plusieurs connexions Raya) :
  1. RDV client noté à l'agenda Outlook
  2. Pendant le RDV : prise vocale du compte-rendu (audio Raya)
  3. Transcription automatique
  4. Import automatique des données dans Vesta

Blocage actuel : API Vesta limitées, certaines fonctions pas exposées.
Mail envoyé aux développeurs Vesta pour obtenir l'accès aux API
manquantes. EN ATTENTE.
```

**Architecture cible (à implémenter quand API ouvertes) :**

```
NIVEAU 1 — À déterminer selon les API offertes :
  • Si API REST avec endpoint "list updates since X" → polling delta
  • Si webhooks natifs Vesta → architecture mail-like
  • Si ni l'un ni l'autre → polling REST classique avec pagination

NIVEAUX 2-4 — Mêmes principes que les autres connexions
  Adaptation selon les capacités de l'API Vesta.

PARTICULARITÉS :
  Vesta est BIDIRECTIONNEL (Raya écrit aussi : import des CR de RDV).
  Validation utilisateur obligatoire avant écriture (cohérent Q7).
```

**Mise à jour 01/05/2026 — retour Maxime AMRAM (cofondateur Vesta) :**

```
Demande Guillaume du 28/04 :
  • Liste complète des projets (pas uniquement par customer_id)
  • Accès aux paramètres d'étude
  • Accès aux notes client
  • Écriture des fiches de visite technique (pente, couverture, 
    distances compteur, type compteur mono/tri, puissance, etc.)
  • Demande d'accès aux endpoints internes Vesta

Réponse Maxime du 01/05 :
  • REFUS d'exposer les endpoints internes 
    Raison : stabilité (pas envie de garantir des contrats sur des 
    endpoints qui peuvent évoluer côté Vesta)
  • CONFIRMATION qu'ils prévoient d'enrichir l'API publique existante
  • DÉLÉGATION au support Vesta pour réponse plus complète
    → On attend une 2e réponse, plus détaillée

Conséquence pour Raya :
  • Vesta reste bloqué côté Vesta — pas de chemin alternatif
  • Le scénario "visite technique vocale → import auto Vesta" est 
    toujours sur l'étagère, en attendant l'enrichissement de l'API 
    publique
  • Pas de timing communiqué par Maxime
  • Pas d'action Raya à mener tant que le support Vesta n'a pas 
    précisé quels endpoints seront ajoutés et quand

À faire quand le support Vesta aura répondu :
  1. Inventorier les nouveaux endpoints disponibles
  2. Vérifier si l'écriture des fiches visite technique est dans 
     le périmètre
  3. Si oui : reprendre la section 3.7 architecture cible
  4. Si non : laisser Vesta en attente prolongée et déprioriser
     le scénario "visite technique vocale" en conséquence
```

**Priorité dans la roadmap :**

```
À traiter en DERNIER, après que toutes les autres connexions soient
sur l'architecture commune. Vesta dépend d'un blocage externe (les
développeurs Vesta), donc on ne peut pas garantir le timing.
```

### 3.8 — Teams (préparé pour le futur)

**Statut :** pas encore connecté, mais l'architecture commune le supporte.

**Architecture cible :**

```
NIVEAU 1 — Polling delta via Microsoft Graph
  Endpoint : /chats/{id}/messages/delta (pour conversations 1-1 et groupes)
  Endpoint : /teams/{id}/channels/{id}/messages (pour canaux d'équipe)
  Cohérent avec mails Outlook (même API famille).

NIVEAU 2 — Webhook Microsoft Graph
  Subscription sur /chats/getAllMessages
  Mêmes principes que mails.

NIVEAUX 3-4 — Identique mails Outlook.
```

**Bidirectionnalité :**

```
Cohérent avec WhatsApp : suggestions + validation.
Particularité : on s'attend à beaucoup d'usage Teams pour les notifs
proactives sortantes (cf vision_proactivite_30avril.md, Niveau 2 des
canaux d'alerte).
```

---

## 🗄️ PARTIE 4 — Modèle de données

### Tables à créer

```sql
-- ═════════════════════════════════════════════════════════════
-- 1. connection_health
-- État de santé de chaque connexion (1 ligne par connexion)
-- ═════════════════════════════════════════════════════════════
CREATE TABLE connection_health (
  id SERIAL PRIMARY KEY,
  connection_id INT NOT NULL REFERENCES tenant_connections(id) ON DELETE CASCADE,
  tenant_id TEXT NOT NULL,
  username TEXT NOT NULL,
  connection_type TEXT NOT NULL,         -- 'mail_outlook', 'mail_gmail', 
                                          -- 'drive_sharepoint', 'odoo', 
                                          -- 'whatsapp', 'vesta', 'teams'
  status TEXT NOT NULL DEFAULT 'unknown', -- 'healthy' / 'degraded' / 'down' / 
                                          -- 'circuit_open' / 'unknown'
  last_successful_poll_at TIMESTAMP,
  last_poll_attempt_at TIMESTAMP,
  consecutive_failures INT DEFAULT 0,
  current_delta_token TEXT,              -- delta_link MS / historyId Gmail / 
                                          -- write_date Odoo / etc.
  expected_poll_interval_seconds INT,    -- 300 mails, 120 Odoo, etc.
  alert_threshold_seconds INT,           -- 3 × expected (par défaut)
  metadata JSONB DEFAULT '{}',           -- spécifique au type de connexion
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW(),
  UNIQUE(connection_id)
);
CREATE INDEX idx_health_status ON connection_health(status) 
  WHERE status != 'healthy';

-- ═════════════════════════════════════════════════════════════
-- 2. connection_health_events
-- Log de chaque tentative de poll (succès ET échec)
-- ═════════════════════════════════════════════════════════════
CREATE TABLE connection_health_events (
  id BIGSERIAL PRIMARY KEY,
  connection_id INT NOT NULL,
  poll_started_at TIMESTAMP NOT NULL,
  poll_ended_at TIMESTAMP,
  status TEXT NOT NULL,                  -- 'ok' / 'auth_error' / 
                                          -- 'network_error' / 'rate_limit' / 
                                          -- 'subscription_dead' / etc.
  items_seen INT DEFAULT 0,
  items_new INT DEFAULT 0,
  next_delta_token TEXT,
  duration_ms INT,
  error_detail TEXT,                     -- pour debug
  created_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_health_events_conn_time
  ON connection_health_events(connection_id, created_at DESC);
-- Partition possible plus tard par mois pour limiter la croissance.

-- ═════════════════════════════════════════════════════════════
-- 3. attachment_index
-- Index unifié de toutes les pièces jointes (mail) + fichiers (drive)
-- ═════════════════════════════════════════════════════════════
CREATE TABLE attachment_index (
  id BIGSERIAL PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  username TEXT NOT NULL,
  source_type TEXT NOT NULL,             -- 'mail_attachment' / 'drive_file'
  source_ref TEXT NOT NULL,              -- ID du mail ou du fichier
  connection_id INT,                     -- ref à la connexion d'origine
  file_name TEXT,
  file_size BIGINT,
  mime_type TEXT,
  text_content TEXT,                     -- extraction étape 1
  summary_content TEXT,                  -- résumé étape 3 (NULL si pas Vision)
  tags JSONB,                            -- {type_document, entites, confidence}
  embedding_global vector(1536),         -- pgvector, embedding du document
  vision_processed BOOLEAN DEFAULT false,
  deleted_at TIMESTAMP,                  -- soft delete si source supprimée
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW(),
  UNIQUE(source_type, source_ref)
);
CREATE INDEX idx_attachment_tenant ON attachment_index(tenant_id, deleted_at);
CREATE INDEX idx_attachment_tags ON attachment_index USING GIN(tags);

-- ═════════════════════════════════════════════════════════════
-- 4. attachment_chunks
-- Chunks vectorisés à granularité fine (paragraphes)
-- → Embeddings 2 niveaux (ENRICHISSEMENT Q14)
-- ═════════════════════════════════════════════════════════════
CREATE TABLE attachment_chunks (
  id BIGSERIAL PRIMARY KEY,
  attachment_id BIGINT NOT NULL REFERENCES attachment_index(id) ON DELETE CASCADE,
  chunk_index INT NOT NULL,              -- ordre dans le document
  content TEXT NOT NULL,
  embedding vector(1536),                -- embedding du paragraphe
  metadata JSONB,                        -- page, position, etc.
  created_at TIMESTAMP DEFAULT NOW(),
  UNIQUE(attachment_id, chunk_index)
);
CREATE INDEX idx_chunks_attachment ON attachment_chunks(attachment_id);

-- ═════════════════════════════════════════════════════════════
-- 5. tenant_drive_blacklist
-- Dossiers Drive/SharePoint exclus de l'indexation par tenant
-- ═════════════════════════════════════════════════════════════
CREATE TABLE tenant_drive_blacklist (
  id SERIAL PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  connection_id INT NOT NULL,
  folder_path TEXT NOT NULL,             -- '/Personnel', '/RH/Confidentiel'
  reason TEXT,                           -- 'rh_confidentiel', 'personnel', etc.
  created_by TEXT NOT NULL,              -- username qui a ajouté
  created_at TIMESTAMP DEFAULT NOW(),
  UNIQUE(connection_id, folder_path)
);

-- ═════════════════════════════════════════════════════════════
-- 6. tenant_whatsapp_whitelist
-- Conversations WhatsApp autorisées à l'indexation
-- ═════════════════════════════════════════════════════════════
CREATE TABLE tenant_whatsapp_whitelist (
  id SERIAL PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  connection_id INT NOT NULL,
  conversation_type TEXT NOT NULL,       -- 'contact' / 'group'
  conversation_id TEXT NOT NULL,         -- numéro ou group_id WhatsApp
  conversation_label TEXT,               -- nom affiché (Pierre Dupont, 
                                          -- Chantier Marseille)
  created_by TEXT NOT NULL,
  created_at TIMESTAMP DEFAULT NOW(),
  UNIQUE(connection_id, conversation_id)
);

-- ═════════════════════════════════════════════════════════════
-- 7. tenant_attachment_rules
-- Règles métier paramétrables par tenant pour la couche compréhension
-- → Cohérent note Guillaume Q13 (règles génériques + métier paramétrable)
-- ═════════════════════════════════════════════════════════════
CREATE TABLE tenant_attachment_rules (
  id SERIAL PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  rule_name TEXT NOT NULL,               -- 'forcer_vision_si_devis_solaire'
  rule_pattern TEXT,                     -- regex sur nom de fichier
  rule_action TEXT NOT NULL,             -- 'force_vision' / 'skip_vision' / 
                                          -- 'force_summary'
  rule_priority INT DEFAULT 0,           -- ordre d'évaluation
  enabled BOOLEAN DEFAULT true,
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW()
);
```

### Modifications de tables existantes

```sql
-- mail_memory : pas de modification structurelle. Le delta sync écrit
-- dans la même table. Champs supplémentaires éventuels (mailbox_source, 
-- direction in/out) déjà en place.

-- gmail_tokens : à supprimer après migration vers tenant_connections 
-- (déjà acté dans audit_connexions_invisibles_30avril.md, D3=A).

-- webhook_subscriptions : peut être conservée pour Niveau 2 (webhook 
-- accélérateur) mais devient OPTIONNELLE. L'app fonctionne sans 
-- subscription active grâce au polling delta du Niveau 1.

-- tenant_connections : ajouter colonne 'connection_type' si elle n'existe 
-- pas encore (alignée avec les types de connection_health.connection_type).
```

### Vue d'ensemble des données générées

```
INGESTION D'UN MAIL ET SA PIÈCE JOINTE FACTURE
─────────────────────────────────────────────────

1. mail_memory                       ← le mail lui-même
2. semantic_graph_nodes              ← nœud du mail
3. attachment_index                  ← la PJ facture
4. attachment_chunks                 ← chunks vectorisés de la facture
5. semantic_graph_nodes              ← nœud de la PJ
6. semantic_graph_nodes              ← nœud "Fournisseur Enedis" (entité)
7. semantic_graph_edges              ← mail → PJ
8. semantic_graph_edges              ← PJ → Fournisseur Enedis
9. semantic_graph_edges              ← PJ → Montant 1247€
10. connection_health_events         ← log "ok, items_new=1"
11. connection_health                ← updated_at + last_successful_poll_at

EXPOSITION DE L'ÉVÉNEMENT MÉTIER (pour module compta) :
  emit_event('attachment.invoice_detected', {
    'tenant_id': 'couffrant_solar',
    'attachment_id': 12847,
    'amount': 1247.00,
    'supplier_name': 'Enedis',
    'invoice_date': '2026-04-28',
    'mail_id': 949,
  })
  
→ Le module accounting_engine s'y abonne et ROUTE selon le paramétrage
   du tenant (Drive perso, SharePoint dossier X, Odoo, etc.).
→ Le module connexion mail ne fait JAMAIS de routage métier.
```

---

## 🚀 PARTIE 5 — Plan de migration et roadmap

### Approche : Foundations first (décision Q18)

Construire d'abord les **modules communs**, puis brancher chaque
connecteur dessus. Chaque connecteur bénéficie alors immédiatement
de tout le filet de sécurité.

### Roadmap sur 6 semaines

```
═══════════════════════════════════════════════════════════════════
SEMAINE 1 — MODULES COMMUNS (foundations)
═══════════════════════════════════════════════════════════════════

Livrables :
  ★ Module connection_health
    - Tables connection_health + connection_health_events
    - API record_poll_attempt, check_all_connections, get_status_summary
    - Job de monitoring toutes les 1 min
  
  ★ Module connection_resilience
    - Décorateur @protected avec retry / backoff / auto-refresh / circuit
    - Pattern circuit breaker (états fermé / demi-ouvert / ouvert)
    - Logging dans connection_health_events
  
  ★ Module alert_dispatcher
    - 5 niveaux (info, warning, attention, critical, blocking)
    - Multi-canaux (Twilio SMS/Voice, email SMTP, push Flutter, 
      chat in-app, Teams)
    - Configuration par défaut + override par utilisateur
    - Auto-escalade après timeout
  
  ★ Page admin /admin/health
    - Vue couleur de toutes les connexions
    - Détail des derniers events par connexion
    - Bouton "forcer un poll maintenant"

  ★ Couche compréhension de contenu (préparation)
    - Tables attachment_index + attachment_chunks
    - Pipeline extraction texte (toutes formats)
    - Pipeline triage 2a + 2b (règles + embeddings) + 2c (Haiku)
    - Pipeline Vision IA via Anthropic Files API
    - Logique embeddings 2 niveaux
    - Tests unitaires sur chacune des étapes

Validation Semaine 1 :
  • /admin/health affiche les connexions actuelles (Outlook, Gmail, 
    Drive, Odoo) en mode "monitoring read-only"
  • Aucune connexion existante n'est modifiée à ce stade
  • Tests unitaires passent
  
Déploiement : Railway, branche main (comme d'habitude)

═══════════════════════════════════════════════════════════════════
SEMAINE 2 — ODOO (faible risque, montée en confiance)
═══════════════════════════════════════════════════════════════════

Pourquoi Odoo en premier : la connexion existante est stable (62k 
records, pas d'incident). Ajouter le monitoring sans toucher au 
polling = risque minimal, confiance maximale dans les modules communs.

Livrables :
  ★ Branchement de odoo_polling.py sur connection_health
    - record_poll_attempt à chaque cycle
    - record du delta_token (write_date par modèle)
  
  ★ Décoration des appels XML-RPC avec @resilience.protected
  
  ★ Job de réconciliation nocturne Odoo
    - Compare count_odoo vs count_raya par modèle
    - Alerte WARNING si delta > 1%
  
  ★ Trancher : Odoo Enterprise ou Community ?
    - Si Enterprise : configurer base.automation pour webhooks → Niveau 2
    - Si Community : on reste polling pur (déjà le cas)

Validation Semaine 2 :
  • /admin/health affiche Odoo en vert, avec poll réussi tous les 2 min
  • Test manuel : couper le réseau Odoo 5 min → alerte WARNING émise
  • Test manuel : couper le réseau Odoo 30 min → alerte CRITICAL émise
  • Réconciliation nocturne tourne, pas de fausse alerte

═══════════════════════════════════════════════════════════════════
SEMAINE 3 — MAIL OUTLOOK (refonte delta sync)
═══════════════════════════════════════════════════════════════════

Le gros morceau : remplacer l'architecture webhook actuelle (fragile)
par delta sync universel.

Livrables :
  ★ Nouveau module mail_outlook_delta_sync.py
    - Polling delta toutes les 5 min sur Inbox + Sent + Junk + custom folders
    - Récupération des modifications (lu, déplacé, supprimé)
    - Stockage delta_link par folder dans connection_health.current_delta_token
  
  ★ Webhook accélérateur (refonte du webhook existant)
    - Plus de fetch direct du mail dans le webhook
    - Le webhook ne fait QUE déclencher poll delta immédiat
    - Beaucoup plus simple, beaucoup plus stable
  
  ★ Lifecycle Notifications (NOUVEAU)
    - Subscription incluant lifecycleNotificationUrl
    - Handler des événements subscriptionRemoved, missed, reauthorizationRequired
    - Auto-recréation de subscription
  
  ★ Réconciliation nocturne mail
    - Count Microsoft vs count mail_memory par boîte
    - Alerte WARNING si delta
  
  ★ Coexistence courte avec l'ancien système (24-48h max)
    - Les deux tournent en parallèle
    - On compare ce qui arrive dans mail_memory : doit être identique
    - Une fois validé → on supprime l'ancien code webhook

Validation Semaine 3 :
  • Boîte Outlook Guillaume : zéro mail manqué pendant 7 jours de test
  • Test manuel : couper la subscription Microsoft de force → 
    Lifecycle Notification reçue → recréation auto → reprise sans incident
  • /admin/health : Outlook vert en permanence
  • Mails sortants détectés (avant : invisibles)
  • Mails déplacés vers dossiers custom détectés (avant : invisibles)

═══════════════════════════════════════════════════════════════════
SEMAINE 4 — MAIL GMAIL (refonte similaire)
═══════════════════════════════════════════════════════════════════

Symétrique de la Semaine 3 mais pour Gmail.

Livrables :
  ★ Nouveau module mail_gmail_history_sync.py
    - Polling history toutes les 5 min via History API
    - Stockage startHistoryId par boîte
    - Multi-boîtes (Guillaume a 6 Gmail)
  
  ★ Setup Pub/Sub Watch sur Google Cloud (Niveau 2 webhook)
    - Topic Pub/Sub
    - Push subscription vers /webhook/gmail
    - Watch renouvelée tous les 6 jours par job nocturne
  
  ★ Réconciliation nocturne Gmail
  
  ★ Décommissionnement de gmail_polling.py legacy

Validation Semaine 4 :
  • Les 6 boîtes Gmail Guillaume + boîte Charlotte : zéro mail manqué
  • Test manuel : laisser expirer le watch Gmail → renew automatique
  • Coexistence courte avec l'ancien système puis suppression

═══════════════════════════════════════════════════════════════════
SEMAINE 5 — DRIVE / SHAREPOINT
═══════════════════════════════════════════════════════════════════

Livrables :
  ★ Nouveau module drive_delta_sync.py
    - Polling Drive Delta toutes les 5 min
    - Webhook accélérateur Microsoft Graph sur /drives/{id}/root
    - Lifecycle Notifications
  
  ★ Pipeline complet de compréhension de contenu
    - Application de la couche commune (extraction → triage → Vision)
    - Stockage dans attachment_index avec embedding 2 niveaux
    - Mise à jour graphe sémantique
  
  ★ Système de blacklist
    - Table tenant_drive_blacklist
    - UI dans /admin/panel pour gérer les exclusions
    - Respect Sensitivity Labels Microsoft Purview (auto-exclusion)
  
  ★ Réconciliation nocturne Drive
  
  ★ Pour Couffrant Solar : ré-onboarding propre
    - Reprendre la connexion à la racine du SharePoint
    - Définir la blacklist initiale avec Guillaume
    - Job d'onboarding historique : indexer TOUT (pas de limite de 
      profondeur pour Guillaume)

Validation Semaine 5 :
  • /admin/health : Drive vert en permanence
  • Toutes les modifications de fichiers détectées en < 6 min
  • Modèles factures correctement compris par Vision IA
  • Embeddings 2 niveaux fonctionnels (recherche fine ET large)

═══════════════════════════════════════════════════════════════════
SEMAINE 6 — WHATSAPP
═══════════════════════════════════════════════════════════════════

Connexion la plus nouvelle, la plus complexe juridiquement, donc 
en dernier (équipe a déjà fait ses armes sur les autres).

Livrables :
  ★ Module whatsapp_connector
    - Abstraction WhatsAppProvider (interface)
    - Implémentation TwilioWhatsAppProvider
    - Réception via webhook /webhook/twilio/whatsapp
    - Liveness check par ping outbound toutes les 15 min
  
  ★ Système de whitelist conversations
    - Table tenant_whatsapp_whitelist
    - UI dans Raya pour gérer les conversations indexées
  
  ★ Bidirectionnalité avec validation
    - Endpoint pour proposer un message à Raya
    - UI de validation avec raisonnement IA visible
    - 3 actions : envoyer / modifier / annuler
  
  ★ Indexation : couche compréhension de contenu sur les pièces 
    jointes WhatsApp (photos chantier, voicemails à transcrire, etc.)

Validation Semaine 6 :
  • Test sur 2-3 conversations whitelistées de Guillaume
  • Réception : 100% des messages indexés
  • Envoi : 0 message envoyé sans validation
  • Conversations non whitelistées : aucune indexation

═══════════════════════════════════════════════════════════════════
SUITE (au-delà de Semaine 6, hors planning précis)
═══════════════════════════════════════════════════════════════════

★ Vesta : à intégrer quand les API seront ouvertes par les 
  développeurs Vesta (statut bloquant externe)

★ Teams : à intégrer quand un cas d'usage clair sera défini 
  (probablement dans le cadre du chantier proactivité, voir 
  vision_proactivite_30avril.md)

★ Audio (transcription des notes vocales) : pourrait être considéré 
  comme une "connexion" à part entière (ingestion audio → texte)
```

### Coexistence et tests

```
PROTOCOLE DE BASCULE PROPRE (pour mail Outlook, mail Gmail, Drive)

1. Démarrage : ancien et nouveau systèmes tournent en parallèle 
   pendant 24-48h.

2. Comparaison automatique :
   • Tous les 30 min, comparer les nouveaux records ingérés par 
     l'ancien vs le nouveau
   • Si différence : enquête immédiate

3. Période d'observation : 7 jours minimum

4. Décision de bascule :
   • Si nouveau ≥ ancien (au moins autant de mails) : bascule
   • Si nouveau < ancien : garder l'ancien, debug le nouveau

5. Bascule :
   • Désactivation du job ancien
   • Suppression du code ancien (commit dédié, pas mélangé avec 
     le nouveau code)

→ Pas de staging environment dans cette phase (pas encore 
  d'utilisateurs externes, décision Guillaume Q12 contexte). 
  La sécurité vient de la coexistence + comparaison.
```

### Mise en place du staging (déclencheur futur)

```
RÈGLE GUILLAUME (captée Q12) :

Phase actuelle (tests internes uniquement)
  → Pas de staging nécessaire, dev direct sur main acceptable

Dès passage en utilisateurs tests réels (1er user externe)
  → Mise en place obligatoire d'un environnement bêta/staging
  → Workflow : dev sur staging → validation → bascule en prod 
    en pleine nuit (heure précise pour minimiser impact)
  → Archive ou écrasement de l'ancienne version

→ À traiter comme un mini-chantier dédié quand le déclencheur 
  arrive, pas dans la roadmap actuelle.
```

---

## 📎 PARTIE 6 — Décisions Guillaume tracées

Toutes les décisions actées pendant la session du 01/05/2026 (10h-12h),
avec contexte et justification.

```
═══════════════════════════════════════════════════════════════════
D1 — Architecture cible mails (Q1)
═══════════════════════════════════════════════════════════════════
Décision : Polling delta + webhook accélérateur
Pourquoi : "Pour la réactivité et la proactivité, c'est indispensable."
Conséquence : webhook devient un BONUS, plus un point de défaillance 
critique. Si webhook plante, polling rattrape en max 5 min.

═══════════════════════════════════════════════════════════════════
D2 — Profondeur d'onboarding par défaut (Q2 cadrage)
═══════════════════════════════════════════════════════════════════
Décision : 12 mois par défaut pour les futurs clients, TOUT pour 
            Guillaume.
Pourquoi : "Pour mon cas, on fera tout. Je veux que Raya ait les 
           contextes même les plus anciens, pour comprendre des 
           choses. Donc il lui faut l'ensemble des données."
Conséquence : UI choix de profondeur à la connexion, avec preset 
"tout l'historique" pour le tenant Guillaume.

═══════════════════════════════════════════════════════════════════
D3 — Sort des fixes du matin (Q3 cadrage)
═══════════════════════════════════════════════════════════════════
Décision : On garde les 4 commits du matin (0f371ef, 19b0ac4, 063bd47).
Pourquoi : "On s'en fout, ça va sauter."
Conséquence : pas de revert, pas de friction. Les fixes tiennent les 
mails en attendant la refonte. À supprimer proprement quand on 
remplacera les modules concernés.

═══════════════════════════════════════════════════════════════════
D4 — Document avant code (Q4 cadrage)
═══════════════════════════════════════════════════════════════════
Décision : Documenter la vision AVANT de coder, TOUJOURS.
Pourquoi : "Oui, on documente tout TOUJOURS. Un suivi propre pour 
           un projet et un résultat propre."
Conséquence : ce document existe avant la première ligne de code 
de la Phase B. Aucun code ne sera écrit avant validation finale du 
doc par Guillaume.

═══════════════════════════════════════════════════════════════════
Q1 — Polling delta + webhook accélérateur (mails)
═══════════════════════════════════════════════════════════════════
Décision : 🅐
Justification : réactivité indispensable + filet de sécurité du 
polling.

═══════════════════════════════════════════════════════════════════
Q2 — Pièces jointes : niveau de compréhension
═══════════════════════════════════════════════════════════════════
Décision : 🅑 — texte par défaut + Vision IA si triage juge important
Pourquoi : "Effectivement, ça ne sert à rien d'interroger l'IA pour 
           analyser une notification LinkedIn."
Conséquence : pipeline triage en cascade (règles génériques → 
embeddings → Haiku) avant tout appel Vision.

═══════════════════════════════════════════════════════════════════
Q3 — Routage automatique des factures
═══════════════════════════════════════════════════════════════════
Décision : ÉCARTÉE — c'est du paramétrage compta, pas du module 
            connexion.
Pourquoi : "Pour moi, c'est plus le paramétrage du bloc comptabilité. 
           Là, je suis en train de mélanger 2 choses. La gestion 
           des mails, l'identification d'une facture, et ensuite on 
           traitera dans la partie comptabilité pour le classement 
           et où est-ce que ça va."
Conséquence : SÉPARATION STRICTE des responsabilités. Le module 
connexion mail expose un événement structuré ("ceci est une facture, 
montant X, fournisseur Y"). Le module compta (à venir) décide où 
ça va selon le paramétrage du tenant.

═══════════════════════════════════════════════════════════════════
Q4 — Tagging des pièces jointes
═══════════════════════════════════════════════════════════════════
Décision : 🅑 — tags auto + validation premières semaines, autonome 
            ensuite
Pourquoi : "Il faut que pendant les premières semaines, elle puisse 
           demander validation si elle n'est pas sûre. Mais attention, 
           il ne faut pas qu'elle pose 3000 questions pour des choses 
           évidentes. Il faut qu'elle reste assez autonome. Quand 
           il y a un doute raisonnable, qu'elle peut interroger son 
           utilisateur."
Conséquence : implémentation Active Learning + seuil de confiance 
dynamique (cf ENRICHISSEMENT Q4). Raya pose une question UNIQUEMENT 
sur les cas à faible confiance, et le seuil descend avec le temps.

═══════════════════════════════════════════════════════════════════
Q5 — API WhatsApp
═══════════════════════════════════════════════════════════════════
Décision : 🅒 — Twilio WhatsApp
Pourquoi : "Si c'est légal, on part sur le C. Cohérent avec stack 
           Twilio existant. Et il faut que les clients aussi puissent 
           avoir un service WhatsApp."
Conséquence : multi-tenant via numéros Twilio dédiés par client. 
Abstraction provider implémentée pour permettre un switch futur 
(MessageBird, WhatsApp Cloud direct).

═══════════════════════════════════════════════════════════════════
Q6 — Sélectivité WhatsApp
═══════════════════════════════════════════════════════════════════
Décision : 🅐 — liste blanche manuelle
Pourquoi : "C'est l'utilisateur qui dit à Raya sur quelle conversation 
           avoir accès."
Conséquence : table tenant_whatsapp_whitelist, UI de gestion. 
Cohérent avec le principe de souveraineté utilisateur.

═══════════════════════════════════════════════════════════════════
Q7 — Bidirectionnalité WhatsApp
═══════════════════════════════════════════════════════════════════
Décision : 🅒 — suggestions + validation manuelle TOUJOURS
Pourquoi : "Toujours une validation."
Conséquence : aucune auto-réponse, même pour les cas évidents. 
La suggestion s'accompagne du raisonnement IA (ENRICHISSEMENT Q7) 
pour permettre une validation rapide en confiance.

═══════════════════════════════════════════════════════════════════
Q8 — Périmètre Drive
═══════════════════════════════════════════════════════════════════
Décision : 🅒 — tout par défaut + blacklist par dossiers
Pourquoi : "Il faut donner accès à l'ensemble des données mais 
           effectivement pouvoir également blacklister certains 
           dossiers pour que Raya ne les voit pas si l'utilisateur 
           le souhaite."
Conséquence : table tenant_drive_blacklist + UI. ENRICHISSEMENT Q8 
ajouté : respect automatique des Sensitivity Labels Microsoft Purview 
comme filet de sécurité supplémentaire.
Action post-implémentation : ré-onboarding propre du SharePoint 
Couffrant Solar (actuellement limité au seul dossier 'photovoltaïque' 
test).

═══════════════════════════════════════════════════════════════════
Q9 — Fréquence Drive
═══════════════════════════════════════════════════════════════════
Décision : 🅐 — delta query 5 min + webhook accélérateur 
            (ENRICHISSEMENT Q9)
Pourquoi : "Cohérent avec mails. 5 min c'est bien."
Conséquence : "Devis modifié à 14h pour réunion à 16h" capté en 
~30 sec via webhook.

═══════════════════════════════════════════════════════════════════
Q10 — Compréhension fichiers Drive
═══════════════════════════════════════════════════════════════════
Décision : 🅐 — même logique que pièces jointes mail
Pourquoi : "Évidemment. Tout doit être en graphe vectorisé pour 
           être trouvable."
Conséquence : mutualisation totale du pipeline de compréhension 
entre PJ mail et fichiers Drive (un seul code à maintenir).

═══════════════════════════════════════════════════════════════════
Q11 — Vesta (informationnelle)
═══════════════════════════════════════════════════════════════════
Statut : EN ATTENTE retour développeurs Vesta.
Contexte : outil de simulation photovoltaïque connecté il y a 
            ~2 jours. API limitées actuellement.
Cas d'usage cible : RDV agenda → prise vocale → transcription → 
                    import auto dans Vesta.
Roadmap : à traiter en DERNIER (statut bloquant externe).

═══════════════════════════════════════════════════════════════════
Q12 — Sort d'Odoo
═══════════════════════════════════════════════════════════════════
Décision : 🅒 — on garde le polling existant + couche monitoring/
            réconciliation
Pourquoi : Guillaume s'interrogeait sur 🅑 (refonte complète). 
           Claude a recommandé 🅒 car le polling actuel est 
           STABLE (62k records sans incident, déjà delta sync via 
           write_date). La refonte serait "casser pour casser".
Question ouverte : Odoo Community ou Enterprise ? Probablement 
Enterprise (Guillaume pas sûr). À trancher en début de Semaine 2 
de la roadmap. Si Enterprise → activer webhooks natifs (Niveau 2).

Sous-décision (staging) :
  Pour la phase actuelle (tests internes), on continue sur main.
  Dès passage en utilisateurs tests externes, mise en place d'un 
  environnement staging avec bascule en pleine nuit.

═══════════════════════════════════════════════════════════════════
Q13 — Stratégie LLM Vision
═══════════════════════════════════════════════════════════════════
Décision : 🅒 — règles génériques + IA en doute
Note critique Guillaume : "Il faut faire attention à ne pas être 
restrictif. Les règles doivent être ÉQUILIBRÉES et GÉNÉRIQUES, pas 
spécifiques au métier de Couffrant. Pour un autre client (commerçant, 
artisan, consultant), les 'documents importants' seront différents."
Conséquence : règles 2a génériques (commercial, contractuel, image 
métier, fichier codé). Règles métier paramétrables par tenant via 
tenant_attachment_rules. Plus pré-filtrage par embeddings (ENRICHISSEMENT 
Q13) intégré dès le début (pas reporté en "futur").

═══════════════════════════════════════════════════════════════════
Q14 — Stockage du résultat de Vision
═══════════════════════════════════════════════════════════════════
Décision : 🅒 — texte + résumé + tags structurés
ENRICHISSEMENT Q14 : embeddings à 2 niveaux (chunk + document).
Conséquence : maximum d'exploitabilité dès l'ingestion. Recherche 
fine ET large optimisées. Alimentation du graphe sémantique avec 
des arêtes structurées.

═══════════════════════════════════════════════════════════════════
Q15 — Définition d'une anomalie ⭐
═══════════════════════════════════════════════════════════════════
Décision : 🅓 — Liveness check (différencier silence technique 
            vs absence de nouveauté)
Insight Guillaume : "Si on met une durée, on va avoir forcément 
des pertes. Existe-t-il une possibilité qu'on ait un retour disant 
'il n'y a pas de changement, mais l'interrogation a bien été faite' ? 
Pour qu'on puisse détecter la différence entre ça et 'on interroge 
mais on n'a pas de retour'."
Conséquence : pattern industriel STANDARD adopté (utilisé par Stripe, 
Datadog, AWS). ZÉRO faux positif. Indépendant des horaires métier.
Note méthodologique : Guillaume a poussé Claude à creuser au-delà 
des solutions médiocres. Principe acté pour la suite.

═══════════════════════════════════════════════════════════════════
Q16 — Canaux d'alerte
═══════════════════════════════════════════════════════════════════
Décision : 🅒 — 5 niveaux multi-canaux + paramétrable
Conséquence : module alert_dispatcher avec valeurs par défaut + 
override utilisateur. Twilio déjà configuré → SMS et appels = 
quasi gratuit à activer.

═══════════════════════════════════════════════════════════════════
Q17 — Auto-récupération
═══════════════════════════════════════════════════════════════════
Décision : 🅒 — Self-healing 4 étapes + circuit breaker
Note Guillaume : "Réutilisable dans l'ensemble des connexions 
                 où c'est possible."
Conséquence : module connection_resilience commun, hérité par 
tous les connecteurs.

═══════════════════════════════════════════════════════════════════
Q18 — Stratégie de migration
═══════════════════════════════════════════════════════════════════
Décision : 🅐 — Foundations first
Pourquoi : "On n'est pas à quelques jours. Mieux vaut une refonte 
           propre et solide qu'un patch fragile."
Pour la branche Git : "On fait comme d'habitude" → main directement.
Conséquence : Semaine 1 dédiée aux modules communs avant tout 
branchement de connecteur. Coexistence courte ancien/nouveau pour 
chaque connecteur lors de sa refonte.

═══════════════════════════════════════════════════════════════════
PRINCIPE MÉTHODOLOGIQUE ACTÉ
═══════════════════════════════════════════════════════════════════
Reproche Guillaume sur Q15 (capté pour la suite du projet) :

"Quand il y a des questions un peu sensibles sur des solutions 
techniques à apporter, j'attends que tu creuses pour me proposer 
des solutions techniques dont je n'ai pas connaissance. C'est toi 
qui connais ces choses-là. Tu peux facilement avoir accès à 
l'ensemble des possibilités de résolution. Donc j'aimerais que 
tu arrives à me proposer des choses comme ça quand elles existent. 
Pas la plus simple sur le moment et puis ensuite on verra comment 
on améliore."

PRINCIPE :
  Guillaume : décide de la VISION et du résultat attendu
  Claude    : apporte les MEILLEURES solutions techniques connues 
              (industrie, patterns, standards), justifie, recommande
  Guillaume reste l'arbitre final sur les compromis 
  (coût/complexité/délai), mais Claude doit faire le travail de 
  recherche EN AMONT.

ET COROLLAIRE :
"Tu as souvent mis 'améliorations possibles dans futur', mais j'ai 
plutôt tendance à vouloir me dire 'on fait bien tout de suite'. 
Donc note-le dans le document, on fait les choses bien tout de suite."

→ Toutes les optimisations identifiées dans l'audit sont intégrées 
   au chantier de départ, pas en "futur".

═══════════════════════════════════════════════════════════════════
ENRICHISSEMENTS TECHNIQUES INTÉGRÉS DÈS LE DÉPART
═══════════════════════════════════════════════════════════════════

Tous issus de l'audit "ai-je bien creusé les standards ?" demandé 
par Guillaume après les 14 premières questions.

E1 — Lifecycle Notifications Microsoft (sur Q1 et Q9)
     Microsoft envoie des événements PUSH quand une subscription 
     va mourir (subscriptionRemoved, missed, reauthorizationRequired). 
     Évite les silences silencieux comme les 17 jours d'avril.

E2 — Anthropic Files API (sur Q2)
     Upload une fois, analyse plusieurs fois (texte + résumé + tags). 
     Économie ~30% sur les coûts Vision IA pour les multi-analyses.

E3 — Active Learning + seuil de confiance dynamique (sur Q4)
     Mécanisme technique pour le "doute raisonnable" demandé par 
     Guillaume. Raya pose des questions UNIQUEMENT sur les cas à 
     faible confiance, et le seuil baisse avec le temps.

E4 — Abstraction provider WhatsApp (sur Q5)
     Interface WhatsAppProvider pour switcher facilement de 
     fournisseur (Twilio → MessageBird → Cloud API direct) sans 
     réécrire le module. Anti-lock-in.

E5 — Suggestion + raisonnement IA visible (sur Q7)
     Quand Raya propose un message WhatsApp, elle montre POURQUOI. 
     Permet une validation utilisateur en 2 secondes en confiance.

E6 — Sensitivity Labels Microsoft Purview (sur Q8)
     Filet de sécurité automatique : un dossier marqué "Confidentiel" 
     par Microsoft Purview est exclu automatiquement de l'indexation, 
     même si l'utilisateur a oublié de le blacklister.

E7 — Webhook accélérateur Drive (sur Q9)
     Cohérent avec architecture mails. Réactivité ~30 sec sur les 
     modifications de fichiers (au lieu de 5 min).

E8 — Pré-filtrage par embeddings (sur Q13)
     Étape 2b dans le pipeline triage. 100x moins cher que LLM. 
     Réduit le nombre d'appels Haiku → réduit le coût total.

E9 — Embeddings 2 niveaux chunk + document (sur Q14)
     Recherche fine ("phrase qui mentionne 9 kWc") ET large ("tous 
     les devis solaires"). Cohérent avec GraphRAG hiérarchique 
     mentionné dans la vision long terme.
```

---

## 🔮 PARTIE 7 — Évolutions futures envisagées

Pas dans la roadmap des 6 semaines, mais à garder en tête pour 
l'architecture (pas de mauvais choix qui empêcheraient ces évolutions).

### E1 — Connexions audio (transcription notes vocales)

Cas d'usage déjà identifié dans le scénario Vesta : RDV chez le 
client, prise vocale du compte-rendu, transcription auto. À traiter 
comme une "connexion" à part entière (ingestion audio → texte → 
graphe).

### E2 — Connexions calendar avancées

Calendrier Outlook déjà partiellement utilisé. À l'avenir :
  • Capture des modifications de RDV
  • Reconnaissance des participants externes (lien vers contacts)
  • Géolocalisation pour les RDV terrain (chantiers)

### E3 — Connexions bancaires

Le module compta documenté dans `vision_compta_30avril.md` mentionne 
l'ingestion bancaire. À l'avenir :
  • API ouverte (DSP2 / Bridge / Tink)
  • Application des mêmes principes (delta sync, monitoring, alertes)
  • Particularité : sécurité accrue (chiffrement supplémentaire des 
    tokens bancaires)

### E4 — Notifications proactives sortantes

Pas une "connexion" au sens lecture, mais cohérent avec le sujet : 
Raya envoie des notifications proactives via les mêmes canaux 
(Teams, WhatsApp, SMS). L'architecture alert_dispatcher (Module 3) 
sert AUSSI à ce besoin. Voir `vision_proactivite_30avril.md`.

### E5 — Migration vers GraphRAG hiérarchique

Vision documentée dans `vision_proactivite_30avril.md` et 
`vision_compta_30avril.md`. Quand le graphe sera plus dense (>1M 
nœuds par tenant), on basculera vers une indexation hiérarchique 
pour optimiser les requêtes. Les embeddings 2 niveaux (E9) sont 
compatibles avec cette évolution.

### E6 — IA multimodale future (vidéo, son contextuel)

Photos chantier déjà gérées par Vision IA. À l'avenir :
  • Vidéos courtes (vidéos de site)
  • Reconnaissance audio dans les fichiers (notes vocales en direct)
  • Cohérent avec la stratégie "LLM swappable" : quand Sonnet 5 
    sortira avec ces capacités, swap en 1 ligne.

### E7 — Connexions ERP autres qu'Odoo

Vesta est déjà un cas particulier. À l'avenir, Raya doit pouvoir 
se connecter à d'autres ERP/CRM (SAP, Hubspot, Salesforce, etc.). 
L'architecture commune (3 modules + delta sync universel) supporte 
ça nativement. Chaque ERP devient juste un nouveau connecteur qui 
hérite des modules communs.

---

## 📌 Conclusion

Ce document est la **référence architecturale de TOUTES les 
connexions Raya**, présentes et futures. Toute évolution future 
de connexions devra :

```
1. Respecter les 7 piliers (Partie 1)
2. Hériter des 3 modules communs (Partie 2)
3. Suivre le pattern delta sync universel (Partie 2)
4. Utiliser la couche compréhension de contenu commune (Partie 2)
5. Respecter le modèle de données (Partie 4)
6. Être validée par un test de coexistence avant bascule (Partie 5)
```

### Ce que ce document garantit

```
✅ Pas de patch sur patch — architecture commune cohérente
✅ Pas d'angle mort — 7 piliers couvrent tous les besoins identifiés
✅ Pas de fragilité — self-healing + monitoring universels
✅ Pas de surprise — toutes les décisions tracées avec justification
✅ Pas de dette technique — les enrichissements sont intégrés dès 
   le départ, pas reportés
✅ Évolutivité — le pattern supporte de nouvelles connexions sans 
   refonte
```

### Prochaine étape concrète

```
1. Validation finale de ce document par Guillaume
2. Démarrage Semaine 1 — Modules communs (foundations)
3. Création des tables (DDL Partie 4)
4. Implémentation et tests
5. Branchement progressif des connexions Semaines 2-6
```

---

## 📌 ADDENDUM 01/05 SOIR — Scan de rattrapage et onboarding historique

**Statut :** non implémenté — à faire après Semaine 4 (Gmail), avant
mise en usage productif par Guillaume.

### Le besoin

Demande Guillaume (1er mai vers 16h, après validation Semaine 3
en prod) :

> "Une fois que tout ça marche, faire un scan de mes boîtes mail pour
> mettre en graphe tous les mails qui sont passés au travers pendant
> les pauses, les pannes de mises à jour, ou alors les historiques
> plus anciens. Il faudra prévoir de mettre ça au propre avant que
> je l'utilise correctement."

### Pourquoi c'est nécessaire

Le polling delta (Niveau 1 du pattern delta sync) garantit la
complétude FUTURE, mais pas la complétude PASSEE. Concrètement :

```
PERIODE A RATTRAPER :
  Bug 17 jours : 14/04 -> 01/05
  Pendant cette periode, le webhook plantait silencieusement.
  Le polling delta n existait pas encore.
  Microsoft retient ~30 jours de delta_history par defaut, donc
  on peut PARTIELLEMENT rattraper via le delta_link initial, mais
  pas garanti.

HISTORIQUES PLUS ANCIENS :
  Mails de 2024, 2025, etc. potentiellement non indexes ou
  partiellement indexes selon les versions du connecteur a l epoque.

PAUSES FUTURES :
  Maintenance Railway, redeploys longs, panne ponctuelle, etc.
  Le filet de reconciliation (Niveau 4) detecte en 24h, mais le
  rattrapage automatique n est pas implemente.
```

### Architecture cible

#### 1. Scan de rattrapage (post-incident, ad-hoc)

```
ENDPOINT /admin/sync/{connection_type}/{connection_id}
  Parametres :
    - period_start : date debut rattrapage (ex: 2026-04-14)
    - period_end : date fin rattrapage (ex: 2026-05-01)
    - dry_run : si true, compte juste ce qui manque
  
  Pour Outlook :
    GET /me/messages?$filter=receivedDateTime ge {start}
                              and receivedDateTime le {end}
                     &$select=id,subject,from,...
                     &$top=100
                     (paginate via @odata.nextLink)
    Pour chaque mail :
      Si mail_exists -> skip
      Sinon : process_incoming_mail (passe par le pipeline standard)
  
  Pour Gmail (apres Semaine 4) :
    Idem avec Gmail API messages.list + filter date

  Pour Drive (apres Semaine 5) :
    Pour chaque file modifie sur la periode -> compare avec
    drive_semantic_content. Reindex si manquant.
```

#### 2. Onboarding historique (a la connexion d'une nouvelle source)

```
Quand un user connecte une nouvelle boite (apres OAuth) :
  
  UI Raya demande :
    "Profondeur d historique a indexer ?"
    [ ] 3 mois     [ ] 6 mois     [x] 12 mois     [ ] tout
    
  Si selection != "rien" :
    Job de fond declanche (apscheduler one-shot ou queue dediee)
    Pagination par batch de 50-100 mails
    Insertion progressive
    Curseur sauvegarde dans connection_health.metadata
      -> "history_import_cursor" : date du dernier mail traite
      -> "history_import_status" : 'in_progress' / 'complete' / 'failed'
    Resume si interrompu (Railway redeploy, crash, etc.)
    Progress bar visible dans /admin/health/connection/{id}

POUR GUILLAUME (decision tracee) :
  Profondeur = "tout" (sans limite)
  Pour les boites mail Outlook + Gmail
  Pour Drive : tout aussi (apres definition de la blacklist)

POUR LES FUTURS CLIENTS :
  Defaut = 12 mois
  Modifiable lors de l onboarding
```

#### 3. Bouton "rattrapage automatique" sur les alertes WARNING

```
Quand la reconciliation nocturne (Niveau 4) detecte une fuite :
  Alerte WARNING via alert_dispatcher contient maintenant :
    - Le delta detecte (X mails manquants)
    - Un BOUTON "Lancer le rattrapage automatique"
    - Bouton declenche le scan de rattrapage sur la periode
      (typiquement les 24-48h precedentes)
  
  Avantage : le user n a pas besoin de comprendre la cause technique,
  il clique et le rattrapage se fait.
```

### Statut d'avancement

```
NON IMPLEMENTE encore au 01/05/2026 soir.

A FAIRE APRES Semaine 4 (Gmail) :
  - Avant que Guillaume bascule en usage productif
  - Sera la premiere chose a faire en Semaine 5 ou 6
  - OU pourrait etre fait en parallele si on a du temps

NOTE TECHNIQUE :
  Le mecanisme doit etre UNIVERSEL (pas un endpoint par source) :
  meme architecture pour Outlook, Gmail, Drive, et toute future
  connexion. Le scan de rattrapage est conceptuellement le NIVEAU 5
  du pattern delta sync (au-dela des 4 niveaux deja documentes).
```

---

*Document de référence pour le chantier Connexions Universelles.*
*Dernière itération : 01/05/2026 matin, après audit + 18 questions/réponses*
*+ audit "creuse les standards" sur 14 premières questions.*
*Auteurs : Guillaume + Claude.*
*À respecter rigoureusement quand on codera.*
