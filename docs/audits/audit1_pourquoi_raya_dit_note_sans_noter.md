# Audit 1 — Pourquoi Raya dit "C'est noté" sans noter

**Date** : 02/05/2026  
**Demandé par** : Guillaume  
**Contexte** : Raya a répondu "Je note — je dois toujours appeler list_my_connections en premier... C'est noté ! 👌" mais aucune règle nouvelle n'apparaît dans `aria_rules` (vérifié en DB : la règle la plus récente date du 01/05).

---

## 🎯 Diagnostic en une phrase

Raya a un **réflexe verbal hérité du système v1** ("C'est noté !") qu'elle utilise quand elle se sent mémoriser quelque chose. Mais cette fois elle **n'a déclenché AUCUN mécanisme de mémorisation** : ni le tag v1 `[ACTION:LEARN]`, ni le tool v2 `remember_preference`.

**C'est de l'hallucination soft** : elle dit faire une chose qu'elle n'a pas faite.

---

## 🔍 Vérifications faites

### 1. Le contenu exact de la réponse (DB `aria_memory.id=422`)

> "Et je note — je dois **toujours appeler `list_my_connections` en premier** pour avoir les vraies adresses, sans jamais te les redemander. C'est noté ! 👌"

**Pas un seul tag `[ACTION:LEARN:...]` dans la réponse.**

### 2. La table `aria_rules`

Aucune règle créée le 02/05. La plus récente date du 01/05 à 06:40. Donc aucun appel à `remember_preference` non plus.

### 3. Mode actif (v1 ou v2)

`app/routes/raya.py:158` :
```python
core_fn = _raya_core_agent if _is_agent_mode() else _raya_core
```

Le feature flag est `RAYA_AGENT_MODE` (env var). Pour savoir lequel tourne en prod, il faudrait lire la config Railway ou ajouter un log. Mais peu importe : dans les **deux cas**, rien n'a été appelé.

---

## 🔬 Les 2 systèmes de mémorisation existants

### Système v1 — tags `[ACTION:LEARN:category|rule]`

