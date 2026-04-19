# RAYA — PLANNING D'AVANCEMENT V4

**Auteur :** Opus + Guillaume
**Date :** 19 avril 2026 soir
**Remplace :** `raya_planning_v3.md` (obsolète)
**Contexte de la refonte** : après 2 jours de galère sur la vectorisation Odoo, Guillaume recadre l'ordre des priorités. La proactivité (Phase 8) est l'objectif final, mais elle ne peut se faire **que sur un socle de données à jour en temps réel** sur **tous les outils** de l'entreprise.

---

## 🎯 PRINCIPE DIRECTEUR

> **"Raya ne peut pas être proactive si elle ne connaît pas les 2 dernières heures de travail de mes collègues."**
> — Guillaume, 19/04/2026

Conséquence directe : la proactivité (Phase 8) n'est attaquée **qu'après** avoir rendu opérationnelle la chaîne **Connexion → Vectorisation → Mise à jour temps-réel → Graphe** sur **tous les outils** de l'entreprise.

---

## 📋 ORDRE DES PHASES (NOUVEAU)

```
┌────────────────────────────────────────────────────────────────┐
│  A. Socle Scanner Odoo (EN COURS, 90% fait)                    │
│     → Scan complet + Temps-réel + Monitoring                   │
└────────────────────────────────────────────────────────────────┘
                              ↓
┌────────────────────────────────────────────────────────────────┐
│  B. Industrialisation de la méthode de connexion               │
│     → Playbook enrichi + Templates + Checklist + Défauts connus│
└────────────────────────────────────────────────────────────────┘
                              ↓
┌────────────────────────────────────────────────────────────────┐
│  C. Application à tous les outils déjà connectés OAuth         │
│     → Drive SharePoint, Outlook, Gmail (+ suite)               │
└────────────────────────────────────────────────────────────────┘
                              ↓
┌────────────────────────────────────────────────────────────────┐
│  D. Sprints Phase 7 restants (multi-mailbox live, WhatsApp,    │
│     vocal, rapport matinal — REPORTÉ APRÈS C)                  │
└────────────────────────────────────────────────────────────────┘
                              ↓
┌════════════════════════════════════════════════════════════════┐
│  E. PHASE 8 — Intelligence avancée / Proactivité               │
│     OBJECTIF FINAL — possible uniquement si A+B+C sont solides │
└════════════════════════════════════════════════════════════════┘
```


---

## 🔧 PHASE A — Socle Scanner Odoo

**Statut global** : 90% terminé. Reste 2 chantiers majeurs.

### A.1 — Scan nuit complet P1+P2 (PRÊT À LANCER)

| Chantier | Statut | Commentaire |
|---|---|---|
| Test P1 valide (0 modèles abandonnés) | ✅ 19/04 | 26 modèles P1 scannent proprement |
| Test P2 valide (0 modèles abandonnés) | ✅ 19/04 | 13 modèles P2 scannent (2 exclus par droits) |
| Script `scripts/scan_nuit_complet.py` | ⏳ À écrire | Fusion scan_nuit.py + volet P2 complet |
| Exécution manuelle par Guillaume au coucher | 🌙 À venir | Durée estimée 2-3h |
| Objectif DB finale | — | ~50-60k chunks couvrant 28 modèles |

### A.2 — Mise à jour temps-réel Odoo (CHANTIER PRINCIPAL RESTANT)

**Problème** : aujourd'hui, si Arlène crée un devis à 14h, Raya ne le verra pas avant le prochain scan complet (manuel). Impossible d'être proactif dans ces conditions.

**Solution architecturale** (spec déjà écrite dans `docs/odoo_webhook_setup.md`, **non implémentée**) :

