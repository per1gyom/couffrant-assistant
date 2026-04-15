# Raya — Spec : Architecture Connecteurs v2

**Auteur :** Opus — **Date :** 16/04/2026
**Statut :** PROPOSITION — à valider par Guillaume

---

## 1. PROBLÈME ACTUEL

Le modèle actuel est `user_tools` : 1 ligne = 1 utilisateur × 1 type d'outil.

```
guillaume × outlook × full × {mailboxes: []}
Arlène   × outlook × write × {mailboxes: []}
```

**Limites :**
- Pas de notion de "compte connecté" (quel token ? quelles credentials ?)
- Impossible d'avoir 2 SharePoint différents dans la même société
- Impossible de partager une boîte mail entre 2 users
- Les tokens OAuth sont stockés à part (`oauth_tokens`) sans lien avec les outils
- Chaque user a "outlook" mais c'est le même token Guillaume qui est utilisé

## 2. MODÈLE CIBLE

### Principe : Connexion = instance d'un outil avec ses credentials propres

```
SOCIÉTÉ (tenant)
  └── CONNEXIONS (instances de tools avec credentials)
        ├── "SharePoint Commun"     [drive]   → assigné à: tous
        ├── "SharePoint Projets"    [drive]   → assigné à: Guillaume, Pierre
        ├── "guillaume@couffrant"   [outlook] → assigné à: Guillaume
        ├── "contact@couffrant"     [outlook] → assigné à: Arlène, Guillaume
        ├── "arlene@couffrant"      [outlook] → assigné à: Arlène
        ├── "Odoo Guillaume"        [odoo]    → assigné à: Guillaume
        └── "Odoo Arlène"           [odoo]    → assigné à: Arlène
```


### Nouvelle table : `tenant_connections`

| Colonne | Type | Description |
|---|---|---|
| id | SERIAL PK | ID unique de la connexion |
| tenant_id | TEXT FK | Société propriétaire |
| tool_type | TEXT | `outlook`, `gmail`, `drive`, `odoo`, `teams`, `whatsapp` |
| label | TEXT | Nom lisible : "SharePoint Commun", "contact@couffrant.fr" |
| auth_type | TEXT | `oauth_microsoft`, `oauth_google`, `api_key`, `credentials`, `shared` |
| credentials | JSONB (chiffré) | Tokens OAuth, clés API, identifiants — chiffré en DB |
| config | JSONB | Config spécifique (site SharePoint, dossier, etc.) |
| status | TEXT | `connected`, `expired`, `not_configured` |
| created_by | TEXT | Username du créateur |
| created_at | TIMESTAMP | |
| updated_at | TIMESTAMP | |

### Nouvelle table : `connection_assignments`

| Colonne | Type | Description |
|---|---|---|
| connection_id | INT FK | → tenant_connections.id |
| username | TEXT FK | → users.username |
| access_level | TEXT | `read_only`, `write`, `full` |
| enabled | BOOLEAN | Actif/inactif pour cet user |
| UNIQUE | | (connection_id, username) |

### Migration depuis l'existant

L'ancienne table `user_tools` reste en place pendant la transition.
La migration crée automatiquement :
- 1 `tenant_connection` par token OAuth existant
- Les assignments correspondants


## 3. FLUX UTILISATEUR (Panel Admin)

### Créer une connexion (tenant admin ou super admin)

1. Onglet Sociétés → ouvrir la fiche société
2. Section "Connexions" → bouton **+ Ajouter une connexion**
3. Choisir le type : Outlook / Gmail / Drive / Odoo / Teams / WhatsApp
4. Selon le type :
   - **OAuth (Outlook, Gmail)** : cliquer "Connecter" → flux OAuth → token sauvé dans `tenant_connections`
   - **Drive/SharePoint** : saisir site + dossier + bibliothèque
   - **Odoo** : saisir URL + API key + user ID
   - **API key** : saisir la clé
5. Donner un label : "Boîte perso Guillaume", "SharePoint Commun", etc.
6. Connexion créée avec statut `connected`

### Assigner une connexion à des utilisateurs

1. Sur la connexion créée → bouton **Assigner**
2. Liste des users de la société avec checkboxes
3. Choisir le niveau d'accès par user (lecture seule / écriture / complet)
4. Valider → `connection_assignments` créés

### Vue par utilisateur

Dans la fiche user (bouton 🔧), on voit :
- Toutes les connexions assignées à cet user
- Le niveau d'accès
- Le statut de chaque connexion (connected/expired)
- Possibilité de retirer une assignation

