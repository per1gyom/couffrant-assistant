"""Endpoint webhook Odoo — reception en temps reel depuis base_automation.

Refonte complete le 19/04/2026 suite aux decisions architecturales Q1-Q6
(voir docs/raya_planning_v4.md annexes).

FLOW D UN WEBHOOK :
  1. OpenFire declenche une regle base_automation (create/write/unlink)
  2. Action serveur Python envoie POST ici avec :
       headers : X-Webhook-Token (secret du tenant)
                 X-Webhook-Nonce (identifiant unique anti-rejeu)
                 X-Webhook-Timestamp (epoch seconds)
       body    : {model, record_id, op}
  3. On valide :
       - secret connu -> deduction du tenant_id
       - timestamp < 5 min (sinon rejet : retardataire suspect)
       - nonce pas deja vu (sinon rejet : rejeu)
  4. On enqueue dans vectorization_queue (dedup 5s automatique)
  5. Reponse 202 immediate (worker traite en async)

PRINCIPE 'VA VOIR' (Q3) : le webhook ne contient QUE model+id+op. Le worker
re-fetche le record complet depuis Odoo au moment du traitement. Raison :
securite + coherence en cas de modifications rapides + simplicite de maintenance.
"""

import os
import time
import logging
from typing import Optional

from fastapi import APIRouter, Request, Header, HTTPException

logger = logging.getLogger("raya.webhook_odoo")
router = APIRouter()

# Tolerance max entre le timestamp d envoi (cote Odoo) et NOW (cote Raya).
# Au-dela : rejet (webhook retardataire suspect, potentiellement un rejeu).
MAX_TIMESTAMP_DRIFT_SECONDS = 300  # 5 minutes


def _load_tenant_secrets() -> dict:
    """Construit la table inverse secret -> tenant_id a partir des variables
    d environnement. Convention : ODOO_WEBHOOK_SECRET_<TENANT_UPPER>.

    Exemples de variables attendues dans Railway :
      ODOO_WEBHOOK_SECRET_COUFFRANT -> secret long unique pour tenant 'couffrant'
      ODOO_WEBHOOK_SECRET_JUILLET   -> secret long unique pour tenant 'juillet'

    Un secret ne peut ouvrir que son propre tenant (cloisonnement - Q5).
    Si aucun secret defini, le webhook renvoie 503 a tout appel.

    Appelee a chaque requete pour permettre la rotation des secrets sans
    redemarrage (un ajout de variable Railway = pris en compte immediatement).
    """
    prefix = "ODOO_WEBHOOK_SECRET_"
    secrets = {}
    for key, val in os.environ.items():
        if key.startswith(prefix) and val:
            tenant = key[len(prefix):].lower().strip()
            if tenant:
                secrets[val.strip()] = tenant
    return secrets


def _identify_tenant(token: str) -> Optional[str]:
    """Retourne le tenant_id si le token correspond a un secret connu,
    None sinon. Hash egalite en temps constant pour eviter les timing attacks."""
    import hmac
    if not token:
        return None
    secrets = _load_tenant_secrets()
    for secret, tenant in secrets.items():
        # compare_digest : protection timing attack
        if hmac.compare_digest(token, secret):
            return tenant
    return None


