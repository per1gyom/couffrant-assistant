"""
Moteur de questions conversationnelles pour l'elicitation Raya.
Extrait de elicitation.py -- SPLIT-5.
"""
import json
import re
from app.llm_client import llm_complete

MAX_TURNS_DEFAULT = 8
LLM_TIER_QUESTIONS = "smart"


def _build_prompt(objective, topics, context, history, turn_count, max_turns):
    covered = [h["topic"] for h in history if h.get("role") == "assistant" and h.get("topic")]
    remaining = [t for t in topics if t not in covered]

    history_text = ""
    for entry in history:
        if entry.get("role") == "assistant":
            q = entry.get("question", "")
            opts = entry.get("options", [])
            topic = entry.get("topic", "")
            if opts:
                history_text += f"\nRaya [{topic}]: {q} [Choix: {', '.join(opts)}]"
            else:
                history_text += f"\nRaya [{topic}]: {q}"
        elif entry.get("role") == "user":
            history_text += f"\nUtilisateur: {entry.get('answer', '')}"

    context_block = ""
    if context:
        lines = [f"  - {k}: {v}" for k, v in context.items() if v]
        if lines:
            context_block = "\nCONTEXTE DEJA CONNU (ne pas redemander) :\n" + "\n".join(lines)

    force_done_str = "true" if (turn_count >= max_turns - 1) else "false"
    turns_left = max_turns - turn_count

    return f"""Tu menes une conversation d'elicitation.

OBJECTIF : {objective}

SUJETS A COUVRIR : {', '.join(topics)}
SUJETS RESTANTS : {', '.join(remaining) if remaining else "Tous couverts"}
{context_block}
HISTORIQUE :{history_text if history_text else " (premier tour)"}

TOUR : {turn_count + 1} / {max_turns} ({turns_left} restant(s))

REGLES :
- Ne repose JAMAIS une question dont la reponse est dans l'historique
- Adapte ta question aux reponses precedentes
- Questions ouvertes pour explorer, choix pour clarifier des preferences
- Options choice : 2 a 4 choix courts
- Le champ topic doit etre un sujet de la liste SUJETS A COUVRIR
- Si tous les sujets essentiels sont couverts OU force_done={force_done_str} : type=done

Reponds en JSON strict SANS backticks :
{{"type": "open",   "question": "...", "topic": "..."}}
{{"type": "choice", "question": "...", "options": ["A", "B"], "topic": "..."}}
{{"type": "done",   "summary": "resume 1-2 phrases", "structured_data": {{}}}}"""



def _call_llm(objective, topics, context, history, turn_count, max_turns):
    """
    Appelle le LLM pour generer la prochaine question ou conclure.
    Utilise Sonnet (smart) pour les questions — rapide, fiable, suffisant.
    Fallback propre si le LLM retourne du JSON invalide.
    """
    from app.llm_client import llm_complete
    prompt = _build_prompt(objective, topics, context, history, turn_count, max_turns)
    last_error = None
    try:
        result = llm_complete(
            messages=[{"role": "user", "content": prompt}],
            model_tier=LLM_TIER_QUESTIONS,  # "smart" = Sonnet
            max_tokens=500,
        )
        raw = result["text"].strip()
        raw = re.sub(r'^```(?:json)?\s*', '', raw, flags=re.MULTILINE)
        raw = re.sub(r'\s*```$', '', raw, flags=re.MULTILINE).strip()
        parsed = json.loads(raw)
        if parsed.get("type") not in ("open", "choice", "done"):
            raise ValueError(f"type inconnu: {parsed.get('type')}")
        if parsed["type"] == "choice":
            opts = parsed.get("options", [])
            if not isinstance(opts, list) or len(opts) < 2:
                raise ValueError("choice requiert au moins 2 options")
        return parsed, None  # (resultat, erreur)
    except Exception as e:
        last_error = str(e)
        print(f"[Elicitation] Erreur LLM: {e}")
        covered = [h["topic"] for h in history if h.get("role") == "assistant" and h.get("topic")]
        remaining = [t for t in topics if t not in covered]
        if remaining:
            fallback = {"type": "open", "question": f"Peux-tu me parler de : {remaining[0]} ?", "topic": remaining[0]}
        else:
            fallback = {"type": "done", "summary": "Session terminee.", "structured_data": {}}
        return fallback, last_error


