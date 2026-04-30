"""
PIN court (4-6 chiffres) pour acces aux panels /admin et /super_admin.

Implemente le LOT 5 du chantier 2FA (decision Guillaume 30/04) :
- PIN demande a CHAQUE entree dans le panel admin (independant des 30j 2FA)
- Different du mot de passe principal et du code 2FA Authenticator
- 3 essais rates -> blocage du PIN, escalade vers 2FA complete pour debloquer
- Validite tant que la fenetre/onglet est ouvert (cookie de session uniquement)
- Si onglet ferme + reouvert -> PIN redemande

Pourquoi ce niveau supplementaire :
  Cas concret : Charlotte ouvre Raya, valide sa 2FA (30j). Elle laisse
  l ordi sans verrouiller. Quelqu un d autre passe et clique 'Admin'.
  Sans LOT 5 : il rentre dans le panel admin de Charlotte.
  Avec LOT 5 : il doit retaper le PIN de Charlotte (qu il ne connait pas).

Stockage :
  - pin_hash dans users (pbkdf2-sha256 + salt 16B)
  - pin_attempts_count : essais rates dans la fenetre courante
  - pin_locked_until : timestamp fin de blocage
  - pin_set_at : timestamp de creation/changement du PIN

Validite session :
  - request.session["admin_pin_validated_at"] : timestamp Unix
  - Comparaison avec PIN_SESSION_VALIDITY_SECONDS (par defaut tant que
    la session existe = pas de check de duree, juste presence du flag)
"""
import base64
import hashlib
import hmac
import os
import re
import time
from datetime import datetime, timedelta
from typing import Optional, Tuple

from app.database import get_pg_conn
from app.logging_config import get_logger

logger = get_logger("raya.admin_pin")


# ─── CONSTANTES ────────────────────────────────────────────────────────

# PIN entre 4 et 6 chiffres
PIN_MIN_LENGTH = 4
PIN_MAX_LENGTH = 6

# Apres N essais rates, on bloque et on demande la 2FA pour debloquer
PIN_MAX_ATTEMPTS = 3

# Duree du blocage PIN apres N essais rates (en secondes)
PIN_LOCKOUT_SECONDS = 5 * 60  # 5 minutes


# ─── VALIDATION ────────────────────────────────────────────────────────


def validate_pin_format(pin: str) -> Tuple[bool, str]:
    """Verifie qu un PIN respecte les regles : 4-6 chiffres uniquement.

    Returns (valid: bool, error_message: str).
    """
    if not pin:
        return False, "PIN requis"
    pin = pin.strip()
    if not re.match(r"^\d+$", pin):
        return False, "Le PIN ne doit contenir que des chiffres"
    if len(pin) < PIN_MIN_LENGTH:
        return False, f"PIN trop court (min {PIN_MIN_LENGTH} chiffres)"
    if len(pin) > PIN_MAX_LENGTH:
        return False, f"PIN trop long (max {PIN_MAX_LENGTH} chiffres)"
    # Refus PIN trivial
    if pin in ("0000", "00000", "000000", "1234", "12345", "123456"):
        return False, "PIN trop simple. Choisis une combinaison moins evidente."
    if len(set(pin)) == 1:
        return False, "PIN trop simple (un seul chiffre repete)."
    return True, ""


# ─── HASHING ───────────────────────────────────────────────────────────


def hash_pin(pin: str) -> str:
    """Hash un PIN avec pbkdf2-sha256 + salt 16B random (meme pattern que password)."""
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", pin.encode("utf-8"), salt, 100_000)
    return base64.b64encode(salt + dk).decode("utf-8")


def verify_pin_hash(pin: str, stored_hash: str) -> bool:
    """Verifie un PIN contre son hash stocke (compare_digest, timing-safe)."""
    if not pin or not stored_hash:
        return False
    try:
        raw = base64.b64decode(stored_hash.encode("utf-8"))
        salt, stored_dk = raw[:16], raw[16:]
        dk = hashlib.pbkdf2_hmac("sha256", pin.encode("utf-8"), salt, 100_000)
        return hmac.compare_digest(dk, stored_dk)
    except Exception:
        return False


