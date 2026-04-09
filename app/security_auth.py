"""
Auth : hachage, vérification mot de passe, rate limiting.
"""
import hashlib
import hmac
import os
import base64
import time

_login_attempts: dict = {}
MAX_ATTEMPTS = 5
LOCKOUT_SECONDS = 15 * 60


def check_rate_limit(ip: str) -> tuple:
    now = time.time()
    data = _login_attempts.get(ip, {})
    locked_until = data.get("locked_until", 0)
    if locked_until > now:
        remaining = int((locked_until - now) / 60) + 1
        return False, f"Trop de tentatives. Réessaie dans {remaining} minute(s)."
    return True, ""


def record_failed_attempt(ip: str):
    now = time.time()
    data = _login_attempts.setdefault(ip, {"count": 0})
    data["count"] = data.get("count", 0) + 1
    if data["count"] >= MAX_ATTEMPTS:
        data["locked_until"] = now + LOCKOUT_SECONDS
        data["count"] = 0


def clear_attempts(ip: str):
    _login_attempts.pop(ip, None)


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
