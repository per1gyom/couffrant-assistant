"""
Mail -> Semantic Graph (V2).

Pousse les mails de mail_memory vers le graphe semantic_graph_nodes
avec leur identification certaine (mailbox_email + connection_id) et
les proprietes utiles pour la proactivite (priority, category, etc.).

Cree le 04/05/2026 dans le cadre de l etape P2 de la roadmap Raya.

ARCHITECTURE :
─────────────────────────────────────────────────────────────────
  TABLE SOURCE : mail_memory (1006+ mails analyses, embeddings deja
                 calcules, IA deja passee : category/priority/etc)
  
  TABLE CIBLE  : semantic_graph_nodes
                 - 1 node Mail par mail_memory.id
                 - node_key = "mail_{id}"
                 - source = mailbox_source ('outlook', 'gmail', etc)
                 - source_record_id = mail_memory.id
                 
  EDGES        : semantic_graph_edges
                 - mail -> mailbox (boite d origine)
                 - mail -> contact Odoo (par from_email matching)
                 - mail -> chantier/deal (via group_hints, futur)

USAGE :
─────────────────────────────────────────────────────────────────
  push_mail_to_graph(mail_id)         # un seul mail
  push_all_mails_to_graph(tenant_id)  # backfill complet d un tenant

INTEGRATION :
─────────────────────────────────────────────────────────────────
  Le hook automatique se fait dans process_incoming_mail :
  apres l insert_mail() reussi, on appelle push_mail_to_graph().
  Voir webhook_ms_handlers.py.
"""
from __future__ import annotations

from typing import Optional
from app.database import get_pg_conn
from app.semantic_graph import add_node, add_edge_by_keys
from app.logging_config import get_logger

logger = get_logger("raya.mail_to_graph")


# ─── HELPERS ─────────────────────────────────────────────────────

def _ensure_mailbox_node(tenant_id: str, mailbox_email: str,
                          connection_id: int,
                          mailbox_label: Optional[str] = None) -> Optional[int]:
    """Cree (ou met a jour) un node Mailbox pour cette boite mail.

    node_key = "mailbox_{email}" pour etre stable et lisible.
    Une boite mail unique = un node unique, peu importe le nombre de mails.
    """
    if not mailbox_email:
        return None
    return add_node(
        tenant_id=tenant_id,
        node_type="Mailbox",
        node_key=f"mailbox_{mailbox_email}",
        node_label=mailbox_label or mailbox_email,
        node_properties={
            "email": mailbox_email,
            "connection_id": connection_id,
        },
        source="tenant_connections",
        source_record_id=str(connection_id) if connection_id else None,
    )


def _build_mail_properties(row: dict) -> dict:
    """Extrait les proprietes utiles pour la proactivite."""
    return {
        # Identite (nouveau, etape 0 du 04/05)
        "mailbox_email": row.get("mailbox_email"),
        "connection_id": row.get("connection_id"),
        "mailbox_source": row.get("mailbox_source"),

        # Brut
        "subject": row.get("subject"),
        "from_email": row.get("from_email"),
        "received_at": row.get("received_at"),
        "thread_id": row.get("thread_id"),

        # Analyse IA (deja calcule a l ingestion)
        "display_title": row.get("display_title"),
        "short_summary": row.get("short_summary"),
        "category": row.get("category"),
        "priority": row.get("priority"),
        "needs_reply": bool(row.get("needs_reply")),
        "reply_urgency": row.get("reply_urgency"),
        "reply_status": row.get("reply_status"),
        "confidence": row.get("confidence"),
    }


# ─── PUSH UNITAIRE ───────────────────────────────────────────────

