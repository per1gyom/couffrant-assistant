# Architecture Raya v2 — Mode Agent

**Date de rédaction** : 21 avril 2026
**Statut** : Specs validées, en attente d'implémentation
**Auteurs** : Guillaume Perrin + Claude (session de conception 21/04)

---

## 🎯 Principe fondateur

Raya n'est plus un assistant qui répond en une seule passe.
Raya est un **agent** qui boucle jusqu'à avoir une réponse satisfaisante.

Elle reçoit une question, elle réfléchit, elle appelle les outils dont
elle a besoin, elle évalue les résultats, elle rappelle d'autres outils
si nécessaire, et elle ne répond que quand elle est certaine.

**C'est exactement le fonctionnement de Claude via l'app Anthropic,
appliqué à Raya.**

---

## 🧠 Pourquoi cette refonte

Le modèle précédent (v1) fonctionnait en inférence simple :
1 question → 1 appel API → 1 réponse finale.

Ce modèle a une limite structurelle : Claude doit **tout faire en une
fois** (comprendre, chercher, croiser, répondre). Plus le prompt
accumule de règles et de tags, plus Claude se disperse et comble les
trous par des inventions plausibles.

Constat du 21/04/2026 : Raya hallucinait des factures, des numéros de
devis, des prénoms. Pas par incompétence du modèle, mais par surcharge
cognitive du prompt.

La v2 libère l'intelligence d'Opus en lui donnant des outils et du
temps, pas des règles supplémentaires.

---

## 🏗️ Architecture technique

### Mécanisme de boucle agent

Implémentation native via **Anthropic API "tool use"** : pas de code
de boucle custom, Anthropic fournit le framework.

```
while True:
    response = anthropic.messages.create(
        model="claude-opus-4-7",
        tools=RAYA_TOOLS,
        messages=messages,
    )
    if response.stop_reason == "end_turn":
        break
    for tool_call in response.content:
        if tool_call.type == "tool_use":
            result = execute_tool(tool_call.name, tool_call.input)
            messages.append(tool_result(result))
```

Claude décide elle-même :
- Quel outil appeler
- Quand elle a assez d'informations
- Quand elle s'arrête (`stop_reason: "end_turn"`)

### Modèle utilisé

**Opus 4.7** en phase de lancement.

Rationale : mettre en production avec le modèle le plus intelligent
pour valider que l'architecture fonctionne sans compromis. Une fois la
qualité confirmée, on pourra basculer vers Sonnet 4.6 ou un routage
Haiku → Sonnet/Opus pour optimiser les coûts.

---

## 🛡️ Garde-fous de la boucle

Pour éviter les boucles infinies et maîtriser les coûts :

| Limite | Valeur | Comportement au dépassement |
|---|---|---|
| Itérations max | 10 tours | Raya s'arrête et te dit "j'ai exploré plusieurs pistes, voici ce que j'ai, tu veux que je continue ?" |
| Timeout | 30 secondes | Idem : réponse partielle + demande de poursuite |
| Budget tokens | ~30 000 tokens dans la boucle | Idem : proposition de continuer |

Au dépassement d'une de ces 3 limites, Raya n'abandonne pas
brutalement : elle **rend compte** de ce qu'elle a trouvé et demande
confirmation pour continuer. C'est le modèle "j'ai atteint ma limite
d'utilisation d'outils, tu veux que je continue ?" que Claude via
l'app Anthropic fait déjà.

---

## 🧰 Les outils exposés à Claude

### Principe
Tous les anciens tags `[ACTION:...]` deviennent des **tools API natifs
Anthropic**. Claude appelle ces outils quand et comme elle juge utile.

La liste n'est **pas exhaustive** : elle est conçue pour s'étendre
facilement au fur et à mesure que de nouveaux logiciels / connecteurs
seront intégrés dans Raya.

### Outils de recherche et lecture (lecture seule, sans confirmation)

| Outil | Rôle | Priorité d'usage |
|---|---|---|
| `search_graph` | Recherche dans le graphe sémantique unifié (entités + relations + conversations passées). **Point d'entrée principal.** | Réflexe par défaut pour toute question métier |
| `search_odoo` | Recherche sémantique dans Odoo (contenu des devis, factures, contacts) | Zoom quand le graphe pointe vers Odoo |
| `search_drive` | Recherche sémantique dans les fichiers SharePoint | Zoom fichiers / recherche par thème |
| `search_mail` | Recherche dans les mails analysés (Outlook, Gmail) | Zoom mails / recherche par thème |
| `search_conversations` | Recherche dans l'historique complet des conversations | Zoom mémoire longue |
| `get_client_360` | Vue consolidée d'un client (partner + devis + factures + events + contacts) | Question "point sur X" |
| `web_search` | Recherche web native Anthropic | Entité / terme inconnu, vérification externe |
| `get_weather` | Météo d'une localisation | Chantiers extérieurs, planning |


