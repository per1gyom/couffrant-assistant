"""
Mail Outlook Delta Sync — nouveau systeme de synchronisation mails Outlook.

Phase Connexions Universelles - Semaine 3 (1er mai 2026).
Voir docs/vision_connexions_universelles_01mai.md.

OBJECTIF :
─────────────────────────────────────────────────────────────
Remplacer l architecture webhook actuelle (fragile, cause du bug
17 jours du 14/04 au 01/05) par un polling delta universel coherent
avec ce qui est fait pour Odoo Semaine 2.

ARCHITECTURE (4 niveaux du doc vision section 2 - Pattern delta sync) :
  NIVEAU 1 - polling delta toutes les 5 min          ← CE MODULE
  NIVEAU 2 - webhook accelerateur (Etape 3.6 future)
  NIVEAU 3 - Lifecycle Notifications (Etape 3.5)
  NIVEAU 4 - reconciliation nocturne (Etape 3.7)

FOLDERS SURVEILLES (decision Q1 + bug 17 jours) :
  - Inbox       : mails entrants
  - SentItems   : mails sortants (INVISIBLE dans le webhook actuel !)
  - JunkEmail   : rattrapage spam mal classe

DEUX MODES DE FONCTIONNEMENT (variables Railway) :
─────────────────────────────────────────────────────────────

  MODE 1 : ACTIVATION DU JOB
    Variable : SCHEDULER_OUTLOOK_DELTA_SYNC_ENABLED
    Defaut : FALSE (job pas execute)
    Si TRUE : le job tourne toutes les 5 min

  MODE 2 : COMPORTEMENT (shadow vs write)
    Variable : OUTLOOK_DELTA_SYNC_WRITE_MODE
    Defaut : FALSE (shadow mode = pas d ecriture dans mail_memory)
    Si TRUE : appelle process_incoming_mail pour chaque message
              -> ecrit dans mail_memory comme le webhook
              -> coexistence avec le webhook (UPSERT via mail_exists)

PROTOCOLE DE BASCULE PROPRE (decision doc vision) :
─────────────────────────────────────────────────────────────
Etape A : Activer SCHEDULER_OUTLOOK_DELTA_SYNC_ENABLED=true
          -> Le job tourne en SHADOW MODE
          -> Verifier dans /admin/health/page que Outlook apparait healthy
          -> Verifier dans connection_health_events que items_seen > 0
          -> Comparer items_new avec ce que le webhook ingere
          -> Si tout concordant : etape suivante

Etape B : Activer OUTLOOK_DELTA_SYNC_WRITE_MODE=true
          -> Le job traite les messages en parallele du webhook
          -> mail_exists() empeche les doublons
          -> Les sortants apparaissent (avant invisibles)
          -> Les modifications (lu/deplace) sont detectees
          -> Observation 24-48h

Etape C : Une fois validee, on peut desactiver le webhook actuel
          en decommissionnant la subscription Microsoft (Etape 3.6)
"""

import json
import logging
import os
from datetime import datetime, timezone
from typing import Optional

from app.database import get_pg_conn

logger = logging.getLogger("raya.outlook_delta_sync")

# Folders surveilles. Microsoft Graph utilise des "well-known names".
WELL_KNOWN_FOLDERS = [
    "Inbox",
    "SentItems",
    "JunkEmail",
]

# Limite de safety : max records a traiter par tick par folder
MAX_MESSAGES_PER_TICK_PER_FOLDER = 500


def _is_write_mode_enabled() -> bool:
    """Lit la variable Railway OUTLOOK_DELTA_SYNC_WRITE_MODE."""
    val = os.getenv("OUTLOOK_DELTA_SYNC_WRITE_MODE", "").strip().lower()
    return val in ("1", "true", "yes", "on")


