"""
Cache mémoire simple avec TTL pour Raya.
Réduit les requêtes DB répétitives (règles, insights, hot_summary).
Thread-safe. TTL par défaut : 5 minutes.
"""
import time
import threading

_lock = threading.Lock()
_cache: dict[str, dict] = {}

DEFAULT_TTL = 300  # 5 minutes


def get(key: str):
    """Retourne la valeur cachée ou None si expirée/absente."""
    with _lock:
        entry = _cache.get(key)
        if entry is None:
            return None
        if time.time() > entry["expires"]:
            del _cache[key]
            return None
        return entry["value"]


def set(key: str, value, ttl: int = DEFAULT_TTL):
    """Stocke une valeur avec TTL en secondes."""
    with _lock:
        _cache[key] = {
            "value": value,
            "expires": time.time() + ttl,
        }


def invalidate(key: str):
    """Supprime une entrée du cache."""
    with _lock:
        _cache.pop(key, None)


def invalidate_prefix(prefix: str):
    """Supprime toutes les entrées dont la clé commence par prefix."""
    with _lock:
        keys_to_delete = [k for k in _cache if k.startswith(prefix)]
        for k in keys_to_delete:
            del _cache[k]


def clear():
    """Vide tout le cache."""
    with _lock:
        _cache.clear()
