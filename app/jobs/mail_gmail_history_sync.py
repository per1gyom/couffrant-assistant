"""
Mail Gmail History Sync — nouveau systeme de synchronisation mails Gmail.

Phase Connexions Universelles - Semaine 4 (1er mai 2026 soir).
Voir docs/vision_connexions_universelles_01mai.md.

OBJECTIF :
─────────────────────────────────────────────────────────────
Symetrique a mail_outlook_delta_sync (Etape 3.3) pour Gmail.
Remplacer le polling actuel base sur "is:unread newer_than:5m"
(qui peut rater des mails si la fenetre 5 min est manquee) par
un polling base sur le cursor historyId de Gmail.

Avantages cles vs polling actuel :
  - GARANTIE DE COMPLETUDE : on reprend toujours la ou on s est arrete
    via le cursor historyId
  - INSCRIPTION AU MONITORING UNIVERSEL : alerte automatique si la
    boite tombe en silence (token mort, 401, etc.)
  - MULTI-BOITES : chaque boite Gmail a son propre cursor
  - DETECTION DES MODIFICATIONS : pas seulement les nouveaux mails,
    aussi les changements de label (lu, archive, supprime)
  - PAS DE FENETRE TEMPORELLE : on n a plus de "newer_than:5m"

DEUX MODES DE FONCTIONNEMENT (variables Railway) :
  SCHEDULER_GMAIL_HISTORY_SYNC_ENABLED : active/desactive le job
  GMAIL_HISTORY_SYNC_WRITE_MODE        : shadow (default) ou write
"""

import json
import logging
import os
from datetime import datetime, timezone
from typing import Optional

from app.database import get_pg_conn

logger = logging.getLogger("raya.gmail_history_sync")

_GMAIL_API = "https://gmail.googleapis.com/gmail/v1/users/me"

# Limite de safety : max records a traiter par tick
MAX_MESSAGES_PER_TICK = 500

# Labels Gmail consideres comme dans le perimetre.
#
# Logique : Gmail attribue TOUJOURS un label "container" (INBOX, SENT,
# SPAM, TRASH) ET potentiellement une CATEGORY_* (Promotions, Social,
# Updates, Forums, Personal) en plus pour les mails en INBOX.
#
# On indexe tous les mails qui sont dans :
#   - INBOX (boite de reception, toutes categories Gmail incluses)
#   - SENT (mails envoyes)
#   - SPAM (spam mal classe par Gmail, on veut quand meme les voir)
#
# Les CATEGORY_* sont AJOUTEES car Gmail peut PARFOIS classer un mail
# en categorie SANS le label INBOX (cas rares, ex : mails archives auto
# ou dans certains dossiers tries). Pour etre exhaustif, on les inclut.
#
# Exclus volontairement : TRASH (corbeille), DRAFT (brouillons),
# CHAT (messages chat Google).
#
# Note Etape 4.4 (01/05/2026 soir) : initialement {INBOX, SENT, SPAM}
# uniquement. Elargi suite a observation : un mail test detecte
# (items_new=1) mais skip silencieux (processed=0, skipped=0) car
# probablement classe en categorie sans label INBOX dans le history feed.
PERIMETRE_LABELS = {
    "INBOX", "SENT", "SPAM",
    "CATEGORY_PERSONAL", "CATEGORY_PROMOTIONS", "CATEGORY_SOCIAL",
    "CATEGORY_UPDATES", "CATEGORY_FORUMS",
}


def _is_write_mode_enabled() -> bool:
    """Lit la variable Railway GMAIL_HISTORY_SYNC_WRITE_MODE."""
    val = os.getenv("GMAIL_HISTORY_SYNC_WRITE_MODE", "").strip().lower()
    return val in ("1", "true", "yes", "on")


def _get_history_id(connection_id: int) -> Optional[str]:
    """Lit le historyId stocke pour cette connexion Gmail.
    Stocke dans connection_health.metadata.history_id (JSONB).
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
        return metadata.get("history_id")
    except Exception as e:
        logger.debug(
            "[GmailHistory] _get_history_id echec : %s", str(e)[:200])
        return None
    finally:
        if conn: conn.close()


def _set_history_id(connection_id: int, history_id: str) -> bool:
    """Stocke le nouvel historyId pour cette connexion."""
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            UPDATE connection_health
            SET metadata = jsonb_set(
                COALESCE(metadata, '{}'::jsonb),
                '{history_id}',
                to_jsonb(%s::text)
            ),
            updated_at = NOW()
            WHERE connection_id = %s
        """, (history_id, connection_id))
        conn.commit()
        return c.rowcount > 0
    except Exception as e:
        logger.error(
            "[GmailHistory] _set_history_id echec : %s", str(e)[:200])
        return False
    finally:
        if conn: conn.close()


def _ensure_health_registered(connection_id: int, tenant_id: str,
                                username: str) -> None:
    """Inscription idempotente dans connection_health."""
    try:
        from app.connection_health import register_connection
        register_connection(
            connection_id=connection_id,
            tenant_id=tenant_id,
            username=username,
            connection_type="mail_gmail",
            expected_poll_interval_seconds=300,    # 5 min
            alert_threshold_seconds=900,           # 15 min
        )
    except Exception as e:
        logger.debug(
            "[GmailHistory] register_connection echec : %s", str(e)[:200])