def _get_folder_delta_link(connection_id: int, folder_name: str) -> Optional[str]:
    """Lit le delta_link stocke pour ce (connection_id, folder).
    Stocke dans connection_health.metadata (JSONB).
    """
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            SELECT metadata FROM connection_health
            WHERE connection_id = %s
        """, (connection_id,))
        row = c.fetchone()
        if not row or not row[0]:
            return None
        metadata = row[0] if isinstance(row[0], dict) else json.loads(row[0])
        return metadata.get("folder_delta_links", {}).get(folder_name)
    except Exception as e:
        logger.debug("[OutlookDelta] _get_folder_delta_link echec : %s", str(e)[:200])
        return None
    finally:
        if conn: conn.close()


def _set_folder_delta_link(connection_id: int, folder_name: str,
                            delta_link: str) -> bool:
    """Stocke le nouveau delta_link pour ce folder."""
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            UPDATE connection_health
            SET metadata = jsonb_set(
                COALESCE(metadata, '{}'::jsonb),
                ARRAY['folder_delta_links', %s],
                to_jsonb(%s::text)
            ),
            updated_at = NOW()
            WHERE connection_id = %s
        """, (folder_name, delta_link, connection_id))
        conn.commit()
        return c.rowcount > 0
    except Exception as e:
        logger.error("[OutlookDelta] _set_folder_delta_link echec : %s",
                     str(e)[:200])
        return False
    finally:
        if conn: conn.close()


def _ensure_health_registered(connection_id: int, tenant_id: str,
                                username: str) -> None:
    """Inscription idempotente dans connection_health.
    Polling toutes les 5 min, seuil alerte = 3x = 15 min.
    """
    try:
        from app.connection_health import register_connection
        register_connection(
            connection_id=connection_id,
            tenant_id=tenant_id,
            username=username,
            connection_type="mail_outlook",
            expected_poll_interval_seconds=300,    # 5 min
            alert_threshold_seconds=900,           # 15 min
        )
    except Exception as e:
        logger.debug("[OutlookDelta] register_connection echec : %s", str(e)[:200])


def _poll_folder_delta(token: str, folder_name: str,
                        connection_id: int,
                        write_mode: bool) -> dict:
    """Execute le delta query pour un folder donne.

    Args:
        write_mode: si True, le $select inclut body pour pouvoir traiter
                    les messages. Sinon, on minimise la bande passante.

    Returns:
        Dict avec keys:
          - status: 'ok' | 'auth_error' | 'network_error' | etc.
          - items_seen: nb total de messages retournes par l API
          - items_new: nb de NOUVEAUX messages (creation/modification)
          - new_delta_link: nouveau delta_link a stocker
          - messages: liste des messages bruts (pour traitement WRITE_MODE)
          - error_detail: si status != 'ok'
    """
    from app.graph_client import graph_get

    delta_link = _get_folder_delta_link(connection_id, folder_name)

    # Choix des champs selon le mode
    if write_mode:
        # Mode WRITE : on a besoin de tous les champs pour appeler process_incoming_mail
        select_fields = "id,subject,from,receivedDateTime,bodyPreview,body,isRead,parentFolderId"
    else:
        # Mode SHADOW : minimum pour reduire la bande passante
        select_fields = "id,subject,from,receivedDateTime,bodyPreview,isRead,parentFolderId"

    if delta_link:
        url = delta_link
        params = None
    else:
        url = f"/me/mailFolders/{folder_name}/messages/delta"
        params = {
            "$select": select_fields,
            "$top": MAX_MESSAGES_PER_TICK_PER_FOLDER,
        }

    try:
        if delta_link:
            import requests
            r = requests.get(
                url,
                headers={"Authorization": f"Bearer {token}"},
                timeout=30,
            )
            if r.status_code == 200:
                response = r.json()
            elif r.status_code in (401, 403):
                return {
                    "status": "auth_error",
                    "items_seen": 0, "items_new": 0,
                    "new_delta_link": None, "messages": [],
                    "error_detail": f"HTTP {r.status_code} : token expire ou revoque",
                }
            elif r.status_code == 410:
                logger.warning(
                    "[OutlookDelta] delta_link expire pour folder=%s, reinit",
                    folder_name,
                )
                _set_folder_delta_link(connection_id, folder_name, "")
                return {
                    "status": "internal_error",
                    "items_seen": 0, "items_new": 0,
                    "new_delta_link": None, "messages": [],
                    "error_detail": "delta_link expire, reinit au prochain cycle",
                }
            else:
                return {
                    "status": "network_error",
                    "items_seen": 0, "items_new": 0,
                    "new_delta_link": None, "messages": [],
                    "error_detail": f"HTTP {r.status_code} : {r.text[:200]}",
                }
        else:
            response = graph_get(token, url, params=params)
    except Exception as e:
        return {
            "status": "network_error",
            "items_seen": 0, "items_new": 0,
            "new_delta_link": None, "messages": [],
            "error_detail": str(e)[:300],
        }

    messages = response.get("value", [])
    items_seen = len(messages)
    items_new = sum(1 for m in messages if "@removed" not in m)
    items_removed = items_seen - items_new

    new_delta_link = response.get("@odata.deltaLink")
    next_link = response.get("@odata.nextLink")
    delta_link_to_store = new_delta_link or next_link

    return {
        "status": "ok",
        "items_seen": items_seen,
        "items_new": items_new,
        "items_removed": items_removed,
        "new_delta_link": delta_link_to_store,
        "messages": messages,
        "has_more": next_link is not None,
        "error_detail": None,
    }