## 4. IMPACT SUR LE CHAT (Raya Core)

Quand Raya traite un message pour un user :

```python
# Ancien modèle
tools = load_user_tools(username)  # → {outlook: {access: full}, drive: {access: write}}
token = get_valid_microsoft_token(username)  # → 1 seul token

# Nouveau modèle
connections = get_user_connections(username, tenant_id)
# → [
#     {id: 1, type: "outlook", label: "guillaume@couffrant", token: "xxx", access: "full"},
#     {id: 2, type: "outlook", label: "contact@couffrant", token: "yyy", access: "write"},
#     {id: 3, type: "drive", label: "SharePoint Commun", config: {...}, access: "full"},
#   ]
```

Raya sait alors :
- Quelles boîtes mail lire (pas juste "outlook oui/non" mais LESQUELLES)
- Quel Drive interroger (le bon SharePoint, pas celui d'une autre société)
- Avec quels credentials (chaque connexion a ses propres tokens)


## 5. PLAN D'IMPLÉMENTATION (3 phases)

### Phase A — Schema + Migration (1 session)
- [ ] Créer tables `tenant_connections` + `connection_assignments`
- [ ] Migration automatique depuis `user_tools` + `oauth_tokens`
- [ ] Fonctions CRUD : `create_connection()`, `assign_connection()`, `get_user_connections()`
- [ ] Endpoints API admin : CRUD connexions + assignments
- [ ] Tests : créer une connexion, l'assigner, la lire

### Phase B — Panel Admin UI (1 session)
- [ ] Section "Connexions" dans chaque fiche société
- [ ] Liste des connexions avec statut, label, type, users assignés
- [ ] Formulaire création connexion (par type)
- [ ] Modal assignation : checkboxes users + niveaux d'accès
- [ ] Vue 🔧 par user : affiche les connexions assignées
- [ ] Tenant admin : gère les connexions de sa société
- [ ] Super admin : gère toutes les connexions

### Phase C — Intégration Raya Core (1 session)
- [ ] `get_user_connections()` remplace `load_user_tools()` dans `_raya_core()`
- [ ] `get_valid_token(connection_id)` remplace `get_valid_microsoft_token(username)`
- [ ] Adapter `drive_connector`, `outlook_connector`, `gmail_connector` pour prendre un `connection` au lieu d'un `username`
- [ ] Adapter le prompt système pour lister les connexions disponibles
- [ ] Déprécier `user_tools` et `oauth_tokens` (garder en fallback temporaire)

## 6. EXEMPLES CONCRETS POST-MIGRATION

### Couffrant Solar après migration :

| Connexion | Type | Label | Assignée à | Accès |
|---|---|---|---|---|
| #1 | drive | SharePoint Commun | Guillaume, Arlène, Benoit, Pierre, Sabrina | full / write / write / write / write |
| #2 | outlook | guillaume@couffrant.fr | Guillaume | full |
| #3 | outlook | contact@couffrant.fr | Guillaume, Arlène | full, write |
| #4 | odoo | Odoo Guillaume | Guillaume | full |
| #5 | odoo | Odoo Arlène | Arlène | read_only |
| #6 | gmail | gmail perso Guillaume | Guillaume | full |

### Juillet (société neuve) :

| Connexion | Type | Label | Assignée à | Accès |
|---|---|---|---|---|
| (vide) | — | — | — | — |

Charlotte connecte son Outlook → connexion #7 créée → assignée à Charlotte.

## 7. QUESTIONS OUVERTES

1. **OAuth multi-user** : Quand Arlène connecte "son" Outlook, on crée une connexion avec son token. Mais il faut qu'elle fasse le flux OAuth elle-même (pas l'admin). → Le flux OAuth doit être accessible depuis le chat (bouton "Connecter mes outils") ET depuis le panel admin.

2. **Refresh tokens** : Chaque connexion a ses propres tokens. Le scheduler doit rafraîchir les tokens de TOUTES les connexions, pas juste ceux de "guillaume".

3. **Boîtes partagées Microsoft** : Dans l'API MS Graph, accéder à une boîte partagée nécessite les permissions `Mail.Read.Shared`. Le token de l'utilisateur qui a l'accès doit avoir ce scope.

4. **Rétrocompatibilité** : Pendant la transition, `user_tools` et `oauth_tokens` continuent de fonctionner. Les nouvelles connexions utilisent `tenant_connections`.