def _gmail_get(token: str, path: str, params: dict = None) -> dict:
    """Wrapper GET vers Gmail API avec gestion d erreurs harmonisee.

    Retourne :
      - dict du JSON Gmail si succes
      - dict {"_error": "auth_error" | "not_found" | "network_error",
              "_status_code": int, "_detail": str} si echec
    """
    import requests
    url = path if path.startswith("http") else f"{_GMAIL_API}{path}"
    try:
        r = requests.get(
            url,
            headers={"Authorization": f"Bearer {token}"},
            params=params or {},
            timeout=30,
        )
        if r.status_code == 200:
            return r.json()
        if r.status_code in (401, 403):
            return {"_error": "auth_error", "_status_code": r.status_code,
                    "_detail": (r.text or "")[:300]}
        if r.status_code == 404:
            return {"_error": "not_found", "_status_code": 404,
                    "_detail": (r.text or "")[:300]}
        return {"_error": "network_error", "_status_code": r.status_code,
                "_detail": (r.text or "")[:300]}
    except Exception as e:
        return {"_error": "network_error", "_status_code": 0,
                "_detail": str(e)[:300]}


def _bootstrap_history_id(token: str) -> tuple[Optional[str], Optional[str]]:
    """Premier run : pas de historyId stocke, on appelle /profile pour
    en avoir un de depart. Tous les mails ANTERIEURS a ce historyId
    ne seront PAS vus par le polling delta — c est le scan de rattrapage
    qui se chargera de les indexer (NIVEAU 5 du pattern).

    Returns:
      (history_id, error_detail)
      - history_id si succes, None sinon
      - error_detail si echec, None sinon (pour debug : code HTTP + message Google)
    """
    response = _gmail_get(token, "/profile")
    if response.get("_error"):
        # Construit un detail d erreur explicite avec le code HTTP et le
        # message Google brut, pour pouvoir distinguer rapidement :
        #   - 401 invalid_grant (token revoke par changement Production)
        #   - 401 invalid_token (token expire et refresh casse)
        #   - 403 access_denied (scopes manquants)
        #   - autre
        err = (f"/profile {response.get('_error')} "
                f"HTTP {response.get('_status_code')} : "
                f"{(response.get('_detail') or '')[:200]}")
        return None, err
    return response.get("historyId"), None


def _poll_history(token: str, connection_id: int,
                   write_mode: bool) -> dict:
    """Execute le history query pour une connexion Gmail donnee.

    Returns:
        Dict avec keys:
          - status: 'ok' | 'auth_error' | 'network_error' | 'reset_needed' | etc.
          - items_seen, items_new, items_modified, new_history_id
          - message_ids (pour write mode)
    """
    history_id = _get_history_id(connection_id)

    # Premier run : bootstrap depuis /profile
    if not history_id:
        bootstrap_id, bootstrap_err = _bootstrap_history_id(token)
        if not bootstrap_id:
            return {
                "status": "auth_error",
                "items_seen": 0, "items_new": 0, "items_modified": 0,
                "new_history_id": None, "message_ids": [],
                "error_detail": (
                    bootstrap_err
                    or "Impossible de bootstrap le historyId via /profile"
                ),
            }
        # Le tout premier cycle ne traite rien - intentionnel
        # (les mails passes sont du ressort du scan de rattrapage)
        _set_history_id(connection_id, bootstrap_id)
        logger.info(
            "[GmailHistory] Bootstrap historyId=%s pour connexion #%d",
            bootstrap_id, connection_id,
        )
        return {
            "status": "ok",
            "items_seen": 0, "items_new": 0, "items_modified": 0,
            "new_history_id": bootstrap_id, "message_ids": [],
            "bootstrapped": True,
            "error_detail": "Bootstrap initial - prochain cycle traitera les nouveaux mails",
        }

    # Cycles suivants : history.list
    response = _gmail_get(token, "/history", {
        "startHistoryId": history_id,
        "maxResults": str(MAX_MESSAGES_PER_TICK),
    })

    if response.get("_error"):
        err = response["_error"]
        if err == "auth_error":
            return {
                "status": "auth_error",
                "items_seen": 0, "items_new": 0, "items_modified": 0,
                "new_history_id": None, "message_ids": [],
                "error_detail": (
                    f"HTTP {response.get('_status_code')} : token expire "
                    f"ou revoque - {response.get('_detail', '')[:150]}"
                ),
            }
        if err == "not_found":
            # historyId trop ancien (>7 jours) ou invalide -> reset
            logger.warning(
                "[GmailHistory] historyId %s invalide pour conn #%d, reset",
                history_id, connection_id,
            )
            _set_history_id(connection_id, "")
            return {
                "status": "reset_needed",
                "items_seen": 0, "items_new": 0, "items_modified": 0,
                "new_history_id": None, "message_ids": [],
                "error_detail": "historyId invalide, reset effectue",
            }
        return {
            "status": "network_error",
            "items_seen": 0, "items_new": 0, "items_modified": 0,
            "new_history_id": None, "message_ids": [],
            "error_detail": (
                f"HTTP {response.get('_status_code')} : "
                f"{response.get('_detail', '')[:200]}"
            ),
        }

    history_entries = response.get("history", [])
    new_history_id = response.get("historyId", history_id)

    # Extraction des messagesAdded (nouveaux mails)
    message_ids_new = []
    message_ids_modified = []
    message_ids_deleted = []
    # Pour les modifications, on garde les labels ajoutes/retires explicitement
    # pour pouvoir detecter TRASH (mise en corbeille) et restauration.
    # Format : {msg_id: {"labels_added": [...], "labels_removed": [...], "current_labels": [...]}}
    label_changes_by_msg = {}
    seen_added = set()
    seen_modified = set()
    seen_deleted = set()

    for entry in history_entries:
        # messagesAdded : liste de {message: {id, threadId, labelIds}}
        for added in entry.get("messagesAdded", []):
            msg = added.get("message", {})
            msg_id = msg.get("id")
            if msg_id and msg_id not in seen_added:
                message_ids_new.append({
                    "id": msg_id,
                    "thread_id": msg.get("threadId", ""),
                    "label_ids": msg.get("labelIds", []),
                })
                seen_added.add(msg_id)

        # messagesDeleted : suppression definitive (vidage corbeille,
        # ou SHIFT+Suppr direct dans Gmail). Le mail n existe plus
        # cote Gmail, on doit le marquer deleted_at en base.
        for deleted in entry.get("messagesDeleted", []):
            msg = deleted.get("message", {})
            msg_id = msg.get("id")
            if msg_id and msg_id not in seen_deleted:
                message_ids_deleted.append({
                    "id": msg_id,
                    "thread_id": msg.get("threadId", ""),
                })
                seen_deleted.add(msg_id)

        # labelsAdded : ex deplace en TRASH = mise a la corbeille
        for change in entry.get("labelsAdded", []):
            msg = change.get("message", {})
            msg_id = msg.get("id")
            if not msg_id:
                continue
            added_labels = change.get("labelIds", [])
            slot = label_changes_by_msg.setdefault(msg_id, {
                "labels_added": [], "labels_removed": [], "current_labels": [],
                "thread_id": msg.get("threadId", ""),
            })
            for lbl in added_labels:
                if lbl not in slot["labels_added"]:
                    slot["labels_added"].append(lbl)
            slot["current_labels"] = msg.get("labelIds", [])
            if msg_id not in seen_modified:
                message_ids_modified.append({
                    "id": msg_id,
                    "thread_id": msg.get("threadId", ""),
                    "label_ids": msg.get("labelIds", []),
                })
                seen_modified.add(msg_id)

        # labelsRemoved : ex sortie de TRASH = restauration depuis corbeille
        for change in entry.get("labelsRemoved", []):
            msg = change.get("message", {})
            msg_id = msg.get("id")
            if not msg_id:
                continue
            removed_labels = change.get("labelIds", [])
            slot = label_changes_by_msg.setdefault(msg_id, {
                "labels_added": [], "labels_removed": [], "current_labels": [],
                "thread_id": msg.get("threadId", ""),
            })
            for lbl in removed_labels:
                if lbl not in slot["labels_removed"]:
                    slot["labels_removed"].append(lbl)
            slot["current_labels"] = msg.get("labelIds", [])
            if msg_id not in seen_modified:
                message_ids_modified.append({
                    "id": msg_id,
                    "thread_id": msg.get("threadId", ""),
                    "label_ids": msg.get("labelIds", []),
                })
                seen_modified.add(msg_id)

    return {
        "status": "ok",
        "items_seen": len(history_entries),
        "items_new": len(message_ids_new),
        "items_modified": len(message_ids_modified),
        "items_deleted": len(message_ids_deleted),
        "new_history_id": new_history_id,
        "message_ids": message_ids_new,
        "modified_message_ids": message_ids_modified,
        "deleted_message_ids": message_ids_deleted,
        "label_changes_by_msg": label_changes_by_msg,
        "has_more": response.get("nextPageToken") is not None,
        "error_detail": None,
    }


