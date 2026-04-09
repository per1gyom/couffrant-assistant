"""
Auth : hachage, vérification, rate limiting progressif, validation MDP robuste.

Logique de blocage par username :
  Round 1 : 3 échecs → 5 min
  Round 2 : 3 échecs → 30 min
  Round 3 : 3 échecs → BLOCAGE DÉFINITIF en DB + alerte admin

Rate limiting par IP :
  5 tentatives rapides → 15 min (anti-bot)
"""
import hashlib
import hmac
import os
import re
import base64
import time

_ip_attempts: dict = {}    # {ip: {count, locked_until}}
_user_attempts: dict = {}  # {username_lower: {count, round, locked_until}}

_LOCKOUT_ROUNDS = [
    (3, 5 * 60),   # Round 1 : 3 échecs → 5 min
    (3, 30 * 60),  # Round 2 : 3 échecs → 30 min
    (3, None),     # Round 3 : 3 échecs → PERMANENT
]


# ─── VALIDATION MDP ───

def validate_password_strength(password: str) -> tuple:
    """
    Vérifie la robustesse d'un mot de passe.
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
    """Vérifie si l'IP est temporairement bloquée."""
    now = time.time()
    data = _ip_attempts.get(ip, {})
    if data.get("locked_until", 0) > now:
        remaining = int((data["locked_until"] - now) / 60) + 1
        return False, f"Trop de tentatives depuis cette adresse. Réessayez dans {remaining} min."
    return True, ""


def record_failed_attempt(ip: str):
    """Incrémente le compteur IP. Alias backward-compat."""
    now = time.time()
    data = _ip_attempts.setdefault(ip, {"count": 0})
    data["count"] = data.get("count", 0) + 1
    if data["count"] >= 5:
        data["locked_until"] = now + 15 * 60
        data["count"] = 0


def clear_attempts(ip: str):
    _ip_attempts.pop(ip, None)


# ─── RATE LIMITING PAR USERNAME (progressif + blocage définitif) ───

def check_user_lockout(username: str) -> tuple:
    """
    Vérifie si le compte est verrouillé (en mémoire ou en DB).
    Retourne (ok: bool, message: str, permanent: bool)
    """
    if is_account_locked_db(username):
        return False, "Compte bloqué suite à trop de tentatives. Contactez votre administrateur.", True
    now = time.time()
    data = _user_attempts.get(username.lower(), {})
    locked_until = data.get("locked_until", 0)
    if locked_until > now:
        remaining = int((locked_until - now) / 60) + 1
        return False, f"Compte temporairement verrouillé. Réessayez dans {remaining} minute(s).", False
    return True, "", False


