# Audit connecteurs tenants - 24 avril 2026

## Objectif

Permettre au super-admin (et plus tard aux users) de connecter
tres facilement depuis une page dediee /admin/connexions :
- Boite mail Gmail (Google)
- Boite mail Outlook (Microsoft 365)
- Google Drive (selection d un dossier racine)
- SharePoint (selection d un site)

## Ce qui existait deja

### Base de donnees
- Table tenant_connections complete OAuth ready :
  auth_type, credentials jsonb, status, connected_email, oauth_state
- Permissions 3 niveaux (super_admin / tenant_admin / previous)
- Table connection_assignments pour lier user a connexion
- 5 connexions operationnelles pour couffrant_solar

### Code backend
- app/routes/admin_oauth.py : flux OAuth super-admin Gmail + Microsoft
- app/connection_token_manager.py : module central des tokens
- app/routes/admin/super_admin.py : endpoints REST connexions
- app/routes/auth.py : _save_ms_token_v2 + _save_gmail_token_v2

### Connecteurs metier
- gmail_connector.py + gmail_auth.py : scopes complets
- outlook_connector.py + microsoft_connector.py
- google_drive_connector.py + drive_connector.py
- sharepoint_connector.py (utilise token MS)

### Decouverte importante
Sites.Read.All est deja dans GRAPH_SCOPES et le scope drive est
deja dans GMAIL_SCOPES. Donc SharePoint et Google Drive n ont PAS
besoin d un nouveau flux OAuth : ils reutilisent les tokens
Microsoft et Google existants.

## Ce qui a ete ajoute

### Commit 1/3 (cb0f887) - Backend pickers

**app/routes/admin_sharepoint.py (131 lignes)**
- GET /admin/sharepoint/sites/{tenant_id}
  -> Liste les sites via Graph /sites?search=*
  -> Utilise le token MS du super-admin
- POST /admin/sharepoint/select
  -> Cree tenant_connections (tool_type=sharepoint, auth_type=shared_ms)
  -> config : site_id + site_name + site_url
  -> status=connected directement

**app/routes/admin_drive.py (133 lignes)**
- GET /admin/drive/folders/{tenant_id}?parent_id=root
  -> Liste les dossiers via Drive API v3
  -> Navigation dans les sous-dossiers via parent_id
  -> Utilise le token Google du super-admin
- POST /admin/drive/select
  -> Cree tenant_connections (tool_type=drive, auth_type=shared_google)
  -> config : folder_id + folder_name + folder_url
  -> status=connected directement

**app/main.py** : import + include_router des 2 nouveaux

## Variables env Railway requises

### Microsoft (Azure AD App)
- TENANT_ID
- CLIENT_ID
- CLIENT_SECRET
- REDIRECT_URI = https://app.raya-ia.fr/auth/callback

### Google (OAuth2)
- GMAIL_CLIENT_ID
- GMAIL_CLIENT_SECRET
- GMAIL_REDIRECT_URI = https://app.raya-ia.fr/auth/gmail/callback

Les 7 variables sont probablement deja definies vu que 5 connexions
fonctionnent deja en prod (verifiees via postgres:query).

## Tests a executer

### Test 1 : Lister sites SharePoint
- Aller sur /admin/connexions
- Cliquer card SharePoint -> Connecter
- La modale doit lister tous les sites accessibles
- Utilise le token MS du super-admin via Graph /sites?search=*

### Test 2 : Choisir un dossier Drive
- Card Drive -> Connecter
- Modale liste les dossiers racine
- Bouton "Ouvrir >" pour naviguer en sous-dossier
- Confirmer -> nouvelle tenant_connections creee

### Test 3 : Connecter 2e boite Gmail
- Pour tester avec pierre_test par exemple
- Card Gmail -> + Connecter (a cote de celle existante)
- Flux OAuth Google complet
- Callback enregistre la nouvelle connexion

### Test 4 : Retirer une connexion
- Bouton Retirer avec confirmation
- DELETE /admin/connections/{id}
- Purge connection_assignments + tenant_connections

## Bilan

Ajout d un volet connexions complet en ~2h au lieu des 3-5j
estimes initialement, grace a la decouverte que :
- Sites.Read.All etait deja dans GRAPH_SCOPES
- Le scope drive etait deja dans GMAIL_SCOPES

Donc SharePoint et Drive reutilisent les tokens MS et Google
deja stockes, pas besoin d un nouveau flux OAuth.

3 commits atomiques :
1. cb0f887 backend sharepoint + drive
2. 0d0fa05 UI /admin/connexions
3. (ce commit) docs
