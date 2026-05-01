"""
Connection Health — surveillance universelle de toutes les connexions Raya.

Module commun (Phase Connexions Universelles, 1er mai 2026) hérité par TOUS
les connecteurs : mails, drive, odoo, whatsapp, vesta, teams.

Voir docs/vision_connexions_universelles_01mai.md.

PHILOSOPHIE — LIVENESS CHECK (decision Q15-D Guillaume) :
─────────────────────────────────────────────────────────
On ne surveille pas "le métier" (volume de mails, activité réelle), on
surveille "la machine" (le connecteur arrive-t-il à parler à la source ?).

À chaque tentative de poll, on log dans connection_health_events :
  status='ok'      → le connecteur a parlé à la source (même si 0 nouveau item)
  status='auth_error' / 'network_error' / etc. → vraie panne technique

Règle d'alerte universelle :
  "Si le dernier event status='ok' est plus vieux que alert_threshold_seconds,
   c'est une panne technique → alerte."

→ ZERO faux positif (indépendant des horaires/volumes métier)
→ Standard industriel (Stripe, Datadog, AWS l'utilisent)

Tables exploitées : connection_health, connection_health_events
(créées via M-CU01 et M-CU02 dans database_migrations.py).
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Optional

from app.database import get_pg_conn

logger = logging.getLogger("raya.connection_health")


# Statuts possibles dans connection_health.status
STATUSES = ("healthy", "degraded", "down", "circuit_open", "unknown")

# Statuts possibles dans connection_health_events.status
EVENT_STATUSES = (
    "ok",                     # poll réussi (peut avoir items_new=0, c'est OK)
    "auth_error",             # token expiré / révoqué
    "network_error",          # impossible de joindre la source
    "rate_limit",             # source nous dit "trop d'appels"
    "subscription_dead",      # subscription côté source supprimée
    "quota_exceeded",         # quota journalier atteint
    "internal_error",         # bug interne du connecteur
    "timeout",                # appel trop long
)


# ─── ENREGISTREMENT D'UNE CONNEXION ───

def register_connection(
    connection_id: int,
    tenant_id: str,
    username: str,
    connection_type: str,
    expected_poll_interval_seconds: int = 300,
    alert_threshold_seconds: Optional[int] = None,
) -> bool:
    """Inscrit ou met à jour une connexion dans le système de monitoring.

    À appeler au démarrage de chaque connecteur (ex: après création d'une
    subscription Microsoft Graph, après init d'un polling Odoo, etc.).
    Idempotent : peut être appelé plusieurs fois sans dommage.

    Args:
        connection_id: référence vers tenant_connections.id
        tenant_id: tenant propriétaire
        username: utilisateur propriétaire
        connection_type: 'mail_outlook' / 'mail_gmail' / 'drive_sharepoint' /
                         'odoo' / 'whatsapp' / 'vesta' / 'teams'
        expected_poll_interval_seconds: intervalle attendu entre 2 polls
                                         (300 mails/drive, 120 odoo, etc.)
        alert_threshold_seconds: seuil avant alerte (défaut = 3 × interval)
    """
    if alert_threshold_seconds is None:
        alert_threshold_seconds = expected_poll_interval_seconds * 3

    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            INSERT INTO connection_health
              (connection_id, tenant_id, username, connection_type, status,
               expected_poll_interval_seconds, alert_threshold_seconds,
               created_at, updated_at)
            VALUES (%s, %s, %s, %s, 'unknown', %s, %s, NOW(), NOW())
            ON CONFLICT (connection_id) DO UPDATE SET
              connection_type = EXCLUDED.connection_type,
              expected_poll_interval_seconds = EXCLUDED.expected_poll_interval_seconds,
              alert_threshold_seconds = EXCLUDED.alert_threshold_seconds,
              updated_at = NOW()
        """, (connection_id, tenant_id, username, connection_type,
              expected_poll_interval_seconds, alert_threshold_seconds))
        conn.commit()
        return True
    except Exception as e:
        logger.error("[Health] register_connection echoue connection_id=%s : %s",
                     connection_id, str(e)[:200])
        return False
    finally:
        if conn: conn.close()


# ─── ENREGISTREMENT D'UN POLL ───