def _fetch_message_full(token: str, message_id: str) -> Optional[dict]:
    """Fetch un message Gmail en mode 'metadata' avec headers principaux.

    Fix 04/05 soir : metadataHeaders DOIT etre une liste Python (pas une
    string virgulee), sinon Gmail interprete "From,Subject,Date" comme un
    seul nom de header bizarre et renvoie payload sans aucun header.
    """
    response = _gmail_get(token, f"/messages/{message_id}", {
        "format": "metadata",
        "metadataHeaders": ["From", "Subject", "Date", "To", "Cc"],
    })
    if response.get("_error"):
        return None
    return response


def _apply_deletes_and_trash(deleted_msg_ids: list,
                              label_changes: dict,
                              tenant_id: str,
                              connection_id: int) -> dict:
    """Applique les suppressions et changements de label TRASH detectes
    par l history Gmail au mail_memory et au graphe.

    deleted_msg_ids : liste de {id, thread_id} pour messagesDeleted
        -> soft-delete (deleted_at = NOW()) en mail_memory + graphe
    label_changes : dict {gmail_msg_id: {labels_added, labels_removed, ...}}
        -> si TRASH dans labels_added : trashed_at = NOW()
        -> si TRASH dans labels_removed : trashed_at = NULL (restauration)

    Le mail est identifie en base par message_id == gmail_msg_id ET
    connection_id == celui de la connexion qui poll.

    Retourne stats : {soft_deleted, trashed, untrashed, errors}
    """
    from app.db_utils import get_pg_conn
    stats = {"soft_deleted": 0, "trashed": 0, "untrashed": 0, "errors": 0}
    if not deleted_msg_ids and not label_changes:
        return stats

    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()

        # 1. Soft-delete des mails purement supprimes (vidage corbeille
        #    ou suppression directe)
        for d in deleted_msg_ids:
            gmail_id = d.get("id")
            if not gmail_id:
                continue
            try:
                # Soft-delete en mail_memory
                c.execute("""
                    UPDATE mail_memory
                    SET deleted_at = NOW()
                    WHERE message_id = %s
                      AND connection_id = %s
                      AND tenant_id = %s
                      AND deleted_at IS NULL
                    RETURNING id
                """, (gmail_id, connection_id, tenant_id))
                rows = c.fetchall()
                if rows:
                    mail_db_id = rows[0][0]
                    # Soft-delete du noeud graphe correspondant
                    c.execute("""
                        UPDATE semantic_graph_nodes
                        SET deleted_at = NOW(), updated_at = NOW()
                        WHERE node_type = 'Mail'
                          AND tenant_id = %s
                          AND source_record_id = %s
                          AND deleted_at IS NULL
                    """, (tenant_id, str(mail_db_id)))
                    stats["soft_deleted"] += 1
            except Exception as e:
                stats["errors"] += 1
                logger.warning(
                    "[GmailHistory][DELETE] echec soft-delete %s : %s",
                    gmail_id, str(e)[:150],
                )

        # 2. Mise en corbeille / restauration via labels TRASH
        for gmail_id, changes in label_changes.items():
            added = changes.get("labels_added", [])
            removed = changes.get("labels_removed", [])
            try:
                if "TRASH" in added:
                    c.execute("""
                        UPDATE mail_memory
                        SET trashed_at = NOW()
                        WHERE message_id = %s
                          AND connection_id = %s
                          AND tenant_id = %s
                          AND deleted_at IS NULL
                          AND trashed_at IS NULL
                        RETURNING id
                    """, (gmail_id, connection_id, tenant_id))
                    if c.fetchall():
                        stats["trashed"] += 1
                if "TRASH" in removed:
                    c.execute("""
                        UPDATE mail_memory
                        SET trashed_at = NULL
                        WHERE message_id = %s
                          AND connection_id = %s
                          AND tenant_id = %s
                          AND trashed_at IS NOT NULL
                        RETURNING id
                    """, (gmail_id, connection_id, tenant_id))
                    if c.fetchall():
                        stats["untrashed"] += 1
            except Exception as e:
                stats["errors"] += 1
                logger.warning(
                    "[GmailHistory][LABEL] echec maj %s : %s",
                    gmail_id, str(e)[:150],
                )

        conn.commit()
    except Exception as e:
        logger.error("[GmailHistory][APPLY] crash : %s", str(e)[:200])
        stats["errors"] += 1
    finally:
        if conn:
            conn.close()

    return stats


