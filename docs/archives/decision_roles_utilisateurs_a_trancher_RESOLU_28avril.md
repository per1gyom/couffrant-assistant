# ⚠️ DOCUMENT ARCHIVÉ — RÉSOLU LE 28 AVRIL 2026

> Ce document est conservé pour traçabilité historique uniquement.
> Le sujet a été tranché lors de la session du 28 avril 2026 matin.

## 📌 Décision finale prise (28/04 matin)

**Modèle retenu** : `Hybride` (proche du modèle 🅲 ci-dessous, mais nuancé) :

- **`super_admin`** (Guillaume, hardcoded par email) : pouvoir total. Inamovible.
- **`admin`** (collaborateur Raya, futur) : cross-tenant volontairement. Te suppléer sur la gestion. Ne peut PAS modifier le statut super_admin.
- **`tenant_admin`** (patron tenant) : limité à son tenant. Autonome sur la gestion quotidienne (reset password, suspension, outils).
- **`tenant_user`** (anciennement `user`, renommé pour clarifier l'attachement à un tenant) : utilisateur normal.

## 📌 Implémentation déployée le 28/04 matin

8 commits, audit isolation finalisé. Voir `docs/etat_complet_chantiers_27avril_nuit.md` pour le détail des LOTs 2-6 :

- LOT 2 : bug logique `scope != "admin"` corrigé partout
- LOT 3 : isolation SQL profile/synthesis/report/memory_teams/connection_token_manager
- LOT 4 : ATTENTION super_admin endpoints + outlook anti-pattern
- LOT 5 : nettoyage magic strings dans hardcoded_permissions.py
- LOT 6 : renommage `user` → `tenant_user`, suppression `SCOPE_CS` legacy

## 📌 État DB final (28/04 13h35)

```
super_admin  : 1 (guillaume, couffrant_solar)
tenant_admin : 1 (Charlotte, juillet)
tenant_user  : 4 (Arlène, benoit, Pierre, Sabrina, couffrant_solar)
```

---

# Document original (pour historique)

# 🎭 Définition des rôles utilisateurs — À TRANCHER

**Statut** : EN ATTENTE DE DÉCISION **Créé le** : 25 avril 2026 fin de soirée **Origine** : Discussion fin de session marathon, après audit isolation 7 phases. Guillaume trop fatigué pour trancher correctement → on documente pour reprendre à tête reposée.

> **Ce document est la source de vérité pour la prochaine session sur les rôles**.Avant de coder quoi que ce soit qui touche aux permissions admin/tenant_admin/user, relire ce document.

---

## 🎯 Le problème à résoudre

Aujourd'hui, **les permissions de création/modification d'utilisateurs sont trop laxistes** :

- Un `tenant_admin` peut créer/supprimer des users dans son tenant (via `POST /tenant/create-user`)
- Un `admin` peut créer des users **dans n'importe quel tenant**(via `POST /admin/create-user`)
- Un `tenant_admin` peut **supprimer N'IMPORTE QUEL tenant** (via `DELETE /admin/tenants/{id}`) — bug critique identifié en Phase 4 de l'audit
- Un `tenant_admin` peut **promouvoir un user en** `super_admin` (via `PUT /admin/update-user/{target}`) — bug critique identifié en Phase 5

Guillaume veut **reprendre le contrôle** sur qui peut faire quoi, mais sans décider à la va-vite. La décision aura des conséquences sur :

1. La sécurité du système
2. Le confort opérationnel quotidien (Charlotte qui doit déranger Guillaume pour chaque action ou pas)
3. Le passage à l'échelle (et si demain il y a 10 tenants ?)

---

## 👥 Les 4 rôles dans Raya aujourd'hui

RôleC'est qui ?Aujourd'hui en DB`super_admin`Guillaume uniquement. Le fondateur. Hardcoded, inviolable.1 (guillaume)`admin`Collaborateur Raya côté Anthropic/équipe. **Pas utilisé aujourd'hui**, prévu pour le futur.0`tenant_admin`Le patron de chaque société cliente.1 (Charlotte, tenant juillet)`user`Utilisateur normal.4 (Pierre, Sabrina, Benoît, Arlène)

Note importante : le rôle `admin` est **différent** de `tenant_admin`. Le `admin`c'est un futur collaborateur Raya côté Anthropic qui aurait des droits d'aide au support multi-tenants. Aujourd'hui personne n'a ce rôle.

---

## 🤔 Les 3 modèles possibles

### 🅰️ Modèle "Apple-like"

**Guillaume contrôle tout.** Chaque opération sensible passe par lui.

- ✅ Sécurité maximale
- ✅ Guillaume voit tout ce qui se passe
- ❌ Goulot d'étranglement (Charlotte doit demander pour tout)
- ❌ Pas scalable au-delà de 5 tenants

### 🅱️ Modèle "SaaS classique"

**Le patron de chaque société est autonome dans la gestion de SES utilisateurs.**

- ✅ Chaque tenant_admin gère son équipe sans déranger
- ✅ Scalable
- ❌ Si Charlotte fait n'importe quoi (crée 50 users d'un coup → vide le quota de tokens Anthropic), c'est la facture de Guillaume qui prend
- ❌ Guillaume ne maîtrise plus qui rentre dans le système

