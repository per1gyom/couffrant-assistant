# RAYA — PLANNING D'AVANCEMENT V3

**Auteur :** Opus — validé par Guillaume
**Date :** 12/04/2026 soir
**Basé sur :** rythme réel session 12/04/2026 (~30 tâches en 1 session)

---

## HYPOTHÈSES DE RYTHME

- 1-2 sessions Opus par semaine
- 8-12 tâches Sonnet par session (tâches simples)
- 4-6 tâches par session si complexes (architecture, multi-fichiers)
- Prompts déjà rédigés pour les 3 prochaines tâches (7-6R, 7-6D, 7-WF)
- Guillaume copie-colle les prompts vers Sonnet, rapporte les SHA

---

## SPRINT 1 — Fin Phase 7 socle (semaine du 14/04)
**Durée : 1 session**

| Tâche | Complexité | Statut |
|---|---|---|
| 7-6R Redesign rapport (stocké + ping) | Moyenne | Prompt prêt |
| 7-6D Livraison rapport à la demande | Moyenne | Prompt prêt |
| 7-WF Workflow intelligence (patterns sur activity_log) | Faible | Prompt prêt |

**Livrable :** Rapport matinal à la demande + intelligence de workflow opérationnelle.

## SPRINT 2 — Multi-mailbox + Monitoring (semaine du 21/04)
**Durée : 1-2 sessions**

| Tâche | Complexité | Notes |
|---|---|---|
| 7-1a Gmail connector (OAuth2 + polling) | Haute | Nouveau connecteur complet |
| 7-1b Ingestion Gmail dans webhook pipeline | Moyenne | Brancher sur le même triage que Microsoft |
| 7-1c Config multi-boîte par tenant | Faible | Settings tenant + UI admin |
| 7-7a Health monitoring renforcé | Moyenne | Alertes si scan inactif > 10min |
| 7-7b Fallback SMS si WhatsApp down | Faible | Twilio SMS connector existe déjà |

**Livrable :** Guillaume voit TOUTES ses boîtes (Microsoft + Gmail) dans Raya. Monitoring fiable.

## SPRINT 3 — Canal bidirectionnel (semaine du 28/04)
**Durée : 1 session**

| Tâche | Complexité | Notes |
|---|---|---|
| 7-8a Webhook Twilio entrant | Moyenne | Recevoir les réponses WhatsApp |
| 7-8b Parser les commandes WhatsApp | Moyenne | "oui réponds", "transfère à X", "rappelle-moi" |
| 7-8c Exécution des commandes | Moyenne | Router vers les actions existantes |

**Livrable :** Guillaume peut répondre depuis WhatsApp, Raya exécute.

## SPRINT 4 — Vocal + polish (semaine du 05/05)
**Durée : 1 session**

| Tâche | Complexité | Notes |
|---|---|---|
| 7-4 Appel vocal sortant (ElevenLabs + Twilio Voice) | Haute | Alertes critiques = appel |
| 7-9 Push notifications PWA | Faible | sw.js existe déjà |
| Canaux de livraison dans tools_registry | Faible | Chat, WhatsApp, vocal, mail comme outils |

**Livrable :** Phase 7 (Jarvis) complète. Raya filtre, alerte, agit par le bon canal.

---

## PHASE 7 TERMINÉE : estimation mi-mai 2026

---

## SPRINT 5 — Intelligence avancée partie 1 (semaines du 12-19/05)
**Durée : 2 sessions**

| Tâche | Complexité | Notes |
|---|---|---|
| 8-1 Workflow automation | Haute | Proposer d'automatiser les séquences détectées |
| 8-2 Détection d'oublis | Moyenne | "Tu n'as pas mis à jour Odoo" |
| 8-3 Détection d'anomalies cross-outils | Haute | Croiser Odoo/mails/Drive |
| 8-4 Conscience rythme business | Moyenne | Fin de mois = factures, cycles saisonniers |

**Livrable :** Raya anticipe, détecte les oublis, repère les anomalies.

