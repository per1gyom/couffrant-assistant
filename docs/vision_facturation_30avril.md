# Vision Facturation Raya — Modèle équitable et non-anxiogène

**Statut :** Vision documentée 30/04/2026 (idée Guillaume sous la douche)
**Auteurs :** Guillaume + Claude
**Objectif :** Capturer le modèle de facturation aux paliers avec
              report automatique, plafonds configurables, et UX
              non-anxiogène. À implémenter avant les premières ventes.

---

## 🎯 Insight Guillaume

> "Pour pas que ce soit anxiogène pour lui de passer un palier et
> puis perdre de l'argent, faire en sorte que les 40 € de tokens
> non utilisés dans un mois soient automatiquement recrédités au
> début du mois d'après. Faire quelque chose d'équitable et en même
> temps pas anxiogène, comme ça il n'aura pas peur d'utiliser, de
> dépasser un petit palier d'un moment et nous ça reste simple avec
> des facturations de palier en 50 € en 50 €."

C'est l'idée centrale : **le client ne perd JAMAIS d'argent en
passant un palier**. Tout surplus payé devient un crédit reporté.

---

## 💎 Le modèle en 3 piliers

### Pilier 1 — Paliers réguliers à 50 € (correction V2)

```
Tous les 50 € de tokens consommés, on facture +75 € (marge 50%) :

  50 € conso  → +75 €  facturé  (marge 25 €)
 100 € conso  → +150 € facturé  (marge 50 €)
 150 € conso  → +225 € facturé  (marge 75 €)
 200 € conso  → +300 € facturé  (marge 100 €)
 250 € conso  → +375 € facturé  (marge 125 €)
 300 € conso  → +450 € facturé  (marge 150 €)
 etc.
```

Avantages :
- Linéaire, prévisible
- Marge 50% constante
- Facile à expliquer
- Aucun effet de seuil pénalisant

### Pilier 2 — Report automatique du surplus payé

**Le mécanisme clé** :

```
EXEMPLE CONCRET :
  Mois N (avril) :
    • Le client consomme et atteint 60 € de tokens consommés
    • Il a passé le palier 50 € → facturé 75 € + 75 € (palier 100)
      = 150 € total au prochain palier
    • Il a payé pour 100 € de tokens, n'en a consommé que 60 €
    • → 40 € de tokens "achetés mais non utilisés"

  Mois N+1 (mai) :
    • Il commence avec un crédit reporté de 40 € (en valeur tokens)
    • Tant qu'il consomme dans ces 40 €, c'est 0 € de palier facturé
    • Une fois les 40 € grignotés, palier 50 € s'active
    • Et ainsi de suite

Résultat :
  Le client n'a JAMAIS perdu d'argent. 
  Le surplus payé est automatiquement reporté.
  Il peut "oser" utiliser sans peur du dépassement.
```

**Pourquoi c'est génial** :
- ✅ **Équitable** : le client paie ce qu'il consomme à terme
- ✅ **Non-anxiogène** : pas de peur de dépasser un palier
- ✅ **Simple côté éditeur** : facturation par paliers de 50 €,
     pas de centimes, pas de calculs micro
- ✅ **Différenciant commercialement** : aucun concurrent ne fait
     ça (Anthropic, OpenAI, Pennylane, etc. font du pay-as-you-go
     sans report)

### Pilier 3 — Plafonds configurables à 2 niveaux

#### Niveau TENANT (pilotage budget global)

Le tenant_admin peut définir :

```
Plafonds globaux :
  • Plafond mensuel : "Ma société ne dépasse pas 300 € de tokens"
  • Plafond hebdomadaire : "Max 100 € cette semaine"
  • Plafond journalier : "Max 30 € par jour" (optionnel)

Comportement à plafond atteint :
  → Notification au tenant_admin
  → Optionnel : blocage des appels jusqu'au cycle suivant
  → Optionnel : mode dégradé (Sonnet only au lieu d'Opus)
  → Configurable par le tenant_admin
```

#### Niveau USER (allocation par personne)

```
Pour chaque user, le tenant_admin peut définir :

  • Quota mensuel : "Pierre = 100 €/mois (compta intensive)"
  • Quota hebdomadaire : "Marie = 50 €/sem (commerciale)"
  • Mode illimité : "Guillaume tenant_admin = pas de plafond"
  • Heures autorisées : "Pierre = 8h-18h uniquement"

Comportement à quota atteint :
  → User voit son quota épuisé dans son interface
  → User peut "demander plus de crédit" à son admin (1 click)
  → L'admin reçoit une notification, peut accorder ou refuser
```

---

## 🎨 UX différenciée selon le rôle

### Pour USER LAMBDA — pourcentages, pas d'euros

L'utilisateur lambda **NE VOIT PAS** d'euros ou de tokens.
Juste des **pourcentages de consommation**.

```
┌─────────────────────────────────────────────┐
│ 🌟 Ma consommation Raya                     │
│                                             │
│ Aujourd'hui     ████░░░░░░░░░░  35%        │
│ Cette semaine   ████████░░░░░░  42%        │
│ Ce mois-ci      █████░░░░░░░░░  28%        │
│                                             │
│ 💡 Tu utilises Raya de manière équilibrée  │
│                                             │
│ [📩 Demander plus de crédit à mon admin]   │
└─────────────────────────────────────────────┘
```

