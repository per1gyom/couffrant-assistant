"""Scanner Drive SharePoint - Phase D.1 (20/04/2026).

Applique le principe universel memoire 3 niveaux :
  Niveau 1 (meta) : 1 ligne par fichier avec resume 1 phrase
  Niveau 2 (detail) : chunks vectorises du contenu (100 pages max pour PDF)
  Niveau 3 (live) : re-fetch a la volee via read_drive_file (non stocke)

Le scan tourne en thread daemon sur Railway. Stocke son avancement en DB
pour permettre la reprise si Railway redemarre au milieu.

Le bouton 'Scanner Drive' du panel admin declenche launch_async().
"""

import io
import logging
import os
import threading
import time
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger("raya.drive_scanner")

# Limites techniques (voir docs/audit_drive_sharepoint_20avril.md pour
# les arbitrages valides avec Guillaume le 20/04)
MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024  # 50 Mo
MAX_PDF_PAGES_VECTORIZED = 100          # au-dela : niveau 1 seul + resume
MAX_TEXT_LENGTH_PER_CHUNK = 8000        # limite OpenAI embedding
SUPPORTED_EXTENSIONS = {"pdf", "docx", "doc", "xlsx", "xls", "txt", "md",
                         "csv", "json", "xml", "log", "jpg", "jpeg", "png"}

# Verrou global contre lancements concurrents
_scan_lock = threading.Lock()
_scan_running = False


def _get_graph_token(username: str) -> Optional[str]:
    """Recupere le token Microsoft Graph actif pour cet utilisateur.
    Utilise get_valid_microsoft_token qui gere le refresh automatique."""
    try:
        from app.token_manager import get_valid_microsoft_token
        return get_valid_microsoft_token(username)
    except Exception as e:
        logger.error("[DriveScanner] get_valid_microsoft_token failed : %s", str(e)[:200])
        return None


def _list_folder_recursive(token: str, drive_id: str, folder_id: str,
                            path_prefix: str = "") -> list:
    """Liste recursivement tous les fichiers d'un dossier SharePoint.
    Retourne une liste plate de dicts file_info."""
    import requests
    GRAPH = "https://graph.microsoft.com/v1.0"
    files = []
    url = f"{GRAPH}/drives/{drive_id}/items/{folder_id}/children"
    params = {"$top": 200,
              "$select": "id,name,size,folder,file,lastModifiedDateTime,webUrl"}

    while url:
        try:
            r = requests.get(url,
                             headers={"Authorization": f"Bearer {token}"},
                             params=params if url.endswith("/children") else None,
                             timeout=30)
            if not r.ok:
                logger.warning("[DriveScanner] list %s HTTP %d", folder_id, r.status_code)
                break
            data = r.json()
        except Exception as e:
            logger.error("[DriveScanner] list crash : %s", str(e)[:200])
            break

        for item in data.get("value", []):
            name = item.get("name", "")
            item_path = f"{path_prefix}/{name}" if path_prefix else name
            if "folder" in item:
                # Sous-dossier : descente recursive
                files.extend(_list_folder_recursive(
                    token, drive_id, item["id"], item_path))
            elif "file" in item:
                files.append({
                    "id": item["id"],
                    "name": name,
                    "path": item_path,
                    "size": item.get("size", 0),
                    "web_url": item.get("webUrl", ""),
                    "mime_type": item.get("file", {}).get("mimeType", ""),
                    "modified_at": item.get("lastModifiedDateTime", ""),
                })
        url = data.get("@odata.nextLink")
        params = None  # les nextLink contiennent deja leurs params
    return files


