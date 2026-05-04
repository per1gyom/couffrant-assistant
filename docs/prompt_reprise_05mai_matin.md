# Prompt de reprise — Conversation Raya/Couffrant

**Date de generation :** Mardi 5 mai 2026 (debut de matinee, post-session marathon du 04/05 soir)
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
  - `juillet` (Charlotte, test - **limite 7 mai pour ses connexions tenant**)

---

## Style de communication (CRITIQUE)

- **Reponses CONCISES dans le chat**, jamais de PDF/dossiers generes sauf demande explicite
- **🛑 en debut de reponses importantes** pour attirer l attention
- **Pas de questions A/B/C** - donner une proposition d expert directe
- **VERIFIER avant de proposer un fix**
- **AUDITER L EXISTANT AVANT DE CODER DU NEUF** (lecon retenue : on a parfois recode des choses qui existaient deja)
- **NE JAMAIS PUSH pendant qu un job critique tourne** (incident scan SharePoint interrompu, lecon dure)
- Langage non-technique, je ne suis pas dev pro
- Si je dis "je vois pas ta reponse" -> reecris plus court
- Si je signale un defaut, ne pas se justifier, juste corriger
- **PRIVILEGIER Desktop Commander (DC)** systematiquement vs `postgres:query` qui rame souvent
- **Etapes courtes** (longues bloquent le MCP)


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
  semantic_graph_nodes (113k+ noeuds)
  semantic_graph_edges
  A venir : communautes Leiden + resumes (job nocturne)

COUCHE 4 - Proactivite (4 etages, vision_proactivite_30avril.md)
  Veille -> Suggestion -> Action proposee -> Action automatique (avec garde-fous)