### 🅲 Modèle "Hybride"

**Distinction entre opérations stratégiques (super-admin) et gestion quotidienne (tenant_admin).**

- **Création/suppression d'user** = stratégique → super_admin
- **Reset password / suspendre / désuspendre / activer outils** = quotidien → tenant_admin OK
- ✅ Guillaume maîtrise l'onboarding (qui rentre = qui consomme tokens)
- ✅ Charlotte gère les oublis de mot de passe sans déranger
- ⚖️ Le bon compromis pour MVP

---

## 📊 Tableau complet — Qui peut faire quoi ?

Pour chaque action possible sur les utilisateurs/tenants, voilà la matrice des 3 modèles. **À utiliser comme support de discussion la prochaine fois.**

Action🅰️ Apple🅱️ SaaS🅲 Hybride**Gestion utilisateurs (création/suppression**)Créer un utilisateursuper_admintenant_adminsuper_adminSupprimer un utilisateursuper_admintenant_adminsuper_adminChanger le rôle (scope) d'un usersuper_adminsuper_adminsuper_admin**Gestion utilisateurs (quotidien**)Reset mot de passesuper_admintenant_admintenant_adminSuspendre temporairementsuper_admintenant_admintenant_adminDésuspendresuper_admintenant_admintenant_adminActiver/désactiver outils (Gmail, Outlook…)super_admintenant_admintenant_adminChanger email/téléphonesuper_admintenant_admintenant_admin**Gestion tenant**Créer un tenantsuper_adminsuper_adminsuper_adminSupprimer un tenantsuper_adminsuper_adminsuper_adminConnecter Drive/SharePoint au tenantsuper_admintenant_admintenant_admin**Données privées (lecture**)Voir les règles d'un usersuper_adminsuper_adminsuper_adminVoir l'historique conversationnel d'un usersuper_adminsuper_adminsuper_adminVoir les insights mémoire d'un usersuper_adminsuper_adminsuper_admin

---

## 🎬 3 scénarios concrets pour aider à choisir

### Scénario 1 — Embauche dans une société cliente

Charlotte (tenant juillet) embauche Marc. Elle veut que Marc utilise Raya.

- 🅰️ / 🅲 : Charlotte écrit à Guillaume "Ajoute Marc dans mon tenant stp" → Guillaume crée le user → délai : selon la réactivité de Guillaume.
- 🅱️ : Charlotte crée Marc elle-même → délai : immédiat.

### Scénario 2 — Marc oublie son mot de passe

Marc oublie son mot de passe.

- 🅰️ : Marc → Charlotte → Guillaume → reset link → Marc. Délai : heures.
- 🅲 / 🅱️ : Marc → Charlotte → reset link → Marc. Délai : minutes.

### Scénario 3 — Marc part en vacances

Marc part 3 semaines. Charlotte veut suspendre son compte (économie tokens).

- 🅰️ : Charlotte → Guillaume. Délai : heures.
- 🅲 / 🅱️ : Charlotte suspend elle-même. Délai : minutes.

---

## 💡 Ma recommandation (Claude)

**Modèle 🅲 Hybride.** Voici pourquoi :

- **Modèle 🅰️** est trop rigide → Guillaume va le regretter dès 5 tenants. Et
  surtout, Charlotte va vivre dans la frustration de toujours devoir demander.
- **Modèle 🅱️** est trop laxiste → Guillaume perd le contrôle de l'onboarding,
  ce qui est un risque financier (tokens) ET stratégique (qui utilise Raya).
- **Modèle 🅲** garde l'onboarding sous contrôle de Guillaume tout en
  permettant aux tenant_admins d'être autonomes pour les opérations
  quotidiennes (reset password, suspension, etc.).

Mais c'est **la décision de Guillaume, pas la mienne**. Il doit être à l'aise
avec son choix.

---

## ❓ 5 questions à trancher la prochaine fois

Quand on reprend, voilà les questions exactes à se poser dans l'ordre :

### Q1 — Création d'utilisateur
Qui peut créer un nouvel utilisateur ?
- 🅰️ Super-admin only (Guillaume)
- 🅱️ Tenant-admin OK (Charlotte peut créer dans juillet)

