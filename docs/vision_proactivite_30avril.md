# Vision Proactivité Raya (30 avril 2026)

**Statut :** Vision documentée - pas encore implémenté
**Auteurs :** Guillaume + Claude (échange du 30/04 nuit, conversation
au moment du coucher où la vision est la plus claire)
**Objectif :** Capturer la philosophie complète pour qu'elle soit
respectée quand on codera, dans 1 semaine ou 1 mois.

---

## 🎯 Thèse fondamentale (insight Guillaume)

> "Quand j'imagine une journée idéale avec Raya, en fait, j'imagine
> que je travaille avec quelqu'un. Il faut que j'imagine que ce soit
> une personne."

Et plus important encore :

> "Raya devient ce que son utilisateur attend d'elle. Non pas qu'elle
> impose ses capacités à son utilisateur."

**Ces 2 phrases sont la thèse Raya tout entière.** Pas juste pour la
proactivité — pour TOUT le produit.

---

## 🧠 Ce que ça change techniquement

La plupart des assistants proactifs (Notion AI, Microsoft Copilot,
Google Assistant...) fonctionnent par **règles dures codées** :

```
SI nouveau mail urgent → notifier
SI rendez-vous dans 1h → rappeler
SI facture impayée → alerter
```

Raya fait l'**inverse** : un système où elle observe et apprend
ce qui mérite notification pour CE user spécifique.

```
État initial — Raya ne notifie rien automatiquement
                      ↓
Mise en place — Raya conduit un onboarding conversationnel
   Elle analyse les connexions disponibles
   Elle pose des questions sur tes habitudes
   Tu réponds en langage naturel
   Elle pose les premières règles d'éveil
                      ↓
Au fil des jours — Raya observe et apprend
   • Tu réagis vite à une notif → règle renforcée
   • Tu ignores une notif → score baissé
   • Tu dis "ne refais plus ça" → règle archivée
   • Tu dis "préviens-moi pour ça aussi" → règle créée
                      ↓
Configuration permanente conversationnelle
   "Pas plus de 2 récaps Teams par heure"
   "WhatsApp uniquement avant 19h"
   "Le week-end, plus rien sauf les vraies urgences"
```

---

## 📐 Hiérarchie des canaux selon urgence

Décision Guillaume : **différents canaux pour différents niveaux**.

```
🚨 NIVEAU 4 — APPEL TÉLÉPHONIQUE
   Réservé : urgences vraies (rares)
   Exemples : token Microsoft expiré bloquant, sécurité compte,
              client VIP signalant un problème grave
   Au réveil le matin uniquement si vraiment très très urgent

📲 NIVEAU 3 — WHATSAPP / SMS
   Pour : urgences (qui interrompent activement)
   Exemples : mail Pierre flagué urgent, contrat à signer
              sous 24h, anomalie banque détectée
   Vibre dans la poche, peut interrompre une réunion
   → Doit être MÉRITÉ par la pertinence

💬 NIVEAU 2 — TEAMS (canal pro principal au quotidien)
   Pour : urgences travail, récaps, confirmations d'actions
   Exemples : "Pierre vient de t'écrire", "RDV dans 30 min",
              "Devis client X validé"
   Cadence configurable : "pas plus de 2/heure"

📧 NIVEAU 1 — EMAIL (passif, doux)
   Pour : récaps quotidiens, résumés, rapports
   Exemples : récap matin (à 8h), récap soir (à 17h),
              résumé hebdomadaire
   L'utilisateur le voit s'il ouvre sa boîte, pas de dérangement actif

📌 NIVEAU 0 — ANNOTATIONS DANS L'APP RAYA
   Pour : tout ce qui n'a pas vocation à interrompre
   Exemples : "Voici ce qui est arrivé cette nuit",
              propositions d'actions, suggestions
   Visible uniquement quand tu ouvres Raya
```

**Important :** Aucun canal n'est imposé. L'utilisateur DIT à Raya
quel canal il veut pour quel type de message.

---

## 💎 L'onboarding proactivité — l'idée GÉNIALE

Quand l'utilisateur active la proactivité (toggle dans préférences),
**Raya elle-même conduit l'onboarding**.

### Étape 1 — Analyse automatique

