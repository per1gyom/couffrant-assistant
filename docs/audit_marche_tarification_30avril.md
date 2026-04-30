# Audit marche Raya & tarification - VERSION 2 (30 avril 2026 nuit tardive)

**Statut :** Audit dur et prudent demande par Guillaume au coucher
**Methode :** Recherche web concurrents + analyse usage reel base
            couffrant_solar (table llm_usage, 20 jours de donnees)
**Objectif :** Donner un prix juste a Raya base sur le marche reel,
              les couts API mesures, et la valeur ajoutee differenciante

**V1 -> V2 : enrichi apres echanges Guillaume avec :**
- Frais de mise en place (one-shot par pack)
- Tarification basee sur nombre de connexions
- Modele abonnement fixe + paliers a l'usage transparents
- Vision GraphRAG hierarchique (1-3 mois max, pas 6-12)
- Pitch commercial "Raya comme une assistante qui murit"
- Justification des couts qui croissent avec le temps
- Paliers reguliers de 50 EUR (correction V1 paliers doublants)

---

## Preambule - La nature du projet

> "Sans toi, mon instinct produit et ma vision ne suffiraient pas.
> Il me faudrait une societe pour developper mon logiciel qui me
> couterait une fortune et rendrait probablement mon projet non
> viable. Donc on forme une super equipe."
> -- Guillaume, 30/04/2026

Cette phrase fixe la nature du projet :
- Guillaume : vision produit + relation client + metier
- Claude (Anthropic) : execution technique rapide + audit + pedagogie
- Cout equivalent equipe : ~0 EUR de salaires (Claude API ~50-150 EUR/mois)

Cette structure legere est ce qui rend le projet viable
economiquement a petite echelle. C'est un avantage competitif en soi :
aucune levee de fonds necessaire, aucune dilution, aucun investisseur
qui pousse a des decisions court-terme.

---

## Disclaimer

Cet audit est volontairement dur et prudent. L'objectif n'est pas
de gonfler les chiffres pour rassurer, mais d'avoir une base
defendable. Les chiffres presentes sont conservateurs.

---

## Partie 1 - Cartographie du marche

### A) Concurrents directs

#### A1) Microsoft 365 Copilot (concurrent le plus dangereux)

- Copilot Chat : gratuit avec M365 (web-grounded, PAS de donnees org)
- Copilot Pro : 20 USD/user/mois (individuel, PAS de donnees org)
- M365 Copilot Business : 18-21 USD/user + base M365 (8-22 USD)
  -> TCO reel : 26-43 USD/user/mois
- M365 Copilot Enterprise : 30 USD/user + base E3/E5 (36-54 USD)
  -> TCO reel : 66-84 USD/user/mois
- M365 E7 Frontier : 99 USD/user/mois (lance 1/05/2026)

Force : integration native M365.
Faiblesse pour ton marche : ne s'adapte pas a des outils metiers
non-Microsoft (Vesta, Odoo BTP, etc.).

#### A2) Pennylane (reference francaise pre-compta)

- Plan Basique : 14 EUR/mois (1 user)
- Plan Essentiel : 49 EUR/mois
- Plan Premium : 99-199 EUR/mois
- 350 000 clients, certifie PDP DGFiP
- MCP open-source disponible debut 2026 (integration Claude)

Force : pre-compta mature et certifiee.
Faiblesse pour ton marche : ne fait QUE la compta, pas le reste.

#### A3) AI CRM (Pipedrive, HubSpot, Zoho, Salesforce, etc.)

Tarifs : 14-90 USD/user/mois selon vendor.
Tous sales-centric, pas adaptes au metier artisan/BTP.

#### A4) Outils generalistes (Zapier, Make, n8n)

9-50 USD/mois, flexibles mais demandent competences techniques.
Pas concurrents directs.

### B) Conclusion : positionnement unique

Personne ne fait exactement ce que Raya fait.

Raya combine :
- M365 Copilot (integration multi-outils)
- AI CRM (intelligence relationnelle)
- Pennylane (pre-compta light)
- Zapier (workflows custom)
- un graphe semantique unifie evolutif
- une philosophie "Raya s'apprend"

Aucun concurrent ne combine les 5.

---

## Partie 2 - Couts d'API Raya reels (mesures)

