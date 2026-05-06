"""
Gestion des abonnements Microsoft Graph webhooks pour la boîte mail.

- Création d'abonnements par utilisateur
- Renouvellement automatique avant expiration (toutes les 6h)
- Recréation si abonnement révoqué
- Alerte email si token Microsoft révoqué
"""
import os
import secrets
from datetime import datetime, timezone, timedelta
import requests

from app.database import get_pg_conn

GRAPH_BASE = "https://graph.microsoft.com/v1.0"
SUBSCRIPTION_DAYS = 3  # Max autorisé par Microsoft Graph pour les mails


def get_notification_url() -> str:
    base = os.getenv("APP_BASE_URL", "https://couffrant-assistant-production.up.railway.app")
    return f"{base}/webhook/microsoft"


def get_lifecycle_notification_url() -> str:
    """URL endpoint pour les Lifecycle Notifications Microsoft Graph.
    
    Phase Connexions Universelles - Etape 3.5 (1er mai 2026).
    Microsoft envoie sur cet URL des evenements speciaux (subscriptionRemoved,
    missed, reauthorizationRequired) qui permettent de reagir avant que la
    subscription ne meurt silencieusement.
    
    AURAIT EVITE LE BUG 17 JOURS du 14/04 au 01/05.
    """
    base = os.getenv("APP_BASE_URL", "https://couffrant-assistant-production.up.railway.app")
    return f"{base}/webhook/microsoft/lifecycle"


def create_subscription(token: str, username: str,
                        connection_id: int | None = None) -> dict | None:
    """Cree un abonnement Graph pour la boite inbox d'un utilisateur.

    Multi-boites 28/04 : connection_id optionnel pour lier l abonnement a
    une connexion specifique (utile quand l user a plusieurs boites Outlook).
    
    Lifecycle Notifications (Etape 3.5, 01/05) : on ajoute lifecycleNotificationUrl
    pour recevoir les evenements speciaux (subscriptionRemoved, missed,
    reauthorizationRequired). Le bug 17 jours d avril aurait ete evite avec ca.
    """
    expiry = (datetime.now(timezone.utc) + timedelta(days=SUBSCRIPTION_DAYS)).strftime("%Y-%m-%dT%H:%M:%SZ")
    client_state = secrets.token_hex(16)
    r = requests.post(
        f"{GRAPH_BASE}/subscriptions",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={
            "changeType": "created",
            "notificationUrl": get_notification_url(),
            "lifecycleNotificationUrl": get_lifecycle_notification_url(),
            "resource": "me/mailFolders/inbox/messages",
            "expirationDateTime": expiry,
            "clientState": client_state,
        },
        timeout=15,
    )
    if r.status_code in (200, 201):
        data = r.json()
        _save_subscription(username, data["id"], data["expirationDateTime"],
                           client_state, connection_id=connection_id)
        print(f"[Webhook] Abonnement créé pour {username} (conn#{connection_id}): {data['id']} (avec lifecycle)")
        return data
    print(f"[Webhook] Erreur création {username} (conn#{connection_id}): {r.status_code} {r.text[:200]}")
    if r.status_code in (401, 403):
        _send_revoked_alert(username)
    return None


def renew_subscription(token: str, subscription_id: str, username: str) -> bool:
    """Renouvelle un abonnement avant expiration."""
    expiry = (datetime.now(timezone.utc) + timedelta(days=SUBSCRIPTION_DAYS)).strftime("%Y-%m-%dT%H:%M:%SZ")
    r = requests.patch(
        f"{GRAPH_BASE}/subscriptions/{subscription_id}",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={"expirationDateTime": expiry},
        timeout=15,
    )
    if r.status_code == 200:
        _update_subscription_expiry(subscription_id, r.json()["expirationDateTime"])
        print(f"[Webhook] Abonnement renouvelé pour {username}: {subscription_id}")
        return True
    print(f"[Webhook] Erreur renouvellement {username}: {r.status_code} {r.text[:200]}")
    _delete_subscription_from_db(subscription_id)
    if r.status_code in (401, 403):
        _send_revoked_alert(username)
    return False


def delete_subscription(token: str, subscription_id: str) -> bool:
    r = requests.delete(
        f"{GRAPH_BASE}/subscriptions/{subscription_id}",
        headers={"Authorization": f"Bearer {token}"},
        timeout=10,
    )
    _delete_subscription_from_db(subscription_id)
    return r.status_code == 204


# ─── DB ───

