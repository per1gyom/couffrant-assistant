# Audit v1 → v2 — Correspondance tags ACTION vers tools

**Date** : 21 avril 2026
**Objectif** : inventaire exhaustif des 51 tags ACTION de la v1 et
décision pour chacun (gardé, remplacé, supprimé) dans la v2.

---

## 📊 Catégorisation des 51 tags

### 🔍 Catégorie 1 — Recherche / lecture (13 tags → 6 tools)

| Tag v1 | Décision v2 | Tool v2 |
|---|---|---|
| `[ACTION:ODOO_SEARCH]` | Fusionner | `search_odoo` |
| `[ACTION:ODOO_SEMANTIC]` | Fusionner | `search_odoo` |
| `[ACTION:ODOO_CLIENT_360]` | Conserver | `get_client_360` |
| `[ACTION:ODOO_MODELS]` | Supprimer (outil de debug, plus nécessaire) | — |
| `[ACTION:SEARCH]` | Remplacer | `search_graph` + `search_conversations` |
| `[ACTION:LISTDRIVE]` | Fusionner | `search_drive` |
| `[ACTION:SEARCHDRIVE]` | Fusionner | `search_drive` |
| `[ACTION:READDRIVE]` | Conserver | `read_drive_file` |
| `[ACTION:READ]` | Conserver | `read_mail` |
| `[ACTION:READBODY]` | Fusionner | `read_mail` |
| `[ACTION:SEARCH_CONTACTS]` | Fusionner | `search_odoo` (sur res.partner) |
| `[ACTION:ODOO_NOTE]` | À voir (interne aux requêtes Odoo) | — |
| **Nouveau en v2** | — | `search_mail` |
| **Nouveau en v2** | — | `search_conversations` |
| **Nouveau en v2** | — | `search_graph` |
| **Nouveau en v2** | — | `web_search` (déjà natif) |
| **Nouveau en v2** | — | `get_weather` (déjà existant) |

### ✍️ Catégorie 2 — Mails (6 tags → 4 tools)

| Tag v1 | Décision v2 | Tool v2 |
|---|---|---|
| `[ACTION:SEND_MAIL]` | Conserver | `send_mail` |
| `[ACTION:SEND_GMAIL]` | Fusionner | `send_mail` avec param `provider` |
| `[ACTION:REPLY]` | Conserver | `reply_to_mail` |
| `[ACTION:ARCHIVE]` | Conserver | `archive_mail` |
| `[ACTION:DELETE]` | Conserver | `delete_mail` |

### 📅 Catégorie 3 — Calendrier / Events (4 tags → 3 tools)

| Tag v1 | Décision v2 | Tool v2 |
|---|---|---|
| `[ACTION:CREATEEVENT]` | Conserver | `create_calendar_event` |
| `[ACTION:UPDATE_EVENT]` | Conserver | `update_calendar_event` |
| `[ACTION:DELETE_EVENT]` | Conserver | `delete_calendar_event` |
| `[ACTION:SHARE_EVENT]` | Fusionner avec create | `create_calendar_event` avec attendees |


### 💬 Catégorie 4 — Teams / messaging (11 tags → 5 tools)

| Tag v1 | Décision v2 | Tool v2 |
|---|---|---|
| `[ACTION:TEAMS_LIST]` | Fusionner | `list_teams_channels` |
| `[ACTION:TEAMS_CHANNEL]` | Fusionner | `read_teams_channel` |
| `[ACTION:TEAMS_CHATS]` | Fusionner | `list_teams_chats` |
| `[ACTION:TEAMS_HISTORY]` | Fusionner | `read_teams_channel` avec param date |
| `[ACTION:TEAMS_READCHAT]` | Conserver | `read_teams_chat` |
| `[ACTION:TEAMS_MSG]` | Conserver | `send_teams_message` |
| `[ACTION:TEAMS_SENDCHANNEL]` | Fusionner | `send_teams_message` avec param channel |
| `[ACTION:TEAMS_REPLYCHAT]` | Fusionner | `send_teams_message` avec param reply_to |
| `[ACTION:TEAMS_MARK]` | Supprimer (peu utile en agent) | — |
| `[ACTION:TEAMS_GROUPE]` | Supprimer (redondant avec list) | — |
| `[ACTION:TEAMS_SYNC]` | Supprimer (interne technique) | — |

### 🗄️ Catégorie 5 — Drive (3 tags → 2 tools)