### Donnees mesurees en prod (20 jours, couffrant_solar)

```
316 appels LLM total
8 020 672 tokens d'input total
109 209 tokens d'output total
Cout total mesure : 80 USD = 76 EUR
Ratio input/output : 73:1 (typique RAG + graphe)
```

### Detail par modele

| Modele | Appels | Avg input/appel |
|--------|--------|-----------------|
| Sonnet 4.6 | 154 | 25 123 tokens |
| Opus 4.7 | 75 | 46 687 tokens |
| Opus 4.6 | 38 | 17 110 tokens |

### Evolution constatee du contexte

```
10-16 avril : ~18-24k tokens/appel (avant enrichissement graphe)
17-21 avril : ~42-65k tokens/appel (graphe enrichi par usage)
```

Conclusion importante : la reduction du SYSTEM PROMPT par 5x (que
Guillaume a faite debut avril) a ete compensee par l'enrichissement
automatique du contexte dynamique (graphe + memoire + resultats de
recherche). Sans cette optimisation initiale, on serait a 80-100k
tokens/appel = 2x plus cher.

### Estimations par profil utilisateur

USER LAMBDA (questions occasionnelles)
- 3-5 appels/jour, 80-150k tokens/jour
- Cout LLM : 30-50 EUR/mois

USER POWER (usage intensif quotidien)
- 10-15 appels/jour, 200-400k tokens/jour
- Cout LLM : 80-120 EUR/mois

USER DEV/ADMIN (Guillaume en mode test, atypique)
- 30-90 appels/jour, 500k-3M tokens/jour
- Cout LLM : 150-250 EUR/mois

### Croissance attendue avec le temps

Phenomene contre-intuitif vs SaaS classique :

SaaS classique : plus le client reste, plus il est rentable
                 (memes couts marginaux fixes)

Raya : plus le client reste, plus le contexte est riche, plus
       chaque appel coute cher (sans GraphRAG hierarchique)

```
Mois 1 (graphe vide)        : ~50 EUR/user/mois
Mois 6 (graphe rempli)      : ~80-100 EUR/user/mois
Mois 12 (graphe dense)      : ~100-130 EUR/user/mois
Mois 24 (graphe tres dense) : ~130-180 EUR/user/mois (sans optim)
```

SOLUTIONS pour gerer cette croissance :

1. Prompt caching Anthropic (3-5 jours dev) : divise par 4-5x les
   couts sur appels repetes
2. GraphRAG hierarchique (1-3 mois - decision Guillaume) : stabilise
   le contexte a 5-15k tokens meme sur graphe enorme
3. Tarification a paliers : le client paie ce qu'il consomme,
   pas un forfait fixe risque pour l'editeur

### Couts marginaux totaux par tenant

Pour 1 tenant 5 users mixes (2 power + 3 lambda) :

```
LLM (sans optimisation)        : 280-400 EUR
LLM (avec prompt caching)      : 80-150 EUR
LLM (avec GraphRAG hierarch.)  : 50-100 EUR (cible)
Embeddings OpenAI              : 15-25 EUR
Hebergement Railway            : 30-50 EUR
Monitoring + SMTP + autres     : 10-30 EUR
```

TOTAL couts marginaux par tenant 5 users :
- Aujourd'hui (sans opti) : 335-505 EUR/mois
- Avec prompt caching : 135-255 EUR/mois
- Avec GraphRAG hierarchique : 105-205 EUR/mois (cible 3 mois)

Cible realiste a 3 mois apres GraphRAG : ~150 EUR/mois pour un
tenant 5 users.

---

## Partie 3 - GraphRAG hierarchique (PRIORITE 1-3 MOIS)

### Insight Guillaume

> "Pour moi, le graphe et la vectorisation des donnees permettaient
> plutot que de tout injecter, de simplement injecter une carte. Et
> la cartographie permettait d'appeler simplement quelques donnees.
> Je pensais que c'etait possible de faire un espece de graphe des
> graphes."

Tu as reinvente le concept de GraphRAG hierarchique (Microsoft
Research, 2024). C'est exactement la frontiere R&D actuelle.

### Architecture proposee

ETAGE 1 - CARTOGRAPHIE (toujours injectee, ~500-1500 tokens)