def _extract_attachment_parts(payload_or_part: dict) -> list:
    """Parse recursif des parts du payload Gmail pour extraire les
    attachments (parts qui ont un filename + body.attachmentId).

    Format Gmail : un mail peut avoir des parts imbriques (multipart/
    alternative dans multipart/mixed pour mail HTML+texte+PJ).

    Returns:
        Liste de dicts {filename, mimeType, size, attachmentId}.
    """
    attachments = []
    parts = payload_or_part.get("parts", []) if isinstance(payload_or_part, dict) else []

    for part in parts:
        # Si c est un attachment (a un filename + attachmentId)
        filename = part.get("filename", "")
        body = part.get("body", {}) or {}
        attachment_id = body.get("attachmentId")
        if filename and attachment_id:
            attachments.append({
                "filename": filename,
                "mimeType": part.get("mimeType", "application/octet-stream"),
                "size": body.get("size", 0),
                "attachmentId": attachment_id,
            })
        # Recursion sur sous-parts
        if part.get("parts"):
            attachments.extend(_extract_attachment_parts(part))

    return attachments


def _fetch_gmail_attachments(token: str, message_id: str,
                              max_size_mb: int = 10) -> list:
    """Recupere les pieces jointes d un mail Gmail.

    Etape 4 (chantier B PJ, 06/05/2026).

    Strategie :
      1. GET /messages/{id}?format=full -> payload complet avec parts
      2. Parse recursif pour extraire les parts attachments
      3. Pour chaque PJ <= max_size_mb : GET /messages/{id}/attachments/{att_id}
         -> retourne les bytes en base64url-encoded
      4. Decode les bytes

    On retourne aussi les PJ trop grosses avec content_bytes=None pour
    que l etape 6 (notification user grosses PJ) puisse les voir.

    Args:
        token: access_token Gmail (frais)
        message_id: id Gmail du mail
        max_size_mb: limite (default 10 MB)

    Returns:
        Liste de dicts. Liste vide si aucune PJ ou erreur.
    """
    import base64

    # Step 1 : fetch en mode full pour avoir les parts
    full_msg = _gmail_get(token, f"/messages/{message_id}", {"format": "full"})
    if not full_msg or full_msg.get("_error"):
        return []

    payload = full_msg.get("payload", {}) or {}
    attachments_meta = _extract_attachment_parts(payload)
    if not attachments_meta:
        return []

    max_size_bytes = max_size_mb * 1024 * 1024
    result = []
    for att in attachments_meta:
        too_large = att["size"] > max_size_bytes
        content_bytes = None

        if not too_large and att["attachmentId"]:
            # Step 2 : download les bytes
            try:
                resp = _gmail_get(
                    token,
                    f"/messages/{message_id}/attachments/{att['attachmentId']}",
                )
                if resp and not resp.get("_error") and resp.get("data"):
                    # Gmail retourne en base64url-encoded (pas le base64 standard)
                    try:
                        content_bytes = base64.urlsafe_b64decode(resp["data"])
                    except Exception as e:
                        logger.warning(
                            "[GmailPJ] base64 decode %s : %s",
                            att["filename"], str(e)[:100],
                        )
                else:
                    logger.warning(
                        "[GmailPJ] Download %s mail=%s : %s",
                        att["filename"], message_id[:30],
                        (resp or {}).get("_error", "no_data"),
                    )
            except Exception as e:
                logger.warning(
                    "[GmailPJ] Download %s exception : %s",
                    att["filename"], str(e)[:100],
                )

        result.append({
            "id": att["attachmentId"],
            "name": att["filename"],
            "size": att["size"],
            "content_type": att["mimeType"],
            "content_bytes": content_bytes,
            "too_large": too_large,
        })

    return result


