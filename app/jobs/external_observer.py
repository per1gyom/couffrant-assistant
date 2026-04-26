"""
Observateur d'activité externe (8-OBSERVE).

Détecte les changements effectués hors Raya :
  - Mails archivés/supprimés directement dans Outlook
  - Fichiers modifiés dans le Drive SharePoint
  - Événements calendrier créés hors Raya

Ne crée PAS d'alertes — juste du logging dans activity_log (source="external")
pour alimenter le pattern engine.

Contrôle : SCHEDULER_OBSERVER_ENABLED (défaut: false).
Fréquence : toutes les 30 minutes.
Silencieux si le token est expiré.
"""
from app.logging_config import get_logger

logger = get_logger("raya.observer")

# Fenêtre d'observation (en minutes) — doit correspondre à la fréquence du job
OBSERVATION_WINDOW_MIN = 35  # légère marge par rapport aux 30 min du scheduler


def _job_external_observer():
    """Observe l'activité externe à Raya pour chaque utilisateur connecté. (8-OBSERVE)"""
    try:
        from app.database import get_pg_conn
        from app.token_manager import get_valid_microsoft_token

        conn = get_pg_conn()
        c = conn.cursor()
        # Utilisateurs actifs ces 7 derniers jours
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

        observed = 0
        for username in active_users:
            try:
                token = get_valid_microsoft_token(username)
                if not token:
                    continue
                _observe_user(username, token)
                observed += 1
            except Exception as e:
                logger.debug(f"[Observer] Erreur {username}: {e}")

        if observed > 0:
            logger.info(f"[Observer] {observed} utilisateur(s) observé(s)")

    except Exception as e:
        logger.error(f"[Observer] ERREUR job global: {e}")


def _observe_user(username: str, token: str):
    """Observe les changements externes pour un utilisateur."""
    _observe_mail_changes(username, token)
    _observe_drive_changes(username, token)
    _observe_calendar_changes(username, token)


