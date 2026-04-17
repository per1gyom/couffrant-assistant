# Raya — Matrice de capabilities (architecture)

**Dernière mise à jour : 17/04/2026**

---

## 1. Vision

Raya est connectée à de nombreux outils (Odoo, Gmail, Drive, Teams, Calendrier…) qui exposent chacun des dizaines d'actions possibles (lire, écrire, envoyer, supprimer, déplacer, etc.). Sans cadre, Raya pourrait tout faire en théorie — ce qui est à la fois dangereux (une suppression peut être irréversible) et inadapté au métier de chaque entreprise.

La **matrice de capabilities** définit **qui peut faire quoi** de façon fine, avec trois niveaux d'autorité :

1. **Défaut code** — ce que le code de Raya peut techniquement faire (tout ce qui est implémenté).
2. **Politique admin (tenant)** — l'admin de l'entreprise autorise ou refuse chaque action, pour tous les utilisateurs de son tenant. Il peut **verrouiller** certaines décisions (aucun user ne peut réactiver).
3. **Préférence user** — chaque utilisateur peut désactiver pour lui-même des actions qui restent techniquement possibles, par prudence personnelle.

**Principe de précaution** : tout se résout par la règle la plus restrictive. L'admin ne peut pas forcer un user à activer une action que l'user a désactivée pour lui-même. L'user ne peut pas activer une action que l'admin a verrouillée.

---

## 2. Principes fondateurs

### 2.1 Découverte 360° d'abord, filtrage ensuite
On ne part plus d'une liste hardcodée de ce qui est autorisé. On **explore tout ce que l'outil expose** à la découverte, on peuple le catalogue des capabilities, puis on applique les politiques admin/user. Avantage : aucune fonctionnalité de l'outil n'est oubliée par négligence de code.

### 2.2 Catalogue central (source de vérité)
Chaque capability a un identifiant unique (`tool.action`), une catégorie (`read`/`write`/`delete`/`admin`), un niveau de risque (`low`/`medium`/`high`/`destructive`), et un nom affichable en français. Le catalogue est en base de données, pas dans le code.

### 2.3 Résolution en cascade
L'ordre d'évaluation est strict : `default → tenant_policy → user_preference → effectif`. Le verrou admin (`locked=true`) coupe la chaîne et empêche l'user d'override.

