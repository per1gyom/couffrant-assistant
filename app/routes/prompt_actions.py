"""
Construction du bloc actions disponibles injecte dans chaque prompt Raya.
Extrait de aria_context.py — REFACTOR-2.
"""


def build_actions_prompt(domains: list[str], tools: dict) -> str:
    sections = []
    sections.append("""=== SYNTAXE DES ACTIONS (usage interne uniquement, ne jamais montrer a l'utilisateur) ===
Quand l'utilisateur demande ce que tu sais faire, decris tes capacites en langage naturel.

Confirmation d'actions en attente :
  [ACTION:CONFIRM:id]  [ACTION:CANCEL:id]
Choix interactif :
  [ACTION:ASK_CHOICE:question|option1|option2|option3]""")

    if "mail" in domains:
        delete_line = "\n  [ACTION:DELETE:id] -> corbeille recuperable (direct, pas de confirmation)" if tools.get("mail_can_delete") else ""
        sections.append(f"""Mails :
  [ACTION:ARCHIVE:id] [ACTION:READ:id] [ACTION:READBODY:id]
  [ACTION:REPLY:id:texte] [ACTION:CREATE_TASK:titre]{delete_line}
  [ACTION:SEND_MAIL:boite|destinataire|sujet|corps]
    boite = adresse email exacte, 'gmail', 'microsoft', 'perso', 'pro', ou '' (auto)
    L'utilisateur dit "boite perso" / "Gmail" → 'gmail'
    L'utilisateur dit "boite pro" / "Outlook" → 'microsoft'
    Aucune indication → '' (premiere boite disponible)
    Mise en queue, necessite confirmation.
    Exemples : [ACTION:SEND_MAIL:|to@mail.fr|Objet|Corps]
               [ACTION:SEND_MAIL:gmail|to@mail.fr|Objet|Corps]
               [ACTION:SEND_MAIL:contact@entreprise.fr|client@mail.fr|Objet|Corps]
  [ACTION:SEARCH_CONTACTS:prenom nom] -> cherche dans TOUTES les boites connectees
    OBLIGATOIRE avant SEND_MAIL si tu ne connais pas l'email exact.
    Retourne nom, email et source ('microsoft'/'gmail').
  [ACTION:CREATE_CONTACT:Nom|email|telephone_opt] -> cree dans la boite la plus adaptee
Filtre mails : pour memoriser une regle de filtrage durable, utilise le tool remember_preference (categorie 'mail_filter').""")

    if "drive" in domains:
        drive_write_lines = "\n  [ACTION:CREATEFOLDER:parent_id|nom] [ACTION:MOVEDRIVE:item_id|dest_id|nom] [ACTION:COPYFILE:source_id|dest_id|nom]" if tools.get("drive_write") else ""
        sections.append(f"""Drive (tous les drives connectes — SharePoint, Google Drive, ...) :
  [ACTION:LISTDRIVE:] ou [ACTION:LISTDRIVE:drive|dossier_id]
    drive = 'sharepoint', 'google' ou vide (auto = premier disponible)
  [ACTION:READDRIVE:item_id] [ACTION:SEARCHDRIVE:query] ou [ACTION:SEARCHDRIVE:drive|query]{drive_write_lines}
  Recherche dans TOUS les drives si pas de drive specifie.""")

    if "teams" in domains:
        sections.append("""Teams — lecture (immediat) :
  [ACTION:TEAMS_LIST:]  [ACTION:TEAMS_CHANNEL:team_id|channel_id]
  [ACTION:TEAMS_CHATS:] [ACTION:TEAMS_READCHAT:chat_id]
Teams — envoi (mise en queue, confirmation requise) :
  [ACTION:TEAMS_MSG:email|texte]
  [ACTION:TEAMS_REPLYCHAT:chat_id|texte]
  [ACTION:TEAMS_SENDCHANNEL:team_id|channel_id|texte]
  [ACTION:TEAMS_GROUPE:email1,email2|sujet|texte]
Teams — memoire (immediat) :
  [ACTION:TEAMS_SYNC:chat_id|label?|type?]
  [ACTION:TEAMS_HISTORY:chat_id|label?|type?]
  [ACTION:TEAMS_MARK:chat_id|message_id|label?|type?]""")

    if "calendar" in domains:
        sections.append("""Calendrier (toutes boites connectees) :
  [ACTION:CREATEEVENT:sujet|debut_iso|fin_iso|lieu_opt|participants_opt|calendrier_opt]
    calendrier_opt = 'microsoft' ou 'gmail' (vide = premier disponible)
    Exemple : [ACTION:CREATEEVENT:Reunion Dupont|2026-04-17T14:00:00|2026-04-17T15:00:00|Paris|client@email.fr|microsoft]
  [ACTION:UPDATE_EVENT:event_id|champ=valeur]
    Exemples : title=Nouveau titre  ou  start=2026-04-17T15:00:00  ou  location=Lyon
  [ACTION:DELETE_EVENT:event_id|calendrier_opt]
  Ces actions necessitent confirmation avant execution.""")

    if "memory" in domains:
        sections.append("""Memoire :
  Pour memoriser : utilise le tool remember_preference.
  [ACTION:FORGET:id]  <- UNIQUEMENT si l'utilisateur demande EXPLICITEMENT d'oublier.
                         JAMAIS sur une correction. Corriger = appel a remember_preference avec la nouvelle valeur.
Onboarding :
  [ACTION:RESTART_ONBOARDING:] -> relance le questionnaire de configuration initiale""")

    sections.append("""Collaboration equipe (8-COLLAB) :
  [ACTION:SHARE_EVENT:type|titre|corps]
  -> partage un evenement avec tous les membres du tenant (immediat)
  Types valides : task_completed, document_modified, mail_important,
                  meeting_scheduled, milestone_reached, alert_shared
  Exemple : [ACTION:SHARE_EVENT:task_completed|Dossier Dupont finalisé|Raccordement validé et signé le 12/04]
  DECIDE TOI-MEME de partager si tu juges l'info utile pour l'equipe.
  Ne demande PAS de confirmation a l'utilisateur — partage directement.""")

    sections.append("""Lecture vocale :
  [SPEAK_SPEED:vitesse] -> change la vitesse de lecture (0.5=lent, 1.0=normal, 1.2=defaut, 1.5=rapide, 2.0=tres rapide)
  Exemples : l'utilisateur dit "lis plus vite" -> [SPEAK_SPEED:1.5]
             "relis ca plus lentement" -> [SPEAK_SPEED:0.8]
             "vitesse normale" -> [SPEAK_SPEED:1.0]
  La vitesse actuelle est memorisee cote navigateur.""")

    if tools.get("odoo_enabled"):
        odoo_write = ""
        if tools.get("odoo_access") == "full":
            odoo_write = """
  [ACTION:ODOO_CREATE:model|{"field":"value","field2":"value2"}]
  [ACTION:ODOO_UPDATE:model|record_id|{"field":"nouvelle_valeur"}]
  [ACTION:ODOO_NOTE:partner_id|texte de la note]"""
        sections.append(f"""Odoo (ERP) :
  [ACTION:SEARCH:question en langage naturel] -> NOUVEAU TAG MULTI-SOURCE
    Balaie EN PARALLELE toutes les memoires de Raya en une seule passe :
      - Odoo (clients, devis, factures, events, contacts, leads)
      - Drive SharePoint (fichiers, photos, PDF, docs techniques)
      - Mails analyses Outlook/Gmail
      - Historique des conversations
    Fusion RRF des resultats, reranking Cohere, enrichissement graphe.
    Chaque resultat est tague avec sa source (📋 odoo, 📁 drive, 📧 mail, 💬 conv).

    A utiliser quand la question peut avoir des elements de reponse dans PLUSIEURS
    sources, par exemple :
      [ACTION:SEARCH:dernieres echanges avec Legroux]
      [ACTION:SEARCH:ou en est le chantier Vauvelle]
      [ACTION:SEARCH:devis et photos AZEM onduleur SE100K]

    Filtre optionnel sur les sources via '|' :
      [ACTION:SEARCH:kit de fixation|drive] (uniquement Drive)
      [ACTION:SEARCH:Coullet|odoo,mail] (Odoo + mails uniquement)

  [ACTION:ODOO_SEMANTIC:requete en langage naturel] -> TON REFLEXE PAR DEFAUT pour TOUTE question impliquant Odoo
    C'est LE tag a utiliser EN PREMIER pour 90% des questions. Il combine :
      - Recherche dense (embeddings OpenAI sur nom, description, commentaires, lignes de devis)
      - Recherche sparse BM25 (termes exacts : noms propres, references produit type SE100K, noms de villes)
      - Reranking Cohere (precision +3-5 pts)
      - Traverse du graphe semantique (remonte les clients lies, devis, events, contacts en une seule passe)
    Retourne un contexte RICHE et exploitable. Le graphe te ramene automatiquement les relations (client d'un devis, contacts d'une entreprise, events lies a un projet).

    UTILISE-LE SYSTEMATIQUEMENT QUAND l'utilisateur mentionne :
      - Un nom propre de personne (meme si pas certain du lien avec Odoo)
      - Un nom d'entreprise, de lieu, de chantier
      - Un produit, materiel ou reference technique (SE100K, Tesla PW3, batterie lithium, etc.)
      - Un concept metier (photovoltaique, couverture, isolation, etc.)
      - Un sujet transversal ("clients dormants", "chantiers en retard", "RDV avec commentaires")

    Exemples concrets :
      [ACTION:ODOO_SEMANTIC:Francine Coullet]
      [ACTION:ODOO_SEMANTIC:devis avec onduleur SolarEdge SE100K]
      [ACTION:ODOO_SEMANTIC:chantiers AZEM onduleur SE100K]
      [ACTION:ODOO_SEMANTIC:RDV ou on a parle du kit de fixation]
      [ACTION:ODOO_SEMANTIC:clients a Tours]
      [ACTION:ODOO_SEMANTIC:leads interesses par batterie lithium]

    Filtre optionnel sur les modeles via '|' :
      [ACTION:ODOO_SEMANTIC:SE100K|sale.order]
      [ACTION:ODOO_SEMANTIC:probleme toiture|calendar.event,crm.lead]

    NE FAIS PAS d'ODOO_SEARCH classique en premier : ODOO_SEMANTIC est PLUS puissant et
    remonte le contexte relationnel (devis + clients + events lies), la ou ODOO_SEARCH
    ne retourne qu'une liste brute sans contexte.
  [ACTION:ODOO_CLIENT_360:nom_ou_id] -> VUE 360° APPROFONDIE D'UN CLIENT (apres ODOO_SEMANTIC)
    A UTILISER EN SECONDE PASSE, une fois que ODOO_SEMANTIC a identifie le bon client.
    Agrege contact + chantiers (sale.order) + devis + factures + paiements
    + leads CRM + tickets SAV + mails recents + indicateurs financiers
    (CA, encaisse, impayes, balance) + detection d'anomalies (factures
    annulees le meme jour qu'impayes, dormance, impayes significatifs).
    Workflow type :
      1. Utilisateur : "topo sur AZEM"
      2. Toi : [ACTION:ODOO_SEMANTIC:AZEM]  -> trouve le bon partner + contexte
      3. Toi (si pertinent) : [ACTION:ODOO_CLIENT_360:AZEM]  -> vue financiere approfondie
    Exemples :
      [ACTION:ODOO_CLIENT_360:AZEM]
      [ACTION:ODOO_CLIENT_360:SARL DES MOINES]
      [ACTION:ODOO_CLIENT_360:2501]
  [ACTION:ODOO_MODELS:] -> liste tous les modeles Odoo accessibles (pour exploration)
  [ACTION:ODOO_SEARCH:model|champ1,champ2,champ3|[["domain","=","filtre"]]]
    Exemples :
      Tous les contacts : [ACTION:ODOO_SEARCH:res.partner|name,email,phone|[]]
      Devis en cours : [ACTION:ODOO_SEARCH:sale.order|name,partner_id,amount_total,state|[["state","=","draft"]]]
      Factures impayees : [ACTION:ODOO_SEARCH:account.move|name,partner_id,amount_total,payment_state|[["payment_state","=","not_paid"],["move_type","=","out_invoice"]]]
      Projets actifs : [ACTION:ODOO_SEARCH:project.project|name,partner_id,date_start,date|[]]
      Taches d'un projet : [ACTION:ODOO_SEARCH:project.task|name,stage_id,date_deadline,user_ids|[["project_id","=",ID]]]
    Le domain suit la syntaxe Odoo : [["champ","operateur","valeur"]]. [] = tous les enregistrements.{odoo_write}
  Pour une exploration complete : commence par ODOO_MODELS, puis ODOO_SEARCH sur les modeles pertinents.
  Tu peux enchainer plusieurs ODOO_SEARCH dans la meme reponse pour croiser les donnees.
  PRIORITE : pour une vue client complete, utilise ODOO_CLIENT_360 plutot que des ODOO_SEARCH multiples.""")

    return "\n".join(sections)
