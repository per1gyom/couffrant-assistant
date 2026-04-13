# Raya — Plan de Maintenance & Suivi

**Créé le : 13/04/2026** — Opus
**À activer : quand Raya sera en production avec clients**

---

## 1. MAINTENANCE RÉCURRENTE

### 1.1 Compatibilité Appareils (trimestrielle)

**Fréquence : tous les 3 mois** (janvier, avril, juillet, octobre)
**Déclencheur additionnel : sortie d'un nouveau modèle iPhone/Android flagship**

Checklist :
- [ ] Tester PWA sur les 2 derniers modèles iPhone (Safari)
- [ ] Tester PWA sur les 2 derniers modèles Android (Chrome)
- [ ] Vérifier safe-area-inset (notch, Dynamic Island, pliables)
- [ ] Vérifier les nouveaux formats d'écran (ratio, taille)
- [ ] Tester la saisie vocale (micro, permissions)
- [ ] Tester la lecture vocale (ElevenLabs, autoplay policies)
- [ ] Tester les notifications WhatsApp
- [ ] Vérifier les icônes PWA (taille, rendu, installation)
- [ ] Tester les gestes iOS/Android (swipe back, pull to refresh)

Sources à surveiller :
- Apple Developer : notes de version iOS/Safari
- Google Chrome : changelog Chrome mobile
- Can I Use : nouvelles API web supportées

### 1.2 Sécurité (mensuelle)

**Fréquence : tous les mois**

- [ ] Vérifier les CVE sur les dépendances Python (pip audit)
- [ ] Vérifier les CVE sur les dépendances JS (CDN marked.js, DOMPurify)
- [ ] Vérifier l'expiration des tokens OAuth (Microsoft, Gmail)
- [ ] Vérifier les certificats SSL (Railway gère automatiquement)
- [ ] Auditer les logs de connexion (tentatives échouées, comptes bloqués)
- [ ] Vérifier les rate limits et cooldowns

### 1.3 Performance (mensuelle)

**Fréquence : tous les mois**

- [ ] Temps de réponse moyen de Raya (objectif < 3s)
- [ ] Temps de chargement de la page chat (objectif < 2s)
- [ ] Consommation LLM (tokens/jour, coût/utilisateur)
- [ ] Taille de la base de données (aria_memory, mail_memory)
- [ ] Purge automatique des vieux mails (> 90 jours)
- [ ] Vérifier les fichiers temporaires /tmp (nettoyage)

### 1.4 Connecteurs Externes (hebdomadaire)

**Fréquence : chaque lundi matin (automatisé via /admin/diag)**

- [ ] Microsoft 365 : token valide
- [ ] Gmail : token valide
- [ ] Odoo : connexion active
- [ ] Twilio/WhatsApp : sandbox ou production active
- [ ] ElevenLabs : clé valide, quota restant

### 1.5 Mises à jour Dépendances (trimestrielle)

**Fréquence : tous les 3 mois**

- [ ] Anthropic SDK (nouvelles fonctionnalités, nouveaux modèles)
- [ ] FastAPI / Uvicorn
- [ ] Pillow, reportlab, openpyxl
- [ ] marked.js, DOMPurify (CDN)
- [ ] Python version (Railway build)
- [ ] PostgreSQL version

---

## 2. MONITORING AUTOMATISÉ (déjà en place)

| Composant | Seuil d'alerte | Canal |
|---|---|---|
| scheduler | 15 min inactivité | WhatsApp |
| webhook_microsoft | 60 min inactivité | WhatsApp |
| gmail_polling | 60 min inactivité | WhatsApp |
| proactivity_scan | 15 min inactivité | WhatsApp |
| Cooldown entre alertes | 6 heures | — |

Endpoint diagnostic : `GET /admin/diag` (panel admin → Actions → Tester les connecteurs)

---

## 3. ÉVOLUTIONS FUTURES À PLANIFIER

### Court terme (avant commercialisation)
- [ ] Migrer WhatsApp du sandbox vers un numéro de production
- [ ] Mettre en place un vrai logo/icône PWA (design professionnel)
- [ ] Domaine app.raya-ia.fr vérifié et SSL actif
- [ ] Tests de charge (combien d'utilisateurs simultanés ?)
- [ ] Plan de backup base de données (pg_dump automatique)
- [ ] RGPD : politique de confidentialité, droit à l'oubli

### Moyen terme (après premiers clients)
- [ ] Push notifications web (remplacer WhatsApp pour certaines alertes)
- [ ] Application native iOS/Android si PWA insuffisante
- [ ] CDN pour les assets statiques (performance)
- [ ] Multi-région Railway (EU + US si clients internationaux)
- [ ] Système de facturation automatisé (Stripe)

---

## 4. PROCÉDURE DE MISE À JOUR

1. **Toujours tester sur un tenant de test** avant de déployer en production
2. **Commits petits et ciblés** — un fichier par commit max pour éviter les timeouts
3. **Vérifier le diagnostic** après chaque déploiement (`/admin/diag`)
4. **Tester sur mobile** après chaque changement UI
5. **Documenter** dans `raya_session_state.md` chaque changement significatif

---

## 5. CONTACTS & ACCÈS

| Service | Console | Compte |
|---|---|---|
| Railway | railway.com | Guillaume |
| Twilio | console.twilio.com | Guillaume |
| Google Cloud | console.cloud.google.com | Guillaume |
| Squarespace DNS | account.squarespace.com | Guillaume |
| Anthropic | console.anthropic.com | Guillaume |
| OpenAI | platform.openai.com | Guillaume |
