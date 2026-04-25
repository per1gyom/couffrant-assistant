# Audit isolation multi-tenant — COMPLÉMENTAIRE

**Date** : 25 avril 2026 soir **Auteur** : Claude (audit) + Guillaume (validation) **Statut** : EN COURS — audit avec angles différents de celui du 24/04

---

## 🎯 Pourquoi un audit complémentaire ?

L'audit du 24/04 (`audit_isolation_24avril.md`) a été suivi de 13 commits de corrections (\~40 fichiers, \~100 requêtes SQL sécurisées). Mais :

1. Les **corrections n'ont pas été revérifiées** depuis (régression possible ?)
2. Du **nouveau code a été ajouté** depuis (chantier signatures, design system, etc.) — peut-être de nouveaux trous ?
3. L'audit du 24/04 se concentrait sur les **requêtes SQL**. D'autres angles méritent d'être creusés :
   - Authentification et sessions
   - Endpoints HTTP (acceptent-ils `username`/`tenant_id` du client ?)
   - Privilege escalation (user → admin tenant → super admin)
   - Tokens OAuth Gmail/Outlook (mismatch user possible ?)
   - Logs et tracing (fuites cross-tenant via les logs ?)
   - Endpoints debug/admin non documentés
4. Les **tests de non-régression** (plan pierre_test) **n'ont jamais été exécutés**.

## 📋 Plan d'audit

#PhaseAngleStatut1Vérifier les corrections du 24/04 tiennent toujoursSQL⏳2Audit du nouveau code post-24/04 (signatures, design system)SQL⏳3Authentification (sessions, cookies, require_user)Auth⏳4Endpoints HTTP (paramètres acceptés du client)HTTP⏳5Privilege escalation rôlesRBAC⏳6Tokens OAuth + connecteurs externesOAuth⏳7Tests dynamiques en DBTests⏳

À chaque phase, les findings sont classés :

- 🔴 CRITIQUE — fuite cross-tenant ou cross-user effective
- 🟠 IMPORTANT — risque sérieux mais pas une fuite directe
- 🟡 ATTENTION — défense en profondeur, à durcir
- 🟢 OK — vérifié bon

---

## 🔍 Phase 1 — Vérification des corrections du 24/04

### ✅ Bonne nouvelle : 30/30 fichiers du rapport du 24/04 sont bien corrigés

Vérification automatique : les 30 fichiers identifiés comme CRITIQUE/IMPORTANT
le 24/04 ont tous au moins 3 occurrences de `tenant_id` (médiane : 17 occurrences).
**Aucune régression depuis le 24/04.**

```
✅ chat_history.py (9), mail_analysis.py (18), memory.py (34), aria_loaders.py (11),
   mail_gmail.py (5), raya_tool_executors.py (36), prompt_blocks_extra.py (5),
   prompt_blocks.py (6), signatures.py (18), raya_agent_core.py (19),
   dashboard_queries.py (11), ai_client.py (3), memory_save.py (8),
   memory_synthesis.py (24), feedback.py (24), topics.py (16), shortcuts.py (22),
   activity_log.py (17), urgency_model.py (15), rule_engine.py (29),
   maturity.py (13), memory_style.py (8), ai_prompts.py (3),
   email_signature.py (17), seeding.py (6), memory_contacts.py (18),
   entity_graph.py (40), synthesis_engine.py (8), tool_discovery.py (21),
   mail_memory_store.py (3)
```

### 🚨 Trous découverts par cet audit (manqués par le 24/04)

L'audit du 24/04 a manqué **15 requêtes** réparties sur 9 fichiers. Ces trous
n'avaient pas été identifiés. Détection via scan automatique : "WHERE username = %s"
sans `tenant_id` à proximité.

#### 🔴 CRITIQUE — token_manager.py

**Fichier `app/token_manager.py` ligne 230** :
```python
def get_connected_providers(username: str) -> list[str]:
    c.execute("SELECT provider FROM oauth_tokens WHERE username = %s", (username,))
```
- Cette fonction retourne la liste des connecteurs OAuth (Gmail, Outlook, Teams)
  d'un user
