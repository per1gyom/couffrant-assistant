# Audit 4 — Robustesse du prompt v2 face à un autre métier

**Date** : 3 mai 2026 (nuit)
**Cible** : Charlotte / tenant `juillet` / agence événementielle B2B scénographique
**Question** : *Le prompt v2 et l'écosystème de tools peuvent-ils fonctionner pour un métier qui n'est pas le photovoltaïque ?*

---

## 🚨 Synthèse exécutive

```
RÉPONSE : NON, pas en l'état.

3 PROBLÈMES STRUCTURELS bloquants :

🔴 P1. Le prompt v2 hardcode "Couffrant Solar (photovoltaique,
       Romorantin-Lanthenay)" + nommage explicite Odoo + SharePoint
       → Charlotte va recevoir un prompt qui dit qu'elle bosse pour
         Couffrant et a accès à Odoo + SharePoint qu'elle n'a pas

🔴 P2. La fonction get_tools_for_user() retourne TOUS les tools sans
       filtrer par connecteurs actifs
       → Charlotte se voit proposer search_odoo, get_client_360,
         send_teams_message, alors qu'elle n'a aucun de ces connecteurs

🔴 P3. Les descriptions des tools mentionnent "SharePoint", "Outlook",
       "Cordialement, Guillaume" en dur

EN REVANCHE :
🟢 Le système de seeds par profil métier existe et fonctionne bien
   (vérifié en DB : Charlotte a 10 règles seedées pertinentes)
🟢 Le mécanisme de chargement des préférences via RAG est métier-
   indépendant
🟢 Les garde-fous généraux (sécurité, anti-injection) sont solides
```


---

## 1. Architecture du prompt v2 — analyse

### 1.1 Construction du prompt système

```
PIPELINE actuel (raya_agent_core.py):

1. _build_agent_system_prompt(username, tenant_id, display_name)
   → Hardcode "Couffrant Solar"  🔴

2. + _load_user_preferences(username, tenant_id, query)
   → RAG sémantique sur aria_rules
   → ✅ Métier-indépendant
   → Pour Charlotte : injecte ses 10 règles seedées (style direct,
     agence événementielle B2B, écosystème Google, etc.)

3. + global_instructions (depuis feedback_store)
   → ✅ Tenant-spécifique

4. + (optionnel) bloc MODE APPROFONDISSEMENT
   → 🟠 Mention "Sonnet 4.6, Odoo, mails, SharePoint"
```

### 1.2 Ce qui marche

```
✅ {display_name} chargé dynamiquement
✅ {tenant_id} passé partout
✅ Le RAG charge bien les règles propres au tenant
✅ Les outils sont passés à l'API Anthropic via tools=
✅ Les garde-fous (anti-injection, format markdown, style
   conversationnel) sont métier-indépendants
✅ Les pending_actions sont gérées tenant-spécifiquement
```

### 1.3 Ce qui ne marche pas

```
🔴 Le préambule "chez Couffrant Solar (photovoltaique...)" apparaît
   dans le prompt envoyé à Anthropic pour Charlotte

🔴 La phrase "Tu as acces a l ensemble des donnees de l entreprise
   via tes outils : Odoo (clients, devis, factures), SharePoint, ..."
   est hardcodée
   → Le prompt promet à Raya des outils qu'elle n'a pas
   → Si Charlotte demande "cherche dans Odoo", Raya appellera
     search_odoo qui plantera

🔴 L'exemple Mermaid utilise "SARL Des Moines / SCI Arrault Legroux"
   = montage juridique réel de Guillaume

🔴 Le mode Approfondissement Opus cite encore Odoo + SharePoint
```

---

## 2. Tools : analyse complète

### 2.1 Inventaire des 22 tools v2

| Tool | Métier-dépendant ? | Charlotte OK ? |
|------|---|---|
| search_graph | Non | ✅ Oui |
| search_odoo | OUI (Odoo) | ❌ Pas d'Odoo |
| get_client_360 | OUI (Odoo) | ❌ Pas d'Odoo |
| search_drive | Description "SharePoint" 🟠 | ⚠️ Marche si nommage neutre |
| search_mail | Non | ✅ Oui (Gmail) |
| search_conversations | Non | ✅ Oui |
| read_mail | Non | ✅ Oui |
| read_drive_file | "SharePoint" 🟠 | ⚠️ Idem |
| web_search | Non | ✅ Oui |
| get_weather | Default Romorantin | ⚠️ Désactivé en v2 |
| send_mail | Default "outlook" 🟠 | ⚠️ Charlotte = gmail |
| reply_to_mail | Non | ✅ Oui |
| archive_mail / delete_mail | Non | ✅ Oui |
| create_calendar_event | "Outlook" en dur 🟠 | ⚠️ Charlotte = Google |
| send_teams_message | OUI (Teams) | ❌ Pas de Teams |
| create_file/pdf/excel/image | Non | ✅ Oui |
| move_drive_file | "SharePoint" 🟠 | ⚠️ Idem |
| create_drive_folder | "SharePoint" 🟠 | ⚠️ Idem |
| remember_preference / forget_preference | Non | ✅ Oui |
| list_my_connections | Non | ✅ Oui |

