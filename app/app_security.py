import hashlib
import hmac
import os
import base64
import time
from app.database import get_pg_conn

# ── Rate limiting en mémoire ──
_login_attempts: dict = {}  # {ip: {"count": int, "locked_until": float}}
MAX_ATTEMPTS = 5
LOCKOUT_SECONDS = 15 * 60  # 15 minutes


def check_rate_limit(ip: str) -> tuple[bool, str]:
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
        print(f"[Auth] IP {ip} bloquée pour {LOCKOUT_SECONDS//60} minutes.")


def clear_attempts(ip: str):
    _login_attempts.pop(ip, None)


# ── Hachage de mot de passe (PBKDF2-SHA256, stdlib uniquement) ──

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


# ── Gestion des utilisateurs ──

def init_default_user():
    """
    Crée l'utilisateur admin par défaut (Guillaume) depuis les env vars.
    scope='admin' = accès complet à tous les contextes.
    """
    username = os.getenv("APP_USERNAME", "guillaume").strip()
    password = os.getenv("APP_PASSWORD", "couffrant2026").strip()

    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM users")
        if c.fetchone()[0] == 0:
            password_hash = hash_password(password)
            c.execute("""
                INSERT INTO users (username, password_hash, scope)
                VALUES (%s, %s, 'admin')
                ON CONFLICT (username) DO NOTHING
            """, (username, password_hash))
            conn.commit()
            print(f"[Auth] Utilisateur admin créé : {username}")
        else:
            # Met à jour le scope admin si l'utilisateur existe déjà sans scope
            c.execute("""
                UPDATE users SET scope = 'admin'
                WHERE username = %s AND (scope IS NULL OR scope = 'couffrant_solar')
                AND username = %s
            """, (username, username))
            conn.commit()
    except Exception as e:
        print(f"[Auth] Erreur init_default_user: {e}")
    finally:
        if conn:
            conn.close()


def authenticate(username: str, password: str) -> bool:
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("SELECT password_hash FROM users WHERE username = %s", (username.strip(),))
        row = c.fetchone()
        if not row:
            return False
        return verify_password(password, row[0])
    except Exception as e:
        print(f"[Auth] Erreur authenticate: {e}")
        return False
    finally:
        if conn:
            conn.close()


def get_user_scope(username: str) -> str:
    """
    Retourne le scope de l'utilisateur.
    'admin'           = Guillaume, accès complet
    'couffrant_solar' = collègue, Couffrant Solar uniquement
    """
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("SELECT scope FROM users WHERE username = %s", (username.strip(),))
        row = c.fetchone()
        return row[0] if row and row[0] else 'couffrant_solar'
    except Exception:
        return 'couffrant_solar'
    finally:
        if conn:
            conn.close()


def create_user(username: str, password: str, scope: str = 'couffrant_solar') -> dict:
    """
    Crée un nouvel utilisateur.
    scope = 'couffrant_solar' pour les collègues (défaut).
    """
    if not username or not password:
        return {"error": "Identifiant et mot de passe requis"}
    if scope not in ('admin', 'couffrant_solar', 'sci_gaucherie', 'sci_romagui', 'sas_gplh', 'holding'):
        return {"error": f"Scope invalide : {scope}"}
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("SELECT 1 FROM users WHERE username = %s", (username.strip(),))
        if c.fetchone():
            return {"error": f"L'utilisateur '{username}' existe déjà"}
        password_hash = hash_password(password)
        c.execute("""
            INSERT INTO users (username, password_hash, scope)
            VALUES (%s, %s, %s)
        """, (username.strip(), password_hash, scope))
        conn.commit()
        return {"status": "ok", "username": username.strip(), "scope": scope}
    except Exception as e:
        return {"error": str(e)[:200]}
    finally:
        if conn:
            conn.close()


def delete_user(username: str) -> dict:
    """Supprime un utilisateur (protection : impossible de supprimer un admin)."""
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("SELECT scope FROM users WHERE username = %s", (username.strip(),))
        row = c.fetchone()
        if not row:
            return {"error": "Utilisateur introuvable"}
        if row[0] == 'admin':
            return {"error": "Impossible de supprimer un compte admin"}
        c.execute("DELETE FROM users WHERE username = %s", (username.strip(),))
        conn.commit()
        return {"status": "ok", "deleted": username.strip()}
    except Exception as e:
        return {"error": str(e)[:200]}
    finally:
        if conn:
            conn.close()


def list_users() -> list:
    """Liste tous les utilisateurs (sans les hash de mots de passe)."""
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("SELECT username, scope, last_login, created_at FROM users ORDER BY created_at")
        rows = c.fetchall()
        return [{"username": r[0], "scope": r[1], "last_login": str(r[2]) if r[2] else None, "created_at": str(r[3])} for r in rows]
    except Exception:
        return []
    finally:
        if conn:
            conn.close()


def update_last_login(username: str):
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("UPDATE users SET last_login = NOW() WHERE username = %s", (username,))
        conn.commit()
    except Exception:
        pass
    finally:
        if conn:
            conn.close()


def get_current_user(request) -> str | None:
    return request.session.get("user")


LOGIN_PAGE_HTML = """
<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Aria — Connexion</title>
<style>
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{
    background: #0a0a0a;
    color: #fff;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif;
    display: flex;
    align-items: center;
    justify-content: center;
    min-height: 100vh;
}}
.card {{
    background: #111;
    border: 1px solid #1e1e1e;
    border-radius: 16px;
    padding: 40px;
    width: 100%;
    max-width: 380px;
    box-shadow: 0 8px 32px rgba(0,0,0,0.5);
}}
.logo {{ font-size: 32px; margin-bottom: 12px; }}
h1 {{ font-size: 24px; color: #e8e8e8; margin-bottom: 4px; font-weight: 700; }}
.subtitle {{ font-size: 13px; color: #555; margin-bottom: 36px; }}
label {{ font-size: 11px; color: #666; text-transform: uppercase; letter-spacing: 0.8px; display: block; }}
input[type=text], input[type=password] {{
    width: 100%;
    padding: 13px 16px;
    background: #161616;
    border: 1px solid #2a2a2a;
    border-radius: 10px;
    color: #e8e8e8;
    font-size: 15px;
    margin: 8px 0 22px;
    outline: none;
    transition: border-color 0.2s;
}}
input:focus {{ border-color: #1565c0; background: #1a1a1a; }}
button {{
    width: 100%;
    padding: 14px;
    background: #1565c0;
    color: white;
    border: none;
    border-radius: 10px;
    font-size: 15px;
    font-weight: 600;
    cursor: pointer;
    transition: background 0.15s;
    letter-spacing: 0.3px;
}}
button:hover {{ background: #1976d2; }}
.error {{
    background: rgba(220,50,50,0.1);
    border: 1px solid rgba(220,50,50,0.3);
    color: #ff7070;
    padding: 12px 16px;
    border-radius: 8px;
    font-size: 13px;
    margin-bottom: 24px;
    text-align: center;
}}
</style>
</head>
<body>
<div class="card">
    <div class="logo">⚡</div>
    <h1>Aria</h1>
    <div class="subtitle">Couffrant Solar — Accès privé</div>
    {error_block}
    <form method="post" action="/login-app">
        <label>Identifiant</label>
        <input type="text" name="username" autocomplete="username" placeholder="Identifiant" required>
        <label>Mot de passe</label>
        <input type="password" name="password" autocomplete="current-password" placeholder="Mot de passe" required>
        <button type="submit">Se connecter →</button>
    </form>
</div>
</body>
</html>
"""
