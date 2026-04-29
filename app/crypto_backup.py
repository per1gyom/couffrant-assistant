"""
Chiffrement symetrique des backups externes — Fernet (cryptography).

Configuration :
  Variable Railway : BACKUP_ENCRYPTION_KEY
  Generation       : python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

Usage :
  from app.crypto_backup import encrypt_bytes, decrypt_bytes

  encrypted = encrypt_bytes(raw_bytes)
  raw = decrypt_bytes(encrypted)

Comportement :
  - Cle presente  : chiffrement actif
  - Cle absente   : leve RuntimeError (volontaire — pas de fallback silencieux
                    pour les backups, sinon on uploaderait du clair par erreur)

Note hygiene : BACKUP_ENCRYPTION_KEY DOIT etre differente de
TOKEN_ENCRYPTION_KEY (regle 1 cle = 1 usage). La premiere chiffre les
backups Drive, la seconde chiffre les tokens OAuth en DB.
"""
import os

_fernet = None
_fernet_loaded = False


def _get_fernet():
    """Charge la cle Fernet une seule fois (lazy)."""
    global _fernet, _fernet_loaded
    if not _fernet_loaded:
        key = os.getenv("BACKUP_ENCRYPTION_KEY", "").strip()
        if key:
            try:
                from cryptography.fernet import Fernet
                _fernet = Fernet(key.encode())
                print("[CryptoBackup] Chiffrement backups actif.")
            except Exception as e:
                print(f"[CryptoBackup] Cle BACKUP_ENCRYPTION_KEY invalide: {e}")
                _fernet = None
        else:
            print("[CryptoBackup] BACKUP_ENCRYPTION_KEY absente.")
            _fernet = None
        _fernet_loaded = True
    return _fernet


def encrypt_bytes(data: bytes) -> bytes:
    """Chiffre des bytes. Leve RuntimeError si la cle est absente."""
    f = _get_fernet()
    if f is None:
        raise RuntimeError(
            "BACKUP_ENCRYPTION_KEY absente ou invalide — "
            "impossible de chiffrer le backup. Refus volontaire pour "
            "ne pas uploader du clair par erreur."
        )
    return f.encrypt(data)


def decrypt_bytes(data: bytes) -> bytes:
    """Dechiffre des bytes. Leve RuntimeError si la cle est absente."""
    f = _get_fernet()
    if f is None:
        raise RuntimeError(
            "BACKUP_ENCRYPTION_KEY absente ou invalide — "
            "impossible de dechiffrer le backup."
        )
    return f.decrypt(data)


def is_configured() -> bool:
    """True si BACKUP_ENCRYPTION_KEY est configuree et valide."""
    return _get_fernet() is not None
