# Audit — Connexions invisibles à Raya (30 avril 2026)

**Statut :** Bug critique identifié, à réparer
**Découvert :** 30/04/2026 nuit, à partir d'une conversation Guillaume ↔ Raya
**Effort estimé pour réparer :** 3-5h sur une session dédiée

---

## 🚨 Constat

Guillaume a connecté plusieurs nouvelles boîtes mail le 28 avril 2026.
Le 30 avril, quand Guillaume demande à Raya "à quoi tu as accès",
Raya répond qu'elle ne voit **que 2 boîtes mail**, alors que **6 sont
connectées** dans la base.

Extrait de la conversation Guillaume ↔ Raya (30/04 16:43) :

```
Guillaume : "Tu ne vois pas la boîte sasgplh@gmail.com ?"

Raya : "La réponse est claire : non, je ne vois pas la boîte 
       sasgplh@gmail.com. Aucun mail indexé en provenance ou à 
       destination de cette adresse. Elle n'est pas connectée à 
       mon système."
```

**Or, dans la table `tenant_connections` :**

| ID | Tool | Email | Status | Tokens OAuth | Créé |
|---|---|---|---|---|---|
| 4 | gmail | per1.guillaume@gmail.com | connected | ✅ | 15/04 |
| 7 | gmail | sasgplh@gmail.com | connected | ✅ | 28/04 |
| 8 | gmail | sci.romagui@gmail.com | connected | ✅ | 28/04 |
| 9 | gmail | sci.gaucherie@gmail.com | connected | ✅ | 28/04 |
| 10 | gmail | sci.mtbr@gmail.com | connected | ✅ | 28/04 |
| 6 | microsoft | guillaume@couffrant-solar.fr | connected | ✅ | 16/04 |
| 12 | outlook | Contact Couffrant Solar | connected | ✅ | 28/04 |

**6 connexions Gmail/Outlook supplémentaires sont actives mais Raya
les ignore complètement.**

---

## 🔍 Cause identifiée

Bug de **migration incomplète** entre 2 sources de vérité :

```
Avant 18 avril :
  Tokens stockés dans gmail_tokens (legacy, 1 boîte/user)

Après 18 avril :
  Tokens stockés dans tenant_connections (multi-boîtes)
  gmail_tokens marquée DEPRECATED dans database_schema.py

Mais en réalité :
  Le code de Raya (les outils que Claude utilise) lit ENCORE
  gmail_tokens dans 45 endroits différents.
  Donc quand Raya répond "à quoi tu as accès", elle interroge
  l'ancienne table et ne voit qu'1 ligne (per1.guillaume@gmail.com).
```

La table `gmail_tokens` ne contient qu'une seule ligne :
```
username | email                       | tenant_id        | access | updated
guillaume| per1.guillaume@gmail.com    | couffrant_solar  | ✅     | 13/04 15:19
```

**C'est exactement la liste de boîtes Gmail que Raya cite à
Guillaume.** Confirmation directe de la source du bug.

---

## 💥 Conséquences

| Conséquence | Impact |
|---|---|
| Raya ne reçoit AUCUN nouveau mail des 4 boîtes SCI | Tu rates les mails de sasgplh, romagui, gaucherie, mtbr |
| Raya ne reçoit AUCUN mail de contact@couffrant-solar.fr | Plus gros volume société manquant |
| Webhooks Microsoft non posés sur les nouvelles boîtes ? | À vérifier - si oui, double bug |
| Raya désinforme l'utilisateur avec confiance | Risque crédibilité produit |
| **La proactivité ne peut pas marcher** sur ces boîtes | Bloque le sujet 2 (proactivité) |
| Charlotte (juillet) connectera ses boîtes → même bug | Cascade sur tous les futurs tenants |

---

## 📋 Plan de réparation (à faire sur session dédiée)

### Étape 1 — Audit du code (~30 min)

- Lister TOUS les endroits qui lisent `gmail_tokens` (45 occurrences)
- Lister TOUS les endroits qui lisent `oauth_tokens` (legacy aussi)
- Lister TOUS les endroits qui lisent `tenant_connections`
- Identifier les divergences

Recherche ciblée :
```bash
grep -rn "gmail_tokens" app/
grep -rn "oauth_tokens WHERE.*provider" app/
grep -rn "tenant_connections" app/
```

### Étape 2 — Convergence vers `tenant_connections` (~2-3h)

Réécrire les helpers qui lisent les tokens :
- Créer `app/connection_token_manager.py` (probablement déjà partiel)
- Source unique de vérité = `tenant_connections`
- Les outils Raya lisent UNIQUEMENT cette table
- `gmail_tokens` et `oauth_tokens` deviennent vraiment legacy

Modules les plus probables à toucher :
- `app/routes/mail_gmail.py`
- `app/routes/aria_loaders.py`
- `app/routes/raya_helpers.py`
- `app/routes/raya_tool_executors.py`
- `app/token_manager.py`

### Étape 3 — Webhooks Microsoft / Gmail (~1h)

- Vérifier que `ensure_all_subscriptions` itère sur les 6 connexions
- Le commit M-W01 du 28/04 a été pensé pour ça mais à valider
- Pour chaque connexion connected sans webhook, en poser un
- Tester qu'un mail entrant déclenche bien le webhook

### Étape 4 — Endpoint diagnostic `/me/connections-status` (~30 min)

Créer un endpoint que Raya appelle quand on lui demande "à quoi
tu as accès". Il retourne en temps réel la liste exacte issue de
`tenant_connections` + les permissions par user.

Format de réponse :
```json
{
  "tenant_id": "couffrant_solar",
  "username": "guillaume",
  "mail_boxes": [
    {"email": "guillaume@couffrant-solar.fr", "provider": "outlook", "read": true, "write": true},
    {"email": "per1.guillaume@gmail.com", "provider": "gmail", "read": true, "write": true},
    {"email": "sasgplh@gmail.com", "provider": "gmail", "read": true, "write": true},
    ...
  ],
  "drive_connections": [...],
  "other_tools": [...]
}
```

### Étape 5 — Mise à jour du system prompt Raya (~15 min)

Le prompt système doit pointer Raya vers le bon endpoint et lui
interdire de "deviner" ses connexions à partir d'une autre source.

### Étape 6 — Tests bout-en-bout (~1h)

- Envoyer un mail test à chaque boîte
- Vérifier que Raya l'indexe et le voit
- Demander à Raya "à quoi tu as accès" et valider la réponse
- Tester sur un user juillet (Charlotte) après qu'elle ait
  connecté ses boîtes

---

## 🎯 Priorité

**Haute** mais pas critique pour la vente version d'essai (ça
peut attendre quelques jours). Cependant :

- **Bloque la proactivité** (sujet 2 du 30/04 nuit)
- **Bloque la pré-compta** (sujet du 30/04 nuit, qui dépend des mails)
- **Mauvaise impression utilisateur** quand Raya désinforme

À faire sur **une session dédiée propre**, pas en interleaving
avec d'autres sujets.

---

## 📎 Liens

- Discussion d'origine : conversation Guillaume ↔ Raya 30/04 16:43
- Fichier `database_schema.py` ligne 152 : la table gmail_tokens
  est marquée DEPRECATED depuis le 18/04
- Migration de tokens : voir `tenant_connections` créée commit
  d'avril sur la migration multi-tenant

---

*Bug à réparer. Documenté pour ne pas l'oublier.*
*Découvert le 30/04 nuit, en lien avec la discussion proactivité.*