def _download_file(token_ref: list, username: str, drive_id: str,
                     file_id: str) -> Optional[bytes]:
    """Telecharge le contenu brut d un fichier SharePoint.

    Le token est passe dans une liste (token_ref) pour permettre sa mise a
    jour automatique : si on recoit un HTTP 401, on re-fetch un token frais
    et on retente. Les tokens Graph expirent apres 1h, or un scan Drive peut
    durer plusieurs heures.
    """
    import requests
    GRAPH = "https://graph.microsoft.com/v1.0"
    for attempt in range(2):
        token = token_ref[0]
        try:
            r = requests.get(f"{GRAPH}/drives/{drive_id}/items/{file_id}/content",
                             headers={"Authorization": f"Bearer {token}"},
                             timeout=60, allow_redirects=True)
            if r.status_code == 200:
                return r.content
            if r.status_code == 401 and attempt == 0:
                logger.info("[DriveScanner] HTTP 401 - refresh token en cours")
                new_token = _get_graph_token(username)
                if new_token and new_token != token:
                    token_ref[0] = new_token
                    continue
                logger.error("[DriveScanner] Refresh token echec - abandon")
                return None
            logger.warning("[DriveScanner] download HTTP %d pour %s",
                           r.status_code, file_id[:12])
            return None
        except Exception as e:
            logger.error("[DriveScanner] download crash : %s", str(e)[:200])
            return None
    return None


def _extract_text_from_file(file_bytes: bytes, filename: str,
                              mime_type: str = "") -> Optional[str]:
    """Utilise le module existant document_extractors pour extraire le texte.
    Gere PDF (avec fallback Claude pour les scans), DOCX, XLSX, images.

    Les .doc (format Word binaire legacy) ne sont pas supportes par
    python-docx, on les saute explicitement pour eviter les erreurs
    bruyantes (le meta niveau 1 est tout de meme cree par l appelant).
    """
    # Filtre .doc legacy - non supporte par python-docx
    if filename.lower().endswith(".doc"):
        logger.debug("[DriveScanner] .doc legacy non supporte : %s", filename)
        return None
    try:
        from app.scanner.document_extractors import extract_document_text
        return extract_document_text(
            content_bytes=file_bytes,
            filename=filename,
            mime_type=mime_type,
        )
    except Exception as e:
        logger.warning("[DriveScanner] extract %s failed : %s",
                       filename, str(e)[:200])
        return None


def _make_meta_summary(file_info: dict, extracted_text: Optional[str]) -> str:
    """Genere le resume meta (Niveau 1) - 1 phrase courte decrivant le fichier.
    Utilise les 500 premiers caracteres si disponibles, sinon les metadonnees."""
    name = file_info.get("name", "?")
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    size_kb = file_info.get("size", 0) // 1024
    path = file_info.get("path", "")

    # Ligne 1 : identite
    summary = f"Fichier {ext.upper()} '{name}' ({size_kb} Ko) dans {path}"

    # Ligne 2 : apercu contenu si disponible
    if extracted_text and len(extracted_text.strip()) > 20:
        preview = extracted_text.strip()[:300]
        preview = " ".join(preview.split())  # normalise whitespace
        summary += f" — Contenu : {preview}..."

    return summary[:1500]


def _chunk_text(text: str, max_len: int = MAX_TEXT_LENGTH_PER_CHUNK) -> list:
    """Decoupe un texte long en chunks de max_len caracteres, en essayant de
    couper sur les sauts de paragraphe ou de ligne."""
    if len(text) <= max_len:
        return [text]
    chunks = []
    remaining = text
    while len(remaining) > max_len:
        # Cherche un point de coupure propre dans les 200 derniers char
        split_zone = remaining[max_len - 200:max_len]
        for sep in ["\n\n", "\n", ". ", " "]:
            pos = split_zone.rfind(sep)
            if pos > 0:
                cut = max_len - 200 + pos + len(sep)
                chunks.append(remaining[:cut].strip())
                remaining = remaining[cut:]
                break
        else:
            # Pas de bon point : on coupe brutalement
            chunks.append(remaining[:max_len])
            remaining = remaining[max_len:]
    if remaining.strip():
        chunks.append(remaining.strip())
    return chunks