```
Odoo/OpenFire
   └─ base_automation.rule sur chaque modèle P1+P2 (on create/write/unlink)
        └─ requests.post(https://app.raya-ia.fr/webhooks/odoo/record-changed)
             ├─ X-Webhook-Token: ODOO_WEBHOOK_SECRET
             └─ payload: {model, record_id, operation, tenant_id}

Raya (à coder)
   └─ POST /webhooks/odoo/record-changed
        ├─ Vérifie le secret
        ├─ Répond 202 immédiat (ne bloque pas Odoo)
        └─ Thread daemon :
             ├─ Fetch record depuis Odoo (1 seul record, pas un batch)
             ├─ Applique manifest → chunk + nodes + edges
             ├─ INSERT ON CONFLICT UPDATE (idempotent)
             └─ Invalide caches éventuels
```

| Chantier | Statut | Commentaire |
|---|---|---|
| Endpoint `POST /webhooks/odoo/record-changed` | ❌ À coder | FastAPI, vérification secret, thread daemon |
| Réutilisation du processor existant | — | processor.process_record() sur 1 record au lieu d'un batch |
| Configuration `base_automation` côté Odoo | ❌ À faire | 1 règle par modèle P1+P2 via System Parameter |
| Fallback polling si webhook down | ❌ À coder | Delta scan `write_date > last_webhook_seen` toutes les 10 min |
| Monitoring | ❌ À coder | Alerte si < N webhooks reçus en 24h (canari) |

**⚠️ Point ouvert** : à discuter ensemble avant de coder. Guillaume souhaite qu'on **réfléchisse à voir si c'est pas trop lourd et que ce soit fluide**. Questions à trancher :

1. **Webhook pour CHAQUE write Odoo** ou agrégation (ex: toutes les 30s) ?
2. **Tous les modèles P1+P2** (28 règles base_automation) ou seulement P1 critique ?
3. **Re-fetch depuis Odoo** à chaque webhook (simple mais coûteux) ou passer directement le payload dans la requête (optimal mais Odoo doit bien formater) ?
4. **Couverture suppression** : base_automation déclenche-t-il bien sur `unlink` dans OpenFire ?


### A.3 — Monitoring de stabilité des connexions

**Problème** : une connexion peut tomber (token expiré, API down, permissions changées) et on ne le sait pas avant que Raya réponde mal.

| Chantier | Statut | Commentaire |
|---|---|---|
| Health check par connecteur (ping périodique) | ❌ À coder | Toutes les 10 min, log succès/échec |
| Alerte WhatsApp/mail si échec > 3 consécutifs | ❌ À coder | Intégrer au système d'alertes existant |
| Dashboard de santé connecteurs | ❌ À coder | Extension du dashboard Intégrité avec ligne par connecteur |
| Auto-reconnexion OAuth si refresh_token valide | ✅ Partiel | Déjà codé pour Microsoft/Gmail, à étendre |

### A.4 — Documentation des défauts connus OpenFire

**Livrable** : section dans `docs/raya_vectorisation_playbook.md` qui liste **tous les défauts connus** rencontrés sur OpenFire (compute fields cassés, droits manquants, etc.) avec leur workaround.

Déjà fait dans `docs/raya_scanner_suspens.md` pour le Scanner Odoo. À consolider dans le playbook.

---

## 🏭 PHASE B — Industrialisation de la méthode de connexion

**Objectif** : passer de "2 jours pour connecter Odoo" à **"moins d'une journée pour un outil standard OAuth2/REST"**.

**Double but** :
1. **Capitaliser** sur nos apprentissages Odoo (défauts connus par plateforme)
2. **Extrapoler une méthode** réutilisable pour un outil inconnu qu'on voudrait brancher demain

### B.1 — Playbook enrichi (`raya_vectorisation_playbook.md` v2)

Sections à ajouter ou enrichir :

| Section | Contenu |
|---|---|
| **Checklist de connexion** | Pas à pas opérationnel (0→1) pour un nouvel outil |
| **Templates de code** | Adaptateur squelette (`adapter_<tool>.py`), manifest minimal, endpoint webhook |
| **Défauts connus par plateforme** | Odoo/OpenFire, SharePoint, Outlook, Gmail (à remplir au fur et à mesure) |
| **Patterns d'erreurs universels** | AccessDenied, TokenExpired, RateLimit, SchemaMismatch, etc. |
| **Tests de validation** | Check-list de validation post-connexion |