@router.post("/webhooks/odoo/record-changed")
async def webhook_odoo_record_changed(
    request: Request,
    x_webhook_token: Optional[str] = Header(None),
    x_webhook_nonce: Optional[str] = Header(None),
    x_webhook_timestamp: Optional[str] = Header(None),
):
    """Recoit une notification de changement Odoo depuis base_automation.

    Headers requis :
      X-Webhook-Token     : secret du tenant (identifie le tenant - Q5)
      X-Webhook-Nonce     : identifiant unique de ce webhook (anti-rejeu - Q6)
      X-Webhook-Timestamp : epoch seconds d emission (anti-rejeu - Q6)

    Body JSON :
      {
        "model": "sale.order",       # nom du modele Odoo
        "record_id": 42,             # id du record affecte
        "op": "create|write|unlink"  # type d operation
      }

    Retourne :
      202 Accepted : webhook valide et mis en queue
      401 Unauthorized : secret invalide / absent
      403 Forbidden : timestamp trop ancien ou dans le futur
      409 Conflict : nonce deja vu (rejeu detecte, on informe mais pas d erreur)
      400 Bad Request : payload invalide
      503 Service Unavailable : aucun secret configure
    """
    # Verif 1 : secret -> tenant
    tenant_id = _identify_tenant(x_webhook_token or "")
    if not tenant_id:
        if not _load_tenant_secrets():
            raise HTTPException(
                status_code=503,
                detail="Webhook desactive (aucun ODOO_WEBHOOK_SECRET_* configure)",
            )
        logger.warning("[Webhook Odoo] Token invalide ou inconnu")
        raise HTTPException(status_code=401, detail="Invalid webhook token")


    # Verif 2 : timestamp anti-rejeu (derive max 5 min)
    try:
        ts = int(x_webhook_timestamp or "0")
    except ValueError:
        raise HTTPException(status_code=400, detail="X-Webhook-Timestamp invalide")
    now = int(time.time())
    drift = abs(now - ts)
    if drift > MAX_TIMESTAMP_DRIFT_SECONDS:
        logger.warning("[Webhook Odoo] tenant=%s timestamp refuse : drift=%ss",
                       tenant_id, drift)
        raise HTTPException(
            status_code=403,
            detail=f"Timestamp hors plage (drift={drift}s, max={MAX_TIMESTAMP_DRIFT_SECONDS}s)",
        )

    # Verif 3 : nonce present (la verif 'deja vu' est faite par webhook_queue.enqueue)
    if not x_webhook_nonce or len(x_webhook_nonce) < 8:
        raise HTTPException(
            status_code=400,
            detail="X-Webhook-Nonce requis (min 8 caracteres)",
        )

    # Verif 4 : payload JSON
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Body JSON invalide")

    model = (payload.get("model") or "").strip()
    record_id = payload.get("record_id")
    op = (payload.get("op") or "write").strip()

    if not model or not isinstance(record_id, int):
        raise HTTPException(
            status_code=400,
            detail="'model' et 'record_id' (int) requis dans le body",
        )
    if op not in ("create", "write", "unlink"):
        raise HTTPException(
            status_code=400,
            detail=f"'op' doit etre create|write|unlink (recu: {op})",
        )


    # Enqueue dans la vectorization_queue (dedup 5s + anti-rejeu nonce)
    from app.webhook_queue import enqueue

    action = "delete" if op == "unlink" else "upsert"
    try:
        result = enqueue(
            tenant_id=tenant_id,
            source="odoo",
            model_name=model,
            record_id=record_id,
            action=action,
            nonce=x_webhook_nonce,
            priority=5,
            source_info={"op": op, "via": "webhook", "ts": ts},
        )
    except Exception as e:
        logger.error("[Webhook Odoo] enqueue failed tenant=%s : %s",
                     tenant_id, str(e)[:200])
        raise HTTPException(status_code=500, detail="Erreur interne queue")

    if result == "replayed":
        # Nonce deja vu : on repond 409 mais on ne signale pas comme erreur
        # (les clients peuvent legitimement retenter une requete, c est saine)
        logger.info("[Webhook Odoo] tenant=%s %s/%s #%d : rejeu detecte (nonce)",
                    tenant_id, "odoo", model, record_id)
        return {
            "status": "replayed",
            "reason": "nonce_already_seen",
            "model": model, "record_id": record_id,
        }

    logger.info("[Webhook Odoo] tenant=%s %s/%s #%d : %s (op=%s)",
                tenant_id, "odoo", model, record_id, result, op)
    return {
        "status": result,  # "enqueued" ou "deduped"
        "tenant": tenant_id,
        "model": model, "record_id": record_id, "op": op,
    }


@router.get("/webhooks/odoo/health")
async def webhook_odoo_health():
    """Health check public. Pas d auth. Permet a OpenFire de verifier la
    dispo de Raya avant de tenter un POST, et fournit un apercu de la
    configuration (nombre de tenants configures, sans reveler les secrets)."""
    secrets = _load_tenant_secrets()
    return {
        "status": "ok",
        "tenants_configured": sorted(set(secrets.values())),
        "tenant_count": len(set(secrets.values())),
        "max_timestamp_drift_seconds": MAX_TIMESTAMP_DRIFT_SECONDS,
    }
