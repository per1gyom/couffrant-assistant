"""
Connecteur DALL-E — génération d'images via l'API OpenAI.
Utilise la clé OPENAI_API_KEY déjà en place pour les embeddings.
"""
import os
import requests as http_requests
from app.logging_config import get_logger

logger = get_logger("raya.dalle")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()


def is_configured() -> bool:
    """True si la clé OpenAI est disponible."""
    return bool(OPENAI_API_KEY)


def generate_image(prompt: str, size: str = "1024x1024") -> dict:
    """
    Génère une image via DALL-E 3.
    Retourne {"url": ..., "revised_prompt": ...} ou {"error": ...}.
    """
    if not OPENAI_API_KEY:
        return {"error": "Génération d'images non configurée (OPENAI_API_KEY manquant)"}

    try:
        resp = http_requests.post(
            "https://api.openai.com/v1/images/generations",
            headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": "dall-e-3",
                "prompt": prompt,
                "n": 1,
                "size": size,
                "quality": "standard",
            },
            timeout=60,
        )

        if resp.status_code != 200:
            error_msg = resp.text[:200]
            logger.error(f"[DALL-E] Erreur API: {resp.status_code} — {error_msg}")
            return {"error": f"Erreur DALL-E ({resp.status_code}): {error_msg}"}

        data = resp.json()
        image_data = data.get("data", [{}])[0]
        url = image_data.get("url", "")
        revised = image_data.get("revised_prompt", prompt)

        logger.info(f"[DALL-E] Image générée — prompt: {prompt[:80]}...")
        return {"url": url, "revised_prompt": revised}

    except Exception as e:
        logger.error(f"[DALL-E] Exception: {e}")
        return {"error": str(e)[:200]}
