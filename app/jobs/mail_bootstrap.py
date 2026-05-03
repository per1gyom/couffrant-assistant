"""
Bootstrap historique d une boite mail (Outlook ou Gmail).

Recupere TOUS les mails depuis N mois en arriere (3/6/9/12 ou tous), reçus
ET envoyés (apprentissage du style d ecriture du user). Pour chaque mail :
  - filtre whitelist/blacklist
  - heuristique anti-bulk
  - triage Haiku (en quelques ms : ANALYSER / STOCKER_SIMPLE / IGNORER)
  - si pas IGNORER : insert dans mail_memory + push graphe

Le triage Haiku evite de vectoriser inutilement les newsletters et
notifications, ce qui rend le bootstrap viable economiquement meme sur
~5000 mails.

Le job tourne en thread daemon. Le state est persiste dans
mail_bootstrap_runs pour que l UI puisse afficher la progression et
pouvoir relancer en cas de crash.

Cree le 04/05/2026 - chantier B2 (mail admin tools).
"""
from __future__ import annotations
import threading
import time
import json
from datetime import datetime, timedelta, timezone
from typing import Optional
from app.database import get_pg_conn
from app.logging_config import get_logger

logger = get_logger("raya.mail_bootstrap")

OUTLOOK_FOLDERS = ["Inbox", "SentItems"]
GMAIL_LABELS = ["INBOX", "SENT"]
GRAPH_PAGE_SIZE = 50
GMAIL_PAGE_SIZE = 100
MAX_ITEMS_PER_RUN = 50000


def _create_run(connection_id: int, tenant_id: str, username: str,
                mailbox_email: str, months_back: int,
                include_sent: bool) -> Optional[int]:
    """Cree un run dans mail_bootstrap_runs. Retourne l id du run."""
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute(
            "INSERT INTO mail_bootstrap_runs "
            "(connection_id, tenant_id, username, mailbox_email, "
            "months_back, include_sent, status, started_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, 'running', NOW()) "
            "RETURNING id",
            (connection_id, tenant_id, username, mailbox_email,
             months_back, include_sent),
        )
        rid = c.fetchone()[0]
        conn.commit()
        return rid
    except Exception as e:
        logger.error("[MailBootstrap] _create_run echec : %s", str(e)[:200])
        return None
    finally:
        if conn:
            conn.close()


def _update_run(run_id: int, **fields) -> None:
    if not fields:
        return
    keys = list(fields.keys())
    values = [fields[k] for k in keys]
    set_clause = ", ".join(f"{k} = %s" for k in keys) + ", last_update = NOW()"
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute(f"UPDATE mail_bootstrap_runs SET {set_clause} WHERE id = %s",
                  (*values, run_id))
        conn.commit()
    except Exception as e:
        logger.warning("[MailBootstrap] _update_run echec : %s", str(e)[:200])
    finally:
        if conn:
            conn.close()


def _increment_run(run_id: int, **counters) -> None:
    if not counters:
        return
    set_parts = [f"{k} = COALESCE({k},0) + %s" for k in counters.keys()]
    set_clause = ", ".join(set_parts) + ", last_update = NOW()"
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute(f"UPDATE mail_bootstrap_runs SET {set_clause} WHERE id = %s",
                  (*counters.values(), run_id))
        conn.commit()
    except Exception:
        pass
    finally:
        if conn:
            conn.close()


def is_running(connection_id: int) -> bool:
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute(
            "SELECT 1 FROM mail_bootstrap_runs "
            "WHERE connection_id = %s AND status IN ('pending','running') LIMIT 1",
            (connection_id,))
        return c.fetchone() is not None
    except Exception:
        return False
    finally:
        if conn:
            conn.close()


