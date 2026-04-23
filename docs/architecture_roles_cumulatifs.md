# Architecture — Modèle de rôles cumulatifs

**Créé le 25 avril 2026** — discussion Guillaume sur la clarification
du modèle de permissions dans Raya.

## 🎯 Principe fondamental

Les rôles dans Raya ne sont **pas exclusifs** — ils sont **cumulatifs**.

Chaque utilisateur possède au minimum le rôle `user`. Certains accumulent
en plus `tenant_admin`, et un seul (Guillaume) accumule en plus `super_admin`.

## 📊 Matrice des rôles

| Profil | user | tenant_admin | super_admin |
|---|---|---|---|
| Utilisateur lambda d'une société | ✅ | ❌ | ❌ |
| Patron d'une société utilisant Raya | ✅ | ✅ | ❌ |
| Guillaume (dev Raya + patron Couffrant) | ✅ | ✅ | ✅ |

Chaque rôle débloque des **accès supplémentaires**, sans enlever ce qui
était accessible avec le rôle inférieur.

## 🎨 Impact sur le menu 3 points

Le menu s'affiche selon les rôles accumulés :

```
Utilisateur lambda :
  • Paramètres (du fait de son rôle user)
  • Déconnexion

Admin tenant :
  • Paramètres (rôle user)
  • Ma société (rôle tenant_admin ajouté)
  • Déconnexion

Guillaume (3 rôles cumulés) :
  • Paramètres (rôle user)
  • Ma société (rôle tenant_admin)
  • Super Admin (rôle super_admin)
  • Déconnexion
```

</content>

## 🏛️ Pages séparées accessibles selon les rôles

Chaque accès à une page séparée (hors du chat) est réservé au rôle
correspondant :

- **`/tenant/panel`** : nécessite rôle `tenant_admin`
- **`/admin/panel`** : nécessite rôle `super_admin`
- **`/chat`** : nécessite rôle `user` (tout le monde)

Le jour où les verrouillages (PIN tenant / TOTP super_admin) seront mis
en place (voir `roadmap_verrouillage_panels.md`), la logique devient :

1. L'utilisateur clique sur un lien de sortie (Ma société ou Super Admin)
2. Le système vérifie le rôle (comme aujourd'hui)
3. Si OK → demande la confirmation additionnelle (PIN ou TOTP)
4. Si confirmation OK → ouverture de la page

## 💻 Implications techniques

### Scopes en base
Aujourd'hui le champ `users.scope` stocke UN seul rôle (user / tenant_admin /
admin / super_admin). C'est techniquement un rôle **hiérarchique** plutôt
que cumulatif. La fonction `require_tenant_admin` accepte déjà `tenant_admin`,
`admin` et `super_admin`. Donc le comportement cumulatif est bien implémenté
côté backend.

Le hardcoding super_admin pour Guillaume (via `is_hardcoded_super_admin`)
garantit que sa promotion à super_admin ne dépend pas d'une valeur DB
qui pourrait être modifiée accidentellement.

### Frontend (chat-core.js)
Le JS doit afficher les items du menu selon le scope reçu du backend.
Logique simple :

```javascript
// scope = 'user' | 'tenant_admin' | 'admin' | 'super_admin'
const isTenantAdmin = ['tenant_admin', 'admin', 'super_admin'].includes(scope);
const isSuperAdmin = ['admin', 'super_admin'].includes(scope);

// Afficher les items en conséquence
if (isTenantAdmin) document.getElementById('adminPanelBtn').style.display = '';
if (isSuperAdmin) document.getElementById('superAdminBtn').style.display = '';
```

## 📋 Règle pratique pour coder

Quand on ajoute une nouvelle fonctionnalité, on se pose toujours 3 questions :

1. **Cette fonctionnalité est-elle utile à l'utilisateur simple ?**
   → Si oui : accessible dans les Paramètres utilisateur (chat)

2. **Cette fonctionnalité est-elle de gestion d'équipe/société ?**
   → Si oui : accessible dans `/tenant/panel`

3. **Cette fonctionnalité est-elle technique/dev/facturation ?**
   → Si oui : accessible dans `/admin/panel`

On ne duplique pas les fonctionnalités — chaque truc a UN seul endroit
où il vit, selon son public cible.
</content>
