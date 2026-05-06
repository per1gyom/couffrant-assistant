"""
Connecteurs v2 — CRUD tenant_connections + connection_assignments.
Chaque connexion est une instance d'outil avec ses propres credentials,
assignable dynamiquement à 1-N utilisateurs de la société.
"""
import json
from datetime import datetime, timezone
from app.database import get_pg_conn
from app.logging_config import get_logger

logger = get_logger("raya.connections")


def create_connection(
    tenant_id: str, tool_type: str, label: str,
    auth_type: str = "manual", credentials: dict = None,
    config: dict = None, created_by: str = "", status: str = "not_configured",
) -> dict:
    """Crée une connexion pour un tenant."""
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            INSERT INTO tenant_connections
            (tenant_id, tool_type, label, auth_type, credentials, config, status, created_by)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (
            tenant_id, tool_type, label, auth_type,
            json.dumps(credentials or {}), json.dumps(config or {}),
            status, created_by,
        ))
        cid = c.fetchone()[0]
        conn.commit()
        logger.info("[Connections] Created #%s %s/%s for %s", cid, tool_type, label, tenant_id)
        return {"status": "ok", "connection_id": cid, "message": f"Connexion '{label}' créée."}
    except Exception as e:
        return {"status": "error", "message": str(e)[:200]}
    finally:
        if conn: conn.close()


def update_connection(connection_id: int, **kwargs) -> dict:
    """Met à jour une connexion (label, config, credentials, status)."""
    allowed = {"label", "auth_type", "credentials", "config", "status"}
    updates = {k: v for k, v in kwargs.items() if k in allowed and v is not None}
    if not updates:
        return {"status": "error", "message": "Rien à mettre à jour."}
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        sets = []
        vals = []
        for k, v in updates.items():
            if k in ("credentials", "config"):
                sets.append(f"{k} = %s")
                vals.append(json.dumps(v))
            else:
                sets.append(f"{k} = %s")
                vals.append(v)
        sets.append("updated_at = NOW()")
        vals.append(connection_id)
        c.execute(f"UPDATE tenant_connections SET {', '.join(sets)} WHERE id = %s", vals)
        conn.commit()
        return {"status": "ok", "message": "Connexion mise à jour."}
    except Exception as e:
        return {"status": "error", "message": str(e)[:200]}
    finally:
        if conn: conn.close()


def delete_connection(connection_id: int) -> dict:
    """Supprime une connexion et ses assignments (CASCADE)."""
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("DELETE FROM tenant_connections WHERE id = %s", (connection_id,))
        if c.rowcount == 0:
            return {"status": "error", "message": "Connexion introuvable."}
        conn.commit()
        return {"status": "ok", "message": "Connexion supprimée."}
    except Exception as e:
        return {"status": "error", "message": str(e)[:200]}
    finally:
        if conn: conn.close()