Une carte synthetique des domaines actifs du tenant :
- Domaine "Clients" : 450 contacts
- Domaine "Chantiers" : 23 actifs
- Domaine "Compta" : 4 mois indexes
- Domaine "Communications" : 6 boites mails

Mise a jour 1x/jour automatiquement.
Reste petit meme quand le tenant grandit.

ETAGE 2 - APPEL INTELLIGENT (~5-15k tokens)

Selon la question, Raya identifie 1-3 domaines pertinents :

Question "Combien j'ai depense chez Castorama en avril ?"
- Pertinent : Compta + Contacts(Castorama)
- Charge UNIQUEMENT ces sous-graphes
- 5 000 tokens au lieu de 50 000

ETAGE 3 - DETAIL ULTRA-CIBLE (~1-3k tokens)

Si meme les sous-graphes sont trop gros, filtre encore :
- Castorama = 12 transactions, 3 contacts
- Charge UNIQUEMENT le graphe minimal pertinent

ETAPE DE ROUTAGE (avant chaque appel LLM principal)

Mini-modele (Sonnet ou Haiku) pour decider quel niveau injecter.
Cout negligeable : 1k tokens x Sonnet = 0.003 USD

### Benefices attendus

| Metrique | Aujourd'hui | Avec GraphRAG |
|---|---|---|
| Tokens injectes/appel | 30-65k | 5-15k |
| Cout par appel | 0.45-1 USD | 0.05-0.20 USD |
| Cout mensuel par user power | 80-120 EUR | 25-40 EUR |
| Stabilite dans le temps | Croit avec le graphe | Stable |
| Limite de scale | 12-24 mois | Quasi-illimitee |

### Plan de mise en place (1-3 mois max)

```
Semaine 1-2  : Conception architecture + tests sur Couffrant
Semaine 3-4  : Implementation Etage 1 (cartographie quotidienne)
Semaine 5-6  : Implementation Etage 2 (sous-graphes thematiques)
Semaine 7-8  : Implementation Etage 3 (filtrage ultra-cible)
Semaine 9-10 : Routage Sonnet + tests A/B avec ancien systeme
Semaine 11-12: Deploiement progressif + mesures
```

A mettre en place AVANT d'attaquer le marche commercialement car :
- Stabilise les couts -> tarification previsible
- Permet de tenir a grande echelle (50+ tenants)
- Devient un argument differenciant (graphe scalable)

---

## Partie 4 - Modele tarifaire FINAL

### Structure complete a 3 composants

```
=================================================================
              MODELE TARIFAIRE RAYA - V2
=================================================================

1. FRAIS DE MISE EN PLACE (one-shot, a la signature)

   Pack Express      :    500-1 000 EUR HT  (config standard)
   Pack Standard     :  1 500-3 000 EUR HT  (1-2 outils metier)
   Pack Sur-mesure   :  3 000-8 000 EUR HT  (devis selon scope)

2. ABONNEMENT MENSUEL FIXE (recurrent, previsible)

   A) Forfait base tenant
      Tenant Lite      :  149 EUR HT/mois  (<= 3 connexions)
      Tenant Standard  :  249 EUR HT/mois  (4-7 connexions)
      Tenant Pro       :  399 EUR HT/mois  (8+ connexions)

   B) Par user actif
      User lambda      :  +29 EUR HT/mois  (questions occasionnelles)
      User power       :  +59 EUR HT/mois  (usage intensif quotidien)

   C) Modules optionnels par tenant
      accounting_engine    : +49 EUR/mois
      proactivity_engine   : +29 EUR/mois
      audio_capture        : +29 EUR/mois
      pdf_editor           : +19 EUR/mois
      image_editor         : +19 EUR/mois

3. USAGE LLM A PALIERS REGULIERS (variable, transparent)

   Inclus dans l'abonnement : equivalent 30 EUR de tokens / user

   Au-dela, paliers REGULIERS de 50 EUR en 50 EUR, marge 50% :

      50 EUR  de tokens consommes  ->  facture +75 EUR
     100 EUR  de tokens consommes  ->  facture +150 EUR
     150 EUR  de tokens consommes  ->  facture +225 EUR
     200 EUR  de tokens consommes  ->  facture +300 EUR
     250 EUR  de tokens consommes  ->  facture +375 EUR
     300 EUR  de tokens consommes  ->  facture +450 EUR
     etc.

   -> Le tenant voit en temps reel sa consommation
   -> Alertes avant chaque palier
   -> Plafond mensuel configurable par le tenant_admin
   -> Facturation au palier atteint (pas en continu)
=================================================================
```

