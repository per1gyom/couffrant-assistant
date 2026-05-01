"""
Gmail Pub/Sub Watch — gestion du subscription/renewal pour push notifications.

Phase Connexions Universelles - Semaine 4 (Etape 4.5, 1er mai 2026 soir).
Voir docs/vision_connexions_universelles_01mai.md.

PRINCIPE :
─────────────────────────────────────────────────────────────────
Gmail API ne supporte PAS les webhooks HTTP directs. Il faut passer
par Google Cloud Pub/Sub :

  1. Creer un Topic Pub/Sub dans Google Cloud Console
  2. Creer une Push Subscription qui POSTe sur notre endpoint
  3. Pour chaque boite Gmail, appeler /users/me/watch avec le topicName
     et la liste des labelIds a surveiller
  4. Google envoie une notification Pub/Sub a chaque change Gmail
  5. Pub/Sub POST le payload (base64 encode) sur notre endpoint
  6. Notre endpoint decode et declenche un poll history immediat

CONTRAINTE :
─────────────────────────────────────────────────────────────────
Le watch Gmail expire au bout de 7 jours. Il faut le renouveler
regulierement. On le fait toutes les 24h (a 6h UTC) pour les watch
qui expirent dans <2 jours. Comme ca on a au moins 5 jours de marge
si le job de renewal lui-meme echoue.

VARIABLES D ENV :
─────────────────────────────────────────────────────────────────
GMAIL_PUBSUB_TOPIC : projects/<PROJECT>/topics/<TOPIC>
                     ex: projects/elyo-prod/topics/gmail-notifications

SETUP MANUEL CONSOLE GCP (a faire par l user une seule fois) :
─────────────────────────────────────────────────────────────────
1. Activer Pub/Sub API
2. Creer un topic gmail-notifications
3. Donner role "Pub/Sub Publisher" au service account
   gmail-api-push@system.gserviceaccount.com sur ce topic
4. Creer une Push Subscription qui POST sur :
   https://app.raya-ia.fr/webhook/gmail/pubsub?token=<SECRET>
5. Mettre les vars Railway :
     GMAIL_PUBSUB_TOPIC=projects/<PROJECT>/topics/<TOPIC>
     GMAIL_PUBSUB_VERIFICATION_TOKEN=<SECRET genere>
"""

import logging
import os
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger("raya.gmail_watch")

_GMAIL_API = "https://gmail.googleapis.com/gmail/v1/users/me"

# Labels Gmail a surveiller (les memes que PERIMETRE_LABELS du polling)
WATCH_LABELS = [
    "INBOX", "SENT", "SPAM",
    "CATEGORY_PERSONAL", "CATEGORY_PROMOTIONS", "CATEGORY_SOCIAL",
    "CATEGORY_UPDATES", "CATEGORY_FORUMS",
]

# Renouveler les watch qui expirent dans moins de N jours
RENEWAL_THRESHOLD_DAYS = 2

# Le watch Gmail dure 7 jours max
WATCH_DURATION_DAYS = 7


def _get_topic_name() -> Optional[str]:
    """Lit la variable d env GMAIL_PUBSUB_TOPIC."""
    topic = os.getenv("GMAIL_PUBSUB_TOPIC", "").strip()
    return topic if topic else None


def setup_gmail_watch(token: str, connection_id: int) -> dict:
    """Inscrit une boite Gmail au Pub/Sub Watch.

    Args:
        token: access_token Gmail valide.
        connection_id: id de la connexion (pour stocker la metadata).

    Returns:
        Dict avec keys :
          - status: 'ok' | 'no_topic' | 'auth_error' | 'error'
          - history_id: le historyId au moment du watch (pour bootstrap)
          - expiration: ms unix du moment d expiration du watch
          - error_detail: si erreur

    Effet de bord : stocke history_id et watch_expiration dans
    connection_health.metadata.
    """
    import requests

    topic_name = _get_topic_name()
    if not topic_name:
        return {
            "status": "no_topic",
            "error_detail": "GMAIL_PUBSUB_TOPIC non defini en env",
        }

    try:
        r = requests.post(
            f"{_GMAIL_API}/watch",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json={
                "topicName": topic_name,
                "labelIds": WATCH_LABELS,
                "labelFilterAction": "include",
            },
            timeout=20,
        )
        if r.status_code == 401 or r.status_code == 403:
            return {
                "status": "auth_error",
                "error_detail": (
                    f"HTTP {r.status_code} - {(r.text or '')[:200]}"
                ),
            }
        if r.status_code != 200:
            return {
                "status": "error",
                "error_detail": (
                    f"HTTP {r.status_code} - {(r.text or '')[:200]}"
                ),
            }
        data = r.json()
        # Reponse Gmail :
        #   { "historyId": "12345", "expiration": "1700000000000" }
        history_id = str(data.get("historyId", ""))
        expiration_ms = int(data.get("expiration", 0))

        # Stocke en metadata
        _store_watch_metadata(connection_id, history_id, expiration_ms)

        logger.info(
            "[GmailWatch] Setup OK pour conn #%d : historyId=%s, "
            "expiration=%s",
            connection_id, history_id,
            datetime.fromtimestamp(expiration_ms / 1000, tz=timezone.utc).isoformat()
            if expiration_ms else "?",
        )
        return {
            "status": "ok",
            "history_id": history_id,
            "expiration_ms": expiration_ms,
        }
    except Exception as e:
        return {
            "status": "error",
            "error_detail": f"crash : {str(e)[:200]}",
        }


