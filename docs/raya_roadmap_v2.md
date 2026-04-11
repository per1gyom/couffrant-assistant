# RAYA — FEUILLE DE ROUTE V2

**Auteur :** Opus (architecte) — validé par Guillaume
**Date :** 12/04/2026
**Basée sur :** audit complet du code 12/04/2026 + vision Guillaume + décisions B1–B32
**Règle :** mise à jour obligatoire à chaque jalon atteint (V2.1, V2.2...)

---

## 0. VISION

Raya est un assistant IA personnel auto-apprenant pour dirigeants d'entreprise.
Destination finale : **Jarvis** — Raya ne répond pas seulement quand on lui parle.
Elle surveille, évalue, alerte, propose, automatise.

### Deux modes sur le même moteur

- **Mode Dirigeant** — transversal multi-sociétés, connaissance profonde de l'utilisateur,
  modèles de réflexion, proactivité. L'utilisateur désactive toutes ses notifications et
  fait confiance à Raya comme unique filtre intelligent entre le monde et lui.
- **Mode Entreprise** — cloisonné à un seul tenant, opérationnel, pour les collaborateurs.

### Principes non négociables

- **LLM-agnostic** : la mémoire, les règles, le RAG sont le vrai asset. Le modèle IA est
  interchangeable. Quand Claude 5 (ou GPT-6, Mistral-next) sort, on change UNE variable
  d'environnement dans `llm_client.py` et Raya est immédiatement plus intelligente.
  Sa mémoire cumulée reste intacte. C'est le meilleur des deux mondes.
- **Auto-apprentissage** : Raya décide librement. Zéro règle métier dans le code.
  Tout est en base et évolue par apprentissage.
- **Maturité relationnelle** : Raya évolue dans sa relation avec l'utilisateur —
  attentive et curieuse au début, autonome et proactive à maturité.
- **Précision factuelle** : Raya ne ment jamais, ne fabrique jamais, ne suppose jamais.
  L'honnêteté épistémique est la base de la confiance.

### Positionnement commercial

Raya n'est pas un outil SaaS classique. C'est un cerveau supplémentaire sur lequel
l'utilisateur peut s'appuyer : gain de productivité, de rigueur, de sérénité.
Sa mémoire se bonifie avec le temps (contrairement à un logiciel qui se dégrade).
Son intelligence hérite automatiquement de chaque avancée IA via l'agnosticisme LLM.
Ces deux propriétés justifient un positionnement tarifaire premium.

---

## 1. CONTEXTE AU 12/04/2026

### État technique

- RAG vectoriel : 1045/1045 embeddings ✅
- Tests Phase 4 : 16/16 verts ✅
- Webhook Teams : subscription valide (expire 13/04 12:42 UTC, renouvellement auto 6h) ✅
- Stack : FastAPI Python 3.13, Railway, PostgreSQL+pgvector, Anthropic 3 tiers, OpenAI embeddings

### Utilisateurs cibles immédiats

**Guillaume Perrin** — Couffrant Solar (installateur photovoltaïque, ~5 collaborateurs, Loire)
- Microsoft 365 + Odoo + SharePoint
- ~10 boîtes mail (mix Microsoft et Gmail)
- Besoin : vision transversale multi-sociétés, proactivité, filtre intelligent