def _process_messages_via_pipeline(messages: list, username: str,
                                     folder_name: str,
                                     connection_id: int = None,
                                     mailbox_email: str = None) -> dict:
    """Mode WRITE : traite chaque message via process_incoming_mail.

    Reutilise le pipeline source-agnostic existant qui :
      - Verifie mail_exists (anti-doublon avec le webhook actuel)
      - Filtre whitelist/blacklist/anti-spam
      - Triage Haiku
      - Analyse IA si demande
      - Insert dans mail_memory
      - Heartbeat + scoring urgence

    Fix 04/05/2026 : on passe maintenant connection_id + mailbox_email pour
    que chaque mail soit etiquete avec sa boite d origine reelle (sinon
    impossible de distinguer les 2 boites Outlook entre elles).

    Returns:
        Dict {processed: int, skipped: int, errors: int}
    """
    from app.routes.webhook_ms_handlers import process_incoming_mail
    from app.mail_memory_store import mail_exists

    processed = 0
    skipped_existing = 0
    skipped_removed = 0
    errors = 0

    for msg in messages:
        try:
            # Skip les messages supprimes (delta peut retourner @removed)
            if "@removed" in msg:
                skipped_removed += 1
                continue

            message_id = msg.get("id")
            if not message_id:
                continue

            # Anti-doublon : si le mail existe deja, on skip
            # (le webhook actuel l a peut-etre deja traite, ou un cycle precedent)
            if mail_exists(message_id, username):
                skipped_existing += 1
                continue

            # Extraction des champs pour process_incoming_mail
            sender_obj = msg.get("from", {}) or {}
            email_addr = sender_obj.get("emailAddress", {}) or {}
            sender = email_addr.get("address", "") or ""
            subject = msg.get("subject", "") or ""
            preview = msg.get("bodyPreview", "") or ""
            received_at = msg.get("receivedDateTime", "")
            body_obj = msg.get("body", {}) or {}
            raw_body = body_obj.get("content", "") or preview

            # Traitement via le pipeline source-agnostic
            result = process_incoming_mail(
                username=username,
                sender=sender,
                subject=subject,
                preview=preview,
                message_id=message_id,
                received_at=received_at,
                mailbox_source="outlook",
                raw_body=raw_body,
                mailbox_email=mailbox_email,
                connection_id=connection_id,
            )

            if result in ("done_ai", "stored_simple", "fallback"):
                processed += 1
            elif result in ("duplicate",):
                skipped_existing += 1
            elif result in ("ignored",):
                # Ignore par les filtres : ce n est pas une erreur
                pass
            elif result == "error":
                errors += 1

        except Exception as e:
            errors += 1
            logger.error(
                "[OutlookDelta][WRITE] %s/%s/%s erreur : %s",
                username, folder_name,
                msg.get("id", "?")[:40], str(e)[:200],
            )

    if processed > 0 or errors > 0:
        logger.info(
            "[OutlookDelta][WRITE] %s/%s : %d traites, %d existants, "
            "%d removed, %d erreurs",
            username, folder_name,
            processed, skipped_existing, skipped_removed, errors,
        )

    return {
        "processed": processed,
        "skipped_existing": skipped_existing,
        "skipped_removed": skipped_removed,
        "errors": errors,
    }