Pourquoi : éviter de mettre la "tête à l'envers" avec des chiffres
techniques que l'utilisateur ne sait pas interpréter.

### Pour TENANT_ADMIN — chiffres complets pour piloter

Le tenant_admin **VOIT TOUT** : euros, paliers, estimations.

```
┌──────────────────────────────────────────────────────────┐
│ 💼 Consommation tenant — Couffrant Solar                 │
│                                                          │
│ Mois en cours (avril 2026)                              │
│ ████████░░░░░░░░░  Palier actuel : 150 €                │
│                                                          │
│ Tokens consommés  : 142 €                                │
│ Tokens reportés du mois précédent : 12 €                 │
│ Estimation fin de mois : ~280 €                          │
│                                                          │
│ Total estimé ce mois :                                   │
│   Abonnement de base : 682 €                             │
│   Paliers tokens     : ~300 €                            │
│   ─────────────────────────                              │
│   TOTAL ESTIMÉ       : ~982 €                            │
│                                                          │
│ ─────────────────────────────────────────────            │
│ Détail par user :                                        │
│                                                          │
│   👤 Guillaume       28%  ████░░░░░░  (illimité)         │
│   👤 Arlène          67%  ████████░░  ⚠️ approche quota  │
│   👤 Pierre          12%  █░░░░░░░░░  (50€/mois)         │
│   👤 Jean             5%  ░░░░░░░░░░  (50€/mois)         │
│                                                          │
│ [⚙️ Configurer plafonds] [📈 Détails] [💳 Paliers]       │
└──────────────────────────────────────────────────────────┘
```

Pourquoi : l'admin pilote le budget, il a besoin de chiffres
précis pour décider d'augmenter/baisser les quotas, anticiper la
facture, allouer entre users.

---

## 🏗️ Architecture technique proposée

### Tables à créer/étendre

```sql
-- Crédits reportés du mois précédent
CREATE TABLE token_credits_carryover (
  id SERIAL PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  username TEXT,                       -- NULL = crédit tenant global
  amount_eur NUMERIC(10,2) NOT NULL,   -- montant en euros
  origin_month DATE NOT NULL,          -- mois d'origine
  applied_month DATE,                  -- mois où c'est appliqué
  status TEXT CHECK (status IN ('pending', 'applied', 'expired')),
  created_at TIMESTAMP DEFAULT NOW()
);

-- Quotas configurés par le tenant_admin
CREATE TABLE token_quotas (
  id SERIAL PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  username TEXT,                       -- NULL = quota tenant global
  scope TEXT CHECK (scope IN ('daily', 'weekly', 'monthly')),
  amount_eur NUMERIC(10,2),            -- montant max ; NULL = illimité
  hard_limit BOOLEAN DEFAULT TRUE,     -- bloquer ou juste alerter
  fallback_mode TEXT,                  -- 'sonnet_only', 'block', NULL
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW()
);

-- Demandes de crédit user → admin
CREATE TABLE token_credit_requests (
  id SERIAL PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  username TEXT NOT NULL,              -- user qui demande
  reason TEXT,                         -- raison (optionnel)
  status TEXT CHECK (status IN ('pending', 'approved', 'rejected')),
  approved_by TEXT,                    -- tenant_admin qui valide
  approved_amount_eur NUMERIC(10,2),
  created_at TIMESTAMP DEFAULT NOW(),
  resolved_at TIMESTAMP
);

-- Historique des paliers atteints
CREATE TABLE billing_palier_log (
  id SERIAL PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  month DATE NOT NULL,
  palier_eur NUMERIC(10,2) NOT NULL,    -- 50, 100, 150...
  consumed_eur NUMERIC(10,2),           -- réellement consommé
  invoiced_eur NUMERIC(10,2),           -- facturé (palier × 1.5)
  carryover_to_next NUMERIC(10,2),      -- reporté au mois suivant
  created_at TIMESTAMP DEFAULT NOW()
);
```

### Algorithme de calcul mensuel

```python
# À la fin du mois, pour chaque tenant :

def cloturer_mois(tenant_id, month):
    # 1. Récupérer le crédit reporté du mois précédent
    carryover = get_carryover(tenant_id, month - 1 mois)  # ex: 40 €
    
    # 2. Récupérer la consommation réelle du mois
    consommation_reelle = get_token_cost(tenant_id, month)  # ex: 187 €
    
    # 3. Soustraire le crédit reporté
    consommation_facturable = max(0, consommation_reelle - carryover)
    # ex: 187 - 40 = 147 €
    
    # 4. Calculer le palier atteint
    palier_atteint = ceil(consommation_facturable / 50) * 50
    # ex: ceil(147/50) * 50 = 150 €
    
    # 5. Facturer (palier × 1.5 = +75 € par palier de 50 €)
    facture_palier = palier_atteint * 1.5
    # ex: 150 × 1.5 = 225 € facturés
    
    # 6. Calculer le report pour le mois suivant
    nouveau_carryover = palier_atteint - consommation_facturable
    # ex: 150 - 147 = 3 € reportés (pas grand-chose ce mois-ci)
    
    # MAIS si le mois précédent il avait reporté beaucoup :
    # ex: il avait acheté 100 € au palier mais consommé 60
    # → reporté 40 € sur ce mois
    # → ce mois il consomme 60, il utilise les 40 reportés
    # → reste 20 à facturer, palier 50 atteint, facturé 75 €
    # → reporté 30 € sur le mois suivant (50 acheté - 20 consommé)
    
    save_carryover(tenant_id, month, nouveau_carryover)
    save_palier_log(tenant_id, month, palier_atteint, ...)
```

