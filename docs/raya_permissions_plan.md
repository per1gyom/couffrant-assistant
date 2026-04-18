# 🔐 Permissions tenant Read/Write/Delete — Plan stratégique

**Version** : 1.0
**Date** : 18/04/2026 soirée
**Statut** : Plan validé par Guillaume, prêt à implémenter
**Estimé** : ~5h de dev

---

## 1. Vision globale (v1 à coder + v2 future)

### Principe de hiérarchie (non négociable, v1 et v2)

```
SUPER ADMIN (Guillaume)
  → Plafond par CONNEXION de chaque tenant
  → Granularité : outil entier (Odoo, Gmail, SharePoint...)
  → Niveaux : read / read_write / read_write_delete
  → JAMAIS de famille d'action, même en v2 (trop lourd à gérer)
         │ plafond imposé
         ▼
TENANT ADMIN (patron du tenant)
  → Distribue les permissions à ses users
  → Ne peut JAMAIS dépasser le plafond du super admin
  → v1 : par connexion + par user
  → v2 : + par famille d'action (évolution future)
         │ permission finale
         ▼
USER (utilisateur Raya)
  → v1 : subit les permissions données
  → v2 : peut SE RESTREINDRE sous son plafond (évolution future)
  → Ne peut JAMAIS s'accorder plus que son plafond admin
```

**Règle d'or** : chaque niveau plafonne le niveau inférieur. Jamais de dépassement possible.

---

## 2. Version 1 — à coder maintenant

### 2.1 Granularité

| Acteur | Granularité v1 |
|---|---|
| Super admin | Par connexion entière (1 niveau pour tout Odoo) |
| Tenant admin | Par connexion + par user |
| User | Subit les permissions données |

### 2.2 Niveaux de permission (3)

| Code | Label | Droits |
|---|---|---|
| `read` | Lecture seule | Chercher, lister, consulter |
| `read_write` | Lecture + modification | read + créer/modifier/assigner |
| `read_write_delete` | Contrôle total | read_write + supprimer |

Hiérarchique : `read_write_delete` contient `read_write` contient `read`.

### 2.3 Valeur par défaut

Toute nouvelle connexion créée part en `read`. Principe de moindre privilège.

### 2.4 Comportement quand Raya tente une action bloquée

Refus explicite + explication : *"Je ne peux pas créer ce devis, ta connexion Odoo est en lecture seule. Demande à Guillaume ou à ton admin de tenant de modifier la permission si tu en as besoin."*

Raya sait dans son prompt système quelles permissions elle a, donc elle n'essaie même pas d'exécuter une action interdite — elle explique direct à l'utilisateur.

### 2.5 Bouton "🔒 Tout en lecture seule" (spec Guillaume)

**Dans le panel super admin** : bouton qui bascule toutes les connexions de TOUS les tenants en `read`. Toggle : cliquer à nouveau = rétablir les permissions précédentes (sauvegardées). Utile pour figer la plateforme avant un déploiement risqué, limiter tous les tenants en période de test intensif.

**Dans le panel tenant admin** : bouton qui bascule toutes les connexions du SIEN tenant en `read`. Toggle : rétablir les permissions précédentes. Utile pour démarrer un nouveau tenant en mode sécurité par défaut, test temporaire, mode "tranquille" pendant les vacances.

Comportement technique :
- Sauvegarde des permissions actuelles dans un champ `previous_permission_level`
- Mise à `read` de toutes les connexions concernées
- Re-clic → restauration depuis `previous_permission_level`
- Toast de confirmation : "27 connexions basculées en lecture seule"

### 2.6 Audit log (obligatoire)

Nouvelle table `permission_audit_log` qui enregistre :
- Qui a tenté (`username`, `tenant_id`)
- Quelle action (`tag`, ex: `ODOO_CREATE`)
- Quelle connexion (`connection_id`)
- Permission au moment de la tentative
- Permission requise
- Résultat (`allowed` / `denied`)
- Timestamp

---

## 3. Version 2 — roadmap future

À implémenter quand la v1 est stabilisée et que les retours des early adopters font émerger des besoins de granularité plus fine.

### 3.1 Tenant admin — granularité par famille d'action

Le tenant admin pourra dire :
- *"Arlène peut lire + envoyer des mails, mais pas supprimer"*
- *"Pierre peut chercher des contacts Odoo mais pas créer de devis"*
- *"Tout le monde peut lire les documents SharePoint, seul Guillaume peut en créer"*

