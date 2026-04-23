# Mail complémentaire OpenFire — 22 avril soir

**Destinataire** : Dorian — équipe technique OpenFire
**Expéditeur** : Guillaume Perrin — Couffrant Solar
**Instance** : `entreprisecouffrant.openfire.fr`

---

## Objet du mail (à copier dans le client mail)

`Couffrant Solar — Complément à ma demande d'ouverture API (3 éléments oubliés)`

---

## Corps du mail (à copier tel quel)

Bonjour Dorian,

Petit complément à mon mail précédent sur l'ouverture des droits API.
En relisant mes notes je me rends compte qu'il me manquait **3 éléments**
identifiés ces derniers jours que j'avais oublié d'inclure. Je te regroupe
tout ça ici pour que tu aies la vue complète en un seul passage.

Tous les accès demandés restent **en lecture seule uniquement**, sur
le même user API déjà en place.

---

### 1. `res.partner.child_ids` — relations parent/enfant entre contacts

**Pourquoi** : aujourd'hui je vois les contacts isolés, mais je ne sais
pas qui est gérant de quelle société, qui est comptable, qui est
chargé d'affaire pour tel chantier. Cette relation existe déjà dans
Odoo (champ `child_ids` / `parent_id` sur `res.partner`), il suffit
qu'elle soit lisible via API.

**Usage concret** : quand je demande "quel est le contact comptable
de la SARL Des Moines ?", aujourd'hui je dois croiser manuellement.
Avec cet accès, je remonte directement les enfants rattachés à la
fiche société.

**Ce qu'il faut ouvrir** :
- Lecture du champ `child_ids` sur `res.partner`
- Lecture du champ `parent_id` sur `res.partner`

---

### 2. `ir.attachment` — lecture des pièces jointes

**Pourquoi** : énormément de documents stratégiques vivent comme
pièces jointes dans Odoo : KBIS scannés, devis signés, bons de
commande fournisseurs, fiches techniques produits, mandats ENEDIS,
attestations Consuel. Aujourd'hui ces documents sont invisibles à
notre outil alors qu'ils existent en base.

**Usage concret** : pour le dossier Coullet, le mandat ENEDIS signé
par Francine est en PJ sur sa fiche. Je dois aller le chercher
manuellement dans Odoo. Avec cet accès, l'outil me dit "mandat signé
présent, daté du 25/03/2026".

**Ce qu'il faut ouvrir** :
- Lecture de `ir.attachment` (métadonnées : nom, type, date, taille)
- Lecture du contenu binaire (champ `datas`) pour pouvoir extraire
  le texte des PDF si besoin
- Si possible, lecture de `ir.attachment.res_model` et `res_id`
  pour retrouver à quel enregistrement (sale.order, res.partner,
  etc.) le document est rattaché.

Si l'ouverture complète pose problème côté volume ou perf, on peut
discuter d'un périmètre restreint (par exemple uniquement les PJ
sur `sale.order`, `account.move`, `res.partner` — ce qui couvre
95% de mon besoin).

---

### 3. Rappel — webhooks temps-réel (mail du 20/04 matin)

Juste pour confirmer qu'il reste en attente de ton côté, pas
urgent. Tu trouveras le détail dans mon mail initial intitulé
"Demande OpenFire — webhooks temps-réel". Si tu préfères qu'on en
reparle plus tard une fois les points 1 et 2 traités, aucun
problème, c'est de loin le moins bloquant des trois.

---

### Récap consolidé pour ta visibilité

Entre ce mail et le précédent, la liste complète de ce que j'attends
de ton côté est :

1. `sale.order.line` ✅ *(déjà ouvert aujourd'hui, merci)*
2. `product.product` + `product.template` (lecture)
3. `account.move.line` (lecture, avec groupe Accounting/Billing)
4. `account.payment.line` (lecture, avec groupe Extra Rights)
5. `mail.message` (approche à caler avec toi sur le filtrage par défaut)
6. `res.partner.child_ids` + `parent_id` (lecture — **nouveau**)
7. `ir.attachment` (lecture métadonnées + `datas` + `res_model`/`res_id` — **nouveau**)
8. Webhooks temps-réel (rappel du mail du 20/04)

Désolé pour le découpage en deux mails, je te remercie d'avance de
ta patience. N'hésite pas à me rappeler si c'est plus simple pour
démêler ça en 10 minutes de visio.

Cordialement,

Guillaume
06 49 43 09 17

---

## ⚠️ Note pour Guillaume (à ne pas copier dans le mail)

**Contenu de ce mail :**
- Les 2 éléments vraiment manquants (child_ids, ir.attachment)
- Rappel du webhook (une ligne, non bloquant)
- Récap numéroté pour qu'il ait la vue d'ensemble

**Ton de l'email** : plus court que le précédent, volontairement
direct. On assume l'oubli ("en relisant mes notes"), on propose
une option de fallback sur ir.attachment (périmètre restreint) si
le volume pose problème, et on reste ouvert à une visio de 10 min
si c'est plus rapide pour lui.

**Pourquoi ne pas tout renvoyer** : Dorian a déjà ton 1er mail bien
détaillé, le spammer avec un second mail identique ferait doublon.
Ce complément-là est court et ciblé.

**Après l'envoi** :
- Mettre à jour `docs/recensement_acces_odoo.md` → ligne
  "Historique des mails envoyés" : ajouter
  "22/04/2026 soir — Complément child_ids + ir.attachment"
- Quand Dorian répond, MAJ les statuts 🟡 → ✅ dans le tableau
