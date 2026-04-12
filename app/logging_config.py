"""
Configuration logging centralisée pour Raya.
Remplace les print() par un logging structuré avec niveaux.
"""
import logging
import sys


def setup_logging():
    """Configure le logging au démarrage de l'app."""
    formatter = logging.Formatter(
        fmt="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    # Éviter les doublons si appelé plusieurs fois
    if not root.handlers:
        root.addHandler(handler)

    # Réduire le bruit des bibliothèques externes
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("apscheduler").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Retourne un logger nommé pour un module."""
    return logging.getLogger(name)
