# Archive — Raya v1 single-shot (21 avril 2026)

**Date de gel** : 21 avril 2026, ~15h
**Commit au moment du gel** : `463608c` sur `main`
**Tag** : `v1-single-shot`
**Branche d'archive** : `archive/raya-v1-single-shot-21avril2026`

---

## 🎯 Objectif de ce document

Figer précisément l'état de Raya v1 au moment du passage en v2 mode
agent. Permet à tout moment de comparer v2 ↔ v1 ou de revenir à v1 si
nécessaire.

---

## 🧬 Caractéristiques techniques de la v1

### Architecture
- **Mode inference single-shot** : 1 question = 1 appel API = 1 réponse
- **Pas de boucle agent**, pas de `tool use` natif Anthropic
- **Tags textuels** dans la réponse de Claude (ex : `[ACTION:SEND_MAIL:...]`)
- Extraction / exécution des tags en post-traitement
- Routage tier : Haiku pour classification, Sonnet/Opus pour exécution

### Prompt système
- Très long : ~15 000 à 20 000 caractères
- Compose plusieurs blocs : `CORE_RULES`, `GUARDRAILS`, `prompt_actions`,
  `prompt_blocks`, `prompt_blocks_extra` (topics, narrative, alerts,
  maturity, team, ton, report, web_info)
- Règles anti-hallucination répétées jusqu'à 3 fois

### Actions disponibles
- **51 tags ACTION** en 10 familles (recherche, mails, calendar, Teams,
  Drive, créations, mémoire, confirmations, tâches, divers)

### Mémoire
- **30 derniers échanges** envoyés dans chaque appel
- `hot_summary` régénéré périodiquement via synthèse
- `aria_rules` pour les règles apprises
- Pas de graphe des conversations (faits isolés, non rattachés aux
  entités métier)

---

## ❌ Limites constatées (déclencheurs de la refonte)

1. **Hallucinations graves** : 21/04 matin, Raya a inventé un client
   "Frédéric Legroux / Christiane Legroux" avec des devis "D25-0025",
   "S01071", "S01072", "S01198" et des factures "FA2025-0019",
   "FA2025-0142" — **totalement fabriqués** avec montants plausibles
   (24722€, 7416€, 17305€).

2. **Incapacité de croiser** les sources en une passe : Raya répondait
   avec Odoo seul alors que les mails contenaient l'information clé.

3. **Accumulation de règles** : chaque nouveau fix ajoutait 50-100
   caractères de prompt. Résultat : prompt final trop lourd, Claude
   perdait la cohérence.

4. **Sous-exploitation du web search** : Raya attendait qu'on lui dise
   "regarde sur internet" au lieu de chercher spontanément les termes
   qu'elle ne maîtrisait pas.

5. **Historique mal exploité** : "Raya avec Alzheimer" selon Guillaume
   le 21/04 — elle ne consulte pas l'historique au-delà des 30 derniers
   échanges bruts.

---

## 🗂️ Comment retrouver la v1

### Via le tag git
```bash
git checkout v1-single-shot
```

### Via la branche d'archive
```bash
git checkout archive/raya-v1-single-shot-21avril2026
```

### En production (après déploiement v2)
Variable d'environnement Railway :
```
RAYA_AGENT_MODE=false
```
Raya repasse immédiatement en comportement v1 (au redémarrage du
conteneur).

---

## 📊 Fichiers clés de la v1

### Orchestration
- `app/routes/raya.py` : endpoint principal
- `app/routes/raya_helpers.py` : `_raya_core()` single-shot
- `app/routes/aria_context.py` : build_system_prompt() long

### Prompt
- `app/routes/prompt_actions.py` : descriptions des 51 tags
- `app/routes/prompt_guardrails.py` : garde-fous détaillés
- `app/routes/prompt_blocks.py` + `prompt_blocks_extra.py` : blocs

### Actions
- `app/routes/actions/*.py` : handlers de chaque famille d'action

### Connecteurs (préservés en v2)
- `app/connectors/odoo.py`, `odoo_enrich.py`
- `app/connectors/drive_read.py`, `drive_actions.py`
- `app/connectors/outlook*.py`, `gmail_connector2.py`
- `app/connectors/teams_actions.py`

---

## 📝 Notes de gel

- Le système fonctionne en production au moment du gel
- La v1 peut être utilisée telle quelle si la v2 déraille
- Les 3 hallucinations constatées n'empêchent pas l'usage quotidien
  avec vigilance de l'utilisateur (Guillaume les détectait et
  corrigeait en conversation)
- Aucun bug bloquant, juste une architecture qui a atteint ses limites

---

## 🔜 Suite : v2 mode agent

Voir `docs/architecture_agent_v1.md` et `docs/audit_v1_vers_v2.md`.
