# Architecture des connexions Raya

**Version** : 1.0 (20 avril 2026)
**Statut** : référence active

Ce document formalise le modèle mental qui guide toutes les décisions d'architecture autour des connexions et des données dans Raya.

---

## 🎯 Le principe directeur

Pour chaque source de données (Odoo, SharePoint, Outlook, Gmail, etc.), **deux questions indépendantes** :

1. **Le contenu est-il partagé ou personnel ?** → détermine le scope de vectorisation
2. **Les actions sont-elles traçables par user ?** → détermine quels identifiants utiliser pour les lectures et écritures

Ces deux dimensions sont **orthogonales**. On peut avoir :
- Un contenu partagé avec des actions non-traçables (ex: SharePoint avec API générique)
- Un contenu partagé avec des actions traçables (ex: SharePoint avec tokens OAuth de chaque user)
- Un contenu personnel par définition traçable (ex: Gmail de chaque collaborateur)


## 📊 Tableau de référence par source

| Source | Contenu | Vectorisation | Actions (lecture/écriture) |
|---|---|---|---|
| **SharePoint Photovoltaïque** | Partagé (tous) | 1× au scope `tenant_id` | Tokens OAuth Microsoft du user qui agit |
| **SharePoint Direction** (à venir) | Partagé (restreint : Guillaume + Arlène) | 1× au scope `tenant_id` avec assignments restreints | Idem |
| **Outlook personnel** (chaque user) | Personnel | 1× par user avec scope `user_id + tenant_id` | Tokens OAuth du user concerné |
| **Shared mailbox** (ex: `contact@couffrant-solar.fr`) | Partagé M365 (Arlène principale + Guillaume + Pierre backup) | 1× au scope `tenant_id` | Tokens OAuth du user qui agit (scope `Mail.Read.Shared`) |
| **OneDrive personnel** | Personnel | 1× par user | Tokens OAuth du user |
| **Gmail personnel** (Guillaume Gmail) | Personnel | 1× par user | Tokens OAuth du user |
| **Odoo / OpenFire** | Partagé (système) | 1× au scope `tenant_id` avec `raya_admin` | Cible : 1 API key par user (`raya_guillaume`, `raya_arlene`...) pour traçabilité. Aujourd'hui : 1 seule API key partagée |

## 🗂️ Le cas SharePoint en détail

C'est la source la plus subtile, d'où l'attention particulière.

### Ce que SharePoint EST réellement

- Un **dossier commun** à la société, hébergé chez Microsoft 365
- **Chaque collaborateur** accède avec **son propre compte Microsoft** (`guillaume@couffrant-solar.fr`, `contact@couffrant-solar.fr` pour Arlène, etc.)
- Chaque accès arrive sur **le même stockage physique**. Les modifications sont tracées par l'identité qui les fait (Guillaume, Arlène, Pierre…)

### Ce qui est partagé vs ce qui ne l'est pas

- ✅ **Le contenu** (fichiers, arborescence) : partagé. Même stockage Microsoft pour tous.
- ✅ **Le graphe sémantique** que Raya construit : partagé. Inutile de le reconstruire pour chaque user.
- ❌ **Les credentials d'accès** : individuels. Pas de token partagé.
- ❌ **Les permissions côté Microsoft** : individuelles. Microsoft gère déjà qui a droit à quoi.

### Conséquence architecturale

- **La vectorisation du SharePoint se fait 1 seule fois** au scope `tenant_id`, idéalement via un user "admin" qui a Full Access sur le SharePoint (aujourd'hui : Guillaume)
- **Les lectures/questions des users** passent par leurs propres tokens OAuth. Microsoft Graph vérifie nativement si le user a droit d'accès au fichier avant de retourner le contenu.
- **Les écritures** (commentaires, déplacement de fichiers, upload) sont faites avec les tokens du user qui demande l'action → traçabilité garantie dans SharePoint.


## 🔧 Le cas Odoo en détail

### État actuel (20/04/2026)

- **1 seule API key OpenFire** nommée `raya`, utilisée pour TOUT :
  - Le polling 2 min qui détecte les modifications
  - La vectorisation initiale des modèles
  - Les actions d'écriture (commentaires, créations, MAJ)
- **Conséquence** : toutes les actions Odoo sont tracées `raya` comme auteur, pas le vrai collaborateur qui a demandé l'action via Raya.

### État cible (étape B, prochaine session)

- **1 API key système** : `raya_admin` pour le polling + vectorisation + scans de rattrapage. Scope tenant.
- **1 API key par collaborateur** : `raya_guillaume`, `raya_arlene`, `raya_benoit`, `raya_sabrina`, `raya_pierre`. Utilisées pour les actions d'écriture initiées par ce collaborateur via Raya.
- **Conséquence** : quand Guillaume demande à Raya *"crée un devis pour le client X"*, Odoo trace `raya_guillaume` comme auteur → traçabilité complète, responsabilité identifiable.

### Création des API keys

Guillaume crée lui-même les 6 API keys côté OpenFire (il a déjà créé la première `raya`). Pas besoin de demande externe.

## 📚 Tables Postgres concernées

| Table | Rôle | Statut |
|---|---|---|
| `tenant_connections` | Une ligne par lien tenant ↔ outil ↔ user. Architecture V2. | ✅ Référence active |
| `oauth_tokens` | Tokens OAuth Microsoft (legacy). Encore utilisée par `drive_scanner.py` via `get_valid_microsoft_token(username)`. | ⚠️ DEPRECATED mais encore utilisée — migration partielle |
| `gmail_tokens` | Tokens Gmail legacy. | ⚠️ DEPRECATED — à purger quand l'user correspondant est migré |
| `drive_semantic_content` | Contenu vectorisé du SharePoint. Stocke `tenant_id` (pas `user_id`) → scope tenant. | ✅ Référence active |
| `drive_folders` | Dossiers SharePoint configurés pour scan. Un par tenant. | ✅ Référence active |
| `connection_assignments` | Liens entre une `tenant_connections` et un username. Contrôle qui peut utiliser cette connexion. | ✅ Référence active |

## 🚧 Roadmap de convergence (étape B)

1. Créer les 6 API keys Odoo (`raya_admin` + 5 utilisateurs) côté OpenFire
2. Refonte `tenant_connections` Odoo : 1 ligne système + 1 ligne par user, avec dispatching automatique selon qui demande l'action
3. Ajouter scopes `Mail.Read.Shared` + `Mail.Send.Shared` à Microsoft OAuth pour gérer les shared mailboxes (ex: `contact@couffrant-solar.fr`)
4. Généraliser `drive_scanner` pour accepter n'importe quel user assigné comme "admin SharePoint" (plus hardcoder `guillaume`)
5. Brancher `retrieval.py` sur `drive_semantic_content` avec filtre par assignment
6. UI "Ajouter un autre SharePoint" (ex: SharePoint Direction avec scope restreint)
7. Migration complète `oauth_tokens` → `tenant_connections.credentials`, suppression de l'ancienne table

## 📌 Règles à ne pas oublier

- **Ne jamais dupliquer le contenu**. Si c'est partagé, 1 seule vectorisation au scope tenant.
- **Les permissions sont du ressort de la source** (Microsoft pour SharePoint, OpenFire pour Odoo). Raya ne doit jamais se substituer à elles.
- **Chaque ligne de connexion a UN rôle clair**. Si la même ligne semble servir à 3 choses différentes, c'est qu'il en manque 2.
- **Tracabilité** : chaque action d'écriture passe par les credentials du user qui a demandé l'action.
