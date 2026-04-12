# RAYA — FEUILLE DE ROUTE V2.2

**Auteur :** Opus (architecte) — validé par Guillaume
**Date :** 12/04/2026 soir
**Basée sur :** V2 + session massive du 12/04/2026 (Phases 5D-2 → 5F complètes)

---

## MISE À JOUR V2.2

### Ce qui a été fait le 12/04/2026

Une session Opus unique a complété 4 phases entières :

**Phase 5D-2 (6 sous-tâches)** — Mode Dirigeant Multi-Tenant
- get_user_tenants() dans tenant_manager.py
- search_similar multi-tenant dans embedding.py (paramètre tenant_ids)
- Toutes fonctions RAG multi-tenant dans rag.py
- LEARN avec tenant cible dans aria_actions.py + save_rule(personal=True)
- build_system_prompt multi-tenant dans aria_context.py
- _raya_core passe user_tenants au prompt builder

**Phase 5E (5 tâches)** — Conscience Outils + Proactivité + Jarvis Minimal
- 5E-1 : get_user_capabilities_prompt(username, tools) — outils dynamiques
- 5E-2 : 23 outils avec functional_description dans tools_registry
- 5E-3 : route_mail_action branché dans webhook (IGNORER/STOCKER_SIMPLE/ANALYSER)
- 5E-4 : proactive_alerts table + proactivity_scan job 30min + injection prompt
- 5E-5 : Twilio connector WhatsApp/SMS + notifications auto sur alertes high/critical

**Phase 5G (6/7 tâches)** — Maturité Relationnelle
- 5G-1 : compute_maturity_score() — 5 critères × 20 pts → 3 phases
- 5G-2 : Paramètres adaptatifs (decay, mask, synth varient par phase)
- 5G-3 : Prompt comportemental adaptatif (discovery/consolidation/maturity)
- 5G-4 : Moteur de patterns (aria_patterns, 5 types, analyse hebdo Opus)
- 5G-5 : Patterns injectés dans prompt, automatisations proposées en maturity
- 5G-6 : Hot_summary évolutif (factuel → analytique → portrait profond)
- 5G-7 : Reporté après Charlotte

**Phase 5F (3 tâches)** — Dashboard & Refactoring
- 5F-1 : /admin/costs endpoint (par tenant/user/modèle/purpose/jour)
- 5F-2 : aria_rules_history table + rollback_rule()
- 5F-3 : aria_actions.py splitté en 6 sous-modules (app/routes/actions/)

### Statut des tâches de la roadmap V2

TOUTES les phases 5 (5A → 5F + 5G) sont terminées.
Les seules tâches reportées sont :
- 5D-4 (onboarding par tenant) — attendre le beta Charlotte
- 5G-7 (modèle générique de démarrage) — besoin de 2 utilisateurs

### Suivi des décisions B1–B32 (mis à jour)

| Décision | Statut | Notes |
|---|---|---|
| B1-B2 routage 3 tiers | ✅ | — |
| B3-B7 RAG + mémoire 4 couches | ✅ | hot_summary évolutif (5G-6) |
| B5 audit Opus hebdo | ✅ | + pattern analysis (5G-4) |
| B6 décroissance confiance | ✅ | adaptative par phase (5G-2) |
| B7 feedback 👍👎 | ✅ | — |
| B8 session thématique | ✅ | — |
| B9 3 niveaux notifs | ✅ | — |
| B10 proactivity_scan | ✅ | 5E-4 — scan 30min + alertes + WhatsApp |
| B11-B12 multi-tenant | ✅ | 5D complet (RAG cross-tenant, LEARN ciblé) |
| B13 onboarding élicitation | ✅ | — |
| B14/B30 rule_validator | ✅ | + versioning + rollback (5F-2) |
| B15 mode hors-cadre | ❌ | à planifier |
| B16 MCP par tenant | ❌ | Phase 6-1 |
| B17 /admin/costs | ✅ | 5F-1 |
| B18/B23 tools_registry | ✅ | descriptions fonctionnelles (5E-2) |
| B20 rename aria→raya | 🟡 | Phase 6-4 |
| B21-B22 hiérarchie règle>skill>code | ✅ | — |
| B24 API externe | ❌ | Phase 6-3 |
| B25 versioning règles | ✅ | 5F-2 |
| B27 bouton Pourquoi | ✅ | — |
| B29 honnêtété épistémique | ✅ | — |
| B31 boucle feedback | ✅ | — |
| B32 RAG vectoriel | ✅ | multi-tenant (5D-2) |

### Prochaine étape : Phase 7 (Jarvis)

Tout le socle est prêt. Les prérequis Phase 7 sont remplis :
- Fiabilité (5C) ✅
- Conscience des outils (5E) ✅
- Maturité relationnelle (5G) ✅
- Twilio connector (5E-5) ✅
- Proactive alerts + scan (5E-4) ✅
- Triage webhook 3 niveaux (5E-3) ✅

Priorités Phase 7 :
1. **7-10 Mode ombre** (shadow mode) — le plus sûr pour commencer
2. **7-2 Modèle d'urgence enrichi** (score 0-100)
3. **7-1 Multi-mailbox** (Gmail en plus de Microsoft)
4. **7-3 Canal WhatsApp structuré** (messages avec options de réponse)
5. **7-5 Préférences de sollicitation** (plages horaires, VIP)
6. **7-6 Heartbeat matinal** (preuve de vie)

Voir la roadmap V2 principale pour le détail des 10 tâches Phase 7.

---

*Ce fichier complète `raya_roadmap_v2.md`. La V2 reste la référence pour la vision,
l'architecture de l'entonnoir 5 étages, et les estimations de coûts.
Cette V2.2 documente l'avancement et les priorités actualisées.*
