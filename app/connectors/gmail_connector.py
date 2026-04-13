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
    Retourne juste l'URL (string), pas de tuple.

    PKCE désactivé volontairement : on est une web app avec client_secret,
    pas besoin de PKCE. Ça évite le bug "(invalid_grant) Missing code verifier".
    """
    if not GMAIL_REDIRECT_URI:
        raise RuntimeError(
            "GMAIL_REDIRECT_URI non configuré. "
            "Ajoutez cette variable dans Railway : "
            "GMAIL_REDIRECT_URI=https://[votre-domaine].railway.app/auth/gmail/callback"
        )
    if not is_configured():
        raise RuntimeError("GMAIL_CLIENT_ID et GMAIL_CLIENT_SECRET doivent être configurés.")

    params = {
        "client_id": GMAIL_CLIENT_ID,
        "redirect_uri": GMAIL_REDIRECT_URI,
        "response_type": "code",
        "scope": " ".join(GMAIL_SCOPES),
        "access_type": "offline",
        "prompt": "consent",
    }
    url = "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode(params)
    logger.info(f"[Gmail] URL auth générée (sans PKCE) → redirect_uri={GMAIL_REDIRECT_URI}")
    return url


def exchange_code_for_tokens(code: str, code_verifier: str = None) -> dict:
    """
    Échange le code OAuth2 contre des tokens Google.
    Retourne {"access_token", "refresh_token", "email"}.

    Utilise une requête HTTP directe (pas Flow) pour éviter les problèmes PKCE.
    """
    if not is_configured() or not GMAIL_REDIRECT_URI:
        raise RuntimeError("Gmail non configuré (CLIENT_ID / CLIENT_SECRET / REDIRECT_URI manquants)")

    # Requête directe à Google token endpoint — pas de PKCE
    token_data = {
        "code": code,
        "client_id": GMAIL_CLIENT_ID,
        "client_secret": GMAIL_CLIENT_SECRET,
        "redirect_uri": GMAIL_REDIRECT_URI,
        "grant_type": "authorization_code",
    }

    resp = http_requests.post(
        "https://oauth2.googleapis.com/token",
        data=token_data,
        timeout=15,
    )

    if resp.status_code != 200:
        error_detail = resp.text[:300]
        logger.error(f"[Gmail] Token exchange failed: {resp.status_code} — {error_detail}")
        raise RuntimeError(f"Google token exchange failed: {error_detail}")

    token_json = resp.json()
    access_token = token_json.get("access_token", "")
    refresh_token = token_json.get("refresh_token", "")
    id_token_raw = token_json.get("id_token", "")

    # Extraire l'email depuis l'id_token (JWT décodé basique)
    email = ""
    if id_token_raw:
        try:
            import base64
            # id_token est un JWT : header.payload.signature
            payload_b64 = id_token_raw.split(".")[1]
            # Ajouter le padding manquant
            payload_b64 += "=" * (4 - len(payload_b64) % 4)
            payload = json.loads(base64.urlsafe_b64decode(payload_b64))
            email = payload.get("email", "")
        except Exception as e:
            logger.warning(f"[Gmail] Impossible de décoder id_token: {e}")

    logger.info(f"[Gmail] Tokens obtenus — email={email}, refresh={'oui' if refresh_token else 'non'}")

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "email": email,
        "expiry": None,
    }


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
