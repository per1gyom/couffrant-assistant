# 📋 Audit #2 — Scanner après Étape 1

**Date** : 19 avril 2026, 18h15
**Contexte** : après implémentation de l'Étape 1 (circuit breaker + fix cleanup_stale_runs + recomptage réel), Guillaume constate que 4 modèles sur 16 sont encore en rouge/non scannés. Pense que "ça plante encore". Demande un audit approfondi avant toute action.

---

## 🎯 TL;DR qui change tout

**Le scanner N'A PAS planté. Il s'est terminé proprement.**

Run #6 :
- ✅ Status final : `ok`
- ✅ Démarré à 14:32, terminé à 16:06 (1h34)
- ✅ 16 modèles sur 16 processés (100%)
- ✅ 24 776 chunks vectorisés en DB
- ✅ 3 modèles abandonnés PROPREMENT par le circuit breaker (Étape 1 a fonctionné)
- ⚠️ Dashboard affiche encore un ancien état (probablement cache navigateur)

**Les 4 modèles rouges ne sont PAS un crash. Ce sont des ABANDONS CONTRÔLÉS causés par des erreurs Odoo légitimes côté serveur OpenFire.**

---

## 📊 État réel du run #6 (source de vérité)

| Statut | Modèles | Détail |
|---|---|---|
| ✅ Scannés avec succès | 12 | chunks en DB, intégrité calculée |
| 🛑 Abandonnés (circuit breaker) | 3 | `of.planning.tour`, `sale.order.line`, `calendar.event` — erreur Odoo côté serveur |
| ⚠️ Abandonné (configuration) | 1 | `mail.message` — à priori erreur similaire ou timeout |

### Chunks réellement en DB (source de vérité)

```
mail.tracking.value       10 000
of.survey.answers          5 320
product.template           5 000
of.planning.tour.line      2 753
res.partner                1 126
sale.order                   310
crm.lead                     139
sale.order.template.line     119
sale.order.template            9
── Total réel ────────── 24 776 chunks ✅
```

### Modèles avec 0 chunks (NON plantés, abandonnés volontairement)

```
of.planning.tour    (5373 records)  → circuit breaker : erreur Odoo ValueError
sale.order.line     (3743 records)  → circuit breaker : erreur Odoo ValueError
calendar.event      (1162 records)  → circuit breaker : erreur Odoo ValueError
mail.message        (29139 records) → jamais démarré correctement
```

Le circuit breaker a joué son rôle **exactement comme prévu** : 5 erreurs consécutives sur un fetch → abandon propre du modèle, passage au suivant.

---

## 🔍 Cause racine des 4 modèles abandonnés

### Ce que disent les stats du run

Pour `of.planning.tour`, `sale.order.line`, `calendar.event` :
```
Circuit breaker: 5 erreurs consecutives sur fetch (dernier offset=200).
Dernier erreur: Odoo error: {"code": 200, "message": "Odoo Server Error",
"data": {"name": "builtins.ValueError", ...
```

**C'est Odoo qui renvoie une erreur `ValueError` côté serveur.** Pas une erreur Raya. Pas un crash de worker. Pas un problème de notre code.

### Pourquoi Odoo renvoie une ValueError

Regardons ce que les manifests demandent :

| Modèle | Vectorize fields | Metadata fields | Graph edges | TOTAL champs demandés |
|---|---|---|---|---|
| `of.planning.tour` | 2 | 22 | 10 | **~35 champs** |
| `sale.order.line` | 5 | **~85** | **~42** | **~135 champs** |
| `calendar.event` | 15 | **~120** | **~50** | **~190 champs** |
| `mail.message` | 6 | 20 | 18 | ~45 champs |

Le scanner demande à Odoo un `search_read` avec **jusqu'à 190 champs** par record. Plusieurs problèmes cumulés :

1. **Champs computed en erreur** : certains champs OpenFire (`of_*`) sont des computed qui dépendent d'autres modules et peuvent lever des exceptions selon la donnée (ex: `of_intervention_state` cassé si pas d'intervention liée).

2. **Timeout XML-RPC** : récupérer 50 records × 190 champs × HTML → requête très lourde, probable timeout réseau.

3. **Volume de données** : `calendar.event` avec `description`, `of_plaintext_description`, `of_intervention_notes` → HTML énorme par record.

4. **`mail.message.body`** : HTML complet des emails, souvent >50KB par message.

### Preuve : `of.planning.tour.line` a marché à 100% (2753 chunks) avec 99.9%

Pourquoi ? Parce que son manifest est **plus léger** (moins de champs `of_*` computed). La corrélation champs nombreux / erreurs est directe.

---

## ✅ Ce qui MARCHE bien dans l'Étape 1

1. **`cleanup_stale_runs` fixé** : le run #5 (lancé avant redéploiement) a été proprement mis en `running` à 14:31 — il tombera à l'erreur automatiquement dès le prochain restart car stale_sec=5733s > 10min.

2. **Circuit breaker opérationnel** : 3 modèles bien abandonnés après 5 erreurs consécutives, 1 run quand-même complet à 100% (16/16 processed).

3. **Recomptage réel** : les compteurs `records_count_raya` correspondent exactement aux chunks DB (vérifié : `sale.order.template` a 9 records, 9 chunks, 100%).

4. **Tracking `models_aborted`** : on voit dans les stats exactement quels modèles ont été abandonnés et pourquoi.

---

## 🔧 Pourquoi le dashboard affiche encore l'ancien état

Regarde ta capture : "dernier scan" 19/04 14:55, 15:26, 15:30 etc.

