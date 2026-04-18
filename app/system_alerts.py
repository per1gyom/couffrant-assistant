"""
Alertes système — détection proactive des anomalies à l'usage.

Table generique system_alerts qui stocke tout probleme meritant l'attention
de l'admin : limites de fetch approchees, modules Odoo manquants, quotas
API epuises, erreurs recurrentes, etc.

Philosophie :
- Upsert sur (tenant_id, alert_type, component) : une seule alerte active
  par combinaison. Si le probleme persiste, on met a jour le message + date,
  pas de spam.
- Severity : 'info' (<50%), 'warning' (50-90%), 'critical' (>=90% ou bloquant)
- acknowledged : l'admin peut accuser reception pour cacher l'alerte jusqu'a
  ce qu'elle se re-declenche ou evolue.
"""

import json
import logging
from typing import Optional

from app.database import get_pg_conn

logger = logging.getLogger("raya.alerts")


# Types d'alertes connus — pour eviter les typos et documenter les cas
ALERT_TYPES = {
    "fetch_limit_approached",   # limit dans vectorize_* presque atteinte
    "fetch_limit_reached",      # limit exactement atteinte (records potentiellement tronques)
    "odoo_module_missing",      # module Odoo requis non installe (helpdesk, planning, etc.)
    "openai_quota_low",         # crédit OpenAI faible (a venir)
    "openai_unavailable",       # OPENAI_API_KEY manquant
    "vectorize_error",          # vectorisation echouee pour un record
    "webhook_missed",           # un webhook a rate (filet de securite a pris le relais)
    "graph_inconsistency",      # aretes orphelines, noeuds sans source
}

SEVERITIES = ("info", "warning", "critical")


def raise_alert(
    tenant_id: str,
    alert_type: str,
    component: str,
    message: str,
    severity: str = "warning",
    details: Optional[dict] = None,
) -> bool:
    """Remonte une alerte systeme. Upsert sur (tenant, type, component) :
    si le probleme persiste, on met a jour le message/details, pas de duplicat.

    Args:
        tenant_id: tenant concerne
        alert_type: type d'alerte (voir ALERT_TYPES)
        component: le sous-composant concerne (ex : 'vectorize_partners',
          'helpdesk.ticket', 'openai_api')
        message: message court lisible par l'admin
        severity: 'info' / 'warning' / 'critical'
        details: dict JSON libre avec contexte technique
    """
    if alert_type not in ALERT_TYPES:
        logger.warning("[Alerts] Type d'alerte inconnu : %s", alert_type)
    if severity not in SEVERITIES:
        severity = "warning"

    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            INSERT INTO system_alerts
              (tenant_id, alert_type, severity, component, message, details,
               acknowledged, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s::jsonb, FALSE, NOW(), NOW())
            ON CONFLICT (tenant_id, alert_type, component) DO UPDATE SET
              severity = EXCLUDED.severity,
              message = EXCLUDED.message,
              details = EXCLUDED.details,
              acknowledged = FALSE,
              updated_at = NOW()
        """, (tenant_id, alert_type, severity, component, message[:1000],
              json.dumps(details or {}, ensure_ascii=False, default=str)))
        conn.commit()
        logger.warning("[Alerts] %s/%s : %s", severity.upper(), component, message)
        return True
    except Exception as e:
        logger.error("[Alerts] raise_alert echoue : %s", str(e)[:200])
        return False
    finally:
        if conn: conn.close()


def clear_alert(
    tenant_id: str,
    alert_type: str,
    component: str,
) -> bool:
    """Supprime une alerte (ex : le probleme est resolu a la source).
    Utilisee automatiquement par les jobs qui detectent que l'alerte
    precedente n'est plus d'actualite."""
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            DELETE FROM system_alerts
            WHERE tenant_id = %s AND alert_type = %s AND component = %s
        """, (tenant_id, alert_type, component))
        conn.commit()
        return c.rowcount > 0
    except Exception as e:
        logger.error("[Alerts] clear_alert echoue : %s", str(e)[:200])
        return False
    finally:
        if conn: conn.close()


