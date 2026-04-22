"""
Continuation P2/P3 de la boucle agent Raya v2.

Permet a l utilisateur d etendre la reflexion de Raya quand un garde-fou
(P1 = 150k tokens) est atteint, sans redemarrer la recherche depuis zero.

Architecture :
  - Quand un garde-fou saute, on sauvegarde l etat complet dans
    agent_continuations (messages, system_prompt, tokens, iterations).
  - Le front affiche un bouton 'Etendre' avec le continuation_id.
  - Au clic, POST /raya/agent/continue reprend exactement la ou on s est
    arrete avec un budget elargi (paliers P2 puis P3+ repetable).

Paliers :
  P1 (defaut) : 150k tokens / 15 iter / 60s
  P2 (1er +) : +150k / +10 iter / +90s -> total 300k / 25 iter / 150s
  P3+ (++)    : +200k / +15 iter / +90s chaque clic, repetable infini
                L utilisateur decide de s arreter (il voit le compteur).

Avertissement unique au passage des 500k cumules (3e extension) :
  Avant d executer, Raya ajoute dans sa prochaine reponse un message
  type 'prends 10 secondes pour reformuler ou preciser, une question
  mieux cadree trouve mieux en 50k que 500k de recherche floue'.
"""
from typing import Optional
import json
import time

from app.database import get_pg_conn
from app.logging_config import get_logger

logger = get_logger("raya.continuation")

# Budgets par palier (deltas et valeurs absolues)
P1_TOKENS = 150_000
P1_ITERATIONS = 15
P1_DURATION = 60

P2_DELTA_TOKENS = 150_000
P2_DELTA_ITERATIONS = 10
P2_DELTA_DURATION = 90

P3_DELTA_TOKENS = 200_000
P3_DELTA_ITERATIONS = 15
P3_DELTA_DURATION = 90


# ═══════════════════════════════════════════════════════════════════════
# SERIALISATION / DESERIALISATION des messages Anthropic
# ═══════════════════════════════════════════════════════════════════════

def _block_to_dict(block) -> dict:
    """
    Convertit un content_block Anthropic (objet SDK) en dict JSON-serializable.

    Les blocks peuvent etre de type : text, tool_use, tool_result.
    Cette fonction est defensive : si le block est deja un dict (messages
    user avec contenu text simple), on le retourne tel quel.
    """
    if isinstance(block, dict):
        return block
    btype = getattr(block, "type", None)
    if btype == "text":
        return {"type": "text", "text": getattr(block, "text", "")}
    if btype == "tool_use":
        return {
            "type": "tool_use",
            "id": getattr(block, "id", ""),
            "name": getattr(block, "name", ""),
            "input": getattr(block, "input", {}),
        }
    if btype == "tool_result":
        return {
            "type": "tool_result",
            "tool_use_id": getattr(block, "tool_use_id", ""),
            "content": getattr(block, "content", ""),
            "is_error": getattr(block, "is_error", False),
        }
    # Fallback : on essaie dict() sinon str()
    try:
        return dict(block)
    except Exception:
        return {"type": "text", "text": str(block)}


def serialize_messages(messages: list) -> list:
    """
    Serialize toute la liste messages pour stockage JSONB.
    Chaque message a role + content (qui peut etre str ou list de blocks).
    """
    out = []
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content")
        if isinstance(content, str):
            out.append({"role": role, "content": content})
        elif isinstance(content, list):
            out.append({"role": role, "content": [_block_to_dict(b) for b in content]})
        else:
            out.append({"role": role, "content": _block_to_dict(content)})
    return out


def deserialize_messages(stored: list) -> list:
    """
    Relit les messages depuis JSONB. Anthropic SDK accepte directement
    les dicts en entree (pas besoin de reconstruire des objets), donc
    c est quasiment un passthrough.
    """
    return stored or []


# ═══════════════════════════════════════════════════════════════════════
# SAUVEGARDE de l etat quand un garde-fou saute
# ═══════════════════════════════════════════════════════════════════════