| Tag v1 | Décision v2 | Tool v2 |
|---|---|---|
| `[ACTION:MOVEDRIVE]` | Conserver | `move_drive_file` |
| `[ACTION:COPYFILE]` | Conserver | `copy_drive_file` |
| `[ACTION:CREATEFOLDER]` | Conserver | `create_drive_folder` |

### 📄 Catégorie 6 — Création de contenus (4 tags → 4 tools)

| Tag v1 | Décision v2 | Tool v2 |
|---|---|---|
| `[ACTION:CREATE_PDF]` | Conserver | `create_pdf` |
| `[ACTION:CREATE_EXCEL]` | Conserver | `create_excel` |
| `[ACTION:CREATE_IMAGE]` | Conserver | `create_image` (DALL-E) |
| — | **Nouveau** | `create_file` (md, txt, csv) |

### 🧠 Catégorie 7 — Mémoire / apprentissage (4 tags → 1-2 tools)

| Tag v1 | Décision v2 | Tool v2 |
|---|---|---|
| `[ACTION:LEARN]` | Transformer | `remember_preference` (pour les règles durables) |
| `[ACTION:FORGET]` | Conserver | `forget_preference` |
| `[ACTION:SYNTH]` | Supprimer (obsolète avec graphe) | — |
| `[ACTION:INSIGHT]` | Supprimer (obsolète avec graphe) | — |

Le reste de la mémoire (apprentissages implicites des conversations)
devient automatique via le graphe. Plus besoin d'action explicite.


### 📋 Catégorie 8 — Confirmations / interactions (3 tags → natif agent)

| Tag v1 | Décision v2 | Tool v2 |
|---|---|---|
| `[ACTION:CONFIRM]` | Supprimer (géré nativement par cartes) | — |
| `[ACTION:CANCEL]` | Supprimer (géré nativement par cartes) | — |
| `[ACTION:ASK_CHOICE]` | Supprimer (Claude pose les questions naturellement) | — |

En mode agent, Claude demande et confirme en langage naturel. Les
tags artificiels ne servent plus.

### 🏢 Catégorie 9 — Tâches / projets Odoo (4 tags → 2 tools)

| Tag v1 | Décision v2 | Tool v2 |
|---|---|---|
| `[ACTION:CREATE_CONTACT]` | Conserver | `create_odoo_contact` |
| `[ACTION:CREATE_TASK]` | Conserver | `create_odoo_task` |
| `[ACTION:ODOO_CREATE]` | **Désactiver, ne pas supprimer** | — (réactivable v2.x) |
| `[ACTION:ODOO_UPDATE]` | **Désactiver, ne pas supprimer** | — (réactivable v2.x) |

### 🎯 Catégorie 10 — Autres (3 tags → décisions variées)

| Tag v1 | Décision v2 | Tool v2 |
|---|---|---|
| `[ACTION:CREATE_TOPIC]` | Supprimer (système de topics abandonné) | — |
| `[ACTION:CREATE_SKILL]` | Supprimer (futur, hors scope v2) | — |
| `[ACTION:RESTART_ONBOARDING]` | Supprimer (Claude gère en langage naturel) | — |

---

## 📊 Bilan quantitatif

| Catégorie | Tags v1 | Tools v2 |
|---|---|---|
| Recherche / lecture | 13 | 6 + 5 nouveaux |
| Mails | 5 | 4 |
| Calendrier | 4 | 3 |
| Teams | 11 | 5 |
| Drive | 3 | 3 |
| Création contenus | 3 | 4 (+1 nouveau) |
| Mémoire | 4 | 2 |
| Confirmations | 3 | 0 (natif) |
| Tâches / projets | 4 | 2-3 |
| Autres | 3 | 0 |
| **TOTAL** | **53** | **~30 tools** |

**Réduction de ~45%** du nombre d'actions exposées. Le reste est soit
absorbé par le comportement naturel de Claude, soit par des
paramètres optionnels des tools existants.


---

## 📁 Audit des fichiers Python à modifier / supprimer

### À réécrire (cœur du système)

| Fichier | Rôle v1 | Action v2 |
|---|---|---|
| `app/routes/raya_helpers.py` | Orchestration single-shot | **Réécrire** en boucle agent |
| `app/routes/aria_context.py` | Prompt système long (~422 lignes) | **Réduire** à ~50 lignes |

### À créer

| Fichier | Rôle |
|---|---|
| `app/routes/raya_tools.py` | **NOUVEAU** — Registre des ~30 tools au format Anthropic |
| `app/routes/raya_tool_executors.py` | **NOUVEAU** — Exécuteurs qui mappent les tool_calls vers les fonctions existantes |
| `app/jobs/graph_indexer.py` | **NOUVEAU** — Batch d'indexation conversations toutes les 8 messages |