**Charlotte Couffrant** — Juillet (événementiel d'entreprise)
- Gmail + LinkedIn + Instagram
- Outils détaillés à préciser ultérieurement
- Besoin : gestion communication, réseaux sociaux, organisation événements
- Premier test beta sur un tenant séparé (validation multi-tenant + onboarding générique)

### Stratégie de déploiement

1. Stabiliser sur Guillaume (Couffrant Solar) — tester toutes les phases
2. Beta sur Charlotte (Juillet) — valider multi-tenant + onboarding générique + Gmail
3. Extraire un modèle générique de démarrage (patterns structurels de dirigeant)
4. Commercialiser à quelques sociétés locales en version beta
5. Recruter pour SAV/bugs puis commercialisation élargie

---

## 2. AUDIT — PROBLÈMES IDENTIFIÉS (12/04/2026)

Chaque problème est adressé par une tâche dans les phases ci-dessous.

| Problème | Gravité | Tâche |
|---|---|---|
| 3 fichiers contournent `llm_client.py` (Anthropic direct) | 🔴 critique | 5A-5/6/7 |
| Mot de passe par défaut dans `config.py` (repo public) | 🔴 critique | 5A-1 |
| Cookie session 30 jours (trop long) | 🔴 critique | 5A-2 |
| Pas de rate limiting sur `/raya` | 🔴 critique | 5A-3 |
| `user_tenant_access` manquant (mode dirigeant impossible) | 🔴 critique | 5D-1 |
| Double `get_contacts_keywords` | 🟡 important | 5A-8 |
| `get_memoire_param` wrapper fragile | 🟡 important | 5A-9 |
| `tools_registry` ignoré par `aria_actions.py` | 🟡 important | 5A-10 |
| Webhook renewal en thread daemon (crash silencieux) | 🟡 important | 5A-11 |
| Pas de logs admin | 🟡 important | 5A-4 |
| Prompt système massif (~5000 tokens à chaque échange) | 🟡 important | 5B-1 |
| Pas de structured logging | 🟡 important | 5C-1 |
| Pas de health check profond | 🟡 important | 5C-2 |
| `aria_actions.py` trop gros (33k) | 🟢 mineur | 5F-3 |
| Wrappers dépréciés encore actifs | 🟢 mineur | 5A-13 |
| Scripts legacy en racine | 🟢 mineur | 5A-12 |

---

## 3. PHASES DE DÉVELOPPEMENT

### PHASE 5A — SÉCURITÉ & DETTE TECHNIQUE

*Objectif : socle fiable et sûr avant d'ajouter des features.*

| # | Tâche | Priorité | Complexité |
|---|---|---|---|
| 5A-1 | Supprimer le mot de passe par défaut dans `config.py` — lever une erreur au démarrage si `APP_PASSWORD` non défini en variable d'environnement | 🔴 critique | faible |
| 5A-2 | Réduire la durée du cookie session de 30 jours à 7 jours | 🔴 critique | faible |
| 5A-3 | Rate limiting sur `/raya` — 60 requêtes/heure par user, compteur mémoire, message propre si dépassé | 🔴 critique | moyenne |
| 5A-4 | Table `admin_audit_log` — logger toute action admin (création/suppression user, déblocage, modification permissions) avec username + action + timestamp | 🟡 important | moyenne |
| 5A-5 | Migrer `ai_client.py` vers `llm_complete()` — supprimer `import anthropic` et `client.messages.create()`. Utiliser `llm_complete(model_tier="fast")` pour l'analyse mails | 🔴 critique | moyenne |
| 5A-6 | Migrer `memory_contacts.py` vers `llm_complete()` — rebuild_contacts utilise Haiku via la couche d'abstraction | 🔴 critique | faible |
| 5A-7 | Migrer `memory_style.py` vers `llm_complete()` — learn_from_correction idem | 🔴 critique | faible |
| 5A-8 | Supprimer le doublon `get_contacts_keywords` dans `memory_contacts.py` — la version canonique est dans `rule_engine.py`, tous les appelants doivent l'importer de là | 🟡 important | faible |
| 5A-9 | Supprimer le wrapper fragile `get_memoire_param` dans `memory_rules.py` — mettre à jour les appelants vers `rule_engine.get_memoire_param(username, param, default)` | 🟡 important | faible |
| 5A-10 | Brancher `aria_actions.py` sur `tools_registry` pour déterminer la sensibilité des actions — une seule source de vérité au lieu de deux listes | 🟡 important | moyenne |
| 5A-11 | Migrer webhook renewal + token refresh de threads daemon (`main.py`) vers APScheduler (`scheduler.py`) — plus robuste, loggé, désactivable par variable d'env | 🟡 important | moyenne |
| 5A-12 | Supprimer scripts legacy racine : `auto_ingest.py`, `push.bat`, `start_assistant.bat`, `test_analyzer.py`, `test_replies.py`, `upgrade_db_reply_fields.py`, `upgrade_reply_learning.py`, `upgrade_reply_status.py`, `reset_admin_password.py` | 🟢 mineur | faible |
| 5A-13 | Supprimer wrappers dépréciés dans `memory_rules.py` (`get_rules_by_category`, `get_memoire_param`, `get_rules_as_text`, `get_antispam_keywords`) — mettre à jour les 2-3 appelants restants | 🟢 mineur | faible |
| 5A-14 | Simplifier `memory_loader.py` → importer directement les 4 modules mémoire, supprimer `memory_manager.py` (couche d'indirection inutile) | 🟢 mineur | faible |

**Reporté :** CSP `unsafe-inline` — durcissement progressif, risque faible avec la base d'utilisateurs actuelle.

---

### PHASE 5B — OPTIMISATION PROMPT & EFFICACITÉ

*Objectif : prompt plus léger SANS perdre en précision. La précision contextuelle est non négociable — Raya doit toujours savoir à qui elle parle, dans quel contexte, avec quelles règles. L'économie vient de l'injection intelligente, pas de la suppression de contexte.*

| # | Tâche | Priorité | Complexité |
|---|---|---|---|
| 5B-1 | **Injection dynamique des actions** — le routeur Haiku classifie non seulement le tier (smart/deep) mais aussi les domaines pertinents (mail, drive, teams, calendar, memory). Seules les actions des domaines détectés sont injectées dans le prompt. Gain estimé : 30-40% de tokens sur les échanges courants. | 🟡 important | haute |
| 5B-2 | **Hot_summary amélioré** — Opus produit un résumé qualitatif structuré en 3 niveaux : (1) situation opérationnelle, (2) patterns d'usage détectés, (3) préférences et modèles de décision. Le résumé est vectorisé dans `aria_hot_summary` avec embedding pour injection RAG fluide. | 🟡 important | moyenne |
| 5B-3 | Cache mémoire TTL 5 min pour règles et insights — les règles changent rarement (quelques fois par jour), pas besoin de re-query la DB à chaque échange | 🟡 important | moyenne |
| 5B-4 | Dédupliquer le contexte conversationnel — si un échange récent est déjà dans les `messages` (historique), ne pas le ré-injecter via `retrieve_relevant_conversations` dans le prompt système | 🟡 important | moyenne |
| 5B-5 | `ThreadPoolExecutor` partagé au niveau app — un pool unique instancié au démarrage au lieu d'un par requête | 🟢 mineur | faible |

---

### PHASE 5C — ROBUSTESSE

*Objectif : Raya ne tombe plus silencieusement. Prérequis absolu pour la Phase 7 (Jarvis) — si l'utilisateur désactive toutes ses notifications mail et fait confiance à Raya, elle ne peut pas mourir sans alerte.*

| # | Tâche | Priorité | Complexité |
|---|---|---|---|
| 5C-1 | **Structured logging** — remplacer tous les `print()` par `logging` avec niveaux INFO/WARN/ERROR et corrélation par requête | 🟡 important | moyenne |
| 5C-2 | **Health check profond** — `/health` vérifie DB (`SELECT 1`), pool de connexions, disponibilité Anthropic. Permet monitoring externe. | 🟡 important | faible |
| 5C-3 | **Timeout global sur `/raya`** — 30s max. Si Anthropic est lent (rate limit, surcharge), message propre « Raya est momentanément surchargée ». | 🟡 important | faible |
| 5C-4 | **Monitoring threads** — alerte si un job de renouvellement meurt silencieusement (résolu par 5A-11 si migration APScheduler complète) | 🟡 important | faible |

---

### PHASE 5D — MODE DIRIGEANT MULTI-SOCIÉTÉ

*Objectif : permettre à un dirigeant (Guillaume) d'interagir avec Raya sur toutes ses sociétés dans la même conversation. Raya fait le lien entre les entités, croise les informations, donne une vision transversale.*

| # | Tâche | Priorité | Complexité |
|---|---|---|---|
| 5D-1 | **Table `user_tenant_access`** — relation many-to-many entre users et tenants avec rôle par tenant (owner/admin/user). Un dirigeant peut appartenir à plusieurs tenants. | 🔴 critique | moyenne |
| 5D-2 | **Contexte multi-tenant dans le prompt** — quand un user dirigeant parle à Raya, elle cherche dans les règles, contacts, mails de TOUS ses tenants. Elle peut croiser : « Dupont relance sur le chantier (Couffrant Solar) ET la facture est en attente (autre société) ». | 🔴 critique | haute |
| 5D-3 | Deuxième compte super_admin de secours | 🟡 important | faible |
| 5D-4 | **Onboarding par tenant** — quand un dirigeant ajoute une nouvelle société, Raya lance un questionnaire adapté au métier (photovoltaïque ≠ événementiel). Les questions sont générées par le moteur d'élicitation existant. | 🟡 important | moyenne |

---

### PHASE 5E — CONSCIENCE DES OUTILS & PROACTIVITÉ

*Objectif : Raya connaît ses outils, sait ce que l'utilisateur peut faire, et commence à anticiper. Prérequis : Raya doit avoir conscience de ses capacités avant de pouvoir proposer des automatisations.*

**Conscience des outils (prérequis proactivité) :**

| # | Tâche | Priorité | Complexité |
|---|---|---|---|
| 5E-1 | **Carte des capacités par utilisateur** — à chaque connexion, Raya construit une vision claire des outils disponibles (quels connecteurs, quels accès, quels MCP). Injectée dans le prompt de façon lisible (pas juste une config technique). Raya ne propose jamais une action que l'utilisateur ne peut pas faire. | 🟡 important | moyenne |
| 5E-2 | **Descriptions fonctionnelles des outils** — le `tools_registry` passe de descriptions techniques (« Liste les fichiers SharePoint ») à des descriptions fonctionnelles que Raya utilise pour raisonner (« Drive permet d'organiser les documents chantier, retrouver un devis, vérifier qu'un dossier est complet »). | 🟡 important | moyenne |

**Proactivité :**

| # | Tâche | Priorité | Complexité |
|---|---|---|---|
| 5E-3 | **Brancher `route_mail_action` dans `webhook.py`** — le triage Haiku IGNORER/STOCKER/ANALYSER est déjà écrit dans `router.py` mais pas connecté. L'activer réduit les coûts (les mails ignorés ne passent plus par l'analyse complète). | 🟡 important | moyenne |
| 5E-4 | **`proactivity_scan` (B10)** — job APScheduler toutes les 30 min. Analyse mails récents, agenda, deadlines. Génère alertes/rappels intelligents. Consulte la carte des capacités avant de proposer quoi que ce soit. | 🟡 important | haute |

**Version Jarvis minimale (intercalée) :**

| # | Tâche | Priorité | Complexité |
|---|---|---|---|
| 5E-5 | **Jarvis minimal** — version légère pour commencer à tester : triage multi-boîte (Microsoft + Gmail) + notification WhatsApp/Twilio message texte pour les mails importants. Pas d'appel, pas de heartbeat, pas de patterns. But : terrain de test concret pendant qu'on avance sur le reste. Ne doit pas rallonger significativement le développement. | 🟡 important | moyenne |

---

### PHASE 5F — DASHBOARD & REFACTORING

| # | Tâche | Priorité | Complexité |
|---|---|---|---|
| 5F-1 | **Dashboard `/admin/costs` (B17)** — visualisation des coûts LLM par tenant, par user, par modèle. Données déjà dans `llm_usage`. | 🟡 important | moyenne |
| 5F-2 | **Versioning des règles (B25)** — historique des modifications de chaque règle. Possibilité de rollback si une règle corrective fait du dégât. | 🟡 important | moyenne |
| 5F-3 | **Refactoring `aria_actions.py`** — split 33k en sous-modules : `actions_mail.py`, `actions_drive.py`, `actions_teams.py`, `actions_memory.py` | 🟢 mineur | moyenne |

---

### PHASE 5G — MATURITÉ RELATIONNELLE

*Objectif : Raya évolue dans sa relation avec l'utilisateur. Comme deux humains qui se rencontrent — attentive au départ, à l'aise à maturité. Le rythme d'apprentissage, la fréquence des confirmations, le niveau de proactivité s'adaptent automatiquement à la maturité de la relation.*

| # | Tâche | Priorité | Complexité |
|---|---|---|---|
| 5G-1 | **Score de maturité utilisateur** — calcul automatique basé sur : nombre de règles actives, total renforcements, nombre de conversations, ancienneté du compte, taux de feedback positif. Recalculé quotidiennement. Détermine la phase : Découverte / Consolidation / Maturité. | 🟡 important | moyenne |
| 5G-2 | **Paramètres adaptatifs** — les paramètres clés varient selon la phase (voir tableau ci-dessous). Le scheduler lit la phase avant d'appliquer la décroissance. | 🟡 important | moyenne |
| 5G-3 | **Comportement Raya adaptatif** — en Découverte : Raya confirme ses apprentissages (« j'ai l'impression que tu préfères X, c'est bien ça ? »), explore les outils avec l'utilisateur. En Consolidation : elle confirme moins, propose des raccourcis. En Maturité : elle agit, propose des automatisations, ne confirme que sur le nouveau. Piloté par la phase dans le prompt système. | 🟡 important | haute |
| 5G-4 | **Moteur de patterns** — analyse périodique (Opus) des comportements récurrents : temporels (« traite les mails financiers le lundi »), relationnels (« Dupont relance = urgent »), thématiques (« cherche toujours le dossier Drive après un mail client »). Stockés dans table `aria_patterns`. | 🟡 important | haute |
| 5G-5 | **Proactivité mature** — en Phase Maturité, Raya propose des automatisations basées sur patterns + outils disponibles. « Tu fais X chaque semaine, je peux le faire pour toi. » Ne propose que ce qui est faisable (consulte la carte des capacités 5E-1). | 🟡 important | haute |
| 5G-6 | **Hot_summary évolutif** — en Découverte : factuel (situation opérationnelle). En Maturité : portrait profond (patterns, préférences implicites, modèles de décision de l'utilisateur). Vectorisé pour RAG fluide. | 🟡 important | moyenne |
| 5G-7 | **Modèle générique de démarrage** — après validation sur 2 sociétés (Couffrant Solar + Juillet), extraire les patterns structurels transférables (comment un dirigeant interagit avec ses mails, son agenda, ses outils). Ce « kit de démarrage » accélère la Phase Découverte d'un nouveau client. | 🟡 important | moyenne |

**Tableau des paramètres adaptatifs (5G-2) :**

| Paramètre | Découverte | Consolidation | Maturité |
|---|---|---|---|
| Synthèse tous les N échanges | 8 | 15 | 30 |
| Décroissance confiance/semaine | -0.08 | -0.05 | -0.02 |
| Seuil de masquage confiance | 0.30 | 0.30 | 0.20 |
| LEARN automatiques par synthèse | beaucoup | modéré | peu mais qualitatif |
| Confirmations utilisateur | fréquentes | occasionnelles | rares |
| Proactivité | aucune (observe) | suggestions ponctuelles | automatisations proposées |

---

### PHASE 7 — JARVIS

*Objectif : Raya devient le filtre intelligent entre le monde et l'utilisateur. L'utilisateur désactive toutes ses notifications mail et fait confiance à Raya pour alerter au bon moment, par le bon canal, avec le bon niveau de détail.*

**Paradigme :**
```
Le monde → [10 boîtes mail, Teams, calendrier, ERP, réseaux sociaux]
                                    ↓
                          Raya surveille en permanence
                                    ↓
                          Raya évalue l'urgence (entonnoir 5 étages)
                                    ↓
                ┌───────────────────┼───────────────────┐
                ↓                   ↓                   ↓
           Pas urgent           Important            Critique
           Stocke,              Message WhatsApp     Appel WhatsApp
           résumé au            avec résumé +        avec contexte
           prochain échange     options d'action     vocal, attend
                                                     décision
```

**Entonnoir de triage — 5 étages :**

| Étage | Mécanisme | Coût | Notes |
|---|---|---|---|
| 1. Filtre par règles apprises | Code pur, règles depuis `aria_rules`. Élimine ~70% (newsletters, noreply, spam connu). **Règles évolutives** : Raya les crée, modifie, supprime. L'utilisateur peut corriger une erreur de classement et la règle se met à jour automatiquement. | Gratuit | Non figé dans le code |
| 2. Triage Haiku | Prompt minimal (expéditeur + sujet + 200 chars + règles urgence). Retourne score urgence + catégorie. | ~0.0003$/mail | `route_mail_action` existant |
| 3. Analyse Sonnet | Mails importants : contexte complet via RAG. Retourne score urgence + score certitude. | ~0.01$/mail | Si certitude > 0.8 → décision finale |
| 3bis. Escalade Opus | Si certitude Sonnet < 0.8 : mail ambigu, implications complexes, croisement multi-dossiers. Opus tranche avec vision profonde. | ~0.05$/mail | ~2-5 mails/semaine |
| 4. Décision d'alerte | Code pur : compare score urgence aux seuils de l'utilisateur. | Gratuit | Seuils configurables |
| 5. Composition message sortant | Haiku compose le résumé pour WhatsApp/notification. | ~0.001$/message | Négligeable |

**Correction utilisateur → boucle de rétroaction :**
Si l'utilisateur trouve un mail mal classé dans les « silencieux », il corrige.
Raya apprend immédiatement (LEARN sur les règles Étage 1).
Plus les règles Étage 1 sont bonnes, moins les étages suivants sont sollicités → coûts décroissants.

**Seuils d'alerte (configurables par utilisateur) :**

| Niveau | Score | Canal | Exemple |
|---|---|---|---|
| Silencieux | 0-30 | Aucun | Newsletter, notification auto |
| Normal | 30-60 | Résumé au prochain échange chat | Mail fournisseur de routine |
| Important | 60-85 | Message WhatsApp avec résumé + options | Relance client, demande deadline |
| Critique | 85-100 | Appel WhatsApp avec contexte vocal | Mail avocat deadline 24h, urgence bancaire |

Seuils adaptatifs selon la maturité : en Découverte, le seuil « important » est plus bas
(Raya préfère déranger pour rien plutôt que de rater quelque chose).
En Maturité, elle est calibrée finement.

**Tâches Phase 7 :**

| # | Tâche | Description | Prérequis |
|---|---|---|---|
| 7-1 | **Multi-mailbox** | Ingestion de toutes les boîtes mail : Microsoft Graph (webhook existant), Gmail (API + polling ou webhook Google), IMAP générique si nécessaire. Polling configurable par boîte. | 5A terminé |
| 7-2 | **Modèle d'urgence enrichi** | Score 0-100 par message entrant. Basé sur : règles apprises + contacts connus + patterns temporels + contexte croisé (calendrier, dossiers en cours) + phase de maturité. Score de certitude Sonnet → escalade Opus si < 0.8. | 5E, 5G |
| 7-3 | **Intégration canal sortant (WhatsApp/Twilio)** | API WhatsApp Business ou Twilio pour messages texte. Numéro dédié identifié comme contact « Raya ». Messages structurés avec résumé + options de réponse rapide. | 5C (fiabilité) |
| 7-4 | **Appel vocal sortant** | Synthèse vocale (ElevenLabs déjà intégré) + appel WhatsApp/Twilio Voice pour les alertes critiques. Raya lit le contexte et attend une instruction vocale. | 7-3 |
| 7-5 | **Préférences de sollicitation** | Plages horaires (« pas entre 22h-7h sauf critique »), canaux préférés, seuils personnalisés, contexte calendrier (« en réunion = seulement critique »), personnes VIP (« ma banque = toujours minimum important »). Stocké dans `aria_rules`, évolue avec la maturité. | 5G |
| 7-6 | **Heartbeat matinal** | Chaque matin, Raya envoie un résumé de la nuit même si rien d'urgent : « 34 mails, 31 silencieux, 2 à voir, 1 urgent ». Preuve de vie. Configurable. | 7-3 |
| 7-7 | **Monitoring et fallbacks** | Alerte automatique si scan inactif > 10 min. Fallback SMS si WhatsApp indisponible, puis email de secours. La fiabilité est non négociable quand l'utilisateur a désactivé toutes ses notifications. | 5C |
| 7-8 | **Réponse par canal sortant** | L'utilisateur répond directement dans WhatsApp : « oui réponds », « transfère à Dupont », « rappelle-moi dans 1h ». Raya exécute via les outils disponibles (mail, Teams, calendrier). | 7-3, 5E |
| 7-9 | **Push notifications PWA** | Niveau intermédiaire pour les utilisateurs Mode Entreprise qui ne veulent pas WhatsApp. Le service worker `sw.js` existe déjà. | — |
| 7-10 | **Mode ombre (shadow mode)** | Période initiale obligatoire : Raya fait le triage mais au lieu d'envoyer les WhatsApp, elle montre dans le chat ce qu'elle AURAIT envoyé. L'utilisateur valide, corrige, et Raya calibre son modèle d'urgence. Durée : ~2 semaines. Correspond à la Phase Découverte du cycle de maturité. | 7-2 |

**Estimation de coûts pour usage personnel (10 boîtes, ~200 mails/jour) :**

| Poste | Estimation/mois |
|---|---|
| Triage Haiku (~60 mails/jour post-filtre) | ~1€ |
| Analyse Sonnet (~10 importants/jour) | ~3€ |
| Escalade Opus (~5/semaine) | ~0.50€ |
| Conversations chat (~10/jour) | ~5€ |
| Synthèses Opus (2/semaine) | ~2€ |
| Audit Opus hebdo | ~0.50€ |
| WhatsApp/Twilio (~10 messages/jour) | ~15€ |
| Embeddings OpenAI | ~1€ |
| Hébergement Railway | ~10€ |
| PostgreSQL Railway | ~5€ |
| **Total estimé** | **~45€/mois** |

---

### PHASE 6 — OUVERTURE (futur, non planifié en détail)

| # | Tâche | Notes |
|---|---|---|
| 6-1 | **MCP par tenant (B16)** — chaque société connecte ses propres outils (ERP, CRM, outils métier). Le registre vivant de 5E-1/5E-2 est conçu pour l'accueillir. | Après 5D |
| 6-2 | **Connecteurs réseaux sociaux** — LinkedIn (publication, analytics), Instagram (publication, stories). Raya aide à la communication : planification, analyse de performance, suggestions de contenu. Utile pour Charlotte (Juillet) et Guillaume. | Après 5D |
| 6-3 | **API externe (B24)** — exposer Raya comme service API pour intégration tiers | Après stabilisation complète |
| 6-4 | **Rename aria→raya complet (B20)** — fichiers, tables, références. En tout dernier. | Cosmétique |
| 6-5 | **Migration Alembic (B11/B12)** — remplacer les 70+ migrations inline de `database.py` par Alembic. Quand scaling nécessaire. | Non urgent |
| 6-6 | **Migration tool_use natif Anthropic** — remplacer le système [ACTION:...] par des appels de fonction structurés. Gros chantier, planifier soigneusement. | Refactoring profond |

---

## 4. ORDRE D'EXÉCUTION

1. **5A** — Sécurité & dette technique (on blinde le socle)
2. **5B** — Optimisation prompt (on rend le moteur efficace)
3. **5C** — Robustesse (on évite les crashes silencieux)
4. **5D** — Mode Dirigeant multi-société (vision personnelle Guillaume)
5. **5E** — Conscience outils + proactivité + **Jarvis minimal** (premier test concret)
6. **5G** — Maturité relationnelle (Raya évolue dans la relation)
7. **5F** — Dashboard & refactoring (visibilité et nettoyage)
8. **7** — Jarvis complet (destination finale)
9. **6** — Ouverture (MCP, réseaux sociaux, API, rename, Alembic)

---

## 5. SUIVI DES DÉCISIONS B1–B32

| Décision | Statut | Lien roadmap |
|---|---|---|
| B1-B2 routage 3 tiers | ✅ fait | — |
| B3-B7 RAG + mémoire 4 couches | ✅ fait | 5B-2 améliore hot_summary |
| B5 audit Opus hebdo | ✅ fait | — |
| B6 décroissance confiance | ✅ fait | 5G-2 rend adaptatif |
| B7 feedback 👍👎 | ✅ fait | — |
| B8 session thématique | ✅ fait | — |
| B9 3 niveaux notifs | ✅ fait | — |
| B10 proactivity_scan | ❌ | 5E-4 |
| B11-B12 multi-tenant | 🟡 partiel | 5D-1, 5D-2, 6-5 |
| B13 onboarding élicitation | ✅ fait | — |
| B14/B30 rule_validator | ✅ fait | — |
| B15 mode hors-cadre | ❌ | à planifier |
| B16 MCP par tenant | ❌ | 6-1 |
| B17 /admin/costs | ❌ | 5F-1 |
| B18/B23 tools_registry | 🟡 registre OK, pas consulté | 5A-10, 5E-2 |
| B20 rename aria→raya | 🟡 en cours | 6-4 |
| B21-B22 hiérarchie règle>skill>code | ✅ fait | — |
| B24 API externe | ❌ | 6-3 |
| B25 versioning règles | ❌ | 5F-2 |
| B27 bouton Pourquoi | ✅ fait | — |
| B29 honnêteté épistémique | ✅ fait | — |
| B31 boucle feedback | ✅ fait | — |
| B32 RAG vectoriel | ✅ fait | — |

---

## 6. RÈGLE DE MISE À JOUR

Ce document est mis à jour par Opus à chaque jalon atteint.
Chaque mise à jour incrémente la version (V2.1, V2.2...) et documente :
la date, ce qui a été fait, ce qui change dans les priorités.
Non négociable. S'applique à toutes les futures conversations Opus.
