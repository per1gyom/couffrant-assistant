# 📚 Documentation Raya — Index

Bienvenue dans la documentation du projet Raya. Ce dossier contient les documents **actifs** — c'est-à-dire ceux qui servent de référence pour le projet en cours.

Les documents historiques (roadmaps v1/v2, spécifications remplacées, livrables conclus, sessions ponctuelles) sont dans `archives/` avec leur propre README.

**Dernière mise à jour de cet index** : 20 avril 2026

---

## 🎯 Démarrage — Lire en premier

1. **`raya_vision_guillaume.md`** — la vision globale du projet, le "pourquoi"
2. **`vision_architecture_raya.md`** — 🔥 **référence architecturale** (minimaliste, anti-bâillonnage, 20/04 soir)
3. **`raya_planning_v4.md`** — la roadmap active, ce qu'on fait en ce moment
4. **`raya_principe_memoire_3_niveaux.md`** — principe architectural universel (adopté 20/04)
5. **`raya_memory_architecture.md`** — les 4 couches mémoire (Live / Graphe / Vectorisation / Surveillance)
6. **`architecture_connexions.md`** — modèle mental connexions (scope tenant vs user)

## 🛠️ Références techniques

| Document | Rôle |
|---|---|
| `raya_vectorisation_playbook.md` | Méthode éprouvée pour connecter un nouvel outil à Raya |
| `raya_capabilities_matrix.md` | Matrice des capacités Raya (ce qu'elle sait faire, ce qu'elle ne sait pas) |
| `spec_connecteurs_v2.md` | Spec technique des connecteurs (Odoo, Microsoft, Google) |
| `raya_roles_roadmap.md` | Modèle de rôles super_admin / admin / tenant_admin / user |
| `onboarding_nouveau_tenant.md` | Procédure pour brancher un nouveau tenant client |
| `raya_style_guide.md` | Guide de style visuel et tonal de Raya |
| `raya_test_protocol.md` | Protocole de test (check-list à dérouler) |
| `raya_maintenance.md` | Guide de maintenance |
| `raya_changelog.md` | Log des changements livrés |

## 🎯 Intégrations en cours

| Document | Statut |
|---|---|
| `architecture_connexions.md` | 📐 Modèle mental de référence pour toute source de données |
| `odoo_integration_etat_actuel.md` | ✅ Polling en place (1-2 min latence) |
| `audit_drive_sharepoint_20avril.md` | ✅ Scan initial réussi (3252/3492 fichiers), plan Drive complet |
| `guide_configuration_shared_mailbox.md` | 📋 Guide pour toi : configurer `contact@couffrant-solar.fr` en shared mailbox M365 |
| `raya_couche5_apprentissage_permanent.md` | 💭 Idée capturée, implémentation à venir |
| `raya_scanner_suspens.md` | 🔗 Suspens techniques par modèle Odoo (droits manquants, etc.) |

## 📨 Demandes en cours auprès d'OpenFire

| Document | Statut |
|---|---|
| `suivis_demandes_openfire.md` | 📍 Tracking central des 2 demandes |
| `demande_openfire_droits_produits_lignes.md` | ⏳ Envoyé 20/04 soir, en attente |
| `demande_openfire_webhooks_temps_reel.md` | ⏳ Envoyé 20/04 matin, en attente |

## 📦 Documents historiques

Tout ce qui est conclu / remplacé / non prioritaire est dans `archives/`.
Voir `archives/README.md` pour la table des matières.

---

## 📐 Conventions

- **Français** dans les documents (français technique quand nécessaire)
- **Markdown** (titres avec `#`, listes avec `-`, tableaux avec `|`)
- **Pas d'emojis en overdose** — ils servent à catégoriser (🔴 problème, 🟢 OK, 💭 idée, ⏳ en attente, ✅ fait)
- **Dater les documents** en haut quand ils marquent une décision
- **Commencer par le contexte** avant la spec technique

## 🔄 Quand ajouter / archiver un doc

**Ajouter un doc dans `docs/`** quand :
- Tu poses une décision architecturale qui doit rester visible
- Tu rédiges une spec qui guide des chantiers à venir
- Tu documentes une procédure qu'il faudra suivre

**Déplacer en archives** quand :
- Le chantier documenté est terminé et la livraison faite
- Le doc est remplacé par une version plus récente
- La spec décrite est obsolète parce que le contexte a changé

**Dans tous les cas** : ne pas modifier un doc archivé. S'il faut en extraire de l'info, mieux vaut créer un nouveau doc dans `docs/` qui fait référence à l'archive.