### À supprimer ou vider

| Fichier | Raison |
|---|---|
| `app/routes/prompt_guardrails.py` | Règles intégrées au prompt court |
| `app/routes/prompt_actions.py` | Remplacé par `raya_tools.py` |
| `app/routes/prompt_blocks.py` | La plupart des blocs disparaissent |
| `app/routes/prompt_blocks_extra.py` | Idem |

### À préserver intact

| Fichier | Raison |
|---|---|
| `app/connectors/*` | Tous les connecteurs (Odoo, Drive, mail, Teams) restent. Ils seront appelés par les tool executors. |
| `app/routes/actions/*` | Logique métier des actions, réutilisée |
| `app/database*.py` | Schéma DB préservé |
| `app/retrieval.py` | Contient `unified_search` qui sert à `search_graph` |
| `app/entity_graph.py` | Graphe sémantique, au cœur de la v2 |
| `app/semantic_graph.py` | Idem |
| `app/memory_loader.py` | Sera adapté légèrement |
| `app/llm_client.py` | Adapter pour supporter `tools=` |
| Tout le front (`app/static/*`, `app/templates/*`) | Inchangé |
| L'app Flutter | Inchangée |

---

## ⚠️ Points d'attention

### Point 1 — ODOO_CREATE et ODOO_UPDATE [DÉCIDÉ 21/04]

**Décision Guillaume** : désactiver mais ne pas supprimer.

En v2, ces tools ne sont pas exposés à Claude. Le code reste dans le
dépôt, mais sans inscription dans le registre `raya_tools.py`.

Rationale :
- Phase de stabilisation v2 = lecture seule, plus safe
- Code préservé pour réactivation facile plus tard
- Une fois la v2 validée (quelques semaines en production), on pourra
  soit les réactiver tels quels, soit les remplacer par des tools
  spécialisés à périmètre limité (`create_odoo_lead`, `update_odoo_contact`)

Tous les autres tools d'action d'écriture (mails, calendar, Teams,
Drive) restent actifs dès la v2, avec cartes de confirmation.

### Point 2 — Cartes de confirmation existantes
Le système de cartes de confirmation côté front doit être préservé.
Les tools d'action doivent créer des `pending_actions` de la même
manière que les tags v1.

### Point 3 — Scan nocturne des mails
Le job d'analyse des mails (`app/jobs/mail_analysis.py`) tourne
indépendamment de Raya. Il reste inchangé en v2.

### Point 4 — Webhooks Odoo
Le polling Odoo (`app/jobs/odoo_polling.py`) reste inchangé en v2.

### Point 5 — Permissions / tenants
Tout le système de permissions (`app/permissions.py`) est préservé.
Les tools exécutent sous l'identité de l'utilisateur authentifié.


---

## 🔢 Chiffres clés de l'audit

### Volume de code v1 à toucher
- `raya_helpers.py` : 368 lignes → à réécrire (~200 lignes en v2)
- `aria_context.py` : 422 lignes → à réduire à ~50 lignes
- `prompt_guardrails.py` : 100 lignes → supprimées
- `prompt_actions.py` : ? lignes → supprimées
- `prompt_blocks.py` + `prompt_blocks_extra.py` : ~350 lignes → très réduites

**Total : ~1200 lignes de prompt/orchestration supprimées ou
remplacées par ~500 lignes en v2.**

Réduction nette du code de l'ordre de **60%**, tout en augmentant les
capacités fonctionnelles.

### Volume de code préservé
- Connecteurs : ~8000 lignes, intacts
- Actions métier : ~3000 lignes, intactes
- Retrieval / graphe : ~2000 lignes, intactes et mieux exploitées

---

## ✅ Validation de l'audit

Ce document est le résultat d'une lecture de l'intégralité du code v1
en regard de `docs/architecture_agent_v1.md` (les specs v2).

Il constitue la **feuille de route technique** pour l'étape 4 (refonte
du code).

Prochaine étape : **archivage de la v1** avant toute modification.

---

## 📚 Documents liés

- `docs/architecture_agent_v1.md` — Specs v2 de référence
- `docs/vision_architecture_raya.md` — Vision fondatrice
- `docs/recensement_acces_odoo.md` — État Odoo

---

## 📝 Historique

- **21/04/2026** : audit initial après rédaction des specs v2. Livrable
  clé pour décision sur le plan de refonte.
