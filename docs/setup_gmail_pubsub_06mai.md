# Setup Gmail Pub/Sub — Guide pas-à-pas

**Date** : 06/05/2026
**Objectif** : activer les webhooks temps réel sur les 5 boîtes Gmail (per1.guillaume, GPLH, Romagui, Gaucherie, MTBR) via Google Cloud Pub/Sub.

**Temps estimé** : ~25 min côté Guillaume (GCP + Railway).

---

## 📋 Pré-requis

- Accès au projet Google Cloud qui héberge l'OAuth Gmail (`GMAIL_CLIENT_ID/SECRET`)
- Accès Railway en admin pour ajouter des variables d'environnement
- Le code Raya déploiement a déjà tout ce qu'il faut (cf commits 06/05).

---

## 🎯 Étape 1 — Activer Cloud Pub/Sub API (~2 min)

1. Aller sur https://console.cloud.google.com/
2. **Sélectionner le bon projet** en haut à gauche (celui qui héberge l'OAuth Gmail)
3. Dans la barre de recherche en haut, taper **"Pub/Sub API"**
4. Cliquer sur **"Cloud Pub/Sub API"** dans les résultats
5. Cliquer sur **"Activer"** (ou vérifier qu'elle est déjà activée)

---

## 🎯 Étape 2 — Créer le Topic Pub/Sub (~3 min)

1. Toujours dans la console GCP, aller dans le menu hamburger (☰) → **Pub/Sub** → **Topics**
2. Cliquer sur **"+ Créer un sujet"** (ou "+ Create topic")
3. **ID du sujet** : `gmail-watch-raya` (ou n'importe quel nom — note-le bien)
4. Laisser les options par défaut (chiffrement Google-managed, etc.)
5. Cliquer sur **"Créer"**

→ Le **nom complet** du topic sera affiché en haut, du type :
   `projects/<projet-id>/topics/gmail-watch-raya`

**📝 Note ce nom complet, on en a besoin à l'étape 5.**

---

## 🎯 Étape 3 — Donner les permissions IAM à Gmail (~3 min)

C'est l'étape critique. Sans ça, Gmail ne peut pas publier dans le topic.

1. Sur la page du topic que tu viens de créer, onglet **"PERMISSIONS"** (à droite ou en haut)
2. Cliquer sur **"+ Ajouter un compte principal"** (ou "Add principal")
3. Dans **"Nouveaux comptes principaux"**, coller exactement :
   ```
   gmail-api-push@system.gserviceaccount.com
   ```
4. Dans **"Sélectionner un rôle"**, chercher et choisir **"Pub/Sub Publisher"** (`roles/pubsub.publisher`)
5. Cliquer sur **"Enregistrer"**

⚠️ **Adresse exacte requise** : `gmail-api-push@system.gserviceaccount.com` — c'est le compte de service Gmail qui publie les notifications. Si tu te trompes, ça ne marchera pas.

---

## 🎯 Étape 4 — Créer la Subscription Push (~5 min)

1. Toujours dans Pub/Sub, aller dans **"Subscriptions"** (menu de gauche)
2. Cliquer sur **"+ Créer un abonnement"**
3. **ID de l'abonnement** : `gmail-watch-raya-push` (ou autre)
4. **Sujet Cloud Pub/Sub** : sélectionner le topic créé à l'étape 2
5. **Type de distribution** : choisir **"Push"** (très important, par défaut c'est "Pull")
6. **Point de terminaison** :
   ```
   https://app.raya-ia.fr/webhook/gmail/pubsub?token=<UN-SECRET-A-GENERER>
   ```
   - Remplacer `<UN-SECRET-A-GENERER>` par un secret aléatoire que tu génères ici :
     https://www.uuidgenerator.net/version4
     (n'importe quel UUID v4 fait l'affaire, du genre `7f8e9c2a-1b3d-4e5f-6789-abcdef123456`)
   - **📝 Note ce secret, on en a besoin à l'étape 5.**

7. **Authentification** : laisser **"Pas d'authentification"** (le secret dans l'URL suffit)
8. **Délai d'expiration de la livraison** : 10 secondes (par défaut)
9. **Délai d'expiration de l'abonnement** : "Jamais" (toggle)
10. Laisser le reste par défaut
11. Cliquer sur **"Créer"**

---

## 🎯 Étape 5 — Variables Railway (~5 min)

Aller sur https://railway.app/ → ton service Raya → onglet **"Variables"**

Ajouter ces 4 variables (clic sur "+ New variable" pour chacune) :

| Nom | Valeur |
|---|---|
| `GMAIL_PUBSUB_TOPIC` | `projects/<ton-projet-id>/topics/gmail-watch-raya` (le nom complet de l'étape 2) |
| `GMAIL_PUBSUB_VERIFICATION_TOKEN` | `<le-secret-genere-a-l-etape-4>` |
| `SCHEDULER_GMAIL_WATCH_RENEWAL_ENABLED` | `true` |
| `GMAIL_PUBSUB_TRIGGER_MODE` | `true` |

**Sauvegarder** (Railway auto-redéploye dans la foulée, ~3 min).

---

## 🎯 Étape 6 — Test (~5 min)

Une fois Railway re-déployé :

1. Aller sur le **panel admin** → onglet **Maintenance**
2. Carte **"📨 Webhooks temps reel Gmail (Pub/Sub)"**
3. Cliquer sur **"🔬 Test diagnostic conn=4 (per1.guillaume@gmail.com)"**

Lecture du résultat :
- `emailAddress` doit être `per1.guillaume@gmail.com`
- `Setup status` doit être `ok`
- `messagesTotal` doit être un nombre cohérent (~3000-4000)

→ Si tout est OK, **clique sur "🔄 Verifier / Creer les watches Gmail maintenant"** pour étendre aux 4 autres boîtes.

→ Si erreur, copie-moi le panneau noir et je débugge.

---

## 🔍 Que se passe-t-il après ?

- Le job `run_gmail_watch_renewal` tournera **chaque jour à 6h UTC** pour renouveler les watches qui expirent dans <2 jours
- Quand un mail arrive sur une boîte avec watch active, Gmail publie une notification Pub/Sub
- Pub/Sub POST sur `https://app.raya-ia.fr/webhook/gmail/pubsub?token=...`
- Notre endpoint (`webhook_gmail_pubsub.py`) déclenche un poll history immédiat → ingestion
- **Délai temps réel** : ~1-2 sec entre arrivée Gmail et ingestion Raya

---

## 🛡️ Sécurité

- Le secret `GMAIL_PUBSUB_VERIFICATION_TOKEN` empêche les requêtes spoofées (seul GCP qui connaît le secret peut POST)
- Le code vérifie ce token à chaque webhook reçu (ligne 168 de `webhook_gmail_pubsub.py`)
- Si tu suspectes une fuite : générer un nouveau secret + mettre à jour l'URL Push GCP + Railway env

---

## ❓ FAQ

**Q : Combien ça coûte ?**
A : Quasi gratuit. Pub/Sub a un free tier de 10 GB/mois. Tu vas envoyer ~quelques KB par notification, soit max ~1 MB/jour. = 0$/mois.

**Q : Et si le webhook est down quand un mail arrive ?**
A : Pub/Sub retry automatiquement pendant 7 jours. Aucun mail perdu.

**Q : Et si Pub/Sub manque un mail quand même ?**
A : Le job de polling 5 min reste actif comme filet de sécurité. Le polling adaptatif passé à 30 min hors heures ouvrées garantit qu'aucun mail n'est raté plus de 30 min.

**Q : Est-ce que je dois faire ça pour CHAQUE boîte ?**
A : Non. **Le setup GCP est fait UNE SEULE FOIS** pour tout le projet. Toutes les boîtes Gmail (et même les futures) utilisent le même topic. C'est le job `run_gmail_watch_renewal` qui appelle Gmail pour chaque boîte avec son token spécifique.
