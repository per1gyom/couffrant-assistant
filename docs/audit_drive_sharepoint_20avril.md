# Audit Drive SharePoint — état actuel et plan de vectorisation

**Date :** 20 avril 2026
**Périmètre :** SharePoint uniquement (Google Drive mis de côté)
**Objectif :** atteindre pour SharePoint le même niveau d'intégration qu'Odoo
(scan initial + temps-réel + recherche sémantique + graphe).

---

## 1. Ce qui existe déjà

### Connexion & lecture SharePoint — **mature**
Fichier `app/connectors/drive_connector.py` et ses satellites.

- Authentification OAuth Microsoft Graph via `microsoft_connector.py`
- Découverte automatique du site SharePoint et du drive cible
- Cache du `drive_id` (évite les rappels d'API)
- Config par tenant : `tenants.settings` contient `sharepoint_site` + `sharepoint_folder`
- 3 fonctions principales dans `drive_read.py` :
  - `list_drive()` — liste le contenu d'un dossier (avec sous-dossiers)
  - `read_drive_file()` — lit un fichier (texte direct pour txt/md/csv ; métadonnées pour PDF/docx/xlsx avec conseil de joindre le fichier à la conversation)
  - `search_drive()` — recherche par mot-clé via l'API Graph
- Actions CRUD (`drive_actions.py`) : créer dossier, déplacer, copier

### Webhooks Microsoft Graph — **partiel**
Fichier `app/connectors/microsoft_webhook.py` (231 lignes).

- Infrastructure de souscription OK : create, renew, delete, DB de suivi
- Renouvellement automatique planifié (scheduler_jobs.py)
- Endpoint de réception `POST /webhook/microsoft` avec validation du `clientState`
- **MAIS** : souscrit uniquement `me/mailFolders/inbox/messages` (les emails).
  **Aucune souscription sur les fichiers SharePoint.**

### Réception webhook Microsoft — **mails uniquement**
Fichier `app/routes/webhook_microsoft.py` + `webhook_ms_handlers.py`.
Toute la logique ne traite que des messages Outlook (filtres spam, processing mail).
Rien pour les fichiers.

### Extraction de texte depuis les documents — **existant mais localisé**
Fichier `app/scanner/document_extractors.py` existe côté Scanner Universel.
À vérifier ce qu'il sait faire (PDF, Word, Excel ?).

---

## 2. Ce qui manque

### A. Modèle de stockage pour les documents Drive
Aujourd'hui la seule table de contenu vectorisé est `odoo_semantic_content`.
Elle est nommée et structurée pour Odoo (colonnes `source_model`,
`source_record_id`, `related_partner_id`, `odoo_write_date`). **Pas adaptée
à Drive** qui a d'autres métadonnées (file_id, path, extension, taille,
modifié_par, parent_folder, etc.).

**Décision à prendre** : une nouvelle table dédiée `drive_semantic_content`
OU une table générique `semantic_content` qui remplace `odoo_semantic_content`
à terme. La deuxième option est plus propre mais implique migration.

### B. Manifests de vectorisation pour les types de fichiers
Pour Odoo on a un manifest par modèle qui dit quels champs vectoriser.
Pour Drive, il faut un équivalent : quelles parties d'un PDF/docx/xlsx
sont pertinentes, comment les découper en chunks (documents longs),
quels noeuds de graphe créer, etc.

### C. Scanner initial du dossier SharePoint
L'équivalent du scanner Odoo : parcourir récursivement le dossier
configuré, extraire le texte de chaque fichier, vectoriser, stocker.
Avec limitations de taille (pas de vidéo 4 Go), filtres d'extension,
gestion des erreurs par fichier (1 fichier corrompu ne doit pas tout
bloquer).

