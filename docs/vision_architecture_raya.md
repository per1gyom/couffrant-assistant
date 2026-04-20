# Vision architecture Raya

**Version** : 1.0 — 20 avril 2026, soirée
**Statut** : référence définitive, à consulter avant toute décision d'architecture
**Auteur de la vision** : Guillaume Perrin (Couffrant Solar)

---

## 🎯 La vision en une phrase

> **Raya = Opus + mémoire de Guillaume + accès à ses données.**
>
> On ne construit pas une IA. On donne à une IA exceptionnelle ce qu'il lui faut pour devenir **le Jarvis de Guillaume**.


## 🧭 Le principe directeur

**Ne jamais bâillonner Opus.** Chaque règle qu'on ajoute dans le prompt ou dans le code restreint l'intelligence naturelle du modèle. Notre job n'est pas de coder de l'intelligence — Opus en a déjà, on la paye cher. Notre job est de :

1. **Donner accès aux données** via un graphe unifié interrogeable
2. **Donner accès aux outils** pour qu'Opus puisse agir
3. **Mémoriser le contexte** entre les conversations
4. **Apprendre les préférences** de Guillaume et des collaborateurs

**Tout le reste — routage sophistiqué, détection d'insatisfaction, doute, créativité, synthèse, auto-correction — Opus sait déjà faire.** Mieux que nous. On lui fait confiance.

## 📐 Les 4 règles immuables

### Règle 1 — Multi-source par défaut, toujours

Toute question métier déclenche **une recherche sur le graphe complet**. Zéro cloisonnement par source. Pas de "cette question concerne Odoo uniquement" ou "là c'est un sujet Drive". Le graphe est unifié, il est interrogé en entier.

### Règle 2 — Le routage ajoute, n'ampute jamais

Le seul filtre en amont est un routeur binaire minimal : *question métier oui/non ?*. En cas de doute → oui. **Jamais de sous-sélection** de "quelle source interroger". Le routage décide seulement si on interroge le graphe du tout.

### Règle 3 — Tout pronom possessif ou référence métier → graphe

Dès que la question contient *"mes / mon / notre / nos / le chantier / le client / la semaine prochaine"* ou toute référence à l'univers Couffrant Solar → on interroge le graphe. Même *"fais-moi un poème sur mes clients"* ou *"génère une image compilant mes chantiers"* déclenche la recherche.

### Règle 4 — Ne pas coder ce qu'Opus sait déjà faire

Avant d'ajouter toute règle, poser la question : *"Opus ne le fait-il pas déjà tout seul ?"*. Si oui → on n'ajoute pas. On ne code ni le doute, ni la reprise après erreur, ni la détection de ton, ni la synthèse intelligente. Tout ça est natif.


## 🏗️ Architecture cible en 4 couches évolutives

### Couche 1 — Graphe sémantique unifié

Tous les nœuds de toutes les sources vivent dans **un seul graphe** (`semantic_graph_nodes` + `semantic_graph_edges`).

Chaque nœud a un attribut `source_type` : `odoo | drive | mail | conversation | rule | insight`.

Les edges cross-source deviennent possibles et sont créés automatiquement : un mail peut pointer vers un client Odoo, un fichier Drive peut pointer vers un devis, une conversation peut pointer vers un chantier.

Les tables de contenu (`odoo_semantic_content`, `drive_semantic_content`, `mail_memory`, `aria_memory`) restent séparées au stockage pour performance, mais elles sont vues comme des **réservoirs** auxquels les nœuds du graphe pointent.

### Couche 2 — Recherche unifiée

Un seul outil exposé à Opus : `SEARCH(query)`.

Pipeline interne :
1. Embedding de la question (1 seul appel OpenAI)
2. Recherche dense (pgvector cosine) sur tous les nœuds du graphe
3. Recherche sparse (BM25 tsvector) sur le contenu pointé
4. Fusion RRF (Reciprocal Rank Fusion)
5. Reranking Cohere multilingue
6. Traversée multi-hop du graphe à partir des top N pour enrichir le contexte
7. Retour à Opus avec résultats unifiés et leur source

Pas de tag par source. Pas de filtre prématuré. Le graphe est interrogé en entier.

### Couche 3 — GraphRAG communautés (futur, étape C)

Quand le graphe sera dense (plusieurs milliers de nœuds + edges cross-source riches), un job nocturne détecte automatiquement les **communautés** (grappes de nœuds très connectés : exemple "client Legroux" + ses devis + ses mails + ses photos chantier).

Pour chaque communauté, un LLM génère un résumé condensé (~300 mots). Ces résumés deviennent un niveau de recherche supplémentaire qui accélère les questions transversales larges ("où en sont mes chantiers actifs").

Approche inspirée de **GraphRAG** (Microsoft Research, 2024).

### Couche 4 — Outils externes (futur, étape D)

Opus reçoit des outils supplémentaires qu'il utilise s'il le juge utile :
- `get_weather(location, date)` — pour croiser avec le planning
- `web_search(query)` — pour l'actualité récente
- `send_mail(...)`, `create_event(...)`, `create_devis(...)` — actions écriture

On ne dit pas à Opus *"quand utiliser tel outil"*. On lui donne les outils, il décide.


## 🤖 Les modèles et leur rôle

### Haiku 4.5 — Routage binaire minimal
Seule responsabilité : répondre à *"question métier oui/non ?"* en ~300ms.
- Latence critique, on ne peut pas se permettre Sonnet ici (ajouterait 1s)
- Règle du prompt : *"en cas de doute, oui. Mieux vaut 5 requêtes inutiles qu'une source ratée."*
- Coût par appel : ~0.0001$

