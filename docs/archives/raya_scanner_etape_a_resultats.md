# 🔍 Résultat Étape A — Investigation Odoo

**Date** : 19 avril 2026, 18h40
**Méthode** : script `scripts/diagnose_odoo_models.py` qui teste chaque modèle problématique avec fetch minimal (id + display_name) puis ajoute progressivement les champs du manifest pour isoler les tueurs.

---

## 🎯 Résultat brut du diagnostic

Les 4 modèles testés plantent **dès le fetch minimal** (juste `id + display_name`) avec une erreur d'authentification :

```
AccessDenied
Traceback ... File "/opt/openfire/16.0.8.5.0/odoo-src/..."
```

**Ce n'est PAS une `ValueError` comme le disait le message tronqué** stocké dans `models_aborted`. C'est `AccessDenied`, erreur d'authentification Odoo.

---

## 🧩 Pourquoi 12 modèles ont marché et 4 ont planté ?

Je n'ai pas la réponse définitive sans les logs Railway complets du run #6. Hypothèses à classer par probabilité :

### H1 — Session Odoo qui expire en cours de route (probable)

Le connecteur `odoo_call` réauthentifie à chaque appel. Si Odoo a un **rate limit** sur la création de sessions, certaines requêtes en cours peuvent hériter d'une session morte.

Indice : les modèles qui ont planté sont ceux qui viennent **plus tard dans la séquence** :
- OK : product.template (#1), mail.tracking.value (#3), of.product.pack.lines (#4), of.survey.answers (#6)
- KO : mail.message (#2) ← ancre exception, of.planning.tour (#5), sale.order.line (#7), calendar.event (#10)

`mail.message` a planté tôt (position #2). C'est peut-être le seul vrai problème de fond. Les autres ont pu hériter d'un état dégradé qui s'est installé après l'échec de `mail.message`.

### H2 — Problème de droits sur certains modèles Odoo (possible)

Le user Odoo `guillaume` a peut-être des droits différents selon les modèles :
- ✅ product, mail.tracking.value, of.product.pack.lines... OK
- ❌ of.planning.tour, sale.order.line, calendar.event, mail.message : accès refusé

Pour `mail.message` notamment, c'est **crédible** : dans Odoo par défaut, seul l'auteur ou destinataire peut lire un message. Il faut des droits étendus pour tout lire.

### H3 — Champs computed qui provoquent AccessDenied (moins probable)

Certains champs computed vérifient des ACL imbriqués qui peuvent retourner AccessDenied même pour les users avec accès. Ça expliquerait que `of.planning.tour` plante avec tous ses champs alors qu'il serait OK avec juste `id, display_name`.

**MAIS** mon test montre que même `id, display_name` plante → donc ce n'est pas H3 ici.

---

## ⚠️ Limitation du test local

Depuis mon poste (`localhost`), je ne peux pas reproduire exactement ce qui se passe en prod (Railway). Les credentials locaux dans `.env` déclenchent `AccessDenied` immédiatement, alors qu'en prod le même connecteur réussit 12 modèles sur 16.

**Il faut donc un diagnostic côté prod** : ajouter du logging détaillé qui s'exécutera au prochain run et nous donnera le vrai stack trace Odoo complet.

---

## 🔧 Plan consolidé pour la session (mise à jour)

### Étape A.2 — Améliorer le logging d'erreur (10 min)

Avant de faire quoi que ce soit d'autre, rendre le scanner plus loquace :

1. **Stocker le message complet** dans `models_aborted` (pas tronqué à 200 chars)
2. **Logger le traceback Odoo complet** dans Railway (avec `logger.exception`)
3. **Compter les types d'erreur** (AccessDenied / ValueError / Timeout / other)

Comme ça, au prochain scan test, on saura exactement quelle erreur Odoo nous renvoie.

### Étape B — Scanner test 200 records (manquants uniquement) (30 min)

Bouton UI qui détecte automatiquement les modèles sans chunks et les teste sur 200 records.

### Étape C — Double validation (clic + modale "Êtes-vous sûr ?") (20 min)

Modale HTML propre (pas `confirm()`) sur toutes les actions destructives :
- 🚀 Scanner P1 (avec purge)
- 🧪 Scanner test
- ⏹️ Arrêter scan
- 🗑️ Supprimer société
- 🗑️ Supprimer utilisateur

### Étape D — Bouton Stop scan (20 min)

Flag `stop_requested` en DB, le worker vérifie après chaque modèle (option A validée).

### Étape A.3 (après test B) — Selon résultats, ajuster les manifests

Si les erreurs sont AccessDenied sur `mail.message` → ajouter un domaine filter `[("message_type","in",["comment","email"])]` dans le manifest pour éviter les messages systèmes restreints.

Si AccessDenied sur `calendar.event` → tester avec domain `[("privacy","=","public")]`.

Etc.

---

## 💡 Conclusion de l'Étape A

**Le problème n'est pas dans le scanner lui-même, c'est dans la relation scanner ↔ Odoo pour certains modèles spécifiques.**

Le diagnostic depuis mon poste ne peut pas reproduire la prod parce que mes credentials locaux ne marchent pas (pb .env, probablement API key différente).

**Ma recommandation** : on saute l'identification des champs tueurs (pas possible sans prod) et on fait directement :
1. Étape A.2 (meilleur logging)
2. Étape C + D (sécurité UI : double validation + bouton stop)
3. Étape B (scanner test 200 records)
4. On relance le test → on verra les vrais messages d'erreur Odoo
5. On adapte les manifests selon ces messages

Ça change légèrement l'ordre mais pas l'esprit du plan. **Tu valides ?**
