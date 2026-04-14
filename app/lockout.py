"""
Gestion des verrouillages de comptes utilisateur Raya.
Extrait de security_auth.py -- SPLIT-6.
"""
import os
from app.database import get_pg_conn

_user_lockout: dict = {}
MAX_ATTEMPTS = 5
LOCKOUT_MINUTES = [5, 15, 60]


def check_user_lockout(username: str) -> tuple:
    """
    Vérifie si le compte est verrouillé (DB).
    Retourne (ok: bool, message: str, permanent: bool)
    """
    from datetime import datetime, timezone
    try:
        from app.database import get_pg_conn
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute(
            "SELECT account_locked, login_locked_until FROM users WHERE username=%s",
            (username,)
        )
        row = c.fetchone()
        conn.close()
        if not row:
            return True, "", False
        account_locked, locked_until = row
        if account_locked:
            return False, "Compte bloqué suite à trop de tentatives. Contactez votre administrateur.", True
        if locked_until:
            now = datetime.now(timezone.utc)
            if locked_until.tzinfo is None:
                locked_until = locked_until.replace(tzinfo=timezone.utc)
            if locked_until > now:
                remaining = int((locked_until - now).total_seconds() / 60) + 1
                return False, f"Compte temporairement verrouillé. Réessayez dans {remaining} minute(s).", False
    except Exception as e:
        print(f"[Auth] check_user_lockout: {e}")
    return True, "", False



def record_user_failed(username: str, ip: str = "") -> dict:
    """
    Enregistre un échec de connexion en DB.
    Applique le blocage progressif. Retourne {blocked, permanent, minutes?}
    """
    from datetime import datetime, timezone, timedelta
    try:
        from app.database import get_pg_conn
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute(
            "SELECT login_attempts_count, login_attempts_round FROM users WHERE username=%s",
            (username,)
        )
        row = c.fetchone()
        if not row:
            conn.close()
            return {"blocked": False}

        count        = (row[0] or 0) + 1
        current_round = row[1] or 0

        if current_round < len(_LOCKOUT_ROUNDS):
            threshold, duration = _LOCKOUT_ROUNDS[current_round]
            if count >= threshold:
                next_round = current_round + 1
                if duration is None:
                    # BLOCAGE DÉFINITIF
                    c.execute("""
                        UPDATE users SET
                            login_attempts_count=0, login_attempts_round=%s,
                            account_locked=true, login_locked_until=NULL
                        WHERE username=%s
                    """, (next_round, username))
                    conn.commit()
                    conn.close()
                    _alert_admin_locked(username, ip)
                    return {"blocked": True, "permanent": True}
                else:
                    locked_until = datetime.now(timezone.utc) + timedelta(seconds=duration)
                    c.execute("""
                        UPDATE users SET
                            login_attempts_count=0, login_attempts_round=%s,
                            login_locked_until=%s
                        WHERE username=%s
                    """, (next_round, locked_until, username))
                    conn.commit()
                    conn.close()
                    return {"blocked": True, "permanent": False, "minutes": duration // 60}
            else:
                c.execute(
                    "UPDATE users SET login_attempts_count=%s WHERE username=%s",
                    (count, username)
                )
                conn.commit()
        conn.close()
        return {"blocked": False}
    except Exception as e:
        print(f"[Auth] record_user_failed: {e}")
        return {"blocked": False}



def clear_user_attempts(username: str):
    """Remet à zéro les compteurs après connexion réussie."""
    try:
        from app.database import get_pg_conn
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            UPDATE users SET
                login_attempts_count=0,
                login_attempts_round=0,
                login_locked_until=NULL
            WHERE username=%s
        """, (username,))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[Auth] clear_user_attempts: {e}")


# ─── BLOCAGE DÉFINITIF EN BASE ───


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
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("UPDATE users SET account_locked=true WHERE username=%s", (username,))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[Auth] Erreur lock DB: {e}")



def unlock_account(username: str) -> dict:
    """Déverrouille un compte et remet les compteurs à zéro (action admin)."""
    try:
        from app.database import get_pg_conn
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            UPDATE users SET
                account_locked=false,
                login_attempts_count=0,
                login_attempts_round=0,
                login_locked_until=NULL
            WHERE username=%s
        """, (username,))
        conn.commit()
        conn.close()
        return {"status": "ok", "message": f"Compte '{username}' déverrouillé."}
    except Exception as e:
        return {"status": "error", "message": str(e)[:100]}


# ─── ALERTE ADMIN ───


def _alert_admin_locked(username: str, ip: str = ""):
    """Envoie un email à l'admin du tenant quand un compte est définitivement bloqué."""
    try:
        from app.database import get_pg_conn
        conn = get_pg_conn()
        c = conn.cursor()
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
  après 9 tentatives de connexion échouées.</p>
  <table style="border:1px solid #e5e7eb;border-radius:8px;padding:12px 16px;
    margin:16px 0;width:100%;border-spacing:0">
    <tr><td style="color:#6b7280;font-size:13px;padding:4px 8px">Compte :</td>
        <td style="padding:4px 8px"><strong>{username}</strong></td></tr>
    <tr><td style="color:#6b7280;font-size:13px;padding:4px 8px">IP :</td>
        <td style="padding:4px 8px"><code>{ip or 'inconnue'}</code></td></tr>
  </table>
  <p>Pour débloquer après vérification :</p>
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

