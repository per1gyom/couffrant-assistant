# 📦 Archives documentation Raya

Ce dossier contient les documents **historiques** du projet Raya, rangés ici parce qu'ils ne sont plus la référence active mais gardent une valeur de mémoire (décisions passées, raisonnements, livraisons conclues).

**Rangés ici le 20 avril 2026** lors d'un tri général.

Rien n'a été modifié — les documents sont dans leur état de l'époque.

---

## 🗺️ Roadmaps et planning historiques

| Fichier | Date | Remplacé par |
|---|---|---|
| `raya_roadmap_v2.md` | avant 15/04 | `raya_planning_v4.md` |
| `raya_roadmap_v2.1.md` | avant 19/04 | idem |
| `raya_roadmap_v2.2.md` | avant 19/04 | idem |
| `raya_roadmap_v2.3.md` | 19/04 | idem |
| `raya_roadmap_demo.md` | 15/04 | obsolète (démo faite) |
| `raya_planning_v3.md` | 19/04 | `raya_planning_v4.md` |

## 🔐 Permissions v1 (implémentées, en place)

| Fichier | Nature |
|---|---|
| `raya_permissions_plan.md` | Plan initial |
| `raya_permissions_audit_rapport.md` | Rapport d'audit |
| `raya_permissions_audit_todo.md` | TODO issue de l'audit |
| `raya_permissions_v1_livraison.md` | Document de livraison |

Le système de permissions 3 niveaux (lecture / écriture / suppression) est en place dans le code, ces docs servent de mémoire de conception.

## 🔎 Scanner Universel (phases conclues)

| Fichier | Contenu |
|---|---|
| `raya_scanner_universel_plan.md` | Plan général du scanner |
| `raya_scanner_audit_rapport.md` | Audit v1 |
| `raya_scanner_audit_2_rapport.md` | Audit v2 |
| `raya_scanner_etape_a_resultats.md` | Résultats étape A |
| `raya_scanner_etape_a_finale.md` | Finale étape A |

Le Scanner Universel tourne en production depuis le 19/04 soir. Ces docs sont la trace des étapes franchies.

## 🔌 Webhooks Odoo (spec périmée par sandbox Odoo 16)

| Fichier | Pourquoi archivé |
|---|---|
| `odoo_webhook_setup.md` | Spec du 18/04 pour les webhooks via base_automation — inapplicable à cause du blocage sandbox Odoo 16 Community |
| `odoo_webhook_setup_guide_couffrant.md` | Guide de configuration pour Guillaume basé sur la même spec — périmé |

La spec actualisée se trouve dans `docs/odoo_integration_etat_actuel.md` et les demandes de déblocage dans `docs/suivis_demandes_openfire.md`.

## 📱 Flutter (pas prioritaire actuellement)

| Fichier | Contenu |
|---|---|
| `raya_flutter_prompt_reprise.md` | Prompt de reprise session Flutter |
| `raya_flutter_session.md` | Session de travail Flutter |
| `raya_flutter_ux_specs.md` | Specs UX |

Le chat mobile Flutter est dans la roadmap mais pas prioritaire pour le moment. Ces docs serviront quand on reprendra.

## 📚 Sessions et briefings ponctuels

| Fichier | Contenu |
|---|---|
| `raya_session_state.md` | Snapshot d'état à un moment donné (19/04) |
| `raya_session_18avril_soiree.md` | Session de travail du 18/04 soir |
| `raya_addendum_phase25_briefing_phase3.md` | Briefing transition phase 2.5 → 3 |
| `raya_bugs_et_securite_plan.md` | Plan bugs et sécu (traité) |
| `approches_abandonnees_20avril.md` | 🧭 Architectures discutées puis écartées le 20/04 soir (tags par source, détecteur de doute, mode recovery scripté, règles conditionnelles, routage Sonnet, bâillonnages divers) — à relire avant de ré-ajouter des règles |

---

## 🔙 Si tu veux ressortir un doc des archives

```bash
git mv docs/archives/<nom_du_doc>.md docs/<nom_du_doc>.md
```

Mais réfléchis-y à deux fois — si tu as besoin de son contenu, c'est souvent plus propre de créer un nouveau doc de référence qui cite celui-ci.
