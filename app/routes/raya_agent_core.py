"""
Coeur de Raya en mode agent (v2).

Cette fonction remplace _raya_core (v1 single-shot) quand la variable
d environnement RAYA_AGENT_MODE vaut "true".

Architecture :
  - Utilise l API Anthropic tool use native
  - Boucle while stop_reason != "end_turn"
  - Chaque iteration : appel API → tool_use → execution → tool_result
  - Garde-fous : 10 iterations, 30s timeout, 30k tokens de budget
"""
import os
import time
import json
from fastapi import Request

from app.logging_config import get_logger
from app.database import get_pg_conn
from app.llm_client import llm_complete, log_llm_usage
from app.rule_engine import get_memoire_param
from app.feedback_store import get_global_instructions
from app.routes.raya_tools import get_tools_for_user
from app.routes.raya_tool_executors import execute_tool
from app.routes.raya_helpers import _strip_action_tags, _build_user_content

logger = get_logger("raya.agent")

# ==========================================================================
# GARDE-FOUS DE LA BOUCLE — Architecture 3 paliers v2.1 (22/04)
# ==========================================================================
# Palier 1 (Standard) : par defaut. Couvre 99% des questions.
# Palier 2 (Etendu)   : clic utilisateur 'Etendre' apres P1 atteint.
# Palier 3 (Profond)  : clic utilisateur 'Etendre encore' apres P2 atteint.
#
# Actuellement seul P1 est actif. Les paliers P2/P3 necessitent la table
# agent_continuations + front bouton 'Etendre' (chantier suivant).
# En attendant, le P1 ci-dessous remplace l ancien budget unique.
BUDGET_P1_STANDARD = 150_000
BUDGET_P2_EXTENDED = 300_000
BUDGET_P3_DEEP     = 500_000

ITER_P1 = 15
ITER_P2 = 25
ITER_P3 = 40

DUR_P1 = 60   # 1 minute
DUR_P2 = 150  # 2m30
DUR_P3 = 300  # 5 minutes

# Constantes effectives utilisees dans la boucle (palier 1 par defaut).
# Quand la continuation sera implementee, ces constantes deviendront
# dynamiques selon le palier demande.
MAX_ITERATIONS = ITER_P1
MAX_DURATION_SECONDS = DUR_P1
MAX_TOKENS_BUDGET = BUDGET_P1_STANDARD


def _build_agent_system_prompt(
    username: str,
    tenant_id: str,
    display_name: str = "Guillaume",
) -> str:
    """
    Prompt systeme court de la v2. Remplace les ~15-20k chars de la v1
    par ~800 chars bien cibles.

    Les descriptions des tools sont injectees automatiquement par l API
    Anthropic (parametre tools=). Pas besoin de les redecrire ici.

    Les preferences durables (aria_rules) sont ajoutees a ce prompt par
    _load_user_preferences() ci-dessous.
    """
    return f"""Tu es Raya, IA de {display_name} chez Couffrant Solar (photovoltaique, Romorantin-Lanthenay).
Tu parles au feminin, tutoiement.

Tu as acces a l ensemble des donnees de l entreprise via tes outils :
Odoo (clients, devis, factures), SharePoint, mails analyses, graphe
semantique des relations, historique des conversations, web.

Regles non negociables :
1. Tout fait cite (nom, date, montant, reference) doit provenir d un
   resultat d outil de cette conversation. Tu ne devines jamais.
2. Si tu rencontres un terme que tu ne maitrises pas (entreprise,
   technologie, personne), tu cherches spontanement avant de repondre.
3. Si tu as un doute, tu cherches a lever ce doute (plusieurs outils
   si besoin) avant de repondre.
4. Clarte avant volume. Pas d invention pour faire serieux. Si tu as
   3 infos, tu donnes 3 infos.
5. Si apres 2 tentatives avec des outils differents tu ne trouves
   toujours pas une donnee precise, ne persiste pas. Conclus que la
   donnee n est pas accessible, explique ce qui manque (quelle source,
   quelle API, quelle permission) et donne ce que tu as deja assemble.
   Exemple : "Je n arrive pas a obtenir les montants detailles des
   devis car sale.order.line n est pas expose par l API Odoo. Il
   faudrait demander a OpenFire d ouvrir ce modele. Voici neanmoins
   ce que je peux te dire : [contexte disponible]."
6. Mails : la signature de l utilisateur est ajoutee automatiquement
   a l envoi par le systeme. Ne mets PAS de signature dans le corps
   du mail (pas de "Cordialement, Guillaume", pas de bloc de contact).
   Termine simplement le corps, le systeme s occupe du reste.
7. Pour tout schema visuel (organigramme, flux, hierarchie, timeline,
   montage juridique, arbre de decision), utilise un bloc ```mermaid :
   le frontend le rend en SVG propre. Ne fais JAMAIS de schema en
   caracteres ASCII (boites avec + - | et fleches ->). Exemple :
   ```mermaid
   graph TD
     A[SARL Des Moines] -->|loue le toit| B[SCI Arrault Legroux]
     A -->|siege| C[43 rue des Moines]
     B -->|batiment| D[79 rue des Deportes]
   ```
"""


