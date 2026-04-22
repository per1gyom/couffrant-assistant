"""
Endpoint "Approfondir avec Opus" (V2.4 fix - 22/04 soir).

Philosophie : approfondir une reponse n est PAS re-interroger Claude sur
une nouvelle base. C est lui donner - sur les MEMES bases (regles RAG,
historique, graphe, tools, preferences) - la possibilite de reflechir
plus profondement avec un modele plus puissant (Opus 4.7 au lieu de
Sonnet 4.6).

Implementation : on reutilise integralement _raya_core_agent avec le
flag deepen_mode=True. Opus herite donc de :
  - Regles apprises (RAG semantique top 10 pertinentes a la question)
  - 3 derniers echanges (inclut la reponse Sonnet qu il voit comme son
    propre message assistant precedent)
  - Graphe des conversations (via tool search_conversations)
  - Tools Odoo, mails, SharePoint, drive
  - Preferences utilisateur + consignes globales du tenant
  - Boucle agent complete avec tool_use iteratifs

Le seul ajout en mode approfondissement : un bloc system prompt qui
explique a Opus qu il doit ENRICHIR / NUANCER / VERIFIER plutot que
refaire ou accuser Sonnet sans preuve. Implemente cote
raya_agent_core.py.

Historique : la reponse Sonnet originale reste intacte dans aria_memory.
La reponse Opus approfondie s ajoute comme nouvelle ligne (sauvegardee
par _raya_core_agent lui-meme via _save_conversation standard). On
garde les 2 pour comparer plus tard.

Avant (v2.4 initiale) : ~280 lignes avec _DEEPEN_SYSTEM_PROMPT,
_build_deepen_messages, _save_deepen_response, llm_complete en one-shot.
Tout cela etait une MAUVAISE reimplementation qui aveuglait Opus.

Apres (v2.4 fix) : ~90 lignes. Chargement de la question originale,
delegation a la vraie boucle agent. Simplicite et correction.
"""

import concurrent.futures
import traceback

from fastapi import APIRouter, Request, Body, Depends, HTTPException

from app.database import get_pg_conn
from app.logging_config import get_logger
from app.routes.deps import require_user
from app.routes.raya_agent_core import _raya_core_agent

logger = get_logger("raya.deepen")


# ═══════════════════════════════════════════════════════════════════════
# LECTURE de l echange source (Sonnet)
# ═══════════════════════════════════════════════════════════════════════

def _load_original_exchange(aria_memory_id: int, username: str, tenant_id: str):
    """
    Charge l echange source depuis aria_memory, avec verif ownership
    (username + tenant_id). Retourne (user_input, aria_response) ou
    None si introuvable ou non accessible.

    Securite : le filtre tenant_id empeche un user d un tenant A de
    lire la reponse d un user du tenant B via /raya/deepen.
    """
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute(
            "SELECT user_input, aria_response "
            "FROM aria_memory "
            "WHERE id = %s AND username = %s "
            "  AND (tenant_id = %s OR tenant_id IS NULL)",
            (aria_memory_id, username, tenant_id),
        )
        row = c.fetchone()
        if not row:
            return None
        return row[0], row[1]
    except Exception as e:
        logger.exception("[Deepen] load_original error: %s", e)
        return None
    finally:
        if conn:
            conn.close()


# ═══════════════════════════════════════════════════════════════════════
# PAYLOAD DE RELECTURE pour _raya_core_agent
# ═══════════════════════════════════════════════════════════════════════

class _ReplayPayload:
    """
    Mimique l objet RayaQuery (pydantic, defini dans raya_helpers.py)
    pour passer a _raya_core_agent sans contraintes de validation.

    RayaQuery a exactement 4 champs :
      - query : str          (obligatoire)
      - file_data : str|None (base64)
      - file_type : str|None (MIME)
      - file_name : str|None

    En mode deepen, on ne rejoue QUE la query textuelle. Le fichier
    d origine eventuel (image, PDF) a deja ete traite par Sonnet au
    premier tour et sa synthese est dans l historique des 3 derniers
    echanges que Opus verra nativement.
    """
    def __init__(self, query: str):
        self.query = query
        self.file_data = None
        self.file_type = None
        self.file_name = None