### B.2 — Scripts et outils génériques

| Livrable | Usage |
|---|---|
| `scripts/connect_new_tool.py` | Assistant interactif pour branchement d'un nouvel outil |
| `scripts/introspect_<tool>.py` | Introspection schéma (un par plateforme) |
| `scripts/test_<tool>_200.py` | Test 200 records générique |
| Endpoint UI `POST /admin/tool/bootstrap` | Wrapper des 3 scripts ci-dessus via un seul clic |

### B.3 — Objectif mesurable

| Métrique | Cible |
|---|---|
| Temps de connexion outil standard OAuth2/REST | < 1 jour (8h de travail) |
| Temps de connexion outil "exotique" (API custom) | < 3 jours |
| Nombre de chantiers techniques à réécrire par outil | 0 (100% via templates) |
| Couverture temps-réel dès la connexion | 100% (pas d'implémentation séparée) |


---

## 🌐 PHASE C — Application à tous les outils déjà connectés

**Prérequis** : Phase A terminée (Odoo solide avec temps-réel), Phase B matérialisée (playbook + templates).

Chaque sous-phase applique la **même méthode industrialisée** que pour Odoo. L'ordre d'attaque est à décider avec Guillaume.

### C.1 — Drive SharePoint Couffrant

**Spécificités** :
- Fichiers bureautiques (docx, xlsx, pdf) → extraction texte nécessaire
- Graphe : qui a créé / modifié / dossier parent / tags
- Temps-réel : webhooks SharePoint (Graph API change notifications) + fallback polling

**Modèles à considérer** : `file`, `folder`, `modification` (avec auteur, date, taille)

### C.2 — Outlook (Microsoft)

**Volume massif** : inbox + sent + archives + dossiers classés × années d'historique.

**Spécificités** :
- Stratégie historique : scanner par tranches (mois par mois) pour éviter explosion DB
- Plafond applicatif nécessaire (`MODEL_RECORD_LIMITS` côté Outlook ?)
- Pièces jointes : extraire texte ou référencer uniquement ?
- Graphe : expéditeur, destinataires, thread, CC, réponses
- Temps-réel : Graph API subscriptions (webhooks) avec renewal périodique (3j max)

### C.3 — Gmail

**Spécificités** :
- L'onglet "Tous les emails" contient tout (inclus archivés)
- Labels Gmail ≈ dossiers Outlook
- Pas de push webhook natif — Gmail utilise Pub/Sub (plus lourd) ou polling via `history.list`
- Graphe : même structure qu'Outlook (expéditeur, destinataires, thread, labels)

### C.n — Futurs outils

Tout nouvel outil branché via Phase B suit le même pattern. Exemples potentiels :
- LinkedIn, Instagram (réseaux sociaux, besoin Charlotte)
- HubSpot, Salesforce (CRM alternatif)
- Trello, Asana, Notion (gestion de projet)
- Slack, Teams (messagerie équipe)

---

## 📅 PHASE D — Sprints Phase 7 restants (REPORTÉS APRÈS C)

Ces chantiers étaient prioritaires dans v3, ils sont **repoussés après Phase C** car ils n'apportent de la valeur que si les données sont déjà à jour en temps réel.

### Sprint 1 Phase 7 socle
- `7-6R` Redesign rapport matinal (stocké + ping)
- `7-6D` Livraison rapport à la demande
- `7-WF` Workflow intelligence (patterns sur `activity_log`)

### Sprint 2 Multi-mailbox live + Monitoring
- `7-1a` Gmail ingestion temps-réel (l'historique sera déjà fait en C.3)
- `7-1b` Pipeline de triage multi-mailbox unifié
- `7-1c` Config multi-boîte par tenant
- `7-7a` Health monitoring renforcé (recoupement avec A.3)
- `7-7b` Fallback SMS si WhatsApp down

### Sprint 3 WhatsApp bidirectionnel
- `7-8a` Webhook Twilio entrant
- `7-8b` Parser commandes WhatsApp
- `7-8c` Exécution commandes

### Sprint 4 Vocal + polish
- `7-4` Appel vocal sortant (ElevenLabs + Twilio Voice)
- `7-9` Push notifications PWA
- Canaux de livraison dans `tools_registry`


---

## 🧠 PHASE E — OBJECTIF FINAL : Intelligence avancée / Proactivité

**Prérequis absolu** : Phases A + B + C terminées et stables (graphe à jour en temps réel sur **tous** les outils Couffrant).

C'est **le cœur de la valeur Raya**. Une fois les données à jour, on lui apprend à être proactive :

| Tâche | Description |
|---|---|
| `8-1` Workflow automation | Proposer d'automatiser les séquences détectées |
| `8-2` Détection d'oublis | "Tu n'as pas relancé le devis Bidule depuis 15 jours" |
| `8-3` Détection d'anomalies cross-outils | Croiser Odoo / mails / Drive pour repérer incohérences |
| `8-4` Conscience rythme business | Fin de mois = factures, cycles saisonniers |
| `8-5` Méta-apprentissage | Raya apprend de ses erreurs |
| `8-8` Redirection support/admin | "Je ne peux pas → contacte ton admin" |

**Note** : c'est ici que Raya devient vraiment utile au quotidien. Guillaume ne compte attaquer cette phase qu'une fois les phases A-B-C terminées.

---

## 🎯 MILESTONE CHARLOTTE (inchangé)

Charlotte (tenant `juillet`) est déjà en test sur `https://app.raya-ia.fr`. Reste à faire :

| Tâche | Statut |
|---|---|
| `5D-4` Onboarding par tenant | ❌ Planifié |
| `5G-7` Modèle générique de démarrage | ❌ Planifié |
| `6-2` Connecteurs réseaux sociaux (LinkedIn, Instagram) | ❌ Besoin Charlotte |
| Validation 3 niveaux d'accès | 🔄 En cours |

Ne bloque rien pour les phases A/B/C mais à faire avant commercialisation.

---

## 💼 PHASE COMMERCIALISATION — Juillet-Août 2026

À ne pas perdre de vue mais pas prioritaire immédiatement.

| Tâche | Description |
|---|---|
| `8-6` Supervision managériale | Dashboard admin, métriques équipe |
| `8-7` Espace perso collaborateur | Mode 3 (avantage en nature) |
| `6-1` MCP par tenant | Outils métier par société |
| `6-3` API externe | Raya comme service |
| `6-4` Rename aria→raya | Cosmétique |
| `6-5` Migration Alembic | Scaling |
| `6-6` Migration tool_use natif | Remplacer `[ACTION:...]` par function calling |

---

## 📊 TIMELINE INDICATIVE (à revalider régulièrement)

```
19 avril (aujourd'hui)   Scanner Odoo P1+P2 : OK sur test 200
                         Manifests nettoyés, bouton Stop, dashboard propre

Fin avril                A.1 Scan nuit complet P1+P2
                         A.2 Architecture temps-réel Odoo : REFLEXION + POC
                         B.1 Playbook v2 enrichi

Mi-mai                   A.2 Temps-réel Odoo en prod
                         A.3 Monitoring de stabilité
                         B.2 Scripts et templates génériques

Fin mai                  C.1 Drive SharePoint Couffrant

Juin                     C.2 Outlook (tranches historiques)
                         C.3 Gmail (onglet Tous les emails)

Juillet                  D. Sprints Phase 7 restants (rapport, WhatsApp, vocal)

Août                     E. PHASE 8 — Proactivité commence !
                         Charlotte / onboarding / commercialisation en parallèle
```

**⚠️ Discipline** : à chaque fin de phase, on prend 30 min pour mettre ce document à jour avec la réalité terrain (durées réelles, défauts rencontrés, décisions architecturales). Sinon on repart de zéro à chaque reprise.

---

## 🔗 DOCUMENTS ASSOCIÉS

- `docs/raya_vectorisation_playbook.md` — méthode de connexion d'un outil (à enrichir en B)
- `docs/raya_scanner_suspens.md` — défauts connus Odoo/OpenFire, droits manquants
- `docs/odoo_webhook_setup.md` — spec architecture webhook Odoo (non implémentée, base pour A.2)
- `docs/raya_scanner_universel_plan.md` — historique du chantier Scanner
- `docs/raya_planning_v3.md` — **OBSOLÈTE** (remplacé par ce document)


---

## 📋 Annexe Q2 — Répartition des 28 modèles Odoo (validé 19/04/2026)

**Contexte** : on ne peut pas webhooker tous les modèles sans alourdir OpenFire et la config. On sépare en 2 groupes selon la valeur métier pour la proactivité.

### 🟢 Niveau 1 — Webhook temps-réel (14 modèles)

Tout ce qui a de la valeur immédiate pour la proactivité. Une règle `base_automation` par modèle côté OpenFire.

**Socle business** :
- `sale.order` — devis, montants, statuts
- `sale.order.line` — lignes de devis
- `crm.lead` — prospects, qualification
- `mail.activity` — tâches, relances, échéances
- `calendar.event` — rendez-vous, planning
- `res.partner` — clients, contacts
- `account.move` — factures émises/reçues
- `account.payment` — paiements

**Tout ce qui touche une intervention** (ajout 19/04 sur demande Guillaume) :
- `of.planning.tour` — tournées
- `of.planning.task` — interventions (contient le compte-rendu, cf captures)
- `of.planning.intervention.template` — gabarits d'intervention
- `of.survey.answers` — réponses questionnaires (= rapports d'intervention)
- `of.survey.user_input.line` — lignes de réponses
- `of.custom.document` — documents custom liés aux interventions

### ⚪ Niveau 2 — Scan delta nocturne (14 modèles)

Modèles à moindre valeur temps-réel. Rattrapés toutes les nuits à 3h via `write_date > last_sync`.

- `account.move.line` — lignes de facturation (cascade de `account.move`)
- `of.sale.payment.schedule`, `of.account.move.payment.schedule` — échéanciers
- `stock.picking` — livraisons/expéditions
- `of.image` — photos d'intervention (volumes)
- `product.template`, `product.product` — catalogue articles (évolue lentement)
- `of.product.pack.lines`, `product.pack.line`, `of.invoice.product.pack.lines` — composants kits
- `sale.order.template`, `sale.order.template.line` — gabarits devis
- `hr.employee` — collaborateurs
- `of.planning.tour.line`, `of.planning.intervention.section` — sous-lignes
- `of.custom.document.field` — métadonnées
- `mail.tracking.value` — audit log (redondant avec les webhooks des modèles sources)
- `mail.message` — bloqué suspens #3 (droits)
- `of.service.request` — 2 records, négligeable

### 🚀 Déploiement progressif validé

| Phase | Modèles ajoutés | Objectif |
|---|---|---|
| Pilote | `sale.order`, `crm.lead`, `mail.activity` (3) | Valider l'architecture sur 48h réelles |
| Vague 2 | `sale.order.line`, `calendar.event`, `res.partner`, `account.move`, `account.payment` (5) | Compléter le socle business |
| Vague 3 | 6 modèles intervention | Couverture complète |

### 💡 Point à rouvrir plus tard

- **Étiquette `COMPTE-RENDU A LIRE`** repérée sur les interventions OpenFire : **signal proactif de grande valeur** pour la Phase 8. À exploiter quand Raya sera proactive (détection automatique → propositions d'actions).
- **Champ exact du compte-rendu** dans `of.planning.task` : à identifier précisément au moment de configurer la première règle `base_automation`.
</content>