def _load_user_preferences(username: str, tenant_id: str) -> str:
    """Charge les preferences durables (niveau 3 de la memoire)."""
    conn = get_pg_conn()
    try:
        c = conn.cursor()
        c.execute(
            "SELECT category, rule_text FROM aria_rules "
            "WHERE username = %s AND active = true "
            "ORDER BY category, id LIMIT 50",
            (username,),
        )
        rules = c.fetchall()
        if not rules:
            return ""
        by_cat = {}
        for cat, rule in rules:
            by_cat.setdefault(cat, []).append(rule)
        lines = ["\n=== PREFERENCES APPRISES DE L UTILISATEUR ==="]
        for cat, items in by_cat.items():
            lines.append(f"\n[{cat}]")
            for r in items:
                lines.append(f"  - {r}")
        return "\n".join(lines)
    except Exception as e:
        logger.warning("[Agent] load_user_preferences error: %s", e)
        return ""
    finally:
        conn.close()


def _load_recent_history(username: str, limit: int = 3) -> list[dict]:
    """
    Charge les `limit` derniers echanges (niveau 1 de la memoire : in-prompt).

    Evolution v2.1 (22/04) : passe de 10 a 3 echanges + troncature des
    reponses longues a 3000 chars. Avec l historique de 10 echanges
    integralement charges, le prompt saturait a 40-50k tokens avant
    meme que Raya commence a travailler, explosant le budget tokens
    sur les questions complexes.

    Desormais :
      - 3 echanges maximum (contexte immediat)
      - user_input tronque a 2000 chars (souvent les requetes courtes)
      - aria_response tronquee a 3000 chars (responses tableaux limitees)
      - Au-dela de 3 echanges : accessible via search_conversations
        qui interroge le graphe semantique (niveau 2)
    """
    MAX_USER_LEN = 2000
    MAX_ASSISTANT_LEN = 3000

    conn = get_pg_conn()
    try:
        c = conn.cursor()
        c.execute(
            "SELECT user_input, aria_response FROM aria_memory "
            "WHERE username = %s AND archived = false "
            "ORDER BY id DESC LIMIT %s",
            (username, limit),
        )
        rows = list(reversed(c.fetchall()))

        history = []
        for user_text, assistant_text in rows:
            if not user_text or not assistant_text:
                continue

            # Troncature avec indication
            if len(user_text) > MAX_USER_LEN:
                user_text = user_text[:MAX_USER_LEN] + " ...(tronque)"
            if len(assistant_text) > MAX_ASSISTANT_LEN:
                assistant_text = assistant_text[:MAX_ASSISTANT_LEN] + \
                                 " ...(tronque, voir historique complet si besoin)"

            history.append({
                "user": user_text,
                "assistant": assistant_text,
            })

        return history
    finally:
        conn.close()