def _store_chunk(tenant_id: str, folder_id: int, file_info: dict,
                  level: int, chunk_index: int, text: str) -> bool:
    """Insere ou met a jour 1 chunk dans drive_semantic_content.
    Calcule l embedding OpenAI. Retourne True si OK.

    Gere le rate limit OpenAI avec backoff exponentiel (3 tentatives) :
    sur un scan de 3491 fichiers x ~6 chunks moyens = 20000+ appels embed,
    des pics de rate limit sont probables et doivent etre absorbes sans
    perdre les chunks.
    """
    try:
        from app.database import get_pg_conn
        from app.embedding import embed
        import json

        if not text or not text.strip():
            return False

        # Retry avec backoff sur rate limit OpenAI
        embedding = None
        for attempt in range(3):
            try:
                embedding = embed(text[:MAX_TEXT_LENGTH_PER_CHUNK])
                if embedding is not None:
                    break
            except Exception as e:
                err_str = str(e).lower()
                if "rate" in err_str or "429" in err_str or "throttl" in err_str:
                    wait = 2 ** attempt  # 1s, 2s, 4s
                    logger.info("[DriveScanner] Rate limit embed, retry dans %ds", wait)
                    time.sleep(wait)
                    continue
                logger.warning("[DriveScanner] embed exception : %s", str(e)[:150])
                break
        if embedding is None:
            logger.warning("[DriveScanner] embed None pour %s chunk %d",
                           file_info.get("name", "?"), chunk_index)
            return False
        vec_str = "[" + ",".join(str(x) for x in embedding) + "]"

        ext = file_info.get("name", "").rsplit(".", 1)[-1].lower() if "." in file_info.get("name", "") else ""

        with get_pg_conn() as conn:
            cur = conn.cursor()
            cur.execute(
                """INSERT INTO drive_semantic_content
                   (tenant_id, folder_id, file_id, file_name, file_path,
                    web_url, mime_type, file_ext, file_size_bytes,
                    level, chunk_index, content_type, text_content,
                    embedding, metadata, drive_modified_at, updated_at)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                           'document', %s, %s, %s, %s, NOW())
                   ON CONFLICT (tenant_id, file_id, level, chunk_index) DO UPDATE
                   SET text_content = EXCLUDED.text_content,
                       embedding = EXCLUDED.embedding,
                       file_path = EXCLUDED.file_path,
                       file_name = EXCLUDED.file_name,
                       drive_modified_at = EXCLUDED.drive_modified_at,
                       deleted_at = NULL,
                       updated_at = NOW()""",
                (tenant_id, folder_id, file_info["id"],
                 file_info["name"], file_info.get("path", ""),
                 file_info.get("web_url", ""), file_info.get("mime_type", ""),
                 ext, file_info.get("size", 0),
                 level, chunk_index, text[:MAX_TEXT_LENGTH_PER_CHUNK],
                 vec_str, json.dumps({}),
                 file_info.get("modified_at")),
            )
            conn.commit()
        return True
    except Exception as e:
        logger.error("[DriveScanner] store chunk failed : %s", str(e)[:300])
        return False


def _is_already_up_to_date(tenant_id: str, file_id: str,
                             drive_modified_iso: str) -> bool:
    """Renvoie True si ce fichier a deja ete vectorise avec succes ET
    qu il n a pas ete modifie depuis.

    Critere : il existe au moins 1 ligne level=1 en base, avec une
    drive_modified_at >= celle du fichier Drive. Cela permet :
    - De skipper les fichiers deja OK (gain massif sur rescan)
    - De retraiter automatiquement les fichiers en erreur (pas de ligne L1)
    - De retraiter les fichiers modifies (drive_modified_at plus recente)
    """
    if not drive_modified_iso:
        return False
    try:
        from app.database import get_pg_conn
        with get_pg_conn() as conn:
            cur = conn.cursor()
            cur.execute(
                """SELECT drive_modified_at FROM drive_semantic_content
                   WHERE tenant_id = %s AND file_id = %s AND level = 1
                     AND deleted_at IS NULL
                   LIMIT 1""",
                (tenant_id, file_id),
            )
            row = cur.fetchone()
        if not row or not row[0]:
            return False
        stored = row[0]
        # Odoo/Graph : "YYYY-MM-DDTHH:MM:SSZ" -> datetime
        drive_dt = datetime.fromisoformat(drive_modified_iso.replace("Z", "+00:00"))
        if stored.tzinfo is None:
            stored = stored.replace(tzinfo=timezone.utc)
        return stored >= drive_dt
    except Exception as e:
        logger.debug("[DriveScanner] check up_to_date failed : %s", str(e)[:150])
        return False


