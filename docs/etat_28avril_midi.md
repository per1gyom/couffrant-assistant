# 📊 État Raya — 28 avril 2026 midi

> **Doc de référence** pour repartir à frais. Mis à jour après la session du 28/04 matin (audit isolation finalisé + nettoyage docs + petites tâches).
>
> Pour l'historique détaillé des chantiers : `docs/etat_complet_chantiers_27avril_nuit.md`.
> Pour la roadmap complète : `docs/a_faire.md`.

---

## ✅ Ce qui est TERMINÉ

### Session 28/04 matin — 9 commits (audit isolation + petites tâches)

| Commit | Sujet |
|---|---|
| `17829b6` | Doc onboarding découverte outils |
| `3f3e1c2` | LOT 2 : bug logique scope I.15 + bonus admin/costs |
| `085542b` | LOT 3a : profile/synthesis/report (I.1-I.6, I.9, I.10) |
| `db2d720` | LOT 3b : memory_teams (I.7, I.8) |
| `5f4283f` | LOT 3c : connection_token_manager (I.14) |
| `e79bb75` | LOT 4 : ATTENTION super_admin + outlook (A.1-A.3, A.5) |
| `516b4e4` | LOT 5 : nettoyage hardcoded_permissions (A.6) |
| `68fbaad` | LOT 6a : renommage backend SCOPE_USER → SCOPE_TENANT_USER + suppression SCOPE_CS |
| `a4bb50b` | LOT 6b : renommage frontend |

**À venir dans le commit suivant** (préparé) :
- Followup A.5 : `username` propagé dans `perform_outlook_action` + 4 call-sites de rédaction de mail
- Nettoyage 28 doublons règles guillaume (archivés via active=false)
- Nettoyage roadmap : 4 sections marquées TERMINÉ
- Doc obsolète archivé : `decision_roles_utilisateurs_a_trancher_RESOLU_28avril.md`

### Sessions précédentes (du 22 au 27/04)