def _process_attachments_for_gmail_mail(token: str, message_id: str,
                                          tenant_id: str, username: str,
                                          connection_id: int) -> dict:
    """Pour un mail Gmail deja insere, fetch et indexe ses PJ.

    Etape 4 (chantier B, 06/05/2026). Pattern aligne sur _process_attachments_for_mail
    cote Outlook (mail_outlook_delta_sync.py) - duplication acceptee pour le MVP,
    pourra etre extraite dans un module commun en etape 7.

    Workflow :
      1. List + download les PJ via _fetch_gmail_attachments
      2. Pour chaque PJ <= 10 MB : process_attachment (extract + index +
         attachment_chunks + push graphe + extraction entites). UPSERT donc
         idempotent.
      3. Pour chaque PJ > 10 MB : skip (sera gere a l etape 6 avec notif user).

    Returns:
        Dict {indexed, skipped_large, errors, large_pjs_meta}
    """
    from app.attachment_pipeline import process_attachment

    attachments = _fetch_gmail_attachments(token, message_id, max_size_mb=10)
    if not attachments:
        return {
            "indexed": 0, "skipped_large": 0, "errors": 0,
            "large_pjs_meta": [],
        }

    indexed = 0
    skipped_large = 0
    errors = 0
    large_pjs_meta = []

    for att in attachments:
        if att["too_large"]:
            skipped_large += 1
            large_pjs_meta.append({
                "name": att["name"],
                "size": att["size"],
                "content_type": att["content_type"],
                "gmail_attachment_id": att["id"],
            })
            logger.info(
                "[GmailPJ] Skip grosse PJ %s (%.1f MB) sur mail %s "
                "(etape 6 a venir)",
                att["name"], att["size"] / (1024 * 1024), message_id[:30],
            )
            continue

        if not att["content_bytes"]:
            errors += 1
            continue

        try:
            result = process_attachment(
                tenant_id=tenant_id,
                username=username,
                source_type="mail_attachment",
                source_ref=f"{message_id}:{att['id']}",
                file_name=att["name"],
                file_bytes=att["content_bytes"],
                mime_type=att["content_type"],
                connection_id=connection_id,
            )
            if result.get("status") == "ok":
                indexed += 1
            else:
                errors += 1
        except Exception as e:
            errors += 1
            logger.warning(
                "[GmailPJ] process_attachment %s echoue : %s",
                att["name"], str(e)[:100],
            )

    if indexed > 0 or skipped_large > 0:
        logger.info(
            "[GmailPJ] mail=%s : %d indexees, %d trop grosses, %d erreurs",
            message_id[:30], indexed, skipped_large, errors,
        )

    return {
        "indexed": indexed,
        "skipped_large": skipped_large,
        "errors": errors,
        "large_pjs_meta": large_pjs_meta,
    }


def _mark_mail_has_attachments_gmail(message_id: str, username: str) -> bool:
    """UPDATE mail_memory.has_attachments=TRUE pour ce mail.
    Etape 4 (chantier B, 06/05/2026)."""
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute(
            """
            UPDATE mail_memory
            SET has_attachments = TRUE
            WHERE message_id = %s AND username = %s
            """,
            (message_id, username),
        )
        conn.commit()
        return c.rowcount > 0
    except Exception as e:
        logger.warning(
            "[GmailPJ] _mark_mail_has_attachments_gmail echec : %s",
            str(e)[:100],
        )
        return False
    finally:
        if conn:
            conn.close()


def _maybe_rattrapage_attachments_gmail(token: str, message_id: str,
                                         tenant_id: str, username: str,
                                         connection_id: int) -> None:
    """Rattrapage des PJ Gmail pour un mail deja en base.

    Etape 4 fix (06/05/2026) : meme principe que cote Outlook. Le canal
    primaire d ingestion Gmail est gmail_polling.py qui n appelle pas le
    pipeline attachments. Au prochain cycle history_sync, on detecte les
    duplicates et on tente le rattrapage si has_attachments=False.

    Idempotent.
    """
    try:
        # Check has_attachments actuel
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute(
            """
            SELECT has_attachments FROM mail_memory
            WHERE message_id = %s AND username = %s LIMIT 1
            """,
            (message_id, username),
        )
        row = c.fetchone()
        conn.close()
        if not row:
            return
        if row[0]:
            return  # deja traite

        att_result = _process_attachments_for_gmail_mail(
            token=token,
            message_id=message_id,
            tenant_id=tenant_id,
            username=username,
            connection_id=connection_id,
        )
        if att_result["indexed"] > 0:
            _mark_mail_has_attachments_gmail(message_id, username)
            logger.info(
                "[GmailPJ-rattrap] mail=%s : %d PJ rattrapees (etait en "
                "duplicate, ingere via gmail_polling)",
                message_id[:30], att_result["indexed"],
            )
    except Exception as e:
        logger.debug(
            "[GmailPJ-rattrap] %s echec : %s",
            message_id[:30], str(e)[:100],
        )