```
RÉSUMÉ :
  ✅ Vraiment OK pour Charlotte : 12 tools sur 22
  ⚠️ Marche après nettoyage descriptions : 7 tools
  ❌ Doivent être retirés (pas de connecteur) : 3 tools
     search_odoo, get_client_360, send_teams_message
```

### 2.2 Le problème central : `get_tools_for_user`

**Code actuel** (raya_tools.py, ligne 555) :
```python
def get_tools_for_user(username, tenant_id):
    # TODO v2.1 : filtrer selon app.permissions et connexions actives
    return RAYA_TOOLS
```

🛑 **Le TODO est resté.** Tous les tools sont exposés.

**Conséquences pour Charlotte** :
- Raya voit `search_odoo` dans sa boîte à outils
- Si elle pense "client + devis = Odoo", elle appelle ce tool
- L'exécuteur retourne erreur ou plante silencieusement
- Raya s'embrouille et donne une mauvaise réponse

**Solution proposée** :
```python
def get_tools_for_user(username, tenant_id):
    from app.tenant_connections import get_active_tool_types
    active = get_active_tool_types(tenant_id)
    # Pour Charlotte : {"gmail", "google_drive", "google_calendar"}
    # Pour Guillaume : {"outlook", "gmail", "sharepoint", "odoo", "teams"}

    tools = []
    for tool in RAYA_TOOLS:
        name = tool["name"]
        if name in ("search_odoo", "get_client_360") and "odoo" not in active:
            continue
        if name == "send_teams_message" and "teams" not in active:
            continue
        if name in ("send_mail", "search_mail", "read_mail",
                    "reply_to_mail", "archive_mail", "delete_mail"):
            if not (active & {"outlook", "gmail"}):
                continue
        if name in ("search_drive", "read_drive_file",
                    "move_drive_file", "create_drive_folder"):
            if not (active & {"sharepoint", "google_drive", "onedrive"}):
                continue
        tools.append(tool)
    return tools
```

---

## 3. Le système de seeds par profil

### 3.1 Vérification en DB pour Charlotte

```
Charlotte (tenant=juillet) a 10 règles seedées :
  comportement  : 2  (style, manière de l'aider)
  métier        : 2  (artistique/scénographique B2B)
  outils        : 2  (Gmail, Google Drive, Lab Events)
  priorités     : 2  (gain de temps, tâches répétitives)
  style         : 2  (direct interne / littéraire externe)

Source : "onboarding" (pas seeding.py standard)
→ Suggère un onboarding personnalisé via conversation Raya
```

### 3.2 Profils standard (`seeding.py`)

```
Profils disponibles : pv_french, event_planner, generic, artisan,
immobilier, conseil, commerce, medical
```

Pour les futurs tenants, choisir le bon profil au moment du seed.

### 3.3 Diagnostic

```
🟢 Les règles seedées de Charlotte sont métier-pertinentes.
🟢 Le RAG va les charger correctement dans le prompt.

⚠️ MAIS si le prompt système dit "chez Couffrant Solar
   (photovoltaïque)" et les règles disent "agence événementielle B2B",
   Raya reçoit un signal contradictoire qui peut la troubler.
```

---

## 4. Tests mentaux : que se passerait-il pour Charlotte ?

### Scénario A : "Quels sont mes mails urgents ?"

```
1. Prompt v2 chargé : préambule "Couffrant Solar" 🔴
2. Règles RAG chargées : "agence événementielle B2B" ✅
3. Tools exposés : tous 🔴 (search_odoo inclus)
4. Raya appelle search_mail → ✅ retourne les mails Gmail
5. Raya répond avec les mails

VERDICT : ⚠️ Marche, mais préambule mensonger.
Si Charlotte signale "tu as dit Couffrant", elle perd confiance.
```

### Scénario B : "Cherche les devis du client Lacoste"

```
1. Raya pense : "client + devis = Odoo"
2. Raya appelle search_odoo(query="Lacoste devis")
3. Tool execute : pas de connecteur Odoo pour juillet → erreur
4. Raya peut :
   a. Comprendre et chercher ailleurs (search_drive, search_mail)
   b. Conclure "pas trouvé"
   c. Halluciner

VERDICT : 🔴 Comportement imprévisible.
Charlotte peut recevoir une mauvaise réponse alors que les infos
sont peut-être dans Gmail/Drive.
```

### Scénario C : "Envoie un mail à Pierre pour confirmer le RDV"

```
1. Raya appelle send_mail(to="pierre@...", body="...", provider="outlook")
2. Default = "outlook" → Charlotte n'a pas Outlook → erreur

VERDICT : 🔴 Échec. Default doit être dynamique selon tenant.
```

### Scénario D : "Fais un schéma de l'organisation pour le projet X"

```
1. Raya voit l'exemple Mermaid dans son prompt :
   "SARL Des Moines / SCI Arrault Legroux"
2. Risque : reproduction par accident des noms d'entités

VERDICT : 🟠 Risque d'hallucination des noms.
```

### Scénario E : "Météo demain pour le RDV en extérieur"