def _observe_mail_changes(username: str, token: str):
    """
    Détecte les mails archivés ou supprimés directement dans Outlook.
    Compare l'état actuel avec les mails connus en base.
    """
    try:
        from app.graph_client import graph_get
        from app.database import get_pg_conn
        from app.activity_log import log_activity
        from app.app_security import get_tenant_id

        tenant_id = get_tenant_id(username)

        # Récupère les message_ids connus en base (non archivés)
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            SELECT message_id FROM mail_memory
            WHERE username = %s
              AND (tenant_id = %s OR tenant_id IS NULL)
              AND created_at > NOW() - INTERVAL '7 days'
              AND mailbox_source = 'outlook'
            LIMIT 200
        """, (username, tenant_id))
        known_ids = {r[0] for r in c.fetchall()}
        conn.close()

        if not known_ids:
            return

        # Récupère les mails actuellement dans l'inbox Outlook (les 50 derniers)
        try:
            data = graph_get(token, "/me/mailFolders/inbox/messages", params={
                "$top": 50,
                "$select": "id,isRead,subject",
                "$orderby": "receivedDateTime DESC",
            })
            current_inbox_ids = {msg["id"] for msg in data.get("value", [])}
        except Exception:
            return

        # IDs connus mais plus dans l'inbox = probablement archivés/déplacés
        archived = known_ids - current_inbox_ids
        if archived:
            log_activity(
                username=username,
                action_type="mail_archived_external",
                action_target=f"{len(archived)} mail(s)",
                action_detail=f"Mails déplacés hors inbox sans passer par Raya",
                tenant_id=tenant_id,
                source="external",
            )
            logger.debug(f"[Observer] {username}: {len(archived)} mail(s) archivé(s) hors Raya")

    except Exception as e:
        logger.debug(f"[Observer] mail_changes {username}: {e}")


def _observe_drive_changes(username: str, token: str):
    """
    Détecte les fichiers récemment modifiés dans SharePoint/OneDrive.
    Utilise la recherche sur les fichiers modifiés dans les dernières 35 min.
    """
    try:
        from app.graph_client import graph_get
        from app.activity_log import log_activity
        from app.app_security import get_tenant_id
        from datetime import datetime, timedelta, timezone

        tenant_id = get_tenant_id(username)

        # Fenêtre temporelle
        since = (datetime.now(timezone.utc) - timedelta(minutes=OBSERVATION_WINDOW_MIN))
        since_str = since.strftime("%Y-%m-%dT%H:%M:%SZ")

        # Recherche des fichiers modifiés récemment
        try:
            data = graph_get(token, "/me/drive/root/search(q='')", params={
                "$filter": f"lastModifiedDateTime gt {since_str}",
                "$select": "id,name,lastModifiedDateTime,file",
                "$top": 20,
            })
            items = data.get("value", [])
        except Exception:
            # Fallback : listing simple du root
            try:
                data = graph_get(token, "/me/drive/root/children", params={
                    "$select": "id,name,lastModifiedDateTime,file",
                    "$top": 20,
                    "$orderby": "lastModifiedDateTime desc",
                })
                items = [
                    item for item in data.get("value", [])
                    if item.get("lastModifiedDateTime", "") >= since_str
                ]
            except Exception:
                return

        # Filtrer les fichiers (pas les dossiers)
        modified_files = [
            item for item in items
            if item.get("file")  # file property = c'est un fichier
        ]

        if modified_files:
            file_names = [f.get("name", "?") for f in modified_files[:5]]
            log_activity(
                username=username,
                action_type="drive_modified_external",
                action_target=f"{len(modified_files)} fichier(s)",
                action_detail=f"Modifiés hors Raya : {', '.join(file_names)}",
                tenant_id=tenant_id,
                source="external",
            )
            logger.debug(f"[Observer] {username}: {len(modified_files)} fichier(s) modifié(s) hors Raya")

    except Exception as e:
        logger.debug(f"[Observer] drive_changes {username}: {e}")


def _observe_calendar_changes(username: str, token: str):
    """
    Détecte les nouveaux événements calendrier créés hors Raya.
    Compare les événements récents avec ceux déjà loggés.
    """
    try:
        from app.graph_client import graph_get
        from app.database import get_pg_conn
        from app.activity_log import log_activity
        from app.app_security import get_tenant_id
        from datetime import datetime, timedelta, timezone

        tenant_id = get_tenant_id(username)

        # Fenêtre : événements créés dans les dernières 35 min
        since = datetime.now(timezone.utc) - timedelta(minutes=OBSERVATION_WINDOW_MIN)
        since_str = since.strftime("%Y-%m-%dT%H:%M:%SZ")

        # Récupère les événements créés récemment
        try:
            data = graph_get(token, "/me/events", params={
                "$filter": f"createdDateTime gt {since_str}",
                "$select": "id,subject,start,createdDateTime,organizer",
                "$top": 10,
                "$orderby": "createdDateTime desc",
            })
            new_events = data.get("value", [])
        except Exception:
            return

        if not new_events:
            return

        # Vérifier lesquels ne sont pas dans activity_log (créés hors Raya)
        conn = get_pg_conn()
        c = conn.cursor()
        external_events = []
        for event in new_events:
            event_id = event.get("id", "")
            # Chercher si Raya a loggé la création de cet événement
            c.execute("""
                SELECT COUNT(*) FROM activity_log
                WHERE username = %s
                  AND (tenant_id = %s OR tenant_id IS NULL)
                  AND action_type IN ('create_event', 'CREATEEVENT')
                  AND action_target LIKE %s
                  AND created_at > NOW() - INTERVAL '1 hour'
            """, (username, tenant_id, f"%{event.get('subject', '')}%"))
            if c.fetchone()[0] == 0:
                external_events.append(event)
        conn.close()

        if external_events:
            subjects = [e.get("subject", "?") for e in external_events[:3]]
            log_activity(
                username=username,
                action_type="calendar_created_external",
                action_target=f"{len(external_events)} événement(s)",
                action_detail=f"Créés hors Raya : {', '.join(subjects)}",
                tenant_id=tenant_id,
                source="external",
            )
            logger.debug(f"[Observer] {username}: {len(external_events)} événement(s) créé(s) hors Raya")

    except Exception as e:
        logger.debug(f"[Observer] calendar_changes {username}: {e}")
