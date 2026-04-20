# Demande à OpenFire — Ouverture de droits API sur modèles produits et lignes

**Destinataire** : équipe technique OpenFire
**Expéditeur** : Guillaume Perrin — Couffrant Solar (instance `entreprisecouffrant.openfire.fr`)
**Date** : 20 avril 2026
**Urgence** : moyen — bloque une part significative des cas d'usage Raya

---

## Contexte

Notre intelligence artificielle métier **Raya** (accessible à l'équipe via
app.raya-ia.fr) est connectée à Odoo en lecture via un utilisateur API
dédié. Elle lit les devis, commandes, factures, activités, interventions
pour répondre aux questions courantes de l'équipe (suivi commercial,
pilotage technique, historique client).

Tout fonctionne bien au niveau "entête" des documents (nom du devis, client,
date, montant total). **Mais Raya n'a actuellement pas accès au détail des
lignes ni au catalogue produits.** Cela bloque toute question qui porte
sur le matériel posé, les références techniques, les quantités, etc.

## Exemple concret du blocage

**Question posée par Guillaume à Raya aujourd'hui (20/04 vers 16h)** :
> *"Où a-t-on posé des onduleurs SE100K ?"*

**Réponse de Raya** :
> *"La recherche sémantique Odoo ne remonte aucun chantier avec SE100K
> clairement identifié. L'API Odoo ne m'expose que les métadonnées des
> devis (nom, montant, client, date) sans le détail des lignes
> (sale.order.line avec produit, modèle, quantité). Je suis aveugle sur
> les questions type 'où ai-je posé du SE100K' ou 'combien de Tesla PW3
> cette année'."*

Ce type de question est **fondamental** pour le pilotage d'une entreprise
photovoltaïque : savoir ce qui a été posé, où, combien, avec quel matériel.

## Ce que nous vous demandons

**Ouvrir les droits de lecture** de l'utilisateur API Raya sur les
modèles Odoo suivants :

| Modèle | Nom fonctionnel | Usage par Raya |
|---|---|---|
| `sale.order.line` | Lignes de devis / commande | Voir quels produits / quantités sur chaque devis |
| `product.product` | Variantes produit | Référentiel des références exactes (SE100K, PW3, etc.) |
| `product.template` | Modèles produit | Fiche catalogue de base |
| `account.move.line` | Lignes de facture | Croiser facturé vs devisé |

## Niveau d'accès demandé

**LECTURE SEULE (read-only)**. Aucune création, modification, suppression.

Raya est un outil d'analyse, pas un outil d'écriture sur ces modèles.
Elle ne doit jamais modifier une ligne de devis ni un produit.

## Utilisateur API concerné

L'utilisateur API Raya déjà en place sur notre instance Odoo Couffrant,
que vous avez configuré précédemment. Merci simplement de lui ajouter
les 4 accès lecture listés ci-dessus via son groupe de permissions.

## Ce que Raya pourra faire une fois ces droits ouverts

Une fois les accès en place (et après un court scan de rattrapage côté
Raya, ~15 min), l'équipe Couffrant pourra poser à Raya des questions
comme :

### Questions matériel
- *"Où a-t-on posé des SolarEdge SE100K cette année ?"*
- *"Combien de Tesla Powerwall 3 installés depuis janvier ?"*
- *"Liste des chantiers avec onduleur Huawei SUN2000"*
- *"Quels clients ont des panneaux DualSun ?"*

### Questions commerciales
- *"Montant total devisé en onduleurs SolarEdge 2025 vs 2024"*
- *"Devis redondants sur le même client avec le même matériel"*
- *"Écart devisé vs facturé sur le chantier XYZ"*

### Questions SAV et garantie
- *"Si un onduleur SE100K tombe en panne, sur quels chantiers ai-je
  ce modèle (pour les prévenir d'un rappel constructeur) ?"*
- *"Produits les plus fréquemment facturés en SAV"*

### Questions pilotage
- *"Stock critique : références apparaissant souvent dans les devis
  récents mais pas encore facturés"*
- *"Prix moyen d'un onduleur par gamme sur les 6 derniers mois"*

## Contrôles côté Raya (ce qui est déjà en place)

Nous avons un système de permissions interne sur 3 niveaux
(lecture / écriture / suppression). Ces droits API élargis n'autoriseront
à Raya que la **lecture sémantique**. Aucune opération destructive n'est
possible côté Raya sur Odoo, ni avec l'architecture actuelle, ni si
Raya tente de le faire dans le futur.

Par ailleurs, Raya est cloisonnée par tenant : les données Couffrant ne
sont accessibles qu'aux utilisateurs Couffrant. Aucune fuite cross-tenant
possible.

## Cas d'usage équivalents sur d'autres instances

Beaucoup d'instances Odoo avec outils IA ou reporting externe
(Metabase, PowerBI, tableaux de bord custom) donnent ces mêmes accès
lecture à des comptes API dédiés. Il s'agit donc d'une configuration
standard, pas d'une demande inhabituelle.

## Volume et charge réseau

Le scan initial Raya (déjà en place et en cours d'utilisation)
interroge par batch de 100-500 records avec `search_read` (appel JSON-RPC
classique). Le polling temps-réel actuel fait 1 appel toutes les 2 min
par modèle actif.

L'ajout de 4 modèles supplémentaires augmentera la charge de quelques
appels en plus par cycle de polling. **Impact négligeable** sur votre
serveur.

## Planning souhaité

- **Idéalement cette semaine** : l'équipe Couffrant perd actuellement
  chaque jour l'opportunité de répondre vite à des questions terrain.
- **Pas urgent absolu** : on continue de fonctionner avec l'accès
  actuel pour les questions de haut niveau.

## Contact

**Guillaume Perrin**
Couffrant Solar — 18 rue de Langon, 41200 Romorantin-Lanthenay
TVA : FR63803487586

---

## Pour votre référence technique

Si vous préférez ouvrir via un groupe custom plutôt que via les groupes
standards "Sales / User : All Documents" + "Inventory / User", les ACL
minimales requises sont :

```
ir.model.access.access_sale_order_line_raya,sale.order.line.read.raya,
  model_sale_order_line,group_raya_readonly,1,0,0,0

ir.model.access.access_product_product_raya,product.product.read.raya,
  model_product_product,group_raya_readonly,1,0,0,0

ir.model.access.access_product_template_raya,product.template.read.raya,
  model_product_template,group_raya_readonly,1,0,0,0

ir.model.access.access_account_move_line_raya,account.move.line.read.raya,
  model_account_move_line,group_raya_readonly,1,0,0,0
```

(les 3 derniers champs `0,0,0` = pas de write, pas de create,
pas de unlink — lecture pure).

Merci d'avance pour votre retour.