def list_alerts(
    tenant_id: str,
    include_acknowledged: bool = False,
    min_severity: Optional[str] = None,
) -> list:
    """Retourne les alertes actives pour un tenant, triees par severity desc
    puis par date desc."""
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        conditions = ["tenant_id = %s"]
        params = [tenant_id]
        if not include_acknowledged:
            conditions.append("acknowledged = FALSE")
        if min_severity in SEVERITIES:
            # Ordre : critical > warning > info
            order_map = {"critical": 3, "warning": 2, "info": 1}
            min_level = order_map[min_severity]
            # On recupere tout puis on filtre en Python (plus simple que CASE SQL)
            pass
        where = " AND ".join(conditions)
        c.execute(f"""
            SELECT id, alert_type, severity, component, message, details,
                   acknowledged, created_at, updated_at
            FROM system_alerts
            WHERE {where}
            ORDER BY
              CASE severity WHEN 'critical' THEN 3
                            WHEN 'warning' THEN 2
                            ELSE 1 END DESC,
              updated_at DESC
            LIMIT 100
        """, params)
        rows = c.fetchall()
        result = [{
            "id": r[0], "alert_type": r[1], "severity": r[2],
            "component": r[3], "message": r[4], "details": r[5] or {},
            "acknowledged": r[6],
            "created_at": str(r[7]), "updated_at": str(r[8]),
        } for r in rows]
        if min_severity in SEVERITIES:
            order_map = {"critical": 3, "warning": 2, "info": 1}
            min_level = order_map[min_severity]
            result = [a for a in result if order_map.get(a["severity"], 0) >= min_level]
        return result
    except Exception as e:
        logger.error("[Alerts] list_alerts echoue : %s", str(e)[:200])
        return []
    finally:
        if conn: conn.close()


def acknowledge_alert(alert_id: int, username: str) -> bool:
    """L'admin accuse reception d'une alerte. Reste en base mais cachee
    jusqu'a ce que le probleme se re-declenche ou evolue."""
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            UPDATE system_alerts
            SET acknowledged = TRUE, acknowledged_by = %s,
                acknowledged_at = NOW()
            WHERE id = %s
        """, (username, alert_id))
        conn.commit()
        return c.rowcount > 0
    except Exception as e:
        logger.error("[Alerts] acknowledge echoue : %s", str(e)[:200])
        return False
    finally:
        if conn: conn.close()


def check_fetch_limit(
    tenant_id: str,
    component: str,
    fetched_count: int,
    limit_configured: int,
    total_in_source: Optional[int] = None,
) -> None:
    """Helper pour check automatique apres chaque fetch de vectorize_*.

    Logique :
    - Si fetched_count >= limit_configured : alerte 'critical' (troncature
      probable, il y a potentiellement des records manquants)
    - Si total_in_source fourni ET total_in_source > limit_configured * 0.9 :
      alerte 'warning' preventive (il reste <10% de marge)
    - Sinon, si une alerte existe pour ce component, la supprimer (probleme
      resolu).
    """
    if fetched_count >= limit_configured:
        raise_alert(
            tenant_id=tenant_id,
            alert_type="fetch_limit_reached",
            component=component,
            severity="critical",
            message=(f"Limite atteinte pour {component} : {fetched_count}/{limit_configured} "
                     f"records recuperes. Il y a probablement des records manquants. "
                     f"Augmente la limite dans le code ou purge les vieilles donnees."),
            details={
                "fetched": fetched_count,
                "limit": limit_configured,
                "total_in_source": total_in_source,
            },
        )
    elif total_in_source and total_in_source > limit_configured * 0.9:
        raise_alert(
            tenant_id=tenant_id,
            alert_type="fetch_limit_approached",
            component=component,
            severity="warning",
            message=(f"Marge faible pour {component} : {total_in_source} records dans la "
                     f"source, limite configuree a {limit_configured} ({int(100*total_in_source/limit_configured)}%). "
                     f"Pense a augmenter la limite."),
            details={
                "total_in_source": total_in_source,
                "limit": limit_configured,
                "usage_pct": round(100 * total_in_source / limit_configured, 1),
            },
        )
    else:
        # Le probleme (s'il y en avait un) est resolu
        clear_alert(tenant_id, "fetch_limit_reached", component)
        clear_alert(tenant_id, "fetch_limit_approached", component)
