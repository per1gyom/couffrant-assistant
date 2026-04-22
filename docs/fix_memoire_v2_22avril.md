# Fix mémoire v2 — à faire le 22 avril

**Date** : 22 avril 2026, 01h30
**Contexte** : premier test réel de la v2 sur dossier Coullet.
**Validation globale** : ✅ succès majeur — Raya n'hallucine plus, s'auto-corrige, apprend.
**Problème trouvé** : la boucle agent a buté sur le garde-fou tokens (60k après ajustement) sur une question métier complexe.

---

## 🔍 Diagnostic : pourquoi ça bute

### Le symptôme
Sur une 3e question complexe (calcul reste-à-facturer devis vs acomptes), la boucle agent atteint le plafond de 60k tokens et répond *"j'ai atteint ma limite de réflexion"*.

### La cause
L'historique in-prompt est **trop lourd** :
- 10 derniers échanges chargés intégralement
- Les échanges de la v2 sont riches (tableaux de factures, listes de mails, etc.)
- Chaque échange = 3-5k tokens
- Total historique : 40-50k tokens **avant même que Raya commence à bosser**

→ Il ne reste que 10-15k tokens pour la vraie recherche, insuffisant pour une question croisée.

### Pourquoi "continue" ne marche pas
Quand l'utilisateur dit "continue", Raya relance une boucle complète avec le **même historique lourd**. Elle re-bute immédiatement.

---

## 🧠 L'intuition de Guillaume (01h30 du matin)

> *"J'ai un doute sur l'injection des conversations passées, le résumé et le graphe, quelque chose ne me paraît pas optimal"*

**Formalisation de cette intuition** :

Il y a 3 mécanismes de mémoire :
1. **In-prompt** (10 derniers échanges, intégralement)
2. **Résumé** (proposé comme fix : compresser les anciens échanges)
3. **Graphe** (search_conversations, via graph_indexer)

**Observation clé** : le résumé et le graphe font la même chose. Ils permettent à Raya d'accéder à des conversations anciennes. Mais :
- Le **résumé** pousse le contexte dans le prompt (coût fixe à chaque requête)
- Le **graphe** permet à Raya d'aller chercher elle-même quand elle en a besoin (coût variable, contextuel)

**Le résumé est redondant avec le graphe** — sauf si le graphe a du retard.

---

## ✅ Architecture cible (décidée le 22/04 à 01h30)

### 3 couches de mémoire, pas 4

| Couche | Rôle | Mécanisme |
|---|---|---|
| **Court terme** | Les 3 derniers échanges | In-prompt intégralement |
| **Associative** | Par entité (Legroux, Coullet, etc.) | `search_graph(entité)` |
| **Temporelle** | Chronologique ancienne | `search_conversations(sujet)` |

**Pas de résumé.** Supprimé par cohérence avec le graphe.

### Paramètres à changer

| Paramètre | Actuel | Cible | Fichier |
|---|---|---|---|
| Historique in-prompt | 10 échanges | **3 échanges** | `raya_agent_core.py` `_load_recent_history` |
| Troncature réponse dans historique | Aucune | **3000 chars max** | `raya_agent_core.py` `_load_recent_history` |
| Batch graph_indexer | 8 convs | **1 conv (immédiat)** | `graph_indexer.py` `BATCH_SIZE` |
| Budget tokens boucle | 60k | **60k (OK)** | `raya_agent_core.py` |
| Itérations max | 15 | **15 (OK)** | `raya_agent_core.py` |
| Durée max | 60s | **60s (OK)** | `raya_agent_core.py` |

### Pourquoi indexer immédiatement (batch=1) ?

**Raison** : cohérence avec historique réduit.

Si l'historique in-prompt ne couvre que les 3 derniers échanges, alors les échanges 4 à 8 (au-delà du court terme mais pas encore indexés) seraient dans un **trou de mémoire**. Raya ne les verrait ni dans le prompt ni dans le graphe.

En indexant immédiatement, on supprime le trou : échange 4 = déjà dans le graphe au moment où l'échange 5 arrive.

**Coût négligeable** : l'indexation fait 1 INSERT + extraction d'entités par regex + N INSERTs d'edges. ~50-100ms, async, pas bloquant.

**Batching prématuré** : j'avais pensé que l'indexation serait coûteuse. En vrai non. Le batch aurait été pertinent si on faisait une analyse LLM groupée, pas pour des inserts SQL.

---

## 🎯 Plan d'implémentation (à faire le 22/04 matin)

### Étape 1 — Fix batch graph_indexer (5 min)
Dans `app/jobs/graph_indexer.py` :
```python
BATCH_SIZE = 1  # Au lieu de 8
INACTIVITY_MINUTES = 1  # Au lieu de 30
```

