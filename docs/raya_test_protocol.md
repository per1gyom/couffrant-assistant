# Raya — Protocole de tests automatisés via Claude in Chrome

**Objectif** : permettre à Claude (Opus 4.7 ou +) de piloter Raya dans un navigateur pour exécuter des batteries de tests, détecter les régressions, et proposer des fixes — avec Guillaume en validation humaine à chaque étape sensible.

**Dernière mise à jour** : 17/04/2026

---

## 🎯 Principes

### Rôles
- **Claude** = pilote + observateur + analyste. Tape les prompts, lit les réponses, mesure, diagnostique, propose.
- **Guillaume** = superviseur. Ouvre la page Raya loguée, autorise chaque batterie, valide les actions sensibles, tranche sur les fixes proposés.

### Règles d'or
1. **Jamais d'action sensible sans validation humaine explicite** : envoi de vrai mail, création de vrai événement, suppression, modification Odoo en écriture.
2. **Tests idempotents** : les scénarios ne doivent laisser aucune trace permanente (ou des traces marquées `[TEST]`).
3. **Rate limit Raya = 120 req/h** : pas plus de 15-20 scénarios par batterie pour garder une marge.
4. **Compte test dédié en production = idéal plus tard** — pour l'instant, on teste sur le compte `guillaume` en évitant les actions destructrices.

---

## 🔧 Prérequis avant de lancer une batterie

1. **Claude in Chrome** installé et activé dans le navigateur de Guillaume.
2. **Onglet ouvert sur `https://app.raya-ia.fr/chat`**, utilisateur logué.
3. **DevTools fermés** (sinon le viewport est réduit et le scroll se comporte différemment).
4. **Vérifier le déploiement Railway à jour** (version du cache-bust JS visible dans les `<script src="...?v=XX">` du DOM).
5. **Guillaume donne l'ordre** : "Lance la batterie X" — sinon Claude ne pilote pas.

---

## 📋 Scénarios de test

Chaque scénario = **nom court**, **étapes**, **critères de succès**, **action Claude si échec**.

### Batterie CHAT-BASELINE (santé du chat, ~3 min)

#### CB-1 — Message simple court
- **Étapes** : taper "Bonjour Raya, comment vas-tu ?" → envoyer.
- **Succès** :
  - Loader ✦ s'affiche avec texte italique rotatif (pas les 3 anciens points).
  - La question remonte en haut du viewport (scroll auto déclenché).
  - Réponse en < 15 s.
  - Heure affichée correspond à l'heure locale Europe/Paris (± 1 min).
  - Aucun warning console navigateur.
- **Si échec** : capturer screenshot + console + rapport à Guillaume.

#### CB-2 — Message long (synthèse complexe)
- **Étapes** : taper "Fais-moi une synthèse de mes 3 derniers échanges importants, en croisant mails et Odoo" → envoyer.
- **Succès** :
  - Pas de message "Raya est momentanément surchargée" (= pas de timeout, le 90 s tient).
  - Réponse structurée avec tableau ou liste.
  - Si synthèse auto déclenchée : réponse cohérente, pas de données brutes visibles.
- **Si échec timeout** : attendre 90 s, observer si la réponse fantôme arrive (toast "Réponse récupérée ✨"). Rapport.

#### CB-3 — Actualisation après réponse
- **Étapes** : après CB-2, appuyer F5 (Cmd+R).
- **Succès** :
  - Les 2 derniers échanges (CB-1 + CB-2) réapparaissent à la bonne heure.
  - Pas de messages fantômes (ancienne erreur surchargée qui réapparaît).

---

### Batterie CARTES-MAIL (position + stabilité, ~2 min)

#### CM-1 — Rédaction mail → carte au bon endroit
- **Étapes** : taper "Rédige un mail à test@couffrant-solar.fr pour lui demander confirmation RDV lundi" → envoyer.
- **Succès** :
  - La carte mail apparaît **juste après la bulle Raya** qui propose la rédaction.
  - Pas en fin de chat.
  - Attributs DOM : `[data-action-id]` et `[data-conversation-id]` présents.

#### CM-2 — Refresh après génération carte
- **Étapes** : après CM-1, F5.
- **Succès** : la carte reste à la même position verticale qu'avant refresh (pas de téléportation en bas).

#### CM-3 — Annulation carte
- **Étapes** : cliquer le bouton "✕ Annuler" de la carte CM-1.
- **Succès** :
  - Boutons disparaissent.
  - Statut "⏹️ annulée" affiché.
  - Rafraîchir → carte toujours visible en historique avec statut final.

---

### Batterie GRAPHE (couche 3 cross-source, ~2 min)

#### GR-1 — Découverte Odoo préalable
- **Prérequis** : aller dans `/admin/panel`, onglet Sociétés, cliquer "🔍 Découvrir" sur la connexion Odoo. Attendre la fin (~30-60 s).
- **Succès** : status "découverte terminée, N modèles, M liens entité créés".

#### GR-2 — Lookup entité connue
- **Étapes** : revenir au chat, taper "Que sais-tu sur SARL DES MOINES ?" → envoyer.
- **Succès** :
  - Raya retourne du contexte cross-source : mentionne société + éventuels devis/factures/mails liés.
  - Pas de "je ne connais pas cette société".
- **Si échec** : screenshot + vérifier DB `entity_links` a bien été peuplée.

#### GR-3 — Lookup entité inconnue
- **Étapes** : taper "Que sais-tu sur SARL FANTÔME QUI N'EXISTE PAS ?" → envoyer.
- **Succès** : Raya répond sans halluciner, quelque chose comme "Je n'ai pas d'info sur cette société, tu veux que je cherche ailleurs ?".

---

### Batterie ODOO-ACTIONS (lecture uniquement, ~3 min)