### Sonnet 4.6 — Réponse par défaut
Le modèle principal qui compose les réponses Raya après interrogation du graphe.
- Équilibre optimal intelligence/latence/coût
- Utilisé pour 95% des réponses
- Coût par réponse typique : ~0.002$

### Opus 4.7 — Escalade
Activé manuellement par Guillaume (*"approfondis"*) ou automatiquement si Sonnet détecte naturellement qu'une question dépasse ses capacités.
- Raisonnement plus profond, meilleur pour les questions complexes multi-contraintes
- Coût : ~5x plus cher que Sonnet, à réserver pour les cas qui le méritent

### Un jour peut-être, d'autres modèles
Si un meilleur modèle sort chez Anthropic ou ailleurs, **on change simplement l'appel API**. L'architecture Raya ne dépend pas du modèle. C'est un principe de conception : Raya apporte la mémoire + l'accès aux données, le modèle apporte l'intelligence. Les deux sont découplés.

## 🔄 Couche 5 — Apprentissage permanent (en continu)

Parallèlement aux 4 couches techniques, Raya **apprend Guillaume** (et à terme chaque collaborateur) en continu :
- Préférences de ton (*"Guillaume aime quand je dis 'j'ai merdé'"*)
- Règles implicites (*"Guillaume refuse toujours les appels les lundis matin"*)
- Habitudes métier (*"Guillaume commence la journée en regardant ses factures impayées"*)
- Connaissances accumulées (*"SE100K = onduleur SolarEdge, utilisé sur les grands chantiers"*)

Stockées dans `aria_rules`, `aria_insights`, `aria_memory` avec un score de confiance et un mécanisme de renforcement. Injectées en tête de chaque prompt pour que Sonnet/Opus partent avec le bon contexte relationnel.

**C'est ça qui fait que Raya = Jarvis de Guillaume spécifiquement**, pas Jarvis générique. Le modèle est le même pour tout le monde ; la mémoire est unique à chaque utilisateur.


## 📋 Plan d'exécution

### Étape A — Multi-source unifié (prochaine session)
1. Migrer les nœuds Drive, mail, conversation dans `semantic_graph_nodes` (ajouter `source_type`)
2. Créer les premiers edges cross-source (mail → partner Odoo, fichier Drive → devis)
3. `unified_retrieval.py` remplace `retrieval.py` (pipeline sur graphe complet)
4. Nouveau tag unique `[ACTION:SEARCH:question]` comme réflexe par défaut dans le prompt
5. Routeur Haiku binaire minimal, biais "en cas de doute, oui"
6. Prompt Opus/Sonnet minimaliste — qui tu es, ce qui t'est accessible, ton attendu. Zéro règle comportementale.

### Étape B — Enrichissement cross-source (session dédiée)
Automatisation de la création d'edges cross-source (détection NLP des références client/chantier dans les mails, association des fichiers Drive aux devis Odoo par pattern de nom, etc.).

### Étape C — GraphRAG communautés (session dédiée, quand le graphe sera dense)
Job nocturne Leiden + résumés LLM par communauté + embedding des résumés + intégration dans la recherche.

### Étape D — Outils externes (session dédiée)
Météo conditionnée au planning, web search, surveillance mails hors horaires, actions écriture (création devis, envoi mail, planification RDV).

### Couche 5 — Continu
Enrichissement permanent de `aria_rules`, `aria_insights`, `aria_memory` via les feedbacks implicites et explicites de Guillaume.

## 💰 Coûts estimés

Ordre de grandeur par message Raya :
- Routage Haiku : 0.0001$
- Embedding question : 0.00001$
- Recherche Postgres : 0$ (CPU)
- Reranking Cohere : 0.002$
- Réponse Sonnet : ~0.002$
- **Total typique : ~0.004$/message**

Pour 100 messages/jour : **~12$/mois**. Pour 500 messages/jour sur 5 utilisateurs : **~60$/mois**. Les scans de nuit des communautés (étape C future) ajoutent ~150$/mois. Négligeable au regard du ROI d'un assistant intelligent.

## 🛑 Quand on est tenté d'ajouter une règle

Avant toute nouvelle règle dans le code ou le prompt, dérouler cette check-list :

1. **Opus sait-il déjà faire cela seul ?** Si oui → ne pas coder
2. **La règle restreint-elle l'accès aux données ?** Si oui → refuser
3. **La règle introduit-elle un cloisonnement par source ?** Si oui → refuser
4. **Y a-t-il un risque de faux négatif qui ampute l'intelligence ?** Si oui → refuser
5. **Si on observe des dérives réelles en usage**, alors seulement → envisager une règle, la plus légère possible, documenter dans `docs/archives/approches_abandonnees_YYYYMMDD.md` avec la raison qui motive son retour

Principe : **il est plus facile d'ajouter des contraintes que de les retirer**. Démarrer libéré.

## 📚 Historique et archives

Ce document est le résultat d'une discussion architecturale profonde menée le 20 avril 2026 au soir entre Guillaume et Raya. Plusieurs approches ont été envisagées puis écartées — elles sont archivées dans `docs/archives/approches_abandonnees_20avril.md` pour référence future, au cas où l'usage révèlerait des dérives qui justifieraient d'y revenir.

## 🔗 Docs liés

- `docs/architecture_connexions.md` — modèle mental des connexions (scope tenant vs user)
- `docs/raya_principe_memoire_3_niveaux.md` — principe universel méta/détail/live
- `docs/raya_memory_architecture.md` — les 4 couches techniques de mémoire
- `docs/raya_couche5_apprentissage_permanent.md` — spec de la couche 5
- `docs/archives/approches_abandonnees_20avril.md` — approches discutées et écartées