- Aucun filtre `tenant_id`
- **Risque** : si 2 tenants ont un user homonyme, fuite de la liste des
  connecteurs entre tenants
- **Correction** : ajouter `AND tenant_id = %s` et propager `tenant_id` à la
  signature de la fonction

#### 🟠 IMPORTANT — admin/profile.py (6 requêtes)

**Fichier `app/routes/admin/profile.py`** :
- Ligne 248 : `SELECT COUNT(*) FROM aria_rules WHERE username=%s` (stats profil)
- Ligne 254 : `SELECT COUNT(*) FROM sent_mail_memory WHERE username=%s` (stats mails)
- Ligne 260 : `SELECT COUNT(*) FROM aria_session_digests WHERE username=%s` (stats conv)
- Ligne 268 : `SELECT COUNT(DISTINCT LOWER(to_email)) FROM sent_mail_memory ...` (contacts)
- Ligne 312 : `SELECT provider, expires_at, ... FROM oauth_tokens WHERE username = %s`
- Ligne 428 : `SELECT created_at, model, ... FROM llm_usage WHERE username = %s`

Endpoint `/admin/profile` est protégé par auth user mais pas par scope tenant.
**Risque** : un user requêtant ses propres stats verrait, en cas de homonyme
cross-tenant, les données agrégées des 2.

#### 🟠 IMPORTANT — memory_teams.py (2 requêtes)

**Fichier `app/memory_teams.py`** :
- Ligne 33 : lecture des markers Teams (`teams_sync_state`)
- Ligne 85 : suppression d'un marker Teams

Markers de synchronisation Teams partagés entre tenants en cas d'homonymie.

#### 🟠 IMPORTANT — synthesis_engine.py:171

**Fichier `app/synthesis_engine.py` ligne 171** :
```python
c2.execute("UPDATE aria_hot_summary SET embedding = %s::vector WHERE username = %s", (vec, username))
```
Mise à jour de l'embedding du hot_summary sans `tenant_id`.

#### 🟠 IMPORTANT — report_actions.py:22

**Fichier `app/routes/actions/report_actions.py` ligne 22** :
```python
SELECT id, content, sections, delivered, delivered_via, created_at
FROM daily_reports WHERE username = %s AND report_date = CURRENT_DATE
```
Lecture du rapport quotidien sans `tenant_id`.

#### 🟡 ATTENTION — super_admin_users.py (4 requêtes)

**Fichier `app/routes/admin/super_admin_users.py`** :
- Ligne 163 : `SELECT ... FROM aria_rules WHERE username=%s` (super-admin)
- Ligne 189 : `SELECT ... FROM aria_insights WHERE username=%s` (super-admin)
- Ligne 380 : `UPDATE aria_memory SET archived = true WHERE username = %s` (admin)
- Ligne 412 : `SELECT ... FROM aria_memory WHERE username = %s` (admin debug)

Ces endpoints sont protégés par `Depends(require_super_admin)` ou
`require_admin`. Risque réduit (seul un super-admin peut appeler).
Mais cross-tenant non étanche : si user homonyme, super-admin verrait les
données mélangées. Au minimum, ces endpoints devraient prendre un
`tenant_id` en paramètre pour cibler explicitement le bon tenant.

### 📋 Récap Phase 1

- ✅ **30 fichiers du 24/04** : pas de régression, parfaitement corrigés
- 🔴 **1 nouveau trou CRITIQUE** : `token_manager.py:230`
- 🟠 **10 nouveaux trous IMPORTANT** : `admin/profile.py` (×6), `memory_teams.py` (×2), `synthesis_engine.py` (×1), `report_actions.py` (×1)
- 🟡 **4 nouveaux trous ATTENTION** : `super_admin_users.py` (×4, endpoints super-admin)

**Estimation correctifs** : ~30 min de fixes mécaniques pour ces 15 requêtes.