def push_mail_to_graph(mail_id: int) -> Optional[int]:
    """Pousse UN mail de mail_memory vers semantic_graph_nodes.

    Idempotent : ON CONFLICT DO UPDATE (pas de doublon).
    Retourne le node_id cree/mis a jour, ou None en cas d echec.
    """
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            SELECT id, tenant_id, message_id, thread_id, subject,
                   from_email, received_at, display_title, short_summary,
                   category, priority, needs_reply, reply_urgency,
                   reply_status, confidence, mailbox_source,
                   mailbox_email, connection_id
            FROM mail_memory
            WHERE id = %s
        """, (mail_id,))
        row = c.fetchone()
        if not row:
            logger.warning("[MailToGraph] mail %d introuvable", mail_id)
            return None

        cols = [
            "id", "tenant_id", "message_id", "thread_id", "subject",
            "from_email", "received_at", "display_title", "short_summary",
            "category", "priority", "needs_reply", "reply_urgency",
            "reply_status", "confidence", "mailbox_source",
            "mailbox_email", "connection_id",
        ]
        m = dict(zip(cols, row))
    except Exception as e:
        logger.error("[MailToGraph] lecture mail %d echouee : %s",
                     mail_id, str(e)[:200])
        return None
    finally:
        if conn:
            conn.close()

    if not m["tenant_id"]:
        logger.debug("[MailToGraph] mail %d sans tenant_id, skip", mail_id)
        return None

    # Skip les mails coquilles vides (bug d ingestion non resolu)
    subject = m.get("subject") or ""
    from_email = m.get("from_email") or ""
    if not subject and not from_email:
        logger.debug("[MailToGraph] mail %d coquille vide, skip", mail_id)
        return None

    # Cree le node Mail
    label = subject or m.get("display_title") or "(sans sujet)"
    node_id = add_node(
        tenant_id=m["tenant_id"],
        node_type="Mail",
        node_key=f"mail_{m['id']}",
        node_label=label[:200],
        node_properties=_build_mail_properties(m),
        source=m.get("mailbox_source") or "outlook",
        source_record_id=str(m["id"]),
    )
    if not node_id:
        logger.warning("[MailToGraph] add_node mail %d a echoue", mail_id)
        return None

    # Edge mail -> mailbox (boite d origine)
    if m.get("mailbox_email") and m.get("connection_id"):
        try:
            _ensure_mailbox_node(
                tenant_id=m["tenant_id"],
                mailbox_email=m["mailbox_email"],
                connection_id=m["connection_id"],
            )
            add_edge_by_keys(
                tenant_id=m["tenant_id"],
                from_type="Mail", from_key=f"mail_{m['id']}",
                to_type="Mailbox", to_key=f"mailbox_{m['mailbox_email']}",
                edge_type="delivered_to",
                edge_confidence=1.0,
                edge_source="explicit_source",
            )
        except Exception as e:
            logger.warning("[MailToGraph] edge mailbox echoue : %s", str(e)[:150])

    return node_id


# ─── BACKFILL ────────────────────────────────────────────────────

def push_all_mails_to_graph(tenant_id: str,
                              limit: Optional[int] = None,
                              skip_unidentified: bool = True) -> dict:
    """Pousse tous les mails d un tenant vers le graphe.

    Args:
        tenant_id : tenant cible
        limit     : nombre max de mails (None = tous)
        skip_unidentified : si True, skip ceux sans mailbox_email
                            (cas des mails non classes par le backfill)

    Returns:
        dict : {processed, ok, skipped_empty, skipped_unidentified, errors}
    """
    stats = {
        "processed": 0, "ok": 0,
        "skipped_empty": 0,
        "skipped_unidentified": 0,
        "errors": 0,
    }

    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        sql = """
            SELECT id, subject, from_email, mailbox_email
            FROM mail_memory
            WHERE tenant_id = %s
            ORDER BY id ASC
        """
        params = (tenant_id,)
        if limit:
            sql += " LIMIT %s"
            params = (tenant_id, limit)
        c.execute(sql, params)
        ids_to_push = []
        for row in c.fetchall():
            mid, subject, from_email, mailbox_email = row
            if not (subject or "") and not (from_email or ""):
                stats["skipped_empty"] += 1
                continue
            if skip_unidentified and not mailbox_email:
                stats["skipped_unidentified"] += 1
                continue
            ids_to_push.append(mid)
    except Exception as e:
        logger.error("[MailToGraph] lecture liste mails : %s", str(e)[:200])
        return stats
    finally:
        if conn:
            conn.close()

    logger.info("[MailToGraph] %d mails a pousser pour %s",
                len(ids_to_push), tenant_id)

    for mid in ids_to_push:
        stats["processed"] += 1
        try:
            node_id = push_mail_to_graph(mid)
            if node_id:
                stats["ok"] += 1
            else:
                stats["errors"] += 1
        except Exception as e:
            stats["errors"] += 1
            logger.error("[MailToGraph] crash mail %d : %s",
                         mid, str(e)[:200])

    logger.info("[MailToGraph] Backfill termine : %s", stats)
    return stats