def record_poll_attempt(
    connection_id: int,
    status: str,
    items_seen: int = 0,
    items_new: int = 0,
    next_delta_token: Optional[str] = None,
    duration_ms: Optional[int] = None,
    error_detail: Optional[str] = None,
    poll_started_at: Optional[datetime] = None,
) -> bool:
    """Enregistre une tentative de poll dans connection_health_events
    et met à jour connection_health (last_*_at, status, consecutive_failures).

    À appeler par CHAQUE connecteur, à chaque cycle de poll, succès OU échec.
    C'est ce qui permet le liveness check : "le poll tourne-t-il vraiment ?"

    Args:
        connection_id: référence vers tenant_connections.id
        status: voir EVENT_STATUSES (ex: 'ok', 'auth_error', ...)
        items_seen: nb d'éléments retournés par la source (peut être 0)
        items_new: nb d'éléments réellement nouveaux (peut être 0)
        next_delta_token: token retourné par Microsoft/Google (preuve de succès)
        duration_ms: temps de la requête en ms
        error_detail: détail technique si status != 'ok'
        poll_started_at: timestamp de début du poll (auto si non fourni)
    """
    if status not in EVENT_STATUSES:
        logger.warning("[Health] Statut inconnu : %s", status)
        status = "internal_error"

    if poll_started_at is None:
        if duration_ms:
            poll_started_at = datetime.now() - timedelta(milliseconds=duration_ms)
        else:
            poll_started_at = datetime.now()

    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()

        # 1. Insert event
        c.execute("""
            INSERT INTO connection_health_events
              (connection_id, poll_started_at, poll_ended_at, status,
               items_seen, items_new, next_delta_token, duration_ms,
               error_detail, created_at)
            VALUES (%s, %s, NOW(), %s, %s, %s, %s, %s, %s, NOW())
        """, (connection_id, poll_started_at, status,
              items_seen, items_new, next_delta_token, duration_ms,
              (error_detail or "")[:1000]))

        # 2. Update connection_health (état courant)
        if status == "ok":
            # Poll réussi : on remet à zéro les compteurs d'échec
            c.execute("""
                UPDATE connection_health
                SET last_successful_poll_at = NOW(),
                    last_poll_attempt_at = NOW(),
                    consecutive_failures = 0,
                    status = 'healthy',
                    current_delta_token = COALESCE(%s, current_delta_token),
                    updated_at = NOW()
                WHERE connection_id = %s
            """, (next_delta_token, connection_id))
        else:
            # Poll échoué : on incrémente le compteur d'échecs consécutifs
            c.execute("""
                UPDATE connection_health
                SET last_poll_attempt_at = NOW(),
                    consecutive_failures = consecutive_failures + 1,
                    status = CASE
                        WHEN consecutive_failures + 1 >= 5 THEN 'down'
                        WHEN consecutive_failures + 1 >= 2 THEN 'degraded'
                        ELSE status
                    END,
                    updated_at = NOW()
                WHERE connection_id = %s
            """, (connection_id,))

        conn.commit()
        return True
    except Exception as e:
        logger.error("[Health] record_poll_attempt echoue connection_id=%s : %s",
                     connection_id, str(e)[:200])
        return False
    finally:
        if conn: conn.close()


def mark_circuit_open(connection_id: int, reason: str = "") -> bool:
    """Marque une connexion en 'circuit_open' (étape 4 du self-healing).
    Appelée par connection_resilience après échec persistant. La connexion
    est considérée HS, on cesse de la solliciter jusqu'à intervention.
    """
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            UPDATE connection_health
            SET status = 'circuit_open',
                metadata = metadata || %s::jsonb,
                updated_at = NOW()
            WHERE connection_id = %s
        """, (json.dumps({"circuit_open_reason": reason[:500],
                          "circuit_opened_at": datetime.now().isoformat()}),
              connection_id))
        conn.commit()
        logger.warning("[Health] Circuit ouvert sur connection_id=%s : %s",
                       connection_id, reason)
        return True
    except Exception as e:
        logger.error("[Health] mark_circuit_open echoue : %s", str(e)[:200])
        return False
    finally:
        if conn: conn.close()


def reset_circuit(connection_id: int) -> bool:
    """Réouvre le circuit (passe de 'circuit_open' à 'healthy'). Appelée
    après une réparation manuelle ou auto réussie."""
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            UPDATE connection_health
            SET status = 'unknown',
                consecutive_failures = 0,
                updated_at = NOW()
            WHERE connection_id = %s AND status = 'circuit_open'
        """, (connection_id,))
        conn.commit()
        return c.rowcount > 0
    except Exception as e:
        logger.error("[Health] reset_circuit echoue : %s", str(e)[:200])
        return False
    finally:
        if conn: conn.close()


# ─── LIVENESS CHECK (cœur du système) ───