def get_last_run(connection_id: int) -> Optional[dict]:
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute(
            "SELECT id, status, started_at, finished_at, last_update, "
            "months_back, include_sent, items_seen, items_processed, "
            "items_skipped_duplicate, items_filtered_haiku, "
            "items_stored_simple, items_analyzed, items_errors, "
            "estimated_total, error_detail, folders_done "
            "FROM mail_bootstrap_runs WHERE connection_id = %s "
            "ORDER BY started_at DESC LIMIT 1", (connection_id,))
        row = c.fetchone()
        if not row:
            return None
        return {
            "id": row[0], "status": row[1],
            "started_at": row[2].isoformat() if row[2] else None,
            "finished_at": row[3].isoformat() if row[3] else None,
            "last_update": row[4].isoformat() if row[4] else None,
            "months_back": row[5], "include_sent": row[6],
            "items_seen": row[7] or 0, "items_processed": row[8] or 0,
            "items_skipped_duplicate": row[9] or 0,
            "items_filtered_haiku": row[10] or 0,
            "items_stored_simple": row[11] or 0,
            "items_analyzed": row[12] or 0, "items_errors": row[13] or 0,
            "estimated_total": row[14], "error_detail": row[15],
            "folders_done": row[16] or {},
        }
    except Exception as e:
        logger.warning("[MailBootstrap] get_last_run : %s", str(e)[:200])
        return None
    finally:
        if conn:
            conn.close()


def _process_mail_via_pipeline(run_id: int, message_id: str, sender: str,
                                 subject: str, preview: str, raw_body: str,
                                 received_at: str, mailbox_source: str,
                                 mailbox_email: str, connection_id: int,
                                 username: str) -> str:
    from app.routes.webhook_ms_handlers import process_incoming_mail
    try:
        result = process_incoming_mail(
            username=username, sender=sender, subject=subject,
            preview=preview, message_id=message_id,
            received_at=received_at, mailbox_source=mailbox_source,
            raw_body=raw_body, mailbox_email=mailbox_email,
            connection_id=connection_id,
        )
        if result == "duplicate":
            _increment_run(run_id, items_skipped_duplicate=1)
        elif result == "ignored":
            _increment_run(run_id, items_filtered_haiku=1)
        elif result == "stored_simple":
            _increment_run(run_id, items_stored_simple=1, items_processed=1)
        elif result in ("done_ai", "fallback"):
            _increment_run(run_id, items_analyzed=1, items_processed=1)
        else:
            _increment_run(run_id, items_errors=1)
        return result or "error"
    except Exception as e:
        _increment_run(run_id, items_errors=1)
        logger.warning("[MailBootstrap] pipeline crash : %s", str(e)[:200])
        return "error"


