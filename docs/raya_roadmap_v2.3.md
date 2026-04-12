# RAYA — FEUILLE DE ROUTE V2.3

**Auteur :** Opus (architecte) — validé par Guillaume
**Date :** 13/04/2026
**Basée sur :** V2.2 + session marathon 12-13/04/2026

---

## MISE À JOUR V2.3 — ÉTAT COMPLET AU 13/04/2026

### Session 12-13/04/2026 — Bilan

Session historique : ~50 tâches en une session. Phase 7 complète (16 tâches),
Phase 8 quasi complète (4/5), 5 refactorings majeurs, 9 fixes/correctifs,
admin panel tenant CRUD, audit bugs multi-tenant.

---

## STATUT PAR PHASE

### Phase 5 (toutes sous-phases) ✅ TERMINÉE
Complétée session précédente. Socle sécurisé, prompt optimisé, robustesse,
multi-tenant, conscience outils, proactivité, maturité relationnelle, dashboard.

### Phase 7 — Jarvis ✅ TERMINÉE (16/16)

| # | Tâche | Statut | Commit / Notes |
|---|---|---|---|
| 7-10 | Shadow mode | ✅ | Colonnes users, étape 5 webhook |
| 7-2 | Modèle d'urgence enrichi | ✅ | urgency_model.py — score 0-100, 4 étages, VIP boost |
| 7-3 | WhatsApp structuré | ✅ | send_whatsapp_structured() avec options |
| 7-5 | Préférences sollicitation | ✅ | notification_prefs.py — plages, VIP, should_notify() |
| 7-ACT | Activity log | ✅ | activity_log.py — 4 handlers + conversations |
| 7-NAR | Mémoire narrative | ✅ | narrative.py — dossier_narratives vectorisée, RAG |
| 7-BRIEF | Briefings réunions | ✅ | Job 6h30, Haiku + narratives |
| 7-6R | Rapport stocké + ping | ✅ | daily_reports, ping léger, livraison à la demande |
| 7-6D | Livraison rapport | ✅ | report_actions.py, marquage auto chat/WhatsApp |
| 7-WF | Workflow intelligence | ✅ | Pattern engine activity_log (type workflow) |
| 7-1a | Gmail connector | ✅ | OAuth2 + polling incrémental historyId |
| 7-1b | Pipeline source-agnostic | ✅ | process_incoming_mail() Microsoft + Gmail |
| 7-1c | Gmail polling job | ✅ | IntervalTrigger 3min |
| 7-7 | Monitoring système | ✅ | system_heartbeat, scan 10min, alerte admin |
| 7-7b | Fallback SMS | ✅ | send_sms() si WhatsApp down |
| 7-8 | WhatsApp bidirectionnel | ✅ | /webhook/twilio, commandes 1-4 + rapport + texte libre |

Tâches Phase 7 non planifiées initialement mais ajoutées et terminées :
- Vitesse lecture ElevenLabs dynamique ([SPEAK_SPEED:x], 0.5-2.5)
- Web search Anthropic (accès internet pour Raya)

### Phase 8 — Intelligence avancée 🟡 4/5

| # | Tâche | Statut | Notes |
|---|---|---|---|
| 8-CYCLES | Patterns cycliques | ✅ | _check_cyclic_alert() Python pur, 4 fréquences |
| 8-TON | Ton adaptatif | ✅ | hot_summary 5 axes + ton_block prompt |
| 8-ANOMALIES | Détection anomalies | ✅ | anomaly_detection.py — Odoo vs mails, 5 étapes |
| 8-OBSERVE | Observation externe | ✅ | external_observer.py — mail/drive/calendar hors Raya |
| 8-COLLAB | Collaboration inter-Rayas | ❌ | Phase commercialisation, haute complexité |

### Refactorings ✅ 5 fichiers découpés

| Fichier | Avant | Après |
|---|---|---|
| scheduler.py | 43k | 5k + 8 modules app/jobs/ |
| database.py | 31k | 9k + database_migrations.py (12k) |
| admin.py | 20k | 3 modules app/routes/admin/ |
| aria_context.py | 25k | 13k + aria_loaders.py (5k) |
| chat.js | 40k | 10k + 6 modules chat-*.js |

### Fixes et correctifs ✅ 9

| Fix | Description |
|---|---|
| Purge Jarvis | Prompt + base + synthèse + patterns nettoyés |
| Security timeout | Inactivité 2h, cookie max 24h |
| ElevenLabs speed | Paramètre dynamique frontend + backend |
| Toast feedback | "👍 Noté, merci !" au lieu de détails internes |
| Hotfix scheduler | Imports lazy — un module cassé ne bloque plus le serveur |
| Tenant form | Auto-lowercase ID côté client + serveur |
| Tenant creation | Formulaire simplifié (forme juridique, SIRET, adresse) |
| 5 bugs critiques | user_tenant_access, delete safety, defaults neutres |
| Intelligence collective | Données anonymisées (pas supprimées) quand un user part |

