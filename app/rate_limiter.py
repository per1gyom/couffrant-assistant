"""
Rate limiter en mémoire pour Raya.
Limite le nombre de requêtes par utilisateur par heure sur /raya.
"""
import time
import threading

_lock = threading.Lock()
_requests: dict[str, list[float]] = {}

RATE_LIMIT_PER_HOUR = 120


def check_rate_limit(username: str) -> bool:
    """
    Retourne True si l'utilisateur peut faire une requête.
    Retourne False si la limite est atteinte.
    """
    now = time.time()
    window = 3600  # 1 heure

    with _lock:
        if username not in _requests:
            _requests[username] = []

        # Nettoyer les entrées hors fenêtre
        _requests[username] = [t for t in _requests[username] if now - t < window]

        if len(_requests[username]) >= RATE_LIMIT_PER_HOUR:
            return False

        _requests[username].append(now)
        return True