def _bootstrap_outlook_folder(token: str, folder_name: str, since_iso: str,
                                run_id: int, username: str,
                                mailbox_email: str,
                                connection_id: int) -> dict:
    import requests
    GRAPH_BASE = "https://graph.microsoft.com/v1.0"
    url = f"{GRAPH_BASE}/me/mailFolders/{folder_name}/messages"
    params = {
        "$top": str(GRAPH_PAGE_SIZE),
        "$filter": f"receivedDateTime ge {since_iso}",
        "$orderby": "receivedDateTime desc",
        "$select": "id,subject,from,receivedDateTime,bodyPreview,body",
    }
    hdrs = {"Authorization": f"Bearer {token}"}
    # Detail par dossier : on aligne sur la semantique des compteurs globaux
    # du run pour eviter l incoherence (bug remonte par Guillaume 04/05) :
    # processed = ingere reellement (analyzed + stored_simple), pas les
    # doublons ni les filtres Haiku.
    stats = {"seen": 0, "processed": 0, "errors": 0,
             "duplicates": 0, "filtered_haiku": 0,
             "stored_simple": 0, "analyzed": 0}
    page_url = url
    page_params = params

    while page_url and stats["seen"] < MAX_ITEMS_PER_RUN:
        try:
            r = requests.get(page_url, params=page_params,
                             headers=hdrs, timeout=30)
            if r.status_code != 200:
                logger.warning("[MailBootstrap] Outlook %s status %d",
                               folder_name, r.status_code)
                stats["errors"] += 1
                break
            data = r.json()
        except Exception as e:
            logger.warning("[MailBootstrap] Outlook %s crash : %s",
                           folder_name, str(e)[:200])
            stats["errors"] += 1
            break

        messages = data.get("value", []) or []
        for msg in messages:
            stats["seen"] += 1
            _increment_run(run_id, items_seen=1)
            try:
                mid = msg.get("id")
                if not mid:
                    continue
                sender = (msg.get("from", {}) or {}).get(
                    "emailAddress", {}).get("address", "") or ""
                subject = msg.get("subject", "") or ""
                preview = msg.get("bodyPreview", "") or ""
                received_at = msg.get("receivedDateTime", "")
                raw_body = (msg.get("body", {}) or {}).get(
                    "content", "") or preview
                result = _process_mail_via_pipeline(
                    run_id=run_id, message_id=mid, sender=sender,
                    subject=subject, preview=preview, raw_body=raw_body,
                    received_at=received_at, mailbox_source="outlook",
                    mailbox_email=mailbox_email,
                    connection_id=connection_id, username=username)
                # Detail aligne sur la semantique du run total
                if result == "duplicate":
                    stats["duplicates"] += 1
                elif result == "ignored":
                    stats["filtered_haiku"] += 1
                elif result == "stored_simple":
                    stats["stored_simple"] += 1
                    stats["processed"] += 1
                elif result in ("done_ai", "fallback"):
                    stats["analyzed"] += 1
                    stats["processed"] += 1
                else:
                    stats["errors"] += 1
            except Exception as e:
                stats["errors"] += 1
                logger.warning("[MailBootstrap] Outlook msg crash : %s",
                               str(e)[:200])

        page_url = data.get("@odata.nextLink")
        page_params = None
        if page_url:
            time.sleep(0.2)

    return stats


def _run_bootstrap_outlook(run_id: int, connection_id: int,
                            tenant_id: str, username: str,
                            mailbox_email: str, months_back: int,
                            include_sent: bool) -> None:
    from app.token_manager import get_valid_microsoft_token
    try:
        token = get_valid_microsoft_token(username)
    except Exception as e:
        _update_run(run_id, status="error",
                    error_detail=f"Token Microsoft KO : {str(e)[:200]}",
                    finished_at=datetime.utcnow())
        return
    if not token:
        _update_run(run_id, status="error",
                    error_detail="Token Microsoft non disponible",
                    finished_at=datetime.utcnow())
        return

    if months_back > 0:
        since = datetime.now(timezone.utc) - timedelta(days=30 * months_back)
        since_iso = since.strftime("%Y-%m-%dT%H:%M:%SZ")
    else:
        since_iso = "1970-01-01T00:00:00Z"

    folders = ["Inbox"] if not include_sent else OUTLOOK_FOLDERS
    folders_done = {}
    for folder in folders:
        try:
            stats = _bootstrap_outlook_folder(
                token=token, folder_name=folder, since_iso=since_iso,
                run_id=run_id, username=username,
                mailbox_email=mailbox_email,
                connection_id=connection_id)
            folders_done[folder] = stats
            _update_run(run_id, folders_done=json.dumps(folders_done))
        except Exception as e:
            folders_done[folder] = {"error": str(e)[:200]}
            logger.error("[MailBootstrap] Outlook folder %s crash : %s",
                         folder, str(e)[:200])
    _update_run(run_id, status="done", finished_at=datetime.utcnow(),
                folders_done=json.dumps(folders_done))
    logger.info("[MailBootstrap] Outlook %s/%s done : %s",
                tenant_id, mailbox_email, folders_done)


