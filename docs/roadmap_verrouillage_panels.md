# Roadmap — Verrouillage des panels admin et super admin

**Créé le 25 avril 2026** — demande Guillaume lors de la discussion sur
l'architecture multi-rôles et la sécurité.

## 🎯 Objectif

Ajouter une **confirmation supplémentaire** à chaque sortie du chat vers
une page admin (qu'elle soit tenant ou super admin), pour éviter qu'un
utilisateur connecté laissé sans surveillance voie ses données sensibles
exposées.

## 🎨 Architecture visuelle (rappel de la vision Guillaume)

**Tous les utilisateurs voient la même interface de chat**, avec les mêmes
paramètres personnels (consommation, préférences, etc.).

Ce qui change selon le rôle, ce sont les **liens de sortie** vers d'autres
pages :

```
┌─────────────────────────────────────────────────────┐
│  CHAT RAYA (commun à tous)                          │
│  + Menu paramètres personnels                       │
│                                                     │
│  Selon le rôle, le menu contient en plus :          │
│                                                     │
│  - Utilisateur normal : rien de plus                │
│  - Admin tenant : lien "Panel admin société"        │
│  - Super admin : lien "Panel admin société" +       │
│                  lien "Panel super admin dev"       │
└─────────────────────────────────────────────────────┘
         │                              │
         │ clic lien (avec PIN)         │ clic lien (TOTP)
         ▼                              ▼
┌──────────────────┐            ┌──────────────────┐
│ PANEL ADMIN      │            │ PANEL SUPER      │
│ TENANT           │            │ ADMIN DEV        │
│ (page séparée,   │            │ (page séparée,   │
│  design noir)    │            │  design noir)    │
└──────────────────┘            └──────────────────┘
```

**Note importante** : pour Guillaume personnellement, il a les 3 niveaux
superposés — il voit donc les 2 liens en plus dans son menu paramètres.

</content>

## 🔐 Niveaux de verrouillage à implémenter

### Panel admin tenant (clic depuis le menu paramètres chat)
- **Confirmation** : code PIN à 4-6 chiffres
- Code configurable par chaque tenant_admin
- Demandé à chaque ouverture du panel (ou à chaque X minutes d'inactivité)
- Timeout session admin : 30 min d'inactivité → re-PIN

### Panel super admin (clic depuis le menu paramètres chat, Guillaume uniquement)
- **Confirmation** : TOTP (Google Authenticator) + mot de passe
- Demandé à chaque ouverture du panel
- Timeout session super_admin : 15 min d'inactivité → re-auth complète
- Log d'audit de chaque accès (IP, timestamp, actions effectuées)

## 🛠️ Technique envisagée

### Pour le PIN admin tenant
- Colonne `admin_pin_hash` sur la table `users` (bcrypt)
- Endpoint `POST /tenant/admin/unlock` qui vérifie le PIN et pose un flag session
- Middleware sur toutes les routes `/tenant/admin/*`
- Auto-expiration du flag après 30 min d'inactivité

### Pour le TOTP super admin
- Colonne `totp_secret` sur `users` (uniquement pour Guillaume)
- QR code à scanner avec Google Authenticator à la première config
- Endpoint `POST /admin/super/unlock` qui vérifie le code à 6 chiffres
- Flag session `super_admin_unlocked_until` (15 min)
- Middleware sur `/admin/super/*`
- Table `super_admin_audit_log` : timestamp, ip, action, details

## 📅 Quand faire ce chantier ?

**Phase actuelle (expérimentale)** : pas urgent — Guillaume est seul
utilisateur actif et contrôle ses appareils.

**Avant passage en prod avec des utilisateurs tiers** : OBLIGATOIRE.

**Déclencheurs** :
- Premier utilisateur externe connecté (hors phase test)
- Premier tenant tiers créé (hors Couffrant Solar + juillet de test)
- Mise en production publique

## 🔐 Notes complémentaires

- Prévoir un mécanisme de **récupération** pour le super_admin en cas de
  perte du téléphone TOTP (backup codes ou reset email avec délai 24h)
- Pour les tenant_admin, prévoir `/tenant/admin/reset-pin` qui nécessite
  le mot de passe du compte
- Les PIN doivent être hashés en DB (bcrypt), jamais en clair
- Le TOTP secret du super_admin doit être chiffré en DB (clé dérivée du
  mot de passe + sel)
</content>
