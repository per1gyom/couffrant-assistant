# Étape 4 terminée — Raya v2 mode agent prête

**Date** : 21 avril 2026 (fin de session marathon)
**État** : ✅ **Toutes les briques techniques en place**
**Prochaine action** : test en conditions réelles avec `RAYA_AGENT_MODE=true`

---

## 🎯 Ce qui est fait

### Code v2 (12 commits)

| Commit | Contenu | Lignes |
|---|---|---|
| `79f822d` | Tools + executeurs | +1053 |
| `a3bf64f` | Boucle agent core | +433 |
| `b82d7b9` | llm_complete support tools | +22 |
| `7291672` | Feature flag RAYA_AGENT_MODE | +14 |
| `5ef1898` | Corrections imports/signatures | ±74 |
| `4b2806a` | Prompt caching Anthropic | +47 |
| `0c11904` | graph_indexer (memoire longue) | +444 |
| `300c293` | Branchement scheduler | +18 |

**Total** : ~2100 lignes de code v2 ajoutées, **aucune modification destructrice de la v1**.

### Architecture opérationnelle

```
Utilisateur pose une question
  ↓
POST /raya
  ↓
RAYA_AGENT_MODE=true ?
  ├─ Oui → _raya_core_agent (v2 boucle agent)
  └─ Non → _raya_core (v1 single-shot, comportement actuel)
  ↓ (cas v2)
Boucle Anthropic tool use native
  - Prompt systeme court (~800 chars, cache 90pct)
  - Historique 10 derniers echanges
  - 23 tools disponibles
  - Max 10 iterations, 30s, 30k tokens
  ↓ a chaque iteration
Claude decide : tool_use ou end_turn ?
  ├─ tool_use → execute_tool → dispatch vers executeur
  └─ end_turn → reponse finale, sauvegarde dans aria_memory

En parallele, toutes les 3 min :
Job graph_indexer
  - Indexe les conversations dans le graphe
  - Cree edges entre conversations et entites citees
  - Memoire longue accessible via search_graph
```

### Feature flags disponibles

| Flag | Defaut | Role |
|---|---|---|
| `RAYA_AGENT_MODE` | `false` | Active la v2 mode agent |
| `SCHEDULER_GRAPH_INDEXER_ENABLED` | `true` | Indexation auto des conversations |
| `LLM_MODEL_DEEP` | `claude-opus-4-7` | Modele Opus pour la boucle |

---

## ⏳ Ce qu'il reste à faire

### Priorité 1 — Avant le premier test
1. **Push GitHub** : 12 commits en attente (auth à régler, SSH recommandé)
2. **Déployer sur Railway** : une fois push fait, Railway redéploie tout seul
3. **Activer la v2 en test** :
   ```
   RAYA_AGENT_MODE=true dans Railway Variables
   ```

### Priorité 2 — Premier test réel
4. Reposer la question **Legroux** (qui a déclenché toute cette refonte)
5. Vérifier qu'elle ne hallucine plus
6. Valider que la boucle agent fonctionne (metadonnees `agent_iterations`, `agent_duration_s`)

### Priorité 3 — Après validation
7. Désactiver les tags v1 progressivement (suppression du code mort)
8. Activer le Batch API Anthropic sur `mail_analysis` (50% d'économie)
9. Tester l'extended thinking sur les questions très complexes

---

## 🔍 Métriques à surveiller au premier test

Le retour API de `_raya_core_agent` contient :
```json
{
  "answer": "...",
  "agent_iterations": 3,        // combien de tours de boucle
  "agent_duration_s": 8.2,       // temps total
  "agent_tokens": 12450,         // tokens cumules
  "agent_stopped_by": null       // si "iterations"/"timeout"/"tokens": garde-fou declenche
}
```

Si `agent_stopped_by` est renseigné pour une question simple → il y a un souci dans la boucle (Claude ne converge pas).

---

## 🛟 Retour à la v1 en cas de probleme

Trois chemins :
1. **Flag** : `RAYA_AGENT_MODE=false` → bascule instantanée
2. **Tag** : `git checkout v1-single-shot`
3. **Branche** : `git checkout archive/raya-v1-single-shot-21avril2026`

**Aucun risque de perdre la v1.**

---

## 📚 Documents de référence

- `docs/architecture_agent_v1.md` — specs v2 complètes (470 lignes)
- `docs/audit_v1_vers_v2.md` — correspondance tags v1 → tools v2 (270 lignes)
- `docs/archive_v1_single_shot.md` — description figée de la v1
- `docs/a_faire.md` — tâches manuelles côté Guillaume
- `docs/vision_architecture_raya.md` — vision fondatrice
- `docs/plan_resilience_et_securite.md` — plan sécurité 7 étapes
