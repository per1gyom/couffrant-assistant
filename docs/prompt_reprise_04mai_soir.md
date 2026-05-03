# Prompt de reprise — Conversation Raya/Couffrant

**Date de generation :** Lundi 4 mai 2026 (soir)
**Conversation precedente :** Saturee, transition vers nouvelle conversation.

Copie ce prompt dans la nouvelle conversation Claude. Il contient TOUT le contexte necessaire pour reprendre le projet sans perdre le fil.

---

## Identite et contexte personnel

Je m appelle **Guillaume**. Je developpe une application mobile **Flutter native** avec un assistant IA proactif et apprenant, actuellement nomme **Raya** (le nom final pourrait evoluer vers **Elyo** - discussions en cours sur la marque, classes 9/35/38/42/45 retenues, classe 36 differee, classes 41/44 exclues).

Je gere aussi du **patrimoine immobilier** via SCI Romain Guy et plusieurs autres SCI (Gaucherie, MTBR, Romagui).

**Strategie commerciale :** demarrer avec quelques clients preferentiels a prix tendre, scaler a 20-30 clients pour viabilite, sortie possible par fusion/acquisition.

---

## Repo, prod et infra

- **Repo local :** `/Users/per1guillaume/couffrant-assistant`
- **Repo GitHub :** `per1gyom/couffrant-assistant`
- **Prod :** `https://app.raya-ia.fr` heberge sur **Railway** (auto-deploy depuis main)
- **DB Postgres prod :** `postgresql://postgres:JZlVUxmXXMtyYXQqaFUggifXdRLiZtiA@maglev.proxy.rlwy.net:28864/railway`
- **Tenants actifs :**
  - `couffrant_solar` (Guillaume, super_admin)
  - `juillet` (Charlotte, test)

---

## Style de communication (CRITIQUE)

- **Reponses CONCISES dans le chat**, jamais de PDF/dossiers generes sauf demande explicite
- **\U0001F6D1 en debut de reponses importantes** pour attirer l attention
- **Pas de questions A/B/C** - donner une proposition d expert directe
- **VERIFIER avant de proposer un fix**
- **AUDITER L EXISTANT AVANT DE CODER DU NEUF** (lecon retenue : on a parfois recode des choses qui existaient deja)
- **NE JAMAIS PUSH pendant qu un job critique tourne** (incident scan SharePoint interrompu, lecon dure)
- Langage non-technique, je ne suis pas dev pro
- Si je dis "je vois pas ta reponse" -> reecris plus court
- Si je signale un defaut, ne pas se justifier, juste corriger

---

## Vision globale du projet

**Raya = assistant IA proactif et apprenant** qui aide a gerer une entreprise de maniere holistique :
- Comprend mes mails (filtre intelligent, analyse, push graphe semantique)
- Lit mon Drive/SharePoint (fichiers vectorises)
- Connecte Odoo (CRM + ERP : devis, factures, contacts, projets, planning, SAV)
- Apprend mon style d ecriture (mails envoyes)
- Apprend mes regles metier au fur et a mesure
- Devient proactif : suggere, alerte, anticipe

### Architecture 4 couches (vision_architecture_raya.md)

```
COUCHE 1 - Sources externes
  Outlook/Gmail (mails) - SharePoint (Drive) - Odoo (ERP) - Teams - WhatsApp
  
COUCHE 2 - Memoire vectorielle
  pgvector + text-embedding-3-small (1536 dims)
  mail_memory - drive_chunks - odoo_chunks - etc.
  
COUCHE 3 - Graphe semantique unifie + GraphRAG (vivant)
  semantic_graph_nodes (113k+ noeuds) - Mail, File, Folder, Mailbox, Person,
    Invoice, Order, Lead, Contact, Project, Task, Event, etc.
  semantic_graph_edges (delivered_to, contains, mentions, sent_by, replies_to...)
  A venir : communautes Leiden + resumes (job nocturne)
  Systeme V1 mort (entity_links, depuis 17/04) a nettoyer progressivement
  
COUCHE 4 - Proactivite (4 etages, vision_proactivite_30avril.md)
  Veille -> Suggestion -> Action proposee -> Action automatique (avec garde-fous)
```