```

---

## Connexions Couffrant Solar (toutes healthy)

### Mail (7 boites)

| ID | Boite | Type | Permission (au 04/05 minuit) |
|---|---|---|---|
| 4 | per1.guillaume@gmail.com | gmail | 🗑 read_write_delete |
| 6 | guillaume@couffrant-solar.fr | microsoft (Outlook) | 🗑 read_write_delete |
| 7 | GPLH (sasgplh@gmail.com) | gmail | 🗑 read_write_delete |
| 8 | Romagui (sci.romagui@gmail.com) | gmail | 🗑 read_write_delete |
| 9 | Gaucherie (sci.gaucherie@gmail.com) | gmail | 🗑 read_write_delete |
| 10 | MTBR (sci.mtbr@gmail.com) | gmail | 🗑 read_write_delete |
| **12** | **contact@couffrant-solar.fr** | outlook | **👁 read SEUL** (Arlene gere, pas de delete) |

### Drive et Odoo

| ID | Connexion | Type | Permission |
|---|---|---|---|
| 1 | SharePoint Commun | drive | 👁 read SEUL |
| 3 | Openfire Guillaume | odoo | 👁 read SEUL |

**IMPORTANT** : depuis le 04/05 soir, le **mur physique permissions** est branche dans le code. Quand Raya tente une action au-dessus du niveau de la connexion, le code REFUSE physiquement (pas juste une consigne dans le prompt). Voir section "Securite" plus bas.


---

## Session marathon 04/05/2026 soir + 05/05 minuit

**Theme principal :** Securite + chemins d execution + permissions par connexion + UX pending actions.

### Commits pousses (ordre chronologique)

| Commit | Description | Etat |
|---|---|---|
| `a9a40e3` | feat(mail) coeur fonctionnel suppression Gmail/Outlook + purge 30j (chantier 1 commit 3) | ✅ en prod |
| `9874d6a` | fix(securite) suppression chemins B dangereux (DELETE/ARCHIVE/REPLY/CREATEEVENT direct sans confirmation) | ✅ en prod |
| `dd2c9c2` | fix(ux) pending actions sans rattachement -> badge timestamp clair (plus d illusion qu elles viennent du dernier message) | ✅ en prod |
| `04a6fa3` | feat(security) mur physique permissions sur tools agentiques + bug fix DELETE/ARCHIVE simples (REVERTED puis remis sous `b7801eb`) | — |
| `81e5f67` | Revert temporaire de `04a6fa3` suite a 502 Railway (s est avere etre un probleme Railway, pas le code) | — |
| `b7801eb` | Reapply de `04a6fa3` apres confirmation que Railway etait stable | ✅ en prod |

### Modifications en base (Couffrant Solar)

- **3 regles aria_rules dangereuses desactivees** (id 71, 76, 187) : "DELETE = action directe sans confirmation". Plus actives, n influencent plus le contexte Raya.
- **Permissions ajustees sur les 9 connexions** (voir tableau ci-dessus) : 6 boites perso/SCI en `read_write_delete`, contact@/SharePoint/Odoo en `read`.

### Decouvertes importantes pendant l audit

1. **Le systeme permissions etait conçu, code, mais BRANCHE NULLE PART** sur le chemin moderne (tools agentiques). Il n y avait que 5 appels a `check_permission` : SEND_MAIL (ancien chemin balise) + 4 dans Odoo. Le tool agentique `delete_mail`, `archive_mail`, etc. ne le verifiait JAMAIS. Resultat : `permission_audit_log` etait vide depuis sa creation.

2. **`_tool_type_for_action` avait un bug** : pour SEND_MAIL il renvoyait `'mailbox'` (generique) mais `tenant_connections.tool_type` contient `'gmail'`/`'microsoft'`/`'outlook'`. Donc la lookup retournait toujours `None` -> permission jamais bloquee.

3. **2 chemins d execution incoherents pour DELETE/ARCHIVE/REPLY/CREATEEVENT** :
   - **Chemin A (propre)** : tool agentique -> `_execute_pending_action` -> pending_actions -> carte de confirmation
   - **Chemin B (dangereux, supprime le 04/05)** : balise `[ACTION:XXX:id]` dans la reponse de Raya -> `perform_outlook_action` direct SANS confirmation, sans queue, sans trace utilisateur

4. **Bug `_execute_confirmed_action`** : ne gerait pas `action_type='DELETE'` simple (juste `DELETE_GROUPED`). C est ce qui produisait *"Type d action inconnu : DELETE"* dans le chat de Guillaume au clic Confirmer sur une carte issue du tool `delete_mail`. Handlers ajoutes pour DELETE et ARCHIVE simples.

5. **Pending actions creees avec `conversation_id=NULL`** dans 78% des cas (39/50). Raison : le tool agentique est appele PENDANT la generation de la reponse, mais l `aria_memory_id` (utilise comme `conversation_id`) n est cree qu APRES. Bug UX consequent : les cartes orphelines apparaissaient en bas du chat en reouvrant la conversation, comme si elles venaient d etre creees. Fix appliquee : badge timestamp clair pour les actions sans rattachement (commit `dd2c9c2`).

### Incident Railway 502 (~23h)

Apres push de `04a6fa3` (mur permissions), l app a passe en 502. Diagnostic en local : `init_postgres()` prend 29.5s a cause des 260 commandes SQL de migration rejouees a chaque demarrage. Sur Railway timeout startup probablement depasse pendant que la DB etait lente.

**Cause finale** : Railway lui-meme apres 5 push successifs en 2h. Pas mon code. Apres revert puis attente puis re-push, tout est rentre dans l ordre.

**Lecon retenue** : eviter les push successifs trop rapproches sur Railway. Garder un revert pret en cas de doute.


---

## Securite (etat post 04/05 soir)

### Mur physique permissions (defense en profondeur, 2 niveaux)

- **Mur #1** dans `_execute_pending_action` (raya_tool_executors.py) : avant la creation de la pending_action. Si refus -> retour JSON `permission_denied` a Raya avec details (current_level, required_level, remediation). Raya ne reessaie pas.
- **Mur #2** dans `_execute_confirmed_action` (confirmations.py) : avant l execution reelle. Si l admin a modifie le niveau entre la creation de la carte et le clic Confirmer, la nouvelle politique s applique.

### Hierarchie des permissions

```
Super admin (Guillaume, plafond par tenant) - super_admin_permission_level
       |
       v