def list_connections(tenant_id: str) -> list:
    """Liste toutes les connexions d'un tenant avec leurs assignments.

    Enrichi 06/05/2026 (Etape 4 refonte UI) : ajoute effective_status a
    chaque connexion pour que l UI puisse afficher le badge 🟢🟡🔴⚪
    base sur la vraie sante du polling (pas sur tenant_connections.status
    qui ne reflete que l etat OAuth initial).
    """
    from app.connection_health import get_effective_status_for_tenant

    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            SELECT tc.id, tc.tool_type, tc.label, tc.auth_type, tc.config,
                   tc.status, tc.created_by, tc.created_at, tc.connected_email
            FROM tenant_connections tc
            WHERE tc.tenant_id = %s
            ORDER BY tc.tool_type, tc.label
        """, (tenant_id,))

        # Recupere l etat effectif de toutes les connexions du tenant en
        # 1 seule query SQL (performant, pas de N+1)
        try:
            effective_list = get_effective_status_for_tenant(tenant_id)
            effective_by_id = {e["connection_id"]: e for e in effective_list}
        except Exception as ex:
            logger.warning("[Connections] effective_status echoue : %s", str(ex)[:200])
            effective_by_id = {}

        connections = []
        for row in c.fetchall():
            cid = row[0]
            c.execute("""
                SELECT username, access_level, enabled
                FROM connection_assignments WHERE connection_id = %s
            """, (cid,))
            assignments = [{"username": r[0], "access_level": r[1], "enabled": bool(r[2])} for r in c.fetchall()]

            # Etat effectif depuis connection_health
            eff = effective_by_id.get(cid, {
                "state": "unknown",
                "reason": "Pas de monitoring",
                "minutes_since_ok": None,
                "consecutive_failures": 0,
                "expected_interval_min": None,
            })
            effective_status = {
                "state": eff.get("state", "unknown"),
                "reason": eff.get("reason", ""),
                "minutes_since_ok": eff.get("minutes_since_ok"),
                "consecutive_failures": eff.get("consecutive_failures", 0),
                "expected_interval_min": eff.get("expected_interval_min"),
                "last_ok_at": (
                    eff["last_ok_at"].isoformat()
                    if eff.get("last_ok_at") else None
                ),
                "health_status": eff.get("health_status"),
            }

            connections.append({
                "id": cid, "tool_type": row[1], "label": row[2],
                "auth_type": row[3], "config": row[4] or {},
                "status": row[5], "created_by": row[6],
                "created_at": str(row[7]) if row[7] else None,
                "connected_email": row[8] or "",
                "assignments": assignments,
                "user_count": len(assignments),
                "effective_status": effective_status,
            })
        return connections
    except Exception as e:
        logger.warning("[Connections] list error: %s", e)
        return []
    finally:
        if conn: conn.close()


def assign_connection(connection_id: int, username: str, access_level: str = "read_only", enabled: bool = True) -> dict:
    """Assigne une connexion à un utilisateur (upsert)."""
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            INSERT INTO connection_assignments (connection_id, username, access_level, enabled)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (connection_id, username) DO UPDATE SET access_level = %s, enabled = %s
        """, (connection_id, username, access_level, enabled, access_level, enabled))
        conn.commit()
        return {"status": "ok", "message": f"'{username}' assigné à la connexion #{connection_id}."}
    except Exception as e:
        return {"status": "error", "message": str(e)[:200]}
    finally:
        if conn: conn.close()


def unassign_connection(connection_id: int, username: str) -> dict:
    """Retire l'accès d'un utilisateur à une connexion."""
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("DELETE FROM connection_assignments WHERE connection_id = %s AND username = %s",
                  (connection_id, username))
        if c.rowcount == 0:
            return {"status": "error", "message": "Assignation introuvable."}
        conn.commit()
        return {"status": "ok", "message": f"'{username}' retiré de la connexion #{connection_id}."}
    except Exception as e:
        return {"status": "error", "message": str(e)[:200]}
    finally:
        if conn: conn.close()


def assert_connection_tenant(connection_id: int, tenant_id: str) -> bool:
    """Vérifie qu'une connexion appartient au tenant. Retourne True si OK."""
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("SELECT tenant_id FROM tenant_connections WHERE id = %s", (connection_id,))
        row = c.fetchone()
        return bool(row and row[0] == tenant_id)
    except Exception:
        return False
    finally:
        if conn: conn.close()


def get_user_connections(username: str, tenant_id: str = None) -> list:
    """Retourne toutes les connexions accessibles à un user."""
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            SELECT tc.id, tc.tool_type, tc.label, tc.auth_type,
                   tc.config, tc.status, ca.access_level, ca.enabled
            FROM connection_assignments ca
            JOIN tenant_connections tc ON tc.id = ca.connection_id
            WHERE ca.username = %s AND ca.enabled = true
            ORDER BY tc.tool_type, tc.label
        """, (username,))
        return [{
            "id": r[0], "tool_type": r[1], "label": r[2],
            "auth_type": r[3], "config": r[4] or {},
            "status": r[5], "access_level": r[6], "enabled": bool(r[7]),
        } for r in c.fetchall()]
    except Exception as e:
        logger.warning("[Connections] get_user error: %s", e)
        return []
    finally:
        if conn: conn.close()