- Raya **génère un tag dans le texte** de sa réponse.
- Après la réponse, le code parse le texte (`memory_actions._parse_learn_actions`) et écrit en DB.
- Encore actif via `app/routes/actions/__init__.py:81` quand `execute_actions` est appelé.
- **Appelé en flow v1** (`raya_helpers.py:232`).
- **Pas appelé en flow v2** (`raya_agent_core.py` n'a aucune référence).

### Système v2 — tool `remember_preference`

- Raya **appelle explicitement le tool** dans la boucle agent Anthropic.
- L'executor `_execute_remember_preference` (raya_tool_executors.py) écrit en DB via `rule_validator`.
- Tool bien déclaré dans `raya_tools.py:469` et bien exposé.

---

## 🐛 Pourquoi Raya dit "C'est noté" sans rien faire

### Cause directe : le system prompt l'incite

Dans `app/routes/prompt_guardrails.py` (lignes 53-65) :

> Quand tu apprends une regle via [ACTION:LEARN], confirme UNIQUEMENT avec une phrase courte et naturelle ("C'est noté !", "Compris, je retiens ça.", etc.) puis ARRÊTE.

Et plus haut dans `prompt_actions.py:36-37` :

> [ACTION:LEARN:mail_filter|autoriser: email@domaine.fr]  
> [ACTION:LEARN:mail_filter|bloquer: promo@xyz.fr]

### Cause profonde : aucune obligation explicite de déclencher l'action

Le system prompt **apprend à dire "C'est noté"** mais **ne dit nulle part** :

> "Si tu dis 'C'est noté', tu DOIS soit générer un tag [ACTION:LEARN:...], soit appeler le tool remember_preference. Sinon ne le dis pas."

Du coup, dans le contexte de la conversation, Raya s'est sentie en train d'apprendre une règle métier ("toujours appeler list_my_connections en premier"), elle a utilisé sa formule verbale ("C'est noté"), mais **elle n'a déclenché aucune action**.

### Hypothèse complémentaire — pourquoi elle a oublié l'action

Plusieurs raisons possibles, dans l'ordre de probabilité :

1. **La règle est déjà dans le system prompt** : on a poussé tout à l'heure le bloc HONNETETE qui dit "Pour toute question sur tes connexions, appelle list_my_connections AVANT de répondre". Raya l'a peut-être interprétée comme déjà acquise → pas besoin d'apprentissage explicite.
2. **Confusion tags v1 vs tool v2** : avec deux systèmes parallèles, Raya hésite peut-être sur lequel utiliser et ne fait ni l'un ni l'autre.
3. **Le mot "note" est trop léger** : pour Raya, "noter mentalement" ≠ "déclencher l'apprentissage formel". Elle considère que c'est juste du verbal.

---

## 🎯 Le vrai problème de fond

Le système actuel a **3 sources de vérité différentes** sur "comment Raya apprend une règle" :

1. `prompt_guardrails.py` parle de `[ACTION:LEARN]` (v1)
2. `prompt_actions.py` montre des exemples de `[ACTION:LEARN]` (v1)
3. `raya_tools.py` expose `remember_preference` (v2)

Aucun de ces 3 endroits ne dit clairement à Raya : **"Voici LE bon mécanisme à utiliser maintenant, voici quand l'utiliser, voici l'effet exact."**

Résultat : Raya choisit de manière probabiliste entre les 3, et parfois ne choisit aucun.

---

## 🔧 Recommandations (à valider à ton retour)

### Priorité 1 — Régler le bug "C'est noté" sans effet

**Choix A — Renforcer le system prompt** (rapide, peu invasif)

Ajouter une règle stricte dans `aria_context.py` ou `prompt_guardrails.py` :

```
COHERENCE PAROLE/ACTE :
Si tu dis "c'est noté", "je retiens", "je mémorise" ou similaire, tu DOIS 
appeler le tool remember_preference dans le même tour. Sinon, ne le dis pas.
Une promesse de mémorisation sans action est un mensonge à l'utilisateur.
```

**Avantage** : 5 lignes, déployable en 5 min, cohérent avec le bloc HONNETETE déjà en place.  
**Inconvénient** : repose sur la discipline de Raya (mais le bloc HONNETETE marche bien jusqu'ici).

**Choix B — Brancher le parser v1 dans le flow v2**

Ajouter `_handle_memory_actions(raya_response, ...)` dans `raya_agent_core.py` après la boucle agent.

**Avantage** : bug fixé même si Raya génère un tag v1.  
**Inconvénient** : maintien de 2 systèmes, dette technique.

**Choix C — Faire les 2** (recommandé)

A pour pousser la cohérence, B en filet de sécurité.

### Priorité 2 — Nettoyer les 2 systèmes (plus tard)

Décider lequel garder, supprimer l'autre, harmoniser le system prompt. C'est le sujet d'un audit séparé.

---

## 📝 Mon avis

Je recommande **Choix A seul** dans un premier temps, parce que :

1. C'est **5 lignes** dans le system prompt.
2. Ça reste cohérent avec ton choix précédent (le bloc HONNETETE qui marche).
3. Tu pourras vérifier en 1 question si ça suffit.
4. Si ça ne suffit pas, on ajoute B en filet.

Je n'ai **rien commit**. À ton retour, dis-moi A / B / C / autre, et je code.

---

## 📊 Tableau de vérifications

| Vérification | Résultat |
|---|---|
| Tool `remember_preference` existe | ✅ OUI |
| Tool `remember_preference` fonctionne | ✅ OUI (testable) |
| Tag v1 `[ACTION:LEARN]` parsé en flow v1 | ✅ OUI |
| Tag v1 `[ACTION:LEARN]` parsé en flow v2 | ❌ NON |
| Tag dans la réponse Raya du 02/05 (id=422) | ❌ AUCUN |
| Règle créée dans aria_rules le 02/05 | ❌ AUCUNE |
| System prompt parle de tags v1 | ✅ OUI (prompt_guardrails:54) |
| System prompt parle du tool v2 | ❌ NON (jamais explicité) |

---

## 📁 Fichiers concernés

- `app/routes/raya.py:158` — feature flag v1/v2
- `app/routes/raya_agent_core.py` — flow v2 (sans parser tags)
- `app/routes/raya_helpers.py:232` — flow v1 (avec parser tags)
- `app/routes/raya_tools.py:469` — tool `remember_preference`
- `app/routes/raya_tool_executors.py` — executor du tool
- `app/routes/actions/memory_actions.py` — parser v1
- `app/routes/actions/__init__.py:81` — orchestrateur v1
- `app/routes/prompt_guardrails.py:54` — mention tags v1
- `app/routes/prompt_actions.py:36-37` — exemples tags v1
- `app/routes/aria_context.py` — system prompt principal (où ajouter Choix A)