def _build_messages(
    user_query: str,
    history: list[dict],
    user_content_parts: list | str,
) -> list[dict]:
    """Construit la liste messages pour l API Anthropic."""
    messages = []
    for h in history:
        messages.append({"role": "user", "content": h["user"]})
        messages.append({"role": "assistant", "content": h["assistant"]})
    # Message courant
    messages.append({"role": "user", "content": user_content_parts})
    return messages


def _call_anthropic_with_tools(
    messages: list[dict],
    system: str,
    tools: list[dict],
    model_tier: str = "deep",
    max_tokens: int = 4096,
) -> dict:
    """
    Appel API Anthropic avec support tool use.

    Retourne un dict avec :
      - stop_reason : "end_turn", "tool_use", "max_tokens", ...
      - content     : liste de blocs (text, tool_use, ...)
      - usage       : dict input_tokens, output_tokens, cache_*
    """
    # llm_complete est notre wrapper existant. On etend avec tools.
    # En v2 on utilise Opus 4.7 par defaut (model_tier="deep").
    # cache_system=True : active le prompt caching Anthropic. Le prompt
    # systeme (identique a chaque tour) est mis en cache pour 5 minutes.
    # Gain : ~90% d economie sur les tokens system aux tours 2+.
    result = llm_complete(
        messages=messages,
        system=system,
        tools=tools,
        model_tier=model_tier,
        max_tokens=max_tokens,
        cache_system=True,
    )
    return result


def _extract_text_content(content_blocks: list) -> str:
    """Extrait le texte final d une reponse agent."""
    parts = []
    for block in content_blocks:
        if isinstance(block, dict):
            if block.get("type") == "text":
                parts.append(block.get("text", ""))
        elif hasattr(block, "type") and block.type == "text":
            parts.append(block.text)
    return "\n".join(parts).strip()


def _extract_tool_uses(content_blocks: list) -> list[dict]:
    """Extrait les appels d outils d une reponse agent."""
    tool_uses = []
    for block in content_blocks:
        if isinstance(block, dict):
            if block.get("type") == "tool_use":
                tool_uses.append({
                    "id": block.get("id"),
                    "name": block.get("name"),
                    "input": block.get("input", {}),
                })
        elif hasattr(block, "type") and block.type == "tool_use":
            tool_uses.append({
                "id": block.id,
                "name": block.name,
                "input": block.input,
            })
    return tool_uses


