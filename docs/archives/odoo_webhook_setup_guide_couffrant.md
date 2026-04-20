# Guide OpenFire — Création des règles webhook pour Raya

**Objectif :** configurer Odoo pour qu'il notifie Raya en temps réel à chaque création/modification/suppression sur certains modèles.

**Pilote (à créer en premier) :** `sale.order` seulement. Une fois validé sur ce modèle, on étendra aux autres.

**Durée estimée :** 10-15 minutes.

---

## 📋 Ce que tu vas créer

Pour le modèle `sale.order`, il faut créer **3 règles** :
1. Une sur la **création** d'un devis
2. Une sur la **modification** d'un devis
3. Une sur la **suppression** d'un devis

Toutes les 3 appellent la même action : envoyer un signal à Raya via son webhook.

---

## 🛠️ Prérequis côté OpenFire

Avant de commencer, il te faut :

1. **Activer le mode développeur** dans Odoo si ce n'est pas déjà fait :
   - Va dans **Paramètres → Développeur**
   - Clique sur **Activer le mode développeur**

2. **Accéder au module Base Automation** :
   - Menu principal → **Paramètres** → **Technique** → **Automatisation** → **Règles d'automatisation**
   - Si tu ne vois pas "Technique", c'est que le mode dev n'est pas activé

---

## 📝 Règle 1/3 — À la création d'un devis

### Étape 1 : Nouvelle règle

Clique sur **Créer** (ou le bouton `+`).

### Étape 2 : Remplir les champs

| Champ | Valeur |
|---|---|
| **Nom de la règle** | `Raya - sale.order - CREATE` |
| **Modèle** | `sale.order` (chercher "Devis de vente" ou "Commande client") |
| **Déclencheur** | `À la création` |
| **Action à faire** | `Exécuter du code Python` |

### Étape 3 : Coller le code Python

Dans le champ **Code Python**, colle exactement ceci :

```python
import urllib.request
import urllib.error
import json
import time
import secrets

# Secret webhook Raya pour Couffrant (configure dans Railway)
SECRET = "d2de2a35a86429fa36344c70f627afc7e61ae619ef77a7796fc576c47ba1a8b7"
URL = "https://app.raya-ia.fr/webhooks/odoo/record-changed"

for record in records:
    payload = json.dumps({
        "model": "sale.order",
        "record_id": record.id,
        "op": "create",
    }).encode("utf-8")

    req = urllib.request.Request(
        URL,
        data=payload,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-Webhook-Token": SECRET,
            "X-Webhook-Nonce": secrets.token_hex(16),
            "X-Webhook-Timestamp": str(int(time.time())),
        },
    )
    try:
        urllib.request.urlopen(req, timeout=5)
    except urllib.error.URLError:
        pass  # On n'empeche jamais la sauvegarde Odoo si Raya est down
```

### Étape 4 : Enregistrer et activer

Clique sur **Enregistrer**, puis coche **Actif**.

---

## 📝 Règle 2/3 — À la modification d'un devis

**Même procédure que la règle 1**, avec juste ces différences :

| Champ | Valeur |
|---|---|
| **Nom de la règle** | `Raya - sale.order - WRITE` |
| **Déclencheur** | `À la sauvegarde` (ou `À la mise à jour`) |

**Et dans le code Python**, remplace cette ligne :

```python
"op": "create",
```

par :

```python
"op": "write",
```

Tout le reste est identique. Enregistre et active.

---

## 📝 Règle 3/3 — À la suppression d'un devis

**Même procédure**, avec ces différences :

| Champ | Valeur |
|---|---|
| **Nom de la règle** | `Raya - sale.order - UNLINK` |
| **Déclencheur** | `À la suppression` (ou `À l'archivage`) |

Et dans le code Python, remplace :

```python
"op": "create",
```

par :

```python
"op": "unlink",
```

Enregistre et active.

---

## ✅ Test de validation

Une fois les 3 règles créées et actives :

1. **Dans Odoo** : crée un nouveau devis de test (peu importe le contenu, tu pourras le supprimer après).

2. **Dans le panel admin Raya** (`app.raya-ia.fr/admin/panel`) :
   - Clique sur le bouton **🔌 Webhooks** sur la ligne Odoo
   - Tu devrais voir :
     - **📥 Reçus 24h** : 1 (ou plus)
     - **✅ Traités 24h** : 1 (ou plus)
     - **❌ Erreurs 24h** : 0
     - Dans le tableau des derniers jobs : une ligne `sale.order` avec ton nouveau devis et un ✅

3. **Si tout est vert** : la première règle marche, on peut étendre aux autres modèles.

4. **Si erreur** : envoie-moi ce que tu vois dans le dashboard, je te diagnostique.

---

## 🚨 Points d'attention

- **Ne pas mettre de `raise` dans le code Python** : si Raya est down ou lent, le devis doit quand même se sauvegarder dans Odoo. Le `try/except` est là pour ça.
- **Le secret** : il est dans ce document en clair car c'est ton secret à toi. Ne le partage pas en dehors. Si tu le perds ou qu'il est compromis, on en génère un nouveau et on met à jour Railway.
- **Les 3 règles doivent être actives** simultanément pour couvrir toutes les cas (create + write + unlink).

---

## 🔜 Après validation du pilote `sale.order`

Une fois que le pilote tourne bien pendant 24h sans erreur, on étendra :

**Vague 2** (5 modèles) :
- `crm.lead`
- `mail.activity`
- `calendar.event`
- `res.partner`
- `account.move`

**Vague 3** (6 modèles intervention) :
- `of.planning.tour`
- `of.planning.task`
- `of.planning.intervention.template`
- `of.survey.answers`
- `of.survey.user_input.line`
- `of.custom.document`

Pour chaque modèle, même modèle de 3 règles (create/write/unlink), juste en remplaçant le nom du modèle dans le code.