def _save_subscription(username: str, subscription_id: str, expires_at: str,
                       client_state: str, connection_id: int | None = None):
    conn = None
    try:
        conn = get_pg_conn(); c = conn.cursor()
        expires_dt = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
        c.execute("""
            INSERT INTO webhook_subscriptions (username, subscription_id, resource, expires_at, client_state, connection_id)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (subscription_id) DO UPDATE SET expires_at=EXCLUDED.expires_at, updated_at=NOW(),
                                                         connection_id=COALESCE(EXCLUDED.connection_id, webhook_subscriptions.connection_id)
        """, (username, subscription_id, "me/mailFolders/inbox/messages", expires_dt, client_state, connection_id))
        conn.commit()
    finally:
        if conn: conn.close()


def _update_subscription_expiry(subscription_id: str, expires_at: str):
    conn = None
    try:
        conn = get_pg_conn(); c = conn.cursor()
        expires_dt = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
        c.execute("UPDATE webhook_subscriptions SET expires_at=%s, updated_at=NOW() WHERE subscription_id=%s",
                  (expires_dt, subscription_id))
        conn.commit()
    finally:
        if conn: conn.close()


def _delete_subscription_from_db(subscription_id: str):
    conn = None
    try:
        conn = get_pg_conn(); c = conn.cursor()
        c.execute("DELETE FROM webhook_subscriptions WHERE subscription_id=%s", (subscription_id,))
        conn.commit()
    finally:
        if conn: conn.close()


def get_subscriptions_for_user(username: str) -> list:
    conn = None
    try:
        conn = get_pg_conn(); c = conn.cursor()
        c.execute("SELECT subscription_id, expires_at, client_state, connection_id "
                  "FROM webhook_subscriptions WHERE username=%s",
                  (username,))
        return [{"subscription_id": r[0], "expires_at": r[1],
                 "client_state": r[2], "connection_id": r[3]}
                for r in c.fetchall()]
    except Exception:
        return []
    finally:
        if conn: conn.close()


def get_subscription_info(subscription_id: str) -> dict | None:
    """Retourne les infos d une subscription Microsoft Graph.
    
    Utilise par le webhook handler pour valider le clientState et router
    la notification vers le bon user.
    
    Etape 3.6 (01/05/2026) : ajout de connection_id au retour pour permettre
    au webhook trigger mode de declencher un poll delta sur la bonne connexion.
    """
    conn = None
    try:
        conn = get_pg_conn(); c = conn.cursor()
        c.execute("SELECT client_state, username, connection_id "
                  "FROM webhook_subscriptions WHERE subscription_id=%s",
                  (subscription_id,))
        row = c.fetchone()
        return {
            "client_state": row[0],
            "username": row[1],
            "connection_id": row[2],
        } if row else None
    except Exception:
        return None
    finally:
        if conn: conn.close()


# ─── ENSURE ALL ───