### Q2 — Suppression d'utilisateur
Qui peut supprimer un utilisateur ?
- 🅰️ Super-admin only
- 🅱️ Tenant-admin OK

### Q3 — Reset mot de passe
Qui peut générer un reset link ?
- 🅰️ Super-admin only
- 🅱️ Tenant-admin OK (a priori OK même dans modèle Apple, c'est juste un mot
  de passe)

### Q4 — Suspension d'utilisateur (pause temporaire)
Qui peut suspendre/désuspendre ?
- 🅰️ Super-admin only
- 🅱️ Tenant-admin OK

### Q5 — Connexion d'outils tiers (Drive, SharePoint, Gmail tenant…)
Qui peut connecter un Drive partagé au niveau tenant ?
- 🅰️ Super-admin only (Guillaume garde la main sur les data sensibles)
- 🅱️ Tenant-admin OK (la société cliente connecte ses propres outils)

---

## 🔗 Implications techniques de la décision

Selon la réponse aux 5 questions, on devra modifier :

### Si Q1 = super_admin only
- `POST /admin/create-user` (super_admin_users.py:55) → passer de
  `require_admin` à `require_super_admin`
- `POST /tenant/create-user` (tenant_admin.py) → soit supprimer, soit passer
  en `require_super_admin`
- Retirer le bouton "Créer utilisateur" du panel admin tenant
  (`tenant_panel.html`)

### Si Q2 = super_admin only
- `DELETE /admin/delete-user/{target}` (super_admin_users.py) → vérifier la
  protection (à priori déjà super_admin, à confirmer)
- `DELETE /tenant/delete-user/{target}` (tenant_admin.py) → soit supprimer,
  soit passer en `require_super_admin`
- Retirer le bouton "Supprimer utilisateur" du panel admin tenant

### Si Q3, Q4, Q5 = tenant_admin OK
- Pas de changement (déjà l'état actuel)
- Mais il faut **vérifier** que ces endpoints ont bien `require_tenant_admin`
  + `assert_same_tenant` (cf. audit Phase 5)

### Quoi qu'il arrive, à corriger absolument
Ces 4 trous critiques de la Phase 4-5 doivent être corrigés **indépendamment**
du modèle choisi :

1. **`POST /admin/tenants`** : passer de `require_admin` à `require_super_admin`
   (un tenant_admin n'a aucune raison de créer un tenant)
2. **`DELETE /admin/tenants/{id}`** : pareil → `require_super_admin`
3. **`PUT /admin/update-user/{target}`** : ajouter validation du scope (un
   tenant_admin ne peut pas promouvoir en super_admin, ni au-dessus de
   son propre rôle)
4. **`POST /admin/create-user`** : retirer le fallback silencieux
   `tenant_id=DEFAULT_TENANT` (forcer le tenant_id explicite, refuser
   sinon)

---

## 🎯 Plan d'action proposé pour la prochaine session

1. **Étape 1** (5 min) : Guillaume relit ce document à tête reposée
2. **Étape 2** (10 min) : Guillaume répond aux 5 questions Q1-Q5
3. **Étape 3** (60-90 min) : Claude code les modifications nécessaires
   (endpoints, UI, tests)
4. **Étape 4** (30 min) : Test bout en bout avec Charlotte (tenant juillet)
   pour vérifier que tout marche bien dans son rôle de tenant_admin

---

## 📝 Ce que cette session a aussi révélé

L'audit isolation a aussi identifié plusieurs trous **non liés aux rôles** qui
devront être corrigés en parallèle (cf. `audit_isolation_25avril_complementaire.md`) :

- 🔴 **8 trous CRITIQUES** : token_manager.py (6 fonctions sans tenant_id),
  DEFAULT_TENANT silencieux, schema users.tenant_id NULLABLE, etc.
- 🟠 **15 trous IMPORTANT** : profile.py, memory_teams.py, synthesis_engine.py,
  endpoints admin acceptant tenant_id du payload, etc.
- 🟡 **10 trous ATTENTION** : bug logique scope != "admin", anti-patterns
  default 'guillaume', magic strings.

**Ordre d'attaque recommandé** :
1. **D'abord** trancher le modèle de rôles (cette discussion)
2. **Ensuite** appliquer les corrections en suivant le modèle choisi
3. **Enfin** corriger les trous critiques annexes (tokens, schema DB, etc.)

---

## 🌙 Note de fin de session

Guillaume a fait une session marathon de 8h+ aujourd'hui (chantier signatures
v2 complet + audit isolation 7 phases). Cette décision est trop importante
pour être prise dans la fatigue.

**Tout est documenté ici, rien ne sera perdu.** À reprendre demain ou au
prochain créneau de cerveau frais.

Bonne nuit Guillaume 💙