### Rapport graphe ↔ search_*

Le graphe et les outils `search_*` sont **complémentaires**, pas
redondants.

Le graphe pointe vers les entités et leurs liens. Il répond à "qu'est-ce
qui concerne Legroux ?" en remontant partners, devis, mails, fichiers,
conversations liés à cette entité.

Les `search_*` cherchent par **contenu textuel**. Ils répondent à "quels
mails parlent de raccordement ?" en fouillant le texte indépendamment
des entités.

Cas où les `search_*` rattrapent le graphe :
- Entité implicite (mail qui dit "le chantier avec le problème
  d'onduleur" sans nommer le client)
- Variante orthographique ratée par l'extraction d'entités
- Mise à jour récente pas encore indexée dans le graphe
- Recherche thématique transversale ("tous les problèmes Enedis 2025")

Claude décide seule quand combiner les deux. Si on lui dit "vérifie
bien tous les mails sur X", elle comprend qu'il faut croiser graphe +
search_mail pour maximiser la couverture.

### Outils d'action (écriture, avec cartes de confirmation)

Tous ces outils **préparent** une action. L'exécution réelle est
toujours validée par Guillaume via la carte de confirmation affichée
dans l'interface.

| Outil | Action préparée | Confirmation |
|---|---|---|
| `send_mail` | Envoi d'un mail (Outlook ou Gmail) | Oui |
| `reply_to_mail` | Réponse à un mail existant | Oui |
| `archive_mail` | Archivage d'un mail | Oui |
| `delete_mail` | Mise à la corbeille d'un mail | Oui |
| `create_calendar_event` | Création d'un RDV | Oui |
| `send_teams_message` | Message Teams | Oui |
| `create_file` | Fichier téléchargeable (.md, .txt, .csv...) | Non |
| `create_pdf` | PDF structuré | Non |
| `create_excel` | Fichier Excel | Non |
| `dalle_image` | Image générée par DALL-E | Non |
| `speak_text` | Lecture vocale ElevenLabs | Non |

Les outils de génération de contenu (PDF, Excel, image) n'ont pas de
carte de confirmation : ils sont inoffensifs et produisent un
téléchargeable.


### Comportement post-écriture dans la boucle

Quand Claude appelle un outil d'écriture (par exemple `send_mail`) :

1. L'outil prépare l'action et affiche la carte de confirmation
2. L'outil renvoie à Claude "action préparée, en attente de validation"
3. Claude intègre cette information, dit à l'utilisateur
   "j'ai préparé le mail, le voici"
4. **La boucle s'arrête**
5. Guillaume valide à son rythme via la carte

Claude ne "boucle pas" sur l'écriture. Elle prépare, rend compte,
attend la validation humaine.

---

## 💬 Le prompt système

Le prompt est réduit à l'essentiel. Fini l'empilement de règles.

```
Tu es Raya, IA de Guillaume Perrin chez Couffrant Solar
(photovoltaïque, Romorantin-Lanthenay).
Tu parles au féminin, tutoiement.

Tu as accès à l'ensemble des données de l'entreprise via tes outils :
Odoo (clients, devis, factures), SharePoint, mails analysés, graphe
sémantique des relations, historique des conversations, web.

Règles non négociables :
1. Tout fait cité (nom, date, montant, référence) doit provenir d'un
   résultat d'outil de cette conversation. Tu ne devines jamais.
2. Si tu rencontres un terme que tu ne maîtrises pas (entreprise,
   technologie, personne), tu cherches spontanément avant de répondre.
3. Si tu as un doute, tu cherches à lever ce doute (plusieurs outils
   si besoin) avant de répondre.
4. Clarté avant volume. Pas d'invention pour faire sérieux. Si tu as
   3 infos, tu donnes 3 infos.
```

**~600 caractères.** C'est tout.

### Injections automatiques dans le prompt

En plus du prompt ci-dessus, sont injectés automatiquement par le code :
- Les **préférences durables** de l'utilisateur (compact, issu de
  `aria_rules`) : "boîte pro = Outlook", "réponses courtes", etc.
- Les **10 derniers échanges** de la conversation en clair
- La date et l'heure actuelles

Rien d'autre. Pas de descriptions de connecteurs, pas de règles de
maturité, pas de bloc narratif, pas de règles anti-hallucination
détaillées. Tout ce que fait Raya est dans les **tools**, pas dans le
prompt.

---

## 🧠 Architecture de la mémoire

### Principe

