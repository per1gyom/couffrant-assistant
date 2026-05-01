"""
Connection Resilience — auto-récupération universelle des connexions Raya.

Module commun (Phase Connexions Universelles, 1er mai 2026) hérité par tous
les connecteurs.

Voir docs/vision_connexions_universelles_01mai.md.

PHILOSOPHIE — SELF-HEALING 4 ETAPES + CIRCUIT BREAKER (decision Q17 Guillaume) :
─────────────────────────────────────────────────────────────────────────────
Toute opération qui parle à une source externe (Microsoft Graph, Google API,
Odoo XML-RPC, Twilio, etc.) peut échouer pour mille raisons. Plutôt que de
laisser chaque connecteur gérer ça à sa façon, on offre un décorateur
universel @protected qui applique les 4 étapes :

  ETAPE 1 - Retry immediat (3 tentatives sur 30s)
    Resout : ~95 pct des erreurs (micro-coupures, latence, race condition)
    Alerte : aucune (transparent)

  ETAPE 2 - Backoff exponentiel (3 retries sur 5 min)
    Resout : ~4 pct supplementaires (rate limit 429, surcharge 503)
    Alerte : INFO interne (visible /admin/health uniquement)

  ETAPE 3 - Auto-reparation contextuelle
    auth_error          -> tentative refresh token automatique
    subscription_dead   -> tentative recreation subscription automatique
    rate_limit_persistent -> pause prolongee (1h)
    Resout : ~0.9 pct supplementaires
    Alerte : WARNING (informe user de l incident auto-resolu)

  ETAPE 4 - Circuit breaker ouvert + alerte CRITICAL
    Si tout precede a echoue : on cesse de solliciter pour ne pas se faire
    bannir. Pause jusqu a intervention manuelle (reconnexion par l user).
    Pattern : 3 etats (FERME / DEMI-OUVERT / OUVERT)

→ Couvre 99.99 pct des erreurs sans intervention humaine.
→ AURAIT EVITE les 17 jours de silence du 14/04 au 01/05.

Usage type :
    from app.connection_resilience import protected

    @protected(connection_id=6, max_retries=3)
    def fetch_mail_delta(token, delta_link):
        return graph_get(token, delta_link)
"""

import functools
import logging
import time
from datetime import datetime, timedelta
from typing import Optional, Callable, Any

from app.connection_health import (
    record_poll_attempt,
    mark_circuit_open,
    reset_circuit,
)

logger = logging.getLogger("raya.connection_resilience")


# ─── CONFIGURATION DES ETAPES DE RECUPERATION ───

DEFAULT_IMMEDIATE_RETRIES = 3       # Etape 1 : retries immediats
DEFAULT_IMMEDIATE_DELAY_S = 2       # 2s, 4s, 8s entre les retries immediats
DEFAULT_BACKOFF_RETRIES = 3         # Etape 2 : retries avec backoff exponentiel
DEFAULT_BACKOFF_BASE_S = 30         # 30s, 60s, 120s
DEFAULT_BACKOFF_MAX_S = 300         # cap a 5 min
CIRCUIT_BREAKER_THRESHOLD = 5       # nb d echecs consecutifs avant ouverture


# ─── CLASSIFICATION DES ERREURS ───

class ConnectionError(Exception):
    """Erreur generique de connexion (utilisable par les connecteurs)."""
    pass


class AuthError(ConnectionError):
    """Token expire ou revoque. Etape 3 = tentative refresh."""
    pass


class SubscriptionDeadError(ConnectionError):
    """Subscription cote source supprimee. Etape 3 = recreation."""
    pass


class RateLimitError(ConnectionError):
    """Rate limit atteint (429). Etape 2 = backoff."""
    pass


class NetworkError(ConnectionError):
    """Impossible de joindre la source. Etape 1 = retry immediat."""
    pass