def record_user_failed(username: str, ip: str = "") -> dict:
    """
    Enregistre un échec de connexion pour ce username.
    Applique le blocage progressif et déclenche le blocage définitif au round 3.
    Retourne {blocked, permanent, minutes?}
    """
    now = time.time()
    key = username.lower()
    data = _user_attempts.setdefault(key, {"count": 0, "round": 0})
    data["count"] = data.get("count", 0) + 1
    current_round = data.get("round", 0)

    if current_round < len(_LOCKOUT_ROUNDS):
        threshold, duration = _LOCKOUT_ROUNDS[current_round]
        if data["count"] >= threshold:
            data["count"] = 0
            data["round"] = current_round + 1
            if duration is None:
                data["permanent"] = True
                _lock_account_db(username)
                _alert_admin_locked(username, ip)
                return {"blocked": True, "permanent": True}
            else:
                data["locked_until"] = now + duration
                return {"blocked": True, "permanent": False, "minutes": duration // 60}

    return {"blocked": False}


def clear_user_attempts(username: str):
    _user_attempts.pop(username.lower(), None)


# ─── COMPTE EN BASE ───

def is_account_locked_db(username: str) -> bool:
    """Vérifie le verrouillage définitif en DB."""
    try:
        from app.database import get_pg_conn
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("SELECT account_locked FROM users WHERE username=%s", (username,))
        row = c.fetchone()
        conn.close()
        return bool(row[0]) if row else False
    except Exception:
        return False


def _lock_account_db(username: str):
    try:
        from app.database import get_pg_conn
        conn = get_pg_conn(); c = conn.cursor()
        c.execute("UPDATE users SET account_locked=true WHERE username=%s", (username,))
        conn.commit(); conn.close()
    except Exception as e:
        print(f"[Auth] Erreur lock DB: {e}")


def unlock_account(username: str) -> dict:
    """Déverrouille un compte (action admin uniquement)."""
    try:
        from app.database import get_pg_conn
        conn = get_pg_conn(); c = conn.cursor()
        c.execute("UPDATE users SET account_locked=false WHERE username=%s", (username,))
        conn.commit(); conn.close()
        clear_user_attempts(username)
        return {"status": "ok", "message": f"Compte '{username}' déverrouillé."}
    except Exception as e:
        return {"status": "error", "message": str(e)[:100]}


# ─── ALERTE ADMIN ───

def _alert_admin_locked(username: str, ip: str = ""):
    """Envoie un email à l'admin du tenant quand un compte est définitivement bloqué."""
    try:
        from app.database import get_pg_conn
        conn = get_pg_conn(); c = conn.cursor()
        c.execute("""
            SELECT u2.email FROM users u1
            JOIN users u2 ON u2.tenant_id = u1.tenant_id
            WHERE u1.username = %s
              AND u2.scope IN ('admin', 'tenant_admin')
              AND u2.email IS NOT NULL
            ORDER BY CASE u2.scope WHEN 'admin' THEN 0 ELSE 1 END
            LIMIT 1
        """, (username,))
        row = c.fetchone()
        conn.close()
        admin_email = row[0] if row else os.getenv("APP_ADMIN_EMAIL", "")
        if not admin_email:
            print(f"[Auth] Blocage {username} — aucun email admin trouvé")
            return
        base_url = os.getenv("APP_BASE_URL", "https://couffrant-assistant-production.up.railway.app")
        subject = f"⚠️ Compte Raya bloqué : {username}"
        body = f"""
<div style="font-family:sans-serif;max-width:560px;color:#111">
  <h2 style="color:#dc2626">⚠️ Alerte sécurité Raya</h2>
  <p>Le compte <strong>{username}</strong> a été <strong>bloqué définitivement</strong>
  après 9 tentatives de connexion échouées consécutives.</p>
  <table style="border:1px solid #e5e7eb;border-radius:8px;padding:12px 16px;
    margin:16px 0;width:100%;border-spacing:0">
    <tr><td style="color:#6b7280;font-size:13px;padding:4px 8px">Compte :</td>
        <td style="padding:4px 8px"><strong>{username}</strong></td></tr>
    <tr><td style="color:#6b7280;font-size:13px;padding:4px 8px">IP :</td>
        <td style="padding:4px 8px"><code>{ip or 'inconnue'}</code></td></tr>
  </table>
  <p>Pour débloquer ce compte après vérification :</p>
  <p><a href="{base_url}/admin/panel" style="background:#6366f1;color:#fff;
     padding:10px 20px;border-radius:8px;text-decoration:none;display:inline-block"
  >Ouvrir le panel admin</a></p>
  <p style="font-size:12px;color:#6b7280;margin-top:16px"><em>
  Si la tentative n'est pas de l'utilisateur lui-même, générez un nouveau mot de passe
  avant de débloquer.</em></p>
</div>"""
        _send_email(admin_email, subject, body)
    except Exception as e:
        print(f"[Auth] Erreur alerte admin: {e}")


def _send_email(to: str, subject: str, html: str) -> bool:
    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart
    smtp_host = os.getenv("SMTP_HOST")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER")
    smtp_pass = os.getenv("SMTP_PASS")
    smtp_from = os.getenv("SMTP_FROM", smtp_user or "noreply@raya-ia.fr")
    if not smtp_host or not smtp_user or not smtp_pass:
        print(f"[Auth] SMTP non configuré — email non envoyé à {to}")
        return False
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = smtp_from
        msg["To"] = to
        msg.attach(MIMEText(html, "html"))
        with smtplib.SMTP(smtp_host, smtp_port) as s:
            s.starttls(); s.login(smtp_user, smtp_pass)
            s.sendmail(smtp_from, to, msg.as_string())
        return True
    except Exception as e:
        print(f"[Auth] Erreur SMTP: {e}")
        return False


# ─── HACHAGE MDP ───

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