def _process_messages_via_pipeline(token: str, messages_meta: list,
                                     username: str,
                                     connection_id: int = None,
                                     mailbox_email: str = None,
                                     tenant_id: str = None) -> dict:
    """Mode WRITE : pour chaque message_id, fetch et appelle process_incoming_mail.

    Reutilise le pipeline source-agnostic existant (cf gmail_polling.py)
    qui :
      - Verifie mail_exists (anti-doublon avec gmail_polling actuel)
      - Filtre whitelist/blacklist/anti-spam
      - Triage Haiku
      - Analyse IA si demande
      - Insert dans mail_memory
      - Heartbeat + scoring urgence

    Fix 04/05/2026 : on passe maintenant connection_id + mailbox_email pour
    que chaque mail soit etiquete avec sa boite Gmail d origine reelle
    (sinon impossible de distinguer les 5 boites Gmail entre elles).

    Returns:
        Dict {processed: int, skipped: int, errors: int, fetched: int}
    """
    from app.routes.webhook_ms_handlers import process_incoming_mail
    from app.mail_memory_store import mail_exists

    processed = 0
    skipped_existing = 0
    skipped_perimetre = 0
    errors = 0
    fetched = 0

    for msg_meta in messages_meta:
        try:
            message_id = msg_meta.get("id")
            if not message_id:
                continue

            # Anti-doublon
            if mail_exists(message_id, username):
                skipped_existing += 1
                # Etape 4 fix (06/05/2026) : rattrapage des PJ. gmail_polling
                # ingere les mails sans appeler le pipeline attachments. Ici
                # on tente le rattrapage si has_attachments=False en base.
                if token and tenant_id:
                    _maybe_rattrapage_attachments_gmail(
                        token=token,
                        message_id=message_id,
                        tenant_id=tenant_id,
                        username=username,
                        connection_id=connection_id,
                    )
                continue

            # Fetch le message complet
            full_msg = _fetch_message_full(token, message_id)
            fetched += 1
            if not full_msg:
                logger.warning(
                    "[GmailHistory][WRITE] Fetch echec %s/%s",
                    username, message_id[:30],
                )
                errors += 1
                continue

            # Extraction des champs
            payload = full_msg.get("payload", {})
            headers = {h["name"].lower(): h["value"]
                       for h in payload.get("headers", [])}
            sender = headers.get("from", "") or ""
            subject = headers.get("subject", "") or ""
            received_at = headers.get("date", "")
            snippet = full_msg.get("snippet", "") or ""

            # Filtre par labels : si pas dans le perimetre, skip
            # avec un log explicite (avant : continue silencieux)
            label_ids = full_msg.get("labelIds", [])
            in_perimetre = any(lid in PERIMETRE_LABELS for lid in label_ids)
            if not in_perimetre:
                logger.info(
                    "[GmailHistory][WRITE] Skip hors perimetre %s/%s : "
                    "labels=%s (sujet=%s)",
                    username, message_id[:30],
                    label_ids, subject[:50],
                )
                skipped_perimetre += 1
                continue

            # Pipeline source-agnostic
            result = process_incoming_mail(
                username=username,
                sender=sender,
                subject=subject,
                preview=snippet[:300],
                message_id=message_id,
                received_at=received_at,
                mailbox_source="gmail",
                mailbox_email=mailbox_email,
                connection_id=connection_id,
            )

            if result in ("done_ai", "stored_simple", "fallback"):
                processed += 1
                # Etape 4 (chantier B PJ, 06/05/2026) : si on a token +
                # tenant_id, on traite les PJ via le pipeline attachment.
                # _fetch_gmail_attachments retourne [] si pas de PJ, donc
                # safe (1 call API en plus pour mails sans PJ).
                if token and tenant_id:
                    try:
                        att_result = _process_attachments_for_gmail_mail(
                            token=token,
                            message_id=message_id,
                            tenant_id=tenant_id,
                            username=username,
                            connection_id=connection_id,
                        )
                        if att_result["indexed"] > 0:
                            _mark_mail_has_attachments_gmail(message_id, username)
                    except Exception as e_att:
                        logger.warning(
                            "[GmailHistory][PJ] %s/%s echec : %s",
                            username, message_id[:30], str(e_att)[:200],
                        )
            elif result in ("duplicate",):
                skipped_existing += 1
            elif result in ("ignored",):
                pass
            elif result == "error":
                errors += 1

        except Exception as e:
            errors += 1
            logger.error(
                "[GmailHistory][WRITE] %s/%s erreur : %s",
                username, msg_meta.get("id", "?")[:30], str(e)[:200],
            )

    if processed > 0 or errors > 0 or skipped_perimetre > 0:
        logger.info(
            "[GmailHistory][WRITE] %s : %d traites, %d existants, "
            "%d hors perimetre, %d fetches, %d erreurs",
            username, processed, skipped_existing, skipped_perimetre,
            fetched, errors,
        )

    return {
        "processed": processed,
        "skipped_existing": skipped_existing,
        "skipped_perimetre": skipped_perimetre,
        "errors": errors,
        "fetched": fetched,
    }