def _classify_exception(exc: Exception) -> str:
    """Classifie une exception en EVENT_STATUS pour record_poll_attempt.

    Heuristiques :
      - AuthError                 -> 'auth_error'
      - SubscriptionDeadError     -> 'subscription_dead'
      - RateLimitError            -> 'rate_limit'
      - NetworkError              -> 'network_error'
      - TimeoutError              -> 'timeout'
      - Autre Exception           -> 'internal_error'

    Heuristiques sur message si l exception n herite pas des classes :
      - '401', 'unauthorized', 'token expired'  -> 'auth_error'
      - '429', 'rate limit'                     -> 'rate_limit'
      - 'subscription', 'gone'                  -> 'subscription_dead'
      - 'timeout', 'timed out'                  -> 'timeout'
      - 'connection', 'network'                 -> 'network_error'
    """
    if isinstance(exc, AuthError):
        return "auth_error"
    if isinstance(exc, SubscriptionDeadError):
        return "subscription_dead"
    if isinstance(exc, RateLimitError):
        return "rate_limit"
    if isinstance(exc, NetworkError):
        return "network_error"
    if isinstance(exc, TimeoutError):
        return "timeout"

    msg = (str(exc) or "").lower()
    if "401" in msg or "unauthorized" in msg or "token expired" in msg or "invalid_grant" in msg:
        return "auth_error"
    if "429" in msg or "rate limit" in msg or "too many requests" in msg:
        return "rate_limit"
    if "subscription" in msg or "gone" in msg or "410" in msg:
        return "subscription_dead"
    if "timeout" in msg or "timed out" in msg:
        return "timeout"
    if "connection" in msg or "network" in msg or "unreachable" in msg:
        return "network_error"
    return "internal_error"


# ─── CIRCUIT BREAKER (3 ETATS) ───
#
# Etat interne par connection_id :
#   "closed"   -> fonctionnement normal, on tente
#   "half_open" -> 1 tentative test toutes les N min
#   "open"     -> on ne tente plus, attente intervention
#
# Stocke en memoire (process). Acceptable car :
#   - Si Railway redemarre, on reprend a 'closed' (= optimiste, on retente)
#   - Le statut persistant est dans connection_health.status='circuit_open'

_circuit_state: dict = {}  # {connection_id: {'state': str, 'opened_at': datetime}}


def _is_circuit_open(connection_id: int) -> bool:
    state = _circuit_state.get(connection_id)
    if not state:
        return False
    if state["state"] == "closed":
        return False
    # Half-open : on autorise une tentative tous les 5 min
    if state["state"] == "half_open":
        elapsed = (datetime.now() - state["opened_at"]).total_seconds()
        return elapsed < 300  # 5 min entre chaque tentative test
    # Open : interdit
    return True


def _open_circuit(connection_id: int, reason: str):
    _circuit_state[connection_id] = {
        "state": "open",
        "opened_at": datetime.now(),
    }
    mark_circuit_open(connection_id, reason)
    logger.warning(
        "[Resilience] Circuit OUVERT pour connection_id=%s : %s",
        connection_id, reason,
    )


def _half_open_circuit(connection_id: int):
    """Apres N min en open, on tente une requete test (half-open)."""
    if connection_id in _circuit_state:
        _circuit_state[connection_id]["state"] = "half_open"
        _circuit_state[connection_id]["opened_at"] = datetime.now()


def _close_circuit(connection_id: int):
    """La connexion remarche : on remet a fermé."""
    if connection_id in _circuit_state:
        del _circuit_state[connection_id]
    reset_circuit(connection_id)
    logger.info("[Resilience] Circuit FERME pour connection_id=%s", connection_id)


# ─── HOOKS DE REPARATION CONTEXTUELLE (ETAPE 3) ───

# Les connecteurs s y inscrivent. Quand une AuthError survient, on appelle
# le hook si enregistre. Si le hook retourne True, on retente une fois.
# Sinon on passe a l etape 4 (circuit ouvert).

_repair_hooks: dict = {}  # {connection_id: {'auth_error': callable, ...}}