La mémoire de Raya n'est pas un système artificiel avec règles et
apprentissages séparés. C'est **l'historique conversationnel connecté
au graphe sémantique**.

Chaque conversation mentionne des entités (Legroux, SARL des Moines,
SE100K...). Ces mentions créent des **edges** dans le graphe entre
le nœud `conversation_N` et les nœuds entités concernées. Quand Raya
fait `search_graph("Legroux")`, elle remonte naturellement les
conversations où Legroux a été évoqué.

**La mémoire n'est pas un module à part. C'est le graphe.**

### Trois niveaux de mémoire

**Niveau 1 — Mémoire de travail (court terme, in-prompt)**
Les **10 derniers échanges** de la conversation envoyés en clair
dans chaque appel Claude. Couvre la continuité conversationnelle
immédiate.

**Niveau 2 — Mémoire sémantique (moyen / long terme, via graphe)**
L'intégralité de l'historique des conversations, vectorisée et
connectée aux entités métier. Accessible via `search_graph` et
`search_conversations`. Pas envoyée dans chaque prompt — interrogée
à la demande par Claude.

**Niveau 3 — Préférences durables (court et persistant)**
Règles apprises par Raya sur les habitudes de Guillaume (sans
rattachement à une entité métier). Stockées dans `aria_rules` et
injectées dans chaque prompt de manière compacte. Exemples :
- "boîte pro = Outlook, boîte perso = Gmail"
- "Guillaume préfère les réponses courtes et directes"
- "Arlène travaille à 80%, 35h/semaine"

### Mise à jour du graphe (batching par paquets de 8)

Le pipeline d'indexation est **asynchrone par batch**.

Déclenchement :
- **Tous les 8 échanges** : batch des 8 conversations passées
- **OU** après **30 minutes d'inactivité** : batch des conversations
  restantes non indexées

Ce qui se passe au batch :
1. Extraction des entités citées dans les 8 conversations
2. Vectorisation de chaque conversation
3. Création des nœuds `conversation_N` dans le graphe
4. Création des edges `conversation_N ↔ entité`
5. Stockage persistant

Propriétés :
- Pas d'impact latence sur les questions de Guillaume
- Les 10 derniers échanges en clair couvrent toute intersection
  possible avec les 8 en attente d'indexation
- Zéro perte : même après une session de 3 messages, la règle des 30
  minutes d'inactivité assure qu'ils seront indexés

### Apprentissage spontané

Raya apprend **spontanément** tout fait important sur Guillaume ou
son entreprise. Pas de carte de confirmation, pas de demande explicite.
Tout est traçable via les conversations passées dans le graphe.

Correction d'erreurs : en **conversation naturelle**. Si Raya ressort
un fait faux, Guillaume lui dit simplement "j'avais dit ça mais je me
trompais, en fait c'est autrement". Raya met à jour.

### Préférences explicites (niveau 3)

Quand Guillaume demande explicitement "retiens ça" ou "apprends que",
Raya utilise un outil `remember_preference` qui ajoute une ligne à
`aria_rules`. Ces préférences sont courtes, durables, et injectées
dans le prompt de chaque appel.

---

## ❌ Échecs d'outils

**Option retenue** : Claude reçoit l'erreur brute et décide.

Si un outil plante (Odoo down, timeout réseau, permission refusée),
l'erreur est transmise telle quelle à Claude qui s'adapte :
- Elle peut retenter
- Elle peut essayer un autre outil équivalent
- Elle peut dire à Guillaume "Odoo ne répond pas, voici ce que j'ai
  trouvé ailleurs"

Pas de logique de retry automatique côté code. Pas de suggestion
d'outils alternatifs codée. On fait confiance à Claude.

---

## 📋 Confirmations massives

Quand une action implique un volume important (ex : envoi à 47 clients),
Claude décide seule si elle prépare d'un coup ou demande confirmation
préalable.

Pas de règle codée. Les garde-fous temps / itérations / tokens assurent
de toute façon qu'une action trop lourde déclencherait une demande de
poursuite.

---

## 💰 Coût et latence prévisionnels

### Latence
- Question simple sans outil : 2-4 secondes
- Question moyenne (2-3 outils) : 5-10 secondes
- Question complexe (5-10 outils) : 15-30 secondes
- Au-delà : garde-fou déclenché, demande de poursuite

**Principe** : la pertinence prime sur la vitesse.

### Coût par message (estimation Opus 4.7)
- Simple : ~0.20-0.40 €
- Moyen : ~0.50-0.80 €
- Complexe : ~1.00-1.50 €

### Coût mensuel estimé
- Usage faible (10 msg/jour) : ~30-50 €/mois
- Usage modéré (30 msg/jour) : ~60-100 €/mois
- Usage intense (équipe, 100 msg/jour) : ~150-250 €/mois