#### OD-1 — Liste devis récents
- **Étapes** : "Liste mes 5 derniers devis Odoo" → envoyer.
- **Succès** :
  - Synthèse auto déclenchée (2e appel LLM).
  - Tableau formaté ou liste claire.
  - Pas de données brutes `📊` visibles.

#### OD-2 — Recherche contact par nom
- **Étapes** : "Trouve-moi le contact de Jean Dupont chez XYZ" (ajuster nom selon Odoo réel).
- **Succès** : info contact propre, pas de JSON Odoo visible.

**⚠️ Actions Odoo en écriture (create/update/note) — NON TESTÉES automatiquement.** Seulement avec validation Guillaume explicite dans une batterie séparée.

---

### Batterie UX-SCROLL (confort visuel, ~1 min)

#### UX-1 — Scroll auto à l'envoi
- **Étapes** : envoyer un message depuis le bas du chat (chat déjà scrollé en bas).
- **Succès** : la question s'affiche en haut du viewport pendant que Raya réfléchit. La réponse se déroule dessous, visible.

#### UX-2 — Loader rotation
- **Étapes** : envoyer un prompt qui prend ≥ 10 s.
- **Succès** : le texte italique change au moins 2× pendant la réflexion (ex: "Raya réfléchit…" → "Analyse du contexte…" → "Consultation de tes outils…"). Le sigle ✦ pulse en continu.

---

## 🚀 Procédure d'exécution

### Côté Guillaume
1. Ouvrir `app.raya-ia.fr/chat` dans Chrome, être logué.
2. Ouvrir une conversation avec Claude (cette interface ou claude.ai).
3. Donner l'ordre : "Lance la batterie CHAT-BASELINE sur Raya."

### Côté Claude
1. **Vérifier la version du chat déployée** (lire `<script src="chat-main.js?v=XX">` dans le DOM).
2. **Confirmer à Guillaume** le contexte avant de lancer : *"Je vais lancer CB-1, CB-2, CB-3. OK ?"*
3. **Exécuter chaque scénario** séquentiellement, avec pause 10 s entre chaque (pour laisser Raya respirer).
4. **Pour chaque scénario** :
   - Saisir le prompt
   - Attendre la réponse (ou l'erreur)
   - Observer DOM + timing
   - Noter succès/échec + preuves
5. **Rapport final** à Guillaume :
   - Tableau résumé (scénario / OK / KO / durée)
   - Détail des échecs avec screenshots ou extraits DOM
   - Proposition de fix pour chaque échec
6. **Attendre validation** de Guillaume avant d'appliquer un fix.

### En cas d'action sensible
Claude **s'arrête** et demande : *"Cette étape va déclencher [action concrète]. Je continue ?"*. Guillaume tape "oui" ou "non".

---

## 📊 Format de rapport

Chaque batterie produit un rapport type :

```
### Rapport batterie CHAT-BASELINE — 17/04/2026 16h30
Version chat : v=65 | Version admin : v=28

| ID   | Résultat | Durée | Note                            |
|------|----------|-------|---------------------------------|
| CB-1 | ✅       | 8 s   | Loader ✦ OK, scroll OK          |
| CB-2 | ✅       | 42 s  | Pas de timeout, synthèse propre |
| CB-3 | ⚠️       | —     | Heure affichée 16:30 au lieu de 18:30 |

Diagnostic CB-3 :
- parseServerTimestamp OK côté v=65 mais le backend retourne ts sans 'Z'
- (détail du diff proposé)

Fixes proposés : 1 — appliqué ? [en attente validation Guillaume]
```

---

## 🔄 Reprise dans une nouvelle conversation

Si le fil actuel est perdu, Guillaume colle le prompt suivant dans une nouvelle conversation :

```
Bonjour Claude. Projet Raya, Guillaume Perrin (Couffrant Solar).
Tutoiement, français, concis.
Lis docs/raya_session_state.md + docs/raya_changelog.md + docs/raya_test_protocol.md
sur per1gyom/couffrant-assistant main.

J'ai Claude in Chrome activé et l'onglet app.raya-ia.fr/chat ouvert et logué.
Lance la batterie [NOM_BATTERIE] selon le protocole.
```

Claude doit alors :
1. Lire les 3 docs
2. Confirmer la version déployée
3. Demander validation avant de démarrer
4. Suivre le protocole à la lettre

---

## 🌱 Évolutions futures

- **Batterie ACTIONS-WRITE** : tests d'actions destructives (SEND_MAIL réel, CREATEEVENT réel, ODOO_CREATE) sur un compte test dédié.
- **Batterie PERFORMANCE** : mesures systématiques du temps de réponse par tier (smart/deep), comparaison entre versions.
- **Batterie SECURITY** : tentatives d'injection prompt, accès cross-tenant — très utile avant chaque commercialisation.
- **Intégration CI** : à terme, ces batteries peuvent tourner en headless sur une branche preview Railway avant merge main.
- **Compte test `raya-qa@couffrant-solar.fr`** : données fake stables pour tests idempotents.

---

## 📌 Batteries disponibles (récap rapide)

| Batterie        | Durée  | Risque | Quand l'utiliser                                |
|-----------------|--------|--------|-------------------------------------------------|
| CHAT-BASELINE   | 3 min  | Nul    | Après chaque déploiement frontend chat          |
| CARTES-MAIL     | 2 min  | Nul    | Après chaque modif pending_actions / cartes     |
| GRAPHE          | 2 min  | Nul    | Après modif entity_links / couche 3             |
| ODOO-ACTIONS    | 3 min  | Nul*   | Après modif parseur actions Odoo                |
| UX-SCROLL       | 1 min  | Nul    | Après modif addMessage / addLoading / scroll    |

\* Lecture seule uniquement. Toute action en écriture = validation humaine.
