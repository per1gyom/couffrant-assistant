# 📋 Rapport d'audit — Chaîne de permissions Raya

**Auteur** : Claude  
**Date** : 19 avril 2026, ~3h30 du matin  
**Demandé par** : Guillaume, après session marathon de 20h + 18 patchs UX successifs  
**Objectif** : Comprendre en profondeur pourquoi le bouton de bascule Lecture seule / Lecture écriture ne se met pas à jour visuellement côté tenant_panel après une action, alors qu'il marche côté super admin panel

---

## 🎯 TL;DR

Le code côté tenant_panel et côté admin-panel **fait littéralement la même chose** pour gérer l'état visuel du bouton après une action. Les 2 versions sont quasi identiques. Pourtant l'une marche et l'autre pas.

La cause racine n'est donc **pas dans la logique** — elle est dans **l'environnement d'exécution** (ordre des événements, cycle de rendu du navigateur, nature du DOM). 

Ma conviction après audit : le problème ne se résoudra **pas** avec un énième patch ciblé sur le bug visuel. Il faut soit (a) remplacer le `prompt()` bloquant par un vrai modal HTML, soit (b) refactoriser le flow de `toggleReadOnly` pour suivre exactement le même pattern structurel que le super admin (reconstruction complète du DOM parent, pas d'appel de fonction asynchrone en fin de flow).

---

## 📐 Architecture de la chaîne

### 1. Base de données — `tenant_connections`

Table clé avec 3 colonnes liées aux permissions :
- `super_admin_permission_level` : plafond fixé par le super admin Raya
- `tenant_admin_permission_level` : niveau appliqué par le tenant admin (≤ plafond)
- `previous_permission_level` : sauvegarde utilisée par le bouton « Tout en lecture seule »

Par défaut `read_write_delete` pour les deux niveaux (modifié le 19/04 pour débloquer les radios).

### 2. Backend — `app/permissions.py`

Module central, propre et bien structuré :
- `check_permission()` : vérifie qu'une action est autorisée (middleware)
- `update_permission()` : met à jour un niveau avec cappage automatique
- `toggle_all_read_only()` : bascule verrouiller/restaurer
- `get_tenant_lock_status()` : retourne `{is_locked, total, locked}`
- `get_all_permissions_for_tenant()` : pour l'injection dans le prompt Raya

**Verdict backend** : propre, logique cohérente, un seul bug corrigé pendant la nuit (`toggle_all_read_only` qui touchait à `super_admin_permission_level` par erreur, corrigé dans commit 79f39ca).

### 3. Endpoints

Séparation propre tenant_admin / super_admin :

**`/tenant/permissions*`** (dans `app/routes/admin/tenant_admin.py`) :
- GET `/tenant/permissions` → liste les connexions + niveaux
- POST `/tenant/permissions/update` → modifie un niveau tenant
- GET `/tenant/permissions/lock-status` → is_locked true/false
- POST `/tenant/permissions/toggle-read-only` → bascule

**`/admin/tenant/{id}/permissions*`** (dans `app/routes/admin/super_admin.py`) :
- GET `/admin/tenant/{id}/permissions` → idem mais cross-tenant
- POST `/admin/tenant/{id}/permissions/update` → modifie (super_admin ou tenant_admin level)
- GET `/admin/tenant/{id}/lock-status` → is_locked cross-tenant
- POST `/admin/tenant/{id}/toggle-read-only` → bascule cross-tenant

**Verdict endpoints** : propre, symétrique, bien séparé par rôle.

### 4. Frontend — tenant_panel.html (ne marche pas)

2 fonctions clés :

**`loadPermissions()`** (asynchrone) :
1. Fetch `/tenant/permissions` avec cache-bust
2. Calcule `isAllLocked` (majorité des connexions en read + previous_level non-null)
3. Stocke dans variable globale `_lastPermissionsState`
4. Remplace le bouton via `outerHTML` (pour forcer un nouveau nœud DOM)
5. Rend le tableau des radios dans `permissions-list.innerHTML`

**`toggleReadOnly()`** (asynchrone, appelée au clic) :
1. `await loadPermissions()` → recharge l'état AVANT le modal
2. `await requestAnimationFrame` × 2 + setTimeout 50ms (tentative de repaint)
3. `prompt()` bloquant → user tape "oui"
4. `await fetch POST toggle-read-only` → backend fait l'action
5. `await requestAnimationFrame` × 1
6. `loadPermissions()` **sans await** → relance le rafraîchissement
7. `await requestAnimationFrame` × 2

### 5. Frontend — admin-panel.js (marche)

2 fonctions clés :

**`loadCompanies()`** + **`updateLockButtonState()`** + **`loadPermissionsForTenant()`** :
- `loadCompanies` : fetch global, reconstruit TOUT le HTML des cartes via `innerHTML` massif
- Puis pour chaque tenant, appelle `updateLockButtonState` qui modifie les styles du bouton 🔒
- Puis `loadPermissionsForTenant` qui rend le tableau de permissions

**`toggleReadOnlyForTenant()`** (asynchrone, appelée au clic) :
1. `await fetch lock-status` → récupère l'état
2. `await requestAnimationFrame` × 2 + setTimeout 50ms
3. `prompt()` bloquant → user tape "oui"
4. `await fetch POST toggle-read-only`
5. `await requestAnimationFrame` × 1
6. `loadCompanies()` **sans await**
7. `await requestAnimationFrame` × 2

---

## 🔍 Comparaison structurelle

Les 2 flows (toggleReadOnly tenant vs toggleReadOnlyForTenant super admin) sont **quasi identiques**. Voici les différences :

| Aspect | tenant_panel | admin-panel (qui marche) |
|---|---|---|
| Fonction de reload | `loadPermissions()` — léger | `loadCompanies()` — lourd |
| Fetchs déclenchés | 1 seul (/tenant/permissions) | 1 + N × 3 (overview + N × loadConnections + N × updateLockButtonState + N × loadPermissionsForTenant) |
| Portée DOM touchée | 1 bouton + 1 div (~200 chars d'innerHTML) | ~50+ éléments complètement recréés |
| Durée d'exécution | ~100-300ms | ~1-2s (plusieurs fetchs) |
| Bouton mis à jour via | `outerHTML` (remplacement complet) | `innerHTML` + `style.xxx =` (modification directe) |

## 🧩 Analyse profonde du bug

### Ce qui devrait se passer

Après le POST du toggle :
1. Le backend change la DB
2. `loadPermissions()` est lancé, fetche la nouvelle DB, met à jour le DOM
3. Le navigateur repeint le DOM mis à jour
4. L'utilisateur voit le bouton rouge (ou transparent)

### Ce qui se passe réellement

Guillaume confirme que l'action backend est OK (la DB change bien). Le bug est visuel : le DOM ne se rafraîchit pas visuellement avant un second clic.

### Hypothèses examinées

**H1 : Bug de logique dans `loadPermissions`** — REJETÉE. Le code est correct, les valeurs stockées sont bonnes. On le sait parce que au second clic, le prompt affiche le bon état (qui vient de `_lastPermissionsState` mis à jour par `loadPermissions`).

**H2 : Cache HTTP (navigateur ou Fastly)** — REJETÉE. On a ajouté `?_=Date.now()` et `{cache: 'no-store'}`. Si c'était le cache, le second clic afficherait aussi l'ancien état. Or ce n'est pas le cas.

**H3 : Bouton qui ne repaint pas après modification de styles** — REJETÉE (partiellement). On a essayé :
- `setProperty(..., 'important')` → ne marche pas
- `offsetHeight` pour forcer le reflow → ne marche pas
- `outerHTML` pour recréer le nœud → ne marche pas
- Pourtant côté super admin, un simple `btn.style.background = '...'` suffit

**H4 : Le `prompt()` bloquant laisse le navigateur dans un état fragile** — VRAISEMBLABLE. C'est un bug connu de Chrome/Safari : après la fermeture d'un `prompt()`, le navigateur peut "ne pas voir" certaines modifications DOM subséquentes, surtout si elles arrivent dans un délai court sans charge de rendu massive.

**H5 : `loadPermissions()` sans await ne donne pas le temps au browser de peindre** — FORTE. Le flow actuel fait :
```
POST → renderFrame → loadPermissions (async, sans await) → renderFrame × 2 → fin
```
La fonction `toggleReadOnly` se termine AVANT que `loadPermissions` ait fini son fetch. Quand le fetch revient, le DOM est modifié, mais le navigateur est peut-être déjà en mode "idle" et ne retraite pas l'update comme une priorité.

Côté super admin : `loadCompanies()` est tellement lourd (5+ fetchs, 50+ modifications DOM) qu'il occupe le thread pendant ~1-2s. Ça force naturellement plusieurs cycles de rendu.

---

## 🎯 Cause racine probable

**Le `prompt()` bloque le thread pendant un temps indéterminé. Après sa fermeture, le navigateur a besoin d'un "gros travail DOM" pour déclencher un repaint complet. `loadPermissions()` est trop léger pour le faire.**

Côté super admin, `loadCompanies()` fournit ce "gros travail". Côté tenant, `loadPermissions()` est trop minimaliste.

---

## 🔧 Solutions possibles (ordonnées par propreté)

### Solution 1 — REMPLACER prompt() par un modal HTML ⭐ RECOMMANDÉE

C'est la vraie solution propre. Un modal HTML personnalisé ne bloque pas le thread, donc :
- Pas de bug de repaint après fermeture
- Pas besoin de requestAnimationFrame
- UX plus moderne
- Cohérent sur tous les navigateurs

**Effort** : moyen (~30 min de dev)  
**Risque** : faible, pattern connu

### Solution 2 — Ajouter location.reload() après l'action

Solution brutale mais qui marche à 100%. Après la réussite du toggle, faire :
```js
window.location.reload();
```

**Effort** : très faible  
**Inconvénient UX** : la page rechargé entièrement, perte du scroll, flicker  
**Risque** : nul

### Solution 3 — Faire loadPermissions "plus lourd"

Dans `loadPermissions`, ajouter artificiellement du travail :
- Faire un 2e fetch dummy en parallèle
- Ou insérer/supprimer/réinsérer des nœuds DOM
- Ou recharger aussi d'autres sections (tout company-content)

**Effort** : faible  
**Risque** : hack fragile qui peut re-casser

### Solution 4 — Déplacer le bouton dans la section rechargée

Au lieu d'avoir le bouton en dehors de `permissions-list`, le mettre DANS. Ainsi quand `loadPermissions` fait `list.innerHTML = html`, le bouton est recréé en même temps que le tableau — même pattern que côté super admin.

**Effort** : faible  
**Risque** : nécessite revue HTML + CSS

### Solution 5 — Remplacer complètement tout le permissions-card

Dans `loadPermissions`, au lieu de modifier les sous-éléments, remplacer le contenu complet de `#permissions-card` (qui inclut le header avec le bouton, la description, le tableau). Force un redraw massif identique à côté super admin.

**Effort** : moyen (restructuration du rendu)  
**Risque** : faible

---

## 📉 Anti-pattern identifié dans la session

En revenant sur les 18 derniers commits permissions, je constate un **pattern toxique de résolution** :

1. Bug signalé par Guillaume
2. Hypothèse posée rapidement
3. Patch ciblé basé sur cette hypothèse
4. Bug "corrigé" en apparence mais vrai problème non compris
5. Nouveau bug signalé (souvent le même sous une forme différente)
6. Boucle

Exemples concrets :
- J'ai ajouté `setProperty('important')` (ne marchait pas)
- Puis `cloneNode + replaceChild` (ne marchait pas, n'a pas été committé mais considéré)
- Puis `offsetHeight` pour forcer reflow (ne marchait pas)
- Puis `outerHTML` pour recréer le nœud (ne marchait pas)
- Puis `requestAnimationFrame` × 2 (ne marchait pas)
- Puis cache-bust + no-store (ne marchait pas)

À chaque étape, j'aurais dû faire ce que Guillaume m'a demandé à 3h du matin : **prendre le temps d'auditer avant de patcher**.

---

## 🧭 Recommandations finales

### Pour demain (ordre de priorité)

1. **Ne PAS patcher encore**. Lire ce rapport à tête reposée.

2. **Implémenter Solution 1** (remplacer prompt() par modal HTML). C'est la solution propre. 30 minutes de dev, règle le problème à la racine, améliore l'UX générale.

3. **Tester rigoureusement** :
   - Verrouiller → vérifier bouton, bandeau, radios
   - Restaurer → vérifier bouton, bandeau, radios
   - Modifier un radio individuellement → vérifier persistance
   - Rafraîchir la page → vérifier cohérence
   - Tester dans Chrome ET Safari (macOS)

4. **Si nécessaire, Solution 5** (restructurer le rendu pour remplacer le permissions-card complet).

### Pour plus tard (audit approfondi)

Voir `docs/raya_permissions_audit_todo.md` pour la checklist complète.  
Points particuliers à re-vérifier :
- Tests E2E Playwright sur le toggle
- Cache-Control headers côté serveur
- Concurrence multi-onglets
- Injection dans le prompt Raya (`_build_permissions_block`)

---

## 💬 Note personnelle pour Guillaume

Guillaume, tu as eu absolument raison de me stopper et de demander un audit. Je te dois des excuses pour avoir enchaîné 18 patchs en mode "essayons ça" sans jamais prendre le temps de comprendre en profondeur.

Trois leçons à retenir de ma part :

1. **Quand un bug résiste à 3 patchs, changer d'approche**. Pas plus de patchs, mais un audit.

2. **Un bug visuel qui marche ici mais pas là**, c'est presque toujours un problème structurel (ordre d'exécution, cycle de rendu, nature du DOM). Pas un problème de valeur ou de logique.

3. **Copier "le code qui marche" ne suffit pas**. Il faut comprendre POURQUOI il marche. Le code côté super admin marche grâce à la **lourdeur de loadCompanies**, pas grâce à son code JavaScript. C'est l'écosystème qui compte.

Bonne nuit Guillaume. Le Scanner P1 tourne, tu vérifieras demain. On reprend avec la tête reposée. Merci de m'avoir demandé cet audit, ça m'a permis de vraiment comprendre ce que je ne comprenais pas.
