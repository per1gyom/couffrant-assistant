# Couche 5 — Apprentissage permanent et arbitrage de vectorisation

**Statut :** 🟡 idée capturée le 20/04/2026, à concevoir après finalisation Odoo
**Dernière mise à jour :** 20/04/2026 matin
**Contexte :** intuition de Guillaume lors du point matinal après le scan de nuit réussi

---

## 1. Le problème que cherche à résoudre la Couche 5

Aujourd'hui, Raya a 4 couches de mémoire (voir `raya_memory_architecture.md`) :
1. **Live** — lecture à la demande (Odoo, Drive, etc.)
2. **Graphe sémantique** — relations typées entre entités
3. **Vectorisation** — recherche sémantique hybride
4. **Surveillance proactive** — CRON briefings, détection d'anomalies

**Il manque une capacité** : quand Raya fait une recherche web pour répondre à une
question, **rien n'est retenu de façon permanente**. Si la même question revient
demain, Raya refait la même recherche web (lente, coûteuse, pas toujours reproductible).

## 2. Le scénario concret de Guillaume (exemple SC 144 → SC 145)

> Aujourd'hui : Raya connaît bien le **dossier SC 144 du Consuel**. Il est dans
> ses documents, elle l'a mémorisé comme règle ("comment remplir ce formulaire",
> champs obligatoires, pièges courants, etc.).
>
> Dans une semaine : le **SC 145** sort. Guillaume le demande à Raya. Elle ne le
> connaît pas. Elle fait une recherche web, trouve le document officiel, répond.
>
> **Ce que Guillaume veut** : qu'à partir de ce moment, le SC 145 devienne pour
> Raya une référence permanente. Plus besoin de refaire la recherche web la fois
> d'après. Et idéalement, Raya comprend que **SC 145 remplace SC 144** et bascule
> ses futures réponses sur le nouveau modèle.

## 3. Les nuances importantes imposées par Guillaume

Ce qui **NE doit PAS** arriver :

- ❌ **Pas tout vectoriser systématiquement**. Si Guillaume demande "quel temps
  fait-il cette semaine ?", c'est une question jetable. Aucun intérêt à stocker.
- ❌ **Pas stocker le contenu brut des pages web**. Ce serait trop volumineux,
  souvent périmé, sans valeur ajoutée par rapport à Internet lui-même.
- ❌ **Pas alourdir le graphe** avec du bruit. Le graphe doit rester un outil
  de précision.

Ce qui **DOIT** arriver :

- ✅ **Stocker la *méthode d'accès*** plutôt que le contenu. Savoir qu'un document
  existe, où le trouver, comment l'interpréter.
- ✅ **Retenir les règles et procédures** (comme "comment remplir un SC").
- ✅ **Gérer l'obsolescence** (SC 145 remplace SC 144).
- ✅ **Rester léger et intelligent** — arbitrer à bon escient.

## 4. La grande question — l'arbitrage

C'est le cœur du problème et ce qu'il faudra concevoir :

> **À quel moment, et selon quels critères, Raya décide de mémoriser
> (vectoriser + graphe) une information glanée en recherche web ?**

Quelques pistes qu'on pourrait explorer (aucune validée à ce stade) :

**Piste A — Signal utilisateur explicite**
> *Guillaume dit "retiens ça"* ou *"c'est la nouvelle référence"*. Raya mémorise
> alors. Avantage : contrôle total. Inconvénient : dépend de l'humain, pas
> automatique.

**Piste B — Détection de "sujet récurrent"**
> Si Guillaume a déjà posé 3 questions liées à "SC 144", la 4ème recherche web
> sur "SC 145" est probablement importante → mémoriser. Si une question tombe
> isolée (météo, trafic, etc.), oublier.

**Piste C — Détection par nature de la source**
> Document officiel (PDF du Consuel, .gouv.fr, normes) → vaut la peine de
> mémoriser la *référence*. Page perso, blog, forum → non.

**Piste D — Classification LLM en temps réel**
> Avant de mémoriser, un petit LLM pose la question :
> "Cette info est-elle :
>  (a) jetable (actualité éphémère, météo) → NE PAS retenir
>  (b) procédurale / réglementaire → RETENIR
>  (c) connaissance métier récurrente → RETENIR
>  (d) déjà connue dans mon graphe → MISE À JOUR éventuelle"

**Piste probable** : combinaison de B + C + D, avec fallback A (Guillaume peut
toujours dire "retiens" ou "oublie").

## 5. Ce qu'on stocke exactement (principe "carnet d'adresses" pas "encyclopédie")

**Philosophie** : imiter comment fonctionne un moteur de recherche. Google ne
stocke pas Internet en entier. Il stocke **des index** : où se trouve quoi, avec
quelques mots-clés. C'est le même principe.

Pour Raya, un apprentissage permanent stockerait par exemple :

