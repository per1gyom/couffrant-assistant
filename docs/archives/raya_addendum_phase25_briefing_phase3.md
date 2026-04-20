# Addendum Phase 2.5 + Briefing Phase 3
**Projet :** Raya
**Architecte :** Claude Opus 4.6
**Destinataires :** Guillaume Perrin (décideur) + Claude Sonnet 4.6 (exécutant)
**Date :** 10 avril 2026
**Statut :** Document de travail actif — à lire en entier avant de commencer la Phase 3a

---

## PARTIE A — Correctifs immédiats (appliqués le 10 avril 2026)

### A1 — Deux fallbacks hardcodés supprimés dans rule_engine.py ✅
- `parse_business_priority` : fallbacks PV supprimés → `return "a_traiter"` neutre
- `get_internal_domains` : fallback `["couffrant-solar.fr"]` supprimé → `return domains`
- **SHA :** `723bcc0`

### A2 — Tier "deep" (Opus) ajouté dans llm_client.py ✅
- `_PROVIDER_MODELS["anthropic"]["deep"] = "claude-opus-4-6-20260401"`
- Utilisé pour synthèse, hot_summary, onboarding, audit de cohérence des règles
- **SHA :** `fcc0817`

### A3 — Webhook Teams ValidationError 400 corrigé ✅
- **Root cause :** Microsoft envoie un POST avec `?validationToken=xxx` pour valider l'URL.
  Le handler POST essayait de parser le body JSON (vide lors de la validation), échouait,
  et retournait 202 au lieu de 200 + token en text/plain. Microsoft refusait la subscription.
- **Fix :** vérification de `request.query_params.get("validationToken")` en priorité absolue,
  avant tout parsing JSON.
- **Bonus :** migration du micro-appel OUI/NON vers `llm_complete(model_tier="fast")`
- **SHA :** `0906b7d`

---

## PARTIE B — Décisions architecturales validées par Opus

### B1 — Architecture LLM à trois tiers avec routage automatique
- **fast (Haiku)** : filtrage mails OUI/NON, classification rapide, routage de tier
- **smart (Sonnet)** : conversations quotidiennes, analyse mails, suggestions
- **deep (Opus)** : synthèse de sessions, hot_summary, audit cohérence, onboarding, questions complexes

Routage automatique : micro-appel Haiku (max_tokens=3) classifie SIMPLE/COMPLEXE → Sonnet ou Opus.
Garde-fou économique : compteur quotidien d'appels Opus configurable par tenant.

### B2 — Pipeline mails à trois niveaux
Cascade Haiku → Sonnet → Opus.
- Haiku : triage (IGNORER / STOCKER SIMPLE / ANALYSER)
- Sonnet : analyse complète avec champ `needs_deep_review` dans la réponse JSON
- Opus : uniquement sur les mails flaggés `needs_deep_review`
Estimation : sur 50 mails/jour → ~30 éliminés Haiku, ~17 Sonnet, ~3 Opus.

### B3 — Vectorisation des règles et RAG contextuel
Les règles dans `aria_rules` sont vectorisées au moment de `save_rule`.
Au lieu d'injecter 60 règles en bloc → recherche de similarité + injection des 8-10 plus pertinentes.
Éléments toujours injectés : hot_summary + garde-fous + pending_actions.
Éléments RAG : top N règles + insights + mails + conversations passées pertinents.

### B4 — Synthèse de sessions par Opus
`synthesize_session` migre vers `model_tier="deep"`.
Le prompt inclut les règles existantes pour éviter les doublons sémantiques.
Seuil de synthèse : migrer de "nombre fixe" vers "seuil de tokens accumulés".

### B5 — Audit hebdomadaire de cohérence des règles
Job hebdomadaire (Phase 4) : envoie les règles actives à Opus → identifie contradictions, redondances, obsolètes.
Résultats présentés comme suggestions, pas actions automatiques.

