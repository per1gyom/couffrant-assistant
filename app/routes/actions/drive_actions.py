"""
Gestion des actions Drive (LISTDRIVE, READDRIVE, SEARCHDRIVE, CREATEFOLDER, MOVEDRIVE, COPYFILE).
7-ACT : log d'activite apres chaque action.
"""
import re
from app.connectors.drive_connector import (
    list_drive, read_drive_file, search_drive,
    create_folder, move_item, copy_item,
    _find_sharepoint_site_and_drive,
)
from app.pending_actions import queue_action
from app.activity_log import log_activity


def _handle_drive_actions(response, token, drive_write, username, tenant_id, conversation_id):
    confirmed = []
    # Vérifier si l'utilisateur peut faire des actions directes sur les fichiers
    from app.direct_actions import can_do_direct_actions
    direct_ok = can_do_direct_actions(username, tenant_id)

    for match in re.finditer(r'\[ACTION:LISTDRIVE:([^\]]*)]', response):
        subfolder = match.group(1).strip()
        try:
            r = list_drive(token, subfolder)
            if r.get("status") == "ok":
                lines = []
                for it in r.get("items", []):
                    icon = "\U0001f4c1" if it.get("type") == "dossier" else "\U0001f4c4"
                    size_str = f"  ({it.get('taille_ko','')} Ko)" if it.get("taille_ko") else ""
                    link = it.get("lien", "")
                    name = it['nom']
                    lines.append(f"  {icon} [**{name}**]({link}){size_str}" if link else f"  {icon} **{name}**{size_str}")
                confirmed.append(f"\U0001f5c2\ufe0f {r.get('dossier', '1_Photovoltaique')} ({r['count']}) :\n" + "\n".join(lines))
                log_activity(username, "drive_list", subfolder or "root", f"{r['count']} items", tenant_id=tenant_id)
            else:
                confirmed.append(f"\u274c {r.get('message', 'Erreur Drive')}")
        except Exception as e:
            confirmed.append(f"\u274c Drive : {str(e)[:80]}")

    for match in re.finditer(r'\[ACTION:READDRIVE:([^\]]+)\]', response):
        file_ref = match.group(1).strip()
        try:
            r = read_drive_file(token, file_ref)
            if r.get("status") == "ok":
                if r.get("type") == "texte":
                    confirmed.append(f"\U0001f4c4 {r['fichier']} :\n{r['contenu'][:2000]}")
                else:
                    link = r.get("lien", "")
                    name = r.get('fichier', file_ref)
                    confirmed.append(
                        f"\U0001f4c4 [{name}]({link}) \u2014 {r.get('message', '')} {r.get('conseil', '')}" if link
                        else f"\U0001f4c4 {name} \u2014 {r.get('message', '')} {r.get('conseil', '')}"
                    )
                log_activity(username, "drive_read", file_ref[:200], r.get('fichier', '')[:100], tenant_id=tenant_id)
            else:
                confirmed.append(f"\u274c {r.get('message')}")
        except Exception as e:
            confirmed.append(f"\u274c {str(e)[:80]}")

    for match in re.finditer(r'\[ACTION:SEARCHDRIVE:([^\]]+)\]', response):
        q = match.group(1).strip()
        try:
            r = search_drive(token, q)
            if r.get("status") == "ok":
                lines = []
                for it in r.get("items", []):
                    icon = "\U0001f4c1" if it.get('type') == 'dossier' else "\U0001f4c4"
                    link = it.get("lien", "")
                    name = it['nom']
                    lines.append(f"  {icon} [**{name}**]({link})" if link else f"  {icon} **{name}**")
                confirmed.append(f"\U0001f50d '{q}' \u2014 {r['count']} resultat(s) :\n" + "\n".join(lines))
                log_activity(username, "drive_search", q[:200], f"{r['count']} resultats", tenant_id=tenant_id)
            else:
                confirmed.append(f"\u274c {r.get('message')}")
        except Exception as e:
            confirmed.append(f"\u274c {str(e)[:80]}")

    if drive_write:
        for match in re.finditer(r'\[ACTION:CREATEFOLDER:([^|^\]]+)\|([^\]]+)\]', response):
            parent_id = match.group(1).strip()
            folder_name = match.group(2).strip()
            if direct_ok:
                # Action directe autorisée
                try:
                    _, drive_id, _ = _find_sharepoint_site_and_drive(token)
                    r = create_folder(token, parent_id, folder_name, drive_id)
                    if r.get("status") == "ok":
                        confirmed.append(f"\u2705 Dossier '{folder_name}' cree")
                        log_activity(username, "drive_create", folder_name[:200], parent_id[:100], tenant_id=tenant_id)
                    else:
                        confirmed.append(f"\u274c {r.get('message')}")
                except Exception as e:
                    confirmed.append(f"\u274c {str(e)[:80]}")
            else:
                # Action en queue — validation requise
                label = f"Creer dossier '{folder_name}'"
                action_id = queue_action(
                    tenant_id=tenant_id, username=username, action_type="CREATEFOLDER",
                    payload={"parent_id": parent_id, "folder_name": folder_name},
                    label=label, conversation_id=conversation_id,
                )
                confirmed.append(f"\u23f8\ufe0f Action #{action_id} en attente : {label}\n   Pour confirmer : dites \"confirme action {action_id}\"")

        for match in re.finditer(r'\[ACTION:MOVEDRIVE:([^|^\]]+)\|([^|^\]]+)\|?([^\]]*)\]', response):
            item_id = match.group(1).strip()
            dest_id = match.group(2).strip()
            new_name = match.group(3).strip() or None
            label = f"Deplacer '{item_id[:20]}' vers '{dest_id[:20]}'"
            action_id = queue_action(
                tenant_id=tenant_id, username=username, action_type="MOVEDRIVE",
                payload={"item_id": item_id, "dest_id": dest_id, "new_name": new_name},
                label=label, conversation_id=conversation_id,
            )
            confirmed.append(f"\u23f8\ufe0f Action #{action_id} en attente : {label}\n   Pour confirmer : dites \"confirme action {action_id}\"")

        for match in re.finditer(r'\[ACTION:COPYFILE:([^|^\]]+)\|([^|^\]]+)\|?([^\]]*)\]', response):
            source_id = match.group(1).strip()
            dest_id = match.group(2).strip()
            new_name = match.group(3).strip() or None
            label = f"Copier '{source_id[:20]}' vers '{dest_id[:20]}'"
            action_id = queue_action(
                tenant_id=tenant_id, username=username, action_type="COPYFILE",
                payload={"source_id": source_id, "dest_id": dest_id, "new_name": new_name},
                label=label, conversation_id=conversation_id,
            )
            confirmed.append(f"\u23f8\ufe0f Action #{action_id} en attente : {label}\n   Pour confirmer : dites \"confirme action {action_id}\"")

    return confirmed
