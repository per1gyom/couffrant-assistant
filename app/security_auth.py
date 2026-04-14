"""
Auth : hachage, vérification, rate limiting progressif, validation MDP robuste.

Logique de blocage par username (persistant en DB, multi-instance safe) :
  Round 1 : 3 échecs → 5 min   (login_locked_until)
  Round 2 : 3 échecs → 30 min  (login_locked_until)
  Round 3 : 3 échecs → BLOCAGE DÉFINITIF (account_locked=true) + alerte admin

Colonnes utilisées dans users :
  login_attempts_count INT  — échecs dans le round courant
  login_attempts_round INT  — round actuel (0, 1, 2)
  login_locked_until TIMESTAMP — fin du verrouillage temporaire
  account_locked BOOLEAN   — blocage définitif

Rate limiting par IP : en mémoire (anti-bot, secondaire)
"""
import hashlib
import hmac
import os
import re
import base64
import time

_ip_attempts: dict = {}  # {ip: {count, locked_until}} — rate limiting IP en mémoire

_LOCKOUT_ROUNDS = [
    (3, 5 * 60),    # Round 1 : 3 échecs → 5 min
    (3, 30 * 60),   # Round 2 : 3 échecs → 30 min
    (3, None),      # Round 3 : 3 échecs → PERMANENT
]


# ─── VALIDATION MDP ───

def validate_password_strength(password: str) -> tuple:
    """
    Vérifie la robustesse du mot de passe.
    Critères : 12 chars min + majuscule + minuscule + chiffre + caractère spécial.
    Retourne (True, "") si valide, (False, "message") sinon.
    """
    errors = []
    if len(password) < 12:
        errors.append("12 caractères minimum")
    if not re.search(r'[A-Z]', password):
        errors.append("au moins une majuscule")
    if not re.search(r'[a-z]', password):
        errors.append("au moins une minuscule")
    if not re.search(r'\d', password):
        errors.append("au moins un chiffre")
    if not re.search(r'[^A-Za-z0-9]', password):
        errors.append("au moins un caractère spécial (!@#$%&*...)")
    if errors:
        return False, "Mot de passe insuffisant : " + ", ".join(errors) + "."
    return True, ""


# ─── RATE LIMITING PAR IP ───

def check_rate_limit(ip: str) -> tuple:
    """Vérifie si l'IP est temporairement bloquée (anti-bot)."""
    now = time.time()
    data = _ip_attempts.get(ip, {})
    if data.get("locked_until", 0) > now:
        remaining = int((data["locked_until"] - now) / 60) + 1
        return False, f"Trop de tentatives depuis cette adresse. Réessayez dans {remaining} min."
    return True, ""


def record_failed_attempt(ip: str):
    """Incrémente le compteur IP."""
    now = time.time()
    data = _ip_attempts.setdefault(ip, {"count": 0})
    data["count"] = data.get("count", 0) + 1
    if data["count"] >= 5:
        data["locked_until"] = now + 15 * 60
        data["count"] = 0


def clear_attempts(ip: str):
    _ip_attempts.pop(ip, None)


# ─── LOCKOUT PAR USERNAME (persistant en DB, multi-instance safe) ───

def hash_password(password: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 100_000)
    return base64.b64encode(salt + dk).decode('utf-8')


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        raw = base64.b64decode(stored_hash.encode('utf-8'))
        salt, stored_dk = raw[:16], raw[16:]
        dk = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 100_000)
        return hmac.compare_digest(dk, stored_dk)
    except Exception:
        return False