# ─── DB OPERATIONS ─────────────────────────────────────────────────────


def has_pin_set(username: str) -> bool:
    """Renvoie True si l user a deja configure un PIN admin."""
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute(
            "SELECT pin_hash FROM users WHERE username = %s AND deleted_at IS NULL",
            (username,),
        )
        row = c.fetchone()
        return bool(row and row[0])
    except Exception as e:
        logger.error("[Admin PIN] has_pin_set error: %s", str(e)[:200])
        return False
    finally:
        if conn:
            conn.close()


def set_pin(username: str, new_pin: str) -> Tuple[bool, str]:
    """Configure ou met a jour le PIN admin d un user.

    Returns (success: bool, error_message: str).
    Reset les compteurs d echecs au passage.
    """
    valid, err = validate_pin_format(new_pin)
    if not valid:
        return False, err

    conn = None
    try:
        pin_hash = hash_pin(new_pin)
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute(
            """
            UPDATE users
            SET pin_hash = %s,
                pin_set_at = NOW(),
                pin_attempts_count = 0,
                pin_locked_until = NULL
            WHERE username = %s AND deleted_at IS NULL
            """,
            (pin_hash, username),
        )
        conn.commit()
        if c.rowcount != 1:
            return False, "Utilisateur introuvable"
        return True, ""
    except Exception as e:
        logger.error("[Admin PIN] set_pin error: %s", str(e)[:200])
        try:
            if conn:
                conn.rollback()
        except Exception:
            pass
        return False, "Erreur lors de la configuration du PIN"
    finally:
        if conn:
            conn.close()


def fetch_pin_state(username: str) -> Optional[dict]:
    """Lit l etat PIN d un user en DB.

    Returns {pin_hash, attempts, locked_until, set_at} ou None.
    """
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute(
            """
            SELECT pin_hash, COALESCE(pin_attempts_count, 0), pin_locked_until, pin_set_at
            FROM users WHERE username = %s AND deleted_at IS NULL
            """,
            (username,),
        )
        row = c.fetchone()
        if not row:
            return None
        return {
            "pin_hash": row[0],
            "attempts": row[1],
            "locked_until": row[2],
            "set_at": row[3],
        }
    except Exception as e:
        logger.error("[Admin PIN] fetch_pin_state error: %s", str(e)[:200])
        return None
    finally:
        if conn:
            conn.close()


def is_pin_locked(username: str) -> Tuple[bool, Optional[int]]:
    """Renvoie (locked: bool, seconds_remaining: int|None).

    Locked = blocage temporaire OU 3 essais atteints (necessite 2FA pour debloquer).
    """
    state = fetch_pin_state(username)
    if not state:
        return False, None

    locked_until = state["locked_until"]
    if locked_until:
        now = datetime.utcnow()
        if locked_until > now:
            remaining = int((locked_until - now).total_seconds())
            return True, remaining

    if state["attempts"] >= PIN_MAX_ATTEMPTS:
        return True, None  # locked indefiniment jusqu a deblocage 2FA

    return False, None


def record_pin_failure(username: str) -> dict:
    """Incrémente le compteur d'echecs et retourne l etat resultant.

    Returns {attempts, max_reached, locked_seconds}.
    Si attempts atteint PIN_MAX_ATTEMPTS, on pose pin_locked_until = NOW + 5min.
    """
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute(
            """
            UPDATE users
            SET pin_attempts_count = COALESCE(pin_attempts_count, 0) + 1,
                pin_locked_until = CASE
                    WHEN COALESCE(pin_attempts_count, 0) + 1 >= %s
                    THEN NOW() + INTERVAL '%s seconds'
                    ELSE pin_locked_until
                END
            WHERE username = %s AND deleted_at IS NULL
            RETURNING pin_attempts_count, pin_locked_until
            """,
            (PIN_MAX_ATTEMPTS, PIN_LOCKOUT_SECONDS, username),
        )
        row = c.fetchone()
        conn.commit()
        if not row:
            return {"attempts": 0, "max_reached": False, "locked_seconds": None}
        attempts = row[0]
        return {
            "attempts": attempts,
            "max_reached": attempts >= PIN_MAX_ATTEMPTS,
            "locked_seconds": PIN_LOCKOUT_SECONDS if attempts >= PIN_MAX_ATTEMPTS else None,
        }
    except Exception as e:
        logger.error("[Admin PIN] record_pin_failure error: %s", str(e)[:200])
        try:
            if conn:
                conn.rollback()
        except Exception:
            pass
        return {"attempts": 0, "max_reached": False, "locked_seconds": None}
    finally:
        if conn:
            conn.close()