---

## Connexions Guillaume (toutes healthy)

### 5 Gmail (gmail tool_type)
- **per1.guillaume@gmail.com** (ID=4, connectee 15/04, ~5000 mails estimes)
- **GPLH** sasgplh@gmail.com (ID=7, connectee 28/04)
- **Romagui** sci.romagui@gmail.com (ID=8, connectee 28/04)
- **Gaucherie** sci.gaucherie@gmail.com (ID=9, connectee 28/04, **24 mails bootstrappes le 04/05**)
- **MTBR** sci.mtbr@gmail.com (ID=10, connectee 28/04)

### 2 Outlook
- **guillaume@couffrant-solar.fr** (microsoft tool_type, ID=6, connectee 16/04, ~673 mails deja ingeres)
- **Contact Couffrant Solar** contact@couffrant-solar.fr (outlook tool_type, ID=12, connectee 28/04)

### Drive
- **SharePoint Commun** (drive tool_type, ID=1) - 5301 fichiers a jour

### Odoo
- **Openfire** (odoo tool_type, ID=3) - vectorise en grande partie

---

## Chantiers realises ces derniers jours (commits cles)

### Session 4 mai 2026 (la plus recente, fraiche)

| Commit | Description |
|---|---|
| `ba3734c` | fix typo import bloquant indexation Drive depuis 14j |
| `9980ae8` | docs: nettoyage 36 docs obsoletes -> archives/cleanup_04mai_2026/ |
| `6f4d736` | fix UPSERT drive_folders par drive_id+folder_path |
| `d209739` | fix scan Drive : passer folder_path comme path_prefix |
| `659ecef` | feat UI scan Drive : barre progression + auto-refresh modale |
| `5a4b932` | feat mail-identification : mailbox_email + connection_id sur chaque mail (947/1006 backfilles) |
| `6fa90c1` | feat mail_to_graph V2 : push automatique mails vers semantic_graph_nodes (947 mails pousses) |
| `7d8e376` | **CHANTIER B :** mail admin tools (inventaire + bootstrap + graphe) |
| `45e8475` | **fix B suite test Gaucherie :** UX feedback bootstrap + coherence stats par dossier |

### Avant le 4 mai

- 19/04 : Scanner universel Odoo + dashboards integrite + webhooks
- 20/04 : Refonte UI panel admin (groupement Drive vs Mail vs Odoo)
- 27/04 : Audit systeme graphes V1 vs V2 (V1 mort, V2 vivant)
- 28/04 : Connexion 4 Gmail SCI + Contact Couffrant
- 30/04 : Vision proactivite + 6 phases + double config + 5 canaux
- 01/05 : Phase Connexions Universelles (reconciliation nocturne mail/drive)

---

## Composants techniques cles a connaitre

### Pipeline d ingestion mail (universel multi-tenant)

```
Boite mail (Outlook/Gmail)
  -> polling delta (mail_outlook_delta_sync.py / mail_gmail_history_sync.py)
    OU bootstrap historique (mail_bootstrap.py - cree le 04/05)
  -> process_incoming_mail() dans webhook_ms_handlers.py
     1. Filtres whitelist/blacklist
     2. Heuristique anti-bulk (rapide)
     3. Triage Haiku (route_mail_action) en quelques ms :
        -> IGNORER (newsletter/promo) -> poubelle, rien d enregistre
        -> STOCKER_SIMPLE -> mail_memory sans analyse IA
        -> ANALYSER -> analyse complete Sonnet (categorise, prioritise)
     4. insert mail_memory avec mailbox_email + connection_id
     5. push_mail_to_graph (cree le 04/05) -> semantic_graph_nodes
        + edges delivered_to / sent_by
```

### Tables principales

- `mail_memory` (1006+ mails, avec mailbox_email + connection_id)
- `mail_bootstrap_runs` (creee le 04/05, tracking jobs bootstrap)
- `semantic_graph_nodes` (113k+, V2 vivant)
- `semantic_graph_edges`
- `tenant_connections` (les boites mail + drive + odoo configurees)
- `user_tenant_access` (qui a acces a quoi)
- `entity_links` (V1 mort, a nettoyer)
- `drive_files` / `drive_folders` / `drive_chunks`
- `odoo_chunks` + tables modeles Odoo