def _poll_user_gmail(connection_id: int, tenant_id: str,
                     username: str, token: str, email: str) -> dict:
    """Polle une boite Gmail pour un user donne.

    Mode dependant de GMAIL_HISTORY_SYNC_WRITE_MODE :
      - shadow : ne traite PAS les messages (default)
      - write  : appelle process_incoming_mail pour chaque message
    """
    poll_started = datetime.now()
    write_mode = _is_write_mode_enabled()

    # Inscription idempotente
    _ensure_health_registered(connection_id, tenant_id, username)

    # Polling history
    try:
        result = _poll_history(token, connection_id, write_mode)
    except Exception as e:
        logger.error(
            "[GmailHistory] %s/%s crash poll_history : %s",
            username, email, str(e)[:200],
        )
        try:
            from app.connection_health import record_poll_attempt
            record_poll_attempt(
                connection_id=connection_id,
                status="internal_error",
                items_seen=0, items_new=0,
                error_detail=f"crash poll_history : {str(e)[:200]}",
                poll_started_at=poll_started,
            )
        except Exception:
            pass
        return {"status": "internal_error", "error": str(e)[:200]}

    items_seen = result.get("items_seen", 0)
    items_new = result.get("items_new", 0)
    items_modified = result.get("items_modified", 0)
    processed = 0
    skipped = 0
    skipped_perimetre = 0
    errors_pipeline = 0
    pipeline_crash = ""

    # Stockage du nouveau historyId si succes
    if result["status"] == "ok" and result.get("new_history_id"):
        _set_history_id(connection_id, str(result["new_history_id"]))

    # MODE WRITE : on traite les messagesAdded
    if write_mode and result["status"] == "ok" and result.get("message_ids"):
        try:
            process_result = _process_messages_via_pipeline(
                token, result["message_ids"], username,
                connection_id=connection_id,
                mailbox_email=email,
                tenant_id=tenant_id,
            )
            processed = process_result["processed"]
            skipped = process_result["skipped_existing"]
            skipped_perimetre = process_result.get("skipped_perimetre", 0)
            errors_pipeline = process_result.get("errors", 0)
        except Exception as e:
            # Trace complete dans error_detail pour qu on puisse
            # diagnostiquer en DB (jusqu ici l exception etait
            # juste loguee dans Railway)
            import traceback
            tb = traceback.format_exc()
            pipeline_crash = (
                f"PIPELINE CRASH : {type(e).__name__}: {str(e)[:150]} "
                f"| trace: {tb.splitlines()[-3] if len(tb.splitlines()) >= 3 else tb[:200]}"
            )
            logger.error(
                "[GmailHistory][WRITE] %s/%s pipeline crash : %s\n%s",
                username, email, str(e)[:200], tb,
            )
    elif result["status"] == "ok" and items_new > 0:
        logger.info(
            "[GmailHistory][SHADOW] %s/%s : %d nouveaux messages detectes "
            "(NON TRAITES, shadow mode)",
            username, email, items_new,
        )

    # ── Suppression / mise en corbeille / restauration (Chantier 1, commit 3a) ──
    # On applique TOUJOURS ces changements meme en shadow mode, parce qu ils
    # representent des actions explicites de l utilisateur sur sa boite et
    # qu il faut que mail_memory + graphe restent fideles a la realite.
    delete_stats = {"soft_deleted": 0, "trashed": 0, "untrashed": 0, "errors": 0}
    if result["status"] == "ok" and (
        result.get("deleted_message_ids") or result.get("label_changes_by_msg")
    ):
        try:
            delete_stats = _apply_deletes_and_trash(
                deleted_msg_ids=result.get("deleted_message_ids", []),
                label_changes=result.get("label_changes_by_msg", {}),
                tenant_id=tenant_id,
                connection_id=connection_id,
            )
            if (delete_stats["soft_deleted"] + delete_stats["trashed"] +
                delete_stats["untrashed"] > 0):
                logger.info(
                    "[GmailHistory][DELETE] %s/%s : soft_deleted=%d, "
                    "trashed=%d, untrashed=%d, errors=%d",
                    username, email,
                    delete_stats["soft_deleted"], delete_stats["trashed"],
                    delete_stats["untrashed"], delete_stats["errors"],
                )
        except Exception as e:
            logger.error(
                "[GmailHistory][DELETE] crash apply : %s", str(e)[:200],
            )

    # Logging dans connection_health_events
    try:
        from app.connection_health import record_poll_attempt

        if result["status"] == "ok":
            global_status = "ok"
            if result.get("bootstrapped"):
                error_detail = "BOOTSTRAP - historyId initial enregistre"
            elif write_mode:
                error_detail = (
                    f"WRITE MODE - items_seen={items_seen}, "
                    f"items_new={items_new}, items_modified={items_modified}, "
                    f"processed={processed}, skipped_existing={skipped}, "
                    f"skipped_perimetre={skipped_perimetre}, "
                    f"errors={errors_pipeline}"
                )
                if pipeline_crash:
                    error_detail = f"{error_detail} || {pipeline_crash}"
            else:
                error_detail = (
                    f"SHADOW MODE - items_seen={items_seen}, "
                    f"items_new={items_new} (NON TRAITES)"
                )
        else:
            global_status = result["status"]
            error_detail = result.get("error_detail", "")

        duration_ms = int((datetime.now() - poll_started).total_seconds() * 1000)
        record_poll_attempt(
            connection_id=connection_id,
            status=global_status,
            items_seen=items_seen,
            items_new=processed if write_mode else items_new,
            duration_ms=duration_ms,
            error_detail=error_detail,
            poll_started_at=poll_started,
        )
    except Exception as e:
        logger.error(
            "[GmailHistory] record_poll_attempt echec : %s", str(e)[:200])

    return {
        "status": result["status"],
        "total_items_seen": items_seen,
        "total_items_new": items_new,
        "total_items_modified": items_modified,
        "total_processed": processed,
        "total_skipped": skipped,
        "write_mode": write_mode,
        "bootstrapped": result.get("bootstrapped", False),
    }


