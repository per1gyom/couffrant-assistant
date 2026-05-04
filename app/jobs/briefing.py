"""
Job de préparation des briefings de réunions. (7-BRIEF)
"""
from app.logging_config import get_logger

logger = get_logger("raya.scheduler")


def _job_meeting_briefing():
    """Prépare des briefings pour les réunions du jour — 06h30."""
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

        for username in active_users:
            try:
                _prepare_briefings(username)
            except Exception as e:
                logger.error(f"[Briefing] Erreur {username}: {e}")

        logger.info(f"[Briefing] Scan terminé — {len(active_users)} utilisateur(s)")
    except Exception as e:
        logger.error(f"[Briefing] ERREUR: {e}")


def _prepare_briefings(username: str):
    """Prépare un briefing pour chaque réunion du jour."""
    from app.token_manager import get_valid_microsoft_token
    from app.connectors.outlook_connector import perform_outlook_action
    from app.proactive_alerts import create_alert
    from app.app_security import get_tenant_id
    from app.llm_client import llm_complete, log_llm_usage
    from app.database import get_pg_conn
    from datetime import datetime, timezone

    token = get_valid_microsoft_token(username)
    if not token:
        return

    tenant_id = get_tenant_id(username)
    now = datetime.now(timezone.utc)
    start = now.replace(hour=0, minute=0, second=0).isoformat()
    end = now.replace(hour=23, minute=59, second=59).isoformat()
    try:
        result = perform_outlook_action(
            "list_calendar_events", {"start": start, "end": end, "top": 10}, token
        )
        events = result.get("items", [])
    except Exception:
        return

    if not events:
        return

    for event in events:
        subject = event.get("subject", "")
        attendees = event.get("attendees", [])
        event_start = event.get("start", "")
        if not subject or not attendees:
            continue
        attendee_emails = [a.get("email", "") for a in attendees if a.get("email")]
        if not attendee_emails:
            continue

        conn = get_pg_conn()
        c = conn.cursor()
        placeholders = ",".join(["%s"] * len(attendee_emails))
        c.execute(
            f"SELECT from_email, subject, short_summary, received_at FROM mail_memory "
            f"WHERE username = %s "
            f"  AND (tenant_id = %s OR tenant_id IS NULL) "
            f"  AND from_email IN ({placeholders}) "
            f"  AND deleted_at IS NULL "
            f"ORDER BY received_at DESC LIMIT 5",
            [username, tenant_id] + attendee_emails,
        )
        recent_mails = c.fetchall()
        conn.close()

        narratives_text = ""
        try:
            from app.narrative import search_narratives
            narrs = search_narratives(subject, username, tenant_id=tenant_id, limit=2)
            if narrs:
                narratives_text = "\n".join(
                    f"  {n['entity_key']}: {n['narrative'][:200]}" for n in narrs
                )
        except Exception:
            pass

        mails_text = (
            "\n".join(f"  {r[0]} — {r[1]} ({r[3]})" for r in recent_mails)
            if recent_mails else "Aucun mail récent."
        )
        prompt = (
            f"Réunion aujourd'hui : {subject}\n"
            f"Heure : {event_start}\nParticipants : {', '.join(attendee_emails)}\n\n"
            f"Mails récents avec ces participants :\n{mails_text}\n\n"
            f"Contexte dossiers :\n{narratives_text or 'Aucun dossier connu.'}\n\n"
            f"Prépare un briefing de 3-5 lignes : contexte, points en suspens, choses à préparer."
        )

        try:
            res = llm_complete(
                messages=[{"role": "user", "content": prompt}],
                model_tier="fast", max_tokens=300,
                system="Tu es Raya. Prépare un briefing concis et actionnable.",
            )
            briefing = res["text"].strip()
            log_llm_usage(res, username=username, tenant_id=tenant_id, purpose="meeting_briefing")
        except Exception:
            briefing = (
                f"Réunion '{subject}' avec {', '.join(attendee_emails[:3])}. "
                f"{len(recent_mails)} mail(s) récent(s)."
            )

        create_alert(
            username=username, tenant_id=tenant_id,
            alert_type="reminder", priority="normal",
            title=f"\U0001f4cb Briefing : {subject[:60]}",
            body=briefing[:500],
            source_type="calendar_briefing",
            source_id=event.get("id", subject[:50]),
        )

    logger.info(f"[Briefing] {username} : {len(events)} événement(s) traité(s)")