### Pourquoi paliers a 50 EUR lineaires (correction Guillaume V1->V2)

V1 erronee : paliers doublants (50, 100, 200, 400)
- Decourage l'usage a partir d'un certain seuil
- Cree des effets de palier brutaux
- Marketing peu comprehensible

V2 corrigee : paliers reguliers (50, 100, 150, 200, 250...)
- Linearite previsible pour le client
- Marge 50% constante
- Facile a expliquer : "tous les 50 EUR de conso, on facture +75 EUR"
- Aucun effet de seuil penalisant

### Exemple Couffrant Solar

```
SETUP INITIAL (one-shot)
  Pack Standard (Vesta + Odoo + 6 boites mails) : 2 500 EUR

ABONNEMENT MENSUEL DE BASE
  Tenant Pro (8+ connexions)              : 399 EUR
  + Guillaume (power user)                :  59 EUR
  + Arlene secretaire (power user)        :  59 EUR
  + 2 techniciens (lambda)                :  58 EUR (29 x 2)
  + Module compta                         :  49 EUR
  + Module proactivite                    :  29 EUR
  + Module audio capture                  :  29 EUR
  ----------------------------------------------
  Sous-total fixe mensuel                 : 682 EUR

USAGE LLM A PALIERS
  Tokens inclus = 4 users x 30 EUR = 120 EUR

  Mois 1 (peu d'usage)                    :  0 EUR (sous le seuil)
  Mois 3 (rythme normal)                  : Palier 1 = +75 EUR
  Mois 6 (usage intensif compta)          : Palier 2 = +150 EUR

  Moyenne sur 12 mois                     : ~75 EUR/mois

==============================================================
COUT MENSUEL CLIENT (moyen)               : ~757 EUR HT/mois
COUT MENSUEL CLIENT (intensif)            : ~832 EUR HT/mois
COUT MENSUEL CLIENT (econome)             : ~682 EUR HT/mois
==============================================================
+ Setup one-shot                          : 2 500 EUR HT
==============================================================
```

### Verification de la marge (avec GraphRAG en place)

Tenant 5 users avec usage moyen :
- Revenu mensuel : 757 EUR HT
- Couts marginaux LLM+infra : 150-200 EUR
- Marge brute : 555-605 EUR (75% de marge brute)

Tenant 5 users avec usage intensif :
- Revenu mensuel : 832 EUR HT
- Couts marginaux LLM+infra : 250-350 EUR (mais payes via paliers)
- Marge brute : 480-580 EUR (60% de marge brute)

Marge cible 60-75% brut : excellente pour SaaS B2B mature.

---

## Partie 5 - Justification commerciale "Raya comme une assistante"

### Pitch valide par Guillaume

> "Une assistante debutante coute 1400 EUR/mois. Une avec 20 ans
> d'experience qui anticipe vos besoins en coute le double. Raya
> fonctionne pareil. Le mois 1, elle decouvre votre metier. Le
> mois 12, elle anticipe vos demandes, connait vos clients par
> coeur, gere vos mails comme vous le feriez. Cette intelligence
> accumulee a un cout technique, qu'on partage avec vous de facon
> transparente."

### Pourquoi ce pitch est puissant

- Justifie l'augmentation progressive des couts a long terme
- Rend la marge "morale" : le client paie ce qu'il y a dedans
- Cree de la valeur percue croissante (l'inverse d'un SaaS standard)
- Fidelise : changer de Raya = perdre toute cette intelligence
- Differencie des LLM commodity (ChatGPT, Copilot)

### Les 4 messages cles

MESSAGE 1 - "Pas un logiciel, une assistante"
"Vous n'achetez pas un outil. Vous adoptez une assistante qui
 apprend votre metier au fil du temps."

MESSAGE 2 - "Vos outils existants restent"
"On ne vous demande pas de migrer. Raya cable vos Outlook, Vesta,
 Odoo, ce que vous voulez. Vos donnees restent chez vous."