## SPRINT 6 — Intelligence avancée partie 2 (semaine du 26/05)
**Durée : 1 session**

| Tâche | Complexité | Notes |
|---|---|---|
| 8-5 Méta-apprentissage | Moyenne | Raya apprend de ses erreurs systémiques |
| 8-8 Redirection support/admin | Faible | "Je ne peux pas → contacte ton admin" |

**Livrable :** Raya s'améliore d'elle-même et ne laisse jamais l'utilisateur face à un mur.

---

## PHASE 8 TERMINÉE : estimation fin mai 2026

---

## MILESTONE CHARLOTTE — ~~Beta mi-juin 2026~~ EN COURS (avancé au 16/04)

| Tâche | Complexité | Statut |
|---|---|---|
| 5D-4 Onboarding par tenant | Moyenne | ❌ Planifié |
| 5G-7 Modèle générique de démarrage | Haute | ❌ Planifié |
| Multi-tenant réel (2 sociétés) | — | ✅ Charlotte créée (tenant juillet, tenant_admin) |
| Panel admin tenant_admin | Moyenne | ✅ Accès panel + onglets filtrés |
| Sécurité panel (re-auth MDP) | Moyenne | ✅ Timeout 10 min |
| Cloisonnement OAuth | Critique | ✅ Fallback "guillaume" supprimé |
| Actions directes per-user | Moyenne | ✅ Toggle cycle hérité/ON/OFF |
| Suspension comptes | Moyenne | ✅ Users + tenants + feedback |
| 6-2 Connecteurs réseaux sociaux (LinkedIn, Instagram) | Haute | ❌ Besoin Charlotte |
| Tests multi-tenant complets | — | 🔄 En cours (3 niveaux d'accès à valider) |

**Avancement** : Charlotte est déjà en test sur `https://app.raya-ia.fr`. Le multi-tenant fonctionne. Reste : onboarding, connecteurs sociaux, validation complète des 3 niveaux d'accès.

---

## PHASE COMMERCIALISATION — Juillet-Août 2026

| Tâche | Complexité | Notes |
|---|---|---|
| 8-6 Supervision managériale | Haute | Dashboard admin, métriques équipe, transfert compétences |
| 8-7 Espace perso collaborateur | Moyenne | Mode 3 (avantage en nature), personal_space_enabled |
| 6-1 MCP par tenant | Haute | Outils métier par société |
| 6-3 API externe | Haute | Raya comme service |
| 6-4 Rename aria→raya | Faible | Cosmétique |
| 6-5 Migration Alembic | Moyenne | Scaling |
| 6-6 Migration tool_use natif | Haute | Remplacer [ACTION:...] par function calling |

**Livrable :** Raya prête pour les premiers clients beta externes.

---

## RÉSUMÉ TIMELINE (mise à jour 16/04)

```
12 avril      Phase 5 complète + Phase 7 à 80%
14-15 avril   Audit + SAV + RGPD + Refactoring complet + Multi-tenant + Suspension
16 avril      Architecture connecteurs unifiés + Système mail complet + Audit cœur
17 avril      Audit sécurité + Panels séparés (super admin / tenant admin)
Mi-avril      Sprint restant — Audits actions/scheduler/frontend
Fin avril     Sprint 2-3 — monitoring + WhatsApp bidirectionnel
Mi-mai        Phase 7 complète (Jarvis opérationnel)
Fin mai       Phase 8 complète (intelligence avancée)
Juin          Onboarding premiers clients + connecteurs sociaux
Juillet-Août  Commercialisation (supervision, API, MCP, clients payants)
```

## RISQUES

| Risque | Impact | Mitigation |
|---|---|---|
| Gmail OAuth2 complexe | Retard Sprint 2 | Commencer par polling IMAP si OAuth bloque |
| Twilio Voice (appels) complexe | Retard Sprint 4 | Optionnel, WhatsApp suffit pour le MVP |
| Charlotte pas dispo mi-juin | Retard beta | Simuler un 2e tenant avec un compte test |
| Railway limitations (scaling) | Phase commercialisation | Anticiper migration si nécessaire |