def _process_file(tenant_id: str, folder_db_id: int, token_ref: list,
                   username: str, drive_id: str, file_info: dict,
                   force_rescan: bool = False) -> dict:
    """Traite UN fichier : download + extract + chunk + store niveaux 1 et 2.
    Retourne un dict de stats.

    token_ref est une liste a 1 element [token] pour permettre le refresh
    automatique en cas de 401 (les tokens Graph expirent apres 1h).

    Si force_rescan=False (defaut) et que le fichier est deja a jour en DB
    (mtime Drive <= mtime stocke), on skip sans rien faire. Permet un
    rescan incremental tres rapide apres un premier scan complet.
    """
    name = file_info.get("name", "?")
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    size = file_info.get("size", 0)

    # Filtre taille
    if size > MAX_FILE_SIZE_BYTES:
        logger.info("[DriveScanner] SKIP %s : %.1f Mo > 50 Mo",
                    name, size / 1024 / 1024)
        return {"status": "skipped", "reason": "too_large", "file": name}

    # Filtre extension
    if ext not in SUPPORTED_EXTENSIONS:
        logger.debug("[DriveScanner] SKIP %s : ext %s non supportee", name, ext)
        return {"status": "skipped", "reason": "unsupported_ext", "file": name}

    # Scan incremental : skip si deja a jour
    if not force_rescan and _is_already_up_to_date(
            tenant_id, file_info["id"], file_info.get("modified_at", "")):
        return {"status": "skipped", "reason": "up_to_date", "file": name}

    # Download + extraction (token peut etre rafraichi in-place via token_ref)
    file_bytes = _download_file(token_ref, username, drive_id, file_info["id"])
    if not file_bytes:
        return {"status": "error", "reason": "download_failed", "file": name}

    extracted = _extract_text_from_file(file_bytes, name, file_info.get("mime_type", ""))

    # Niveau 1 : resume meta (toujours stocke, meme si extraction vide)
    meta = _make_meta_summary(file_info, extracted)
    _store_chunk(tenant_id, folder_db_id, file_info, level=1, chunk_index=0, text=meta)

    # Niveau 2 : chunks detailles si extraction reussie
    level2_count = 0
    if extracted and len(extracted.strip()) > 50:
        chunks = _chunk_text(extracted)
        for i, chunk in enumerate(chunks):
            if _store_chunk(tenant_id, folder_db_id, file_info,
                             level=2, chunk_index=i, text=chunk):
                level2_count += 1

    logger.info("[DriveScanner] OK %s : L1=1 + L2=%d chunks",
                name, level2_count)
    return {"status": "ok", "file": name,
            "level1_chunks": 1, "level2_chunks": level2_count}


def _save_progress(folder_db_id: int, stats: dict):
    """Persiste l avancement dans drive_folders.last_scan_stats pour que le
    dashboard puisse l afficher et pour permettre la reprise si besoin."""
    import json
    try:
        from app.database import get_pg_conn
        with get_pg_conn() as conn:
            cur = conn.cursor()
            cur.execute(
                """UPDATE drive_folders
                   SET last_scan_stats = %s, updated_at = NOW()
                   WHERE id = %s""",
                (json.dumps(stats), folder_db_id),
            )
            conn.commit()
    except Exception as e:
        logger.error("[DriveScanner] save progress failed : %s", str(e)[:200])


