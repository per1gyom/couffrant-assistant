"""
Endpoint "Approfondir avec Opus" (V2.4).

Permet a l utilisateur de demander une version plus profonde d une
reponse qui a ete donnee par Sonnet 4.6 (tier smart). Declenche Opus
4.7 (tier deep) avec le CONTEXTE COMPLET de l echange precedent,
pas une nouvelle question isolee.

Logique :
  - L utilisateur pose une question -> Sonnet repond (tier smart)
  - Si la reponse est un peu juste, il clique "Approfondir avec Opus"
  - Opus recoit : question originale + reponse Sonnet
  - Opus produit une reponse qui CONSTRUIT dessus :
      - Complete les lacunes
      - Corrige les imprecisions
      - Explore des angles que Sonnet a rates
      - Nuance les conclusions si besoin

Avantages vs relancer from scratch :
  - Opus ne refait pas le travail de Sonnet
  - Moins cher (pas de nouveau retrieval, pas de tool calls redondants
    dans la majorite des cas)
  - Meilleure UX : Opus repart des memes donnees factuelles, se
    concentre sur la profondeur

Historique : la reponse Sonnet reste dans aria_memory. La reponse Opus
est sauvegardee dans une nouvelle ligne aria_memory. On garde les 2
pour comparer plus tard.
"""
from fastapi import APIRouter, Request, Body, Depends, HTTPException
from fastapi.responses import JSONResponse

from app.database import get_pg_conn
from app.logging_config import get_logger
from app.llm_client import llm_complete
from app.routes.deps import require_user
from app.routes.raya_helpers import _strip_action_tags

logger = get_logger("raya.deepen")


# ═══════════════════════════════════════════════════════════════════════
# LECTURE de la reponse source (Sonnet)
# ═══════════════════════════════════════════════════════════════════════

def _load_original_exchange(aria_memory_id: int, username: str, tenant_id: str):
    """
    Charge l echange source depuis aria_memory, avec verif ownership.
    Retourne (user_input, aria_response) ou None si pas trouve / pas a lui.
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
# PROMPT "deepen" - Opus construit sur la reponse Sonnet
# ═══════════════════════════════════════════════════════════════════════

_DEEPEN_SYSTEM_PROMPT = """Tu es Raya en mode "approfondissement".

L utilisateur vient de recevoir une reponse a sa question (notee ci-apres
"REPONSE INITIALE"). Cette reponse a ete produite par un modele rapide
(Sonnet 4.6). L utilisateur estime qu elle merite d etre approfondie et
demande une version plus complete, plus nuancee, avec plus d analyse.

Ta mission :
  1. Lis la question originale et la reponse initiale attentivement
  2. Identifie ce qui manque : profondeur d analyse, contextes ignores,
     nuances eludees, chiffres sans interpretation, recommendations
     absentes, angles morts
  3. Produis une reponse qui CONSTRUIT sur la reponse initiale :
     - Ne refais pas tout le travail depuis zero
     - Prends la reponse initiale comme socle factuel
     - Ajoute ce qui manque : analyses croisees, implications,
       recommandations pratiques, points d attention subtils
     - Corrige si tu detectes une erreur ou approximation
     - Nuance les conclusions trop tranchees si besoin

Important :
  - Commence directement par ta reponse approfondie (pas d introduction
    "Voici ma version approfondie...", tu rentres dans le vif du sujet)
  - Structure ta reponse pour qu elle soit lisible (titres, puces,
    tableaux si pertinent, mais sans en abuser)
  - Si apres reflexion la reponse initiale etait deja tres bonne, dis-le
    honnetement et apporte juste les 1-2 nuances qui manquaient plutot
    que d inventer du contenu pour faire volume