### D. Temps-réel via webhooks SharePoint
Il faut créer des souscriptions Graph sur le drive SharePoint (pas
l'inbox mail). Ressource cible :
```
/drives/{drive_id}/root
```
ou pour être plus ciblé :
```
/drives/{drive_id}/items/{folder_id}
```
Endpoint de réception dédié pour les notifications de fichiers
(différent de celui des mails, ou avec un dispatcher selon la ressource).

### E. Mécanisme facile pour ajouter un nouveau dossier
Guillaume veut pouvoir ouvrir de nouveaux dossiers à Raya sans dev.
Il faut une UI ou une config qui permet d'ajouter un dossier à la liste
des dossiers vectorisés, et déclencher automatiquement le scan initial
sur ce dossier + la souscription webhook.

---

## 3. Bonne nouvelle — ce qu'on peut réutiliser tel quel

| Brique Odoo | Réutilisable pour Drive ? | Comment |
|---|---|---|
| `vectorization_queue` | ✅ Totalement | Juste changer `source` de `odoo` à `drive` |
| `webhook_queue.enqueue()` | ✅ Totalement | Même fonction, nouveau source |
| Worker + dédup + anti-rejeu | ✅ Totalement | Déjà multi-source par design |
| Scanner processor (`process_record`) | ⚠️ Partiellement | Générique mais conçu pour records Odoo, à adapter pour documents |
| `semantic_graph_nodes` / `edges` | ✅ Totalement | Types Document déjà prévus |
| Dashboard 📊 Intégrité | ⚠️ À étendre | Ajouter une ligne par "source" (Odoo / Drive) |
| Dashboard 🔌 Webhooks | ✅ Totalement | Marchera tel quel pour les webhooks Drive |
| Ronde de nuit 5h | ✅ À étendre | Ajouter la ressource Drive dans la comparaison |

**Grosse conclusion** : l'infra de hier soir (webhook_queue, worker, dashboard,
ronde de nuit) est générique par design. **~70% du travail est déjà fait**.
Il reste principalement :
- Le modèle de stockage document
- Le scanner initial documents
- Les manifests par type de fichier
- La souscription webhook SharePoint
- L'UI d'ajout de dossier

---

## 4. Proposition de plan (4 phases)

### Phase D.1 — Fondations stockage et extraction (1-2 jours)
1. Créer la table `drive_semantic_content` (ou renommer en `semantic_content`
   générique)
2. Créer un manifest minimal pour les extensions clés (pdf, docx, xlsx, txt, md)
3. Réutiliser `document_extractors.py` ou l'étendre
4. Fonction `process_document()` qui prend un fichier Drive et produit chunks +
   nœud graphe + arêtes

### Phase D.2 — Scanner initial (1 jour)
1. Fonction `scan_drive_folder()` qui parcourt récursivement un dossier
   SharePoint, liste tous les fichiers, les enqueue dans
   `vectorization_queue` (réutilisation totale)
2. Bouton panel admin : ligne Drive sur le tenant, dropdown "🚀 Scanner" avec
   "🧪 Test 20 fichiers" et "📈 Scan complet du dossier"
3. Dashboard 📊 Intégrité étendu avec les stats Drive

### Phase D.3 — Temps-réel via webhooks SharePoint (1 jour)
1. Étendre `microsoft_webhook.py` pour souscrire aussi `/drives/{id}/root`
2. Endpoint dédié `POST /webhooks/microsoft/drive-changed` (ou extension du
   dispatcher existant)
3. À chaque notification : fetch les changements depuis `delta`, enqueue dans
   `vectorization_queue`
4. Ronde de nuit étendue pour vérifier la cohérence Drive (filet de sécurité)

### Phase D.4 — UI d'ajout de dossier (0.5 jour)
1. Dans le panel admin, sur le connecteur Drive : bouton "➕ Ajouter un dossier"
2. Formulaire simple : site SharePoint + chemin dossier
3. Au submit : enregistre dans une table `drive_folders`, lance le scan initial,
   crée la souscription webhook

---

## 5. Points ouverts à discuter

- **Taille max** des fichiers vectorisés ? (PDF de 200 pages ? vidéos ? images ?)
- **Extensions supportées** : on commence par PDF + docx + xlsx + txt, on
  étend plus tard ?
- **OCR pour PDF scannés** (photos de documents imprimés) : utile ?
  coûteux mais parfois nécessaire pour les devis reçus
- **Cloisonnement tenant** : un dossier SharePoint = 1 tenant ? OK mais
  vérifier qu'on peut ajouter plusieurs dossiers par tenant
- **Priorité des fichiers** : quand un PDF de 500 pages arrive, est-ce qu'on
  le vectorise en entier ou on limite ?
- **Suppression / archivage** : quand Arlène supprime un fichier SharePoint,
  on marque `deleted_at` côté Raya ou on purge ?

---

## 6. Recommandation d'enchaînement

Vu le temps déjà investi ce matin sur le polling Odoo, et vu qu'on est en
fin de matinée, je recommande de :

1. **Toi** : laisser tourner l'Odoo polling quelques heures et vérifier que
   tout marche (création d'un devis test → apparition dans 🔌 Webhooks).
2. **Nous** : prendre une vraie session (1-2h au calme, pas ce midi) pour
   trancher les points ouverts (section 5) et attaquer la Phase D.1.
3. **Pas de code Drive maintenant** tant que les points ouverts ne sont pas
   tranchés. Pas envie de refaire la boulette Odoo 16 d'hier soir.

Ce document reste comme référence pour la prochaine session.