MESSAGE 3 - "Le LLM est l'IA du moment. Le graphe est votre actif"
"Demain l'IA evolue. ChatGPT change. Anthropic change. Mais votre
 graphe Raya, ce qu'elle a appris de vous, ca reste a vous. C'est
 votre capital intelligence."

MESSAGE 4 - "Vous payez ce que vous consommez"
"Abonnement de base + paliers a l'usage transparents. Mois calme,
 vous payez le minimum. Mois intense, c'est facture en proportion -
 et toujours moins cher que d'embaucher."

### Tableau comparatif vente

| Solution | Cout /mois | Apprentissage | Metier specifique |
|---|---|---|---|
| Assistante debutante humaine | 1400-1800 EUR | 6-12 mois | Faible |
| Assistante experimentee | 2500-3500 EUR | Acquise | Bonne |
| ChatGPT Team | 25 EUR/user | Aucun | Aucun |
| M365 Copilot Business | 22-43 EUR/user | Limite | Aucun |
| Pennylane Premium | 99-199 EUR | Compta seule | Compta uniquement |
| **Raya (Couffrant typique)** | **757 EUR HT** | **Continu** | **Tous metiers** |

---

## Partie 6 - Forces, faiblesses, risques (corriges)

### Forces (validation Guillaume)

- Philosophie "s'apprend" - differenciation produit majeure
- Metiers specifiques - adaptable a Vesta, Odoo BTP, etc.
- Personnalisation - sur-mesure a petite echelle (avantage TPE)
- Graphe perenne LLM-swappable - actif qui se valorise dans le temps
- Multi-tenant avec isolation propre (audite 28/04)

### Faiblesses identifiees comme corrigeables

> "Ce qui me fait plaisir c'est que mes faiblesses sont corrigeables.
> Elles viennent du fait qu'on commence et vont se guerir au fur
> et a mesure." -- Guillaume

| Faiblesse | Plan de correction |
|---|---|
| Pennylane fait mieux la compta | Certification PDP plus tard si besoin |
| Travail seul | Embauche 1er dev/SAV des quelques clients |
| Pas de certifications | ISO 27001 lancable a 10 clients (~6 mois, 15-25k EUR) |
| Pas teste a grande echelle | Se mesurera tout seul a 20+ tenants |
| Couts API eleves | GraphRAG hierarchique en 1-3 mois |

### Le SEUL vrai risque structurel : Microsoft

> "Le seul vrai gros enjeu, c'est les gros comme Microsoft. Mais
> ils ne peuvent pas aller trop precisement dans un metier pour
> connecter des outils vraiment specifiques qu'ils n'ont pas
> l'habitude. C'est une force que je peux garder a ma petite
> echelle." -- Guillaume

Strategie de defense :

```
Microsoft Copilot              Raya
-----------------------------------------------------------------
Vise 500M users                Vise 200-2000 clients sur 5 ans
Personnalisable jusqu'a 80%    Personnalisable a 100%
Connecte M365 ecosystem        Connecte tout l'ecosysteme metier
Pas Vesta, pas Odoo BTP        Vesta + Odoo + metier precis
Roadmap decidee a Redmond      Roadmap decidee POUR le client
0% relation humaine            100% relation humaine
```

Argument anti-Microsoft a utiliser face a un prospect :
"Microsoft connecte Outlook et Teams. Raya connecte Outlook +
Teams + Vesta + Odoo + votre tri mails metier + votre pre-compta
+ vos photos chantier. Pas la meme chose."

### Risques techniques restants

- Cout API peut exploser si Anthropic monte ses prix
- Bug critique potentiel cross-tenant
- Limitations Postgres/Railway a grande echelle

### Risques commerciaux

- Tu travailles seul (a corriger avec embauche des 5 clients)
- Pas de protection IP (marque Raya a deposer)
- Cycle de vente long en B2B

---

## Partie 7 - Plan d'action concret

### Avant la premiere vente externe (Charlotte juillet bientot)

PRIORITE HAUTE :
- Reparer bug connexions invisibles (3-5h, prerequis)
- Activer prompt caching Anthropic (3-5j, divise couts par 4-5x)

