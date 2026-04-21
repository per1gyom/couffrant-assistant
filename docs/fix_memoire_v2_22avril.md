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