| Champ | Contenu | Exemple |
|---|---|---|
| `subject` | Le sujet canonique | "Dossier Consuel SC 145" |
| `type` | Type de savoir | "procédure administrative" |
| `source_url` | L'URL de référence | "https://consuel.com/sc145.pdf" |
| `source_date` | Date de consultation | "2026-04-27" |
| `summary_text` | Résumé court vectorisé | "Nouveau formulaire depuis mai 2026, remplace SC 144. Champs obligatoires : ..." |
| `rules_extracted` | Règles / connaissances | ["champ 12 doit être signé par l'installateur", ...] |
| `supersedes` | Ce que ça remplace | "SC 144" |
| `validity` | Peut encore être utilisé ? | "valid" / "deprecated" / "uncertain" |
| `confidence` | Niveau de confiance | 0.8 (provient d'une source officielle .fr) |

Stockage : 1 nœud graphe (`WebKnowledge` ou similaire) + 1 chunk vectorisé
court (< 500 tokens) + quelques arêtes (`supersedes`, `relates_to`).

**Pas** : le PDF complet, le contenu de la page, les images. Juste le *quoi*,
le *où* et le *pourquoi c'est important*.

## 6. Le workflow côté Raya (pipeline de question)

Ce qui change dans la façon dont Raya répond à une question :

```
1. Question Guillaume : "Comment remplir un SC 145 ?"
2. Raya interroge d'abord sa mémoire (Couches 1/2/3)
3. Trouve un nœud WebKnowledge "SC 145" (validity=valid, source_date récente)
   → Réponse sans recherche web, avec la source citée
   → Si le nœud est ancien (> 30 jours), propose "Je connais, je vérifie
      si c'est toujours à jour ?"
4. Si rien trouvé : recherche web classique
5. Avant de répondre, classification de l'information trouvée :
   → jetable : répondre, ne rien retenir
   → durable : créer un nœud WebKnowledge + vectoriser un résumé
6. Optionnellement : dire à Guillaume "J'ai appris quelque chose, tu veux
   que je le garde ?" pour les cas ambigus
```

## 7. Détection d'obsolescence (le cas SC 144 → SC 145)

Quand Raya apprend que "SC 145 remplace SC 144" :

- Créer l'arête `SC 145 —[supersedes]→ SC 144`
- Marquer SC 144 avec `validity=deprecated_by(SC 145)`
- Les futures recherches sur "SC" ou "Consuel" privilégient les nœuds `valid`
- SC 144 reste en mémoire (traçabilité) mais n'est plus proposé spontanément

## 8. Interaction avec le reste du système

**Avec l'agent conversationnel** :
Il devra appeler systématiquement une fonction `search_memory()` avant
`web_search`, et si la mémoire contient un résultat pertinent et frais,
l'utiliser.

**Avec le graphe** :
Nouveau type de nœud `WebKnowledge`. Nouvelles arêtes `supersedes`,
`learned_from_query`, `validated_by_user`.

**Avec la vectorisation** :
Nouvelle `source` dans `odoo_semantic_content` (ou nouvelle table dédiée
`web_knowledge_content` pour séparer proprement du reste). À trancher.

**Avec la Couche 4 (surveillance proactive)** :
Un job périodique (toutes les 2 semaines ?) pourrait re-vérifier la
fraîcheur des `WebKnowledge` anciens — "SC 145 existe toujours ? a-t-il
évolué ?".

## 9. Ce qui reste à décider (vraies questions ouvertes)

- **Arbitrage** : quelle combinaison des pistes A/B/C/D ? Priorité à la piste D
  (LLM) ou au signal explicite (A) ?
- **Granularité** : 1 nœud par document web ? Ou 1 nœud par "concept" (SC 145
  globalement, et pas chaque sous-section) ?
- **Durée de vie** : un WebKnowledge a-t-il une date d'expiration automatique ?
- **Confidentialité** : les WebKnowledge sont-ils cloisonnés par tenant ? Oui
  a priori (Couffrant et Juillet ont des métiers différents).
- **Validation humaine** : faut-il que Guillaume confirme explicitement avant
  stockage, ou Raya décide seule avec possibilité d'annulation ?
- **Interaction avec Couches 1-4** : faut-il que le search_memory retourne
  prioritairement les WebKnowledge quand ils sont frais, ou l'Odoo d'abord ?
- **Stockage du texte intégral** : on dit "pas le contenu brut" mais pour un
  PDF du Consuel, peut-on quand même télécharger le PDF et le mettre dans
  un chunk ? Ou juste l'URL ?

## 10. Planning

- **Capture (ce document)** : ✅ fait le 20/04/2026
- **Conception détaillée** : à faire APRÈS finalisation Odoo (webhooks activés
  + règles base_automation pilotes validées sur 48h)
- **Implémentation** : plusieurs jours/semaines, à découper en jalons comme
  on a fait pour les webhooks
- **Déclenchement** : Guillaume dira quand il veut qu'on attaque. Pas avant
  que la couche Odoo soit stable en prod.

## 11. Raison d'être de ce document

Capture d'idée pour éviter qu'elle se perde. Le détail de la conception viendra
dans un document dédié `raya_couche5_conception.md` quand on décidera d'attaquer.

L'objectif final exprimé par Guillaume :

> *"J'aimerais que quand on lui demande quelque chose, avoir un graphe tellement
> précis que c'est comme si elle faisait une recherche internet à chaque fois."*

C'est la vision : un graphe sémantique qui devient, au fil du temps,
**aussi précis qu'un moteur de recherche** sur les sujets du métier, tout en
restant léger parce qu'il ne stocke que les bonnes abstractions, pas la masse
du web.