def stop_gmail_watch(token: str) -> bool:
    """Arrete le watch d une boite Gmail.

    Utile pour :
      - Reinitialiser un watch qui marche pas
      - Liberer les ressources avant suppression d une connexion

    Args:
        token: access_token Gmail valide.

    Returns:
        True si OK ou si pas de watch actif, False sinon.
    """
    import requests
    try:
        r = requests.post(
            f"{_GMAIL_API}/stop",
            headers={"Authorization": f"Bearer {token}"},
            timeout=20,
        )
        # 204 No Content = succes ; 404 = pas de watch (ok aussi)
        return r.status_code in (204, 404)
    except Exception as e:
        logger.warning("[GmailWatch] stop crash : %s", str(e)[:200])
        return False


def _store_watch_metadata(connection_id: int, history_id: str,
                           expiration_ms: int) -> None:
    """Stocke history_id et watch_expiration dans connection_health.metadata.

    On ecrase l ancien historyId par le nouveau retourne par /watch.
    C est le SEUL historyId fiable pour ce watch (Gmail garantit qu il
    capture tous les changements a partir de cet ID).
    """
    from app.database import get_pg_conn
    import json

    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        # Recupere la metadata actuelle
        c.execute("""
            SELECT metadata FROM connection_health
            WHERE connection_id = %s
        """, (connection_id,))
        row = c.fetchone()
        metadata = {}
        if row and row[0]:
            metadata = (
                row[0] if isinstance(row[0], dict) else json.loads(row[0])
            )

        metadata["history_id"] = history_id
        metadata["watch_expiration_ms"] = expiration_ms
        metadata["watch_set_at"] = datetime.now(timezone.utc).isoformat()

        c.execute("""
            UPDATE connection_health
            SET metadata = %s
            WHERE connection_id = %s
        """, (json.dumps(metadata), connection_id))
        conn.commit()
    except Exception as e:
        logger.error(
            "[GmailWatch] _store_watch_metadata echec %d : %s",
            connection_id, str(e)[:200],
        )
    finally:
        if conn: conn.close()


def _get_watch_metadata(connection_id: int) -> dict:
    """Lit la metadata watch d une connexion."""
    from app.database import get_pg_conn
    import json

    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            SELECT metadata FROM connection_health
            WHERE connection_id = %s
        """, (connection_id,))
        row = c.fetchone()
        if row and row[0]:
            metadata = (
                row[0] if isinstance(row[0], dict) else json.loads(row[0])
            )
            return metadata
        return {}
    except Exception:
        return {}
    finally:
        if conn: conn.close()


def run_gmail_watch_renewal():
    """Job nocturne (6h00 UTC) : renouvelle les watch qui expirent dans
    moins de RENEWAL_THRESHOLD_DAYS jours.

    Tourne en best effort : ne plante jamais le scheduler.
    """
    started_at = datetime.now()
    total_renewed = 0
    total_skipped = 0
    total_failed = 0

    if not _get_topic_name():
        logger.info(
            "[GmailWatch] GMAIL_PUBSUB_TOPIC non defini, "
            "renouvellement watch desactive"
        )
        return

    try:
        from app.jobs.mail_gmail_history_sync import _get_gmail_connections
        from app.connection_token_manager import get_connection_token
        connections = _get_gmail_connections()
    except Exception as e:
        logger.error(
            "[GmailWatch] Import connections echec : %s", str(e)[:200])
        return

    if not connections:
        logger.debug("[GmailWatch] Aucune connexion Gmail active, skip")
        return

    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    threshold_ms = (
        RENEWAL_THRESHOLD_DAYS * 24 * 3600 * 1000  # ms dans N jours
    )

    for conn_info in connections:
        connection_id = conn_info["connection_id"]
        tenant_id = conn_info["tenant_id"]
        username = conn_info["username"]
        email = conn_info.get("email", "?")

        try:
            metadata = _get_watch_metadata(connection_id)
            current_expiration = int(metadata.get("watch_expiration_ms", 0))

            # Si watch n existe pas (premier setup) OU expire bientot
            time_to_expiry = current_expiration - now_ms
            needs_renewal = (
                current_expiration == 0
                or time_to_expiry < threshold_ms
            )

            if not needs_renewal:
                total_skipped += 1
                logger.debug(
                    "[GmailWatch] %s/%s : watch encore valide pour "
                    "%.1f jours, skip",
                    username, email, time_to_expiry / (24 * 3600 * 1000),
                )
                continue

            # Recupere un token frais
            token = get_connection_token(
                username=username,
                tool_type="gmail",
                tenant_id=tenant_id,
                email_hint=email if email != "?" else None,
            )
            if not token:
                logger.warning(
                    "[GmailWatch] %s/%s : pas de token, renewal skip",
                    username, email,
                )
                total_failed += 1
                continue

            # Setup le watch
            result = setup_gmail_watch(token, connection_id)
            if result["status"] == "ok":
                total_renewed += 1
                logger.info(
                    "[GmailWatch] Renouvelle %s/%s : history_id=%s",
                    username, email, result["history_id"],
                )
            else:
                total_failed += 1
                logger.warning(
                    "[GmailWatch] Echec %s/%s : %s",
                    username, email, result.get("error_detail", "?"),
                )
        except Exception as e:
            total_failed += 1
            logger.error(
                "[GmailWatch] %s/%s crash : %s",
                username, email, str(e)[:200],
            )

    duration = (datetime.now() - started_at).total_seconds()
    logger.info(
        "[GmailWatch] Renewal termine : %d renouvelle(s), %d skip, "
        "%d echec(s) en %.1fs",
        total_renewed, total_skipped, total_failed, duration,
    )
