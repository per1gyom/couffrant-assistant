"""
Job de scan proactif — alertes mails urgents, relances, patterns cycliques.
(5E-4b + 8-CYCLES)
"""
from datetime import datetime
from app.logging_config import get_logger

logger = get_logger("raya.scheduler")


def _job_proactivity_scan():
    """Scan toutes les 30 min — alertes mails + patterns cycliques calendaires."""
    try:
        from app.database import get_pg_conn
        from app.proactive_alerts import create_alert, cleanup_expired
        cleanup_expired()
        conn = get_pg_conn()
        c = conn.cursor()
        # CROSS-TENANT INTENTIONNEL (etape A.5 part 2 du 26/04) :
        # Ce job tourne en boucle scheduler et traite TOUS les users
        # actifs tous tenants confondus. Le SELECT ne filtre donc
        # volontairement pas par tenant_id. Les fonctions appelees en
        # aval doivent re-resoudre le tenant_id depuis le username.
        # Voir docs/tests_isolation_26avril.md scenario 1.2.
        c.execute(
            "SELECT DISTINCT username FROM aria_memory "
            "WHERE created_at > NOW() - INTERVAL '7 days'"
        )
        active_users = [r[0] for r in c.fetchall()]
        conn.close()
        for username in active_users:
            try:
                _scan_user(username)
            except Exception as e:
                logger.error(f"[Proactivity] Erreur scan {username}: {e}")
        logger.info(f"[Proactivity] Scan terminé — {len(active_users)} utilisateur(s)")
    except Exception as e:
        logger.error(f"[Proactivity] ERREUR scan global: {e}")


def _scan_user(username: str):
    """Wrapper qui garantit la fermeture de la connexion meme en cas
    d'exception SQL. HOTFIX 26/04/2026 : avant ce wrapper, une exception
    SQL dans la fonction faisait fuir la connexion du pool en etat
    'idle in transaction (aborted)' — cause originelle de la saturation
    'pool exhausted' qui a commence le 25/04 ~20h42."""
    from app.database import get_pg_conn
    conn = get_pg_conn()
    try:
        _scan_user_inner(username, conn)
    finally:
        try:
            conn.rollback()
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass


