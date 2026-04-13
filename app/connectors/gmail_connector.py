"""
Connecteur Gmail — Phase 7 (7-1a).
Utilise l'API Google Gmail pour récupérer les mails.
Polling incrémental via historyId (pas de webhook).

Variables d'environnement OBLIGATOIRES pour activer Gmail :
  GMAIL_CLIENT_ID      : Client ID Google OAuth2
  GMAIL_CLIENT_SECRET  : Client Secret Google OAuth2
  GMAIL_REDIRECT_URI   : https://[domaine-railway].railway.app/auth/gmail/callback

Les tokens sont stockés dans la table gmail_tokens (un enregistrement par user).
HOTFIX-GMAIL-TOKENS : _save_refreshed_credentials() gère l'absence de updated_at.
"""
import os
import json
from app.database import get_pg_conn
from app.logging_config import get_logger

logger = get_logger("raya.gmail")

GMAIL_CLIENT_ID = os.getenv("GMAIL_CLIENT_ID", "").strip()
GMAIL_CLIENT_SECRET = os.getenv("GMAIL_CLIENT_SECRET", "").strip()
GMAIL_REDIRECT_URI = os.getenv("GMAIL_REDIRECT_URI", "").strip()

GMAIL_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/userinfo.email",
    "openid",
]


def is_configured() -> bool:
    """True si les clés OAuth2 Gmail sont présentes dans les variables d'env."""
    return bool(GMAIL_CLIENT_ID and GMAIL_CLIENT_SECRET)


def get_gmail_auth_url() -> str:
    """
    Génère l'URL d'autorisation Google OAuth2 pour Gmail.
    Lève une RuntimeError si GMAIL_REDIRECT_URI est manquante.
    """
    if not GMAIL_REDIRECT_URI:
        logger.error(
            "[Gmail] GMAIL_REDIRECT_URI manquant ! "
            "Configurez GMAIL_REDIRECT_URI=https://[domaine].railway.app/auth/gmail/callback "
            "dans les variables Railway."
        )
        raise RuntimeError(
            "GMAIL_REDIRECT_URI non configuré. "
            "Ajoutez cette variable dans Railway : "
            "GMAIL_REDIRECT_URI=https://[votre-domaine].railway.app/auth/gmail/callback"
        )
    if not is_configured():
        logger.error("[Gmail] GMAIL_CLIENT_ID ou GMAIL_CLIENT_SECRET manquant")
        raise RuntimeError("GMAIL_CLIENT_ID et GMAIL_CLIENT_SECRET doivent être configurés.")

    try:
        from google_auth_oauthlib.flow import Flow
    except ImportError:
        logger.warning("[Gmail] google-auth-oauthlib absent, génération URL manuelle")
        import urllib.parse
        params = {
            "client_id": GMAIL_CLIENT_ID,
            "redirect_uri": GMAIL_REDIRECT_URI,
            "response_type": "code",
            "scope": " ".join(GMAIL_SCOPES),
            "access_type": "offline",
            "prompt": "consent",
        }
        return "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode(params)

    flow = Flow.from_client_config(
        {
            "web": {
                "client_id": GMAIL_CLIENT_ID,
                "client_secret": GMAIL_CLIENT_SECRET,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [GMAIL_REDIRECT_URI],
            }
        },
        scopes=GMAIL_SCOPES,
    )
    flow.redirect_uri = GMAIL_REDIRECT_URI
    auth_url, _ = flow.authorization_url(
        access_type="offline",
        prompt="consent",
        include_granted_scopes="true",
    )
    return auth_url


def exchange_code_for_tokens(code: str) -> dict:
    """
    Échange le code OAuth2 contre des tokens Google.
    Retourne {"access_token", "refresh_token", "email"}.
    """
    if not is_configured() or not GMAIL_REDIRECT_URI:
        raise RuntimeError("Gmail non configuré (CLIENT_ID / CLIENT_SECRET / REDIRECT_URI manquants)")

    try:
        from google_auth_oauthlib.flow import Flow
        from google.oauth2 import id_token
        from google.auth.transport import requests as g_requests
    except ImportError:
        raise RuntimeError("google-auth-oauthlib non installé. Ajoutez-le dans requirements.txt")

    flow = Flow.from_client_config(
        {
            "web": {
                "client_id": GMAIL_CLIENT_ID,
                "client_secret": GMAIL_CLIENT_SECRET,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [GMAIL_REDIRECT_URI],
            }
        },
        scopes=GMAIL_SCOPES,
    )
    flow.redirect_uri = GMAIL_REDIRECT_URI
    flow.fetch_token(code=code)
    creds = flow.credentials

    email = ""
    try:
        id_info = id_token.verify_oauth2_token(
            creds.id_token, g_requests.Request(), GMAIL_CLIENT_ID
        )
        email = id_info.get("email", "")
    except Exception as e:
        logger.warning(f"[Gmail] Impossible de lire l'email depuis id_token: {e}")

    return {
        "access_token": creds.token or "",
        "refresh_token": creds.refresh_token or "",
        "email": email,
        "expiry": creds.expiry.isoformat() if creds.expiry else None,
    }


def get_gmail_service(username: str):
    """
    Retourne un service Gmail authentifié pour l'utilisateur.
    Rafraîchit automatiquement le token si expiré.
    Lit les credentials depuis la table gmail_tokens.
    Retourne None si pas de credentials ou si non configuré.
    """
    if not is_configured():
        return None

    try:
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
    except ImportError:
        logger.warning("[Gmail] google-auth-oauthlib / google-api-python-client non installés")
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
    """
    Sauvegarde les credentials rafraîchis dans gmail_tokens.
    Robuste si updated_at n'existe pas encore (avant migration HOTFIX-GMAIL-TOKENS) :
    - Tente d'abord avec updated_at = NOW()
    - Fallback sans updated_at si la colonne est absente
    """
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        try:
            # Version avec updated_at (après migration)
            c.execute("""
                INSERT INTO gmail_tokens (username, access_token, refresh_token, updated_at)
                VALUES (%s, %s, %s, NOW())
                ON CONFLICT (username) DO UPDATE
                SET access_token = EXCLUDED.access_token,
                    updated_at   = NOW()
            """, (username, creds.token, creds.refresh_token))
        except Exception:
            # Fallback : updated_at absent (avant migration)
            conn.rollback()
            c.execute("""
                INSERT INTO gmail_tokens (username, access_token, refresh_token)
                VALUES (%s, %s, %s)
                ON CONFLICT (username) DO UPDATE
                SET access_token = EXCLUDED.access_token
            """, (username, creds.token, creds.refresh_token))
        conn.commit()
        logger.debug(f"[Gmail] Credentials rafraîchis sauvegardés pour {username}")
    except Exception as e:
        logger.error(f"[Gmail] Erreur sauvegarde credentials {username}: {e}")
    finally:
        if conn: conn.close()


def fetch_new_messages(username: str, max_results: int = 20) -> list:
    """
    Récupère les nouveaux mails Gmail depuis le dernier polling.
    Utilise historyId pour le polling incrémental.
    Retourne une liste de dicts {message_id, sender, subject, preview, received_at}.
    """
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