def check_all_connections() -> list:
    """Parcourt toutes les connexions inscrites et retourne celles qui
    sont en alerte (silence > alert_threshold_seconds).

    Cette fonction est appelée par le job scheduler toutes les 60s.
    Ne fait PAS l'envoi d'alerte elle-même : retourne juste la liste
    des connexions concernées. L'alert_dispatcher (Étape 1.4) s'en charge.

    Returns:
        Liste de dicts : [
          {
            'connection_id': int, 'tenant_id': str, 'username': str,
            'connection_type': str, 'last_successful_poll_at': datetime,
            'silence_seconds': int, 'alert_threshold_seconds': int,
            'status': str, 'consecutive_failures': int
          },
          ...
        ]
    """
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            SELECT
              connection_id, tenant_id, username, connection_type,
              last_successful_poll_at, last_poll_attempt_at,
              consecutive_failures, status, alert_threshold_seconds,
              expected_poll_interval_seconds, metadata
            FROM connection_health
            WHERE status != 'circuit_open'
              AND alert_threshold_seconds IS NOT NULL
              AND (
                last_successful_poll_at IS NULL
                OR last_successful_poll_at < NOW() - (alert_threshold_seconds || ' seconds')::interval
              )
        """)
        rows = c.fetchall()

        in_alert = []
        for r in rows:
            last_ok = r[4]
            silence_seconds = None
            if last_ok:
                silence_seconds = int((datetime.now() - last_ok).total_seconds())
            in_alert.append({
                "connection_id": r[0],
                "tenant_id": r[1],
                "username": r[2],
                "connection_type": r[3],
                "last_successful_poll_at": last_ok,
                "last_poll_attempt_at": r[5],
                "consecutive_failures": r[6],
                "status": r[7],
                "alert_threshold_seconds": r[8],
                "expected_poll_interval_seconds": r[9],
                "metadata": r[10] or {},
                "silence_seconds": silence_seconds,
            })
        return in_alert
    except Exception as e:
        logger.error("[Health] check_all_connections echoue : %s", str(e)[:200])
        return []
    finally:
        if conn: conn.close()


# ─── SUMMARY POUR L'UI /admin/health ───

def get_status_summary(tenant_id: Optional[str] = None) -> dict:
    """Retourne un résumé global des connexions, prêt à être affiché.

    Si tenant_id est None, agrège tous les tenants (vue super_admin).
    Sinon, restreint à un tenant.

    Returns:
        {
          'total': int, 'healthy': int, 'degraded': int, 'down': int,
          'circuit_open': int, 'unknown': int,
          'connections': [
            {
              'connection_id': int, 'tenant_id': str, 'connection_type': str,
              'status': str, 'last_successful_poll_at': str,
              'silence_seconds': int, 'consecutive_failures': int,
              'alert_threshold_seconds': int, 'in_alert': bool
            },
            ...
          ]
        }
    """
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()

        where_clause = ""
        params = []
        if tenant_id:
            where_clause = "WHERE tenant_id = %s"
            params.append(tenant_id)

        c.execute(f"""
            SELECT
              connection_id, tenant_id, username, connection_type, status,
              last_successful_poll_at, last_poll_attempt_at,
              consecutive_failures, alert_threshold_seconds,
              expected_poll_interval_seconds
            FROM connection_health
            {where_clause}
            ORDER BY
              CASE status
                WHEN 'down' THEN 1
                WHEN 'circuit_open' THEN 2
                WHEN 'degraded' THEN 3
                WHEN 'unknown' THEN 4
                ELSE 5
              END,
              tenant_id, connection_type
        """, params)
        rows = c.fetchall()

        connections = []
        counts = {"healthy": 0, "degraded": 0, "down": 0,
                  "circuit_open": 0, "unknown": 0}
        for r in rows:
            status = r[4]
            counts[status] = counts.get(status, 0) + 1

            last_ok = r[5]
            silence_seconds = None
            in_alert = False
            if last_ok:
                silence_seconds = int((datetime.now() - last_ok).total_seconds())
                if r[8] and silence_seconds > r[8]:
                    in_alert = True
            elif r[8] and r[6]:
                # Pas de last_ok mais on a une dernière tentative : alerte si trop vieille
                last_attempt = r[6]
                if last_attempt:
                    in_alert = (datetime.now() - last_attempt).total_seconds() > r[8]

            connections.append({
                "connection_id": r[0],
                "tenant_id": r[1],
                "username": r[2],
                "connection_type": r[3],
                "status": status,
                "last_successful_poll_at": str(last_ok) if last_ok else None,
                "last_poll_attempt_at": str(r[6]) if r[6] else None,
                "silence_seconds": silence_seconds,
                "consecutive_failures": r[7],
                "alert_threshold_seconds": r[8],
                "expected_poll_interval_seconds": r[9],
                "in_alert": in_alert,
            })

        return {
            "total": len(connections),
            "healthy": counts.get("healthy", 0),
            "degraded": counts.get("degraded", 0),
            "down": counts.get("down", 0),
            "circuit_open": counts.get("circuit_open", 0),
            "unknown": counts.get("unknown", 0),
            "connections": connections,
        }
    except Exception as e:
        logger.error("[Health] get_status_summary echoue : %s", str(e)[:200])
        return {"total": 0, "connections": [], "error": str(e)[:200]}
    finally:
        if conn: conn.close()


def get_recent_events(connection_id: int, limit: int = 50) -> list:
    """Retourne les N derniers events d'une connexion. Utile pour debug
    et pour l'UI /admin/health quand on clique sur une connexion."""
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            SELECT id, poll_started_at, poll_ended_at, status,
                   items_seen, items_new, duration_ms, error_detail, created_at
            FROM connection_health_events
            WHERE connection_id = %s
            ORDER BY created_at DESC
            LIMIT %s
        """, (connection_id, limit))
        return [{
            "id": r[0],
            "poll_started_at": str(r[1]) if r[1] else None,
            "poll_ended_at": str(r[2]) if r[2] else None,
            "status": r[3],
            "items_seen": r[4],
            "items_new": r[5],
            "duration_ms": r[6],
            "error_detail": r[7],
            "created_at": str(r[8]),
        } for r in c.fetchall()]
    except Exception as e:
        logger.error("[Health] get_recent_events echoue : %s", str(e)[:200])
        return []
    finally:
        if conn: conn.close()