def _get_gmail_connections() -> list:
    """Retourne la liste des connexions Gmail actives (multi-user, multi-tenant).

    PATTERN ALIGNE SUR mail_outlook_delta_sync._get_outlook_connections() :
    le username vient de connection_assignments (table de liaison),
    pas de tenant_connections.

    On filtre :
      - tc.tool_type IN ('gmail', 'google')   : conventions de nommage
      - tc.status = 'connected'                : connexion active
      - ca.enabled = true                      : assignation active

    DISTINCT ON (tc.id) : si plusieurs users ont la meme connexion, on
    prend le 1er.
    """
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            SELECT DISTINCT ON (tc.id)
                tc.id, tc.tenant_id, ca.username, tc.label, tc.tool_type,
                tc.connected_email
            FROM connection_assignments ca
            JOIN tenant_connections tc ON tc.id = ca.connection_id
            WHERE tc.tool_type IN ('gmail', 'google')
              AND tc.status = 'connected'
              AND ca.enabled = true
            ORDER BY tc.id, ca.username
        """)
        return [{
            "connection_id": r[0],
            "tenant_id": r[1],
            "username": r[2],
            "label": r[3] or "Gmail",
            "tool_type": r[4],
            "email": r[5] or "",
        } for r in c.fetchall()]
    except Exception as e:
        logger.error(
            "[GmailHistory] _get_gmail_connections echec : %s", str(e)[:200])
        return []
    finally:
        if conn: conn.close()


def _get_gmail_token_for_connection(connection_id: int,
                                     username: str,
                                     email: str = "",
                                     tenant_id: str = "") -> Optional[str]:
    """Recupere un access_token Gmail VALIDE (avec refresh automatique
    si expire) pour une connexion donnee.

    FIX 01/05/2026 soir (2eme bug Etape 4.3) :
    ─────────────────────────────────────────────────────────────
    Avant : utilisait get_all_user_connections() qui retourne
    l access_token brut SANS faire le refresh quand il est expire.
    Resultat : apres 1h le token est mort -> 401 systematique.
    Meme bug que gmail_polling legacy qui spamme 401 dans les logs.

    Apres : utilise get_connection_token() qui delegue a _get_v2_token,
    laquelle :
      1. Lit access_token + refresh_token + expires_at en base
      2. Si access_token expire dans <5 min -> appelle Google pour
         refresh, sauvegarde le nouveau, et retourne le nouveau
      3. Sinon retourne l access_token courant

    L email est passe en email_hint pour cibler la BONNE boite
    quand l user a plusieurs Gmail (Guillaume en a 5).
    """
    try:
        from app.connection_token_manager import get_connection_token
        token = get_connection_token(
            username=username,
            tool_type="gmail",
            tenant_id=tenant_id or None,
            email_hint=email or None,
        )
        return token if token else None
    except Exception as e:
        logger.error(
            "[GmailHistory] _get_gmail_token_for_connection echec : %s",
            str(e)[:200],
        )
        return None


def run_gmail_history_sync():
    """Fonction principale appellee par APScheduler toutes les 5 min."""
    started_at = datetime.now()
    write_mode = _is_write_mode_enabled()
    connections = _get_gmail_connections()

    if not connections:
        logger.debug("[GmailHistory] Aucune connexion Gmail active, skip")
        return

    total_seen = 0
    total_new = 0
    total_modified = 0
    total_processed = 0
    boites_ok = 0
    boites_failed = 0
    boites_bootstrapped = 0

    for conn_info in connections:
        connection_id = conn_info["connection_id"]
        tenant_id = conn_info["tenant_id"]
        username = conn_info["username"]
        email = conn_info["email"] or "?"

        # Etape 5 (06/05/2026) : polling adaptatif jour/nuit. Skip si
        # hors heures ouvrees Paris ET dernier poll < 30 min.
        try:
            from app.polling_schedule import should_skip_poll_now
            if should_skip_poll_now(connection_id):
                logger.debug(
                    "[GmailHistory] skip conn=%s (hors heures ouvrees + dernier poll < 30 min)",
                    connection_id,
                )
                continue
        except Exception as _e_sk:
            logger.warning("[GmailHistory] should_skip check echoue : %s", str(_e_sk)[:120])

        # Recuperation du token pour cette connexion specifique
        # avec refresh automatique si expire (fix 01/05/2026 soir)
        token = _get_gmail_token_for_connection(
            connection_id=connection_id,
            username=username,
            email=email if email != "?" else "",
            tenant_id=tenant_id,
        )
        if not token:
            try:
                from app.connection_health import record_poll_attempt
                record_poll_attempt(
                    connection_id=connection_id,
                    status="auth_error",
                    items_seen=0, items_new=0,
                    error_detail=(
                        f"Token Gmail non disponible pour {username}/{email} "
                        f"(connection_id={connection_id})"
                    ),
                    poll_started_at=started_at,
                )
                # Inscription pour qu elle apparaisse dans /admin/health/page
                # avec status auth_error
                _ensure_health_registered(connection_id, tenant_id, username)
            except Exception:
                pass
            boites_failed += 1
            continue

        try:
            result = _poll_user_gmail(
                connection_id=connection_id,
                tenant_id=tenant_id,
                username=username,
                token=token,
                email=email,
            )
            if result["status"] == "ok":
                boites_ok += 1
                if result.get("bootstrapped"):
                    boites_bootstrapped += 1
            else:
                boites_failed += 1
            total_seen += result.get("total_items_seen", 0)
            total_new += result.get("total_items_new", 0)
            total_modified += result.get("total_items_modified", 0)
            total_processed += result.get("total_processed", 0)
        except Exception as e:
            boites_failed += 1
            logger.error(
                "[GmailHistory] Crash sur connection_id=%s : %s",
                connection_id, str(e)[:300],
            )

    duration = (datetime.now() - started_at).total_seconds()
    if total_new > 0 or total_modified > 0 or boites_failed > 0 or boites_bootstrapped > 0:
        mode_label = "WRITE" if write_mode else "SHADOW"
        logger.info(
            "[GmailHistory][%s] Cycle termine en %.1fs : %d boites OK, "
            "%d echec, %d bootstrap, %d items vus, %d nouveaux, "
            "%d modifies, %d traites",
            mode_label, duration, boites_ok, boites_failed,
            boites_bootstrapped, total_seen, total_new, total_modified,
            total_processed,
        )

    # Heartbeat
    try:
        from app.database import get_pg_conn as _hb_get
        _hb = _hb_get(); _hb_c = _hb.cursor()
        _hb_c.execute("""
            INSERT INTO system_heartbeat (component, last_seen_at, status)
            VALUES ('gmail_history_sync', NOW(), 'ok')
            ON CONFLICT (component) DO UPDATE SET last_seen_at=NOW(), status='ok'
        """)
        _hb.commit(); _hb.close()
    except Exception:
        pass
