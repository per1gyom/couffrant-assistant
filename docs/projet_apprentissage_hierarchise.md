# Projet — Apprentissage hiérarchisé de Raya

*Lancé le 05/05/2026 soir par Guillaume après l'incident de la règle 124 (boîte contact@ à connecter prochainement obsolète) qui a fait refuser à Raya une action sur une boîte pourtant connectée.*

## Contexte et déclencheur

Voir `raya_changelog.md`, session 05/05/2026 après-midi, point 6.

Resume rapide : Raya a en mémoire une règle id=124 datant du 17/04 qui dit *"boîte contact@ à connecter prochainement"*. Le 05/05 vers 17h, Guillaume reconnecte la boîte. Le contexte injecté à Raya pour chaque conversation contient bien `connected_mailboxes` avec contact@ dedans (liste vivante issue de `tenant_connections`). Mais Raya, à 18h38, refuse la demande de suppression en se basant sur la règle 124 plutôt que sur sa liste vivante.

Le système actuel ne distingue pas :
- Une règle de comportement durable
- Un fait stable
- Un état temporel qui peut périmer
- Une donnée vivante (toujours fraîche)
- Une connaissance métier / culture générale

Tout est dans `aria_rules`, tout au level "moyenne", tout traité pareil.

## Vision (formulation Guillaume)

> *Raya doit apprendre comme un humain le ferait, avec des priorisations d'importance et des notions différentes entre règle, information générale, information passagère, culture générale ou connaissance de son utilisateur. Pour la règle 124, elle aurait dû soit me dire qu'on avait évoqué de la connecter plus tard, soit me demander si elle est connectée maintenant, soit aller vérifier elle-même.*

> *Je pense qu'un humain dans la plupart du temps va être autonome et n'embêtera son responsable qu'en cas de doute sérieux ou de blocage.*

## Architecture proposée

### Dimension 1 — `nature` (NOUVELLE colonne)

4 valeurs, choisies pour avoir des comportements distincts dans le code (pas plus, pas moins) :

| Valeur | Description | Exemple | Comportement |
|---|---|---|---|
| `fact_stable` | Fait/préférence durable, pas de date d'expiration prévisible | "Charlotte = compta", "j'aime les réponses courtes", "siège social à Saint-Laurent" | Injecté dans `<connaissances_durables>`. Pas d'expiration. |
| `fact_temporal` | Information à durée limitée, qui peut périmer | "Romain en arrêt jusqu'à mai", "boîte contact@ à connecter prochainement", "deadline X le 7 mai" | Injecté dans `<infos_a_confirmer>` avec date. Si `revalidate_at` dépassé, marquée comme à reconfirmer. |
| `behavior` | Règle de comportement Raya elle-même | "ne jamais supprimer sans confirmation", "DELETE = action directe sans confirmation", "toujours préférer le tutoiement" | Injectée dans `<comportements>` du prompt système. |
| `knowledge` | Culture générale / vocabulaire métier | "un CONSUEL c'est…", "TVA solaire = 10%", "Enedis = gestionnaire réseau" | Injectée dans `<culture_metier>`. Stable, pas d'expiration. |

**Pourquoi 4 et pas plus** : chaque valeur a un comportement distinct dans le code (où on l'injecte, comment on la priorise, est-ce qu'elle peut expirer). En aller au-delà créerait des zones de chevauchement sans bénéfice fonctionnel. C'est la règle "autant de catégories que nécessaire pour des comportements distincts, mais pas plus".

### Dimension 2 — `category` (existante, à nettoyer)

On garde la colonne `category` qui sert à filtrer thématiquement (Équipe, Outils, Tri mails, etc.). C'est une dimension orthogonale à `nature`. Une règle "Romain est en arrêt" est `category=Équipe` ET `nature=fact_temporal`.

À nettoyer pour normaliser le vocabulaire (28 valeurs actuelles, certaines redondantes : "Comportement" / "Style" / "UX" pourraient fusionner).

### Dimension 3 — Dates (NOUVELLES colonnes)

| Colonne | Type | Usage |
|---|---|---|
| `expires_at` | TIMESTAMP NULL | Date à laquelle la règle est explicitement périmée. NULL pour `fact_stable`/`behavior`/`knowledge`. Posé pour `fact_temporal` quand une date de fin est mentionnée. |
| `revalidate_at` | TIMESTAMP NULL | Date à laquelle Raya doit reconfirmer (par défaut +30j pour `fact_temporal`). Au-delà : ne pas affirmer, demander ou vérifier vivement. |

### Hiérarchie de priorisation (logique d'utilisation)

Quand 2 sources contredisent au moment de répondre :

```
1. DONNÉE VIVANTE (connected_mailboxes, calendar, mail_memory récent)
   → toujours fait foi, jamais périmée
2. DÉCLARATION EXPLICITE RÉCENTE (< 7j) de l'utilisateur dans la conversation courante
3. fact_stable + reinforced récemment + confidence haute
4. behavior + reinforced + confidence haute
5. fact_temporal pas expirée + revalidate_at dans le futur
6. knowledge (rarement contradictoire)
7. fact_stable ancien jamais reinforced
8. fact_temporal expirée ou revalidate_at dépassée
   → ne pas affirmer, soit vérifier via tool, soit demander à l'user
9. inférence / hypothèse → toujours à confirmer
```

