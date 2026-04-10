"""
Couche d'abstraction LLM pour Raya.

Tout le code applicatif appelle llm_complete() au lieu de client.messages.create().
Le fournisseur réel (Anthropic, OpenAI, etc.) est sélectionné par variable d'environnement.

Migration vers un autre LLM = ajouter un nouveau provider ici, pas toucher au reste du code.

Variables d'environnement :
    LLM_PROVIDER         : 'anthropic' (défaut), 'openai' (futur), 'mistral' (futur)
    LLM_MODEL_SMART      : modèle "intelligent" — conversations quotidiennes, analyse mails
    LLM_MODEL_FAST       : modèle "rapide" — filtrage, classifications, routage de tier
    LLM_MODEL_DEEP       : modèle "profond" — synthèse, hot_summary, onboarding, audit règles
    ANTHROPIC_API_KEY    : clé Anthropic

Tiers :
    fast  (Haiku)  : micro-appels OUI/NON, routage, triage mails
    smart (Sonnet) : conversations quotidiennes, analyse mails, suggestions
    deep  (Opus)   : synthèse de sessions, hot_summary, audit cohérence, onboarding
"""
import os
from app.config import (
    ANTHROPIC_API_KEY, ANTHROPIC_MODEL_SMART, ANTHROPIC_MODEL_FAST,
)


# ─── CONFIGURATION ───

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "anthropic").lower()

# Mapping des tiers "logiques" vers les modèles réels selon le provider
_PROVIDER_MODELS = {
    "anthropic": {
        "fast":  os.getenv("LLM_MODEL_FAST",  ANTHROPIC_MODEL_FAST),
        "smart": os.getenv("LLM_MODEL_SMART", ANTHROPIC_MODEL_SMART),
        "deep":  os.getenv("LLM_MODEL_DEEP",  "claude-opus-4-6-20260401"),
    },
    # Futurs providers à brancher ici :
    # "openai":  {"fast": "gpt-5-mini", "smart": "gpt-5", "deep": "gpt-5"},
    # "mistral": {"fast": "mistral-small-latest", "smart": "mistral-large-latest", "deep": "mistral-large-latest"},
}


# ─── CLIENT LAZY-INITIALIZED ───

_anthropic_client = None


def _get_anthropic_client():
    global _anthropic_client
    if _anthropic_client is None:
        import anthropic
        _anthropic_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    return _anthropic_client


# ─── INTERFACE PUBLIQUE ───

def llm_complete(
    messages: list,
    model_tier: str = "smart",
    max_tokens: int = 1024,
    system: str = None,
    temperature: float = None,
) -> dict:
    """
    Effectue un appel LLM unifié, indépendant du provider.

    Args:
        messages   : liste {"role": "user|assistant", "content": "..."}
        model_tier : "fast" | "smart" | "deep"
        max_tokens : limite de tokens en sortie
        system     : prompt système (optionnel)
        temperature: optionnel, défaut du provider sinon

    Returns:
        dict standardisé :
        {
            "text":          str,   # texte de la réponse
            "stop_reason":   str,   # 'end_turn', 'max_tokens', etc.
            "input_tokens":  int,
            "output_tokens": int,
            "model":         str,   # nom réel du modèle utilisé
            "provider":      str,   # 'anthropic', etc.
            "raw":           Any,   # objet brut du provider
        }

    Lève RuntimeError si le provider est inconnu ou mal configuré.
    """
    if LLM_PROVIDER not in _PROVIDER_MODELS:
        raise RuntimeError(
            f"LLM_PROVIDER='{LLM_PROVIDER}' inconnu. "
            f"Providers supportés : {list(_PROVIDER_MODELS.keys())}"
        )

    model_name = _PROVIDER_MODELS[LLM_PROVIDER].get(model_tier)
    if not model_name:
        raise RuntimeError(f"Tier '{model_tier}' non défini pour {LLM_PROVIDER}")

    if LLM_PROVIDER == "anthropic":
        return _complete_anthropic(messages, model_name, max_tokens, system, temperature)

    raise RuntimeError(f"Provider '{LLM_PROVIDER}' déclaré mais non implémenté")


def _complete_anthropic(messages, model_name, max_tokens, system, temperature):
    client = _get_anthropic_client()

    kwargs = {
        "model":      model_name,
        "max_tokens": max_tokens,
        "messages":   messages,
    }
    if system:
        kwargs["system"] = system
    if temperature is not None:
        kwargs["temperature"] = temperature

    response = client.messages.create(**kwargs)

    # Extraction robuste (un message peut contenir plusieurs blocs)
    text_parts = [block.text for block in response.content if hasattr(block, "text")]
    text = "".join(text_parts)

    return {
        "text":          text,
        "stop_reason":   response.stop_reason,
        "input_tokens":  response.usage.input_tokens,
        "output_tokens": response.usage.output_tokens,
        "model":         model_name,
        "provider":      "anthropic",
        "raw":           response,
    }


# ─── LOGGING DES COÛTS (non-bloquant) ───

def log_llm_usage(result: dict, username: str, tenant_id: str, purpose: str = ""):
    """
    Logge l'usage LLM en base pour suivi des coûts par tenant.
    Non-bloquant : si l'écriture échoue, on continue.
    """
    try:
        from app.database import get_pg_conn
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            INSERT INTO llm_usage
              (tenant_id, username, provider, model, input_tokens, output_tokens, purpose)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (
            tenant_id, username,
            result.get("provider", "unknown"),
            result.get("model",    "unknown"),
            result.get("input_tokens",  0),
            result.get("output_tokens", 0),
            (purpose or "")[:100],
        ))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[llm_usage] Logging échoué (non bloquant) : {e}")