def save_continuation(
    username: str,
    tenant_id: str,
    query: str,
    system_prompt: str,
    messages: list,
    tokens_used: int,
    iterations_used: int,
    duration_seconds: float,
    stopped_by: str,
    previous_continuation_id: Optional[int] = None,
    previous_extension_count: int = 0,
    previous_palier: str = "P1",
) -> Optional[int]:
    """
    Sauvegarde l etat de la boucle agent pour reprise future.

    Retourne l id de la continuation cree, ou None si echec
    (degradation gracieuse : on renvoie la reponse normale au user
    sans bouton 'Etendre').

    Si previous_continuation_id est set, c est une extension d une
    continuation existante -> on incremente extension_count et on
    calcule le nouveau palier.
    """
    # Calcul du nouveau palier et de l extension_count
    if previous_continuation_id is None:
        # 1ere sauvegarde : on etait en P1, prochaine = P2
        new_extension_count = 0
        new_palier = "P1"  # palier actuel, celui qui vient de s arreter
    else:
        new_extension_count = previous_extension_count + 1
        if new_extension_count == 1:
            new_palier = "P2"
        else:
            new_palier = "P3"

    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute(
            """
            INSERT INTO agent_continuations
              (username, tenant_id, query, system_prompt, messages,
               tokens_used, iterations_used, duration_seconds,
               extension_count, palier, stopped_by,
               expires_at)
            VALUES (%s, %s, %s, %s, %s::jsonb,
                    %s, %s, %s,
                    %s, %s, %s,
                    NOW() + INTERVAL '1 hour')
            RETURNING id
            """,
            (
                username, tenant_id, query, system_prompt,
                json.dumps(serialize_messages(messages)),
                tokens_used, iterations_used, duration_seconds,
                new_extension_count, new_palier, stopped_by,
            ),
        )
        continuation_id = c.fetchone()[0]

        # Si c est une extension, on marque l ancienne comme consumed
        if previous_continuation_id is not None:
            c.execute(
                "UPDATE agent_continuations SET consumed = true, updated_at = NOW() "
                "WHERE id = %s",
                (previous_continuation_id,),
            )

        conn.commit()
        logger.info(
            "[Continuation] sauvegarde id=%d palier=%s ext=%d tokens=%d",
            continuation_id, new_palier, new_extension_count, tokens_used,
        )
        return continuation_id
    except Exception as e:
        if conn:
            conn.rollback()
        logger.exception("[Continuation] echec sauvegarde: %s", e)
        return None
    finally:
        if conn:
            conn.close()


# ═══════════════════════════════════════════════════════════════════════
# LECTURE d une continuation
# ═══════════════════════════════════════════════════════════════════════

def load_continuation(continuation_id: int, username: str, tenant_id: str) -> Optional[dict]:
    """
    Charge une continuation pour reprise. Verifie :
      - Qu elle existe
      - Qu elle appartient bien a cet utilisateur (securite)
      - Qu elle n est pas expiree (>1h)
      - Qu elle n a pas deja ete consommee
    """
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute(
            """
            SELECT id, username, tenant_id, query, system_prompt, messages,
                   tokens_used, iterations_used, duration_seconds,
                   extension_count, palier, stopped_by,
                   created_at, expires_at, consumed
            FROM agent_continuations
            WHERE id = %s
              AND username = %s
              AND tenant_id = %s
              AND consumed = false
              AND expires_at > NOW()
            """,
            (continuation_id, username, tenant_id),
        )
        row = c.fetchone()
        if not row:
            return None
        return {
            "id": row[0],
            "username": row[1],
            "tenant_id": row[2],
            "query": row[3],
            "system_prompt": row[4],
            "messages": deserialize_messages(row[5]),
            "tokens_used": row[6],
            "iterations_used": row[7],
            "duration_seconds": float(row[8] or 0),
            "extension_count": row[9],
            "palier": row[10],
            "stopped_by": row[11],
            "created_at": row[12],
            "expires_at": row[13],
            "consumed": row[14],
        }
    except Exception as e:
        logger.exception("[Continuation] echec load id=%s: %s", continuation_id, e)
        return None
    finally:
        if conn:
            conn.close()


# ═══════════════════════════════════════════════════════════════════════
# CALCUL DES BUDGETS selon le palier demande
# ═══════════════════════════════════════════════════════════════════════

