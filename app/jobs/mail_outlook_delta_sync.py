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
  NIVEAU 2 - webhook accelerateur (Etape 3.6)
  NIVEAU 3 - Lifecycle Notifications (Etape 3.5)
  NIVEAU 4 - reconciliation nocturne (Etape 3.7)

FOLDERS SURVEILLES (decision Q1 + bug 17 jours) :
  - Inbox       : mails entrants
  - SentItems   : mails sortants (INVISIBLE dans le webhook actuel !)
  - JunkEmail   : rattrapage spam mal classe
  - DeletedItems : mails supprimes (trace pour le graphe)
  - Custom folders : auto-discovery via list mailFolders

⚠️ ATTENTION : SHADOW MODE (Etape 3.3) ⚠️
─────────────────────────────────────────────────────────────
Pour cette etape, le module fait LE POLLING DELTA mais :
  - NE TRAITE PAS les messages (pas d appel a process_incoming_mail)
  - NE STOCKE PAS dans mail_memory
  - LOG juste dans connection_health_events (items_seen, items_new)

Le but est de VERIFIER que :
  1. Le delta query Microsoft fonctionne pour cet user/folder
  2. Le delta_link est correctement stocke et reutilise au cycle suivant
  3. Le nombre d items detectes est COHERENT avec ce que le webhook
     actuel ingere dans la meme periode
  4. Aucune erreur d API, de token, de format

Une fois shadow mode valide (1-2 cycles complets reussis), on passe en
mode actif (Etape 3.4) en activant le traitement des messages.

ACTIVATION :
  Variable Railway : SCHEDULER_OUTLOOK_DELTA_SYNC_ENABLED=true
  Par defaut FALSE pour ne pas perturber la prod actuelle.
