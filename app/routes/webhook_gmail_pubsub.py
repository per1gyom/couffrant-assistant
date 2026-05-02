"""
Webhook Pub/Sub Gmail — recoit les notifications push de Google Cloud Pub/Sub.

Phase Connexions Universelles - Semaine 4 (Etape 4.5/4.6, 1er mai 2026 soir).

PRINCIPE :
─────────────────────────────────────────────────────────────────
Quand un mail change dans une boite Gmail "watched" (cf
mail_gmail_watch.py), Google publie un message dans le Topic Pub/Sub
configure. Pub/Sub POSTe ce message sur cet endpoint.

Le payload Pub/Sub est un JSON de la forme :
{
  "message": {
    "data": "<base64 encoded JSON>",  // {"emailAddress":..., "historyId":...}
    "messageId": "...",
    "publishTime": "...",
    "attributes": {}
  },
  "subscription": "projects/.../subscriptions/..."
}

Apres decodage, on a :
{
  "emailAddress": "user@example.com",
  "historyId": "12345"
}

WORKFLOW :
─────────────────────────────────────────────────────────────────
1. Reception du POST de Pub/Sub
2. Validation token (?token=<SECRET>) si GMAIL_PUBSUB_VERIFICATION_TOKEN
3. Decodage payload base64 -> {emailAddress, historyId}
4. Identification de la connexion Gmail par email
5. Mode dependant de GMAIL_WEBHOOK_TRIGGER_MODE :
     - SHADOW (false) : log juste, retourne 200
     - TRIGGER (true) : declenche poll_user_gmail immediat
6. Retour 200 OK rapide (Pub/Sub timeout 10s, sinon retry)

NOTE SECURITY :
─────────────────────────────────────────────────────────────────
La validation par token URL est suffisante pour le MVP mais fragile.
A terme : valider le JWT signe par Google (audience = URL endpoint).
Pour l instant, le token URL evite que n importe qui poste sur
l endpoint.
"""

import base64
import json
import logging
import os
from typing import Optional

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse

logger = logging.getLogger("raya.webhook.gmail_pubsub")

router = APIRouter()


def _get_verification_token() -> Optional[str]:
    """Lit la variable d env GMAIL_PUBSUB_VERIFICATION_TOKEN."""
    tok = os.getenv("GMAIL_PUBSUB_VERIFICATION_TOKEN", "").strip()
    return tok if tok else None


def _is_trigger_mode_enabled() -> bool:
    """Lit GMAIL_WEBHOOK_TRIGGER_MODE.

    SHADOW (false, default) : log la notification mais ne fait rien
    TRIGGER (true) : declenche poll history immediat
    """
    val = os.getenv("GMAIL_WEBHOOK_TRIGGER_MODE", "").strip().lower()
    return val in ("1", "true", "yes", "on")


