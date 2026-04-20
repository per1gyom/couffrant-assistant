# 🎯 Étape A finale — Cause racine identifiée

**Date** : 19 avril 2026, 19h05
**Run analysé** : #8 (test avec troncature 5000 chars)

---

## ✅ Diagnostic COMPLET

Les 3 modèles qui plantaient à chaque scan sont cassés par **3 champs computed spécifiques côté OpenFire** :

| Modèle | Champ computed cassé | Type | Raison |
|---|---|---|---|
| `of.planning.tour` | **`gb_sector_id`** | graph_edges (LINKS_GB_SECTOR) | Compute method failed |
| `sale.order.line` | **`of_gb_partner_tag_id`** | graph_edges (LINKS_OF_GB_PARTNER_TAG) | Compute method failed |
| `calendar.event` | **`of_gb_employee_id`** | graph_edges (LINKS_OF_GB_EMPLOYEE) | Compute method failed |

**Erreur Odoo exacte** :
```
ValueError: Compute method failed to assign <model>(<ids>).<field>
```

**Interprétation technique** : ces 3 champs sont des "related/computed" fields du module OpenFire (préfixe `gb_*`, probablement "GBook" ou "Gestion Book" — un module custom). Leur méthode `_compute_*()` côté Python OpenFire est buggée et lève un `CacheMiss` au lieu d'assigner une valeur. **Ce n'est PAS un problème Raya, c'est un bug côté Odoo OpenFire.**

---

## 🔍 Vérifications complémentaires

**Pattern `gb_*`** : j'ai scanné les 16 manifests P1 pour trouver tous les champs contenant `gb_`. Résultat : **uniquement ces 3 champs cassés**, pas de bombe cachée dans les autres modèles.

**`mail.message`** : il n'est PAS abandonné par le circuit breaker. Progress = `0/200`, mais pas d'erreur stockée. Hypothèse : **Odoo retourne 0 record** (droits insuffisants ou domain filter implicite qui exclut tous les messages). À investiguer séparément.

**`product.pack.line`, `of.product.pack.lines`, `of.survey.user_input.line`** : 150-200 records processed mais **0 chunks créés**. Suspicion : le manifest n'a pas de `vectorize_fields` (donc pas de chunk créé, juste du graph). À vérifier.

---

## 🔧 Solution recommandée : retrait des 3 champs cassés des manifests

### Approche

**Retirer chirurgicalement les 3 champs problématiques** de la section `graph_edges` des manifests concernés. Rien d'autre ne change. Les relations de graphe perdues sont minimes (3 relations sur des dizaines par modèle).

### Ce qu'on perd

- **`of.planning.tour` → `of.sector`** (via `gb_sector_id`) : la relation Tour → Secteur ne sera pas dans le graphe.
- **`sale.order.line` → `res.partner.category`** (via `of_gb_partner_tag_id`) : tag fournisseur/catégorie partner.
- **`calendar.event` → `hr.employee`** (via `of_gb_employee_id`) : assignation employé (MAIS il y a déjà `of_employee_id` et `user_id` dans le même manifest donc l'info sera captée autrement).

**Impact réel sur la proactivité** : très faible. Le champ `gb_*` est un doublon/alias d'autres champs de relation déjà présents.

### Implémentation

Script Python qui :
1. Charge chaque manifest
2. Retire le champ cassé de `graph_edges`
3. Sauvegarde la version modifiée
4. Idempotent (relançable sans risque)

Temps estimé : **5 min**.

---

## 🧪 Plan de validation

1. **Retirer les 3 champs** via script (5 min)
2. **Relancer Scanner test** (bouton violet "🧪 Test manquants") → les 3 modèles devraient passer (10 min)
3. Si OK sur 200 records → **relancer Scanner test une 2e fois** avec limite plus haute (1000 records) pour confirmer que ça tient la charge (15 min)
4. Si toujours OK → **intégrer ces modèles au Scanner P1** (complet, non-destructif, juste un top-up sur les 4 manquants)

---

## ❓ mail.message séparément

`mail.message` reste à traiter après. Hypothèses :
- **H1 (la plus probable)** : droits Odoo sur `mail.message`. Par défaut, seul l'auteur/destinataire peut lire un message. Le compte API OpenFire utilisé par Raya n'a peut-être pas l'ACL pour lire tous les messages.
- **H2** : domain filter implicite côté Odoo (ex: exclut les messages archivés, les messages sans destinataire, etc.).

**Solution possible** : tester un appel `mail.message search_count` via Odoo avec notre compte pour voir combien de messages on voit réellement. Si c'est 0, c'est un pb de droits. Si c'est >0 mais < 29139, c'est un filter.

À traiter en **session suivante** pour ne pas allonger celle-ci.

---

## 🎯 Ma recommandation

1. ✅ **Maintenant** : retirer les 3 champs cassés des manifests (5 min + relance test)
2. ⏳ **Session suivante** : investiguer `mail.message` (pb de droits Odoo probable)
3. ⏳ **Après** : relancer Scanner P1 complet (non-destructif, juste top-up) → on aura 24 776 + ~9 000 chunks = base complète pour la proactivité

Tu valides ?