"""

import json
import logging
import time
from datetime import datetime, timezone
from typing import Optional

from app.database import get_pg_conn

logger = logging.getLogger("raya.outlook_delta_sync")

# Folders surveilles. Microsoft Graph utilise des "well-known names".
# Reference : https://learn.microsoft.com/en-us/graph/api/resources/mailfolder
WELL_KNOWN_FOLDERS = [
    "Inbox",
    "SentItems",
    "JunkEmail",
    # NOTE: "DeletedItems" pas inclus pour eviter spam (peut etre activable
    # par config tenant plus tard si besoin de tracer les suppressions)
]

# Limite de safety : max records a traiter par tick par folder
MAX_MESSAGES_PER_TICK_PER_FOLDER = 500


def _get_folder_delta_link(connection_id: int, folder_name: str) -> Optional[str]:
    """Lit le delta_link stocke pour ce (connection_id, folder).
    Stocke dans connection_health.metadata (JSONB) sous la clef
    'folder_delta_links' qui est un dict {folder_name: delta_link}.
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
    """Stocke le nouveau delta_link pour ce folder. UPSERT du JSONB
    metadata.folder_delta_links."""
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
    """Inscription idempotente dans connection_health (comme Odoo Semaine 2).
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
                        connection_id: int) -> dict:
    """Execute le delta query pour un folder donne.

    Logique :
      - Si on a un delta_link stocke : l utiliser pour ne recuperer que
        les changements depuis la derniere fois
      - Sinon : initialiser le delta query (1er passage = retourne tout
        l historique recent + delta_link initial)

    Returns:
        Dict avec keys:
          - status: 'ok' | 'auth_error' | 'network_error' | etc.
          - items_seen: nb total de messages retournes par l API
          - items_new: nb de NOUVEAUX messages (creation/modification)
          - new_delta_link: nouveau delta_link a stocker
          - error_detail: si status != 'ok'
    """
    from app.graph_client import graph_get

    # Construction de l URL initiale ou reuse du delta_link
    delta_link = _get_folder_delta_link(connection_id, folder_name)

    if delta_link:
        # On reuse le delta_link complet (qui contient deja les params)
        # Microsoft retourne un URL absolu, on appelle directement
        url = delta_link
        # graph_get accepte des URL completes ou des paths relatifs
        # On appelle directement via requests pour les URLs absolus
        params = None
    else:
        # 1er passage : initialiser le delta query
        url = f"/me/mailFolders/{folder_name}/messages/delta"
        # Limiter les fields pour reduire la bande passante en shadow mode
        params = {
            "$select": "id,subject,from,receivedDateTime,bodyPreview,isRead,parentFolderId",
            "$top": MAX_MESSAGES_PER_TICK_PER_FOLDER,
        }

    try:
        # Appel API
        if delta_link:
            # Pour les delta_links absolus, on doit appeler directement requests
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
                    "new_delta_link": None,
                    "error_detail": f"HTTP {r.status_code} : token expire ou revoque",
                }
            elif r.status_code == 410:
                # delta_link expire (limite 30 jours), on doit reinitialiser
                logger.warning(
                    "[OutlookDelta] delta_link expire pour folder=%s, reinit",
                    folder_name,
                )
                _set_folder_delta_link(connection_id, folder_name, "")
                return {
                    "status": "internal_error",
                    "items_seen": 0, "items_new": 0,
                    "new_delta_link": None,
                    "error_detail": "delta_link expire, reinit au prochain cycle",
                }
            else:
                return {
                    "status": "network_error",
                    "items_seen": 0, "items_new": 0,
                    "new_delta_link": None,
                    "error_detail": f"HTTP {r.status_code} : {r.text[:200]}",
                }
        else:
            # 1er passage : appel via graph_get
            response = graph_get(token, url, params=params)
    except Exception as e:
        return {
            "status": "network_error",
            "items_seen": 0, "items_new": 0,
            "new_delta_link": None,
            "error_detail": str(e)[:300],
        }

    # Parse la reponse
    messages = response.get("value", [])
    items_seen = len(messages)

    # Compter les NOUVEAUX (pas @removed = creation/modification)
    items_new = sum(1 for m in messages if "@removed" not in m)
    items_removed = items_seen - items_new

    # Recuperer le nouveau delta_link
    # Microsoft envoie soit @odata.deltaLink (fin du delta) soit
    # @odata.nextLink (page suivante a fetcher)
    new_delta_link = response.get("@odata.deltaLink")
    next_link = response.get("@odata.nextLink")

    # NOTE : pour cette etape shadow mode, on NE pagine PAS via nextLink
    # On fait un seul appel par cycle. Si plus de MAX_MESSAGES_PER_TICK
    # de messages a traiter, on les recuperera au cycle suivant.
    # Si pas de deltaLink mais un nextLink : on stocke le nextLink pour
    # poursuivre au cycle suivant.
    delta_link_to_store = new_delta_link or next_link

    return {
        "status": "ok",
        "items_seen": items_seen,
        "items_new": items_new,
        "items_removed": items_removed,
        "new_delta_link": delta_link_to_store,
        "has_more": next_link is not None,
        "error_detail": None,
    }


def _poll_user_outlook(connection_id: int, tenant_id: str,
                        username: str) -> dict:
    """Polle tous les folders surveilles pour un user donne.

    NOTE shadow mode : NE TRAITE PAS les messages (pas d appel a
    process_incoming_mail). On compte juste les items pour comparaison
    avec le webhook actuel.
    """
    from app.token_manager import get_valid_microsoft_token

    poll_started = datetime.now()

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
        # Pas de token : on log l event mais avec status auth_error
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
    folders_ok = 0
    folders_failed = 0
    per_folder_stats = {}

    for folder_name in WELL_KNOWN_FOLDERS:
        try:
            result = _poll_folder_delta(token, folder_name, connection_id)
            per_folder_stats[folder_name] = result

            if result["status"] == "ok":
                folders_ok += 1
                total_seen += result["items_seen"]
                total_new += result["items_new"]

                # Stockage du nouveau delta_link
                if result["new_delta_link"]:
                    _set_folder_delta_link(
                        connection_id, folder_name, result["new_delta_link"],
                    )

                # SHADOW MODE : on log mais on ne traite PAS les messages
                if result["items_new"] > 0:
                    logger.info(
                        "[OutlookDelta][SHADOW] %s/%s/%s : %d items detectes "
                        "(NON TRAITES, shadow mode)",
                        username, folder_name,
                        "init" if not _get_folder_delta_link(connection_id, folder_name) else "delta",
                        result["items_new"],
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

        # Status global : ok si majorite des folders ok
        if folders_failed >= len(WELL_KNOWN_FOLDERS) / 2:
            global_status = "internal_error"
            error_detail = f"{folders_failed}/{len(WELL_KNOWN_FOLDERS)} folders en erreur"
        else:
            global_status = "ok"
            error_detail = (
                f"SHADOW MODE - {folders_ok}/{len(WELL_KNOWN_FOLDERS)} folders OK, "
                f"items_new={total_new} (NON TRAITES)"
            )

        duration_ms = int((datetime.now() - poll_started).total_seconds() * 1000)
        record_poll_attempt(
            connection_id=connection_id,
            status=global_status,
            items_seen=total_seen,
            items_new=total_new,
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
        "per_folder": per_folder_stats,
    }


def _get_outlook_connections() -> list:
    """Retourne la liste des connexions Outlook actives (multi-user, multi-tenant).

    Format retourne :
      [
        {"connection_id": int, "tenant_id": str, "username": str, "email": str},
        ...
      ]
    """
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        # On filtre sur tool_type = 'microsoft' ou 'outlook' et statut 'connected'
        c.execute("""
            SELECT id, tenant_id, username, label, status, tool_type
            FROM tenant_connections
            WHERE tool_type IN ('microsoft', 'outlook')
              AND status = 'connected'
            ORDER BY id
        """)
        return [{
            "connection_id": r[0],
            "tenant_id": r[1],
            "username": r[2],
            "label": r[3] or "Outlook",
            "tool_type": r[5],
        } for r in c.fetchall()]
    except Exception as e:
        logger.error("[OutlookDelta] _get_outlook_connections echec : %s",
                     str(e)[:200])
        return []
    finally:
        if conn: conn.close()


def run_outlook_delta_sync():
    """Fonction principale appellee par APScheduler toutes les 5 min.

    Pour chaque connexion Outlook active :
      - Recupere le token Microsoft
      - Polle chaque folder (Inbox, SentItems, JunkEmail) via delta query
      - Log dans connection_health_events
      - SHADOW MODE : ne traite PAS les messages
    """
    started_at = datetime.now()
    connections = _get_outlook_connections()

    if not connections:
        logger.debug("[OutlookDelta] Aucune connexion Outlook active, skip")
        return

    total_seen = 0
    total_new = 0
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
        except Exception as e:
            users_failed += 1
            logger.error(
                "[OutlookDelta] Crash sur connection_id=%s : %s",
                conn_info["connection_id"], str(e)[:300],
            )

    duration = (datetime.now() - started_at).total_seconds()
    if total_new > 0 or users_failed > 0:
        logger.info(
            "[OutlookDelta] Cycle termine en %.1fs : %d connexions OK, "
            "%d echec, %d items vus, %d nouveaux (SHADOW MODE - non traites)",
            duration, users_ok, users_failed, total_seen, total_new,
        )