### B6 — Décroissance temporelle de confiance
Règles non renforcées : -0.05 confiance/mois d'inactivité.
Sous 0.3 → masquées du RAG mais pas supprimées.
Compteur `used_count` incrémenté quand une règle est injectée dans un prompt positif.

### B7 — Boucle de correction par feedback
Boutons 👍 👎 sous chaque réponse Raya.
👎 → mini-dialogue → Opus formule une règle corrective.
👍 → renforcement silencieux des règles dans le contexte.

### B8 — Sessions de travail thématiques
Détection automatique (Haiku) de cohérence thématique des derniers échanges.
Enrichissement RAG contextuel sur le sujet en cours.
Proposition de reprise après une pause.

### B9 — Transparence du raisonnement
Bouton "Pourquoi ?" → quelles règles injectées, quels mails/insights RAG, quel tier utilisé.
Stocké en base à chaque réponse.

### B10 — Proactivité (cerveau central)
Notifications à trois niveaux :
- Alertes critiques (toujours) : mail urgent non lu, RDV imminent, token expirant
- Rappels intelligents (activable) : dossier en retard, échéance, relance
- Suggestions proactives (activable) : patterns détectés, améliorations productivité
Job périodique ~30 min. Haiku pour triage, Sonnet pour formulation.

### B11 — Multi-tenant par utilisateur
- Standard (mono-tenant) : voit uniquement son tenant
- Admin multi-tenant : voit TOUS ses tenants simultanément, Raya croise et conseille
Routage d'écriture par Haiku : dans quel tenant ranger la donnée.
Si ambigu → espace personnel de l'utilisateur (reclassement possible plus tard).
Table nécessaire : `user_tenant_access (user_id, tenant_id, role, multi_tenant BOOLEAN)`.

### B12 — Collaboration intra-tenant (scope des règles)
Chaque règle a un scope `tenant` (partagée) ou `user` (personnelle).
Règles métier = scope tenant par défaut. Préférences perso = scope user.
Conflit → règle user l'emporte pour cet utilisateur.

### B13 — Onboarding structuré par Opus
À la première connexion : Opus mène une conversation de découverte.
10-15 questions en 4 blocs (contexte pro, outils/habitudes, préférences communication, contexte métier).
Génère automatiquement règles + profil + insights vectorisés.
Skippable. Relançable à tout moment.

### B14 — Mémoire hybride à 4 couches
1. **Relationnelle** (SQL) : contacts, faits précis, requêtables par SQL
2. **Sémantique** (vectorisation + RAG) : règles, insights, patterns
3. **Épisodique** (session_digests) : résumés avec contexte temporel et émotionnel
4. **Procédurale** (skills, Phase 5) : séquences d'outils pour tâches complexes
Fusion à chaque conversation : 4 couches interrogées en parallèle.

### B15 — Détection d'usage hors-cadre
Pour users salariés (scope=user) : détection conversations hors-cadre professionnel.
Seuil configurable par tenant_admin. Stats pro/hors-sujet dans dashboard.

### B16 — MCP par tenant avec facturation à la carte
Chaque tenant a sa propre config de serveurs MCP.
Le nombre de MCP actifs est un axe de pricing.

### B17 — Suivi des coûts et quotas par tenant
Endpoint `/admin/costs` : données `llm_usage` agrégées par tenant/user/jour/tier.
Base pour facturation des surcoûts et détection de dérives.
Table `llm_usage` déjà en place depuis la Phase 2.

### B18 — Multi-modalité (lecture ET modification de documents)
Raya lit et modifie des fichiers (PDF, images, documents).
Via MCP ou skills Python. Phase 5.

### B19 — Résilience et dégradation gracieuse
Anthropic tombe → message clair + connecteurs fonctionnels.
Graph tombe → cache et données locales.
Chaque dégradation signalée honnêtement. Dernière phase avant commercialisation.

### B20 — Renommage aria → raya
À la toute fin du projet. Tables SQL, fichiers Python, imports — tout en une passe propre.

