"""
Connecteur Gmail — Phase 7 (7-1a).
Utilise l'API Google Gmail pour récupérer les mails.
Polling incrémental via historyId (pas de webhook).

Variables d'environnement OBLIGATOIRES pour activer Gmail :
  GMAIL_CLIENT_ID      : Client ID Google OAuth2
  GMAIL_CLIENT_SECRET  : Client Secret Google OAuth2
  GMAIL_REDIRECT_URI   : https://[domaine-railway].railway.app/auth/gmail/callback

Les tokens sont stockés dans la table gmail_tokens (un enregistrement par user).

HOTFIX-GMAIL-PKCE v2 : contourne PKCE en construisant l'URL manuellement.
  Les web apps avec client_secret n'ont pas besoin de PKCE.
  L'échange de tokens se fait aussi par requête directe (pas via Flow).
"""
import os
import json
import urllib.parse
import requests as http_requests
from app.database import get_pg_conn
from app.logging_config import get_logger
from app.connectors.gmail_auth import is_configured,get_gmail_auth_url,exchange_code_for_tokens  # noqa

logger = get_logger("raya.gmail")

GMAIL_CLIENT_ID = os.getenv("GMAIL_CLIENT_ID", "").strip()
GMAIL_CLIENT_SECRET = os.getenv("GMAIL_CLIENT_SECRET", "").strip()
GMAIL_REDIRECT_URI = os.getenv("GMAIL_REDIRECT_URI", "").strip()

GMAIL_SCOPES = [
    "https://mail.google.com/",          # Accès complet : lecture, envoi, suppression, labels, archive, corbeille
    "https://www.googleapis.com/auth/userinfo.email",
    "openid",
]


def get_gmail_service(username: str):
    """
    Retourne un service Gmail authentifié pour l'utilisateur.
    Rafraîchit automatiquement le token si expiré.
    """
    if not is_configured():
        return None

    try:
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
    except ImportError:
        logger.warning("[Gmail] google-api-python-client non installé")
        return None

    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            SELECT access_token, refresh_token
            FROM gmail_tokens WHERE username = %s
        """, (username,))
        row = c.fetchone()
    except Exception as e:
        logger.error(f"[Gmail] Erreur lecture gmail_tokens {username}: {e}")
        return None
    finally:
        if conn: conn.close()

    if not row:
        # Fallback : essayer users.gmail_credentials pour compatibilité
        try:
            conn = get_pg_conn()
            c = conn.cursor()
            c.execute("SELECT gmail_credentials FROM users WHERE username = %s", (username,))
            row2 = c.fetchone()
            conn.close()
            if row2 and row2[0]:
                cred_data = row2[0]
                row = (
                    cred_data.get("token", ""),
                    cred_data.get("refresh_token", ""),
                )
            else:
                return None
        except Exception:
            return None

    access_token, refresh_token = row
    if not refresh_token:
        return None

    creds = Credentials(
        token=access_token,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=GMAIL_CLIENT_ID,
        client_secret=GMAIL_CLIENT_SECRET,
        scopes=GMAIL_SCOPES,
    )

    if creds.expired and creds.refresh_token:
        try:
            from google.auth.transport.requests import Request
            creds.refresh(Request())
            _save_refreshed_credentials(username, creds)
        except Exception as e:
            logger.error(f"[Gmail] Erreur refresh {username}: {e}")
            return None

    try:
        return build("gmail", "v1", credentials=creds)
    except Exception as e:
        logger.error(f"[Gmail] Erreur build service {username}: {e}")
        return None


def _save_refreshed_credentials(username: str, creds) -> None:
    """Sauvegarde les credentials rafraîchis dans gmail_tokens."""
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        try:
            c.execute("""
                INSERT INTO gmail_tokens (username, access_token, refresh_token, updated_at)
                VALUES (%s, %s, %s, NOW())
                ON CONFLICT (username) DO UPDATE
                SET access_token = EXCLUDED.access_token,
                    updated_at   = NOW()
            """, (username, creds.token, creds.refresh_token))
        except Exception:
            conn.rollback()
            c.execute("""
                INSERT INTO gmail_tokens (username, access_token, refresh_token)
                VALUES (%s, %s, %s)
                ON CONFLICT (username) DO UPDATE
                SET access_token = EXCLUDED.access_token
            """, (username, creds.token, creds.refresh_token))
        conn.commit()
    except Exception as e:
        logger.error(f"[Gmail] Erreur sauvegarde credentials {username}: {e}")
    finally:
        if conn: conn.close()


def fetch_new_messages(username: str, max_results: int = 20) -> list:
    """Récupère les nouveaux mails Gmail depuis le dernier polling."""
    service = get_gmail_service(username)
    if not service:
        return []

    conn = None
    last_history_id = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("SELECT gmail_last_history_id FROM users WHERE username = %s", (username,))
        row = c.fetchone()
        last_history_id = row[0] if row else None
    except Exception as e:
        logger.error(f"[Gmail] Erreur lecture historyId {username}: {e}")
        return []
    finally:
        if conn: conn.close()

    messages = []

    try:
        if last_history_id:
            try:
                history = service.users().history().list(
                    userId="me",
                    startHistoryId=last_history_id,
                    historyTypes=["messageAdded"],
                    maxResults=max_results,
                ).execute()

                new_history_id = history.get("historyId", last_history_id)
                msg_ids = set()
                for record in history.get("history", []):
                    for added in record.get("messagesAdded", []):
                        msg_id = added.get("message", {}).get("id")
                        if msg_id:
                            msg_ids.add(msg_id)

                for msg_id in msg_ids:
                    msg = _get_message_details(service, msg_id)
                    if msg:
                        messages.append(msg)

                _update_history_id(username, new_history_id)

            except Exception as e:
                if "404" in str(e) or "historyid" in str(e).lower():
                    logger.warning(f"[Gmail] historyId invalide pour {username}, full fetch")
                    messages = _full_fetch(service, username, max_results)
                else:
                    raise
        else:
            messages = _full_fetch(service, username, max_results)

    except Exception as e:
        logger.error(f"[Gmail] Erreur fetch {username}: {e}")

    return messages


def _full_fetch(service, username: str, max_results: int) -> list:
    """Fetch initial : récupère les derniers mails et initialise historyId."""
    messages = []
    try:
        result = service.users().messages().list(
            userId="me", maxResults=max_results, q="is:inbox"
        ).execute()

        for msg_meta in result.get("messages", []):
            msg = _get_message_details(service, msg_meta["id"])
            if msg:
                messages.append(msg)

        profile = service.users().getProfile(userId="me").execute()
        _update_history_id(username, profile.get("historyId"))

    except Exception as e:
        logger.error(f"[Gmail] Erreur full fetch {username}: {e}")
    return messages


def _get_message_details(service, msg_id: str) -> dict | None:
    """Récupère les détails d'un message Gmail (métadonnées uniquement)."""
    try:
        msg = service.users().messages().get(
            userId="me", id=msg_id, format="metadata",
            metadataHeaders=["From", "Subject", "Date"],
        ).execute()

        headers = {h["name"].lower(): h["value"] for h in msg.get("payload", {}).get("headers", [])}
        return {
            "message_id": f"gmail_{msg_id}",
            "gmail_id": msg_id,
            "sender": headers.get("from", ""),
            "subject": headers.get("subject", ""),
            "preview": msg.get("snippet", "")[:500],
            "received_at": headers.get("date", ""),
        }
    except Exception:
        return None


