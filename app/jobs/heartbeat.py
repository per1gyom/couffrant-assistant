"""
Job heartbeat matinal — prépare le rapport du jour et envoie un ping. (7-6R)
USER-PHONE : utilise get_user_phone(username) pour la résolution du numéro.
"""
import os
import json
from app.logging_config import get_logger

logger = get_logger("raya.scheduler")


def _job_heartbeat_morning():
    """
    Prépare le rapport matinal (07h00) et envoie un PING léger.
    Le rapport est stocké dans daily_reports — l'utilisateur choisit
    comment le recevoir (chat, vocal, WhatsApp).
    """
    try:
        from app.database import get_pg_conn
        conn = get_pg_conn()
        c = conn.cursor()
        # CROSS-TENANT INTENTIONNEL (etape A.5 part 2 du 26/04) :
        # Ce job tourne en boucle scheduler et traite TOUS les users
        # actifs tous tenants confondus. Le SELECT ne filtre donc
        # volontairement pas par tenant_id. Les fonctions appelees en
        # aval doivent re-resoudre le tenant_id depuis le username.
        # Voir docs/tests_isolation_26avril.md scenario 1.2.
        c.execute("""
            SELECT DISTINCT username FROM aria_memory
            WHERE created_at > NOW() - INTERVAL '7 days'
        """)
        active_users = [r[0] for r in c.fetchall()]
        conn.close()

        prepared = 0
        for username in active_users:
            try:
                _prepare_daily_report(username)
                _send_report_ping(username)
                prepared += 1
            except Exception as e:
                logger.error(f"[Heartbeat] Erreur {username}: {e}")

        logger.info(f"[Heartbeat] {prepared} rapport(s) préparé(s)")
    except Exception as e:
        logger.error(f"[Heartbeat] ERREUR: {e}")


def _prepare_daily_report(username: str):
    """Prépare et stocke le rapport du jour. Ne l'envoie PAS."""
    from app.database import get_pg_conn
    from app.app_security import get_tenant_id

    tenant_id = get_tenant_id(username)
    conn = get_pg_conn()
    c = conn.cursor()
    sections = []

    c.execute("""
        SELECT
          COUNT(*) as total,
          COUNT(*) FILTER (WHERE priority = 'haute') as urgent,
          COUNT(*) FILTER (WHERE priority = 'moyenne') as moyen,
          COUNT(*) FILTER (WHERE needs_reply = 1 AND reply_status = 'pending') as a_repondre
        FROM mail_memory
        WHERE username = %s
          AND (tenant_id = %s OR tenant_id IS NULL)
          AND created_at > NOW() - INTERVAL '12 hours'
    """, (username, tenant_id))
    stats = c.fetchone()
    total = stats[0] or 0
    urgent = stats[1] or 0
    moyen = stats[2] or 0
    a_repondre = stats[3] or 0
    silencieux = max(0, total - urgent - moyen)

    mail_lines = []
    if total > 0:
        mail_lines.append(f"{total} mail(s) :")
        if urgent > 0:    mail_lines.append(f"  \U0001f534 {urgent} urgent(s)")
        if moyen > 0:     mail_lines.append(f"  \U0001f7e1 {moyen} à voir")
        if silencieux > 0: mail_lines.append(f"  \u26aa {silencieux} silencieux")
    else:
        mail_lines.append("Nuit calme, aucun mail notable.")
    if a_repondre > 0:
        mail_lines.append(f"\u2709\ufe0f {a_repondre} réponse(s) en attente")
    sections.append({"type": "mails", "title": "Mails de la nuit", "content": "\n".join(mail_lines)})

    c.execute("""
        SELECT COUNT(*) FROM proactive_alerts
        WHERE username = %s
          AND (tenant_id = %s OR tenant_id IS NULL)
          AND seen = false AND dismissed = false
          AND (expires_at IS NULL OR expires_at > NOW())
    """, (username, tenant_id))
    alerts_count = c.fetchone()[0]
    if alerts_count > 0:
        sections.append({
            "type": "alerts",
            "title": "Alertes",
            "content": f"\u26a0\ufe0f {alerts_count} alerte(s) active(s) à consulter.",
        })

    full_content = "\n\n".join(
        f"\U0001f4cc {s['title']}\n{s['content']}" for s in sections
    )
    full_content = f"\u2600\ufe0f Bonjour ! Raya veille.\n\n{full_content}"

    c.execute("""
        INSERT INTO daily_reports (username, tenant_id, content, sections)
        VALUES (%s, %s, %s, %s::jsonb)
        ON CONFLICT (username, report_date)
        DO UPDATE SET content = EXCLUDED.content,
                      sections = EXCLUDED.sections,
                      created_at = NOW()
    """, (username, tenant_id, full_content, json.dumps(sections, ensure_ascii=False)))
    conn.commit()
    conn.close()


def _send_report_ping(username: str):
    """
    Envoie un PING léger pour prévenir que le rapport est prêt.
    Utilise get_user_phone() pour trouver le numéro en base ou
    dans les variables d'environnement (USER-PHONE).
    """
    try:
        from app.security_users import get_user_phone
        phone = get_user_phone(username)
    except Exception:
        # Fallback direct si security_users non disponible
        phone = os.getenv(f"NOTIFICATION_PHONE_{username.upper()}", "").strip()
        if not phone:
            phone = os.getenv("NOTIFICATION_PHONE_DEFAULT", "").strip()

    if not phone:
        return

    try:
        from app.notification_prefs import should_notify
        if not should_notify(username, "normal"):
            return
    except Exception:
        pass
    try:
        from app.connectors.twilio_connector import send_whatsapp
        send_whatsapp(
            phone,
            "\u2600\ufe0f Raya — Ton rapport matinal est prêt.\n"
            "Dis-moi comment tu veux le recevoir.",
        )
    except Exception as e:
        logger.error(f"[Heartbeat] Ping échoué {username}: {e}")