### Étape 2 — Fix historique in-prompt (10 min)
Dans `app/routes/raya_agent_core.py`, modifier `_load_recent_history()` :
```python
def _load_recent_history(username: str, limit: int = 3) -> list[dict]:
    # ...
    # Tronquer les réponses > 3000 chars :
    for msg in rows:
        user = (msg['user_input'] or '')[:2000]
        assistant = (msg['aria_response'] or '')[:3000]
        ...
```

Et dans `_raya_core_agent` :
```python
history = _load_recent_history(username, limit=3)  # Au lieu de 10
```

### Étape 3 — Test (5 min)
Reposter la question Coullet complète (topo + facture + acomptes) et vérifier :
- Budget tokens au tour 1 : devrait être ~15k au lieu de 45k
- La question ne bute plus sur le garde-fou
- La réponse reste de qualité

### Étape 4 — Vérification aria_rules (5 min)
Vérifier si la règle *"RFAC = Règlement de FACture"* a bien été enregistrée
par Raya ce soir via `remember_preference` :
```sql
SELECT * FROM aria_rules
WHERE username = 'guillaume'
AND rule ILIKE '%rfac%'
ORDER BY id DESC LIMIT 5;
```

Si absent → corriger le prompt pour que Raya appelle plus souvent
`remember_preference` quand elle apprend une règle métier.

---

## 🔄 Le mécanisme "continue" (à voir plus tard)

**Problème** : quand l'utilisateur dit "continue" après un garde-fou, la boucle
redémarre de zéro avec le même historique → re-bute immédiatement.

**Solution propre** (pas urgent) : détecter "continue" / "poursuis" / "va plus loin"
dans la requête et :
- Garder le contexte de la boucle précédente (messages + tool_uses déjà faits)
- Augmenter temporairement le budget de 50%
- Indiquer à Raya dans son prompt système qu'elle reprend une exploration

À mettre dans `raya_agent_core.py` comme paramètre spécial `continuation=True`.

---

## 🎉 Ce qui marche déjà (validation test réel Coullet)

À garder en tête au milieu des ajustements :

1. ✅ **Plus d'hallucinations** : Raya a dit *"aucune facture"* au lieu d'inventer des numéros
2. ✅ **Auto-correction** : a reconnu son erreur sur les factures manquantes sans broncher
3. ✅ **Apprentissage** : a proposé de mémoriser la règle RFAC (à vérifier en DB)
4. ✅ **Conscience des limites** : mentionne explicitement la limitation `sale.order.line`
5. ✅ **Intelligence relationnelle** : a noté que Francine Coullet est aussi contact GIR
6. ✅ **Proactivité** : a remarqué qu'un mail ENEDIS du 13/04 n'a pas encore été traité

L'architecture est bonne. Les ajustements ci-dessus sont des **réglages fins**,
pas des refontes.


---

## 🎯 Ajout 01h45 — Comportement attendu face aux limites de données

**Retour Guillaume** :
> *"Là par exemple pour ma question, j'aurais aimé qu'elle arrive à la conclusion
> qu'elle ne peut pas me donner les chiffres car elle n'a pas accès aux devis,
> aux tarifs des devis, au montant des devis. Et qu'elle me dise : je ne peux pas
> voir le montant des devis correspondants, il faut libérer l'outil."*

### Ce qu'il s'est passé vraiment sur la 3e question

Raya a voulu calculer "montant devis vs reste à facturer". Elle a tenté plusieurs voies :
- `search_odoo` avec divers termes → pas de montants de lignes
- `get_client_360` → montants ligne par ligne pas exposés
- `search_drive` → chercher le PDF du devis
- `search_mail` → chercher un mail qui mentionne le montant
- etc.

Chaque tentative consomme 3-5k tokens. Au bout de 5-6 tentatives, elle explose le budget.

### Le problème de fond (pas juste le budget)

**Même avec 200k tokens de budget**, si Raya s'acharne à contourner une limite, elle finira par exploser. Le problème n'est pas la taille du budget, c'est le **comportement** :

- ✅ Comportement voulu : *"Après 2 tentatives infructueuses pour obtenir les
  montants des lignes de devis, je conclus que sale.order.line n'est pas exposé
  par l'API. Je signale la limitation et je donne les infos dont je dispose."*
- ❌ Comportement actuel : *"J'essaie une 3e voie, puis une 4e, puis une 5e..."*

### Les 2 leviers à activer demain

**Levier 1 — Instruction explicite dans le prompt système**

Ajouter une règle claire dans `_build_agent_system_prompt()` :

