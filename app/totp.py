"""
TOTP RFC 6238 — generation secret, verification, codes recovery.

Module pur sans dependances FastAPI/DB. Tous les inputs/outputs sont
typés et testables en isolation. Aucun import de ce module ne touche
encore au flow login/auth (ce sera le LOT 2/3).

Securite :
  - Secret TOTP toujours chiffre via TOKEN_ENCRYPTION_KEY (Fernet).
    REFUS DUR si la cle est absente : on ne stocke jamais un secret 2FA
    en clair en DB (contrairement a crypto.py qui fait passthrough).
  - Codes recovery hashes via pbkdf2-sha256 100k iter + salt 16 bytes
    (meme pattern que hash_password de security_auth.py).
  - Fenetre de verification +-1 cycle = +-90s (Q5=B valide par Guillaume).
  - Codes recovery generes via secrets module (cryptographiquement fort).
  - Comparaison via hmac.compare_digest pour resistance timing.

Configuration :
  Variable Railway requise : TOKEN_ENCRYPTION_KEY (Fernet, deja en prod
  pour les tokens OAuth Microsoft/Gmail). Pas de nouvelle cle a creer.

Usage type (dans les LOTs suivants) :
  # Setup 2FA (LOT 2)
  secret = generate_totp_secret()
  uri = generate_provisioning_uri("guillaume", secret)
  qr_png = generate_qr_code_png(uri)
  encrypted = encrypt_totp_secret(secret)
  # ... stocker encrypted dans users.totp_secret_encrypted

  # Login 2FA (LOT 3)
  encrypted = db.fetch_totp_secret(username)
  secret = decrypt_totp_secret(encrypted)
  ok = verify_totp_code(secret, user_input)
"""
import base64
import hashlib
import hmac
import os
import secrets
from io import BytesIO

import pyotp
import qrcode

from app.crypto import encrypt_token, decrypt_token


# --- CONSTANTES ---

ISSUER_NAME = "Raya"
TOTP_INTERVAL = 30           # 30s par cycle (standard RFC 6238)
TOTP_VERIFY_WINDOW = 1       # +-1 cycle = +-90s tolerance (Q5=B)
RECOVERY_CODES_COUNT = 8     # 8 codes (Q2=B)
RECOVERY_CODE_LENGTH = 10    # 10 chars utiles, formates en XXXXX-XXXXX
# Alphabet sans ambiguites visuelles (pas de 0/O ni 1/I/L)
RECOVERY_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


# --- HELPERS PRIVES ---

def _ensure_encryption_available():
    """
    Refuse de tourner si TOKEN_ENCRYPTION_KEY absent.
    Durcissement specifique 2FA : on ne tolere PAS le passthrough
    silencieux de crypto.py pour les secrets TOTP.
    """
    if not os.getenv("TOKEN_ENCRYPTION_KEY", "").strip():
        raise RuntimeError(
            "TOKEN_ENCRYPTION_KEY absent : refus de stocker un secret 2FA "
            "en clair en DB. Configurer la variable d'environnement Railway "
            "avant d'activer la 2FA."
        )


def _normalize_recovery_code(code: str) -> str:
    """Uppercase + retire tirets/espaces (tolerant a la saisie)."""
    return (code or "").strip().upper().replace("-", "").replace(" ", "")


# --- TOTP SECRET ---

def generate_totp_secret() -> str:
    """
    Genere un nouveau secret TOTP base32 (160 bits = 32 caracteres).
    Compatible Google Authenticator, Microsoft Authenticator, Authy, 1Password.
    """
    return pyotp.random_base32()


def encrypt_totp_secret(secret: str) -> str:
    """
    Chiffre le secret TOTP via Fernet pour stockage en DB.
    Refuse si TOKEN_ENCRYPTION_KEY absent (pas de passthrough).
    """
    _ensure_encryption_available()
    encrypted = encrypt_token(secret)
    if encrypted == secret:
        # encrypt_token a fait un passthrough = cle effectivement absente
        raise RuntimeError(
            "Echec chiffrement secret 2FA : crypto.py n'a pas chiffre. "
            "Verifier TOKEN_ENCRYPTION_KEY."
        )
    return encrypted


def decrypt_totp_secret(encrypted: str) -> str:
    """
    Dechiffre un secret TOTP. Renvoie le base32 brut (32 chars).
    Refuse si TOKEN_ENCRYPTION_KEY absent.
    """
    _ensure_encryption_available()
    if not encrypted:
        return ""
    return decrypt_token(encrypted)


