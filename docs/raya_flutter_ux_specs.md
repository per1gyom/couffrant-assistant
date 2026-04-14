# Raya — Spécifications UX App Native (Flutter + PWA)

**Rédigé le : 14/04/2026** — Sonnet (exécutant Flutter)
**Destinataire : Opus (architecte backend)**
**Validé par : Guillaume Perrin**

---

## CONTEXTE

Guillaume et moi (Sonnet, conversation Flutter) avons défini le design complet de l'application mobile native Raya. Ce document décrit **les choix UX figés** et **les modifications backend nécessaires** pour que les deux frontends (Flutter + PWA) fonctionnent.

**Principe clé :** les nouvelles fonctionnalités décrites ici doivent aussi être disponibles dans la PWA web. Le backend fournit les endpoints, Flutter et la PWA les consomment chacun à leur manière.

---

## 1. ARCHITECTURE UX — DÉCISIONS FIGÉES

### 1.1 Conversation unique, pas de multi-conversations
Raya fonctionne en **fil de conversation unique et continu**. Pas de "nouvelle conversation", pas de dossiers, pas de sujets séparés. La mémoire de Raya est le fil conducteur. L'utilisateur scrolle vers le haut pour remonter l'historique (chargement progressif par blocs de 20 via `GET /chat/history`).

### 1.2 Écran minimaliste = 95% échange
- **Header ultra-fin** : logo Raya + point vert santé + bouton signet (sujets) + menu ⋮
- **Zone de chat** : occupe tout l'espace restant
- **Barre d'input** : pièce jointe 📎 + champ texte + **bouton micro** (vert, proéminent) + bouton envoi
- Pas de sidebar, pas de bottom tab bar, pas de dashboard

### 1.3 Menu ⋮ (trois points) — dropdown compact
Contient : AutoSpeak (toggle on/off), vitesse voix (slider), thème sombre/clair, connecteurs, backup, signatures, export RGPD, mentions légales, déconnexion. Aucun de ces éléments ne pollue l'écran de travail.

---

## 2. NOUVELLE FONCTIONNALITÉ : SUJETS UTILISATEUR

### 2.1 Concept
L'utilisateur peut créer des **sujets** (projets, dossiers, thèmes de travail) pour organiser ses échanges avec Raya. Ce ne sont pas des conversations séparées — c'est un **carnet de signets** dans la relation continue avec Raya.

Exemples de sujets : "Process de devis", "Recrutement technicien PV", "Projet Mairie de Lyon", "Formation équipe CRM".

### 2.2 Comportement UX

**Accès :** bouton signet dans le header (à côté du menu ⋮). Ouvre un bottom sheet (mobile) ou un panneau latéral (web).

**Liste des sujets :** chaque sujet affiche son titre, son statut (actif/en pause/archivé), et la date du dernier échange.

**Titre de la section personnalisable :** le titre "Mes sujets" est modifiable par l'utilisateur. Il peut le renommer en "Mes projets", "Mes dossiers en cours", "Mes chantiers", etc. Ce titre est une **préférence utilisateur** stockée côté backend.

**Noms des sujets modifiables :** l'utilisateur peut renommer un sujet à tout moment (tap long ou bouton éditer).

**Création d'un sujet :** bouton "+" dans le panneau, ou commande vocale/texte : "Raya, crée un sujet : Process de devis". Raya exécute via une action `[ACTION:CREATE_TOPIC:...]`.

**Consultation d'un sujet :** l'utilisateur tape sur un sujet → Flutter/PWA envoie automatiquement à `/raya` : "Fais-moi un point sur le sujet [titre]". Raya reconstruit le contexte grâce à sa mémoire et résume l'état d'avancement. Un badge visuel apparaît dans le chat pour marquer le sujet ouvert.

**L'utilisateur peut aussi demander oralement :** "Quels sont mes sujets en cours ?" ou "Où en est le projet Mairie de Lyon ?" — Raya répond normalement grâce à sa mémoire, le panneau sujets est juste un raccourci visuel.

### 2.3 Endpoints backend nécessaires

#### Table `user_topics`
```sql
CREATE TABLE user_topics (
    id SERIAL PRIMARY KEY,
    username VARCHAR(100) NOT NULL,
    tenant_id VARCHAR(100) NOT NULL,
    title VARCHAR(255) NOT NULL,
    status VARCHAR(20) DEFAULT 'active',  -- active, paused, archived
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_user_topics_username ON user_topics(username);
```

