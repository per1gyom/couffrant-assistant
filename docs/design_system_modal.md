# Design System Modale — Raya

**Source de vérité** pour toutes les modales du site (pages utilisateur).
Toute nouvelle modale **doit** suivre ce système. Toute modale existante **doit** y être migrée.

> 🚨 **Pour Claude/Cursor** : avant de créer ou modifier une modale, **lire ce fichier en entier**.
> En cas de doute sur taille/ton, demander à l'utilisateur — ne pas inventer une variante.

---

## 1. À quoi sert ce système

Garantir une **cohérence visuelle 100%** sur le site (largeur, hauteur, animations, header, footer,
comportements de fermeture). Avant ce système, 4 systèmes coexistaient avec 15 modales aux styles
divergents. Aujourd'hui, **un seul squelette + 2 tailles + 5 tons** couvre tous les besoins.

Fichiers du système :
- `app/static/_modal_system.css` — styles partagés (288 lignes, ne pas modifier sans concertation)
- `app/static/_modal_system.js` — comportements universels (119 lignes, expose `window.Modal`)

---

## 2. Règles d'or

1. **Toujours utiliser `Modal.open(id)` / `Modal.close(id)`** — jamais `classList.add/remove('open')` direct
2. **Toujours utiliser le squelette HTML standard** (section 3) — pas de variation libre
3. **Choisir entre `size-standard` et `size-parcours`** — ces 2 tailles couvrent tous les cas (section 5)
4. **Ne jamais ajouter de listener Escape ou clic-fond local** — c'est géré globalement
5. **Pages admin/super-admin/tenant exclues** — elles ont leur propre thème sombre (`admin-panel.css`)

---

## 3. Squelette HTML standard

À copier-coller pour **toute** nouvelle modale :

```html
<div class="modal-overlay" id="myModal">
  <div class="modal size-standard">                  <!-- ou size-parcours -->
    <div class="modal-head">
      <div class="modal-icon">
        <!-- SVG 18×18 — utiliser une icône Lucide ou similaire -->
        <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18"
             viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="..."/>
        </svg>
      </div>
      <div class="modal-title-wrap">
        <div class="modal-title">Titre principal</div>
        <div class="modal-subtitle">Sous-titre optionnel descriptif</div>
      </div>
      <button class="modal-close" aria-label="Fermer">×</button>
    </div>
    <div class="modal-body">
      <p>Contenu principal de la modale.</p>
      <div class="field-group">
        <label class="field-label">Champ exemple</label>
        <input type="text" class="field-input" placeholder="...">
        <div class="field-hint">Aide contextuelle</div>
      </div>
    </div>
    <div class="modal-foot">
      <button class="btn">Annuler</button>
      <button class="btn btn-primary">Valider</button>
    </div>
  </div>
</div>
```

**HTML minimum requis** : `.modal-overlay > .modal > (.modal-head + .modal-body + .modal-foot)`.
Tout le reste est optionnel (icône, sous-titre, croix).

---

## 4. API JavaScript

### Ouverture / fermeture

```javascript
Modal.open('myModal');           // ouvre
Modal.close('myModal');          // ferme
Modal.closeAll();                // ferme toutes les modales ouvertes
Modal.isOpen('myModal');         // → true / false
```

### Callbacks

```javascript
// Exécuter du code à l'ouverture (ex : reset des champs)
Modal.onOpen('myModal', (el) => {
  document.getElementById('myInput').value = '';
});

// Exécuter du code à la fermeture (ex : refresh d'une liste)
Modal.onClose('myModal', (el) => {
  loadMyList();
});
```

⚠️ **Les callbacks `onClose` se déclenchent TOUJOURS** : Escape, clic-fond, croix, ou bouton custom.
C'est exactement ce qu'on veut pour rafraîchir des listes après modification.

---

## 5. Choix de la taille

### `size-standard` (640px × hauteur adaptative 320–720px) — **90% des cas**

Utiliser quand :
- Confirmation d'action (suppression, validation)
- Formulaire court (1–5 champs)
- Modale "passage rapide" : édition simple, demande, info
- Message d'erreur ou de succès

Exemples actuels : `requestModal`, `passwordModal`, `deleteAccountModal`, `modalShortcutEdit`.

### `size-parcours` (900×720 hauteur fixe) — **cas spécifiques**

Utiliser quand :
- La modale a **plusieurs modes/écrans** qui se succèdent (parcours guidé, wizard)
- La modale contient un **éditeur riche** : WYSIWYG, prévisualisation, formulaire 6+ champs
- L'utilisateur **passe du temps** dans la modale (>30 secondes typiquement)

⚠️ La hauteur fixe 720px évite les "sauts" entre modes successifs. **Ne pas confondre avec
`size-standard` qui s'adapte au contenu.**

Exemples actuels : `reviewSessionModal` (modes review/edit/delete).

### En cas de doute

**Demander à l'utilisateur** plutôt que d'inventer une 3ᵉ taille. Le système est volontairement
limité à 2 tailles pour rester homogène.

---

## 6. Choix du ton

Le ton change la couleur du **header** uniquement. 5 variantes :