```
5. Si après 2 tentatives avec des outils différents, tu ne trouves toujours pas
   une donnée précise, ne persiste pas. Conclus que la donnée n'est pas
   accessible, explique ce qui manque à l'utilisateur (quelle source, quelle
   API, quelle permission), et donne ce que tu as pu assembler jusqu'ici.
   Exemple de bonne formulation : "Je n'arrive pas à obtenir les montants
   détaillés des devis — l'API Odoo actuelle n'expose pas sale.order.line.
   Ce qu'il faudrait : demander à OpenFire d'ouvrir ce modèle. Voici ce que
   je sais quand même : [contexte]."
```

**Levier 2 — Mécanisme de détection de boucle**

Dans `raya_agent_core.py`, détecter si Raya refait le même tool avec des
paramètres similaires. Si oui, lui signaler dans le tool_result :
*"Tu as déjà appelé ce tool avec des paramètres proches 2 fois. Pense à
conclure plutôt que chercher une 3e fois."*

Pseudo-code :
```python
tool_call_history = []  # (tool_name, signature_hash) par iteration
# ... dans la boucle
sig = hash(json.dumps(tool_input, sort_keys=True))
similar_calls = sum(1 for (n, s) in tool_call_history if n == tu["name"])
if similar_calls >= 2:
    # Avertir dans le tool_result
    result_str += "\n\n[SYSTEME: tu as deja appele ce tool plusieurs fois, " \
                  "pense a conclure avec ce que tu as si la donnee n existe pas.]"
tool_call_history.append((tu["name"], sig))
```

### Plan ajusté pour le 22/04 matin

Par ordre d'importance :

1. **Historique 10 → 3 échanges + troncature** (le fix structurel memoire)
2. **Règle n°5 dans le prompt** : s'arrêter après 2 tentatives infructueuses
3. **Batch graph_indexer 8 → 1** (cohérence avec historique réduit)
4. **Détection de boucle de tool calls** (levier 2 ci-dessus)
5. **Budget tokens** : monter à 100k (filet de sécurité pour les questions vraiment complexes après activation des leviers 1 et 2)

Avec ces 5 changements, l'architecture devient robuste :
- Mémoire efficace (plus de saturation prompt)
- Comportement intelligent face aux impasses (reconnaissance explicite des limites)
- Budget large pour les cas où la réflexion est vraiment longue
- Protection anti-boucle pour éviter les dérapages

### Pourquoi c'est important au-delà de Coullet

Ce comportement est **transposable à tous les cas** où Raya peut manquer de
données : mails non indexés, clients absents du graphe, permissions Odoo
limitées, documents SharePoint non crawlés, etc. Le pattern *"chercher →
chercher encore → conclure honnêtement l'impasse"* est générique et précieux.

C'est exactement l'inverse de la v1 qui, confrontée à un trou de données,
**inventait** pour combler. Ici, confrontée à un trou de données, la v2 doit
**nommer le trou** et le signaler.


---

## 🔧 Ajout 02h10 — Dimensionnement final du budget

**Question Guillaume** :
> *"Je te pose parfois des questions complexes et te demande parfois des audits
> profonds, 200k de réflexion est-ce suffisant ?"*

### Analyse par cas d'usage

| Cas d'usage | Tokens typiques | 200k ? | 300k ? |
|---|---|---|---|
| Question simple | 5-20k | ✅ | ✅ |
| Topo client (Coullet) | 40-80k | ✅ | ✅ |
| Calcul croisé (reste-à-facturer) | 60-100k | ✅ marge | ✅ large marge |
| Audit profond (impayés + patterns) | 150-300k | ⚠️ juste | ✅ ok |
| Audit très profond (multi-dimension) | 300-500k | ❌ | ⚠️ juste |

### Décision : 300k

Paramètres finaux pour le fix de demain :
```python
MAX_ITERATIONS = 20          # etait 15
MAX_DURATION_SECONDS = 120   # etait 60
MAX_TOKENS_BUDGET = 300_000  # etait 60_000
```

### Rationnel

1. **Couvre 99% des cas** y compris les vrais audits profonds
2. **Coût : ~1.50 € par question qui atteint 300k**
3. **Budget = filet de sécurité, pas objectif**

Avec les 4 autres fix (règle stop-après-2, détection boucle, historique
tronqué, graphe synchrone), Raya atteindra rarement 300k. Quand elle
l'atteindra quand même, ce sera le signal d'une question légitimement
énorme OU d'un bug à identifier.

### Philosophie retenue

*"Ne pas empêcher la réflexion, juste avertir quand ça dérape."*