def generate_provisioning_uri(username: str, secret: str, issuer: str = ISSUER_NAME) -> str:
    """
    Genere l'URI otpauth:// a encoder en QR code.
    Format : otpauth://totp/Raya:guillaume?secret=ABCD...&issuer=Raya
    Lu directement par les apps d'authentification.
    """
    return pyotp.totp.TOTP(secret).provisioning_uri(name=username, issuer_name=issuer)


def generate_qr_code_png(uri: str, box_size: int = 8, border: int = 2) -> bytes:
    """
    Genere un QR code PNG (bytes) pour un URI otpauth.
    Taille par defaut adaptee a un affichage web (~256x256 px).
    """
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=box_size,
        border=border,
    )
    qr.add_data(uri)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def verify_totp_code(secret: str, code: str, window: int = TOTP_VERIFY_WINDOW) -> bool:
    """
    Verifie un code TOTP (6 chiffres) avec tolerance fenetre.

    window=1 (defaut) : accepte le code precedent et suivant le code courant
                       = +-90s autour de maintenant.

    Tolerant a la saisie : strip, retire les espaces.
    Renvoie False sur input invalide, jamais d'exception.
    """
    if not secret:
        return False
    code = (code or "").strip().replace(" ", "")
    if not code.isdigit() or len(code) != 6:
        return False
    try:
        return pyotp.TOTP(secret, interval=TOTP_INTERVAL).verify(code, valid_window=window)
    except Exception:
        return False


# --- RECOVERY CODES ---

def generate_recovery_codes(count: int = RECOVERY_CODES_COUNT) -> list:
    """
    Genere `count` codes de recuperation au format XXXXX-XXXXX.
    Alphabet sans ambiguites visuelles.
    Cryptographiquement fort (secrets module).

    A afficher UNE SEULE FOIS au user, jamais restocker en clair.
    """
    codes = []
    for _ in range(count):
        raw = "".join(
            secrets.choice(RECOVERY_CODE_ALPHABET) for _ in range(RECOVERY_CODE_LENGTH)
        )
        codes.append(f"{raw[:5]}-{raw[5:]}")
    return codes


def hash_recovery_code(code: str) -> str:
    """
    Hash un code recovery via pbkdf2-sha256 100k iter + salt 16 bytes random.
    Meme pattern que hash_password de security_auth.py.
    Format de sortie : base64(salt || dk).
    """
    normalized = _normalize_recovery_code(code)
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", normalized.encode("utf-8"), salt, 100_000)
    return base64.b64encode(salt + dk).decode("utf-8")


def hash_recovery_codes_batch(codes: list) -> list:
    """Hash une liste de codes (helper pour la generation initiale)."""
    return [hash_recovery_code(c) for c in codes]


def _verify_against_hash(code: str, stored_hash: str) -> bool:
    """Verifie un code candidat contre un hash stocke (compare_digest)."""
    try:
        normalized = _normalize_recovery_code(code)
        raw = base64.b64decode(stored_hash.encode("utf-8"))
        salt, stored_dk = raw[:16], raw[16:]
        dk = hashlib.pbkdf2_hmac("sha256", normalized.encode("utf-8"), salt, 100_000)
        return hmac.compare_digest(dk, stored_dk)
    except Exception:
        return False


def consume_recovery_code(code: str, hashes: list) -> tuple:
    """
    Tente de consommer un code recovery.

    Args:
      code   : code saisi par le user (format X-Y ou XY tolere)
      hashes : liste de hashes stockes en DB (jsonb users.recovery_codes_hashes)

    Returns:
      (matched: bool, remaining_hashes: list)
      Si matched=True, le hash correspondant est retire de remaining_hashes.
      Si matched=False, remaining_hashes == hashes (inchange).

    Note timing : on parcourt TOUTE la liste meme apres match pour eviter
    les fuites par mesure de temps.
    """
    matched_index = -1
    for i, h in enumerate(hashes or []):
        if _verify_against_hash(code, h):
            matched_index = i
            # Pas de break : on continue pour timing constant
    if matched_index >= 0:
        remaining = [h for i, h in enumerate(hashes) if i != matched_index]
        return True, remaining
    return False, list(hashes or [])
