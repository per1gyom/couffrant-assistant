"""
Gestion des actions Drive (LISTDRIVE, READDRIVE, SEARCHDRIVE, CREATEFOLDER, MOVEDRIVE, COPYFILE).
Utilise drive_manager pour router vers SharePoint ou Google Drive automatiquement.
"""
import re
from app.pending_actions import queue_action
from app.activity_log import log_activity


def _get_drive(username: str, hint: str = ""):
    """Résout le drive à utiliser pour cet utilisateur."""
    try:
        from app.drive_manager import get_drive_for
        return get_drive_for(username, hint)
    except Exception:
        return None


def _handle_drive_actions(response, token, drive_write, username, tenant_id, conversation_id):
    confirmed = []
    from app.direct_actions import can_do_direct_actions
    direct_ok = can_do_direct_actions(username, tenant_id)

    for match in re.finditer(r'\[ACTION:LISTDRIVE:([^\]]*)]', response):
        # Format : [ACTION:LISTDRIVE:dossier] ou [ACTION:LISTDRIVE:drive:dossier]
        arg = match.group(1).strip()
        drive_hint, folder_id = ("", arg)
        if "|" in arg:
            parts = arg.split("|", 1)
            drive_hint, folder_id = parts[0].strip(), parts[1].strip()
        try:
            drive = _get_drive(username, drive_hint)
            if not drive:
                confirmed.append("❌ Aucun drive connecté.")
                continue
            items = drive.list(folder_id)
            if items:
                lines = [f"  {'📁' if i.item_type=='folder' else '📄'} [**{i.name}**]({i.url})" if i.url
                         else f"  {'📁' if i.item_type=='folder' else '📄'} **{i.name}**"
                         for i in items[:30]]
                confirmed.append(f"🗂️ {drive.display_name} ({len(items)}) :\n" + "\n".join(lines))
            else:
                confirmed.append(f"🗂️ {drive.display_name} — dossier vide.")
            log_activity(username, "drive_list", folder_id or "root", f"{len(items)} items", tenant_id=tenant_id)
        except Exception as e:
            confirmed.append(f"❌ Drive : {str(e)[:80]}")

    for match in re.finditer(r'\[ACTION:READDRIVE:([^\]]+)\]', response):
        file_ref = match.group(1).strip()
        try:
            drive = _get_drive(username)
            if not drive:
                confirmed.append("❌ Aucun drive connecté.")
                continue
            content = drive.read(file_ref)
            if content:
                confirmed.append(f"📄 Contenu :\n{content[:2000]}")
            else:
                # Essayer de trouver via search
                results = drive.search(file_ref)
                if results:
                    i = results[0]
                    link_text = f"[{i.name}]({i.url})" if i.url else i.name
                    confirmed.append(f"📄 {link_text}")
                else:
                    confirmed.append(f"❌ Fichier '{file_ref}' introuvable.")
            log_activity(username, "drive_read", file_ref[:200], "", tenant_id=tenant_id)
        except Exception as e:
            confirmed.append(f"❌ {str(e)[:80]}")

    for match in re.finditer(r'\[ACTION:SEARCHDRIVE:([^\]]+)\]', response):
        # Format : [ACTION:SEARCHDRIVE:query] ou [ACTION:SEARCHDRIVE:drive|query]
        arg = match.group(1).strip()
        drive_hint, query = ("", arg)
        if "|" in arg:
            parts = arg.split("|", 1)
            drive_hint, query = parts[0].strip(), parts[1].strip()
        try:
            from app.drive_manager import search_all_drives
            if drive_hint:
                drive = _get_drive(username, drive_hint)
                results = drive.search(query) if drive else []
                items = [{"name": i.name, "url": i.url, "type": i.item_type,
                          "source": i.source, "drive_label": i.drive_label} for i in results]
            else:
                items = search_all_drives(username, query)
            if items:
                lines = [f"  {'📁' if i['type']=='folder' else '📄'} [**{i['name']}**]({i['url']}) — {i.get('drive_label','')}"
                         if i.get('url') else f"  📄 **{i['name']}**"
                         for i in items[:20]]
                confirmed.append(f"🔍 '{query}' — {len(items)} résultat(s) :\n" + "\n".join(lines))
            else:
                confirmed.append(f"🔍 '{query}' — aucun résultat.")
            log_activity(username, "drive_search", query[:200], f"{len(items)} resultats", tenant_id=tenant_id)
        except Exception as e:
            confirmed.append(f"❌ {str(e)[:80]}")

    if drive_write:
        for match in re.finditer(r'\[ACTION:CREATEFOLDER:([^|^\]]+)\|([^\]]+)\]', response):
            parent_id = match.group(1).strip()
            folder_name = match.group(2).strip()
            if direct_ok:
                try:
                    drive = _get_drive(username)
                    if not drive:
                        confirmed.append("❌ Aucun drive connecté.")
                        continue
                    result = drive.create_folder(parent_id, folder_name)
                    if result.get("ok"):
                        confirmed.append(f"\u2705 Dossier '{folder_name}' cree")
                        log_activity(username, "drive_create", folder_name[:200], parent_id[:100], tenant_id=tenant_id)
                    else:
                        confirmed.append(f"\u274c {result.get('message', 'Erreur création dossier')}")
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
