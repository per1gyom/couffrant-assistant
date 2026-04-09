"""
Chiffrement symétrique des tokens OAuth — Fernet (bibliothèque cryptography).

Configuration :
  Variable Railway : TOKEN_ENCRYPTION_KEY
  Génération     : python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

Comportement :
  - Clé présente  : chiffrement actif, tokens opaques en base
  - Clé absente   : passthrough transparent, tokens en clair (compat ascendante)
  - Migration auto : tokens en clair lus correctement, rechiffrés à la prochaine sauvegarde

Les tokens Fernet commencent toujours par 'gAAAAA' — utilisé pour détecter l'état.
"""
import os

_fernet = None
_fernet_loaded = False


def _get_fernet():
    """Charge la clé Fernet une seule fois (lazy)."""
    global _fernet, _fernet_loaded
    if not _fernet_loaded:
        key = os.getenv("TOKEN_ENCRYPTION_KEY", "").strip()
        if key:
            try:
                from cryptography.fernet import Fernet
                _fernet = Fernet(key.encode())
                print("[Crypto] Chiffrement tokens OAuth actif.")
            except Exception as e:
                print(f"[Crypto] Clé TOKEN_ENCRYPTION_KEY invalide — chiffrement désactivé: {e}")
                _fernet = None
        else:
            print("[Crypto] TOKEN_ENCRYPTION_KEY absent — tokens en clair (passthrough).")
        _fernet_loaded = True
    return _fernet


def encrypt_token(value: str) -> str:
    """
    Chiffre un token.
    Passthrough si TOKEN_ENCRYPTION_KEY absent ou si valeur vide.
    """
    if not value:
        return value
    f = _get_fernet()
    if f is None:
        return value
    try:
        return f.encrypt(value.encode()).decode()
    except Exception as e:
        print(f"[Crypto] Erreur chiffrement: {e}")
        return value


def decrypt_token(value: str) -> str:
    """
    Déchiffre un token.
    - Si la clé est absente : passthrough
    - Si le token ne commence pas par 'gAAAAA' : c'est du clair, retourne tel quel (migration)
    - Si erreur de déchiffrement : retourne tel quel (sécurité)
    """
    if not value:
        return value
    f = _get_fernet()
    if f is None:
        return value
    if not value.startswith("gAAAAA"):
        # Token en clair (avant migration) — passthrough
        return value
    try:
        return f.decrypt(value.encode()).decode()
    except Exception as e:
        print(f"[Crypto] Erreur déchiffrement: {e}")
        return value


def is_encrypted(value: str) -> bool:
    """True si le token est déjà chiffré (préfixe Fernet)."""
    return bool(value and value.startswith("gAAAAA"))
