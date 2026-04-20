# Approches architecturales discutées puis abandonnées — 20 avril 2026

**Contexte** : ce document archive les pistes d'architecture Raya qui ont été discutées lors de la session du 20 avril 2026 au soir, puis écartées au profit d'une approche ultra-minimaliste (voir `docs/vision_architecture_raya.md`).

**Pourquoi les archiver et pas les supprimer ?**

Chacune de ces approches pourrait avoir du sens un jour — si l'usage révèle des dérives que la version minimaliste ne gère pas. Il est plus facile de ressortir une idée déjà réfléchie que de la réinventer. Si on doit ré-introduire des règles, on le fera en connaissance de cause, avec mention explicite dans ce fichier de la raison qui motive le retour.

**Règle d'or retenue** : il est toujours plus facile d'ajouter des contraintes que de les retirer. On démarre libéré.

---


## 1. Tags par source séparés (ODOO_SEMANTIC, DRIVE_SEMANTIC, MAIL_SEMANTIC...)

**Idée** : créer un tag dédié par source de données. Le prompt dit à Raya *"utilise ODOO_SEMANTIC pour les questions Odoo, DRIVE_SEMANTIC pour les fichiers, etc."*.

**Pourquoi c'était tentant** : structure claire, facile à tracer dans les logs, permet de restreindre les appels et donc les coûts.

**Pourquoi abandonné** : c'est du cloisonnement artificiel. Guillaume a correctement identifié que beaucoup de questions nécessitent des ponts entre sources (un mail récent peut modifier l'interprétation d'un devis Odoo, une photo du Drive peut confirmer l'avancement d'un chantier). Forcer le prompt à choisir UNE source risque de faire manquer des informations pertinentes. Le cloisonnement ampute l'intelligence.

