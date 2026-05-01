"""
Job connection_health_check — liveness check toutes les 60 secondes.

Phase Connexions Universelles (1er mai 2026).
Voir docs/vision_connexions_universelles_01mai.md.

Tourne en arrière-plan via APScheduler. Utilise check_all_connections() du
module app.connection_health pour identifier les connexions silencieuses
trop longtemps (> alert_threshold_seconds), puis délègue à alert_dispatcher
(Étape 1.4) pour l'envoi des notifications.

Volume estimé : ~13 connexions actives × 1 lecture toutes les 60s = négligeable.
"""
from app.logging_config import get_logger

logger = get_logger("raya.scheduler")


def _job_connection_health_check():
    """Vérifie toutes les connexions et alerte celles en silence anormal.

    Logique :
      1. Appel check_all_connections() qui retourne les connexions
         dont last_successful_poll_at est plus vieux que leur seuil.
      2. Pour chaque connexion en alerte, déléguer à alert_dispatcher
         (qui sait comment router selon la sévérité et les préférences user).
      3. Logger un résumé pour le suivi.

    Le job est protégé par try/except large : il ne doit jamais faire planter
    le scheduler, peu importe ce qui se passe en aval.
    """
    try:
        from app.connection_health import check_all_connections

        in_alert = check_all_connections()

        if not in_alert:
            # Pas de log si tout va bien (évite le bruit dans Railway logs).
            return

        logger.warning(
            "[ConnHealth] %d connexion(s) en alerte (silence > seuil)",
            len(in_alert),
        )

        # Délégation à alert_dispatcher (sera disponible en Étape 1.4).
        # Pour l'instant on tente l'import en lazy : si le module n'existe
        # pas encore, on log juste la liste des connexions en alerte.
        try:
            from app.alert_dispatcher import dispatch_connection_alert
            for conn_alert in in_alert:
                try:
                    dispatch_connection_alert(conn_alert)
                except Exception as e:
                    logger.error(
                        "[ConnHealth] Dispatch echoue connection_id=%s : %s",
                        conn_alert.get("connection_id"),
                        str(e)[:200],
                    )
        except ImportError:
            # alert_dispatcher pas encore implémenté (Étape 1.4 à venir).
            # On log la liste des connexions concernées pour le suivi.
            for conn_alert in in_alert:
                logger.warning(
                    "[ConnHealth] EN ALERTE : connection_id=%s type=%s "
                    "tenant=%s silence=%ss seuil=%ss failures=%d status=%s",
                    conn_alert.get("connection_id"),
                    conn_alert.get("connection_type"),
                    conn_alert.get("tenant_id"),
                    conn_alert.get("silence_seconds"),
                    conn_alert.get("alert_threshold_seconds"),
                    conn_alert.get("consecutive_failures"),
                    conn_alert.get("status"),
                )
    except Exception as e:
        logger.error("[ConnHealth] Job echoue : %s", str(e)[:300])