def _bootstrap_gmail_label(token: str, label_id: str, after_str: str,
                             run_id: int, username: str,
                             mailbox_email: str,
                             connection_id: int) -> dict:
    import requests
    GMAIL_API = "https://gmail.googleapis.com/gmail/v1/users/me"
    list_url = f"{GMAIL_API}/messages"
    hdrs = {"Authorization": f"Bearer {token}"}
    # Detail par dossier aligne sur la semantique du run total
    # (cf commentaire identique dans _bootstrap_outlook_folder).
    stats = {"seen": 0, "processed": 0, "errors": 0,
             "duplicates": 0, "filtered_haiku": 0,
             "stored_simple": 0, "analyzed": 0}
    query = f"label:{label_id}"
    if after_str:
        query += f" after:{after_str}"
    page_token = None

    while stats["seen"] < MAX_ITEMS_PER_RUN:
        params = {"q": query, "maxResults": str(GMAIL_PAGE_SIZE)}
        if page_token:
            params["pageToken"] = page_token
        try:
            r = requests.get(list_url, params=params,
                             headers=hdrs, timeout=30)
            if r.status_code != 200:
                logger.warning("[MailBootstrap] Gmail %s status %d",
                               label_id, r.status_code)
                stats["errors"] += 1
                break
            data = r.json()
        except Exception as e:
            stats["errors"] += 1
            logger.warning("[MailBootstrap] Gmail %s crash : %s",
                           label_id, str(e)[:200])
            break

        message_ids = [m.get("id") for m in data.get("messages", [])
                       if m.get("id")]
        if not message_ids:
            break

        for msg_id in message_ids:
            stats["seen"] += 1
            _increment_run(run_id, items_seen=1)
            try:
                rmsg = requests.get(
                    f"{GMAIL_API}/messages/{msg_id}",
                    headers=hdrs,
                    # Fix 04/05 soir : metadataHeaders DOIT etre une liste
                    # Python (et non une string virgulee). requests envoie
                    # alors le param en multi-valeurs, format attendu par
                    # l API Gmail. Sinon le payload retourne ne contient
                    # AUCUN header (subject/from/date vides systemiquement).
                    params={"format": "metadata",
                            "metadataHeaders": ["From", "Subject", "Date"]},
                    timeout=20)
                if rmsg.status_code != 200:
                    stats["errors"] += 1
                    _increment_run(run_id, items_errors=1)
                    continue
                msg = rmsg.json()
                hh = {h["name"].lower(): h["value"]
                      for h in (msg.get("payload", {}) or {}).get("headers", [])}
                sender = hh.get("from", "") or ""
                subject = hh.get("subject", "") or ""
                received_at = hh.get("date", "")
                snippet = msg.get("snippet", "") or ""
                result = _process_mail_via_pipeline(
                    run_id=run_id, message_id=msg_id, sender=sender,
                    subject=subject, preview=snippet[:300], raw_body=snippet,
                    received_at=received_at, mailbox_source="gmail",
                    mailbox_email=mailbox_email,
                    connection_id=connection_id, username=username)
                if result == "duplicate":
                    stats["duplicates"] += 1
                elif result == "ignored":
                    stats["filtered_haiku"] += 1
                elif result == "stored_simple":
                    stats["stored_simple"] += 1
                    stats["processed"] += 1
                elif result in ("done_ai", "fallback"):
                    stats["analyzed"] += 1
                    stats["processed"] += 1
                else:
                    stats["errors"] += 1
            except Exception as e:
                stats["errors"] += 1
                _increment_run(run_id, items_errors=1)
                logger.warning("[MailBootstrap] Gmail msg crash : %s",
                               str(e)[:200])
            time.sleep(0.05)

        page_token = data.get("nextPageToken")
        if not page_token:
            break
        time.sleep(0.5)

    return stats