**Condition de retour** : si l'usage montre que Raya fait trop d'appels inutiles et que les coûts explosent de manière significative (>10x l'estimation), on pourrait envisager un routeur plus fin qui exclut certaines sources. À ne considérer qu'après 3 mois de télémétrie réelle.

---

## 2. Détection codée du doute par Raya

**Idée** : après chaque réponse, un second appel LLM évalue *"suis-je sûre à >80% de ma réponse ?"*. Si non, Raya l'annonce explicitement *"je propose cette réponse mais j'ai un doute..."*.

**Pourquoi c'était tentant** : augmenterait la confiance utilisateur dans Raya, permettrait de déclencher automatiquement des vérifications supplémentaires.

**Pourquoi abandonné** : Opus sait déjà nuancer ses réponses quand il a un doute, sans qu'on ait besoin de lui coder. Ajouter un second appel LLM doublerait la latence et le coût, pour un bénéfice quasi-nul. C'est du micromanagement d'une capacité que le modèle maîtrise déjà.

**Condition de retour** : si on observe en usage que Raya affirme avec trop de certitude des choses fausses (hallucinations non signalées), envisager. Mais la première approche serait plutôt d'ajuster le prompt avec une simple phrase *"quand tu n'es pas sûre, dis-le"*, pas un second appel LLM.

---


## 3. Détecteur Haiku d'insatisfaction automatique

**Idée** : après chaque message utilisateur, un petit appel Haiku classifie *"signal d'insatisfaction sur la réponse précédente ? oui/non/neutre"*. Si oui, déclencher automatiquement un mode recovery.

**Pourquoi c'était tentant** : permettrait à Raya de se reprendre sans que Guillaume ait à le dire explicitement. *"Ah j'ai merdé, je creuse"* déclenché par détection.

**Pourquoi abandonné** : Opus lit naturellement le ton et les signaux d'insatisfaction dans la conversation. Il comprend *"non c'est pas ça"*, *"tu as oublié..."*, *"mais je te parlais de..."*. Pas besoin d'un détecteur séparé. De plus, un faux positif du détecteur serait gênant (Raya qui s'excuse alors que l'utilisateur était satisfait).

**Condition de retour** : si on observe que Opus rate systématiquement certains signaux implicites d'insatisfaction (*"hmm..."* ou reformulations multiples), envisager. Mais à nouveau, la première approche serait d'améliorer le prompt avant d'ajouter du code.

---

## 4. Mode recovery scripté avec étapes codées

**Idée** : quand insatisfaction détectée, séquence prédéfinie : (1) reconnaissance "j'ai merdé" (2) recherche élargie multi-hop +2 niveaux (3) reranking intensif top 30 (4) escalade Opus pour synthèse (5) stockage du pattern dans `aria_insights` pour ne pas reproduire.

**Pourquoi c'était tentant** : transformer les ratés en apprentissage structuré, avec une procédure garantie.

**Pourquoi abandonné** : ça force Raya à faire toujours la même chose en cas d'insatisfaction, même quand ce n'est pas nécessaire. Opus s'adapte mieux à chaque situation spécifique si on ne lui impose pas de pipeline. De plus, le *"stockage du pattern"* revient à essayer d'apprendre à la place d'Opus, alors que Couche 5 (apprentissage continu de préférences utilisateur) fait déjà ce travail de manière plus fine.

**Condition de retour** : si on observe que Raya rate les mêmes types de questions de manière répétée et n'apprend pas de ses erreurs, envisager. Mais préalablement, vérifier que Couche 5 capture bien ces feedbacks.

---

## 5. Règles conditionnelles dans le prompt (si X alors Y)

**Idée** : enrichir le prompt système avec des règles du type *"si la question mentionne un nom propre, utilise ODOO_CLIENT_360"* / *"si la question concerne un fichier, utilise DRIVE_SEMANTIC"* / *"après 3 échanges sans réponse, escalade à Opus"*.

**Pourquoi c'était tentant** : cadre clair, prévisibilité du comportement.

**Pourquoi abandonné** : plus on ajoute de règles conditionnelles, plus on contraint le raisonnement naturel d'Opus. Le modèle est entraîné pour interpréter les questions et choisir les bons outils. Lui imposer des règles revient à lui dire *"ne réfléchis pas, applique ce script"*. C'est une régression d'intelligence. C'est aussi le piège dans lequel on était déjà tombé dans des sessions précédentes et qu'on avait corrigé — Guillaume a explicitement signalé qu'on risquait d'y retourner.

**Condition de retour** : jamais systématiquement. Au cas par cas, uniquement si une dérive comportementale spécifique est observée et qu'aucune autre solution (amélioration de la mémoire, enrichissement du graphe, simple mention dans le prompt) ne suffit.

---


## 6. Routeur Sonnet (au lieu de Haiku)

**Idée** : utiliser Sonnet 4.6 au lieu de Haiku 4.5 pour le routage initial, pour avoir une meilleure précision de classification.

**Pourquoi c'était tentant** : +2 points de précision sur la classification métier/non-métier. Moins de faux négatifs sur les questions ambiguës.

**Pourquoi abandonné** : le différentiel de précision est marginal (~2 points) sur une tâche aussi cadrée qu'un routage binaire. Le différentiel de **latence** est énorme : Sonnet ajouterait ~1 seconde à chaque message avant même que la recherche ne commence. Raya passerait de "instantanée" à "y a un lag". Le coût serait aussi 30x plus élevé sur cette étape. Avec le biais "en cas de doute, métier = oui" côté Haiku, le risque de faux négatif est quasi nul.

**Condition de retour** : si on observe en usage que Haiku rate systématiquement certaines catégories de questions (classe en non-métier des questions qui auraient dû déclencher SEARCH), envisager. Préalablement : améliorer le prompt du routeur Haiku, c'est 10x moins cher que de passer à Sonnet.

---

## 7. Bâillonnage par sélection de sources dans le prompt

**Idée** : dans le prompt, énumérer précisément *"pour question de type A, tu as accès aux sources X et Y uniquement"*. Logique de whitelist par type de question.

**Pourquoi c'était tentant** : contrôle fin, traçabilité, économie de tokens.

**Pourquoi abandonné** : idem points 1 et 5, c'est du cloisonnement qui ampute l'intelligence. Guillaume a été très clair : *"le prompt ne doit pas sélectionner trop les données auquel elle a accès parce que je pense qu'on va lui limiter son intelligence"*. Position architecturale, pas optimisation locale.

**Condition de retour** : jamais en tant que principe par défaut. Potentiellement pour des cas de confidentialité stricte (ex: un utilisateur avec permissions limitées qui ne doit pas voir certaines sources), mais ça serait alors une gestion de permissions, pas un cloisonnement d'intelligence.

---

## 🗓️ Notes sur l'évolution future

Ce document est vivant. Si dans le futur on re-considère une de ces approches :

1. **Documenter la dérive observée** qui motive le retour (avec exemples concrets)
2. **Chiffrer l'impact** (combien de messages ratés, combien de temps perdu, coût réel)
3. **Tester la moindre intervention possible** (amélioration prompt > ajout d'une règle légère > ajout d'un détecteur codé)
4. **Retirer la contrainte à la première occasion** si la dérive se résout par d'autres moyens (amélioration du graphe, enrichissement de Couche 5, etc.)

## 🔗 Voir aussi

- `docs/vision_architecture_raya.md` — la vision minimaliste retenue
- `docs/architecture_connexions.md` — modèle mental des connexions
- `docs/raya_couche5_apprentissage_permanent.md` — spec Couche 5