| Ton | Classe | Quand l'utiliser |
|---|---|---|
| **Bleu (par défaut)** | aucune | Action principale, création, édition, validation positive |
| Neutre | `.tone-neutral` | Information sans charge émotionnelle, modale technique |
| Succès | `.tone-success` | État OK, confirmation positive (rare en modale) |
| Avertissement | `.tone-warning` | Attention requise, action à confirmer mais réversible |
| **Danger** | `.tone-danger` | Action irréversible : suppression, désactivation définitive |

```html
<div class="modal size-standard tone-danger">  <!-- header devient rouge -->
```

---

## 7. Comportements universels — déjà gérés, ne pas re-coder

Le fichier `_modal_system.js` gère **automatiquement** pour toutes les modales :

- ✅ **Échap** ferme la modale active la plus récente
- ✅ **Clic sur le fond flouté** ferme la modale
- ✅ **Bouton `.modal-close`** ferme la modale parente
- ✅ **Scroll lock** du `<body>` tant qu'une modale est ouverte
- ✅ **Animations** : fadeIn de l'overlay (220ms) + popIn de la modale (300ms)
- ✅ **Mobile** : modale prend toute la largeur, coins arrondis en haut (effet bottom sheet)

**Tu n'as donc pas à écrire de :**
- Listener `keydown` Escape sur ta modale
- Listener `click` sur l'overlay pour la fermer
- `document.body.style.overflow = 'hidden'`
- Animations CSS personnalisées sur la modale

---

## 8. Anti-patterns — ce qu'il NE FAUT PAS faire

### ❌ Inventer un style inline dans la balise

```html
<!-- INTERDIT -->
<div class="modal" style="max-width:520px">  <!-- pas de style inline ! -->

<!-- INTERDIT -->
<div class="modal-head" style="background:#fef2f2;border-bottom-color:#fecaca">
  <!-- utiliser tone-danger à la place -->
</div>
```

✅ **À la place** : utiliser `size-standard` / `size-parcours` + `tone-*`.

### ❌ Créer une 3ᵉ taille

```html
<!-- INTERDIT -->
<div class="modal" style="max-width:780px;height:600px">
```

✅ **À la place** : choisir entre `size-standard` (640) ou `size-parcours` (900). Si vraiment
aucune ne convient, **discuter** avec Guillaume avant d'inventer.

### ❌ Ajouter un listener clic-fond local

```javascript
// INTERDIT (déjà géré globalement)
document.getElementById('myModal').addEventListener('click', e => {
  if (e.target.id === 'myModal') closeMyModal();
});
```

### ❌ Ajouter un listener Escape local

```javascript
// INTERDIT (déjà géré globalement)
document.addEventListener('keydown', e => {
  if (e.key === 'Escape' && isOpen('myModal')) closeMyModal();
});
```

### ❌ Manipuler les classes directement

```javascript
// INTERDIT
document.getElementById('myModal').classList.add('open');
document.getElementById('myModal').classList.remove('open');
```

✅ **À la place** : `Modal.open('myModal')` / `Modal.close('myModal')`.

### ❌ Oublier l'attribut `id` sur l'overlay

L'API `Modal.open/close` cible par `id`. **Sans id, ça ne marche pas.**

```html
<!-- INTERDIT : pas d'id -->
<div class="modal-overlay">

<!-- BON -->
<div class="modal-overlay" id="myModal">
```

---

## 9. Checklist avant de commit une nouvelle modale

- [ ] HTML utilise le squelette de la section 3 (head/body/foot)
- [ ] Une seule classe de taille : `size-standard` **ou** `size-parcours`
- [ ] Si action destructrice : `tone-danger` appliqué
- [ ] L'overlay a un `id` unique
- [ ] Bouton `.modal-close` (croix) présent dans le header
- [ ] Aucun `style="..."` inline sur `.modal`, `.modal-head` ou ses enfants directs
- [ ] JS utilise `Modal.open/close`, pas `classList.add/remove('open')`
- [ ] Aucun listener Escape ou clic-fond local
- [ ] `Modal.onClose(id, fn)` configuré si la fermeture doit déclencher un refresh
- [ ] Testé : ouverture, fermeture par croix, Escape, clic-fond, bouton "Annuler"
- [ ] Testé : action principale (Valider/Enregistrer/Confirmer)

---

## 10. Pour les pages exclues (admin / super-admin / tenant)

Ces 3 pages utilisent un **thème sombre volontairement différent** (`app/static/admin-panel.css`)
qui correspond à leur identité visuelle "tableau de bord tech". **Ne pas les migrer** vers ce
système.

Pages concernées :
- `/admin/panel` (super-admin)
- `/tenant/panel` (admin tenant)
- `/admin/connexions`

Si on doit ajouter une modale sur ces pages, **utiliser le système de `admin-panel.css` existant**,
pas celui-ci.

---

## 11. Historique des migrations

| Date | Modale | Commit |
|---|---|---|
| 2026-04 | Création du design system | `5da2fdb` |
| 2026-04 | Inclusion dans /settings et /chat | `ed57570` |
| 2026-04 | requestModal | `6b5619a` |
| 2026-04 | passwordModal | `99b85c5` |
| 2026-04 | deleteAccountModal (tone-danger) | `69f860e` |
| 2026-04 | modalShortcutEdit | `a53708f` |
| 2026-04 | reviewSessionModal (size-parcours) | `be25620` |

---

*Dernière mise à jour : avril 2026 — créé suite à la session marathon Raya v2 du 22-26 avril.*
