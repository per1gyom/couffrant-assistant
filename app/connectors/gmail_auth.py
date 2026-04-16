"""
Authentification OAuth2 Gmail.
Extrait de gmail_connector.py -- SPLIT-C4.
"""
import os
import json
import urllib.parse
import requests as http_requests
from app.database import get_pg_conn
from app.logging_config import get_logger
logger=get_logger("raya.gmail")

GMAIL_CLIENT_ID     = os.getenv("GMAIL_CLIENT_ID", "").strip()
GMAIL_CLIENT_SECRET = os.getenv("GMAIL_CLIENT_SECRET", "").strip()
GMAIL_REDIRECT_URI  = os.getenv("GMAIL_REDIRECT_URI", "").strip()
GMAIL_SCOPES = [
    "https://mail.google.com/",
    "https://www.googleapis.com/auth/contacts",
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/drive",
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


