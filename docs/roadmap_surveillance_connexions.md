# Roadmap — Surveillance des connexions OAuth

**Créé le 25 avril 2026** — demande Guillaume lors de la discussion sur
la refonte de la page Paramètres utilisateur.

## 🎯 Objectif

Éviter que Raya continue à fonctionner silencieusement avec une connexion
perdue (token expiré, mot de passe changé, OAuth révoqué côté provider)
sans que l'utilisateur s'en rende compte.

## 💡 Comportement attendu

Quand une connexion de l'utilisateur se perd :

1. **Détection** : Raya détecte l'échec d'appel API (401, 403, token
   expired, refresh failed, etc.)
2. **Alerte visible** : bannière rouge/orange dans le chat qui dit
   "Ta connexion Gmail est perdue. Tu vois plus tes mails. [Me reconnecter]"
3. **Notification** : éventuellement un email ou une notif push
4. **Dégradation transparente** : Raya doit dire clairement
   "Je ne peux plus lire tes mails Gmail depuis X heures" quand
   on lui pose une question qui dépend de cette connexion
5. **Reconnexion simple** : un clic pour relancer le flow OAuth,
   depuis la page Paramètres > Mes connexions

## 🛠️ Technique à envisager

### Détection des pertes
- Log centralisé des erreurs OAuth dans une table `connection_health`
- Champ `last_success_at`, `last_error_at`, `consecutive_failures`
- Job nocturne qui vérifie la validité de chaque token actif

### Alertes
- Flag en session `connection_warnings` qui se réinjecte dans le chat
- Badge rouge sur l'onglet "Mes connexions" des Paramètres
- Optionnel : notification push si l'user a activé le truc

### Self-healing
- Tentative automatique de refresh du token avant de déclarer la perte
- Backoff exponentiel avant d'alerter (pour éviter les faux positifs
  pendant une micro-coupure réseau)