Familles d'action envisagées : SEARCH (lecture), CREATE, UPDATE, DELETE, SEND (spécifique emails/Teams).

### 3.2 User — peut se restreindre sous son plafond

L'utilisateur pourra choisir, dans son profil, d'avoir moins de droits que ce que son admin lui a accordés.

Exemple : admin donne `read_write` sur Gmail à Guillaume. Guillaume, par prudence au début, décide de rester en `read` sur Gmail pendant ses premières semaines d'utilisation. Il peut remonter à `read_write` quand il se sent prêt, sans avoir à demander à son admin.

### 3.3 Super admin — inchangé

Le super admin continue de gérer uniquement la connexion entière, même en v2. Sinon ça devient ingérable avec beaucoup de tenants.

Responsabilité du super admin : *"ce tenant a droit à cette connexion, avec tel niveau max"*. Le détail fin est délégué au tenant admin.

---

## 4. Politique de sécurité temporaire (18/04/2026)

Pendant le développement et la stabilisation :
- Toutes les connexions en `read` par défaut
- Seule exception consciente : le compte de Guillaume en `read_write` pour tester les envois de mail, créations de devis, etc.
- Dès que les tests deviennent plus nombreux ou qu'on ouvre aux premiers testeurs → passer tous les comptes en `read` (y compris Guillaume)
- Revenir en `read_write` progressivement, par action validée

Objectif : éviter tout dégât sur les données réelles pendant les phases instables.

---

## 5. Schéma DB

### 5.1 Modifications sur `tenant_connections`

```sql
ALTER TABLE tenant_connections
  ADD COLUMN super_admin_permission_level TEXT DEFAULT 'read',
  ADD COLUMN tenant_admin_permission_level TEXT DEFAULT 'read',
  ADD COLUMN previous_permission_level TEXT DEFAULT NULL;
```

- `super_admin_permission_level` : le plafond fixé par le super admin
- `tenant_admin_permission_level` : la permission réelle appliquée (≤ plafond)
- `previous_permission_level` : utilisé par le bouton "tout en lecture seule" pour restaurer l'état précédent au toggle

Contrainte métier vérifiée par middleware : `tenant_admin_permission_level <= super_admin_permission_level`.

### 5.2 Nouvelle table `permission_audit_log`

```sql
CREATE TABLE permission_audit_log (
    id SERIAL PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    username TEXT NOT NULL,
    connection_id INTEGER,
    action_tag TEXT NOT NULL,
    current_permission_level TEXT NOT NULL,
    required_permission_level TEXT NOT NULL,
    allowed BOOLEAN NOT NULL,
    user_input_excerpt TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);
```

---

## 6. Mapping tag ACTION → niveau requis

### 6.1 Actions niveau `read`

- `ODOO_SEARCH`, `ODOO_SEMANTIC`, `ODOO_CLIENT_360`, `ODOO_INTROSPECT`
- `READ_MAIL`, `SEARCHMAIL`, `LIST_MAILS`
- `SEARCHDRIVE`, `READ_DOCUMENT`, `LIST_FOLDERS`
- `LIST_EVENTS`, `SEARCH_CALENDAR`, `READ_EVENT`

### 6.2 Actions niveau `read_write`

Tout `read` + :
- `SEND_MAIL`, `REPLY_MAIL`, `FORWARD_MAIL`
- `ODOO_CREATE`, `ODOO_UPDATE`
- `CREATEEVENT`, `UPDATE_EVENT`
- `CREATEFOLDER`, `UPLOAD_DOCUMENT`, `UPDATE_DOCUMENT`

### 6.3 Actions niveau `read_write_delete`

Tout `read_write` + :
- `ODOO_DELETE`
- `DELETE_EVENT`, `DELETE_MAIL`, `DELETE_DOCUMENT`

### 6.4 Implémentation

Un dictionnaire dans un nouveau fichier `app/permissions.py` :

```python
ACTION_PERMISSION_MAP = {
    'ODOO_SEARCH': 'read',
    'ODOO_CREATE': 'read_write',
    'ODOO_DELETE': 'read_write_delete',
    # ...etc
}

def get_required_permission(action_tag: str) -> str:
    return ACTION_PERMISSION_MAP.get(action_tag, 'read_write_delete')
```

---

## 7. Plan d'implémentation (7 étapes)

### Étape 1 — Migration DB (~20 min)

- Ajouter les 3 colonnes à `tenant_connections`
- Créer la table `permission_audit_log`
- Script de migration idempotent dans `app/database_migrations.py`

