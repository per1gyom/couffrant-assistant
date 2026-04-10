"""
Queue de confirmation pour les actions sensibles de Raya.

Aucune action irréversible (REPLY, DELETE, TEAMS_MSG, etc.) ne doit être
exécutée sans passer par cette queue. C'est le garde-fou en CODE qui complète
le garde-fou en PROMPT (GUARDRAILS dans aria_context.py).

Cycle de vie d'une action :
    pending → confirmed → executing → executed
                       ⇘ cancelled
    pending → expired  (après 24h)
    pending → cancelled (si Guillaume refuse)
"""
import json
from app.database import get_pg_conn


# Actions qui nécessitent confirmation obligatoire
SENSITIVE_ACTIONS = {
    "REPLY",
    "TEAMS_MSG",
    "TEAMS_REPLYCHAT",
    "TEAMS_SENDCHANNEL",
    "TEAMS_GROUPE",
    "DELETE",
    "MOVEDRIVE",
    "COPYFILE",
    "CREATEEVENT",
}


def is_sensitive(action_type: str) -> bool:
    """Retourne True si l'action nécessite confirmation."""
    return action_type.upper() in SENSITIVE_ACTIONS


def queue_action(
    tenant_id: str,
    username: str,
    action_type: str,
    payload: dict,
    label: str = "",
    conversation_id: int = None,
) -> int:
    """
    Met une action en attente de confirmation.
    Retourne l'ID de l'action en queue.
    """
    if not tenant_id:
        raise ValueError("queue_action : tenant_id obligatoire")
    if not username:
        raise ValueError("queue_action : username obligatoire")
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            INSERT INTO pending_actions
              (tenant_id, username, conversation_id, action_type, action_label, payload_json, status)
            VALUES (%s, %s, %s, %s, %s, %s::jsonb, 'pending')
            RETURNING id
        """, (
            tenant_id, username, conversation_id,
            action_type.upper(), label, json.dumps(payload, ensure_ascii=False),
        ))
        action_id = c.fetchone()[0]
        conn.commit()
        return action_id
    finally:
        if conn: conn.close()


def get_pending(username: str, tenant_id: str, limit: int = 10) -> list:
    """Liste les actions en attente pour un utilisateur."""
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            SELECT id, action_type, action_label, payload_json, created_at, expires_at
            FROM pending_actions
            WHERE username = %s AND tenant_id = %s
              AND status = 'pending'
              AND expires_at > NOW()
            ORDER BY created_at ASC
            LIMIT %s
        """, (username, tenant_id, limit))
        return [
            {
                "id": r[0],
                "action_type": r[1],
                "label": r[2],
                "payload": r[3],
                "created_at": r[4].isoformat() if r[4] else None,
                "expires_at": r[5].isoformat() if r[5] else None,
            }
            for r in c.fetchall()
        ]
    finally:
        if conn: conn.close()


def get_action(action_id: int, username: str, tenant_id: str):
    """Lit une action en queue par son ID (vérification appartenance)."""
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            SELECT id, action_type, action_label, payload_json, status, created_at, expires_at
            FROM pending_actions
            WHERE id = %s AND username = %s AND tenant_id = %s
        """, (action_id, username, tenant_id))
        row = c.fetchone()
        if not row:
            return None
        return {
            "id": row[0], "action_type": row[1], "label": row[2],
            "payload": row[3], "status": row[4],
            "created_at": row[5].isoformat() if row[5] else None,
            "expires_at": row[6].isoformat() if row[6] else None,
        }
    finally:
        if conn: conn.close()


def confirm_action(action_id: int, username: str, tenant_id: str):
    """
    Marque une action comme confirmée.
    Retourne l'action mise à jour, ou None si introuvable / déjà traitée.
    """
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            UPDATE pending_actions
            SET status = 'confirmed', confirmed_at = NOW()
            WHERE id = %s AND username = %s AND tenant_id = %s
              AND status = 'pending' AND expires_at > NOW()
            RETURNING id, action_type, action_label, payload_json
        """, (action_id, username, tenant_id))
        row = c.fetchone()
        conn.commit()
        if not row:
            return None
        return {"id": row[0], "action_type": row[1], "label": row[2], "payload": row[3]}
    finally:
        if conn: conn.close()


def cancel_action(action_id: int, username: str, tenant_id: str, reason: str = "") -> bool:
    """Marque une action comme annulée."""
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            UPDATE pending_actions
            SET status = 'cancelled', cancelled_at = NOW(), error_message = %s
            WHERE id = %s AND username = %s AND tenant_id = %s
              AND status IN ('pending', 'confirmed')
        """, (reason or None, action_id, username, tenant_id))
        ok = c.rowcount > 0
        conn.commit()
        return ok
    finally:
        if conn: conn.close()


def mark_executing(action_id: int) -> None:
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute(
            "UPDATE pending_actions SET status = 'executing' WHERE id = %s AND status = 'confirmed'",
            (action_id,)
        )
        conn.commit()
    finally:
        if conn: conn.close()


def mark_executed(action_id: int, result: dict) -> None:
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            UPDATE pending_actions
            SET status = 'executed', executed_at = NOW(), result_json = %s::jsonb
            WHERE id = %s
        """, (json.dumps(result, ensure_ascii=False, default=str), action_id))
        conn.commit()
    finally:
        if conn: conn.close()


def mark_failed(action_id: int, error: str) -> None:
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            UPDATE pending_actions
            SET status = 'failed', executed_at = NOW(), error_message = %s
            WHERE id = %s
        """, (error[:500], action_id))
        conn.commit()
    finally:
        if conn: conn.close()


def expire_old_pending(hours: int = 24) -> int:
    """Job à appeler périodiquement pour expirer les actions trop vieilles."""
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute(
            "UPDATE pending_actions SET status = 'expired' WHERE status = 'pending' AND expires_at < NOW()"
        )
        n = c.rowcount
        conn.commit()
        return n
    finally:
        if conn: conn.close()
