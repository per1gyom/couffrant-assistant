# Audit marché Raya & tarification — 30 avril 2026

**Statut :** Audit dur et prudent demandé par Guillaume au coucher
**Méthode :** Recherche web concurrents + analyse usage réel base
            couffrant_solar (table llm_usage, 20 jours de données)
**Objectif :** Donner un prix juste à Raya basé sur le marché réel,
              les coûts API mesurés, et la valeur ajoutée différenciante

---

## ⚠️ Disclaimer

Cet audit est volontairement **dur et prudent**. L'objectif n'est pas
de gonfler les chiffres pour rassurer, mais d'avoir une base
défendable. Les chiffres présentés sont conservateurs.

---

## 🎯 Partie 1 — Cartographie du marché

### A) Concurrents directs : "AI assistant pour la PME"

Aucun concurrent ne fait **exactement** ce que Raya fait. Mais
plusieurs catégories convergent vers ton territoire.

#### A1) Microsoft 365 Copilot (concurrent le plus dangereux)

C'est le concurrent le plus sérieux car :
- Intégration native M365 (Outlook, Teams, SharePoint, Excel, Word)
- Microsoft Graph = équivalent embryonnaire de ton graphe sémantique
- Push commercial massif (90% des Fortune 500 l'ont déjà)
- Wave 3 (mars 2026) ajoute Cowork, multi-modèles (Claude inclus)

**Tarification 2026** :
- Copilot Chat : gratuit avec M365 (web-grounded, PAS de données org)
- Copilot Pro : 20 $/user/mois (individuel, PAS de données org)
- M365 Copilot Business : 18 $/user/mois (promo jusqu'au 30/06/2026)
  puis 21 $/user/mois standard, MAIS nécessite M365 Business
  Standard (8 $) ou Premium (22 $) en plus
  → TCO réel : **26-43 $/user/mois**
- M365 Copilot Enterprise : 30 $/user/mois + base E3 (36 $) ou
  E5 (54 $)
  → TCO réel : **66-84 $/user/mois**
- M365 E7 Frontier : 99 $/user/mois (lancé 1er mai 2026)

**Augmentation tarifaire prévue 1er juillet 2026** : E3 +13%,
Business Standard +12%, etc. Microsoft pousse vers le haut.

**Forces** :
- Connecté nativement à tout ce que la PME utilise déjà
- Sécurité enterprise, conformité, IA d'OpenAI dernière génération
- Forrester ROI : 52% à 468% selon déploiement
- Microsoft annonce 11h/user/mois économisées en moyenne

**Faiblesses pour TES clients (TPE/PME françaises)** :
- Trop cher pour des artisans/TPE (66+ $/seat = 60+ €/seat)
- Beaucoup de fonctionnalités jamais utilisées
- Setup complexe (3-6 mois selon EPC Group)
- "11h économisées" = chiffre marketing, peu mesurable en vrai
- Anglais-first, support FR moyen
- Force la PME à monter sur E3/E5 (hausse coût base)

**Verdict** : c'est ton concurrent le plus sérieux pour les PME 50+
salariés qui ont déjà M365 Premium. Pour les TPE/artisans (10-30
salariés type Couffrant), c'est trop cher et trop complexe.

#### A2) AI CRM (Pipedrive, HubSpot, Zoho, Salesforce, etc.)

**Tarification observée 2026** :
- Capsule CRM : 18 $/user/mois (AI summaries GPT-based)
- Pipedrive : 14 $/user (entrée) à 79 $ (Professional avec AI)
- Freshsales : 9-19 $/user/mois (Freddy AI)
- Zoho CRM Plus : 40 $/user/mois (Zia AI inclus)
- HubSpot : free puis 50-90 $/user/mois (Breeze AI)
- Salesforce Einstein : 25-50 $/user (base) + add-ons 75 $
- monday CRM : visuel + AI Sales Agents (Lexi, Agent Factory)
- Microsoft Dynamics 365 Sales : 65 $/user/mois
- Sybill : 30 $/user/mois (spécialisé meetings)

**Forces** : matures, intégrations massives (1000+ connecteurs), AI
qui fait du scoring de leads, suggestions emails, prévisions deals.

**Faiblesses pour ton cas** :
- Tous sont **sales-centric** (CRM = pipeline commercial)
- Aucun ne fait de la pré-compta sérieuse
- Aucun ne fait l'extension de graphe sémantique métier
- AI = plugins greffés, pas une philosophie produit
- Setup demande paramétrage (à l'inverse de "Raya s'apprend")

**Verdict** : zone concurrentielle si tu te poses CRM. Mais Raya
n'est PAS un CRM. Ces outils ne font pas la pré-compta, le tri
mails métier, la mémoire conversationnelle profonde. Tu es à côté.

#### A3) Pré-compta française (Pennylane, Tiime, Dext, Indy)

**Pennylane (référence française)** :
- Plan Basique : 14 €/mois (1 user, factures only)
- Plan Essentiel : 49 €/mois (rapprochement bancaire IA, OCR justifs,
  prévisionnel)
- Plan Premium : 99-199 €/mois (analytics, comptabilité intégrée)
- Au-delà 15 salariés : devis sur mesure
- 350 000 entreprises clientes
- Plateforme Agréée DGFiP (PDP) pour la facture électronique 2026
- IA fait : OCR factures, classification mouvements bancaires
  apprenants, rapports financiers automatiques

**Ce que Pennylane fait DÉJÀ et que tu ne ferais PAS mieux** :
- Rapprochement bancaire automatique (apprenant)
- OCR factures + classification PCG
- Synchro bancaire native (Qonto, CIC, SG, Crédit Agricole...)
- Conformité PDP/Factur-X (obligation 2026)
- Collaboration expert-comptable temps réel

**Ce que Pennylane NE FAIT PAS** :
- Le tri mails / réponses automatiques
- Le graphe sémantique cross-domaines (mails + drive + RDV + compta)
- L'apprentissage de règles globales par exposition
- Les autres modules (audio capture, gestion projet, photos chantiers)

**Verdict critique** : Pennylane fait déjà 80-90% de ce que tu
imaginais pour ton module compta, en mieux et certifié PDP. **Si tu
te bats sur la pré-compta seule, tu perds.** Mais Raya ne se bat pas
là-dessus : la pré-compta n'est qu'UN module parmi N de Raya.

**Important nouveau** : un MCP Pennylane open-source est paru début
2026 et permet de connecter Pennylane à Claude Code. Ça veut dire
que ton `accounting_connector` (lecture/écriture Pennylane) est
**faisable techniquement** sans réinventer la roue.

#### A4) Outils "AI agents" généralistes (Zapier, Make, n8n + AI)

- Zapier AI : 20-50 $/mois pour automatiser des workflows
- Make.com : 9-30 $/mois (low-code automation + AI)
- n8n : self-hosted gratuit ou cloud 20 $/mois

**Forces** : flexibilité totale, 5000+ intégrations.

**Faiblesses** : pas de mémoire long terme, pas de graphe, pas
d'apprentissage adaptatif, demande des compétences techniques.

**Verdict** : pas concurrents directs. Plutôt des outils que des
techies utilisent pour bricoler un assistant maison.

### B) Conclusion de la cartographie

**Personne ne fait exactement ce que Raya fait.** Tu es dans une
case unique :

```
Raya = M365 Copilot (intégration multi-outils)
       + AI CRM (intelligence relationnelle)
       + Pennylane (pré-compta light)
       + Zapier (workflows custom)
       + un graphe sémantique unifié évolutif
       + une philosophie "Raya s'apprend"
       
Aucun concurrent ne combine les 5.
```

**MAIS** : chaque concurrent fait son sous-domaine **mieux** que toi
sur ce sous-domaine. Tu n'es pas le meilleur en CRM, ni en compta,
ni en intégration M365. Tu es le **seul à intégrer tout ensemble
avec une philosophie "personne qu'on apprend"**.

C'est à la fois ta force et ta faiblesse.

---

## 🎯 Partie 2 — Coûts d'API Raya réels (mesurés en base)

### Données mesurées en prod (table llm_usage)

20 jours d'usage réel sur couffrant_solar :

```
316 appels LLM total
8 020 672 tokens d'input total
109 209 tokens d'output total
Ratio input/output : 73:1 (typique RAG + graphe)
```

### Détail par modèle

| Modèle | Appels | Input total | Avg input/appel | Avg output/appel |
|--------|--------|-------------|----------------|----------------|
| Sonnet 4.6 | 154 | 3.87M | 25 123 | 190 |
| Opus 4.7 | 75 | 3.50M | 46 687 | 839 |
| Opus 4.6 | 38 | 0.65M | 17 110 | 446 |

### Détail par usage

| Usage | Appels | Avg input/appel |
|-------|--------|-----------------|
| Conversation principale | 223 | 33 568 tokens |
| Synthèse follow-up | 19 | 23 346 tokens |
| Synthèse session | 16 | 4 060 tokens |
| Audit Opus | 5 | 3 653 tokens |
| Optimisation règles | 2 | 3 095 tokens |
| Onboarding profil | 2 | 1 020 tokens |

### Coût API estimé (base tarifs Anthropic 2026)

Tarifs Anthropic (par million de tokens) :
- Sonnet 4.6 : 3 $ input / 15 $ output
- Opus 4.7 : 15 $ input / 75 $ output

**Calcul du coût réel sur 20 jours pour Couffrant Solar :**

```
Sonnet 4.6 :
  3.87M input × 3 $/M  =  11.61 $
  29k output × 15 $/M  =   0.44 $
  → Sous-total Sonnet : 12.05 $

Opus 4.7 :
  3.50M input × 15 $/M =  52.50 $
  63k output × 75 $/M  =   4.73 $
  → Sous-total Opus 4.7 : 57.23 $

Opus 4.6 :
  0.65M input × 15 $/M =   9.75 $
  17k output × 75 $/M  =   1.27 $
  → Sous-total Opus 4.6 : 11.02 $

TOTAL 20 jours = 80.30 $ → 76 €
```

### Extrapolation mensuelle

**Pour Couffrant Solar (1 user actif modéré, 316 appels/20j) :**
- ~474 appels/mois
- **~115-120 €/mois de coût API LLM**

⚠️ **C'est BEAUCOUP**. C'est 10x ce qu'un Pennylane Basique coûte
au client. Et c'est uniquement le coût LLM, sans le reste.

### Coûts additionnels à inclure

| Poste | Coût mensuel par tenant |
|-------|------------------------|
| **LLM (Claude API)** | 100-150 € selon usage |
| **Embeddings OpenAI** | 5-15 € (vectorisation) |
| **Hébergement Railway** | 20-40 € (postgres + app) |
| **Stockage Postgres** | dans Railway |
| **GeoLite2** | gratuit (license MaxMind) |
| **Microsoft Graph API** | gratuit (côté tenant) |
| **Google Drive API** | gratuit |
| **Webhooks** | dans Railway |
| **Sauvegardes Drive** | gratuit (dans le quota tenant) |
| **TOTAL coûts variables** | **125-205 €/mois par tenant** |

⚠️ **Et ça, c'est UN seul user actif.** Si Couffrant a 5 users actifs,
on peut tabler sur ~3-4x le coût LLM (pas du linéaire car cache
graphe partagé).

### Coûts cachés à long terme

- **Coûts fixes structurels** :
  - Domaine + DNS : 10 €/an
  - Service Account Drive : gratuit
  - Stockage backups : gratuit jusqu'à un certain volume
  - Monitoring (UptimeRobot) : 7-15 €/mois
  - Email transactionnel (SMTP) : 5-15 €/mois
  - Twilio (si SMS/WhatsApp activé) : 30-60 €/mois variable
  
- **Coûts de croissance** :
  - À 50 tenants actifs : 150 € de LLM × 50 = 7 500 €/mois
  - Postgres montera de plan, prévoir 200-500 €/mois en plus
  - Support client : si tu travailles seul, plafonné en volume

**Donc le coût marginal réel par tenant Couffrant-like est de
**150-220 €/mois** selon usage. Avec un facteur d'incertitude
de 30-50% à la hausse possible.

---

## 🎯 Partie 3 — Comparaison honnête fonctionnelle

### Ce que Raya FAIT MIEUX que le marché

✅ **Intégration multi-outils unifiée** (mails + drive + Odoo + Vesta
+ calendar + Teams + WhatsApp en un graphe). M365 Copilot le fait
chez Microsoft, mais pas en dehors. Aucun outil français équivalent.

✅ **Apprentissage de règles par exposition naturelle**. Pas de
configuration. Pennylane et Pipedrive ont leurs IA mais imposent
des configurations préalables.

✅ **Mémoire conversationnelle profonde et durable**. Aria_memory,
aria_rules, semantic_graph qui s'accumule. Aucun concurrent ne
prétend ça à ton niveau.

✅ **Multi-tenant avec isolation propre**. Tu as audité ça en
profondeur. Pas tous les concurrents le font (HubSpot Free a des
fuites cross-clients régulières).

✅ **Adaptable à un métier précis** (Couffrant = installateur PV).
Aucun produit ne fait Vesta + Odoo + photos chantier + tri mails
spécifique BTP.

✅ **Connectivité mails native multi-boîtes** (Outlook + Gmail
multiples). Pennylane n'a qu'un canal de réception facture.
M365 Copilot uniquement Outlook.

### Ce que Raya FAIT MOINS BIEN que le marché

❌ **Pré-compta** : Pennylane est plus mature. Tu auras 80% du
besoin en 5-7 semaines, mais Pennylane est PDP-certifié, pas toi.

❌ **CRM commercial** : HubSpot/Pipedrive ont 10 ans d'avance sur
les fonctionnalités sales (pipeline, scoring, sequences, signaux
d'achat).

❌ **Conformité fiscale** : aucune certification (PDP, FEC officiel,
etc.). Pour être un vrai outil compta, il faudrait des audits.

❌ **Sécurité enterprise** : pas de SOC 2, pas d'ISO 27001, pas de
certification HDS. M365 Copilot a tout ça.

❌ **Intégrations** : tu en as 6-8. HubSpot en a 1500. Zapier 5000.

❌ **Maturité** : ton produit a 4-5 semaines de vie. Pennylane 6 ans,
HubSpot 20 ans.

❌ **Scale** : tu peux supporter combien de tenants simultanés ?
50 ? 200 ? Pas testé. Les concurrents ont des dizaines de milliers.

❌ **Support** : tu travailles seul. Si un client a un problème
critique à 22h, tu réponds quand ?

❌ **Coût marginal élevé** : 150-220 €/mois par tenant. Pennylane
vend à 49 €/mois et reste profitable car ils ont mutualisé les
coûts sur 350k clients.

### Ce qui te rend UNIQUE (mais à preuver)

🎯 **La philosophie "Raya s'apprend"** est ton vrai différenciateur.
Mais il faut le prouver à grande échelle. Pour l'instant, démontré
sur 1 tenant (Couffrant) = 1 témoignage.

🎯 **Le graphe pérenne LLM-swappable** est ta vision long terme.
Si tu tiens 2-3 ans, ça devient un fossé concurrentiel. Mais à
court terme, c'est invisible commercialement.

🎯 **L'intégration métier sur-mesure**. Tu peux dire à un nouveau
prospect "je vais brancher ton Vesta/Odoo/SAP/etc., câbler ton tri
mails métier en 2 semaines". Aucun concurrent ne fait ça à ce prix.

---

## 🎯 Partie 4 — Tarification proposée (vision dure et prudente)

### Principes directeurs

1. **Couvrir tes coûts** d'abord. 150-220 €/mois de coûts marginaux
   doivent être largement remboursés.
2. **Ne pas dépasser** ce que le marché paie pour des solutions
   matures (Pennylane Premium = 199 €).
3. **Justifier la prime** par l'intégration + le sur-mesure.
4. **Prévoir l'évolution** : tu ne pourras pas baisser les prix
   plus tard, prévois un peu de marge.
5. **Tenir compte du coût de support** : tu travailles seul, chaque
   client = du temps réel.

### Scénario A — Tarification "TPE artisan" (cible Couffrant)

```
Forfait base tenant       : 200 € HT / mois
  Inclus : 1 user actif, mails + drive + calendar
            graphe sémantique, mémoire, tri mails de base
  
Par user supplémentaire   : +50 € HT / mois
  Jusqu'à 5 users : 200 + 4×50 = 400 € HT / mois pour 5 users
  
Module audio_capture      : +30 € HT / mois (si activé)
Module pdf_editor         : +20 € HT / mois (si activé)
Module image_editor       : +20 € HT / mois (si activé)
Module accounting_engine  : +50 € HT / mois (si activé, V1)
Module proactivity_engine : +30 € HT / mois (si activé)

Tenant Couffrant complet (5 users + tous modules) :
  400 + 150 = 550 € HT / mois
  (~6 600 € HT / an)
```

**Justification commerciale** :
- Un comptable facture 80-150 €/h, économiser 4-5h/mois = 400-750 €
- Embaucher une assistante = 2 000-3 000 €/mois charges incluses
- Raya à 550 € est ~80% moins cher qu'une assistante à temps partiel
- M365 Copilot Business à 18 $/user × 5 = 90 $ + base M365 = 200 €
  (mais pas d'intégration métier, pas de pré-compta)

### Scénario B — Tarification "PME 10-30 salariés"

```
Forfait base tenant       : 350 € HT / mois
  Inclus : 3 users actifs, intégrations multiples
  
Par user supplémentaire   : +60 € HT / mois
  
Modules : pareil que Scénario A

PME 15 users + tous modules :
  350 + 12×60 + 150 = 1 220 € HT / mois
  (~14 600 € HT / an)
```

### Scénario C — Tarification "module unique" (entry-level)

```
Pour un client qui ne veut tester qu'une fonctionnalité :

Module tri-mails seul     : 99 € HT / mois (1 user)
Module compta seul        : 149 € HT / mois (1 user)
Module audio capture      : 49 € HT / mois (1 user)

→ Conversion vers forfait complet quand le client est convaincu
```

### Comparaison avec le marché

| Solution | Prix typique 5 users | Ce qu'on a en plus | Ce qu'on a en moins |
|---|---|---|---|
| **Raya forfait Couffrant** | **550 € / mois** | Intégration métier, mémoire profonde, multi-modules | Conformité fiscale, scale |
| Pennylane Essentiel | 49-99 €/mois | Rien (1 user) | Pas multi-modules |
| Pennylane Premium 5 users | ~250-400 €/mois | PDP officiel, OCR mature | Pas de tri mails, pas de graphe métier |
| HubSpot Pro 5 users | 450 €/mois | Sales/marketing matures | Pas de pré-compta, pas de métier BTP |
| M365 Copilot Business 5 users | 100 $ + base 100 $ = 200 € | Intégration M365 native | Pas de pré-compta, pas de tri mails métier |
| Salesforce + Einstein | 250 €/user = 1250 €/mois 5 users | Enterprise mature | Cher, complexe, hors-sujet TPE |
| Embaucher assistante 50% | 1500-2000 €/mois | Humain, jugement | Coûte 3-4x plus cher |

### Verdict tarification

**🎯 Recommandation finale** :

Pour un tenant TPE-PME français type Couffrant Solar :
- **Forfait de base : 350-400 € HT / mois** (3 users + modules de base)
- **Modules optionnels : 30-50 € HT chacun**
- **User additionnel : 50-60 €**

Cible client : **400-700 € HT / mois** pour la PME moyenne.

Marges attendues :
```
Revenu mensuel par tenant  :   400-700 € HT
Coûts marginaux Anthropic +
Railway + OpenAI           :   150-250 €
Marge brute par tenant     :   250-450 € HT
```

À 20 tenants actifs : 5-9 k€/mois de marge brute = 60-108 k€/an
de marge brute. À 50 tenants : 12-22 k€/mois = 150-270 k€/an.

C'est suffisant pour vivre + investir dans le produit, sans être
extravagant.

---

## 🎯 Partie 5 — Positionnement honnête

### Ce que tu DOIS dire à un prospect

✅ "Raya est un assistant qui s'apprend à vivre avec votre entreprise"
✅ "On câble vos outils existants au lieu de vous forcer à migrer"
✅ "L'intelligence est dans le graphe, pas dans le LLM — donc
   l'investissement reste pérenne quand l'IA évolue"
✅ "Vous payez pour 1 outil qui en remplace 5-6"

### Ce que tu NE DOIS PAS dire

❌ "Raya remplace Pennylane / votre comptable" (faux, c'est de la
   pré-compta uniquement)
❌ "Raya est plus puissant que M365 Copilot" (pas vrai sur leur
   terrain Microsoft)
❌ "Raya est certifié X" (rien n'est certifié)
❌ "Raya scale à des milliers de tenants" (jamais testé)

### Ce qu'il faut PROUVER avant d'attaquer le marché

1. Une **vente test** réussie (Charlotte juillet va te servir)
2. Un **témoignage client** (Couffrant lui-même = toi, donc pas
   neutre — il faut un 2e témoin externe)
3. Une **estimation honnête du temps gagné** (mesurable, pas du
   marketing)
4. Une **résilience technique** (uptime, backups, sécurité)
5. Un **support défini** (heures de réponse garanties)

---

## 🎯 Partie 6 — Risques à anticiper

### Risque concurrentiel

🔴 **M365 Copilot Wave 4** (été 2026) va probablement intégrer
plus profondément l'extra-Microsoft. Si ils ouvrent leur Work IQ à
des connecteurs métier (Vesta, Odoo, Pennylane), tu perds une partie
de ton avantage.

🔴 **Pennylane peut sortir un assistant conversationnel** au-dessus
de leur compta. Ils ont les moyens financiers (350k clients).

🟡 **Anthropic peut sortir Claude pour Business** avec des
intégrations natives. Tu deviens redondant.

🟡 **Une startup française** peut copier ta vision avec plus de
moyens (équipe de 5-10, levée de fonds).

### Risque technique

🔴 **Le coût d'API peut exploser** si Anthropic monte ses prix.
Aujourd'hui Opus 4.7 = 15$/M input. Si ça passe à 25 ou 30, tu dois
soit absorber soit augmenter tes prix → friction client.

🟡 **Bug critique** non détecté qui fait fuiter des données entre
tenants → fin du produit.

🟡 **Limitation Postgres / Railway** à un certain volume → migration
forcée onéreuse.

### Risque commercial

🔴 **Tu travailles seul** — si tu tombes malade 2 semaines, le
support s'effondre. Prévois soit un assureur, soit un partenaire.

🟡 **Cible TPE = volume + petits prix** = beaucoup de support pour
peu de revenu. Cible PME = peu de support mais cycle de vente long.

🟡 **Pas de protection IP** : tu n'as pas déposé de marque "Raya",
pas de brevets, pas de SAS officielle.

---

## 🎯 Partie 7 — Prochaines étapes concrètes

### Avant de vendre la version d'essai

1. **Mesurer précisément** le coût API sur Couffrant en avril complet
   (pas juste 20 jours)
2. **Estimer** le coût d'usage typique pour Charlotte (juillet)
3. **Réparer** le bug des connexions invisibles (sinon perte de
   crédibilité produit)
4. **Documenter** un SLA support clair (heures, délais, escalades)
5. **Préparer** un kit commercial : pitch deck, démos vidéo,
   tarifs publics ou sur-mesure

### Pendant les 6 premiers mois

1. **Stabiliser** sur 3-5 tenants (toi + 2-4 amis/proches)
2. **Mesurer** les vrais coûts marginaux (pas extrapoler)
3. **Documenter** les vrais retours clients
4. **Affiner** la proposition de valeur et le pitch

### Après 6 mois

1. **Décider** : grand public ou niche métier (BTP, artisans, etc.)
2. **Évaluer** : seul ou s'associer ?
3. **Lever** ou rester bootstrap ?

---

## 🧠 Synthèse finale

```
Raya, en l'état (30/04/2026) :
  • Produit unique en son genre (philosophie "s'apprend")
  • Couvre 5-6 cas d'usage qu'aucun concurrent ne réunit
  • Coût marginal : 150-220 €/mois par tenant
  • Prix juste estimé : 350-700 €/mois selon taille tenant
  • Marge brute : 50-65% (sain pour SaaS)

Concurrents directs :
  • M365 Copilot : sérieux mais Microsoft-only et cher
  • Pennylane : excellent en compta seule, pas le reste
  • HubSpot/Pipedrive : sales-only, pas le métier
  • Personne ne fait l'intégration multi-domaines + apprentissage
    + métier que tu fais

Risques majeurs :
  • Bug connexions à réparer d'urgence
  • Tu travailles seul, pas de redondance
  • Pas de certification (PDP, ISO, SOC2)
  • Coût API peut exploser

Vision long terme :
  • Le graphe pérenne est l'actif. Le LLM est le consommable.
  • À 2-3 ans, ton fossé concurrentiel est inattaquable.
  • À condition de survivre les 12 premiers mois.
```

**Le prix juste pour Raya en 2026 est entre 350 et 700 € HT par
mois pour un tenant TPE/PME, avec modules optionnels en sus.**

**Plus bas, tu travailles à perte. Plus haut, tu sors du marché TPE.**

---

*Audit effectué le 30/04/2026 nuit, sur la base de :*
*- Recherches web sur 30+ concurrents AI CRM, M365 Copilot, Pennylane*
*- Analyse réelle de 316 appels LLM Anthropic en 20 jours*
*- Analyse multi-modèles : Sonnet 4.6, Opus 4.6, Opus 4.7*
*- Vision dure et prudente comme demandé par Guillaume*
*- À mettre à jour quand les premiers vrais clients seront vendus*