- ✅ Phase B isolation déployée (seat counter + UI quotas + soft-delete + workflow purge + force-purge super_admin)
- ✅ Refonte graphage conversations en temps réel (collecteur d'entités via ContextVar)
- ✅ Suppression code legacy (graph_indexer + odoo_vectorize.py = 1 173 lignes en moins)
- ✅ Nettoyage 1 894 anciens noeuds doublons + 2 517 edges
- ✅ Migration tenant orphelin `couffrant` → `couffrant_solar` (840 563 lignes)
- ✅ Format clés graphe : 100% moderne (odoo:res.partner:3795)
- ✅ Mapping `_enrich_with_graph` : 17 modèles (vs 7 avant)
- ✅ Fix feedback 👍 (TypeError silencieux + metadata stockée en V2)
- ✅ Fix UI badge Sonnet superposé
- ✅ Page /settings : 6 phases déployées
- ✅ Éditeur signatures multi-boîtes complet (avec image + redim + compression)
- ✅ Design system modale unifié

### État DB (28/04 14h00)

```
super_admin  : 1 (guillaume, couffrant_solar)
tenant_admin : 1 (Charlotte, juillet)
tenant_user  : 4 (Arlène, benoit, Pierre, Sabrina)

aria_rules guillaume  : 138 actives (28 doublons archivés ce midi)
                       + 69 inactives (archives historiques)

Graphe conversations  : 6 conv récentes ont des edges (181 mentioned_in)
                       Ancien job graph_indexer supprimé, graphage temps réel OK
```

### Bilan audit isolation 25/04 — 100% TRAITÉ

| Catégorie | Compte | Statut |
|---|---|---|
| 🔴 CRITIQUE | 8 | Tous fixés (étapes 0+A 26/04) |
| 🟠 IMPORTANT | 15 | 14/14 actifs fixés (I.12/I.13 = features intentionnelles) |
| 🟡 ATTENTION | 10 | 9/10 fixés (A.4 = volontairement cross-tenant pour debug) |

**Modèle de rôles tranché** : 4 scopes (`super_admin` / `admin` / `tenant_admin` / `tenant_user`).

---

## 🔄 Ce qui RESTE à faire (par priorité)

### 🟢 Petits trucs à faire à l'occasion

| Tâche | Effort | Note |
|---|---|---|
| Tests bout-en-bout `pierre_test` (plan déjà rédigé) | 1h | À faire par Guillaume plus tard |
| Étendre instrumentation `_teamFetchJson` aux autres pages | 30 min/page | Qualité de vie debug |
| 3 manifests Odoo cassés à régénérer | 1h | Bloqué par retour OpenFire |

### 🟠 Gros chantiers — par ordre logique pour l'avenir

#### 🔴 Haute priorité (bloquant onboarding)

| # | Sujet | Effort | Pourquoi |
|---|---|---|---|
| 1 | **Connexion simplifiée outils tiers** (panel admin tenant — Gmail, M365, Drive, Vesta...) | 3-5 jours | Avant d'onboarder Pierre/Sabrina/Benoît |
| 2 | **Onboarding découverte outils** (mode "tour guidé" super_admin) | 4-6h | Cf. doc dédié `onboarding_decouverte_outils.md`. Évite le bug de ce matin (planning équipe vs Guillaume) |
| 3 | **Plan résilience & sécurité** (2FA + backups auto + UptimeRobot) | 2h15 | Avant tout 2e utilisateur réel |

#### 🟠 Moyenne priorité (qualité)

| # | Sujet | Effort | Note |
|---|---|---|---|
| 4 | **Sujet du moment** : graphe/rendez-vous (Raya doit filtrer par employee pour le planning) | 1-2h | Identifié ce matin, lié au sujet 2 |
| 5 | **Migration cœur graphe V1 → V2** (entity_links → semantic_graph) | 3-5h | Quand on a une matinée complète |
| 6 | **Pool DB résilience** (3 sous-chantiers, voir P7 dans `a_faire.md`) | 4-7h | Arrière-plan, pas urgent |
| 7 | **Job nocturne rules_optimizer** | 3-4h | Débloqué (audit isolation fait) |
| 8 | **Comportement agentique multi-tour** | 1-2h selon test | Lié au sujet 4 |

#### 🟢 Future (valeur élevée mais pas urgent)

| # | Sujet | Effort | Quand |
|---|---|---|---|
| 9 | **Auto-détection des manques** par Raya (re-scan ciblé) | 4-6h | Session dédiée |
| 10 | **Editeur de mail enrichi avec apprentissage par diff** | 6-8h | Vision phare v3 |
| 11 | **Connexion Odoo durable** | 1h+ | Bloqué par OpenFire |

#### 🔵 Pas pour maintenant

| # | Sujet | Effort |
|---|---|---|
| 12 | Renommage Raya → Saiyan / raya-ia.fr → saiyan-ai | Gros chantier dédié |
| 13 | Refonte profonde système graphes | Avec prestataire spécialisé |
| 14 | Promotion règles user → règles tenant | Quand l'archi sera stable |

---

## 🧠 Idées notées (ne pas oublier)

### Comportement agentique multi-tour

Test du 28/04 matin : Raya creuse parfois (Q2), pas toujours (Q1), et peut creuser dans la mauvaise direction (sortie des rendez-vous des collègues au lieu de Guillaume).

3 pistes si modification nécessaire :
1. Renommer les labels techniques (`of.planning.tour` → "Tournée chantier")
2. Ajouter une règle de raisonnement générique au prompt
3. Adoucir la détection de boucle (warning au 3e appel au lieu du 2e)

### Auto-détection des manques

Quand Raya cherche une info absente du graphe → propose un re-scan ciblé. Pas dangereux si :
- Raya **propose** (jamais auto-execute)
- Demande confirmation
- Périmètre limité à 1 record

### Onboarding découverte outils (sujet majeur)

Cf. doc dédié `docs/onboarding_decouverte_outils.md`. Engagement Guillaume du 28/04 :
- Pas attaquer entre 2 chantiers (gros sujet, session dédiée)
- À faire avant ou en parallèle des prochaines connexions (Vesta notamment)
- Ne doit PAS être restreignant (Raya doit rester libre)

---

## 📂 Documents de référence à connaître

| Document | Rôle |
|---|---|
| `docs/a_faire.md` | Roadmap principale (avec sections marquées ✅ TERMINÉ) |
| `docs/etat_28avril_midi.md` | **Ce fichier** — état synthétique au 28/04 |
| `docs/etat_complet_chantiers_27avril_nuit.md` | Historique détaillé des sessions 27-28/04 |
| `docs/audit_isolation_25avril_complementaire.md` | Audit complet (33 findings, tous traités) |
| `docs/onboarding_decouverte_outils.md` | Note sur le sujet du tour guidé d'outils |
| `docs/raya_roles_roadmap.md` | Modèle de rôles 4 scopes (à jour) |
| `docs/archive/decision_roles_utilisateurs_a_trancher_RESOLU_28avril.md` | Doc historique (résolu, archivé) |

---

## 🎯 Recommandation pour la prochaine session

Compte tenu de l'état actuel, **3 chantiers candidats** pour la prochaine grosse session :

### Option A — Sujet du moment (bug graphe/rendez-vous)
**1-2h**, ciblé, concret. Quick fix possible : règle apprise pour Guillaume "filtre par of_employees_names". Fix structurel : modif `search_odoo` calendar.event.

### Option B — Onboarding découverte outils + Connexion simplifiée
**Plusieurs jours**, mais c'est le **vrai bloqueur** pour onboarder de nouveaux users. C'est aussi ce qui résout structurellement le sujet A.

### Option C — Plan résilience & sécurité
**2h15**, important avant tout 2e utilisateur réel.

**Recommandation Claude** : Option A en quick-win d'abord (règle apprise = 15 min, satisfaction immédiate), puis discussion ouverte sur quand attaquer B et C.

---

*Document écrit le 28 avril 2026 à 14h. Dernière mise à jour de la roadmap source : `docs/a_faire.md` à la même date.*
