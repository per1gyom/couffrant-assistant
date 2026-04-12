"""
CRUD des alertes proactives de Raya.
Permet de creer, lister, marquer vues et nettoyer les alertes.
"""
from app.database import get_pg_conn


def create_alert(
    username: str,
    tenant_id: str,
    alert_type: str,
    priority: str,
    title: str,
    body: str = "",
    source_type: str = None,
    source_id: str = None,
) -> int:
    """
    Insere une alerte proactive.
    Deduplique par (username, source_id) sur les 24 dernieres heures.
    Retourne l'id de l'alerte inseree ou 0 si doublon.
    """
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        if source_id:
            c.execute("""
                SELECT id FROM proactive_alerts
                WHERE username = %s AND source_id = %s
                  AND created_at > NOW() - INTERVAL '24 hours'
                LIMIT 1
            """, (username, source_id))
            if c.fetchone():
                return 0
        c.execute("""
            INSERT INTO proactive_alerts
              (username, tenant_id, alert_type, priority, title, body, source_type, source_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (username, tenant_id, alert_type, priority, title, body or "",
               source_type, source_id))
        alert_id = c.fetchone()[0]
        conn.commit()

        # 5E-5b : notification WhatsApp si alerte haute ou critique
        if priority in ("high", "critical"):
            try:
                _notify_external(username, tenant_id, alert_type, priority, title, body)
            except Exception as e:
                import logging
                logging.getLogger("raya.alerts").error(f"[Alerts] Notif externe echouee: {e}")

        return alert_id
    except Exception as e:
        print(f"[ProactiveAlerts] Erreur create_alert: {e}")
        return 0
    finally:
        if conn: conn.close()


def _notify_external(username, tenant_id, alert_type, priority, title, body):
    """
    Envoie une notification WhatsApp structuree si Twilio est configure.
    7-5 : respect des plages silencieuses et du canal prefere.
    7-3 : messages structures avec options de reponse rapide.
    """
    import os

    # 7-5 : verification des preferences de notification
    try:
        from app.notification_prefs import should_notify
        if not should_notify(username, priority):
            return  # plage silencieuse ou chat_only
    except Exception:
        pass

    phone = os.getenv(f"NOTIFICATION_PHONE_{username.upper()}", "").strip()
    if not phone:
        phone = os.getenv("NOTIFICATION_PHONE_DEFAULT", "").strip()
    if not phone:
        return

    from app.connectors.twilio_connector import send_whatsapp_structured, send_whatsapp, is_available
    if not is_available():
        return

    icon = "\U0001f534" if priority == "critical" else "\U0001f7e0"
    try:
        send_whatsapp_structured(
            to=phone,
            title=f"{icon} Raya \u2014 {alert_type.replace('_', ' ').capitalize()}",
            body=f"{title}\n{body[:300] if body else ''}",
            options=[
                "Oui, g\u00e8re pour moi",
                "Je m'en occupe",
                "Rappelle-moi dans 1h",
                "Ignorer",
            ],
        )
    except Exception:
        # Fallback texte brut si structure echoue
        message = (
            f"{icon} Raya \u2014 Alerte {priority}\n\n"
            f"{title}\n"
            f"{body[:300] if body else ''}\n\n"
            f"Connecte-toi au chat pour agir."
        )
        send_whatsapp(phone, message)


def get_active_alerts(username: str, limit: int = 10) -> list:
    """
    Retourne les alertes non vues, non dismissed, non expirees,
    triees par priority DESC puis created_at DESC.
    """
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            SELECT id, alert_type, priority, title, body, source_type, source_id, created_at
            FROM proactive_alerts
            WHERE username = %s
              AND seen = false
              AND dismissed = false
              AND expires_at > NOW()
            ORDER BY
                CASE priority
                    WHEN 'critical' THEN 0
                    WHEN 'high'     THEN 1
                    WHEN 'normal'   THEN 2
                    WHEN 'low'      THEN 3
                    ELSE 4
                END ASC,
                created_at DESC
            LIMIT %s
        """, (username, limit))
        cols = ["id", "alert_type", "priority", "title", "body",
                "source_type", "source_id", "created_at"]
        return [dict(zip(cols, row)) for row in c.fetchall()]
    except Exception as e:
        print(f"[ProactiveAlerts] Erreur get_active_alerts: {e}")
        return []
    finally:
        if conn: conn.close()


def mark_seen(alert_ids: list, username: str) -> int:
    """Marque les alertes comme vues. Retourne le nombre mis a jour."""
    if not alert_ids:
        return 0
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            UPDATE proactive_alerts
            SET seen = true
            WHERE id = ANY(%s) AND username = %s
        """, (alert_ids, username))
        updated = c.rowcount
        conn.commit()
        return updated
    except Exception as e:
        print(f"[ProactiveAlerts] Erreur mark_seen: {e}")
        return 0
    finally:
        if conn: conn.close()


def dismiss_alert(alert_id: int, username: str) -> bool:
    """Marque une alerte comme dismissed. Retourne True si succes."""
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            UPDATE proactive_alerts
            SET dismissed = true
            WHERE id = %s AND username = %s
        """, (alert_id, username))
        ok = c.rowcount > 0
        conn.commit()
        return ok
    except Exception as e:
        print(f"[ProactiveAlerts] Erreur dismiss_alert: {e}")
        return False
    finally:
        if conn: conn.close()


def cleanup_expired() -> int:
    """Supprime les alertes expirees depuis plus de 7 jours."""
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            DELETE FROM proactive_alerts
            WHERE expires_at < NOW() - INTERVAL '7 days'
        """)
        deleted = c.rowcount
        conn.commit()
        return deleted
    except Exception as e:
        print(f"[ProactiveAlerts] Erreur cleanup_expired: {e}")
        return 0
    finally:
        if conn: conn.close()
