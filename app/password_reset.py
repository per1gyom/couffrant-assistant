"""
Réinitialisation de mot de passe : génération, envoi email, validation, consommation.
Extrait de security_users.py — REFACTOR-5.
"""
import os
import secrets
from datetime import datetime, timezone, timedelta
from app.database import get_pg_conn
from app.security_auth import hash_password, validate_password_strength


def generate_reset_token(username: str, ttl_hours: int = 24) -> dict:
    """
    Génère un lien de réinitialisation.
    Active aussi must_reset_password pour forcer la redéfinition à la prochaine connexion.
    """
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(hours=ttl_hours)
    conn = None
    try:
        conn = get_pg_conn(); c = conn.cursor()
        c.execute("UPDATE password_reset_tokens SET used=true WHERE username=%s AND used=false", (username,))
        c.execute("""
            INSERT INTO password_reset_tokens (username, token, expires_at) VALUES (%s, %s, %s)
        """, (username, token, expires_at))
        c.execute("SELECT email FROM users WHERE username=%s", (username,))
        row = c.fetchone()
        user_email = row[0] if row else None
        c.execute("UPDATE users SET must_reset_password=true WHERE username=%s", (username,))
        conn.commit()
    finally:
        if conn: conn.close()

    base_url = os.getenv("APP_BASE_URL", "https://couffrant-assistant-production.up.railway.app")
    reset_url = f"{base_url}/reset-password?token={token}"
    email_sent = False
    if user_email:
        email_sent = _send_reset_email(user_email, username, reset_url)

    return {"status": "ok", "token": token, "reset_url": reset_url,
            "email": user_email, "email_sent": email_sent, "expires_in": f"{ttl_hours}h"}


def _send_reset_email(to_email: str, username: str, reset_url: str) -> bool:
    smtp_host = os.getenv("SMTP_HOST")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER")
    smtp_pass = os.getenv("SMTP_PASS")
    smtp_from = os.getenv("SMTP_FROM", smtp_user or "noreply@raya-ia.fr")
    if not smtp_host or not smtp_user or not smtp_pass:
        return False
    try:
        import smtplib
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart
        msg = MIMEMultipart("alternative")
        msg["Subject"] = "Réinitialisation de votre mot de passe Raya"
        msg["From"] = smtp_from
        msg["To"] = to_email
        html = f"""<p>Bonjour {username},</p>
<p>Voici votre lien de réinitialisation de mot de passe. Il est valable 24h.</p>
<p><a href="{reset_url}">Réinitialiser mon mot de passe</a></p>
<p>Si vous n'avez pas demandé cette réinitialisation, ignorez cet email.</p>"""
        msg.attach(MIMEText(html, "html"))
        with smtplib.SMTP(smtp_host, smtp_port) as s:
            s.starttls(); s.login(smtp_user, smtp_pass)
            s.sendmail(smtp_from, to_email, msg.as_string())
        return True
    except Exception as e:
        print(f"[SMTP] Erreur envoi email: {e}")
        return False


def validate_reset_token(token: str) -> dict | None:
    conn = None
    try:
        conn = get_pg_conn(); c = conn.cursor()
        c.execute("""
            SELECT username, expires_at FROM password_reset_tokens WHERE token=%s AND used=false
        """, (token,))
        row = c.fetchone()
        if not row: return None
        username, expires_at = row
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at < datetime.now(timezone.utc): return None
        c.execute("SELECT email FROM users WHERE username=%s", (username,))
        urow = c.fetchone()
        return {"username": username, "email": urow[0] if urow else None}
    except Exception:
        return None
    finally:
        if conn: conn.close()


def consume_reset_token(token: str, new_password: str) -> dict:
    """Consomme un token de reset. Valide la force du MDP avant de l'enregistrer."""
    ok, msg = validate_password_strength(new_password)
    if not ok:
        return {"status": "error", "message": msg}
    conn = None
    try:
        conn = get_pg_conn(); c = conn.cursor()
        c.execute("""
            SELECT username, expires_at FROM password_reset_tokens
            WHERE token=%s AND used=false FOR UPDATE
        """, (token,))
        row = c.fetchone()
        if not row: return {"status": "error", "message": "Lien invalide ou déjà utilisé."}
        username, expires_at = row
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at < datetime.now(timezone.utc):
            return {"status": "error", "message": "Lien expiré. Demandez-en un nouveau."}
        c.execute("""
            UPDATE users SET password_hash=%s, must_reset_password=false WHERE username=%s
        """, (hash_password(new_password), username))
        c.execute("UPDATE password_reset_tokens SET used=true WHERE token=%s", (token,))
        conn.commit()
        return {"status": "ok", "message": "Mot de passe mis à jour."}
    except Exception as e:
        return {"status": "error", "message": str(e)[:100]}
    finally:
        if conn: conn.close()
