"""
Signature email HTML pour Raya — B3 v2.

get_email_signature(username, from_address=None)
  → cherche en DB (email_signatures), fallback statique Guillaume.

extract_and_save_signature(username, tenant_id, token)
  → lit les 5 derniers mails envoyés via Graph, extrait la signature avec Haiku,
    stocke en DB avec UPSERT.

router : POST /admin/extract-signatures (require_admin)
"""
import os
import requests as _requests

from fastapi import APIRouter, Depends
from app.routes.deps import require_admin
from app.logging_config import get_logger

logger = get_logger("raya.signature")
router = APIRouter(tags=["signature"])

# ─── FALLBACK STATIQUE ───

def _static_signature(username: str) -> str:
    """Signature statique Guillaume — fallback si rien en DB."""
    base_url = os.getenv("APP_BASE_URL", "https://app.raya-ia.fr").rstrip("/")
    banner_url = f"{base_url}/static/couffrant_solar_banner.jpg"
    return f"""
<br><br>
<table cellpadding="0" cellspacing="0" style="font-family: Helvetica, Arial, sans-serif; font-size: 14px; color: #333;">
  <tr><td style="padding-bottom: 4px;">Solairement,</td></tr>
  <tr><td style="font-weight: bold; font-size: 15px; padding-bottom: 4px;">Guillaume Perrin</td></tr>
  <tr><td style="padding-bottom: 4px;">&#128222; 06 49 43 09 17</td></tr>
  <tr><td style="padding-bottom: 12px;"><a href="https://couffrant-solar.fr" style="color: #1D6FD9; text-decoration: none;">&#127758; couffrant-solar.fr</a></td></tr>
  <tr><td><img src="{banner_url}" alt="Couffrant Solar" style="width: 500px; max-width: 100%; height: auto; border: 0;"></td></tr>
</table>
"""


# ─── LOOKUP DB ───

def get_email_signature(username: str, from_address: str = None) -> str:
    """
    Retourne la signature HTML pour un utilisateur.

    Ordre de résolution :
      1. DB : email_signatures WHERE username = %s AND email_address = %s (match exact adresse)
      2. DB : email_signatures WHERE username = %s AND email_address IS NULL (signature générique)
      3. Fallback statique Guillaume
    """
    conn = None
    try:
        from app.database import get_pg_conn
        conn = get_pg_conn()
        c = conn.cursor()

        # 1. Match exact sur l'adresse email
        if from_address:
            c.execute("""
                SELECT signature_html FROM email_signatures
                WHERE username = %s AND email_address = %s
                LIMIT 1
            """, (username, from_address))
            row = c.fetchone()
            if row:
                return row[0]

        # 2. Signature générique (email_address IS NULL)
        c.execute("""
            SELECT signature_html FROM email_signatures
            WHERE username = %s AND email_address IS NULL
            LIMIT 1
        """, (username,))
        row = c.fetchone()
        if row:
            return row[0]

    except Exception as e:
        logger.warning("[Signature] DB lookup échoué : %s", e)
    finally:
        if conn:
            conn.close()

    # 3. Fallback statique
    return _static_signature(username)


# ─── EXTRACTION LLM ───

def extract_and_save_signature(username: str, tenant_id: str, token: str) -> dict:
    """
    Lit les 5 derniers mails envoyés via Microsoft Graph, extrait la signature
    avec Haiku (model_tier='fast'), stocke en DB avec UPSERT.

    Retourne : {"ok": bool, "signature_preview": str, "message": str}
    """
    if not token:
        return {"ok": False, "message": "Token Microsoft manquant"}

    # 1. Récupération des mails envoyés
    try:
        resp = _requests.get(
            "https://graph.microsoft.com/v1.0/me/mailFolders/sentitems/messages",
            headers={"Authorization": f"Bearer {token}"},
            params={
                "$top": 5,
                "$select": "body,from",
                "$orderby": "sentDateTime desc",
            },
            timeout=15,
        )
        resp.raise_for_status()
        messages = resp.json().get("value", [])
    except Exception as e:
        logger.warning("[Signature] Graph sentitems échoué : %s", e)
        return {"ok": False, "message": f"Erreur Graph : {str(e)[:100]}"}

    # 2. Premier mail avec un corps HTML non vide
    body_html = ""
    from_address = None
    for msg in messages:
        body = msg.get("body", {})
        if body.get("contentType", "").lower() == "html" and body.get("content", "").strip():
            body_html = body["content"]
            from_addr = msg.get("from", {}).get("emailAddress", {})
            from_address = from_addr.get("address")
            break

    if not body_html:
        return {"ok": False, "message": "Aucun mail HTML trouvé dans les envoyés"}

    # 3. Extraction LLM via Haiku
    try:
        from app.llm_client import llm_complete
        result = llm_complete(
            messages=[{"role": "user", "content": (
                f"Voici le corps HTML d'un mail professionnel :\n\n{body_html[:8000]}\n\n"
                "Extrais UNIQUEMENT la signature email HTML de ce mail. "
                "La signature est le bloc récurrent en bas du mail "
                "(nom, titre, téléphone, logo, etc.). "
                "Retourne UNIQUEMENT le HTML de la signature, sans le corps du mail. "
                "Si tu ne trouves pas de signature, retourne exactement : VIDE"
            )}],
            system="Tu es un extracteur de signature email. Retourne uniquement le HTML demandé, sans explication.",
            model_tier="fast",
            max_tokens=1500,
        )
        extracted = result["text"].strip()
    except Exception as e:
        logger.warning("[Signature] Extraction LLM échouée : %s", e)
        return {"ok": False, "message": f"Erreur LLM : {str(e)[:100]}"}

    if not extracted or extracted.upper() == "VIDE" or len(extracted) < 20:
        return {"ok": False, "message": "Aucune signature détectée dans les mails"}

    # 4. Stockage en DB (UPSERT)
    conn = None
    try:
        from app.database import get_pg_conn
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            INSERT INTO email_signatures
              (username, tenant_id, email_address, signature_html, extracted_from)
            VALUES (%s, %s, %s, %s, 'microsoft_sent')
            ON CONFLICT (username, email_address) DO UPDATE
              SET signature_html = EXCLUDED.signature_html,
                  extracted_from = EXCLUDED.extracted_from
        """, (username, tenant_id, from_address, extracted))
        conn.commit()
        logger.info("[Signature] Signature extraite et sauvegardée pour %s (%s)", username, from_address)
    except Exception as e:
        logger.warning("[Signature] Sauvegarde DB échouée : %s", e)
        return {"ok": False, "message": f"Erreur DB : {str(e)[:100]}"}
    finally:
        if conn:
            conn.close()

    preview = extracted[:200].replace("\n", " ")
    return {"ok": True, "signature_preview": preview, "message": "Signature extraite et sauvegardée"}


# ─── ENDPOINT ADMIN ───

@router.post("/admin/extract-signatures")
def extract_signatures_endpoint(user: dict = Depends(require_admin)):
    """
    Déclenche l'extraction de signature depuis les mails envoyés Microsoft.
    Requiert le token Microsoft de l'utilisateur admin connecté.
    """
    username = user["username"]
    tenant_id = user.get("tenant_id", "couffrant_solar")
    try:
        from app.token_manager import get_valid_microsoft_token
        token = get_valid_microsoft_token(username)
    except Exception as e:
        return {"ok": False, "message": f"Token Microsoft indisponible : {str(e)[:100]}"}

    return extract_and_save_signature(username, tenant_id, token)