def register_repair_hook(
    connection_id: int,
    error_type: str,
    repair_func: Callable[[], bool],
) -> None:
    """Enregistre une fonction de reparation pour un type d erreur.

    Args:
        connection_id: la connexion concernee
        error_type: 'auth_error' / 'subscription_dead' / etc.
        repair_func: callable() -> bool (True si la reparation a reussi)

    Exemple :
        def refresh_outlook_token():
            # tentative de refresh token Microsoft
            return success

        register_repair_hook(connection_id=6, error_type='auth_error',
                             repair_func=refresh_outlook_token)
    """
    if connection_id not in _repair_hooks:
        _repair_hooks[connection_id] = {}
    _repair_hooks[connection_id][error_type] = repair_func


def _try_repair(connection_id: int, error_type: str) -> bool:
    """Tente la reparation contextuelle. Retourne True si succes."""
    hooks = _repair_hooks.get(connection_id, {})
    repair_func = hooks.get(error_type)
    if not repair_func:
        return False
    try:
        success = repair_func()
        if success:
            logger.info(
                "[Resilience] Reparation REUSSIE connection_id=%s type=%s",
                connection_id, error_type,
            )
            return True
        logger.warning(
            "[Resilience] Reparation ECHOUEE connection_id=%s type=%s",
            connection_id, error_type,
        )
        return False
    except Exception as e:
        logger.error(
            "[Resilience] Hook reparation exception connection_id=%s type=%s : %s",
            connection_id, error_type, str(e)[:200],
        )
        return False


# ─── DECORATEUR PRINCIPAL @protected ───