def _find_connection_by_email(email: str) -> Optional[dict]:
    """Retrouve la connexion Gmail correspondante a un email.

    Returns:
        Dict {connection_id, tenant_id, username, email} ou None.
    """
    from app.database import get_pg_conn
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            SELECT tc.id, tc.tenant_id, ca.username, tc.connected_email
            FROM tenant_connections tc
            JOIN connection_assignments ca ON ca.connection_id = tc.id
            WHERE tc.tool_type = 'gmail'
              AND tc.status = 'connected'
              AND ca.enabled = true
              AND LOWER(tc.connected_email) = LOWER(%s)
            LIMIT 1
        """, (email,))
        row = c.fetchone()
        if not row:
            return None
        return {
            "connection_id": row[0],
            "tenant_id": row[1],
            "username": row[2],
            "email": row[3],
        }
    except Exception as e:
        logger.error(
            "[GmailPubSub] _find_connection_by_email crash : %s",
            str(e)[:200],
        )
        return None
    finally:
        if conn: conn.close()


def _track_pubsub_received(connection_id: int, history_id: str,
                              email: str, mode: str) -> None:
    """Trace en DB chaque push Pub/Sub recu, peu importe le mode.
    Stocke en metadata : last_pubsub_received_at, last_pubsub_history_id,
    last_pubsub_email, last_pubsub_mode, pubsub_received_count.
    Permet de verifier en mode SHADOW que Pub/Sub a bien recu quelque
    chose, sans avoir a fouiller les logs Railway.
    """
    from app.database import get_pg_conn
    from datetime import datetime, timezone
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute(
            "SELECT metadata FROM connection_health WHERE connection_id = %s",
            (connection_id,),
        )
        row = c.fetchone()
        metadata = {}
        if row and row[0]:
            metadata = (
                row[0] if isinstance(row[0], dict) else json.loads(row[0])
            )
        metadata["last_pubsub_received_at"] = datetime.now(
            timezone.utc).isoformat()
        metadata["last_pubsub_history_id"] = history_id
        metadata["last_pubsub_email"] = email
        metadata["last_pubsub_mode"] = mode
        metadata["pubsub_received_count"] = (
            int(metadata.get("pubsub_received_count", 0)) + 1
        )
        c.execute(
            "UPDATE connection_health SET metadata = %s "
            "WHERE connection_id = %s",
            (json.dumps(metadata), connection_id),
        )
        conn.commit()
    except Exception as e:
        logger.error(
            "[GmailPubSub] _track_pubsub_received echec : %s",
            str(e)[:200],
        )
    finally:
        if conn: conn.close()


@router.post("/webhook/gmail/pubsub")
async def gmail_pubsub_webhook(request: Request):
    """Endpoint recevant les push Pub/Sub de Gmail.

    IMPORTANT : doit retourner 200 rapidement (timeout Pub/Sub = 10s).
    Sinon Pub/Sub retry et on accumule des doublons.
    """
    # ─── 1. Validation token (security minimale) ───
    expected_token = _get_verification_token()
    if expected_token:
        provided = request.query_params.get("token", "")
        if provided != expected_token:
            logger.warning(
                "[GmailPubSub] Token invalide (provided=%s)",
                provided[:8] + "..." if provided else "(vide)",
            )
            raise HTTPException(status_code=401, detail="invalid token")

    # ─── 2. Parse du payload ───
    try:
        body = await request.json()
    except Exception as e:
        logger.warning(
            "[GmailPubSub] Body non parsable JSON : %s", str(e)[:200])
        # Pub/Sub interprete 4xx comme echec definitif (pas de retry)
        # on retourne 200 pour eviter d accumuler des erreurs
        return JSONResponse({"status": "bad_body"}, status_code=200)

    message = body.get("message", {})
    data_b64 = message.get("data", "")
    if not data_b64:
        logger.debug("[GmailPubSub] Push sans data, ignore")
        return JSONResponse({"status": "no_data"}, status_code=200)

    try:
        decoded = base64.b64decode(data_b64).decode("utf-8")
        payload = json.loads(decoded)
    except Exception as e:
        logger.warning(
            "[GmailPubSub] Decodage data echec : %s", str(e)[:200])
        return JSONResponse({"status": "bad_data"}, status_code=200)

    email_address = payload.get("emailAddress", "")
    new_history_id = str(payload.get("historyId", ""))

    if not email_address or not new_history_id:
        logger.debug(
            "[GmailPubSub] Payload incomplet : email=%s, historyId=%s",
            email_address, new_history_id,
        )
        return JSONResponse({"status": "incomplete"}, status_code=200)

    # ─── 3. Identification de la connexion ───
    conn_info = _find_connection_by_email(email_address)
    if not conn_info:
        logger.info(
            "[GmailPubSub] Notification pour %s mais pas de connexion "
            "active correspondante, ignore",
            email_address,
        )
        return JSONResponse({"status": "unknown_email"}, status_code=200)

    # ─── 4. Mode SHADOW vs TRIGGER ───
    trigger_mode = _is_trigger_mode_enabled()
    mode_label = "trigger" if trigger_mode else "shadow"

    # Tracking en DB (independant du mode) pour permettre la verification
    # post-test sans fouiller les logs Railway
    _track_pubsub_received(
        connection_id=conn_info["connection_id"],
        history_id=new_history_id,
        email=email_address,
        mode=mode_label,
    )

    if not trigger_mode:
        # Mode SHADOW : log juste, ne fait rien
        logger.info(
            "[GmailPubSub][SHADOW] Notif %s -> conn #%d (historyId=%s) "
            "- ne traite PAS (TRIGGER mode off)",
            email_address, conn_info["connection_id"], new_history_id,
        )
        return JSONResponse(
            {"status": "ok", "mode": "shadow"}, status_code=200,
        )

    # Mode TRIGGER : declenche le poll history immediat (best effort)
    logger.info(
        "[GmailPubSub][TRIGGER] Notif %s -> conn #%d (historyId=%s)",
        email_address, conn_info["connection_id"], new_history_id,
    )
    try:
        # Import lazy pour eviter les cycles d import au boot
        from app.jobs.mail_gmail_history_sync import (
            _poll_user_gmail,
            _get_gmail_token_for_connection,
        )

        token = _get_gmail_token_for_connection(
            connection_id=conn_info["connection_id"],
            username=conn_info["username"],
            email=conn_info["email"] or "",
            tenant_id=conn_info["tenant_id"],
        )
        if not token:
            logger.warning(
                "[GmailPubSub][TRIGGER] Pas de token pour conn #%d, "
                "ignore",
                conn_info["connection_id"],
            )
            return JSONResponse(
                {"status": "no_token"}, status_code=200,
            )

        # Lance le poll - le polling 5 min sert de filet si ca echoue
        result = _poll_user_gmail(
            connection_id=conn_info["connection_id"],
            tenant_id=conn_info["tenant_id"],
            username=conn_info["username"],
            token=token,
            email=conn_info["email"] or "?",
        )
        return JSONResponse(
            {
                "status": "triggered",
                "mode": "trigger",
                "poll_status": result.get("status", "?"),
            },
            status_code=200,
        )
    except Exception as e:
        # Toujours retourner 200 pour eviter retry infini
        logger.error(
            "[GmailPubSub][TRIGGER] Crash : %s", str(e)[:200])
        return JSONResponse(
            {"status": "trigger_crash", "error": str(e)[:100]},
            status_code=200,
        )
