# 📘 Guide de communication Claude ↔ Guillaume

**Date** : 19 avril 2026
**À lire en début de chaque session Claude**

---

## 🎯 Profil Guillaume

- Dirigeant de Couffrant Solar, pas développeur
- Comprend les concepts métier très bien, mais le jargon technique l'égare
- Préfère les analogies concrètes (téléphonique, humaine, physique) aux schémas techniques
- Valide toujours au sens avant de valider au détail

## ✅ Bonnes pratiques de réponse (validées 19/04/2026)

### Quand on pose un choix architectural
1. **Commencer par une analogie humaine simple** (2 façons, A et B, avec scénario concret)
2. **Expliquer les pièges** en situation réelle (pas en théorie)
3. **Tableau comparatif court** sur 4-5 critères max
4. **Recommandation claire** avec justification en 2-3 points
5. **Questions finales** : oui/non, pas 10 sous-questions

### Volume
- **Trop long** : décevoir la lecture, Guillaume saute → décisions mal prises
- **Trop court** : pas assez d'infos pour décider → Guillaume est perdu
- **Bon équilibre** : 1 écran-1 écran et demi par sujet, analogies + tableau + reco

### Vocabulaire à éviter
- "payload", "fetch", "endpoint", "middleware", "daemon", sauf si vraiment indispensable
- Sigles obscurs : "Option α", "Pattern XYZ"
- Utiliser plutôt : "la façon 1", "l'option que je recommande", des prénoms concrets (Arlène, Benoît)

### Vocabulaire autorisé (Guillaume comprend)
- Webhook (expliqué = "un appel automatique")
- Dashboard, base de données, serveur
- Nom des modèles Odoo (sale.order, etc.) car il les côtoie

### Validation par étape
- Une question architecturale = une réponse, pas 5 d'un coup
- Après chaque décision, résumer en 2 lignes ce qui est acté avant de passer à la suivante
- Garder la trace dans `raya_planning_v4.md` (annexes Q1, Q2, Q3, etc.)

## 🚫 Règles strictes héritées

- Jamais lancer de vectorisation sans "go" explicite de Guillaume
- Jamais toucher au Flutter (géré ailleurs)
- Tutoiement, français, concision