def ensure_all_subscriptions():
    """
    Appele au demarrage et toutes les 6h.
    Multi-boites 28/04 : pour chaque utilisateur, on itere sur TOUTES ses
    connexions Microsoft/Outlook (via get_all_user_connections) et on
    s assure qu UN abonnement par connexion existe et est valide.

    Pour chaque (user, connexion microsoft active) :
    - Cree l abonnement s il n existe pas pour cette connexion specifique
    - Renouvelle si expiration < 24h
    - Recree si renouvellement echoue
    """
    from app.connection_token_manager import (
        get_all_users_with_tool_connections,
        get_all_user_connections,
        get_connection_token,
    )
    now = datetime.now(timezone.utc)

    try:
        # Fix 06/05/2026 : on cherche aussi les users qui n auraient que des
        # connexions 'outlook' (sans 'microsoft'). Avant, ils etaient ignores.
        users_ms = set(get_all_users_with_tool_connections("microsoft") or [])
        users_outlook = set(get_all_users_with_tool_connections("outlook") or [])
        users = sorted(users_ms | users_outlook)
    except Exception as e:
        print(f"[Webhook] Erreur récupération users V2: {e}")
        return

    for username in users:
        try:
            # Recupere TOUTES les connexions de l user, filtre microsoft/outlook
            all_conns = get_all_user_connections(username)
            ms_conns = [c for c in all_conns
                        if c.get("tool_type", "").lower() in ("microsoft", "outlook")
                        and c.get("token")]
            if not ms_conns:
                continue
            existing_subs = get_subscriptions_for_user(username)
            # Index des subs par connection_id pour lookup rapide
            subs_by_conn = {s["connection_id"]: s for s in existing_subs
                            if s.get("connection_id") is not None}
            # Subs sans connection_id : on les considere comme orphelins
            orphan_subs = [s for s in existing_subs if s.get("connection_id") is None]

            for conn_info in ms_conns:
                conn_id = conn_info["connection_id"]
                # Fix 06/05/2026 : on prend un token FRAIS via
                # get_connection_token (qui refresh automatiquement si
                # expire). Avant : on prenait c.get('token') brut depuis
                # get_all_user_connections, qui retournait le token
                # decrypted mais potentiellement expire (1h). Resultat :
                # creation de sub plantait avec 401 InvalidAuthenticationToken.
                # Bug visible sur conn=14 contact@ ce matin (token expire
                # 28 min apres reconnexion -> sub jamais creee).
                tool_type_lower = conn_info.get("tool_type", "").lower()
                email = conn_info.get("email", "?")
                fresh_token = get_connection_token(
                    username=username,
                    tool_type=tool_type_lower,
                    email_hint=email if email and email != "?" else None,
                )
                # Fallback sur le token brut si le refresh echoue (mieux
                # que pas de token du tout, mais peu probable de marcher)
                token = fresh_token or conn_info["token"]
                try:
                    sub = subs_by_conn.get(conn_id)
                    if not sub and orphan_subs:
                        # Adopter un orphelin existant pour cette connexion
                        # (cas typique apres la migration M-W02 : la ligne
                        # existante avait connection_id rempli par backfill)
                        sub = None  # le backfill aura deja matche, sinon on cree
                    if not sub:
                        create_subscription(token, username, connection_id=conn_id)
                    else:
                        expires_at = sub["expires_at"]
                        if expires_at.tzinfo is None:
                            expires_at = expires_at.replace(tzinfo=timezone.utc)
                        hours_left = (expires_at - now).total_seconds() / 3600
                        if hours_left < 24:
                            ok = renew_subscription(
                                token, sub["subscription_id"], username)
                            if not ok:
                                create_subscription(
                                    token, username, connection_id=conn_id)
                except Exception as e:
                    print(f"[Webhook] Erreur ensure {username}/{email}: {e}")
        except Exception as e:
            print(f"[Webhook] Erreur ensure user {username}: {e}")


# ─── ALERTE TOKEN RÉVOQUÉ ───

def _send_revoked_alert(username: str):
    """Envoie un email d'alerte quand le token Microsoft est révoqué."""
    try:
        conn = get_pg_conn(); c = conn.cursor()
        c.execute("SELECT email FROM users WHERE username=%s", (username,))
        row = c.fetchone(); conn.close()
        user_email = row[0] if row else None

        smtp_host = os.getenv("SMTP_HOST")
        smtp_port = int(os.getenv("SMTP_PORT", "587"))
        smtp_user = os.getenv("SMTP_USER")
        smtp_pass = os.getenv("SMTP_PASS")
        smtp_from = os.getenv("SMTP_FROM", smtp_user or "noreply@raya-app.fr")
        admin_email = os.getenv("APP_ADMIN_EMAIL", user_email)

        if not smtp_host or not smtp_user or not smtp_pass or not admin_email:
            print(f"[Webhook] ALERTE : token révoqué pour {username} — SMTP non configuré")
            return

        import smtplib
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"\u26a0\ufe0f Raya — Token Microsoft révoqué ({username})"
        msg["From"] = smtp_from
        msg["To"] = admin_email
        base_url = os.getenv("APP_BASE_URL", "")
        html = f"""<p>Bonjour,</p>
<p>Le token Microsoft 365 de l'utilisateur <strong>{username}</strong> a été révoqué ou est invalide.</p>
<p>Raya ne peut plus recevoir les nouveaux mails de cette boîte.</p>
<p><strong>Action requise :</strong> reconnectez le compte Microsoft en allant sur
<a href="{base_url}/login">{base_url}/login</a>.</p>
<p>— Raya</p>"""
        msg.attach(MIMEText(html, "html"))
        with smtplib.SMTP(smtp_host, smtp_port) as s:
            s.starttls(); s.login(smtp_user, smtp_pass)
            s.sendmail(smtp_from, admin_email, msg.as_string())
        print(f"[Webhook] Alerte token révoqué envoyée pour {username}")
    except Exception as e:
        print(f"[Webhook] Erreur envoi alerte: {e}")