### Étape 2 — Module permissions (~1h)

- Nouveau fichier `app/permissions.py`
- Constante `ACTION_PERMISSION_MAP` (mapping complet)
- Fonction `get_required_permission(action_tag)`
- Fonction `check_permission(tenant_id, connection_id, action_tag, username)` qui vérifie contre `tenant_admin_permission_level` et log dans audit
- Fonction helper `can_action(...)` → retourne `True/False` + raison du refus

### Étape 3 — Middleware d'interception (~1h)

- Dans `app/direct_actions.py` (ou équivalent), avant chaque exécution d'action : appel à `check_permission()`
- Si refus : retourne un message d'erreur explicite au lieu d'exécuter
- Raya voit le refus et formule une réponse à l'utilisateur

### Étape 4 — UI tenant_panel (~1h)

- Section "Permissions" sur chaque connexion
- 3 radio buttons : `read` / `read_write` / `read_write_delete`
- Le radio inaccessible (au-dessus du plafond super admin) est grisé
- Bouton "🔒 Tout en lecture seule" en haut de la section Connexions
- Toast de confirmation après action

### Étape 5 — UI admin_panel (~45 min)

- Vue "Plafonds par tenant" : tableau des tenants × connexions × niveau
- Radio buttons pour modifier le plafond super admin
- Bouton "🔒 Tout en lecture seule" global (pour tous les tenants)

### Étape 6 — Injection dans le prompt système de Raya (~30 min)

Bloc dans `app/routes/aria_context.py::build_system_prompt()` :

```
=== PERMISSIONS SUR TES CONNEXIONS ===
- Odoo : LECTURE SEULE
  Tu peux chercher, lister, consulter.
  Tu ne peux PAS créer, modifier, supprimer.
- Gmail : LECTURE + ÉCRITURE
  Tu peux consulter et envoyer des mails.
  Tu ne peux PAS supprimer de mail.
```

Raya sait donc en permanence ce qu'elle a le droit de faire et peut l'expliquer à l'utilisateur sans même tenter.

### Étape 7 — Tests + docs + commit (~30 min)

- Test manuel : switcher les permissions et vérifier que Raya réagit correctement
- Test du bouton "Tout en lecture seule" (switch + restore)
- Vérifier l'audit log
- Commit + push
- Mise à jour du changelog session 18/04

**Total estimé** : ~5h

---

## 8. Règles de migration v1 → v2

Prérequis pour passer à la v2 :
- V1 stable depuis au moins 2-3 semaines
- Au moins 3 tenants actifs avec leurs users
- Retours des early adopters indiquant un besoin de granularité fine
- Bugs de permissions nuls ou minimes

Migration technique :
- Ajouter colonne `user_permission_overrides JSONB` sur `users`
- Ajouter colonne `tenant_admin_action_family_overrides JSONB` sur `tenant_connections`
- L'UI tenant_panel gagne une section "Permissions fines"
- L'UI profil user gagne une section "Mes restrictions volontaires"
- Le prompt système de Raya inclut les détails fins

---

## 9. Ce qui NE change PAS entre v1 et v2

- Le principe de hiérarchie (super admin → tenant admin → user)
- La granularité du super admin (par connexion uniquement, jamais par famille)
- Les 3 niveaux fondamentaux (`read` / `read_write` / `read_write_delete`)
- Le bouton "Tout en lecture seule" dans les 2 panels
- L'audit log

Tout ce qui est codé en v1 est pérenne. La v2 ajoute, ne remplace pas.

---

## 10. Cohérence avec les autres chantiers

### Bug Tracking System

Les actions refusées peuvent déclencher un bug si le refus semble être une erreur de config. Lien : `permission_audit_log.allowed = FALSE` + fréquence anormale → alerte à Guillaume.

### Sécurité Phase A (Clerk)

Les permissions fonctionnent au-dessus de l'auth Clerk (qui décide QUI accède). Les permissions décident QUOI chaque user peut faire une fois authentifié.

### Scanner Universel

Le scan ne fait que de la lecture Odoo → compatible avec permission `read`. Les webhooks Odoo en Phase 5 nécessiteront `read_write` minimum pour pouvoir réagir aux changements (lookup initial via API Odoo lit donc `read` suffit).

### Argument commercial

Deviendra un argument marketing : *"Avec Raya, vous contrôlez exactement ce que l'IA peut toucher. Pas de surprise, pas de dégât possible."* À mettre en avant dans la landing page SAS Logiciel.