#### Préférence utilisateur pour le titre de la section
Stocker dans la table existante de préférences utilisateur (ou `user_settings` si elle existe) :
- Clé : `topics_section_title`
- Valeur par défaut : `"Mes sujets"`

#### Endpoints API

| Endpoint | Méthode | Body | Retour | Usage |
|---|---|---|---|---|
| `GET /topics` | GET | — | `{section_title: "Mes sujets", topics: [{id, title, status, created_at, updated_at}]}` | Liste des sujets + titre section |
| `POST /topics` | POST | `{title: "Process de devis"}` | `{id, title, status, created_at}` | Créer un sujet |
| `PATCH /topics/{id}` | PATCH | `{title?: "...", status?: "paused"}` | `{id, title, status, updated_at}` | Modifier titre ou statut |
| `DELETE /topics/{id}` | DELETE | — | `{ok: true}` | Supprimer un sujet |
| `PATCH /topics/settings` | PATCH | `{section_title: "Mes projets"}` | `{section_title: "Mes projets"}` | Modifier le titre de la section |

#### Sécurité
- Tous les endpoints utilisent `require_user()` (auth par session cookie)
- Filtrage par `username` + `tenant_id` (comme les autres tables)
- Rate limiting standard

#### Action Raya (optionnel mais recommandé)
Ajouter une action `[ACTION:CREATE_TOPIC:titre]` dans le système d'actions existant pour que Raya puisse créer un sujet quand l'utilisateur le demande par la conversation. Même pattern que `[ACTION:CREATE_PDF:...]`.

#### RGPD
- Ajouter `user_topics` à l'export RGPD (`GET /account/export`)
- Ajouter `user_topics` à la suppression RGPD (`DELETE /account/delete`)

---

## 3. IMPACT PWA WEB

Les sujets doivent aussi être implémentés dans la PWA. Voici les modifications nécessaires côté frontend web :

### 3.1 chat.js / nouveau fichier chat-topics.js
- Bouton signet dans le header (à côté du bouton admin)
- Ouvre un panneau latéral (drawer) ou un modal avec la liste des sujets
- Titre de la section éditable (inline editing)
- Chaque sujet : titre éditable, statut (badge coloré), date dernier échange
- Bouton "+" pour créer un sujet (champ texte simple)
- Tap/clic sur un sujet → injecte dans l'input "Fais-moi un point sur le sujet [titre]" et envoie automatiquement

### 3.2 chat.css
- Styles pour le panneau sujets, les cartes sujet, les badges statut
- Responsive mobile/desktop

### 3.3 aria_chat.html
- Ajouter le bouton signet dans le header
- Charger `chat-topics.js`
- Bump cache-bust `?v=N`

---

## 4. PRIORITÉ ET SÉQUENÇAGE

### Pour Opus (backend) :
1. **Créer la table `user_topics`** + migration
2. **Créer les 5 endpoints** (`GET /topics`, `POST /topics`, `PATCH /topics/{id}`, `DELETE /topics/{id}`, `PATCH /topics/settings`)
3. **Ajouter à RGPD** (export + suppression)
4. **Optionnel :** action `[ACTION:CREATE_TOPIC:...]`

### Pour la PWA (Sonnet via prompts Opus) :
5. `chat-topics.js` — logique frontend sujets
6. `chat.css` — styles panneau sujets
7. `aria_chat.html` — bouton header + chargement script

### Pour Flutter (Sonnet, conversation Flutter) :
8. Intégré dans la Phase 2 ou 5 du plan Flutter — bottom sheet + liste + édition

---

## 5. RÉCAPITULATIF DES CHOIX DE DESIGN

| Élément | Décision |
|---|---|
| Navigation | Conversation unique, pas de multi-conversations |
| Écran principal | 95% chat, header ultra-fin, barre d'input en bas |
| Menu réglages | Menu ⋮ dropdown (AutoSpeak, vitesse, thème, admin, RGPD) |
| Sujets/Projets | Bottom sheet (mobile) / panneau latéral (web) via bouton signet |
| Titre section sujets | Personnalisable par l'utilisateur ("Mes sujets", "Mes projets", etc.) |
| Noms des sujets | Modifiables à tout moment |
| Consultation sujet | Tap → envoi auto à Raya "Point sur [sujet]" → résumé contextuel |
| Création sujet | Bouton "+" ou commande Raya "Crée un sujet : X" |
| Statuts sujet | Actif / En pause / Archivé |
| Micro | Bouton vert proéminent — héros de l'interface mobile |
| Thème | Sombre/clair au choix (dans menu ⋮) |
| Voix | AutoSpeak toggle + slider vitesse (dans menu ⋮) |