# ═══════════════════════════════════════════════════════════════════════
# ENDPOINT FASTAPI
# ═══════════════════════════════════════════════════════════════════════

router = APIRouter(tags=["raya"])


@router.post("/raya/deepen")
def raya_deepen_endpoint(
    request: Request,
    payload: dict = Body(...),
    user: dict = Depends(require_user),
):
    """
    Transforme une reponse Sonnet en reponse Opus approfondie.

    Body JSON attendu :
      { "aria_memory_id": 123 }

    Flow :
      1. Charger la question originale via aria_memory_id (verif ownership)
      2. Construire un _ReplayPayload avec cette query
      3. Appeler _raya_core_agent(deepen_mode=True)
         -> vraie boucle agent avec tous les moyens habituels
         -> tier Opus force
         -> bloc system prompt "MODE APPROFONDISSEMENT" injecte
      4. Retourner le resultat (meme format que /raya/ask pour que le
         front rende la bulle Opus avec pastille doree et eventuellement
         bouton Etendre si garde-fou)
    """
    username = user["username"]
    tenant_id = user["tenant_id"]

    aria_memory_id = payload.get("aria_memory_id")
    if not isinstance(aria_memory_id, int):
        raise HTTPException(
            status_code=400,
            detail="aria_memory_id (int) requis",
        )

    # 1. Charger l echange original (question + reponse Sonnet)
    original = _load_original_exchange(aria_memory_id, username, tenant_id)
    if original is None:
        raise HTTPException(
            status_code=404,
            detail="Echange introuvable ou non accessible",
        )
    user_input, _aria_response = original

    # 2. Construire le payload de relecture
    replay_payload = _ReplayPayload(query=user_input)

    # 3. Appel de la vraie boucle agent avec deepen_mode=True
    #    Opus va avoir : regles RAG, historique 3 derniers echanges (avec
    #    reponse Sonnet comme dernier assistant), tools, graphe, etc.
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(
                _raya_core_agent,
                request, replay_payload, username, tenant_id,
                None,   # existing_continuation (pas une reprise P2/P3)
                True,   # deepen_mode=True
            )
            # Timeout 120s : Opus avec boucle agent + RAG + tools peut
            # legitimement prendre plus longtemps qu un tour Sonnet
            # standard. 120s laisse la marge sans bloquer a vie.
            result = future.result(timeout=120)
    except concurrent.futures.TimeoutError:
        return {
            "answer": (
                "\u26a0\ufe0f Opus a depasse le timeout serveur pour "
                "l approfondissement. La reponse Sonnet initiale reste "
                "valide. Retente si besoin avec une question plus ciblee."
            ),
            "actions": [], "pending_actions": [],
            "aria_memory_id": None, "model_tier": "deep",
            "ask_choice": None,
            "is_error": True, "error_type": "timeout",
        }
    except Exception:
        tb = traceback.format_exc()
        logger.error("[Deepen] ERREUR pour %s:\n%s", username, tb)
        return {
            "answer": (
                "\u26a0\ufe0f Une erreur interne est survenue lors de "
                "l approfondissement. La reponse Sonnet initiale reste valide."
            ),
            "actions": [], "pending_actions": [],
            "aria_memory_id": None, "model_tier": "deep",
            "ask_choice": None,
            "is_error": True, "error_type": "internal",
        }

    # 4. Enrichir la trace : ajouter source_memory_id pour que le front
    #    sache que c est un approfondissement d un echange precedent
    #    (utile pour d eventuelles evolutions UX futures).
    if isinstance(result, dict):
        result["source_memory_id"] = aria_memory_id

    logger.info(
        "[Deepen] OK user=%s source_id=%d new_id=%s iter=%d tokens=%d",
        username, aria_memory_id,
        result.get("aria_memory_id") if isinstance(result, dict) else None,
        result.get("agent_iterations", 0) if isinstance(result, dict) else 0,
        result.get("agent_tokens", 0) if isinstance(result, dict) else 0,
    )

    return result