### 2.4 Raya a conscience (stratégie 4 — ultra-minimaliste actionnable)
Le prompt système reçoit seulement les **exceptions actionnables** : capabilities désactivées par l'user (réactivables par lui-même) ou par l'admin (où l'user peut faire une demande). Les capabilities autorisées par défaut ne sont pas listées — Raya les tente naturellement, le résolveur backend valide.

### 2.5 Double sécurité
Le prompt guide Raya, mais **chaque action** passe par `resolve()` avant exécution. Si hallucination ou contournement, le résolveur refuse.

### 2.6 Refus pédagogique
Quand une action est refusée, Raya ne dit pas juste "non". Elle explique la raison et propose une solution (réactiver soi-même, demander à l'admin, action alternative).

---

## 3. Modèle de données

### 3.1 Table `tool_capabilities` (catalogue)

```sql
CREATE TABLE tool_capabilities (
    id              SERIAL PRIMARY KEY,
    tool_type       TEXT NOT NULL,          -- 'odoo' | 'drive' | 'gmail' | 'calendar' | ...
    capability_key  TEXT NOT NULL,          -- 'read_contacts' | 'send_mail' | 'delete_file' ...
    category        TEXT NOT NULL,          -- 'read' | 'write' | 'delete' | 'admin'
    risk_level      TEXT NOT NULL,          -- 'low' | 'medium' | 'high' | 'destructive'
    display_name    TEXT NOT NULL,          -- "Supprimer un fichier"
    description     TEXT,                   -- explication courte pour l'UI
    default_enabled BOOLEAN DEFAULT true,   -- autorisé par défaut si aucune politique
    discovered_at   TIMESTAMP DEFAULT NOW(),
    UNIQUE(tool_type, capability_key)
);
```

Peuplée automatiquement par la découverte 360° à chaque clic **🔍 Découvrir** ou job scheduler périodique. Les capabilities inconnues au code sont ajoutées avec `default_enabled=false` pour prudence (admin doit les activer explicitement).

### 3.2 Table `tenant_capability_policy` (règles admin)

```sql
CREATE TABLE tenant_capability_policy (
    id              SERIAL PRIMARY KEY,
    tenant_id       TEXT NOT NULL,
    connection_id   INTEGER,                -- NULL = s'applique à toutes les connexions du tool_type
    tool_type       TEXT NOT NULL,
    capability_key  TEXT NOT NULL,
    enabled         BOOLEAN NOT NULL,       -- true = autorisé, false = interdit
    locked          BOOLEAN DEFAULT false,  -- true = aucun user ne peut override
    reason          TEXT,                   -- optionnel, explication admin
    updated_by      TEXT,                   -- username admin ayant fait la modif
    updated_at      TIMESTAMP DEFAULT NOW(),
    UNIQUE(tenant_id, connection_id, tool_type, capability_key)
);
```

### 3.3 Table `user_capability_preference` (prefs user)

```sql
CREATE TABLE user_capability_preference (
    id              SERIAL PRIMARY KEY,
    username        TEXT NOT NULL,
    tool_type       TEXT NOT NULL,
    capability_key  TEXT NOT NULL,
    enabled         BOOLEAN NOT NULL,       -- true = user veut, false = user refuse
    updated_at      TIMESTAMP DEFAULT NOW(),
    UNIQUE(username, tool_type, capability_key)
);
```

L'user ne peut créer/modifier une entrée ici que si la politique admin correspondante a `locked=false`. Une entrée `enabled=false` ici désactive pour l'user même si l'admin a autorisé.

### 3.4 Index de performance

```sql
CREATE INDEX idx_tool_capabilities_tool ON tool_capabilities(tool_type);
CREATE INDEX idx_tenant_policy_lookup ON tenant_capability_policy(tenant_id, tool_type, capability_key);
CREATE INDEX idx_user_pref_lookup ON user_capability_preference(username, tool_type, capability_key);
```

---

## 4. Résolveur

Le résolveur est la fonction centrale qui répond à la question : *"Est-ce que cet user, dans ce tenant, peut faire cette action sur cet outil ?"*

### 4.1 Signature

```python
def resolve(username: str, tool_type: str, capability_key: str,
            tenant_id: str, connection_id: int = None) -> dict:
    """
    Retourne :
    {
        "allowed": bool,
        "reason": str,          # 'default_enabled' | 'admin_enabled' | 'admin_disabled' |
                                # 'admin_locked' | 'user_disabled' | 'not_found'
        "can_self_enable": bool,  # true si user peut réactiver dans ses prefs
        "can_request_admin": bool,  # true si admin pourrait débloquer
        "capability": dict,     # métadonnées (display_name, risk, category)
    }
    """
```

### 4.2 Algorithme

```
1. Lire la capability dans tool_capabilities
   → Si inexistante : return {allowed: false, reason: 'not_found'}

2. Chercher la politique tenant (tenant_id, tool_type, capability_key)
   → Si trouvée et enabled=false et locked=true :
        return {allowed: false, reason: 'admin_locked', can_self_enable: false,
                can_request_admin: true}
   → Si trouvée et enabled=false et locked=false :
        (continuer en regardant user preference)

3. Chercher la préférence user (username, tool_type, capability_key)
   → Si trouvée et enabled=false :
        return {allowed: false, reason: 'user_disabled', can_self_enable: true}
   → Si trouvée et enabled=true :
        allowed = (admin_policy absent OR admin_policy.enabled=true)

4. Si aucune pref user :
   → allowed = politique admin.enabled SI politique existe, SINON default_enabled
   → reason selon origine
```

### 4.3 Wrapper `try_action`

Utilisé par les modules d'actions (`mail_actions.py`, `confirmations.py`, etc.) pour protéger chaque point d'entrée :

```python
def try_action(username, tool_type, capability_key, tenant_id, action_fn, *args, **kwargs):
    """
    Protège une action : vérifie resolve() avant d'exécuter.
    Si autorisé → exécute action_fn et retourne le résultat.
    Si refusé → retourne un dict {ok: False, refused: True, reason, can_self_enable, ...}
                sans exécuter l'action.
    """
    decision = resolve(username, tool_type, capability_key, tenant_id)
    if not decision["allowed"]:
        return {
            "ok": False, "refused": True,
            "reason": decision["reason"],
            "capability": decision["capability"]["display_name"],
            "can_self_enable": decision["can_self_enable"],
            "can_request_admin": decision["can_request_admin"],
        }
    return action_fn(*args, **kwargs)
```

### 4.4 Cache

`resolve()` est appelée potentiellement 10-50× par conversation. Cache mémoire 60 s par combinaison `(username, tool_type, capability_key, tenant_id)`, invalidé sur modification de politique/pref.

---

## 5. Injection prompt (Stratégie 4)

### 5.1 Principe

On ne liste dans le prompt QUE **ce qui est bloqué ET a une valeur pour l'UX**.
- ❌ On ne liste pas les capabilities autorisées (Raya les tente naturellement).
- ❌ On ne liste pas les blocages sans recours (pas utile à savoir).
- ✅ On liste les blocages réactivables par l'user.
- ✅ On liste les blocages débloquables par escalade admin.

### 5.2 Format du bloc injecté

```
=== CAPACITÉS DÉSACTIVÉES (réactivables) ===
⚙️ Par toi (réactivables dans Paramètres → Outils) :
  • drive.delete_file — "Supprimer un fichier"
  • calendar.delete_event — "Supprimer un événement"
🔒 Par ton admin (tu peux demander le déblocage) :
  • odoo.create_invoice — "Créer une facture"
```

Si aucune exception → bloc **totalement absent** du prompt (0 tokens gaspillés).

### 5.3 Instructions comportementales (ajoutées aux CORE_RULES)

```
Si l'utilisateur demande une action :
- Vérifie si la capability est dans la liste des désactivées (bloc ci-dessus).
- Si oui et ⚙️ (désactivée par lui-même) : propose-lui de la réactiver
  dans Paramètres → Outils → [outil]. Donne le nom affichable exact.
- Si oui et 🔒 (désactivée admin) : explique que l'admin a bloqué, propose
  une action alternative (ex: préparer le brouillon au lieu de créer).
- Si la capability n'est pas listée : tente l'action normalement.
  Le résolveur backend validera à l'exécution.
```

### 5.4 Implémentation

```python
def build_capabilities_block(username: str, tenant_id: str) -> str:
    """
    Génère le bloc à injecter dans le prompt système.
    Retourne une chaîne vide si aucune exception à signaler.
    """
    exceptions = get_capability_exceptions(username, tenant_id)
    if not exceptions["user_disabled"] and not exceptions["admin_locked"]:
        return ""
    # formater les deux sections avec display_name + catégorie
    ...
```

Appelé par `build_system_prompt` dans `aria_context.py`, injecté juste avant CORE_RULES.

---

## 6. UI — Admin & User

### 6.1 Panel admin — nouvel onglet "Outils & Permissions"

Accessible uniquement aux `super_admin` + `tenant_admin`.

**Structure** :
```
┌─ Outils & Permissions ───────────────────────────────────────┐
│                                                              │
│ Sélectionner connexion : [Odoo Couffrant ▼]                  │
│                                                              │
│ LECTURE                                                      │
│   Lire les contacts              [✓] activé  □ verrouiller  │
│   Lire les devis                 [✓] activé  □ verrouiller  │
│   Lire les factures              [✓] activé  □ verrouiller  │
│                                                              │
│ ÉCRITURE                                                     │
│   Créer un contact               [✓] activé  □ verrouiller  │
│   Créer un devis                 [✓] activé  ☑ verrouiller  │
│   Créer une facture              [✗] DÉSACTIVÉ  ☑ verrouillé│
│                                                              │
│ SUPPRESSION                                                  │
│   Supprimer un enregistrement    [✗] DÉSACTIVÉ  ☑ verrouillé│
│                                                              │
│ [💾 Enregistrer]                                             │
└──────────────────────────────────────────────────────────────┘
```

Le flag **Verrouiller** (checkbox à droite du toggle) force l'état admin et empêche les users de modifier leur préférence perso. Sans verrou, un user peut override en local.

### 6.2 Panel user — modal Paramètres → section "Outils & Permissions"

```
┌─ Outils & Permissions ───────────────────────────────────────┐
│                                                              │
│ Sélectionner outil : [Google Drive ▼]                        │
│                                                              │
│ LECTURE       Lire les fichiers          [✓] activé          │
│               Télécharger un fichier      [✓] activé          │
│                                                              │
│ ÉCRITURE      Déplacer un fichier         [✓] activé          │
│               Renommer un fichier         [✓] activé          │
│                                                              │
│ SUPPRESSION   Supprimer un fichier        [✗] désactivé      │
│                                                              │
│ [VERROUILLÉ PAR L'ADMIN — grisé]                             │
│   Partager publiquement un fichier  [non modifiable]         │
│                                                              │
│ [💾 Enregistrer]                                             │
└──────────────────────────────────────────────────────────────┘
```

Les lignes verrouillées admin apparaissent grisées avec mention "verrouillé par l'admin".

### 6.3 API REST

**Admin (super_admin ou tenant_admin, selon scope)** :
```
GET    /admin/capabilities/{tenant_id}/{tool_type}
       → catalogue + politique admin en cours
POST   /admin/capabilities/{tenant_id}
       → body: [{tool_type, capability_key, enabled, locked, connection_id?}]
       → met à jour les politiques en batch
```

**User** :
```
GET    /capabilities/me
       → liste effective pour l'user (avec source de chaque décision)
POST   /capabilities/me
       → body: [{tool_type, capability_key, enabled}]
       → met à jour ses préférences, refuse si admin-locked
```

---

## 7. Alternatives envisagées et écartées

### 7.1 Stratégie "rien dans le prompt"
Raya tente tout, le backend bloque. Écarté car : double appel LLM coûteux sur tout refus, expérience user frustrante (pas d'explication), pas de proposition proactive de réactivation.

### 7.2 Stratégie "lister tout l'autorisé"
~800 tokens dans le prompt, donne à Raya une vision de ce qu'elle peut faire mais pas de ce qui est bloqué. Écarté car : coût en tokens, pas de proactivité sur les réactivables, inefficace versus stratégie 4.

### 7.3 Stratégie "tout lister (autorisé + bloqué)"
~270 tokens, proactivité totale. Écarté car : 10× plus lourd que la stratégie 4 pour un gain d'info marginal (Raya n'a pas besoin de savoir qu'elle peut lire les mails, elle le tente naturellement).

### 7.4 Vectorisation des capabilities
Embedding + recherche sémantique au lieu de liste déterministe. Écarté car : les capabilities sont un système de **décision binaire** (oui/non), pas de recherche. Risque d'hallucination (Raya pourrait "trouver" une capability proche mais inexistante). La certitude est critique ici.

### 7.5 Permissions RBAC classiques (roles)
Rôles `viewer`/`editor`/`admin` comme dans beaucoup d'outils. Écarté car : trop grossier pour le cas Raya (granularité par capability nécessaire), pas de concept de préférence perso user, ne gère pas le verrou admin.

---

## 8. Plan d'implémentation par étapes

Chaque étape est **indépendamment déployable** sans casser l'existant. Pas de big-bang.

### Étape A — Socle DB + résolveur (backend uniquement, ~2h)
1. Créer les 3 tables dans `database_migrations.py`.
2. Créer `app/capabilities.py` avec `resolve()`, `try_action()`, `get_capability_exceptions()`.
3. Peupler `tool_capabilities` avec le catalogue initial (manuel, basé sur les actions Raya existantes). Seed dans `tools_seed_data.py`.
4. Tests unitaires : chaque branche du résolveur.

À ce stade : **aucun changement visible**. Le résolveur existe mais n'est pas encore câblé.

### Étape B — Intégration prompt (1h)
1. `build_capabilities_block()` dans `aria_context.py`.
2. Injection dans `build_system_prompt()` avant CORE_RULES.
3. Ajout des instructions comportementales dans CORE_RULES.
4. Test : créer une politique admin bloquante → vérifier que Raya adapte sa réponse.

### Étape C — Câblage actions (~2h)
1. Wrapper chaque point d'entrée d'action avec `try_action()` :
   - `mail_actions.py` : SEND_MAIL → `gmail.send_mail` ou `microsoft.send_mail`.
   - `confirmations.py` : TEAMS, DRIVE, CREATEEVENT.
   - `odoo_actions.py` : ODOO_CREATE, ODOO_UPDATE, ODOO_NOTE.
2. Quand refus : renvoyer le refus dans `actions_raw` avec marqueur `🚫` pour que le 2e appel LLM (synthèse) le traduise en réponse user.

### Étape D — UI admin (~2h)
1. Nouvel onglet dans `admin_panel.html` (+ code JS dans `admin-panel.js`).
2. Routes `/admin/capabilities/*`.
3. Bump cache-bust admin-panel.

### Étape E — UI user (~1h)
1. Bloc dans la modal Paramètres (`chat_panel.html` ou équivalent).
2. Routes `/capabilities/me`.
3. Bump cache-bust chat.

### Étape F — Découverte 360° connectée au catalogue (~2h)
1. Modifier les fonctions `discover_*` pour qu'elles insèrent/updatent aussi dans `tool_capabilities` (chaque capability découverte).
2. Rapport de découverte enrichi : nombre de nouvelles capabilities détectées.

---

## 9. Tests de non-régression

À chaque modification du résolveur ou du catalogue, dérouler :

### 9.1 Tests unitaires résolveur
- Capability inexistante → `not_found`, non autorisée.
- Capability `default_enabled=true`, aucune politique, aucune pref → `allowed=true`.
- Politique admin `enabled=false`, `locked=false`, aucune pref user → `allowed=false`, `can_self_enable=true`.
- Politique admin `enabled=false`, `locked=true`, pref user `enabled=true` → `allowed=false`, `can_self_enable=false`.
- Politique admin `enabled=true`, pref user `enabled=false` → `allowed=false`, `can_self_enable=true` (via modif pref).
- Politique admin absente, pref user `enabled=false` → `allowed=false`, `can_self_enable=true`.

### 9.2 Tests d'intégration prompt
- Tenant sans aucune politique → bloc capabilities **absent** du prompt.
- Tenant avec 1 politique admin bloquante → bloc contient 1 🔒.
- User avec 1 pref désactivée → bloc contient 1 ⚙️.
- Mix des deux → bloc contient les deux sections.

### 9.3 Tests de refus pédagogique
- Demander à Raya une action désactivée par l'user → vérifier qu'elle propose réactivation avec chemin UI exact.
- Demander une action locked admin → vérifier qu'elle explique + propose alternative.
- Demander une action autorisée mais refusée au runtime par le backend (cas rare d'hallucination) → vérifier que le message d'erreur remonte et que Raya le traduit proprement.

### 9.4 Tests UI
- Admin désactive une capability → vérifier prop descendante dans `/capabilities/me` pour tous les users du tenant.
- Admin verrouille → vérifier que le toggle user correspondant devient grisé.
- User active/désactive une pref → vérifier persistance et effet immédiat dans le prompt du message suivant.

---

## 10. Glossaire

- **Capability** — unité atomique d'action dans un outil (ex: `drive.delete_file`). Identifiant `tool_type.capability_key`.
- **Catalogue** — table `tool_capabilities`, source de vérité de ce qui existe techniquement.
- **Politique** — décision admin (tenant) sur une capability. Table `tenant_capability_policy`.
- **Préférence** — décision user sur une capability. Table `user_capability_preference`.
- **Verrou** (`locked=true`) — politique admin qui empêche toute override user.
- **Résolveur** — fonction `resolve()` qui produit la décision finale.
- **Découverte 360°** — introspection exhaustive d'un outil pour peupler le catalogue sans liste hardcodée.
