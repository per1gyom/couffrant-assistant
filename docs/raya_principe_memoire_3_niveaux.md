# Principe universel — mémoire à 3 niveaux

**Date** : 20 avril 2026
**Auteur** : décision de Guillaume lors de la session Drive, matin du 20/04
**Statut** : 🟢 principe architectural adopté, à appliquer à toutes les sources

---

## 1. Le principe en une phrase

> **Raya mémorise comme un humain** : elle sait précisément ce qu'elle utilise
> souvent, elle sait vaguement ce qui existe autour, et elle sait où retourner
> voir quand elle a besoin du détail précis.

## 2. Les 3 niveaux

### Niveau 1 — Résumé méta (toujours en base, très léger)

Pour CHAQUE objet connu (document, record Odoo, apprentissage web…) :

- Identifiant canonique (URL, file_id, record_id)
- Nom / titre
- Type / catégorie
- 1 phrase descriptive ("Ce PDF contient le règlement thermique 2024,
  60 pages, sections X/Y/Z")
- Date de dernier accès
- Source et chemin d'accès pour y retourner

**Taille** : 500-1000 caractères max. Toujours en base. Toujours indexé
pour recherche rapide.

### Niveau 2 — Détail vectorisé (contenu précis, chunked)

Pour les objets jugés pertinents :

- Le contenu lui-même découpé en chunks sémantiques
- Chaque chunk vectorisé via OpenAI `text-embedding-3-small`
- Stocké avec son embedding + son tsvector (recherche hybride)
- Lié au Niveau 1 par l'identifiant canonique

**Limite** : volumétrique (ex : 100 premières pages d'un PDF, 8000 tokens
max par chunk). Au-delà, on s'arrête et on garde l'accès Niveau 3.

### Niveau 3 — Accès à la demande (re-fetch live)

Pour les détails rares ou volumineux :

- Raya ne garde PAS le contenu en base
- Elle sait où le trouver (URL, path, record_id via Niveau 1)
- Quand nécessaire, elle le récupère **à la volée** (appel API Odoo, download
  Drive, recherche web)
- Elle peut ensuite extraire l'info pertinente et soit répondre, soit
  **promouvoir** cette nouvelle connaissance vers le Niveau 2 (la
  prochaine fois sera instantanée)

## 3. Pourquoi ces 3 niveaux

| Niveau | Coût | Vitesse | Utilité |
|---|---|---|---|
| 1 — Méta | 🟢 Très bas | ⚡ Instantané | Savoir ce qui existe |
| 2 — Détail vectorisé | 🟡 Moyen (embeddings) | ⚡ Rapide (< 1s) | Recherche sémantique précise |
| 3 — À la demande | 🔴 Élevé (I/O + parfois LLM) | 🐢 Lent (2-10s) | Accès au détail rare |

C'est la même **hiérarchie mémoire** que le cerveau humain :
- Niveau 1 = mémoire sémantique (tu sais que le Petit Prince existe)
- Niveau 2 = mémoire vive (tu te souviens de passages entiers que tu relis souvent)
- Niveau 3 = bibliothèque (tu sais où est le livre, tu vas le chercher au besoin)

## 4. Application par source de données

### 4.1 Drive SharePoint (Phase D, à venir)

| Niveau | Contenu |
|---|---|
| 1 — Méta | 1 entrée par fichier : nom, chemin, type, taille, résumé 1 phrase, dernière modif |
| 2 — Détail | Texte vectorisé chunké (100 premières pages si gros PDF, tout le fichier sinon) |
| 3 — Live | Via `read_drive_file()` : Raya ouvre le fichier complet à la volée |

### 4.2 Odoo

Actuellement implémenté avec **uniquement Niveau 2** (tout est vectorisé en
entier). À terme, rétrofitter pour suivre le même pattern :

| Niveau | Contenu |
|---|---|
| 1 — Méta | 1 entrée par record : nom, type, statut, date. Aujourd'hui dans `semantic_graph_nodes` = **déjà quasi conforme** |
| 2 — Détail | Chunks vectorisés (déjà fait). Mais revoir la limite : pour un devis de 50 lignes, pas besoin de tout chunker si on a le résumé méta |
| 3 — Live | Déjà géré via `odoo_call()` live. **Conforme.** |

**Action future** : rien d'urgent, Odoo marche. Juste à vérifier que quand
un record est déjà présent au Niveau 1, on n'a pas besoin de le re-vectoriser
au Niveau 2 si le résumé suffit.

### 4.3 Couche 5 — Apprentissage web (idée capturée, à concevoir plus tard)

| Niveau | Contenu |
|---|---|
| 1 — Méta | 1 entrée par `WebKnowledge` : sujet canonique, URL, date, 1 phrase |
| 2 — Détail | Résumé court vectorisé (pas le contenu brut de la page) |
| 3 — Live | Raya refait la recherche web si elle estime son Niveau 2 périmé |

### 4.4 Outlook / Gmail (plus tard)

| Niveau | Contenu |
|---|---|
| 1 — Méta | 1 entrée par mail : expéditeur, sujet, date, 1 phrase de résumé |
| 2 — Détail | Corps du mail vectorisé (et pièces jointes traitées comme documents Drive) |
| 3 — Live | Via l'API Graph / Gmail : ouvrir le mail complet au besoin |

## 5. Règles transversales

### 5.1 Critères de promotion Niveau 1 → Niveau 2

Ce n'est **pas** automatique. Un document monte au Niveau 2 si :

- Il est **dans un dossier vectorisé actif** (SharePoint surveillé)
- Son **type est pertinent** (PDF, Word, Excel — pas les images décoratives)
- Sa **taille est raisonnable** (< seuil configuré)
- Il **n'est pas déjà identifié comme redondant** (ex : 15 versions du même
  contrat → on garde la dernière en détail, les autres restent en méta)

