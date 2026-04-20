# Guide : configurer la boîte partagée `contact@couffrant-solar.fr`

**Pour qui** : Guillaume (pas expert Microsoft 365)
**Durée** : ~10 minutes
**Quand** : au moment où tu veux que Guillaume + Pierre aient accès à la boîte d'Arlène pour la dépanner en son absence.

---

## 🎯 Ce qu'on veut obtenir

Aujourd'hui : `contact@couffrant-solar.fr` est probablement un **compte utilisateur classique** auquel Arlène se connecte directement.

Cible : faire de `contact@couffrant-solar.fr` une **boîte aux lettres partagée** (Shared Mailbox) où :
- Arlène reste l'utilisatrice principale au quotidien
- Guillaume peut lire les mails et y répondre depuis son propre Outlook, **au nom de contact@**
- Pierre aussi (backup quand Arlène et Guillaume absents)
- Les réponses sont tracées dans la boîte partagée (visibles par tous)
- **Microsoft gère tout automatiquement** : pas de licence supplémentaire, apparition native dans Outlook des 3 personnes

---

## 📋 Étape 1 — Vérifier le type actuel de la boîte

1. Va sur **https://admin.microsoft.com** (Microsoft 365 Admin Center)
2. Connecte-toi avec `guillaume@couffrant-solar.fr` (il faut que tu sois **admin global** du tenant — à vérifier au passage)
3. Dans le menu de gauche : **Utilisateurs** → **Utilisateurs actifs**
4. Cherche `contact@couffrant-solar.fr`

**Si tu le trouves ici avec une licence Microsoft 365 attribuée** : c'est un compte utilisateur classique → il faut le convertir (étape 2).
**Si tu ne le trouves pas** : regarde dans **Équipes et groupes** → **Boîtes aux lettres partagées**. Si c'est là, c'est déjà une shared mailbox → passe directement à l'étape 3.


---

## 📋 Étape 2 — Convertir en boîte partagée (si c'est un compte utilisateur)

**Attention** : cette étape **déconnecte Arlène**. Préviens-la avant. Elle devra se reconnecter avec son propre compte Microsoft ensuite.

### Méthode simple (recommandée)