def clear_pin_lockout(username: str) -> bool:
    """Reset les compteurs PIN. Appele apres un debloquage par 2FA reussie."""
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute(
            """
            UPDATE users
            SET pin_attempts_count = 0, pin_locked_until = NULL
            WHERE username = %s AND deleted_at IS NULL
            """,
            (username,),
        )
        conn.commit()
        return c.rowcount == 1
    except Exception as e:
        logger.error("[Admin PIN] clear_pin_lockout error: %s", str(e)[:200])
        try:
            if conn:
                conn.rollback()
        except Exception:
            pass
        return False
    finally:
        if conn:
            conn.close()


# ─── SESSION HELPERS ───────────────────────────────────────────────────


def mark_pin_validated(request) -> None:
    """Pose le timestamp de validation PIN dans la session.

    Different de admin_2fa_validated_at : le PIN est valide tant que la
    fenetre est ouverte. La session FastAPI starlette est detruite a la
    fermeture du navigateur (cookie de session sans max_age explicite,
    ou max_age 24h pour Raya).
    """
    request.session["admin_pin_validated_at"] = time.time()


def is_pin_validated_in_session(request) -> bool:
    """True si le PIN a ete valide dans la fenetre courante.

    On stocke juste le timestamp (sans expiration courte) car la session
    elle-meme expire avec la fenetre. Si on voulait re-demander tous les X
    minutes meme dans la meme fenetre, on ajouterait une comparaison ici.
    """
    return bool(request.session.get("admin_pin_validated_at"))


def clear_pin_session(request) -> None:
    """Efface la validation PIN de la session (force re-saisie au prochain acces)."""
    request.session.pop("admin_pin_validated_at", None)


# ─── VERIFICATION (LOGIQUE PRINCIPALE) ─────────────────────────────────


def verify_pin(username: str, pin: str) -> Tuple[bool, str, dict]:
    """Tente de valider un PIN candidat.

    Returns (success: bool, error_message: str, state: dict)
    state contient : {attempts, max_reached, locked_seconds}

    Logique :
    1. Si PIN bloque (locked_until ou max_attempts) -> echec direct
    2. Hash le PIN candidat, compare au pin_hash stocke
    3. Si OK -> reset compteurs, return True
    4. Si KO -> increment compteur, return False avec etat
    """
    # Verif blocage actuel
    locked, seconds = is_pin_locked(username)
    if locked:
        if seconds is not None:
            return False, f"PIN bloque temporairement. Reessayez dans {seconds // 60 + 1} min.", {"locked_seconds": seconds}
        return False, "PIN bloque apres trop d echecs. Authentification 2FA requise pour debloquer.", {"max_reached": True}

    # Lire le hash stocke
    state = fetch_pin_state(username)
    if not state or not state["pin_hash"]:
        return False, "PIN non configure. Configurez-le via les parametres 2FA.", {}

    # Comparer
    if verify_pin_hash(pin, state["pin_hash"]):
        # Succes : reset compteurs
        clear_pin_lockout(username)
        return True, "", {"attempts": 0}

    # Echec : incrementer + verifier blocage
    new_state = record_pin_failure(username)
    if new_state.get("max_reached"):
        return False, "Trop d essais rates. Le PIN est bloque. Validez votre 2FA pour debloquer.", new_state

    remaining = PIN_MAX_ATTEMPTS - new_state.get("attempts", 0)
    return False, f"PIN incorrect. {remaining} essai(s) restant(s).", new_state