def _update_history_id(username: str, history_id: str) -> None:
    """Met à jour le historyId en base."""
    if not history_id:
        return
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            UPDATE users SET gmail_last_history_id = %s WHERE username = %s
        """, (str(history_id), username))
        conn.commit()
    except Exception as e:
        logger.error(f"[Gmail] Erreur update historyId {username}: {e}")
    finally:
        if conn: conn.close()


def send_gmail_message(username: str, to_email: str, subject: str, html_body: str) -> dict:
    """
    Envoie un mail depuis la boîte Gmail de l'utilisateur.
    Retourne {"ok": True, "message_id": ...} ou {"ok": False, "error": ...}.
    Nécessite le scope gmail.send — si absent, retourne une erreur avec lien de re-auth.
    """
    service = get_gmail_service(username)
    if not service:
        return {"ok": False, "error": "Gmail non connecté — reconnecte ta boîte Gmail via Paramètres."}

    import base64
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText

    # Récupérer l'adresse Gmail de l'expéditeur
    gmail_email = ""
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("SELECT email FROM gmail_tokens WHERE username=%s LIMIT 1", (username,))
        row = c.fetchone()
        if row and row[0]:
            gmail_email = row[0]
    except Exception:
        pass
    finally:
        if conn: conn.close()

    try:
        # Injecter la signature
        from app.email_signature import get_email_signature
        signature = get_email_signature(username, gmail_email)
        full_body = f'<div style="font-family:Arial,sans-serif;font-size:14px;color:#222;">{html_body}</div>{signature}'

        msg = MIMEMultipart("alternative")
        msg["To"] = to_email
        msg["Subject"] = subject
        if gmail_email:
            msg["From"] = gmail_email
        msg.attach(MIMEText(full_body, "html", "utf-8"))

        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        result = service.users().messages().send(
            userId="me",
            body={"raw": raw}
        ).execute()

        return {"ok": True, "message_id": result.get("id"), "from": gmail_email or "Gmail"}

    except Exception as e:
        err_str = str(e)
        if "insufficient" in err_str.lower() or "scope" in err_str.lower() or "403" in err_str:
            return {
                "ok": False,
                "error": "Permissions insuffisantes — reconnecte ta boîte Gmail pour autoriser l'envoi (/login/gmail)."
            }
        return {"ok": False, "error": f"Erreur envoi Gmail : {err_str[:150]}"}