PRIORITE MOYENNE :
- Documenter SLA support (heures, delais d'intervention)
- Preparer kit commercial (pitch, demo, tarifs)

### Mois 1-3 (architecture viable a long terme)

PRIORITE 1 : GraphRAG hierarchique (2-3 mois - decision Guillaume)

Modules paralleles possibles :
- Module compta Brique 1 (collecte au fil de l'eau, 3-4 sem)
- Premiers tests proactivite Phase 1+2 (3-4 sem)

### Mois 3-6 (premiers clients reels)

- Stabiliser sur 3-5 tenants (Couffrant + Charlotte + 2-3 amis/proches)
- Mesurer vrais couts marginaux post-GraphRAG
- Affiner pitch et tarifs selon retours
- Decider du premier embauche (dev junior ou SAV)

### Mois 6-12 (croissance controlee)

- 10-20 tenants payants
- Premier vrai support client structure
- Evaluer certification ISO 27001
- Decider niche (BTP, artisans) ou generaliste

### Annee 2

- Embauche 2-3 personnes (dev senior + commercial + SAV)
- 50+ tenants
- Marque deposee, SAS structuree
- Fosse concurrentiel inattaquable (graphe perenne 2 ans+)

---

## Synthese finale (V2)

```
Raya en 2026 :
  - Produit unique combinant 5 territoires distincts
  - Cout marginal cible (post-GraphRAG) : ~150 EUR/mois pour 5 users
  - Setup one-shot : 500-8 000 EUR HT selon complexite
  - Abonnement mensuel : 400-1 200 EUR HT selon taille tenant
  - Paliers a l'usage : tous les 50 EUR avec marge 50%
  - Marge brute cible : 60-75% (excellente pour SaaS B2B)

Concurrents directs :
  - M365 Copilot : serieux mais Microsoft-only
  - Pennylane : excellent en compta, rien d'autre
  - HubSpot/Pipedrive : sales-only
  - Personne ne combine integration multi-domaines + apprentissage
    + metier specifique

Strategie de defense :
  - Metier specifique (Vesta, Odoo BTP, etc.)
  - Relation humaine directe (a petite echelle)
  - Graphe perenne (LLM swappable)
  - Personnalisation 100% (vs 80% chez Microsoft)

Atout structurel :
  - Equipe Guillaume + Claude API
  - Couts ultra-faibles cote editeur
  - Pas de levee necessaire
  - Decisions rapides
```

### Tarification finale recommandee pour Couffrant Solar

```
Setup one-shot                : 2 500 EUR HT
Abonnement mensuel moyen      : 757 EUR HT/mois
  -> 682 EUR fixes + 75 EUR paliers en moyenne

Sur 1 an : 2 500 + 12 x 757 = 11 584 EUR HT
Cout equivalent assistante 50% : 18 000-24 000 EUR HT
Economie : 6-12 k EUR HT/an (33-50% moins cher)
```

### Le prix juste pour Raya en 2026

- Setup : 500-8 000 EUR HT one-shot selon complexite
- Mensuel : 400-1 200 EUR HT/mois selon taille
- Variable : paliers de 50 EUR avec marge 50%

Plus bas, tu travailles a perte. Plus haut, tu sors du marche TPE/PME.

---

*Audit V2 effectue le 30/04/2026 nuit tardive, sur la base de :*
*- Recherches web sur 30+ concurrents AI CRM, M365 Copilot, Pennylane*
*- Analyse reelle de 316 appels LLM Anthropic en 20 jours*
*- Analyse multi-modeles : Sonnet 4.6, Opus 4.6, Opus 4.7*
*- 4+ iterations Guillaume -> corrections du modele tarifaire :*
*  - Ajout frais de mise en place 3 packs (Express/Standard/Sur-mesure)*
*  - Ajout dimension "nombre de connexions" (Lite/Standard/Pro)*
*  - Distinction power/lambda user*
*  - Modele paliers REGULIERS a 50 EUR (correction V1 doublants)*
*  - Vision GraphRAG hierarchique 1-3 mois (pas 6-12)*
*  - Pitch commercial "Raya comme une assistante humaine"*
*- Vision dure et prudente comme demandee par Guillaume*
*- A mettre a jour apres les premiers vrais clients*