def _scan_user_inner(username: str, conn):
    """Logique reelle de scan (extraite par hotfix 26/04). Re-utilise la
    connexion ouverte par le wrapper plutot que d'en ouvrir une nouvelle,
    pour que le finally du wrapper la libere proprement."""
    from app.proactive_alerts import create_alert
    from app.app_security import get_tenant_id

    tenant_id = get_tenant_id(username)
    c = conn.cursor()

    # Mails urgents non traités
    # HOTFIX 26/04/2026 : mail_memory.created_at est de type text. Sans
    # cast explicite, la comparaison avec NOW() declenchait une exception
    # de conversion implicite qui fuyait la connexion du pool (origine
    # de la saturation "pool exhausted" depuis le 25/04 ~20h42).
    c.execute("""
        SELECT id, subject, from_email, priority, received_at FROM mail_memory
        WHERE username = %s
          AND (tenant_id = %s OR tenant_id IS NULL)
          AND priority = 'haute'
          AND deleted_at IS NULL
          AND created_at::timestamp > NOW() - INTERVAL '48 hours'
          AND created_at::timestamp < NOW() - INTERVAL '2 hours'
          AND id NOT IN (
              SELECT CAST(source_id AS INTEGER) FROM proactive_alerts
              WHERE username = %s
                AND (tenant_id = %s OR tenant_id IS NULL)
                AND source_type = 'mail'
                AND created_at > NOW() - INTERVAL '24 hours'
          ) LIMIT 5
    """, (username, tenant_id, username, tenant_id))
    for row in c.fetchall():
        create_alert(
            username=username, tenant_id=tenant_id,
            alert_type="mail_urgent", priority="high",
            title=f"Mail urgent non traité : {row[1][:60]}",
            body=f"De : {row[2]} — reçu il y a plus de 2h, priorité haute.",
            source_type="mail", source_id=str(row[0]),
        )

    # Réponses en attente
    # HOTFIX 26/04/2026 : meme cast que ci-dessus pour eviter fuite pool.
    c.execute("""
        SELECT id, subject, from_email, reply_urgency FROM mail_memory
        WHERE username = %s
          AND (tenant_id = %s OR tenant_id IS NULL)
          AND needs_reply = 1 AND reply_status = 'pending'
          AND deleted_at IS NULL
          AND created_at::timestamp < NOW() - INTERVAL '24 hours'
          AND created_at::timestamp > NOW() - INTERVAL '7 days'
          AND id NOT IN (
              SELECT CAST(source_id AS INTEGER) FROM proactive_alerts
              WHERE username = %s
                AND (tenant_id = %s OR tenant_id IS NULL)
                AND source_type = 'mail_reply'
                AND created_at > NOW() - INTERVAL '24 hours'
          ) LIMIT 5
    """, (username, tenant_id, username, tenant_id))
    for row in c.fetchall():
        prio = "high" if row[3] == "haute" else "normal"
        create_alert(
            username=username, tenant_id=tenant_id,
            alert_type="reminder", priority=prio,
            title=f"Réponse en attente : {row[1][:60]}",
            body=f"De : {row[2]} — en attente depuis plus de 24h.",
            source_type="mail_reply", source_id=str(row[0]),
        )

    # Patterns cycliques calendaires (8-CYCLES)
    try:
        now = datetime.now()
        c.execute("""
            SELECT id, description, evidence FROM aria_patterns
            WHERE username = %s
              AND (tenant_id = %s OR tenant_id IS NULL)
              AND active = true AND pattern_type = 'temporal'
              AND confidence >= 0.5
        """, (username, tenant_id))
        for pat_id, desc, evidence in c.fetchall():
            alert_msg = _check_cyclic_alert(now, desc or "", evidence or "")
            if alert_msg:
                c.execute("""
                    SELECT COUNT(*) FROM proactive_alerts
                    WHERE username = %s
                      AND (tenant_id = %s OR tenant_id IS NULL)
                      AND source_type = 'cyclic_pattern'
                      AND source_id = %s
                      AND created_at > NOW() - INTERVAL '6 days'
                """, (username, tenant_id, str(pat_id)))
                if c.fetchone()[0] == 0:
                    create_alert(
                        username=username, tenant_id=tenant_id,
                        alert_type="reminder", priority="normal",
                        title=f"\U0001f4c5 Cycle détecté : {desc[:60]}",
                        body=alert_msg,
                        source_type="cyclic_pattern",
                        source_id=str(pat_id),
                    )
    except Exception as e:
        logger.error(f"[Cyclic] Erreur patterns cycliques {username}: {e}")

    # HOTFIX 26/04 : la fermeture de la connexion est faite par le
    # wrapper _scan_user via try/finally. Surtout pas de conn.close() ici
    # (sinon double-close, la connexion partirait au pool 2 fois).


def _check_cyclic_alert(now: datetime, description: str, evidence: str) -> str | None:
    """
    Vérifie si la date actuelle correspond à un pattern cyclique. (8-CYCLES)
    Retourne un message d'alerte si on est dans la période, None sinon.
    """
    text = (description + " " + evidence).lower()
    day, weekday, month = now.day, now.weekday(), now.month

    if any(kw in text for kw in (
        "fin de mois", "fin_mois", "fin du mois", "end of month",
        "relance fin", "facture fin", "clôture mensuelle",
    )):
        if day >= 25:
            return f"Nous sommes le {day} — période de fin de mois.\nPattern : {description}"

    if any(kw in text for kw in (
        "début de mois", "debut de mois", "début_mois", "début du mois", "premier du mois",
    )):
        if day <= 5:
            return f"Nous sommes le {day} — début de mois.\nPattern : {description}"

    if any(kw in text for kw in (
        "lundi", "monday", "début de semaine", "debut de semaine", "tri mails lundi",
    )):
        if weekday == 0:
            return f"C'est lundi — Pattern : {description}"

    if any(kw in text for kw in (
        "vendredi", "friday", "fin de semaine", "bilan semaine", "point semaine",
    )):
        if weekday == 4:
            return f"C'est vendredi — Pattern : {description}"

    if any(kw in text for kw in (
        "fin de trimestre", "fin_trimestre", "trimestriel",
        "end of quarter", "reporting trimestriel", "clôture trimestrielle",
    )):
        if month in (3, 6, 9, 12) and day >= 20:
            label = {3: "Q1", 6: "Q2", 9: "Q3", 12: "Q4"}.get(month, "")
            return f"Fin de trimestre {label} (mois {month}, j{day}).\nPattern : {description}"

    if any(kw in text for kw in ("août", "aout", "estival", "ralentissement été", "summer")):
        if month == 8:
            return f"Nous sommes en août — Pattern : {description}"

    if any(kw in text for kw in ("janvier", "january", "reprise", "nouvelle année", "début d'année")):
        if month == 1:
            return f"Nous sommes en janvier — Pattern : {description}"

    return None