def _poll_user_outlook(connection_id: int, tenant_id: str,
                        username: str) -> dict:
    """Polle tous les folders surveilles pour un user donne.

    Mode dependant de OUTLOOK_DELTA_SYNC_WRITE_MODE :
      - shadow : ne traite PAS les messages (default)
      - write  : appelle process_incoming_mail pour chaque message
    """
    from app.token_manager import get_valid_microsoft_token
    from app.database import get_pg_conn

    poll_started = datetime.now()
    write_mode = _is_write_mode_enabled()

    # Resolution de l adresse de boite reelle (fix 04/05/2026 : on ne veut
    # plus mailbox_source generique 'outlook' ; on stocke l adresse exacte
    # qui a recu le mail, pour eviter les confusions entre les 2 boites
    # Outlook d un meme user).
    mailbox_email = None
    _conn_mb = None
    try:
        _conn_mb = get_pg_conn()
        _c_mb = _conn_mb.cursor()
        _c_mb.execute(
            "SELECT connected_email FROM tenant_connections WHERE id = %s",
            (connection_id,),
        )
        _row_mb = _c_mb.fetchone()
        if _row_mb and _row_mb[0]:
            mailbox_email = _row_mb[0]
    except Exception as _e_mb:
        logger.warning(
            "[OutlookDelta] Recuperation mailbox_email echouee conn=%d : %s",
            connection_id, str(_e_mb)[:150],
        )
    finally:
        if _conn_mb:
            _conn_mb.close()

    # Recupere le token utilisateur
    try:
        token = get_valid_microsoft_token(username)
    except Exception as e:
        logger.warning(
            "[OutlookDelta] Token recup echec pour %s : %s",
            username, str(e)[:200],
        )
        token = None

    if not token:
        try:
            from app.connection_health import record_poll_attempt
            record_poll_attempt(
                connection_id=connection_id,
                status="auth_error",
                items_seen=0,
                items_new=0,
                error_detail="Token Microsoft non disponible ou expire",
                poll_started_at=poll_started,
            )
        except Exception:
            pass
        return {"status": "auth_error", "folders_polled": 0}

    # Inscription idempotente
    _ensure_health_registered(connection_id, tenant_id, username)

    # Poll de chaque folder
    total_seen = 0
    total_new = 0
    total_processed = 0
    total_skipped = 0
    folders_ok = 0
    folders_failed = 0
    per_folder_stats = {}

    for folder_name in WELL_KNOWN_FOLDERS:
        try:
            result = _poll_folder_delta(token, folder_name,
                                         connection_id, write_mode)
            per_folder_stats[folder_name] = result

            if result["status"] == "ok":
                folders_ok += 1
                total_seen += result["items_seen"]
                total_new += result["items_new"]

                if result["new_delta_link"]:
                    _set_folder_delta_link(
                        connection_id, folder_name, result["new_delta_link"],
                    )

                # MODE WRITE : on traite les messages via le pipeline
                if write_mode and result["messages"]:
                    process_result = _process_messages_via_pipeline(
                        result["messages"], username, folder_name,
                        connection_id=connection_id,
                        mailbox_email=mailbox_email,
                    )
                    total_processed += process_result["processed"]
                    total_skipped += process_result["skipped_existing"]
                    per_folder_stats[folder_name]["process_result"] = process_result
                else:
                    # MODE SHADOW : on log juste les compteurs
                    if result["items_new"] > 0:
                        logger.info(
                            "[OutlookDelta][SHADOW] %s/%s : %d items detectes "
                            "(NON TRAITES, shadow mode)",
                            username, folder_name, result["items_new"],
                        )
            else:
                folders_failed += 1
                logger.warning(
                    "[OutlookDelta] %s/%s : %s - %s",
                    username, folder_name, result["status"],
                    (result.get("error_detail") or "")[:150],
                )
        except Exception as e:
            folders_failed += 1
            logger.error(
                "[OutlookDelta] %s/%s crash : %s",
                username, folder_name, str(e)[:200],
            )
            per_folder_stats[folder_name] = {
                "status": "internal_error",
                "items_seen": 0, "items_new": 0,
                "error_detail": str(e)[:200],
            }

    # Logging dans connection_health_events (status global du cycle)
    try:
        from app.connection_health import record_poll_attempt

        if folders_failed >= len(WELL_KNOWN_FOLDERS) / 2:
            global_status = "internal_error"
            error_detail = f"{folders_failed}/{len(WELL_KNOWN_FOLDERS)} folders en erreur"
        else:
            global_status = "ok"
            mode_label = "WRITE" if write_mode else "SHADOW"
            if write_mode:
                error_detail = (
                    f"WRITE MODE - {folders_ok}/{len(WELL_KNOWN_FOLDERS)} folders OK, "
                    f"items_new={total_new}, processed={total_processed}, "
                    f"skipped={total_skipped}"
                )
            else:
                error_detail = (
                    f"SHADOW MODE - {folders_ok}/{len(WELL_KNOWN_FOLDERS)} folders OK, "
                    f"items_new={total_new} (NON TRAITES)"
                )

        duration_ms = int((datetime.now() - poll_started).total_seconds() * 1000)
        record_poll_attempt(
            connection_id=connection_id,
            status=global_status,
            items_seen=total_seen,
            items_new=total_processed if write_mode else total_new,
            duration_ms=duration_ms,
            error_detail=error_detail,
            poll_started_at=poll_started,
        )
    except Exception as e:
        logger.error("[OutlookDelta] record_poll_attempt echec : %s", str(e)[:200])

    return {
        "status": "ok" if folders_failed == 0 else "partial",
        "folders_polled": len(WELL_KNOWN_FOLDERS),
        "folders_ok": folders_ok,
        "folders_failed": folders_failed,
        "total_items_seen": total_seen,
        "total_items_new": total_new,
        "total_processed": total_processed,
        "write_mode": write_mode,
        "per_folder": per_folder_stats,
    }