def _run_bootstrap_gmail(run_id: int, connection_id: int,
                          tenant_id: str, username: str,
                          mailbox_email: str, months_back: int,
                          include_sent: bool) -> None:
    from app.connection_token_manager import get_all_user_connections
    token = None
    try:
        for c in get_all_user_connections(username):
            if c.get("connection_id") == connection_id:
                token = c.get("token")
                break
    except Exception as e:
        _update_run(run_id, status="error",
                    error_detail=f"Lecture token KO : {str(e)[:200]}",
                    finished_at=datetime.utcnow())
        return
    if not token:
        _update_run(run_id, status="error",
                    error_detail="Token Gmail non disponible",
                    finished_at=datetime.utcnow())
        return

    if months_back > 0:
        since = datetime.now(timezone.utc) - timedelta(days=30 * months_back)
        after_str = since.strftime("%Y/%m/%d")
    else:
        after_str = ""

    labels = ["INBOX"] if not include_sent else GMAIL_LABELS
    labels_done = {}
    for label in labels:
        try:
            stats = _bootstrap_gmail_label(
                token=token, label_id=label, after_str=after_str,
                run_id=run_id, username=username,
                mailbox_email=mailbox_email,
                connection_id=connection_id)
            labels_done[label] = stats
            _update_run(run_id, folders_done=json.dumps(labels_done))
        except Exception as e:
            labels_done[label] = {"error": str(e)[:200]}
            logger.error("[MailBootstrap] Gmail label %s crash : %s",
                         label, str(e)[:200])
    _update_run(run_id, status="done", finished_at=datetime.utcnow(),
                folders_done=json.dumps(labels_done))
    logger.info("[MailBootstrap] Gmail %s/%s done : %s",
                tenant_id, mailbox_email, labels_done)


def start_bootstrap(connection_id: int, months_back: int = 12,
                     include_sent: bool = True) -> dict:
    """Lance un bootstrap historique en thread daemon.

    Args:
        connection_id : ID de tenant_connections
        months_back   : 3, 6, 9, 12 ou 0 (= tout)
        include_sent  : si True, parcourt aussi SentItems / SENT

    Returns:
        {status, run_id, message}
    """
    if is_running(connection_id):
        return {"status": "already_running",
                "message": "Un bootstrap est deja en cours pour cette connexion"}

    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute(
            "SELECT tenant_id, tool_type, connected_email "
            "FROM tenant_connections WHERE id = %s", (connection_id,))
        row = c.fetchone()
        if not row:
            return {"status": "error",
                    "message": f"Connexion {connection_id} introuvable"}
        tenant_id, tool_type, connected_email = row[0], row[1], row[2]
        c.execute(
            "SELECT username FROM user_tenant_access "
            "WHERE tenant_id = %s AND role IN ('owner','admin') "
            "ORDER BY (role='owner') DESC LIMIT 1", (tenant_id,))
        ur = c.fetchone()
        username = ur[0] if ur else None
    except Exception as e:
        return {"status": "error",
                "message": f"Lookup connexion KO : {str(e)[:200]}"}
    finally:
        if conn:
            conn.close()

    if not username:
        return {"status": "error",
                "message": f"Aucun owner pour le tenant {tenant_id}"}
    if not connected_email:
        return {"status": "error",
                "message": "connected_email vide sur cette connexion"}

    run_id = _create_run(connection_id, tenant_id, username,
                         connected_email, months_back, include_sent)
    if not run_id:
        return {"status": "error", "message": "Creation run echouee"}

    if tool_type in ("microsoft", "outlook"):
        target = _run_bootstrap_outlook
    elif tool_type == "gmail":
        target = _run_bootstrap_gmail
    else:
        _update_run(run_id, status="error",
                    error_detail=f"tool_type {tool_type} non supporte",
                    finished_at=datetime.utcnow())
        return {"status": "error",
                "message": f"tool_type {tool_type} non supporte"}

    t = threading.Thread(
        target=target,
        kwargs=dict(
            run_id=run_id, connection_id=connection_id,
            tenant_id=tenant_id, username=username,
            mailbox_email=connected_email,
            months_back=months_back, include_sent=include_sent),
        daemon=True, name=f"mail_bootstrap_{run_id}")
    t.start()

    logger.info("[MailBootstrap] Lance conn=%d (%s, %s, %s mois) run_id=%d",
                connection_id, tool_type, connected_email,
                months_back if months_back else "tous", run_id)
    return {"status": "started", "run_id": run_id,
            "message": f"Bootstrap demarre (run_id={run_id})"}