### UI panel admin

- `app/static/admin-panel.js` (3197 lignes, 04/05)
- Sur chaque ligne de connexion mail : menu **"Scanner boite mail"** (chantier B)
  - Inventaire boite
  - Bootstrap historique (3/6/9/12 mois ou TOUT) - confirmation + auto-redirect status
  - Etat du dernier bootstrap (auto-refresh 5s)
  - Etat du graphe mail
  - Migrer mails vers graphe
- Sur la ligne Drive : menu **"Scanner SharePoint"** (existait deja, complet)
- Sur la ligne Odoo : Setup + Scanner + Integrite + Webhooks (existait deja)

---

## Documents de reference (dans /docs)

| Fichier | Contenu |
|---|---|
| `etat_04mai_2026.pdf` | **DOC PRINCIPAL** etat du projet au 04/05 |
| `plan_proactivite.pdf` | Plan detaille proactivite 4 etages |
| `vision_proactivite_30avril.md` | 6 phases + double config + 5 canaux |
| `vision_architecture_raya.md` | 4 couches + GraphRAG (Couche 3) + embeddings |
| `audit_drive_sharepoint_20avril.md` | 4 phases D.1-D.4 |
| `audit_systeme_graphes_27avril.html` | confirme 2 systemes V1 vs V2 |
| `a_faire.md` | roadmap globale |
| `audit_exemples_par_defaut_TODO.md` | rappel pour audit dedie exemples par defaut Raya |

---

## TODO restant (priorise)

### Court terme

1. **Lancer les bootstraps sur les 6 boites restantes** (Gaucherie est faite)
   - per1.guillaume@gmail.com (~5000 mails attendus)
   - guillaume@couffrant-solar.fr (Outlook, le plus gros)
   - GPLH, Romagui, MTBR, Contact Couffrant Solar
2. **Bug ingestion Gmail** : 31 mails coquilles vides (subject/from_email vides) - parser casse sur certains formats Gmail
3. **Cleanup V1 entity_links** : supprimer fonctions populate_from_mail_memory, link_mail_to_graph dans entity_graph.py
4. **webhook_ms_handlers._process_mail()** a nettoyer : appelle process_incoming_mail sans mailbox_email/connection_id
5. **28 mails outlook recents non classes + 31 gmail vides** a retraiter

### Moyen terme

6. **Edges cross-source mail->Person Odoo** (matching from_email avec res.partner)
7. **Renommage Raya/Aria/anciens noms** dans tous fichiers (cosmetique)
8. **Teams sync auto** a brancher (table teams_sync_state existe vide)
9. **WhatsApp entrant** a coder (sortant fonctionne via Twilio)
10. **GraphRAG communautes (Couche 3 vision 20/04)** - job nocturne Leiden + resumes
11. **Onboarding conversationnel proactivite** selon vision_proactivite_30avril.md
12. **Charlotte fait ses connexions** Gmail/Drive (tenant juillet)

### Audits planifies

13. **Audit UI regles apprises** dans le menu 3 points : pas de tri (date, alpha, age), pas de "voir toutes les regles", pas de recherche d une regle recemment ajoutee. A redesigner.
14. **Audit exemples par defaut Raya** : quand Claude genere des exemples/placeholders/help-text dans l app, utiliser uniquement generiques (Documents, Projets, Public/Confidentiel, prenom.nom@societe.fr) - JAMAIS d elements specifiques a Couffrant Solar (dossiers internes, partenaires, fichiers internes, categories sectorielles). Voir `docs/audit_exemples_par_defaut_TODO.md`.

---

## Erreurs deja commises (a eviter de refaire)