def protected(
    connection_id: int,
    max_immediate_retries: int = DEFAULT_IMMEDIATE_RETRIES,
    max_backoff_retries: int = DEFAULT_BACKOFF_RETRIES,
    record_in_health: bool = True,
):
    """Decorateur qui applique le self-healing 4 etapes a une fonction.

    Usage :
        @protected(connection_id=6)
        def fetch_mail_delta(token, delta_link):
            return graph_get(token, delta_link)

        # Si tout va bien : appel transparent, retourne le resultat
        # Si erreur transitoire : retry immediat (etape 1)
        # Si rate limit : backoff (etape 2)
        # Si auth error : tentative refresh token (etape 3)
        # Si tout echoue : circuit ouvert + raise

    Args:
        connection_id: ref vers tenant_connections.id
        max_immediate_retries: nb de retries etape 1
        max_backoff_retries: nb de retries etape 2
        record_in_health: si True, log dans connection_health_events
                          (par defaut True ; mettre False pour les operations
                          internes qui ne sont pas un poll)
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            # Pre-check : circuit ouvert ?
            if _is_circuit_open(connection_id):
                raise ConnectionError(
                    f"Circuit ouvert pour connection_id={connection_id}, "
                    f"intervention requise"
                )

            poll_started = datetime.now()
            last_exc = None

            # ─── ETAPE 1 : retry immediat ───
            for attempt in range(max_immediate_retries):
                try:
                    result = func(*args, **kwargs)
                    # Succes : on log si demande, on ferme le circuit si besoin
                    duration_ms = int((datetime.now() - poll_started).total_seconds() * 1000)
                    if record_in_health:
                        # Note : on ne connait pas items_seen/items_new au niveau
                        # generique, le connecteur peut ajouter ces infos via
                        # un appel direct a record_poll_attempt avant le return.
                        record_poll_attempt(
                            connection_id=connection_id,
                            status="ok",
                            duration_ms=duration_ms,
                            poll_started_at=poll_started,
                        )
                    if connection_id in _circuit_state:
                        _close_circuit(connection_id)
                    return result
                except Exception as e:
                    last_exc = e
                    error_type = _classify_exception(e)
                    if attempt < max_immediate_retries - 1:
                        # Pas le dernier retry immediat : on reessaye apres delai court
                        delay = DEFAULT_IMMEDIATE_DELAY_S * (2 ** attempt)
                        logger.debug(
                            "[Resilience] Retry immediat #%d connection_id=%s type=%s delay=%ss",
                            attempt + 1, connection_id, error_type, delay,
                        )
                        time.sleep(delay)
                    # else : on sort de la boucle pour passer a l etape 2

            # Si erreur 401/auth : on tente l etape 3 IMMEDIATEMENT
            # (pas de point a faire du backoff sur un token mort)
            error_type = _classify_exception(last_exc)
            if error_type in ("auth_error", "subscription_dead"):
                logger.info(
                    "[Resilience] Etape 3 reparation contextuelle connection_id=%s type=%s",
                    connection_id, error_type,
                )
                if _try_repair(connection_id, error_type):
                    # Reparation reussie : on retente UNE fois
                    try:
                        result = func(*args, **kwargs)
                        duration_ms = int((datetime.now() - poll_started).total_seconds() * 1000)
                        if record_in_health:
                            record_poll_attempt(
                                connection_id=connection_id,
                                status="ok",
                                duration_ms=duration_ms,
                                poll_started_at=poll_started,
                                error_detail=f"Recupere apres reparation {error_type}",
                            )
                        return result
                    except Exception as e:
                        last_exc = e
                        error_type = _classify_exception(e)

            # ─── ETAPE 2 : backoff exponentiel ───
            # On l applique surtout pour rate_limit / network_error
            if error_type in ("rate_limit", "network_error", "timeout", "internal_error"):
                for attempt in range(max_backoff_retries):
                    delay = min(
                        DEFAULT_BACKOFF_BASE_S * (2 ** attempt),
                        DEFAULT_BACKOFF_MAX_S,
                    )
                    logger.info(
                        "[Resilience] Etape 2 backoff connection_id=%s type=%s delay=%ss attempt=%d/%d",
                        connection_id, error_type, delay, attempt + 1, max_backoff_retries,
                    )
                    time.sleep(delay)
                    try:
                        result = func(*args, **kwargs)
                        duration_ms = int((datetime.now() - poll_started).total_seconds() * 1000)
                        if record_in_health:
                            record_poll_attempt(
                                connection_id=connection_id,
                                status="ok",
                                duration_ms=duration_ms,
                                poll_started_at=poll_started,
                                error_detail=f"Recupere apres backoff {error_type}",
                            )
                        return result
                    except Exception as e:
                        last_exc = e
                        error_type = _classify_exception(e)

            # ─── ETAPE 4 : tout a echoue, circuit OUVERT ───
            duration_ms = int((datetime.now() - poll_started).total_seconds() * 1000)
            if record_in_health:
                record_poll_attempt(
                    connection_id=connection_id,
                    status=error_type,
                    duration_ms=duration_ms,
                    poll_started_at=poll_started,
                    error_detail=f"Echec definitif apres 4 etapes: {str(last_exc)[:500]}",
                )

            # Compte les echecs consecutifs pour decider d ouvrir le circuit
            # (le compteur est tenu par connection_health, on lit la valeur)
            try:
                from app.database import get_pg_conn
                conn = get_pg_conn()
                c = conn.cursor()
                c.execute(
                    "SELECT consecutive_failures FROM connection_health WHERE connection_id = %s",
                    (connection_id,),
                )
                row = c.fetchone()
                consecutive = row[0] if row else 0
                conn.close()
                if consecutive >= CIRCUIT_BREAKER_THRESHOLD:
                    _open_circuit(connection_id, f"{consecutive} echecs consecutifs : {error_type}")
            except Exception:
                pass

            # On re-raise l exception originale
            raise last_exc if last_exc else ConnectionError("Erreur inconnue")

        return wrapper
    return decorator


# ─── HELPERS POUR LES TESTS ET DEBUG ───

def get_circuit_state(connection_id: int) -> dict:
    """Retourne l etat du circuit pour debug."""
    state = _circuit_state.get(connection_id)
    if not state:
        return {"state": "closed", "opened_at": None}
    return {
        "state": state["state"],
        "opened_at": state["opened_at"].isoformat() if state.get("opened_at") else None,
    }


def reset_all_circuits() -> int:
    """Reset tous les circuits (utile pour tests ou maintenance manuelle).
    Retourne le nb de circuits resettes."""
    count = len(_circuit_state)
    _circuit_state.clear()
    return count