Règle d'or pour le prompt système :

> *"Si une info dans `<infos_a_confirmer>` ou une règle `fact_temporal` ancienne contredit ce que tu vois dans `<donnees_vivantes>`, fais confiance aux données vivantes et marque l'info comme à mettre à jour. Si l'info est centrale à la réponse mais pas vérifiable par données vivantes, vérifie avant d'affirmer (via search_mail, list_connexions, etc.) ; ne demande à l'utilisateur qu'en dernier recours."*

## Pipeline de capture améliorée

### Principe — "RAG before write"

Quand Raya capture une nouvelle règle, **un LLM Sonnet** (pas Haiku, pour la nuance) est appelé avec :
- La nouvelle info à capturer
- Le contexte de la conversation
- Les **5 règles existantes les plus proches** (recherche par embedding)
- Une demande structurée

Le LLM répond avec :
- **Décision** : `nouvelle` / `mise_a_jour_id_X` / `rejete_ephemere` / `rejete_doublon`
- Si `nouvelle` ou `mise_a_jour` :
  - `nature` (fact_stable / fact_temporal / behavior / knowledge)
  - `category` (parmi liste fermée nettoyée)
  - `expires_at` (NULL ou date)
  - `revalidate_at` (NULL ou date)
  - `confidence` (0..1)
  - `texte_propre` (reformulation propre, sans "tu" ambigu)
- **Raisonnement** (pour audit) : pourquoi cette classification

### Coût estimé

- ~3000 tokens input + 500 output par capture
- Sonnet : 0.017 € par capture
- Si Raya capture 5 règles/jour : ~2.5 €/mois
- Acceptable

### Action selon la décision

| Décision | Action |
|---|---|
| `nouvelle` | INSERT dans aria_rules avec tous les champs |
| `mise_a_jour_id_X` | UPDATE de la règle X (texte fusionné, nature actualisée) |
| `rejete_ephemere` | Ne pas mémoriser (info passagère qu'on utilise une fois) |
| `rejete_doublon` | Réactiver la règle existante (`last_reinforced_at = NOW`, `confidence++`) |

## Reclassement initial des 200 règles existantes

Toutes les règles actuelles sont `level=moyenne` sans nature. À reclasser en one-shot.

**Approche** : Claude Opus (pas Haiku ni Sonnet) traite les 200 règles en une seule passe, avec analyse profonde et nuance. Guillaume valide ensuite par échantillonnage.

**Pourquoi Opus** :
- Erreur initiale lourde de conséquences (chaque règle mal classée = comportement faux pendant longtemps)
- Capacité à voir des nuances ("à connecter prochainement" → temporel, alors qu'un Haiku peut le confondre avec stable)
- Coût acceptable pour un one-shot

**Pratique** :
- Lecture des 200 règles en bloc
- Pour chacune : produire `nature`, `category` propre, `expires_at`, `revalidate_at`, `confidence` ajustée
- Output : un fichier SQL d'UPDATE
- Review humain rapide sur 30 cas tirés au hasard avant exécution

## Plan d'exécution proposé (étages)

### Étage 1 — Schéma + migration (1h)
- ALTER TABLE aria_rules ADD COLUMN nature, expires_at, revalidate_at
- Index sur nature pour les requêtes du loader
- Tests : pas de régression du système existant

### Étage 2 — Reclassement Opus des 200 règles (2-3h)
- Read all 200 rules
- Analyse profonde + production des UPDATE
- Review échantillonnage Guillaume
- Apply

### Étage 3 — Modification du loader (1-2h)
- `aria_loaders.py` modifié pour séparer en 4 blocs au lieu d'un fourre-tout
- Filtrage `expires_at < NOW()` exclus, `revalidate_at < NOW()` marqués
- Test : Raya doit voir les règles correctement séparées

### Étage 4 — Modification du prompt système (1-2h)
- Ajout de la règle d'or "donnée vivante > règle ancienne"
- Instructions sur le réflexe de vérification avant d'affirmer
- Test bout-en-bout : refaire le test contact@ avec la règle 124 reformulée pour voir si Raya gère

### Étage 5 — Pipeline de capture amélioré (3-4h)
- Modification de `_save_rule_to_db` (ou équivalent)
- Recherche par embedding des 5 plus proches
- Appel Sonnet de classification
- Application de la décision (insert / update / rejet)
- Test en conditions réelles

### Étage 6 — Renforcement passif (1-2h)
- Quand Raya utilise une règle et que ça marche → `last_reinforced_at = NOW()`, `confidence++`
- Quand une règle est contredite par les données vivantes → désactivation auto et journalisation dans `rule_modifications`

### Total estimé : 1.5 à 2 journées de travail

## Décisions à prendre avant de coder

- [ ] Validation Guillaume de la granularité 4-valeurs (nature)
- [ ] Validation des 4 valeurs proposées
- [ ] Validation du principe "Sonnet pour capture, Opus pour reclassement initial"
- [ ] Validation du plan en étages (ou ré-ordonnancement)
- [ ] Décision sur l'ordre : finir aujourd'hui Étage 1+2 ? ou seulement Étage 1 ?