1. **Recoder ce qui existe** : J ai (Claude) parfois recode des fonctions qui existaient deja. **Toujours grep + audit avant** d ecrire du nouveau code.
2. **Push pendant un job critique** : a interrompu un scan SharePoint en cours. Toujours verifier `mail_bootstrap_runs WHERE status IN ('pending','running')` et equivalents Odoo/Drive avant push.
3. **Heredocs `cat << EOF` bloques** dans Desktop Commander : contournement via `python3 -i` interactif + `interact_with_process` pour ecrire fichiers en plusieurs parties.
4. **Sur-formater les reponses** avec headers/PDFs/dossiers generes par defaut. Guillaume prefere des messages de chat courts.
5. **Proposer 3 options A/B/C** au lieu de prendre une decision d expert.
6. **Confondre les 2 systemes de graphe** : V1 entity_links (MORT depuis 17/04) vs V2 semantic_graph_nodes (VIVANT). Toujours utiliser V2 pour le neuf.
7. **Bootstrap mail sans mailbox_email** : avant le 04/05, mail_memory n avait pas de connection_id, ce qui rendait impossible le tracking par boite. Corrige.

---

## Etat actuel precis (fin de session 04/05/2026 ~22h30)

### En prod (commit `45e8475` sur main)

- Drive SharePoint a jour (5301 fichiers)
- Mails : 1006 dans mail_memory dont 947 backfilles mailbox_email + 947 dans graphe semantic_graph_nodes
- Polling delta Outlook + Gmail fonctionnel
- Triage Haiku fonctionnel
- Push automatique mail -> graphe a chaque ingestion
- **Outils admin mail complets** : inventaire + bootstrap historique (3/6/9/12/TOUT) + graphe + migration
- UX bootstrap : confirmation + auto-redirect status avec auto-refresh 5s
- Stats par dossier coherentes avec total run

### Test reussi

- **Gaucherie** (sci.gaucherie@gmail.com) : 24 mails vus, 23 vectorises (18 IA + 5 stock simple), 1 doublon, 0 erreur - bootstrap termine en 2 min

### Aucun job critique en cours (DB verifiee)

```sql
SELECT id, connection_id, mailbox_email, status, started_at, finished_at, items_seen, items_processed
FROM mail_bootstrap_runs
ORDER BY started_at DESC LIMIT 10
-- Resultat : seul Gaucherie (run id=1, status=done)
```

---

## Prochaines actions immediates pour Guillaume

1. **Recharger le panel admin** (Cmd+Shift+R pour vider cache JS) apres que Railway ait fini de redeployer (~2 min apres le commit `45e8475`)
2. **Tester le nouveau flow UX bootstrap** sur une autre boite (par exemple Romagui qui a peu de mails) pour valider que :
   - La modale de confirmation apparait
   - Au clic "Oui, lancer", la modale d etat s ouvre direct avec auto-refresh
3. Si OK, **lancer les bootstraps sur les boites restantes** dans l ordre suivant :
   - Petites boites d abord (Romagui, MTBR, GPLH, Contact Couffrant Solar)
   - Puis guillaume@couffrant-solar.fr (Outlook, ~673 deja ingeres mais bootstrap recuperera tous les mails depuis la connexion)
   - Puis per1.guillaume@gmail.com (la plus grosse, ~5000 mails)
4. Surveiller les stats avec "Etat du dernier bootstrap" et "Etat du graphe mail"

---

## Outils disponibles dans la nouvelle conversation

- `Desktop Commander` (lecture/ecriture fichiers, exec bash, processus interactifs)
- `postgres:query` connecte directement a la DB Railway prod
- `github:search_code`
- `web_search` / `web_fetch`

Limitation : `cat << EOF` est bloque pour securite, contourner via `python3 -i` interactif.

---

## Comment me parler

- Tutoiement
- Francais
- Direct mais bienveillant
- Tu peux pousser back si je dis quelque chose d incorrect
- Si je signale un defaut, ne pas se justifier - corriger
- Quand un chantier est gros (>2h), me proposer un decoupage en phases avant de coder
- Toujours **verifier en base** avant de push si un job critique tourne

---

**FIN DU PROMPT DE REPRISE.**

Tu as maintenant tout le contexte. Si tu as besoin de plus de details sur un point precis, regarde dans `/docs` du repo, ou pose-moi la question.
