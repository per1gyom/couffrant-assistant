"""
Construction du bloc actions disponibles injecte dans chaque prompt Raya.
Extrait de aria_context.py — REFACTOR-2.
"""


def build_actions_prompt(domains: list[str], tools: dict) -> str:
    sections = []
    sections.append("""=== ACTIONS DISPONIBLES (SYNTAXE INTERNE — NE JAMAIS MONTRER A L'UTILISATEUR) ===
REGLE ABSOLUE : Ces codes entre crochets sont UNIQUEMENT pour ton usage interne.
Tu ne dois JAMAIS les afficher, les citer ni les mentionner dans tes réponses.
Quand l'utilisateur demande ce que tu sais faire, décris tes capacités en langage naturel :
- "Je peux lire, envoyer et archiver tes mails"
- "Je peux chercher et créer des fichiers sur le Drive"
- "Je retiens tes préférences et j'apprends de nos échanges"
JAMAIS : "[ACTION:LEARN]", "[ACTION:ARCHIVE:id]", "[SPEAK_SPEED:X]" etc.

Confirmation des actions en attente :
  [ACTION:CONFIRM:id]  -> execute une action sensible mise en queue
  [ACTION:CANCEL:id]   -> annule une action sensible mise en queue
Interactif (immediat) :
  [ACTION:ASK_CHOICE:question|option1|option2|option3]
  -> affiche des boutons de choix cliquables dans le chat (2 a 4 options)""")

    if "mail" in domains:
        delete_line = "\n  [ACTION:DELETE:id] -> corbeille recuperable (direct, pas de confirmation)" if tools.get("mail_can_delete") else ""
        sections.append(f"""Mails :
  [ACTION:ARCHIVE:id] [ACTION:READ:id] [ACTION:READBODY:id]
  [ACTION:REPLY:id:texte] [ACTION:CREATEEVENT:sujet|debut_iso|fin_iso|participants]
  [ACTION:CREATE_TASK:titre]{delete_line}
  [ACTION:SEND_MAIL:destinataire@email.fr|sujet|corps] -> envoyer un NOUVEAU mail (pas une reponse)
    Exemple : [ACTION:SEND_MAIL:per1.guillaume@gmail.com|Test Raya|Bonjour, ceci est un test.]
    -> met en queue + confirmation requise avant envoi (l'utilisateur peut aussi choisir "Brouillon")
Filtre mails :
  [ACTION:LEARN:mail_filter|autoriser: email@domaine.fr]
  [ACTION:LEARN:mail_filter|bloquer: promo@xyz.fr]""")

    if "drive" in domains:
        drive_write_lines = "\n  [ACTION:CREATEFOLDER:parent|nom] [ACTION:MOVEDRIVE:item|dest|nom] [ACTION:COPYFILE:source|dest|nom]" if tools.get("drive_write") else ""
        sections.append(f"""Drive (1_Photovoltaique) — resultat : lien cliquable :
  [ACTION:LISTDRIVE:] [ACTION:LISTDRIVE:id] [ACTION:READDRIVE:id] [ACTION:SEARCHDRIVE:mot]{drive_write_lines}""")

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
        sections.append("""Calendrier :
  [ACTION:CREATEEVENT:sujet|debut_iso|fin_iso|participants]""")

    if "memory" in domains:
        sections.append("""Memoire (immediat) :
  [ACTION:LEARN:ta_categorie|ta_regle]   <- UNE SEULE IDEE PAR REGLE
  [ACTION:INSIGHT:sujet|observation]
  [ACTION:FORGET:id]  <- UNIQUEMENT si l'utilisateur demande EXPLICITEMENT d'oublier.
                         JAMAIS sur une correction. Corriger = [ACTION:LEARN] avec la nouvelle valeur.
  [ACTION:SYNTH:]
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

    return "\n".join(sections)