def compute_extended_budgets(previous_tokens_used: int,
                              previous_iterations_used: int,
                              previous_duration_seconds: float,
                              next_extension_count: int) -> dict:
    """
    Retourne les nouveaux plafonds absolus pour la boucle etendue.

    previous_* : ce qui a deja ete consomme dans les tours precedents
    next_extension_count : combien d extensions deja faites + 1
                           (1 = on passe en P2, 2+ = P3 successifs)

    Exemple :
      Tour 1 (P1) : tokens=150k, iter=15, dur=60s (garde-fou tokens)
      Clic etendre :
        next_extension_count=1 -> P2
        nouveau budget tokens = 150k + 150k (delta P2) = 300k
        nouvelle budget iter = 15 + 10 = 25
        nouvelle duree = 60 + 90 = 150s
    """
    if next_extension_count == 1:
        delta_tokens = P2_DELTA_TOKENS
        delta_iter = P2_DELTA_ITERATIONS
        delta_dur = P2_DELTA_DURATION
        palier = "P2"
    else:
        delta_tokens = P3_DELTA_TOKENS
        delta_iter = P3_DELTA_ITERATIONS
        delta_dur = P3_DELTA_DURATION
        palier = "P3"

    # Avertissement "reformule plutot que creuser a l aveugle" declenche
    # DES QU ON ENTRE EN P3 (2e extension, soit ~300k cumules qui vont
    # devenir 500k). Logique : si P1 + P2 n ont pas suffi, c est le bon
    # moment pour Raya de faire une pause introspective et de poser une
    # question complementaire a l utilisateur plutot que de creuser sans
    # fin. Pas au-dela car l utilisateur a deja vu l avertissement.
    return {
        "max_tokens": previous_tokens_used + delta_tokens,
        "max_iterations": previous_iterations_used + delta_iter,
        "max_duration": previous_duration_seconds + delta_dur,
        "palier": palier,
        "delta_tokens": delta_tokens,
        "show_warning": next_extension_count == 2,  # entree en P3 uniquement
    }


# ═══════════════════════════════════════════════════════════════════════
# MESSAGE DE SELF-REFLECTION injecte au debut de chaque extension
# ═══════════════════════════════════════════════════════════════════════

def build_reflection_prompt(extension_count: int, show_warning: bool) -> str:
    """
    Genere le message injecte au debut de l extension, selon le contexte.

    extension_count : 1 = P2 (1ere extension), 2+ = P3 successives
    show_warning : True au moment du passage en P3 (2e extension)

    Principe :
      - En P2 : petit rappel pour prendre du recul
      - En P3+ : idem + encourage Raya a poser une question si elle peine
      - show_warning (actif uniquement a l entree en P3) : ajoute un
        recadrage plus ferme pour eviter le creusage a l aveugle
    """
    parts = []

    if show_warning:
        parts.append(
            "RECADRAGE IMPORTANT : l utilisateur a deja fait 2 tours "
            "d extension sans que tu aies trouve de reponse claire a sa "
            "question. C est le signal qu il ne faut PAS simplement "
            "continuer a creuser dans la meme direction. Fais l une de "
            "ces 2 choses : "
            "(1) pose une question complementaire a l utilisateur pour "
            "reformuler ou preciser son besoin (par exemple : 'J ai "
            "explore X et Y sans trouver Z, peux-tu preciser [element] "
            "ou reformuler ta question sous un autre angle ?'), "
            "OU (2) explique clairement ce que tu as deja trouve et ce "
            "qui te manque, en etant honnete sur les limites. Une "
            "question mieux cadree trouve en peu de temps ce qu une "
            "recherche floue ne trouvera jamais."
        )

    if extension_count == 1:
        parts.append(
            "L utilisateur t a demande d etendre ta reflexion (extension n°1). "
            "Tu as plus de budget maintenant. Avant de repartir, prends une "
            "respiration mentale : ou en es-tu vraiment, qu est-ce qui te "
            "manque concretement, quelle nouvelle piste semble la plus "
            "prometteuse ? Evite de creuser dans la meme direction si "
            "c etait un cul-de-sac."
        )
    else:
        parts.append(
            "L utilisateur t a demande d etendre encore ta reflexion "
            "(extension n°{n}). Prends du recul : si tu peines a trouver "
            "une reponse claire, pose une question complementaire a "
            "l utilisateur plutot que de continuer a chercher. Il vaut "
            "mieux demander une precision que tourner en rond.".format(n=extension_count)
        )

    return "\n\n".join(parts)
