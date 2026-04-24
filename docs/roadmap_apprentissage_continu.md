# Roadmap — Apprentissage continu des règles Raya

**Créé le 25 avril 2026** — discussion Guillaume sur l'ergonomie du
panel "Mes règles" face à la croissance attendue du nombre de règles.

## 🎯 Problème à résoudre

Avec la vectorisation et l'apprentissage continu, Raya va accumuler
des centaines voire des milliers de règles+infos par utilisateur.

Un utilisateur qui ouvre un écran contenant 300+ règles ne va rien
en faire : il sera noyé, ne connaît pas les termes exacts pour faire
une recherche pertinente, et n'aura ni le temps ni l'envie de trier.

Pire : les **nouvelles règles importantes passeront inaperçues** car
noyées dans la masse d'anciennes règles validées.

## 🧠 Principes du système d'apprentissage continu

### Principe 1 — Raya vient à l'utilisateur, pas l'inverse

L'utilisateur ne doit jamais avoir à fouiller. C'est Raya qui propose,
l'utilisateur qui valide ou corrige.

Mécanismes :
- **Interpellation dans le chat** tous les ~5-10 nouvelles règles :
  "J'ai appris quelques choses sur toi, on fait le point ?"
- **Bouton "Faisons le point"** → lance un parcours guidé, une règle
  à la fois, avec dialogue contextualisé sur chaque
- **Panel "Mes règles" ouvre par défaut sur "À revoir avec Raya"**,
  pas sur la liste complète

### Principe 2 — Toujours afficher le plus important en premier

Dans chaque vue, les règles sont triées par score d'importance :
`score = confidence × log(reinforcements + 1) × recency_factor`

L'utilisateur ne voit que les 5-7 premières par défaut. Les autres
sont masquées derrière un bouton "Voir tout".

### Principe 3 — Vectoriser l'intégralité du dialogue

Quand l'utilisateur édite ou supprime une règle, le dialogue Raya ↔
utilisateur doit être **intégralement vectorisé** (pas seulement la
réponse finale). Raison : c'est dans les explications que se trouve
la vraie intention de l'utilisateur, pas dans la règle finale.

Table à prévoir : `rule_dialogues` avec champs :
- `rule_id` (FK vers aria_rules)
- `dialogue_turns` (JSONB : liste de tours question Raya / réponse user)
- `dialogue_embedding` (vecteur pgvector pour recherche sémantique)
- `action_type` ('edit' / 'delete' / 'create' / 'pin')
- `timestamp`

### Principe 4 — Recherche sémantique, pas textuelle

L'utilisateur ne connaît pas les termes exacts des règles.
La recherche dans le panel doit utiliser l'embedding vectoriel
(pgvector), pas un ILIKE.

Exemple : l'utilisateur tape "réunions" → ça doit remonter
les règles qui parlent de "rendez-vous", "meetings", "RDV clients",
"visio", etc.

</content>

## 🎨 Impact sur l'UX

### Point d'entrée par défaut du panel "Mes règles"

Au lieu d'ouvrir sur la liste complète, le panel ouvre par défaut
sur une **section "À revoir avec Raya"** :

```
┌────────────────────────────────────────────────┐
│ ✨ À revoir avec Raya                          │
│                                                │
│ Raya a appris 8 nouvelles choses sur toi       │
│ depuis ta dernière visite.                     │
│                                                │
│   [ Faisons le point ensemble ]                │
└────────────────────────────────────────────────┘

Ensuite : liste des règles groupées par catégorie,
avec tri par importance et limitation par défaut.
```

### Mode "Faisons le point" — parcours guidé

Quand l'utilisateur clique sur "Faisons le point", une vue en
plein écran affiche les règles une par une, avec pour chaque :

- La règle telle que Raya l'a formulée
- Un petit contexte : "J'ai appris ça en analysant tes 3 derniers
  mails à Sophie" ou "Tu m'as dit ça lundi matin"
- 4 actions rapides :
- ✅ C'est bon, garde-la
- ✏️ Corrige-la
- 🗑️ Supprime-la
- ⏭️ Passe, on verra plus tard

Le parcours s'arrête automatiquement quand toutes les nouvelles règles ont été traitées, ou quand l'utilisateur clique "Pause".

### Dans le chat principal

Après un certain seuil (à définir : 5 ? 10 ?), Raya interpelle naturellement l'utilisateur :

> "Dis, j'ai capté quelques nouvelles habitudes chez toi cette semaine — 7 éléments. J'aimerais ton avis pour **confirmer ma compréhension** de ce que tu attends de moi. Tu as 2 minutes ?"

Avec un bouton intégré à la bulle : **\[ Faisons le point \]**

Le ton est important : Raya ne propose pas une conversation pour discuter, elle **demande une confirmation/validation**. C'est plus respectueux du temps de l'utilisateur et plus utile — on vient lui demander son avis sur des points précis, pas l'engager dans un dialogue ouvert.

Cette interpellation ne doit PAS être répétitive ni intrusive : maximum 1 fois par semaine, et seulement si le seuil est atteint.

## 📋 Implémentation technique à venir

### Backend

- Ajouter colonne `last_reviewed_at` sur `aria_rules`
- Calculer score d'importance côté serveur
- Endpoint `/memory/rules/new-since-last-visit` (retourne les règles
  non-reviewed)
- Endpoint `/memory/rules/review-session/start` + `/complete` pour
  tracer les parcours guidés
- Vectorisation complète des dialogues (table `rule_dialogues`)
- Recherche sémantique via pgvector

### Frontend
- Nouvelle section "À revoir" en tête du panel règles
- Mode parcours guidé (carousel plein écran)
- Tri par importance + limitation 5-7 items par groupe
- Bannière d'interpellation dans le chat (conditionnelle)

### Quand l'implémenter
Pas urgent tant qu'il y a moins de ~100 règles par utilisateur.
Devient critique au-delà de 150-200 règles. Aujourd'hui Guillaume
est à 134, donc on approche du seuil.

**Priorité** : à faire avant l'ouverture à des utilisateurs tiers,
sinon leur première expérience sera un mur de règles incompréhensible.
</content>