def _get_outlook_connections() -> list:
    """Retourne la liste des connexions Outlook actives (multi-user, multi-tenant).

    PATTERN ALIGNE SUR connection_token_manager.get_all_user_connections() :
    le username vient de connection_assignments (table de liaison user/connexion),
    pas de tenant_connections (qui n a pas de colonne username).

    On filtre :
      - tc.tool_type IN ('microsoft', 'outlook')   : les 2 conventions de nommage
      - tc.status = 'connected'                    : connexion active
      - ca.enabled = true                          : assignation active

    DISTINCT ON (tc.id) : si plusieurs users ont la meme connexion, on prend
    le 1er (le polling est lie a la connexion via le token, pas au user).
    """
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            SELECT DISTINCT ON (tc.id)
                tc.id, tc.tenant_id, ca.username, tc.label, tc.tool_type
            FROM connection_assignments ca
            JOIN tenant_connections tc ON tc.id = ca.connection_id
            WHERE tc.tool_type IN ('microsoft', 'outlook')
              AND tc.status = 'connected'
              AND ca.enabled = true
            ORDER BY tc.id, ca.username
        """)
        return [{
            "connection_id": r[0],
            "tenant_id": r[1],
            "username": r[2],
            "label": r[3] or "Outlook",
            "tool_type": r[4],
        } for r in c.fetchall()]
    except Exception as e:
        logger.error("[OutlookDelta] _get_outlook_connections echec : %s",
                     str(e)[:200])
        return []
    finally:
        if conn: conn.close()


def run_outlook_delta_sync():
    """Fonction principale appellee par APScheduler toutes les 5 min."""
    started_at = datetime.now()
    write_mode = _is_write_mode_enabled()
    connections = _get_outlook_connections()

    if not connections:
        logger.debug("[OutlookDelta] Aucune connexion Outlook active, skip")
        return

    total_seen = 0
    total_new = 0
    total_processed = 0
    users_ok = 0
    users_failed = 0

    for conn_info in connections:
        try:
            result = _poll_user_outlook(
                connection_id=conn_info["connection_id"],
                tenant_id=conn_info["tenant_id"],
                username=conn_info["username"],
            )
            if result["status"] == "ok":
                users_ok += 1
            else:
                users_failed += 1
            total_seen += result.get("total_items_seen", 0)
            total_new += result.get("total_items_new", 0)
            total_processed += result.get("total_processed", 0)
        except Exception as e:
            users_failed += 1
            logger.error(
                "[OutlookDelta] Crash sur connection_id=%s : %s",
                conn_info["connection_id"], str(e)[:300],
            )

    duration = (datetime.now() - started_at).total_seconds()
    if total_new > 0 or users_failed > 0:
        mode_label = "WRITE" if write_mode else "SHADOW"
        logger.info(
            "[OutlookDelta][%s] Cycle termine en %.1fs : %d connexions OK, "
            "%d echec, %d items vus, %d nouveaux, %d traites",
            mode_label, duration, users_ok, users_failed,
            total_seen, total_new, total_processed,
        )