Style : ton direct et professionnel, comme d habitude. Pas de flatterie,
pas de "excellente question", on va a l essentiel.
"""


def _build_deepen_messages(user_input: str, aria_response: str) -> list:
    """
    Construit les messages pour Opus : 1 seul tour user qui contient
    la question originale + la reponse initiale a approfondir.
    """
    content = (
        f"QUESTION ORIGINALE :\n{user_input}\n\n"
        f"REPONSE INITIALE (Sonnet 4.6) :\n{aria_response}\n\n"
        f"Approfondis cette reponse."
    )
    return [{"role": "user", "content": content}]


# ═══════════════════════════════════════════════════════════════════════
# SAUVEGARDE de la nouvelle reponse Opus dans aria_memory
# ═══════════════════════════════════════════════════════════════════════

def _save_deepen_response(username: str, tenant_id: str,
                           original_id: int,
                           user_input: str, aria_response: str) -> int | None:
    """
    Sauvegarde la reponse approfondie dans aria_memory.
    La question est prefixee pour marquer qu il s agit d un
    approfondissement d une reponse precedente (tracabilite).
    """
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        # user_input avec prefixe trace : on garde la question originale
        # mais on marque que c est un approfondissement pour ne pas polluer
        # l historique normal avec des doublons
        marked_input = f"[Approfondissement de #{original_id}] {user_input}"
        c.execute(
            "INSERT INTO aria_memory (username, tenant_id, user_input, aria_response) "
            "VALUES (%s, %s, %s, %s) RETURNING id",
            (username, tenant_id, marked_input, aria_response),
        )
        row = c.fetchone()
        conn.commit()
        return row[0] if row else None
    except Exception as e:
        if conn:
            conn.rollback()
        logger.exception("[Deepen] save_response error: %s", e)
        return None
    finally:
        if conn:
            conn.close()


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

    Retour : memes champs que /raya, avec la nouvelle reponse Opus
    et model_tier="deep" pour que le front affiche la pastille Opus.
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
    user_input, aria_response = original

    # 2. Construire les messages pour Opus
    messages = _build_deepen_messages(user_input, aria_response)

    # 3. Appel Opus avec le prompt deepen
    try:
        result = llm_complete(
            messages=messages,
            system=_DEEPEN_SYSTEM_PROMPT,
            model_tier="deep",  # Opus 4.7 force
            max_tokens=8192,  # Reponse potentiellement longue (analyse profonde)
        )
    except Exception as e:
        logger.exception("[Deepen] appel LLM echoue: %s", e)
        return JSONResponse(
            status_code=500,
            content={
                "answer": (
                    "\u26a0\ufe0f Une erreur technique est survenue pendant "
                    "l approfondissement. La reponse initiale reste valide, "
                    "retente dans quelques secondes."
                ),
                "is_error": True,
                "error_type": "llm_error",
            },
        )

    deepened_text = result.get("text", "").strip()
    if not deepened_text:
        return JSONResponse(
            status_code=500,
            content={
                "answer": "\u26a0\ufe0f Opus n a pas produit de reponse. Retente.",
                "is_error": True,
                "error_type": "empty_response",
            },
        )

    # 4. Sauvegarder la reponse approfondie dans aria_memory
    cleaned = _strip_action_tags(deepened_text)
    new_memory_id = _save_deepen_response(
        username=username,
        tenant_id=tenant_id,
        original_id=aria_memory_id,
        user_input=user_input,
        aria_response=cleaned,
    )

    logger.info(
        "[Deepen] OK user=%s original=%d new=%s tokens_in=%d tokens_out=%d",
        username, aria_memory_id, new_memory_id,
        result.get("usage", {}).get("input_tokens", 0),
        result.get("usage", {}).get("output_tokens", 0),
    )

    # 5. Retour au format /raya pour compatibilite front
    return {
        "answer": cleaned,
        "actions": [],
        "pending_actions": [],
        "aria_memory_id": new_memory_id,
        "model_tier": "deep",  # Opus -> pastille doree front
        "ask_choice": None,
        "is_error": False,
        # Metadatas pour continuation eventuelle
        "agent_iterations": 1,  # deepen = 1 appel LLM pas de boucle
        "agent_duration_s": None,
        "agent_tokens": (
            result.get("usage", {}).get("input_tokens", 0)
            + result.get("usage", {}).get("output_tokens", 0)
        ),
        "agent_stopped_by": None,
        "continuation_id": None,
        "source_memory_id": aria_memory_id,  # trace de la reponse Sonnet source
    }