def _ensure_folder_registered(tenant_id: str, token: str) -> Optional[dict]:
    """Utilise la config SharePoint du tenant pour localiser le dossier cible,
    l enregistre dans drive_folders s il ne l est pas encore, et retourne
    un dict avec folder_db_id, drive_id, folder_id, etc.
    """
    from app.connectors.drive_connector import (
        get_drive_config, _find_sharepoint_site_and_drive, _find_folder_root,
    )
    from app.database import get_pg_conn

    config = get_drive_config(tenant_id)
    if not config.get("configured"):
        return None

    site_name = config["site_name"]
    folder_name = config["folder_name"]

    _, drive_id, _ = _find_sharepoint_site_and_drive(token, config)
    if not drive_id:
        logger.error("[DriveScanner] SharePoint drive introuvable")
        return None
    folder_path, folder_id = _find_folder_root(token, drive_id, config)
    if not folder_id:
        logger.error("[DriveScanner] Dossier %s introuvable", folder_name)
        return None

    with get_pg_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO drive_folders
               (tenant_id, provider, folder_name, site_name, drive_id,
                folder_id, folder_path, enabled, updated_at)
               VALUES (%s, 'sharepoint', %s, %s, %s, %s, %s, TRUE, NOW())
               ON CONFLICT (tenant_id, provider, folder_name) DO UPDATE
               SET drive_id = EXCLUDED.drive_id,
                   folder_id = EXCLUDED.folder_id,
                   folder_path = EXCLUDED.folder_path,
                   enabled = TRUE, updated_at = NOW()
               RETURNING id""",
            (tenant_id, folder_name, site_name, drive_id, folder_id, folder_path),
        )
        folder_db_id = cur.fetchone()[0]
        conn.commit()
    return {"folder_db_id": folder_db_id, "drive_id": drive_id,
            "folder_id": folder_id, "folder_name": folder_name,
            "folder_path": folder_path, "site_name": site_name}


def _run_scan(tenant_id: str, username: str, force_rescan: bool = False):
    """Thread principal du scan. Liste recursivement le dossier SharePoint,
    traite chaque fichier, stocke stats, nettoie l etat a la fin.

    Si force_rescan=True : re-traite meme les fichiers deja a jour en DB.
    Par defaut False = scan incremental (rapide apres un 1er passage).
    """
    global _scan_running
    from app.database import get_pg_conn

    try:
        logger.info("[DriveScanner] ===== DEMARRAGE tenant=%s =====", tenant_id)
        token = _get_graph_token(username)
        if not token:
            logger.error("[DriveScanner] Pas de token Microsoft actif pour %s", username)
            return

        folder = _ensure_folder_registered(tenant_id, token)
        if not folder:
            logger.error("[DriveScanner] Config SharePoint absente ou invalide")
            return

        logger.info("[DriveScanner] Cible : %s > %s",
                    folder["site_name"], folder["folder_name"])
        files = _list_folder_recursive(token, folder["drive_id"],
                                         folder["folder_id"])
        total = len(files)
        logger.info("[DriveScanner] %d fichiers detectes", total)

        stats = {"started_at": datetime.now(timezone.utc).isoformat(),
                 "total_files": total, "processed": 0, "ok": 0,
                 "skipped": 0, "errors": 0,
                 "level1_chunks": 0, "level2_chunks": 0}
        _save_progress(folder["folder_db_id"], stats)

        # token_ref mutable pour permettre le refresh in-place sur HTTP 401
        token_ref = [token]
        # Refresh proactif : re-fetch un token frais toutes les 30 min
        # pour ne jamais laisser expirer en cours de scan
        last_refresh = time.time()

        for i, f in enumerate(files):
            # Refresh proactif toutes les 30 min (1800s)
            if time.time() - last_refresh > 1800:
                fresh = _get_graph_token(username)
                if fresh:
                    token_ref[0] = fresh
                    last_refresh = time.time()
                    logger.info("[DriveScanner] Token refresh proactif OK")
            try:
                result = _process_file(tenant_id, folder["folder_db_id"],
                                        token_ref, username,
                                        folder["drive_id"], f,
                                        force_rescan=force_rescan)
                stats["processed"] += 1
                if result["status"] == "ok":
                    stats["ok"] += 1
                    stats["level1_chunks"] += result.get("level1_chunks", 0)
                    stats["level2_chunks"] += result.get("level2_chunks", 0)
                elif result["status"] == "skipped":
                    stats["skipped"] += 1
                else:
                    stats["errors"] += 1
            except Exception as e:
                stats["errors"] += 1
                logger.error("[DriveScanner] CRASH sur %s : %s",
                             f.get("name", "?"), str(e)[:200])

            # Sauvegarde progression tous les 10 fichiers
            if (i + 1) % 10 == 0:
                stats["last_update"] = datetime.now(timezone.utc).isoformat()
                _save_progress(folder["folder_db_id"], stats)
                logger.info("[DriveScanner] Progression %d/%d (ok=%d skip=%d err=%d)",
                            i + 1, total, stats["ok"], stats["skipped"], stats["errors"])

            # Micro-pause entre fichiers pour lisser la charge OpenAI
            # embed (5000 rpm) et Graph download (10k req / 10 min).
            # 100 ms = max 10 fichiers/s = tres en-dessous des limites.
            time.sleep(0.1)

        stats["finished_at"] = datetime.now(timezone.utc).isoformat()
        _save_progress(folder["folder_db_id"], stats)

        # Marque le last_full_scan_at
        with get_pg_conn() as conn:
            cur = conn.cursor()
            cur.execute(
                "UPDATE drive_folders SET last_full_scan_at = NOW() WHERE id = %s",
                (folder["folder_db_id"],),
            )
            conn.commit()

        logger.info("[DriveScanner] ===== TERMINE tenant=%s : %d ok, %d skip, %d err =====",
                    tenant_id, stats["ok"], stats["skipped"], stats["errors"])
    finally:
        with _scan_lock:
            _scan_running = False


def launch_async(tenant_id: str = "couffrant_solar", username: str = None,
                  force_rescan: bool = False) -> dict:
    """Declenche le scan Drive en thread daemon. Retourne immediatement.
    Appele par le bouton Scanner Drive du panel admin.

    Si aucun username fourni, prend APP_USERNAME de l env (Guillaume).

    Si force_rescan=True : retraite TOUS les fichiers meme deja OK en DB.
    Sinon (defaut) : scan incremental - skip les fichiers deja a jour.
    """
    global _scan_running
    if username is None:
        username = os.getenv("APP_USERNAME", "guillaume").strip()

    with _scan_lock:
        if _scan_running:
            return {"status": "already_running",
                    "message": "Un scan Drive est deja en cours."}
        _scan_running = True

    t = threading.Thread(
        target=_run_scan, args=(tenant_id, username, force_rescan),
        name="drive-scanner", daemon=True,
    )
    t.start()
    mode = "force_rescan=all" if force_rescan else "incremental"
    logger.info("[DriveScanner] Thread lance tenant=%s user=%s mode=%s",
                tenant_id, username, mode)
    return {
        "status": "started",
        "tenant_id": tenant_id,
        "mode": mode,
        "message": f"Scan Drive lance ({mode}). Suivi via le bouton Drive du panel.",
    }


def is_running() -> bool:
    with _scan_lock:
        return _scan_running


def get_last_scan_stats(tenant_id: str) -> dict:
    """Recupere les stats du dernier scan pour affichage UI."""
    from app.database import get_pg_conn
    try:
        with get_pg_conn() as conn:
            cur = conn.cursor()
            cur.execute(
                """SELECT folder_name, last_full_scan_at, last_scan_stats,
                          enabled, folder_path
                   FROM drive_folders
                   WHERE tenant_id = %s
                   ORDER BY updated_at DESC""",
                (tenant_id,),
            )
            rows = cur.fetchall()
        return {"status": "ok", "folders": [
            {"folder_name": r[0],
             "last_full_scan_at": r[1].isoformat() if r[1] else None,
             "stats": r[2] or {},
             "enabled": r[3], "folder_path": r[4]}
            for r in rows
        ], "scan_running": is_running()}
    except Exception as e:
        return {"status": "error", "message": str(e)[:300]}