---

## PARTIE C — Modèle de facturation

```
Forfait tenant de base          : 150-300 €/mois
  → 5 utilisateurs standard + 1 tenant_admin + seeding + onboarding Opus

Utilisateur supplémentaire      : 30-50 €/mois
Accès multi-tenant par user     : 50-80 €/mois par tenant supplémentaire
Serveur MCP supplémentaire      : à définir
Surcoût usage LLM               : au-delà du quota inclus
```

Offre de lancement : prix unique par tenant, tout inclus, ajusté au cas par cas.

---

## PARTIE D — Phasage Phase 3

### Phase 3a — RAG vectoriel + Synthèse Opus (2 semaines)
- Vectorisation des règles dans `aria_rules` au moment de `save_rule`
- Module `app/rag.py` : recherche similarité sur règles, insights, mails, conversations
- `build_system_prompt` : injection par RAG au lieu d'injection en bloc
- `synthesize_session` → `model_tier="deep"` + injection des règles existantes
- `rebuild_hot_summary` → `model_tier="deep"`
- Module `app/router.py` : unification de tous les micro-appels Haiku
- Routage automatique de tier LLM (Haiku classifie → Sonnet ou Opus répond)

### Phase 3b — Boucle de correction + Sessions thématiques + Transparence (1 semaine)
- Boutons 👍👎 frontend + endpoint backend + appel Opus pour règle corrective
- Détection session de travail thématique + enrichissement RAG contextuel
- Stockage métadonnées de raisonnement à chaque réponse
- Bouton "Pourquoi ?" frontend

### Phase 3c — Onboarding + Registre d'outils + Permissions (1 semaine)
- Onboarding structuré Opus à la première connexion (4 blocs, skippable)
- Table `tools_registry` : chaque outil enregistré avec nom, description, schéma, sensibilité, permissions
- Migration progressive des actions [ACTION:...] vers tool use natif Anthropic
- Permissions granulaires par utilisateur sur les outils

---

## PARTIE E — Points de vigilance pour Sonnet

### À NE PAS faire
- Ne pas introduire LangChain, LangGraph, CrewAI — Raya a son propre mécanisme d'orchestration
- Ne pas créer de base vectorielle séparée (Pinecone, Weaviate) — pgvector suffit
- Ne pas hardcoder de règles métier dans le code — tout via `aria_rules` et seeding
- Ne pas supprimer les `DEFAULT 'guillaume'` SQL sans migration de backfill préalable

### À TOUJOURS faire
- Passer `tenant_id` à toute fonction qui lit ou écrit dans une table scopée
- Tout nouvel outil/skill → `tools_registry` (quand il existera), pas hardcodé dans le prompt
- Toute action sensible → `pending_actions` (queue de confirmation). Pas d'exception.
- Tout appel LLM → `llm_client.llm_complete()` + `log_llm_usage()`. Plus d'appel direct anthropic.
- Tout micro-appel Haiku → `app/router.py` (quand il existera). Pas de duplication.

### En cas de doute architectural
Demander à Guillaume, qui consulte Opus. Ne pas inventer de solution d'architecture sans validation.

---

## PARTIE F — Documents de référence

| Document | Contenu | Statut |
|---|---|---|
| `audit_raya_v2_code_based.md` | État des lieux avant Phase 0 | ✅ Historique |
| `raya_phase0_architecture.md` | Cahier d'exécution Phase 0+2 (15 étapes) | ✅ Exécuté |
| `raya_roadmap_phase3_et_au_dela.md` | Vision Phase 3, 4, 5+ | ✅ Référence |
| **`raya_addendum_phase25_briefing_phase3.md`** | **Ce document — décisions Opus + briefing Phase 3** | ✅ **Document de travail actif** |
| `docs/onboarding_nouveau_tenant.md` | Procédure onboarding nouveau tenant | ✅ Opérationnel |