### 5.2 Critères de rétrogradation Niveau 2 → Niveau 1

Un document **redescend** au Niveau 1 si :

- Il n'a pas été consulté depuis X mois (à définir, ex : 12 mois)
- Il est **obsolète** (remplacé par une version plus récente)
- Il occupe trop de place et rentre dans les derniers consultés

Ça évite la DB qui gonfle indéfiniment.

### 5.3 Résumé méta automatique

Qui génère le résumé 1 phrase du Niveau 1 ?

- Pour un **PDF court** : les 500 premiers caractères suffisent souvent
- Pour un **PDF long** : extraction table des matières + titre → résumé via
  LLM léger (Claude Haiku 4.5)
- Pour un **record Odoo** : assemblage automatique depuis les champs
  sémantiques (déjà fait dans `build_composite_text`)
- Pour un **mail** : expéditeur + sujet + 1re ligne
- Pour une **recherche web** : titre de la page + meta description

### 5.4 Budget par tenant

Chaque tenant a un budget implicite :
- **Niveau 1** : pas de limite raisonnable (1 ligne par fichier = très léger)
- **Niveau 2** : limite configurable (ex : 100 000 chunks max par tenant,
  au-delà on rétrograde les plus anciens)
- **Niveau 3** : pas de stockage, donc pas de limite

## 6. Unification du modèle de données

### 6.1 Table générique recommandée

Aujourd'hui on a `odoo_semantic_content`. À terme, renommer et généraliser en :

```
semantic_content (tenant_id, source, source_id, level, content, embedding, ...)
```

où `level` = 1 (méta) ou 2 (détail) et `source` = 'odoo' / 'drive' / 'web' / 'mail'.

**Décision** : ne pas faire la migration tout de suite. Elle sera lourde.
Commencer avec Drive sur une **nouvelle table** `drive_semantic_content`
propre. Plus tard, on fusionnera les deux en `semantic_content`.

### 6.2 Graphe sémantique

Le graphe typé (`semantic_graph_nodes` + `semantic_graph_edges`) est
**universel par design** — il ne change pas. On ajoute juste de nouveaux
types de nœuds (`Document`, `PdfPage`, `WebKnowledge`) et d'arêtes
(`contains_section`, `supersedes`, `stored_in_folder`).

## 7. Impact sur la recherche (retrieval)

Quand Raya cherche une info pour répondre à une question :

```
1. Interroger le Niveau 1 (recherche par mots-clés + graphe)
   → Trouve ce qui existe sur le sujet
2. Pour les résultats jugés pertinents, interroger le Niveau 2
   → Récupère les chunks précis
3. Si le Niveau 2 ne suffit pas OU si l'info est marquée "voir Niveau 3"
   → Faire un appel live (Odoo / Drive / web) à la volée
```

Ce pipeline est déjà en partie implémenté dans `app/retrieval.py`.
À étendre pour supporter les 3 niveaux proprement.

## 8. Ce qui change dans le quotidien

### Pour l'utilisateur (Guillaume)

Rien de visible tout de suite. Les réponses deviendront :
- **Plus rapides** (Niveau 1 + 2 = instantanés, Niveau 3 seulement si besoin)
- **Plus fiables** (on ne confond pas 2 versions du même doc)
- **Mieux sourcées** (Raya peut dire "j'ai trouvé ça dans le PDF X, section Y")

### Pour l'architecte (nous)

On devra **toujours se poser la question du niveau** quand on ajoute une
source. La question standard :

> Pour cette donnée X, quel contenu va au Niveau 1 ? au Niveau 2 ?
> Quand faut-il aller au Niveau 3 ?

## 9. Conséquences immédiates

### À faire maintenant (pendant la conception Drive)

- Structurer le modèle de données Drive pour supporter les 3 niveaux dès
  le départ (pas de rétrofit douloureux plus tard)
- Choisir les seuils : taille max, nombre de pages max, limite chunks/tenant

### À noter pour plus tard

- **Rétrofit Odoo** pour supporter explicitement le Niveau 1 séparé du Niveau 2
- **Rétrofit `retrieval.py`** pour interroger dans le bon ordre
- **Interface admin** pour voir et gérer les 3 niveaux (quels docs promus,
  lesquels rétrogradés, budget restant)

## 10. Lien avec les autres documents

- `raya_memory_architecture.md` — les 4 couches (Live, Graphe, Vectorisation,
  Surveillance). Ce document ajoute une **5e dimension orthogonale** : les
  3 niveaux de détail appliqués à chaque source.
- `raya_couche5_apprentissage_permanent.md` — la Couche 5 web appliquera
  strictement ce principe (résumé + pas le contenu brut).
- `audit_drive_sharepoint_20avril.md` — plan Drive à enrichir avec ce principe.
- `raya_planning_v4.md` — roadmap globale, mettre à jour la Phase D.

## 11. Principe de conception : "Comment un humain fait-il ?"

Règle simple à garder en tête à chaque décision :

> Si un humain compétent dans le métier devait gérer cette info, comment
> mémoriserait-il ? Est-ce qu'il retiendrait chaque ligne ? Non. Est-ce qu'il
> ignorerait totalement ? Non. Il saurait "il y a un truc sur le sujet,
> je vais chercher". C'est exactement ce que Raya doit faire.

Cette règle tranchera la plupart des arbitrages. Ne retenir précisément
que ce qui est consulté souvent. Pour le reste, savoir où chercher suffit.