Plus cher qu'en v1 (qui tournait à ~15 €/mois), mais cohérent avec la
valeur apportée par un agent qui ne hallucine plus. Optimisation
possible plus tard par bascule en Sonnet ou routage Haiku/Sonnet/Opus.

---

## 🔄 Ce qui disparaît par rapport à v1

### Code / concepts supprimés
- Le système de **tags** `[ACTION:...]` (remplacé par tools natifs)
- `CORE_RULES` long et détaillé
- `GUARDRAILS` de `prompt_guardrails.py`
- Les règles anti-hallucination empilées (redondances)
- Les descriptions de connecteurs dans le prompt
- Les blocs de maturité, narrative, alerts, topics, etc.
- Le routage Haiku → Sonnet/Opus (pour l'instant, en v2.0)
- Le `hot_summary` régénéré périodiquement (remplacé par graphe)
- Les résumés intermédiaires des anciennes sessions

### Fichiers probablement à supprimer / vider
- `app/routes/prompt_guardrails.py` (intégralement remplacé)
- `app/routes/prompt_actions.py` (remplacé par registre des tools)
- `app/routes/prompt_blocks.py` et `prompt_blocks_extra.py`
  (la plupart des blocs)
- Grande partie de `app/routes/aria_context.py`

### Ce qui est préservé
- L'infrastructure Odoo / Drive / mail / Teams (les **connecteurs**
  restent, ils seront juste appelés via des tools au lieu de tags)
- La DB (`aria_memory`, `pending_actions`, `aria_rules`, le graphe)
- Le système de permissions / tenants
- Les cartes de confirmation côté front
- L'app Flutter

---

## 🚧 Plan de mise en œuvre (5 étapes)

### Étape 1 — Spécifications (terminée)
Ce document.

### Étape 2 — Audit de l'existant (à venir)
Inventaire exhaustif de ce qui existe aujourd'hui dans le code :
tous les tags ACTION actuels, les prompts, les connecteurs, la DB.
Livrable : tableau de correspondance "existant → futur".

### Étape 3 — Archivage de l'existant
Avant toute modification :
- Branche git `archive/raya-v1-single-shot-21avril2026`
- Tag git `v1-single-shot`
- Document `docs/archive_v1_single_shot.md`

Garantit un retour arrière possible en quelques secondes.

### Étape 4 — Refonte du code (v2)
Par petits commits testables.

Fichiers principaux à modifier :
- `app/routes/raya_helpers.py` → boucle agent
- `app/routes/raya_tools.py` → nouveau fichier, registre des tools
- `app/routes/aria_context.py` → prompt réduit

Plus la suppression progressive des fichiers mentionnés plus haut.

Durée estimée : 1-2 jours de travail concentré.

### Étape 5 — Bascule progressive
Feature flag `RAYA_AGENT_MODE=true/false` dans les variables
d'environnement Railway. Permet de basculer instantanément entre v1
et v2, notamment pour les tests.

Tests prioritaires :
- Question Legroux (le vrai test qui a déclenché cette refonte)
- Question SE100K (matériel par référence)
- Question OpenFire (entité externe inconnue)
- Enchaînement de questions pour valider la continuité conversationnelle

Une fois la v2 validée pendant quelques jours, le feature flag est
retiré et la v1 est archivée définitivement.

---

## 🎯 Critères de succès

La v2 est considérée comme réussie quand :

1. Raya ne hallucine plus (ni noms, ni devis, ni factures inventés)
2. Raya cherche spontanément les termes inconnus (web search)
3. Raya croise plusieurs outils quand nécessaire sans qu'on le demande
4. Raya admet clairement quand elle n'a pas une information
5. Raya retrouve naturellement les faits des conversations passées
6. Guillaume ressent une **relation continue** avec Raya plutôt qu'un
   enchaînement de questions isolées
7. Le coût reste soutenable (< 200 €/mois en usage normal)

---

## 📚 Documents liés

- `docs/vision_architecture_raya.md` — Vision fondatrice (septembre 2025)
- `docs/plan_resilience_et_securite.md` — Plan résilience 7 étapes
- `docs/recensement_acces_odoo.md` — État des accès Odoo
- `docs/rapport_audit_session_21avril_nuit.md` — Audit de cohérence

---

## 📝 Historique de ce document

- **21/04/2026 après-midi** : rédaction initiale après session de
  conception Guillaume + Claude (~3h d'échanges). Specs validées par
  Guillaume.
- **Prochaines étapes** : audit de l'existant, puis archivage, puis
  refonte.

**Ce document est la référence unique pour la refonte v2.
Toute décision future doit s'y référer.**
