# 🔐 Roadmap Gestion des Rôles — Raya

**Version** : 1.0
**Date** : 18/04/2026 tard soirée
**Statut** : v1 livrée, v2 planifiée

---

## État actuel (v1 livrée le 18/04/2026)

### Hiérarchie des rôles

```
super_admin  (toi, Guillaume - hardcodé par email)
     │
     ├── Accès complet : admin_panel + tenant_panel (tous tenants)
     ├── Peut créer/modifier/supprimer admins, tenant_admins, users
     ├── Peut modifier son display_name/phone/email MAIS pas son scope
     └── HARDCODÉ : per1.guillaume@gmail.com dans app/hardcoded_permissions.py
     │
admin  (collaborateur Raya - à créer plus tard)
     │
     ├── Accès : admin_panel + tenant_panel
     ├── Peut modifier tenant_admins et users
     ├── NE PEUT PAS modifier un super_admin ni un autre admin
     └── NE PEUT PAS promouvoir en super_admin
     │
tenant_admin  (patron d'un tenant client)
     │
     ├── Accès : tenant_panel de SON tenant uniquement
     ├── Peut modifier les users de SON tenant (sauf lui-même niveau scope)
     ├── Cloisonnement strict : ne voit pas les autres tenants
     └── NE PEUT PAS modifier son propre statut tenant_admin
     │
user  (salarié d'un tenant client)
     │
     └── Utilise Raya selon les permissions de son tenant_admin
```

### Garde-fous implémentés (commit `a72f50d`)

Fonctions `can_modify_user()` et `can_change_scope()` dans `app/hardcoded_permissions.py` :
1. Hardcoded super_admin jamais modifiable par autrui
2. Auto-modification du scope interdite (cause du bug Guillaume x2)
3. Seul un super_admin peut promouvoir en super_admin
4. Tenant_admin cloisonné à son tenant

### UI mise à jour (B5)

- Formulaire `editUser` dans tenant_panel affiche display_name + phone
- Le select scope devient un badge "🛡️ Super admin Raya protégé" en lecture seule si l'utilisateur édité est super_admin ou hardcodé
- `saveUser` envoie display_name et phone (corrigeant 2 bugs d'enregistrement)

---

## Roadmap v2 (future)

### R2.1 — Code d'accès MFA soft sur les menus admin (~4h)

**Besoin** : si un super_admin ou tenant_admin laisse son compte connecté sur un ordinateur, personne d'autre ne doit pouvoir accéder aux menus admin sans un code.

**Solution proposée** :
- Ajout colonne `admin_pin_hash` sur `users` (nullable)
- Au premier accès à `/admin/panel` ou `/tenant/panel`, si le user n'a pas de PIN : on lui demande d'en définir un (4-6 chiffres)
- Chaque visite ultérieure : modal demandant le PIN
- Session séparée : le PIN est valide 30 minutes puis re-demandé
- Possibilité de reset le PIN par un super_admin

**Effort** : ~4h (backend + UI modal + tests)

### R2.2 — Gestion des collaborateurs Raya (~6h)

**Besoin** : pouvoir créer des comptes `admin` (salariés Raya) depuis le super admin panel.

**Solution proposée** :
- Nouvel onglet "👥 Équipe Raya" dans `/admin/panel`
- Formulaire de création d'un admin Raya avec :
  - Email (unique)
  - Display name
  - Téléphone
  - Tenant technique "raya" (à créer la première fois)
- Liste des admins avec possibilité de les désactiver/supprimer
- Un admin Raya appartient au tenant `raya` (pas à un tenant client)

**Effort** : ~6h

### R2.3 — Granularité par famille d'action (lié aux permissions v2)

Voir `docs/raya_permissions_plan.md` section Roadmap v2.

Permet à un tenant_admin de dire : *"Arlène peut lire + envoyer des mails, mais pas supprimer"* etc.

### R2.4 — Séparation stricte super_admin / tenant_admin (optionnel)

**Si besoin de cloisonnement renforcé** : migrer vers la solution B évoquée (2 comptes distincts).
- 1 compte `guillaume@couffrant-solar.fr` / tenant_admin de couffrant
- 1 compte `guillaume.raya@...` / super_admin Raya

**Non nécessaire pour le MVP**. À reconsidérer quand Raya a plusieurs tenants clients et que l'audit log doit être cristallin.

---

## Règles d'or pérennes (v1 et v2)

1. **Un super_admin hardcodé est inamovible** — modifier la liste dans le code + deploy = acte conscient
2. **Un acteur ne modifie jamais son propre scope** — protection contre les auto-retrogradations
3. **Un tenant_admin reste cloisonné à son tenant** — ne voit ni ne touche les autres
4. **Un admin ne peut jamais modifier un super_admin** — ni un autre admin
5. **Seul un super_admin nomme un super_admin** — pas d'admin qui se promeut lui-même

---

## Liste des emails hardcodés actuellement

Fichier source : `app/hardcoded_permissions.py`

```python
HARDCODED_SUPER_ADMINS_BY_EMAIL = [
    "per1.guillaume@gmail.com",
]
```

Pour ajouter un nouveau super_admin immuable :
1. Ajouter son email à la liste
2. Commit + push
3. Redéploiement Railway

Pour retirer un super_admin hardcodé :
1. Retirer son email de la liste
2. Commit + push
3. Redéploiement Railway
4. Optionnellement : `UPDATE users SET scope='user' WHERE email='...'` si on veut aussi le rétrograder en DB