### Admin panel ✅

- CRUD tenants complet (créer, modifier, supprimer avec protection)
- Formulaire création : ID + Nom + Forme juridique + SIRET + Adresse
- SharePoint optionnel, configuré après création
- Détection super_admin au démarrage

---

## PROCHAINES ÉTAPES

### Priorité 1 — Beta Charlotte (objectif mi-juin)
- Tests parcours complet : création tenant → users → connexion → conversations
- Volet B — Ergonomie UI (largeur chat, design épuré, responsive)
- 5D-4 — Onboarding par tenant (questionnaire adapté au métier)

### Priorité 2 — Outils de création
- DALL-E + Pillow (création/modification images)
- Excel (openpyxl), PDF (reportlab)
- Posts LinkedIn (texte + visuel) + publication LinkedIn/Instagram

### Priorité 3 — Commercialisation (objectif juillet-août)
- 8-COLLAB — Collaboration inter-Rayas (événements tenant partagés)
- Application mobile (PWA ou native)
- Audit performance (profiler et optimiser temps de réponse)
- Modèle commercial (packs Essentiel/Pro/Dirigeant)

---

## PRINCIPES AJOUTÉS CETTE SESSION

### Intelligence collective
Quand un utilisateur est supprimé, ses données personnelles (conversations,
tokens, profil) sont effacées. Mais l'intelligence (règles, insights, patterns,
narratives, mails, activity_log) est anonymisée (`ancien_username`) et conservée.
L'expérience acquise profite au collectif.

### Imports lazy scheduler
Chaque job est importé localement dans son bloc try/except. Un module cassé
n'empêche pas les 11 autres jobs de fonctionner ni le serveur de démarrer.

### Prompts architecte
Opus donne le QUOI, le OÙ, le POURQUOI, les contraintes. Sonnet code.
Opus ne rédige pas le code dans les prompts.

### Formulaire tenant générique
La création d'un tenant ne présuppose rien sur les outils (pas de SharePoint,
pas de fournisseur email). Infos de base = légales. Outils = configurés après.

---

## SUIVI DES DÉCISIONS B1–B32

| Décision | Statut |
|---|---|
| B1-B2 routage 3 tiers | ✅ |
| B3-B7 RAG + mémoire | ✅ + hot_summary évolutif + narratives |
| B5 audit Opus hebdo | ✅ + patterns + anomalies |
| B6 décroissance confiance | ✅ adaptative par phase |
| B7 feedback 👍👎 | ✅ + toast simplifié |
| B8 session thématique | ✅ |
| B9 3 niveaux notifs | ✅ |
| B10 proactivity_scan | ✅ + cycles calendaires |
| B11-B12 multi-tenant | ✅ + user_tenant_access fix |
| B13 onboarding | ✅ |
| B14/B30 rule_validator | ✅ + versioning + rollback |
| B15 mode hors-cadre | ❌ |
| B16 MCP par tenant | ❌ Phase 6 |
| B17 /admin/costs | ✅ |
| B18/B23 tools_registry | ✅ |
| B20 rename aria→raya | 🟡 Phase 6 |
| B24 API externe | ❌ Phase 6 |
| B25 versioning règles | ✅ |
| B27 bouton Pourquoi | ✅ |
| B29 honnêteté épistémique | ✅ |
| B31 boucle feedback | ✅ |
| B32 RAG vectoriel | ✅ multi-tenant |

---

## VARIABLES RAILWAY

```
TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_WHATSAPP_FROM
NOTIFICATION_PHONE_GUILLAUME, NOTIFICATION_PHONE_ADMIN
GMAIL_CLIENT_ID, GMAIL_CLIENT_SECRET, SCHEDULER_GMAIL_ENABLED=true
RAYA_WEB_SEARCH_ENABLED=true
ELEVENLABS_SPEED=1.2
SCHEDULER_ANOMALY_ENABLED=false
SCHEDULER_OBSERVER_ENABLED=false
SCHEDULER_MONITOR_ENABLED=true
```

URL webhook Twilio : `https://[domaine].railway.app/webhook/twilio` (POST)

---

*Ce fichier V2.3 complète la V2 (vision, architecture entonnoir, coûts) et remplace la V2.2.
La V2 reste la référence pour la vision produit et l'architecture détaillée de l'entonnoir 5 étages.*