1. Dans **Admin Center** → **Utilisateurs** → **Utilisateurs actifs**
2. Clique sur `contact@couffrant-solar.fr`
3. Onglet **Courrier** → **Convertir en boîte aux lettres partagée** (si le bouton est visible)
4. Confirme la conversion
5. **Supprime la licence Microsoft 365** attribuée à ce compte (ce n'est plus nécessaire pour une shared mailbox < 50 Go → économie de ~10 €/mois)

### Méthode alternative (si le bouton n'apparaît pas)

Via Exchange Admin Center :
1. Va sur **https://admin.exchange.microsoft.com**
2. **Boîtes aux lettres** → clique sur `contact@couffrant-solar.fr`
3. **Autre** → **Convertir en boîte aux lettres partagée**

---

## 📋 Étape 3 — Ajouter Guillaume et Pierre comme membres

1. Dans **Admin Center** → **Équipes et groupes** → **Boîtes aux lettres partagées**
2. Clique sur `contact@couffrant-solar.fr`
3. Dans le panneau de droite, section **Membres** → **Modifier**
4. Clique **Ajouter des membres** et ajoute :
   - Arlène (qui l'utilisait déjà)
   - Guillaume (toi)
   - Pierre
5. Pour chaque membre, vérifie que les 3 permissions sont cochées :
   - ✅ **Lire et gérer** (Full Access) — lire les mails, les classer
   - ✅ **Envoyer en tant que** (Send As) — envoyer comme si c'était `contact@`
   - ✅ **Envoyer de la part de** (Send On Behalf) — optionnel, moins utile si Send As activé

6. Enregistre


---

## 📋 Étape 4 — Vérifier dans Outlook

**Délai** : jusqu'à 30 minutes pour que la config se propage.

### Sur Outlook Desktop (Windows/Mac)

1. Ferme et rouvre Outlook
2. Dans la liste des dossiers à gauche, tu devrais voir apparaître automatiquement **contact@couffrant-solar.fr** sous ta boîte personnelle
3. Tu peux dérouler et voir Boîte de réception, Envoyés, etc. de la shared mailbox

**Si la boîte n'apparaît pas automatiquement** :
- Outlook → **Fichier** → **Paramètres du compte** → **Paramètres du compte**
- Sélectionne ton compte → **Modifier** → **Autres paramètres** → onglet **Avancé** → **Ajouter** → saisir `contact@couffrant-solar.fr` → OK

### Sur Outlook Web (outlook.office.com)

1. Clique-droit sur ton nom dans la liste des dossiers (en haut à gauche)
2. **Ajouter un dossier partagé ou une boîte aux lettres**
3. Saisis `contact@couffrant-solar.fr`

### Envoyer un mail "as contact@"

Quand tu rédiges un mail, clique sur le champ **De** et choisis `contact@couffrant-solar.fr` au lieu de ta propre adresse. Le destinataire verra "contact@couffrant-solar.fr" comme expéditeur, pas ton nom.

Si le champ **De** n'apparaît pas :
- Desktop : menu **Options** → **Afficher les champs** → coche **De**
- Web : lors de la rédaction, clique sur les 3 points → **Afficher de**

---

## 📋 Étape 5 — Surveillance Raya des mails hors horaires

Une fois la shared mailbox en place et toi + Pierre ajoutés comme membres, Raya pourra :

1. **Détecter automatiquement** les mails reçus sur `contact@couffrant-solar.fr` via les scopes OAuth Microsoft étendus (à activer dans l'étape B)
2. **Identifier les mails "hors horaires d'Arlène"** : reçus en dehors des plages où elle travaille (Arlène 35h/semaine à 80%, soit des plages spécifiques à paramétrer)
3. **Te pousser une notification** dans Raya ou par email pour ces mails
4. **Permettre de répondre depuis ton interface Raya** en utilisant `contact@couffrant-solar.fr` comme expéditeur (grâce au scope `Mail.Send.Shared` côté OAuth)

**Ce que tu auras à faire côté Raya** (étape B, prochaine session) :
- Déclarer les horaires d'Arlène dans les paramètres du tenant
- Activer la surveillance sur `contact@couffrant-solar.fr` (une case à cocher dans l'UI quand elle sera faite)


---

## ❓ FAQ

**Q : Est-ce que ça coûte quelque chose ?**
R : Non. Une boîte aux lettres partagée < 50 Go est **gratuite** chez Microsoft 365. Tu économises même la licence que `contact@` utilisait avant (~10 €/mois). Seule contrainte : tous les membres (toi, Arlène, Pierre) doivent avoir une licence M365 standard.

**Q : Arlène va-t-elle perdre son historique de mails ?**
R : Non. Tout l'historique reste dans la boîte (c'est la même boîte, juste re-qualifiée en shared). Arlène continue à voir tous les mails d'avant la conversion.

**Q : Comment Arlène se connecte après la conversion ?**
R : Elle ne se connecte **plus directement** à `contact@couffrant-solar.fr`. Elle doit utiliser son **propre compte Microsoft** (si elle n'en a pas un distinct, il faut en créer un pour elle, ex: `arlene@couffrant-solar.fr`). Elle accède ensuite à la shared mailbox via Outlook comme décrit en étape 4.

**Q : Que se passe-t-il pour les règles de tri automatique qu'elle avait ?**
R : Les règles créées côté shared mailbox sont conservées. Les règles côté compte personnel d'Arlène (si elle en avait) sont perdues — à recréer côté son nouveau compte.

**Q : Et les contacts, calendriers associés ?**
R : Ils restent liés à la shared mailbox. Tout le monde y a accès via les permissions Full Access.

**Q : Si je veux retirer Pierre plus tard ?**
R : Tu retournes dans **Équipes et groupes** → **Boîtes aux lettres partagées** → section **Membres** → **Modifier**, tu retires Pierre. Effet immédiat.

**Q : Je n'arrive pas à trouver le bouton "Convertir en boîte partagée". Pourquoi ?**
R : Deux raisons possibles :
- Tu n'es pas **admin global** du tenant (vérifie ton rôle dans Admin Center → Rôles)
- Le bouton apparaît à des endroits différents selon la version de l'interface Microsoft. Méthode alternative : Exchange Admin Center (voir étape 2).

---

## 🆘 En cas de blocage

Si tu bloques à une étape, envoie-moi une capture d'écran de ce que tu vois dans Admin Center. On débloque ensemble.

Cas typiques :
- Bouton de conversion grisé → question de licence ou de permission
- Erreur "action non autorisée" → il manque le rôle Exchange Admin
- La boîte convertie n'apparaît pas dans "Boîtes partagées" → il faut attendre jusqu'à 30 minutes de propagation

## 🔗 Liens utiles Microsoft

- Documentation officielle shared mailbox : https://learn.microsoft.com/fr-fr/exchange/collaboration-exo/shared-mailboxes
- Admin Center : https://admin.microsoft.com
- Exchange Admin Center : https://admin.exchange.microsoft.com
- Outlook Web : https://outlook.office.com