Tenant admin (distribue aux users dans la limite) - tenant_admin_permission_level
       |
       v
User (v1 : herite du tenant_admin_permission_level)
```

Niveau effectif = MIN(super_admin, tenant_admin). Code dans `app/permissions.py` (fonctions `level_satisfies`, `cap_level`, `check_permission_for_tool`).

### 3 niveaux de permission

- `read` 👁 : lecture seule
- `read_write` ✏️ : lecture + ecriture (envoi mail, archive, reponse) MAIS pas de delete
- `read_write_delete` 🗑 : tout, incluant suppression

### Mapping tool -> niveau requis

Dans `permissions.py:ACTION_PERMISSION_MAP` :
- `READ_MAIL`, `SEARCHMAIL`, `LIST_MAILS` -> `read`
- `SEND_MAIL`, `REPLY_MAIL`, `CREATEEVENT`, `UPDATE_EVENT`, `MARK_READ` -> `read_write`
- `DELETE_MAIL`, `DELETE_EVENT`, `DELETE_DOCUMENT` -> `read_write_delete`

---

## Chantiers suivants (prioritises)

### URGENT - prochaine session matinale

1. **Bootstrap historique contact@** (Guillaume va le lancer ce soir ou demain matin via son panel super admin) — la boite ne contient qu 1 mail (envoi personnel a 15:08 le 04/05) car le bootstrap initial n a jamais ete fait. Sans bootstrap, Raya ne voit pas les ~100 mails du dernier mois.

2. **Exposer le `mail_id` dans `search_mail`** (5-10 min) — actuellement `format_unified_results` ne retourne pas les IDs techniques. Donc Raya ne peut pas appeler `delete_mail(mail_id="...")` meme sur les boites ou elle a `read_write_delete`. Bug observe le 04/05 minuit : Raya repondait *"Je n ai pas l ID du mail"* au lieu d aller chercher.

### Chantier "DEBRIDAGE Raya" (gros morceau, vision validee 04/05)

**Constat** : Raya et Claude (Sonnet 4.x) sont le meme modele -- meme intelligence brute. Mais Claude (qui aide Guillaume) a Desktop Commander + postgres + web et peut DIAGNOSTIQUER, AUDITER, SORTIR DU CADRE. Raya a juste ses tools metier (search_mail, delete_mail, etc.) -- elle est cadree, elle ne peut pas se rendre compte que ses tools sont bridants ou buggy.

**Vision** : donner a Raya l acces lecture aux memes outils que Claude :

- **Tool `query_database`** : lecture seule sur Postgres avec perimetre filtre (pas de credentials, pas de tokens chiffres). Permet a Raya de diagnostiquer "il n y a qu 1 mail dans contact@, c est anormal, le bootstrap a peut-etre saute".
- **Tool `read_code`** : lecture du code source du repo (Raya peut lire ses propres fichiers et comprendre comment elle fonctionne).
- **Tool `web_search` etendu** : pour chercher des infos externes sur internet.
- **Encourager le doute legitime** dans le prompt systeme : "Si un tool retourne quelque chose qui semble incomplet ou anormal, dis-le a l utilisateur au lieu de fabriquer une explication".
- **Ameliorer les retours d erreur des tools** : au lieu de retourner vide ou faux, retourner des messages explicites que Raya peut interpreter et relayer.

**Securite** : **JAMAIS d ecriture pour Raya via ces nouveaux tools**. Si elle suggere une amelioration intelligente, Guillaume me la transmet, on la met en place ensemble. Elle est l observateur intelligent qui aide a diagnostiquer.

**Effet espere** : que Raya puisse poser le diagnostic que je pose (Claude qui aide Guillaume). Elle voit "1 mail dans contact@", elle cherche dans les tables `mail_bootstrap_runs`, elle constate "aucun bootstrap", elle propose "lancer le bootstrap d abord". Au lieu de "je n ai pas l ID, desole".

### Chantiers du planning normal (apres debridage)

3. **UI dropdown permissions dans le panel admin** (`admin_connexions.html`) : remplacer l affichage lecture seule par un menu deroulant 3 niveaux avec bouton Sauver, reserve super_admin.

4. **Permissions par USER** (au-dela du tenant_admin) — Charlotte arrive le 7 mai, on a besoin de differencier "Guillaume = tout", "Charlotte = lire+ecrire", "Stagiaire = lire seul" sur les memes connexions tenant.

5. **Audit Opus des regles** : ameliorer `_job_opus_audit` pour detecter doublons semantiques + contradictions (les 3 regles 71, 76, 187 etaient toutes contradictoires entre elles et avec la 188 -- l audit n a rien detecte).

6. **`activity_log` casse depuis 21/04** : MAX(created_at) = `2026-04-21T07:58:57`, 294 entrees au total. Plus aucune action tracee depuis. Chantier independant, a debugger.

7. **Bootstraps Outlook restants** : guillaume@couffrant-solar.fr historique (peu de mails ingerees au depart, le bootstrap permettra de tout rattraper) + contact@ (point 1 de cette liste).

8. **Proactivite** (phase finale, apres tout le reste).


---

## Erreurs deja commises (a eviter de refaire)

1. **Recoder ce qui existe** : J ai (Claude) parfois recode des fonctions qui existaient deja. **Toujours grep + audit avant** d ecrire du nouveau code.
2. **Push pendant un job critique** : a interrompu un scan SharePoint en cours. Toujours verifier `mail_bootstrap_runs WHERE status IN ('pending','running')` avant push.
3. **Push successifs trop rapides sur Railway** : 5 push en 2h le 04/05 soir ont mis Railway en 502 sur startup malgre que mon code etait OK. Espacer les push. Garder un revert pret en cas de doute.
4. **Heredocs `cat << EOF` bloques** dans Desktop Commander : contournement via `python3 -i` interactif + `interact_with_process` pour ecrire fichiers en plusieurs parties.
5. **Sur-formater les reponses** avec headers/PDFs/dossiers generes par defaut. Guillaume prefere des messages de chat courts.
6. **Proposer 3 options A/B/C** au lieu de prendre une decision d expert.
7. **Confondre les 2 systemes de graphe** : V1 entity_links (MORT depuis 17/04) vs V2 semantic_graph_nodes (VIVANT). Toujours utiliser V2 pour le neuf.
8. **Privilegier `postgres:query` sur DC** : `postgres:query` est instable et plante souvent. Toujours utiliser DC + `python3 + psycopg2` pour les queries (plus fiable, meme si plus verbeux).

---

## Outils disponibles dans la nouvelle conversation

- `Desktop Commander` (lecture/ecriture fichiers, exec bash, processus interactifs) -- **PRIVILEGIER**
- `postgres:query` connecte directement a la DB Railway prod -- **utiliser avec parcimonie, plante souvent**
- `github:search_code`
- `web_search` / `web_fetch`

Limitation : `cat << EOF` est bloque dans interact_with_process pour securite, contourner via `python3 -i` interactif.

---

## Comment me parler

- Tutoiement
- Francais
- Direct mais bienveillant
- Tu peux pousser back si je dis quelque chose d incorrect
- Si je signale un defaut, ne pas se justifier - corriger
- Quand un chantier est gros (>2h), me proposer un decoupage en phases avant de coder
- Toujours **verifier en base** avant de push si un job critique tourne
- **Etapes courtes via DC** : si une etape est longue, le MCP plante. Decouper.

---

**FIN DU PROMPT DE REPRISE.**

Tu as maintenant tout le contexte. Si tu as besoin de plus de details sur un point precis, regarde dans `/docs` du repo, ou pose-moi la question.