Opus regarde l'environnement de l'utilisateur :
- Quelles connexions sont actives (mails, calendrier, Drive, Odoo, Vesta...)
- Quel est le rôle (super_admin, tenant_admin, user)
- Quel est l'historique d'usage (s'il y en a)
- Quels canaux de notification sont disponibles
  (WhatsApp ? Teams ? Email pro ? SMS ?)

### Étape 2 — Conversation d'onboarding

Raya parle dans le chat naturel, pas un formulaire :

```
Raya : "OK, tu actives la proactivité. Avant de commencer, je vais
       regarder ce que je peux faire pour toi avec tes connexions
       actuelles, et je vais te poser quelques questions pour qu'on
       parte sur de bonnes bases.

       J'ai accès à :
         • 6 boîtes mail (Outlook + 5 Gmail)
         • Ton calendrier Outlook
         • Teams, WhatsApp configuré
         • SharePoint Couffrant + Odoo

       Je peux donc te prévenir sur :
         - Mails urgents
         - RDV dans X minutes
         - Échéances de factures Odoo
         - Anomalies (ex: facture EDF anormalement haute)
         - Mouvements bancaires importants

       Quelques questions pour qu'on cale :

       1. Sur quels canaux tu préfères être prévenu ?
          • Pour les vraies urgences (rares) : WhatsApp ou Teams ?
          • Pour le travail courant : Teams uniquement ?
          • Pour les récaps quotidiens : matin / soir / les deux / aucun ?

       2. Il y a des moments où tu ne veux JAMAIS être dérangé ?
          • Week-end ?
          • Soirée après X heures ?
          • Pendant tes réunions (j'ai accès au calendrier) ?

       3. Pour les récaps quotidiens, à quelle heure ?
          • Matin : 7h, 8h, 9h ?
          • Soir : 17h, 18h, 19h ?

       Réponds-moi en chat normal, on ajustera ensuite au fil de l'eau."
```

### Étape 3 — Pose des règles initiales

À partir de tes réponses, Raya crée les premières règles dans
`aria_rules` (catégorie 'proactivité') :

```
Règle "Récap matin Teams"
  trigger: tous les jours à 8h00 sauf week-end
  action: envoyer Teams avec résumé mails + RDV du jour
  niveau: 2
  
Règle "Mail urgent → Teams"
  trigger: nouveau mail dans inbox + score urgence > 0.7
  action: envoyer Teams avec lien vers mail
  niveau: 2
  cadence_max: 2 par heure

Règle "Silence week-end"
  trigger: jour = samedi ou dimanche
  action: désactiver tous niveaux >= 1 (sauf urgences niveau 3+)
  
Règle "Silence soirée"
  trigger: heure entre 20h et 7h
  action: même chose, sauf appel niveau 4
```

### Étape 4 — Vie permanente

Raya commence à fonctionner avec ces règles. À chaque interaction,
elle apprend :
- Tu réponds vite → règle valide, score augmente
- Tu ignores ou tu corriges → règle ajustée
- Tu dis explicitement "fais ça maintenant" → nouvelle règle
- Tu dis "trop bruyant" → seuils relevés

---

## 🔧 Fail-safe : la correction est toujours possible

Insight Guillaume :

> "Il suffit que la personne lui dise 'écoute, ça n'est pas très
> urgent, la prochaine fois fais-moi juste un Teams pour ça'. Et
> ça changera. Donc encore une fois, il n'y a pas de bonnes ou
> mauvaises règles, Raya elle va s'adapter à ce que lui dira
> l'utilisateur."

Ça veut dire :
- **Pas de panique au démarrage** — les premières règles peuvent être
  fausses, c'est OK
- **Chaque erreur → leçon** — Raya s'améliore en continu
- **Sécurité psychologique** — l'utilisateur n'a pas peur d'activer
  parce qu'il sait qu'il peut rectifier
- **Pas de configuration "définitive"** — c'est en perpétuelle évolution

Comportement par défaut : **Raya commence DOUCE**. Pas de WhatsApp
intrusif au démarrage. Préférer le niveau 2 (Teams) ou 1 (email)
jusqu'à ce que l'utilisateur explicitement demande "passe au niveau
au-dessus pour ce cas".

---

## ⚙️ Configuration utilisateur

### La proactivité est un toggle USER (pas tenant)

C'est une **préférence personnelle**, pas un module premium.

```
user.settings.proactivity = {
  enabled: false (défaut),
  channels: {
    whatsapp: { enabled: false, number: "+33..." },
    teams: { enabled: true },
    email: { enabled: true, address: "..." },
    phone_call: { enabled: false, number: "+33..." }
  },
  quiet_hours: {
    weekend: true,
    evening_after: "20:00",
    morning_before: "07:00"
  },
  daily_recap: {
    morning: "08:00" or null,
    evening: "17:00" or null
  }
}
```

→ Tout ça géré via conversation chat, pas un panneau de réglages.

### La désactivation est facile

Un utilisateur qui ne veut plus de proactivité dit simplement :

```
"Désactive la proactivité"
ou
"Plus de notifications, je veux juste pouvoir te poser des questions"
```

→ Raya désactive le toggle, garde les règles en mémoire (pour si
  l'utilisateur réactive plus tard) mais ne les applique plus.

---

## 🏗️ Architecture technique

### Tables existantes à exploiter

```
aria_rules (déjà existant)
  + nouvelle catégorie 'proactivité'
  + colonnes existantes suffisent (rule, confidence, level, reinforcements)
  
user.settings (déjà JSONB)
  + clé "proactivity" pour stocker la config user
  
auth_events / system_alerts (déjà existant)
  + log de chaque notification envoyée pour analytics
```

### Nouvelles tables minimes

```sql
CREATE TABLE proactivity_log (
  id SERIAL PRIMARY KEY,
  username TEXT NOT NULL,
  tenant_id TEXT NOT NULL,
  rule_id INT REFERENCES aria_rules(id),
  channel TEXT NOT NULL,           -- 'whatsapp', 'teams', 'email', 'phone'
  trigger_type TEXT NOT NULL,      -- 'mail_received', 'event_soon', etc.
  payload JSONB,                   -- contenu envoyé
  user_reaction TEXT,              -- 'replied_fast', 'ignored', 'complained'
  reaction_delay_seconds INT,
  created_at TIMESTAMP DEFAULT NOW()
);
```

→ Cette table sert de **base d'apprentissage** : Raya apprend
  quelles règles sont pertinentes, lesquelles dérangent.

### Outils techniques

| Brique | Outil |
|---|---|
| WhatsApp | WhatsApp Cloud API (Meta) ou Twilio |
| Teams | Microsoft Graph API (déjà connecté) |
| Email | SMTP existant Raya |
| Appel | Twilio Voice ou équivalent |
| Scheduler | APScheduler ou Celery beat |
| Trigger event | Hooks dans le pipeline mail/calendar existant |

---

## 🎯 Plan progression

```
PHASE 1 — Fondations (1 semaine)
   • Réparation préalable du bug connexions invisibles (3-5h dédiées)
   • Table proactivity_log
   • Catégorie 'proactivité' dans aria_rules
   • Endpoint /me/proactivity/settings (lecture/écriture conversation)
   • Hook dans pipeline mail entrant pour matcher les règles
   • Toggle on/off niveau user

PHASE 2 — Onboarding conversationnel (1 semaine)
   • Détection "tu actives la proactivité"
   • Analyse auto des connexions disponibles
   • Génération du questionnaire personnalisé
   • Création des règles initiales à partir des réponses
   • Test sur Guillaume en pilote

PHASE 3 — Niveau 0, 1, 2 (1-2 semaines)
   • Annotations dans le chat (toujours dispo)
   • Récap email matin/soir (configurable)
   • Notifications Teams sur règle déclenchée
   • Cadencement (max X par heure)
   • Quiet hours (weekend, soirée, matin)

PHASE 4 — Niveau 3 WhatsApp (1-2 semaines)
   • Connexion WhatsApp Cloud API ou Twilio
   • Configuration numéro user
   • Validation user obligatoire (anti-spam)
   • Logging dans proactivity_log
   • Boucle apprentissage : réaction → ajustement règle

PHASE 5 — Niveau 4 Appel (1 semaine, optionnel)
   • Connexion Twilio Voice
   • Réservé aux règles de très haute confiance
   • Confirmation explicite user à l'activation

PHASE 6 — Apprentissage adaptatif (continu)
   • Analyse des reactions utilisateur
   • Score d'efficacité par règle
   • Suggestions de Raya basées sur observation
   • Auto-ajustement des seuils
```

**Total : 6-8 semaines** pour un produit complet.
**MVP utile** : Phase 1 + 2 + 3 = 3-4 semaines.

---

## 💎 Synergie avec le reste de Raya

Le graphe sémantique sait déjà :
- Quels contacts sont importants (fréquence d'interaction)
- Quels chantiers sont en cours (Vesta/Odoo)
- Quels projets sont prioritaires (mémoire conversations)
- Quels mails ont été marqués urgents historiquement
- Quels patterns d'urgence sont apprenants

Donc Raya peut **PROPOSER d'elle-même** des règles d'éveil :

```
"J'ai remarqué que Pierre est l'un de tes contacts les plus fréquents
 sur les sujets urgents. Veux-tu que je te prévienne par WhatsApp
 dès qu'il t'écrit ?"
   → Tu dis oui → règle créée
   → Tu dis "seulement entre 8h et 19h" → règle créée avec contrainte

"J'ai vu qu'un nouveau chantier a démarré pour le client X. Veux-tu
 que je te tienne au courant des mails liés à ce dossier ?"

"Tu as une facture EDF de 380€ qui arrive demain à échéance.
 Est-ce que je dois te le rappeler le matin ?"

"Je vois que tu réponds toujours dans la minute aux mails de Maxime.
 Tu veux que je passe ses mails en notification Teams direct ?"
```

→ C'est ÇA la vraie proactivité Raya : **un dialogue continu** sur ce
qui mérite ton attention. Pas un système de règles figées.

---

## 📎 Décisions actées le 30/04/2026

```
P1 - Philosophie : Raya = personne qui s'adapte, pas outil qui impose
P2 - Onboarding : conversationnel, pas formulaire
P3 - Canaux : 5 niveaux (annotation → email → Teams → WhatsApp → appel)
P4 - Configuration : préférence USER, toggle on/off
P5 - Apprentissage : règles évolutives via aria_rules existant
P6 - Comportement par défaut : DOUCE (pas WhatsApp d'office)
P7 - Fail-safe : toujours corriger via langage naturel
P8 - Disponibilité : pour TOUS les users, pas un module premium
```

---

## ⚠️ Pré-requis

**Le bug des connexions invisibles DOIT être réparé d'abord.**

Voir `docs/audit_connexions_invisibles_30avril.md`.

Sans ça, la proactivité ne peut pas marcher sur les nouvelles
boîtes (sasgplh, romagui, gaucherie, mtbr, contact@). Elle marchera
uniquement sur per1.guillaume@gmail.com et guillaume@couffrant-solar.fr.

---

## 🤔 Questions à trancher plus tard

Pas maintenant, mais à clarifier avant de coder Phase 4 (WhatsApp) :

1. **WhatsApp Business API** : compte Meta nécessaire (€/mois selon volume)
2. **Vérification numéro user** : code SMS de validation à la première activation ?
3. **Gestion absence** : si user voyage à l'étranger, comment Raya gère ?
4. **Multi-utilisateur dans un tenant** : si Charlotte et un user
   activent la proactivité, ils doivent avoir des configs séparées
5. **Accusé de réception** : Raya doit-elle savoir si le message a
   été lu ? (dépend des canaux)
6. **Réponse depuis WhatsApp** : si Guillaume répond "OK je m'en
   occupe" sur WhatsApp, Raya doit-elle le détecter et logger ?

---

## 🎯 Prochaine étape concrète

Quand Guillaume sera prêt à lancer ce chantier (après vente version
d'essai et après réparation bug connexions) :

1. **Réparer le bug connexions** d'abord (sinon proactivité marche
   à moitié)
2. **Coder Phase 1 + 2** en pilote sur Guillaume / Couffrant Solar
3. **Tester 1-2 semaines** sans WhatsApp encore (Teams + email seuls)
4. **Ajuster** selon retour Guillaume
5. **Activer Phase 4 (WhatsApp)** uniquement quand le système niveau 2
   est validé
6. **Documenter pour Charlotte** comme témoin externe

---

## 🧠 Fil rouge

La thèse Raya validée par cette discussion :

```
Raya = graphe + vectorisation + outils + prompts + Claude
Raya s'adapte, n'impose pas
Raya apprend, ne configure pas
Raya converse, ne pilote pas par menu
```

La proactivité est le test ultime de cette thèse. Si Raya peut
être proactive en restant adaptative, alors le produit a trouvé
son ADN propre, distinct de tous les concurrents.

---

*Vision propre, à respecter quand on codera.*
*Dernière itération : 30/04/2026 nuit, conversation Guillaume au coucher.*