```
1. get_weather() default = "Romorantin-Lanthenay"
2. Charlotte reçoit la météo de Romorantin alors qu'elle est ailleurs

VERDICT : 🟠 Tool désactivé en v2 d'après commentaire, donc OK.
Si réactivé, à corriger.
```

---

## 5. Propositions structurelles

### 5.1 Court terme (avant Charlotte) — CRITIQUE

```
A. CRÉER UNE TABLE tenant_profile (ou tenants.metadata JSONB)
   Champs :
   - company_name      ("juillet", "Couffrant Solar")
   - activity_short    ("agence événementielle B2B")
   - location          ("Paris", "Romorantin-Lanthenay")
   - gender            ("feminin", "masculin", "neutre")
   - address_form      ("tutoiement", "vouvoiement")
   - default_outbound  ("gmail", "outlook")
   - connectors_blurb  ("Gmail, Google Drive, Google Agenda")

B. REFACTOR _build_agent_system_prompt
   Charger profile via tenant_id, l'injecter dans le f-string.
   Plus aucune mention en dur de Couffrant.

C. REFACTOR get_tools_for_user
   Filtrer dynamiquement selon les connecteurs actifs du tenant.
   3 tools à filtrer : search_odoo, get_client_360, send_teams_message.

D. NETTOYER les descriptions des tools Drive/Mail
   "SharePoint" → "Drive" générique.
   "Outlook par defaut" → phrasing dynamique.

E. NETTOYER les exemples du prompt
   - Mermaid SARL → exemple générique
   - Cordialement Guillaume → Cordialement [Prenom]
   - Email guillaume@couffrant → prenom.nom@societe.fr
```

### 5.2 Moyen terme (après tests Charlotte)

```
F. SYSTÈME DE PROMPT ADAPTATIF
   Construire dynamiquement la liste des sources accessibles
   selon les connecteurs actifs.

   Exemple Charlotte :
   "Tu as accès à : tes mails Gmail, ton Google Drive, tes
   conversations passées, le graphe sémantique, le web."

   Exemple Guillaume :
   "Tu as accès à : Odoo (clients, devis, factures), tes mails
   Outlook + Gmail, ton SharePoint, Teams, le graphe sémantique,
   l'historique des conversations, le web."

G. GLOSSAIRE MÉTIER PAR TENANT
   Charlotte n'utilise pas "raccordement" / "consuel" / "kWc".
   Elle utilise "scénographie" / "lieu" / "prestataire" / "Lab Events".
   Constituer un mini-glossaire au moment du seeding.
```

---

## 6. Plan d'action

### Phase 1 — Avant Charlotte (BLOQUANT)

```
JOUR 1 (4-6h)
  1. Migration DB : tenants.metadata JSONB (1h)
  2. Helper get_tenant_profile(tenant_id) (30 min)
  3. Refactor _build_agent_system_prompt (45 min)
  4. Refactor get_tools_for_user avec filtre (1h)
  5. Nettoyage descriptions tools (45 min)
  6. Nettoyage exemples prompt + guardrails (45 min)
  7. Tests bout-en-bout sur juillet (1h)
```

### Phase 2 — Avant 2e tenant test

```
JOUR 2-3 (2-3h)
  1. Construction dynamique de la liste des sources (1h)
  2. Glossaire métier basique (1h)
  3. Tests
```

---

## 7. Checklist de validation

Après implémentation de la Phase 1, vérifier :

```
☐ Charlotte se logue et reçoit le prompt v2
☐ Le system prompt Anthropic ne contient PLUS aucune mention de
  "Couffrant", "photovoltaique", "Romorantin", "ENEDIS", "Consuel"
☐ Les tools exposés à Charlotte excluent search_odoo,
  get_client_360, send_teams_message
☐ Charlotte peut envoyer un mail (default = gmail, pas outlook)
☐ Charlotte peut chercher dans son Drive (description = "Drive"
  pas "SharePoint")
☐ Demande un organigramme → exemple Mermaid neutre
☐ Météo → pas de fallback Romorantin (ou tool désactivé)
```

---

## 8. Conclusion

```
LE PROMPT V2 EST FONDAMENTALEMENT ROBUSTE pour la mécanique générale
(boucle agent, tool use, gardes-fous, RAG, graphage automatique,
archivage, oubli doux).

LE SYSTÈME DE SEEDS PAR PROFIL EST BIEN CONÇU et permet d'adapter
le métier sans toucher au code.

LES BIAIS sont concentrés dans :
1. Le préambule du prompt v2 (1 fichier, 5 lignes)
2. La fonction de filtrage des tools (1 fonction, 30 lignes)
3. Les descriptions de quelques tools (4 occurrences)

→ AVEC ~4 HEURES DE TRAVAIL CIBLÉ, Charlotte peut commencer à
  utiliser Raya dans des conditions correctes.

→ APRÈS ce sprint, on n'aura PAS un système 100% propre, mais on
  aura un système 90% utilisable. Les 10% restants (météo,
  branding email, code mort) peuvent attendre.

→ RECOMMANDATION : faire la Phase 1 dès demain en parallèle de tes
  propres ajustements.
```