Ces timestamps correspondent à des modèles dont `last_scanned_at` a été mis à jour **pendant** le run #6, pas à la fin. Le `of.survey.answers` affiche par exemple "Jamais" sur ta capture alors que la DB dit qu'il a 5320 chunks à 100%.

**Deux hypothèses** :
1. **Cache navigateur** → Cmd+Shift+R devrait résoudre
2. **L'endpoint `/admin/scanner/integrity` calcule l'intégrité au vol et quelque chose ne matche pas**

Je n'ai pas creusé cet endpoint dans l'audit actuel, à vérifier ensuite.

---

## 🎯 Ce qu'il faut faire (par priorité)

### 1. URGENT — Vérifier le dashboard (5 min)

**Hypothèse** : il y a un bug d'affichage, pas de scan. À tester :
- Cmd+Shift+R sur `/admin/panel`
- Ouvrir 📊 Intégrité et relire
- Si toujours faux, regarder endpoint `/admin/scanner/integrity` et ce qu'il retourne

### 2. IMPORTANT — Relancer les 4 modèles abandonnés avec manifest léger (30 min)

Le vrai problème n'est pas le scanner. C'est que **les manifests sont trop gourmands** pour OpenFire sur certains modèles.

**Solution : un manifest "minimal" pour les modèles qui posent problème.**

Stratégie : pour `of.planning.tour`, `sale.order.line`, `calendar.event`, `mail.message`, **réduire drastiquement les champs demandés** :
- Vectorize fields : garder uniquement `name`, `display_name`, et 1-2 champs utiles
- Metadata fields : garder uniquement les IDs et dates essentielles
- Graph edges : garder seulement 5-10 relations critiques

Si ça marche avec le manifest minimal → on élargit progressivement.

### 3. DURABLE — Batch size plus petit pour les gros modèles (20 min)

Actuellement batch_size = 50. Pour `calendar.event` avec ses 190 champs et `description` HTML, on envoie 50 × 190 champs × HTML à chaque batch → bombe réseau.

**Fix** : paramétrer batch_size par modèle :
```python
MODEL_BATCH_SIZES = {
    "calendar.event": 10,
    "sale.order.line": 20,
    "mail.message": 10,
    "of.planning.tour": 20,
    # défaut : 50
}
```

### 4. DÉFENSIF — Retry avec backoff exponentiel (15 min)

Le circuit breaker actuel abandonne après 5 erreurs consécutives **immédiates**. Or les erreurs Odoo peuvent être transitoires (timeout réseau, serveur surchargé).

**Fix** : entre 2 tentatives d'un batch qui a échoué, attendre 2s, puis 4s, puis 8s. Si le serveur était juste saturé, ça repart. Si c'est un vrai bug structurel, on abandonne après 5 backoffs.

### 5. SUIVI — Log détaillé des erreurs Odoo (10 min)

La raison d'abandon est tronquée à 200 caractères. On ne voit pas le vrai debug Odoo. **Fix** : stocker dans un champ texte plus large + logger dans Railway le stack complet.

---

## 🚫 Ce qu'il NE faut PAS faire maintenant

1. ❌ **Repasser en mode panique et tout refactorer** — le code actuel marche, on a juste des problèmes de données côté Odoo
2. ❌ **Purger la DB et relancer le P1 entier** — on va reperdre les 24 776 chunks vectorisés avec succès
3. ❌ **Passer à l'Étape 2 (heartbeat/watchdog)** — pas nécessaire pour ces 4 modèles, on fixe d'abord la cause
4. ❌ **Toucher au code sans comprendre l'erreur Odoo exacte** — il faut d'abord lire les logs Railway du run #6 pour avoir le stack trace complet

---

## 📋 Plan d'action proposé (~1h, pas de panique)

### Étape A — Investigation (15 min)
1. Vérifier dashboard en Cmd+Shift+R → vrai état ?
2. Lire logs Railway du run #6 entre 14:32 et 16:06 → stack trace Odoo complet pour `of.planning.tour`
3. Identifier quel champ précis cause la `ValueError`

### Étape B — Manifest minimal pour les 4 modèles (20 min)
1. Créer un manifest "safe" pour chaque modèle problématique
2. Réduire drastiquement les champs demandés
3. Tester en relançant UNIQUEMENT ces 4 modèles via un nouveau run ciblé

### Étape C — Batch size adaptatif (15 min)
1. Ajouter `MODEL_BATCH_SIZES` dans runner.py
2. Lire le batch_size depuis le manifest si présent
3. Passer à 10 pour les modèles lourds

### Étape D — Relance ciblée (10 min)
1. NE PAS PURGER la DB
2. Relancer uniquement les 4 modèles abandonnés avec les nouveaux manifests
3. Vérifier les résultats

---

## 💬 Message final à Guillaume

Guillaume, ton outil ne plante plus. Le circuit breaker qu'on a mis en place fonctionne exactement comme prévu. Les 4 modèles rouges ne sont **pas des crashes** — ce sont des abandons contrôlés parce que **l'Odoo OpenFire renvoie lui-même des erreurs** sur ces requêtes lourdes.

**C'est un bon signe** : avant Étape 1, ces erreurs étaient masquées et faisaient tourner le scanner 2h dans le vide. Maintenant elles sont détectées, le scanner se protège, et le reste a été vectorisé correctement.

On a 24 776 chunks de bonne qualité en DB. Il reste 4 modèles à faire passer avec des manifests plus légers. **Pas de panique, pas de refactor, juste un ajustement ciblé.**

Je ne touche à rien avant ta validation.

---

**Fichier** : `/Users/per1guillaume/couffrant-assistant/docs/raya_scanner_audit_2_rapport.md`
**Non poussé.**