def _raya_core_agent(
    request: Request,
    payload,
    username: str,
    tenant_id: str,
) -> dict:
    """
    Boucle agent Raya v2. Remplacement de _raya_core quand
    RAYA_AGENT_MODE=true.

    Principe :
      1. Prepare prompt systeme court + preferences
      2. Charge historique 10 derniers echanges
      3. Construit messages[]
      4. Boucle :
         - appel API avec tools
         - si tool_use : execute tool, ajoute resultat a messages, continue
         - si end_turn : extrait texte, sauvegarde, retourne
         - si garde-fou depasse : resume partiel + demande de poursuite
    """
    start_time = time.time()

    # 1. Prompt systeme
    display_name = username.capitalize()
    base_system = _build_agent_system_prompt(username, tenant_id, display_name)
    preferences = _load_user_preferences(username, tenant_id)
    system = base_system + preferences

    # Consignes globales (tenant-wide)
    global_instructions = get_global_instructions(tenant_id=tenant_id)
    if global_instructions:
        system += "\n\n=== CONSIGNES GLOBALES ===\n"
        for instr in global_instructions:
            system += f"- {instr}\n"

    # 2. Historique (10 derniers echanges)
    # 2. Historique (3 derniers echanges + troncature, voir _load_recent_history)
    # Au-dela, Raya utilise search_conversations qui interroge le graphe.
    history = _load_recent_history(username, limit=3)

    # 3. Messages initiaux
    user_content_parts = _build_user_content(payload)
    messages = _build_messages(payload.query or "", history, user_content_parts)

    # 4. Tools disponibles pour cet utilisateur
    tools = get_tools_for_user(username, tenant_id)

    # 5. Boucle agent
    iterations = 0
    total_input_tokens = 0
    total_output_tokens = 0
    final_text = ""
    stopped_by_guard = None  # si garde-fou depasse

    # Tracking des tool calls pour detection de boucle :
    # {(tool_name, params_hash): nb_appels}
    # Si un meme tool est appele avec des params tres proches 3+ fois,
    # on injecte un avertissement dans le tool_result pour aider Raya
    # a conclure plutot que de boucler.
    tool_call_counts: dict[tuple[str, str], int] = {}


    while iterations < MAX_ITERATIONS:
        iterations += 1
        elapsed = time.time() - start_time

        # Check garde-fous avant appel
        if elapsed > MAX_DURATION_SECONDS:
            stopped_by_guard = "timeout"
            break
        if total_input_tokens + total_output_tokens > MAX_TOKENS_BUDGET:
            stopped_by_guard = "tokens"
            break

        logger.info(
            "[Agent] iteration=%d elapsed=%.1fs tokens=%d/%d",
            iterations, elapsed,
            total_input_tokens + total_output_tokens, MAX_TOKENS_BUDGET,
        )

        # Appel Anthropic avec tools
        try:
            response = _call_anthropic_with_tools(
                messages=messages,
                system=system,
                tools=tools,
                model_tier="deep",  # Opus 4.7 par defaut en phase test
                max_tokens=4096,
            )
        except Exception as e:
            logger.exception("[Agent] appel API echoue iteration=%d", iterations)
            final_text = f"Desole, une erreur technique est survenue : {type(e).__name__}. Je n ai pas pu terminer ma reflexion."
            break

        # Accumuler les tokens
        usage = response.get("usage", {})
        total_input_tokens += usage.get("input_tokens", 0)
        total_output_tokens += usage.get("output_tokens", 0)

        content_blocks = response.get("content", [])
        stop_reason = response.get("stop_reason", "end_turn")
        tool_uses = _extract_tool_uses(content_blocks)
        text_part = _extract_text_content(content_blocks)


        # Si Claude a appele des tools, les executer et relancer
        if stop_reason == "tool_use" and tool_uses:
            logger.info(
                "[Agent] iter %d : %d tool_use demandes : %s",
                iterations, len(tool_uses),
                [t["name"] for t in tool_uses],
            )

            # On doit d abord ajouter le message assistant (avec tool_use)
            messages.append({
                "role": "assistant",
                "content": content_blocks,
            })

            # Executer chaque tool et ajouter les resultats
            tool_results_content = []
            for tu in tool_uses:
                # Detection de boucle : hash des parametres pour cle unique
                import hashlib
                import json as _json
                params_str = _json.dumps(tu["input"], sort_keys=True)
                params_hash = hashlib.md5(params_str.encode()).hexdigest()[:8]
                call_key = (tu["name"], params_hash)
                tool_call_counts[call_key] = tool_call_counts.get(call_key, 0) + 1
                call_count = tool_call_counts[call_key]

                # Compter aussi le nombre total d appels au meme tool
                # (params differents mais meme outil)
                same_tool_count = sum(
                    n for (tname, _), n in tool_call_counts.items()
                    if tname == tu["name"]
                )

                result_str = execute_tool(
                    tool_name=tu["name"],
                    tool_input=tu["input"],
                    username=username,
                    tenant_id=tenant_id,
                    conversation_id=None,  # pas encore cree
                )

                # Injection d avertissement si boucle detectee
                warning = ""
                if call_count >= 2:
                    warning = (
                        "\n\n[SYSTEME] Tu as deja appele ce tool avec des "
                        "parametres identiques. Si tu n as pas trouve, c est "
                        "probablement que cette donnee n est pas accessible. "
                        "Conclus avec ce que tu as et signale la limite."
                    )
                elif same_tool_count >= 4:
                    warning = (
                        f"\n\n[SYSTEME] Tu as appele {tu['name']} "
                        f"{same_tool_count} fois avec des parametres differents. "
                        "Pense a utiliser un autre tool ou a conclure avec ce "
                        "que tu as deja trouve."
                    )

                if warning:
                    logger.info(
                        "[Agent] iter %d : avertissement boucle sur %s",
                        iterations, tu["name"],
                    )
                    result_str = result_str + warning

                tool_results_content.append({
                    "type": "tool_result",
                    "tool_use_id": tu["id"],
                    "content": result_str,
                })

            messages.append({
                "role": "user",
                "content": tool_results_content,
            })

            # Continue la boucle
            continue

        # Sinon, c est la fin (end_turn, max_tokens, stop_sequence)
        final_text = text_part
        logger.info(
            "[Agent] fin normale iter=%d stop=%s tokens=%d texte_len=%d",
            iterations, stop_reason,
            total_input_tokens + total_output_tokens, len(final_text),
        )
        break
    else:
        # La boucle while s est terminee naturellement = MAX_ITERATIONS atteint
        stopped_by_guard = "iterations"


    # Gestion garde-fou depasse
    if stopped_by_guard:
        guard_msg = {
            "iterations": f"J ai atteint ma limite d exploration ({MAX_ITERATIONS} etapes).",
            "timeout": f"J ai atteint ma limite de temps ({MAX_DURATION_SECONDS}s).",
            "tokens": f"J ai atteint ma limite de reflexion ({MAX_TOKENS_BUDGET} tokens).",
        }[stopped_by_guard]

        # Si Claude a produit du texte partiel avant de boucler, on le garde
        partial = final_text.strip()
        if partial:
            final_text = (
                f"{partial}\n\n"
                f"{guard_msg} Voici ce que j ai trouve jusqu ici. "
                f"Tu veux que je continue ?"
            )
        else:
            final_text = (
                f"{guard_msg} Je n ai pas encore de reponse complete. "
                f"Tu peux preciser ta question ou me dire de continuer "
                f"l exploration ?"
            )

        logger.warning(
            "[Agent] stop garde-fou=%s iter=%d elapsed=%.1fs tokens=%d",
            stopped_by_guard, iterations,
            time.time() - start_time,
            total_input_tokens + total_output_tokens,
        )

    # Sauvegarde dans aria_memory
    aria_memory_id = _save_conversation(
        username=username,
        user_input=payload.query or "",
        aria_response=_strip_action_tags(final_text),
    )

    # Log usage total
    log_llm_usage(
        {"usage": {
            "input_tokens": total_input_tokens,
            "output_tokens": total_output_tokens,
        }},
        username=username,
        tenant_id=tenant_id,
        purpose=f"agent_loop_iter{iterations}",
    )


    # Retour au format attendu par le front (compatible v1)
    from app.pending_actions import get_pending
    updated_pending = get_pending(username=username, tenant_id=tenant_id, limit=10)

    return {
        "answer": final_text,
        "actions": [],  # les actions v2 passent par pending_actions direct
        "pending_actions": updated_pending,
        "aria_memory_id": aria_memory_id,
        "model_tier": "deep",
        "ask_choice": None,
        "is_error": False,
        # Metadonnees debug v2
        "agent_iterations": iterations,
        "agent_duration_s": round(time.time() - start_time, 2),
        "agent_tokens": total_input_tokens + total_output_tokens,
        "agent_stopped_by": stopped_by_guard,
    }


def _save_conversation(username: str, user_input: str, aria_response: str) -> int | None:
    """Persiste l echange dans aria_memory. Retourne l ID cree."""
    conn = get_pg_conn()
    try:
        c = conn.cursor()
        c.execute(
            "INSERT INTO aria_memory (username, user_input, aria_response) "
            "VALUES (%s, %s, %s) RETURNING id",
            (username, user_input, aria_response),
        )
        row = c.fetchone()
        conn.commit()
        return row[0] if row else None
    except Exception as e:
        logger.exception("[Agent] save_conversation error: %s", e)
        return None
    finally:
        conn.close()