Le garde-fou n'est plus là pour limiter l'ambition de Raya, mais pour
détecter les anomalies (vraies ou de comportement). Le fait qu'il se
déclenche devient une information, pas une contrainte.


---

## 💡 IDÉE MAJEURE 02h25 — Budget à 2 niveaux (Guillaume)

**L'idée de Guillaume** (reformulée) :

> Au lieu d'un budget unique (qui doit être gros pour couvrir les audits mais
> coûte cher en cas de boucle sur question simple), avoir 2 niveaux :
> - **Standard** (100-150k) : s'applique à toutes les questions par défaut
> - **Étendu** (300-500k) : débloqué explicitement par l'utilisateur pour
>   les questions qu'il sait complexes

**Quand Raya atteint le budget standard**, au lieu du classique
*"tu veux que je continue ?"*, elle rend **une synthèse partielle** de ce
qu'elle a trouvé jusqu'ici + propose **un bouton de déblocage**.

### Pourquoi cette approche est supérieure au budget unique

1. **Protection par défaut** : 99% des questions sont simples, si Raya
   boucle elle s'arrête vite (économie + sécurité financière)
2. **Intention consciente** : pour les audits profonds, l'utilisateur
   valide le surcoût en connaissance de cause
3. **Diagnostic automatique** : le déclenchement du seuil standard est
   en soi une information utile ("attention, cette question sort de
   l'ordinaire")
4. **Contrôle du coût** : pas de surprise de facture. Dérapage plafonné
   au seuil standard tant que l'utilisateur n'autorise pas le déblocage

### Architecture technique

**Dans `raya_agent_core.py`** :
```python
MAX_TOKENS_STANDARD = 150_000   # budget par defaut
MAX_TOKENS_EXTENDED = 500_000   # budget si l utilisateur debloque
```

**Dans la signature de `_raya_core_agent`** :
```python
def _raya_core_agent(request, payload, username, tenant_id):
    # Lire un flag depuis payload :
    extended_budget = getattr(payload, 'extended_budget', False)
    max_tokens = MAX_TOKENS_EXTENDED if extended_budget else MAX_TOKENS_STANDARD
```

**Dans le flux** :
1. Standard 150k atteint → Raya rend synthèse partielle + marqueur
   spécial dans la réponse (ex: `{"needs_extended_budget": true}`)
2. Le front détecte ce marqueur → affiche bouton "Continuer (jusqu'à 500k)"
3. Si clic → nouvelle requête avec `extended_budget=true` ET contexte
   de la boucle précédente passé en référence (via `continuation_id`)
4. Si stop → on garde la synthèse partielle dans aria_memory

### Variantes à considérer

**Option A — Bouton dans la réponse** (RECOMMANDÉE)
Raya atteint 150k → synthèse partielle + bouton *"Continuer 500k"*.
Clic → relance avec budget étendu ET contexte préservé.

**Option B — Préfixe explicite dans la question**
`##audit Fais-moi un bilan complet des impayés du semestre`.
Donne 500k dès le départ. Utile quand l'utilisateur sait d'avance.

**Option C — Toggle "Mode audit" dans l'UI**
Switch qui donne 500k à toutes les questions de la session.
Risque d'oubli → surcoût. Déconseillé.

**Reco** : **A en principal, B en secours**. Pas C.

### Gain financier estimé

Sur 1000 questions/mois :
- Budget unique à 500k : ~1000€/mois (pessimiste)
- Budget double-seuil 150k/500k : ~300-400€/mois (estimation)
  - 90% × 0.50€ (standard 150k) + 10% × 2.50€ (étendu 500k)

### Ajout au plan du 22/04

Le plan initial à 300k de budget unique est **remplacé** par ce plan à
2 niveaux :

```python
MAX_ITERATIONS_STANDARD = 15
MAX_ITERATIONS_EXTENDED = 30

MAX_DURATION_STANDARD = 60    # 1 minute
MAX_DURATION_EXTENDED = 180   # 3 minutes

MAX_TOKENS_STANDARD = 150_000
MAX_TOKENS_EXTENDED = 500_000
```

### Travail nécessaire

- ~15 min de code en backend (double seuil + flag)
- ~20 min côté front (détecter marqueur + afficher bouton de déblocage)
- Mécanisme de continuation propre (préserver contexte boucle précédente)

### Remarque

Cette idée résout simultanément :
- Le problème du budget insuffisant sur audits (validé : 500k si débloqué)
- Le problème des dérapages coûteux (contenu à 150k par défaut)
- Le problème de "continue" qui repart de zéro (continuation propre)
- Le problème de visibilité du coût (l'utilisateur voit qu'il débloque)

**C'est l'idée la plus aboutie architecturalement de la session.**