### Endpoints à créer

```
GET  /api/billing/quota/me                    → user lambda voit ses %
GET  /api/billing/quota/tenant                → tenant_admin voit tout
POST /api/billing/quota/request_more          → user demande crédit
POST /api/billing/quota/grant                 → admin accorde
PUT  /api/billing/quota/user/{username}       → admin configure quota user
PUT  /api/billing/quota/tenant                → admin configure quota tenant
GET  /api/billing/palier/current              → admin voit palier en cours
GET  /api/billing/palier/estimate             → admin voit estimation fin de mois
GET  /api/billing/carryover                   → admin voit le report
```

---

## 🎯 Plan d'implémentation

### Phase 1 — Mesure et affichage (1 semaine)

- Étendre la page "Ma consommation" existante
- Affichage en pourcentages pour user lambda
- Affichage en euros + paliers pour tenant_admin
- Estimation fin de mois calculée en live

### Phase 2 — Quotas configurables (1 semaine)

- UI tenant_admin pour configurer quotas par user/par tenant
- Logique de blocage/alerte/fallback
- Notifications quand quota atteint

### Phase 3 — Paliers et report automatique (1 semaine)

- Calcul des paliers au fil de l'eau
- Job mensuel de clôture
- Application du report automatique
- Logging dans billing_palier_log

### Phase 4 — Demandes de crédit user → admin (3-5 jours)

- Bouton "demander plus de crédit"
- Notification admin (Teams + email)
- UI admin pour accorder/refuser
- Application immédiate

### Phase 5 — Facturation Stripe / SEPA (à venir)

- Génération de facture mensuelle automatique
- Intégration Stripe ou SEPA prélèvement
- Plus tard, après les premières ventes manuelles

**Total : 3-4 semaines pour le système complet**.

À mettre en place AVANT les premières ventes externes pour que :
- Charlotte (juillet) ait un système clair dès le début
- Pas de surprise pour les premiers clients
- Pas de stress côté éditeur (Guillaume) sur la facturation

---

## 💎 Pourquoi ce modèle est puissant

```
✅ ÉQUITABLE
   Le client ne perd jamais d'argent en passant un palier
   Le surplus payé est reporté

✅ NON-ANXIOGÈNE  
   L'utilisateur ose utiliser, ne flippe pas devant les paliers
   Pourcentages au lieu d'euros pour user lambda

✅ TRANSPARENT
   Le tenant_admin voit tout en chiffres précis
   Estimation fin de mois pour anticiper

✅ CONTRÔLABLE
   Plafonds configurables tenant + user
   Mode illimité possible pour les power users de confiance
   Demandes de crédit user → admin

✅ SIMPLE CÔTÉ ÉDITEUR
   Paliers de 50 € en 50 €, pas de centimes
   Facturation lisible, automatisable
   Marge 50% constante

✅ DIFFÉRENCIANT COMMERCIALEMENT
   Aucun concurrent ne fait ça (Anthropic, OpenAI, Pennylane,
   M365 Copilot, etc. font du pay-as-you-go sans report)
   Argument de vente : "Vous payez ce que vous consommez,
   et le surplus est toujours reporté"
```

---

## 📎 Décisions actées

```
F1 - Paliers : tous les 50 € avec marge 50% (75 € facturés / palier)
F2 - Report : surplus automatiquement reporté au mois suivant
F3 - Plafonds : configurables tenant + par user (3 scopes : J/S/M)
F4 - UX user : pourcentages uniquement (pas d'euros)
F5 - UX admin : chiffres complets + estimation fin de mois
F6 - Demandes : user peut demander, admin accorde en 1 click
F7 - Mode illimité : possible pour les power users de confiance
F8 - Fallback : Sonnet only ou blocage selon préférence admin
```

---

## ⚠️ Pré-requis

Avant l'implémentation :

1. **Réparer bug connexions invisibles** (3-5h)
2. **Activer prompt caching** (3-5j) — divise les coûts par 4-5x,
   donc les paliers sont atteints moins vite
3. **GraphRAG hiérarchique en place** (1-3 mois) — stabilise les
   coûts dans le temps, rend le modèle prévisible

Ce système de facturation sera **encore meilleur** une fois ces
3 prérequis en place : les coûts seront stables, prévisibles,
maîtrisés.

---

*Vision propre, à respecter quand on codera la facturation.*
*Dernière itération : 30/04/2026 nuit, idée Guillaume sous la douche.*
