"""
Endpoints admin pour la gestion des boites mail.
Cree le 04/05/2026 - chantier B (mail admin tools).

Endpoints :
  GET  /admin/mail/inventory/{conn_id}        : compte par dossier (Outlook+Gmail)
  POST /admin/mail/bootstrap/start            : lance bootstrap historique
  GET  /admin/mail/bootstrap/status/{conn_id} : etat run en cours / dernier
  GET  /admin/mail/graph-stats/{conn_id}      : stats graphe pour cette boite
  POST /admin/mail/migrate-to-graph/{conn_id} : rattrape mails ingere->graphe
"""
from typing import Optional
from fastapi import APIRouter, Request, Depends, Query
from app.database import get_pg_conn
from app.routes.deps import require_admin
from app.logging_config import get_logger

logger = get_logger("raya.routes.admin_mail")

router = APIRouter()


# ─── HELPER ─────────────────────────────────────────────────

def _lookup_connection(conn_id: int) -> Optional[dict]:
    """Recupere les infos d une connexion (tenant, type, email, owner)."""
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute(
            "SELECT tenant_id, tool_type, connected_email, label "
            "FROM tenant_connections WHERE id = %s", (conn_id,))
        row = c.fetchone()
        if not row:
            return None
        tenant_id, tool_type, email, label = row[0], row[1], row[2], row[3]
        c.execute(
            "SELECT username FROM user_tenant_access "
            "WHERE tenant_id = %s AND role IN ('owner','admin') "
            "ORDER BY (role='owner') DESC LIMIT 1", (tenant_id,))
        ur = c.fetchone()
        username = ur[0] if ur else None
        return {"tenant_id": tenant_id, "tool_type": tool_type,
                "connected_email": email, "label": label,
                "username": username}
    except Exception as e:
        logger.error("[AdminMail] _lookup_connection : %s", str(e)[:200])
        return None
    finally:
        if conn:
            conn.close()


# ─── INVENTAIRE ─────────────────────────────────────────────

@router.get("/admin/mail/inventory/{conn_id}")
def admin_mail_inventory(conn_id: int, _: dict = Depends(require_admin)):
    """Compte par dossier les mails dans la boite (sans rien ingerer).
    Reutilise les fonctions de comptage de la reconciliation nocturne.
    """
    info = _lookup_connection(conn_id)
    if not info:
        return {"status": "error",
                "message": f"Connexion {conn_id} introuvable"}

    tool_type = info["tool_type"]
    username = info["username"]
    if not username:
        return {"status": "error",
                "message": "Aucun owner trouve pour cette connexion"}

    folders_count = {}

    if tool_type in ("microsoft", "outlook"):
        from app.token_manager import get_valid_microsoft_token
        from app.jobs.mail_outlook_reconciliation import _count_folder_microsoft
        try:
            token = get_valid_microsoft_token(username)
        except Exception:
            token = None
        if not token:
            return {"status": "error",
                    "message": "Token Microsoft non disponible"}
        for folder in ["Inbox", "SentItems", "JunkEmail", "Archive",
                        "DeletedItems"]:
            try:
                cnt = _count_folder_microsoft(token, folder)
                folders_count[folder] = cnt if cnt is not None else None
            except Exception:
                folders_count[folder] = None

    elif tool_type == "gmail":
        from app.connection_token_manager import get_all_user_connections
        from app.jobs.mail_gmail_reconciliation import _count_label_google
        token = None
        try:
            for c in get_all_user_connections(username):
                if c.get("connection_id") == conn_id:
                    token = c.get("token")
                    break
        except Exception:
            pass
        if not token:
            return {"status": "error",
                    "message": "Token Gmail non disponible"}
        for label in ["INBOX", "SENT", "SPAM", "TRASH",
                       "CATEGORY_PROMOTIONS", "CATEGORY_UPDATES",
                       "CATEGORY_SOCIAL"]:
            try:
                cnt = _count_label_google(token, label)
                folders_count[label] = cnt if cnt is not None else None
            except Exception:
                folders_count[label] = None
    else:
        return {"status": "error",
                "message": f"tool_type {tool_type} non supporte"}

    # Comptage cote Raya (mail_memory + graphe)
    conn = None
    raya_count = 0
    graph_count = 0
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute(
            "SELECT COUNT(*) FROM mail_memory WHERE connection_id = %s",
            (conn_id,))
        raya_count = c.fetchone()[0] or 0
        c.execute(
            "SELECT COUNT(*) FROM semantic_graph_nodes "
            "WHERE tenant_id = %s AND node_type = 'Mail' "
            "AND deleted_at IS NULL "
            "AND (node_properties->>'connection_id')::int = %s",
            (info["tenant_id"], conn_id))
        graph_count = c.fetchone()[0] or 0
    except Exception as e:
        logger.warning("[AdminMail] inventory raya count : %s", str(e)[:200])
    finally:
        if conn:
            conn.close()

    # Compte total ignore les valeurs None
    total_remote = sum(v for v in folders_count.values() if v)

    return {
        "status": "ok",
        "connection": info,
        "folders": folders_count,
        "total_remote": total_remote,
        "ingere_chez_raya": raya_count,
        "dans_graphe": graph_count,
    }


# ─── BOOTSTRAP ───────────────────────────────────────────────

@router.post("/admin/mail/bootstrap/start")
def admin_mail_bootstrap_start(
    conn_id: int = Query(...),
    months: int = Query(12, description="3, 6, 9, 12 ou 0 pour tout"),
    include_sent: bool = Query(True),
    _: dict = Depends(require_admin),
):
    """Lance un bootstrap historique en thread daemon.
    months=0 = tout l historique.
    """
    from app.jobs.mail_bootstrap import start_bootstrap
    return start_bootstrap(connection_id=conn_id,
                            months_back=months,
                            include_sent=include_sent)


@router.get("/admin/mail/bootstrap/status/{conn_id}")
def admin_mail_bootstrap_status(conn_id: int,
                                  _: dict = Depends(require_admin)):
    """Etat du dernier (ou en cours) bootstrap."""
    from app.jobs.mail_bootstrap import get_last_run, is_running
    info = _lookup_connection(conn_id)
    last = get_last_run(conn_id)
    return {
        "status": "ok",
        "connection": info,
        "is_running": is_running(conn_id),
        "last_run": last,
    }


# ─── GRAPHE MAIL ─────────────────────────────────────────────

@router.get("/admin/mail/graph-stats/{conn_id}")
def admin_mail_graph_stats(conn_id: int,
                            _: dict = Depends(require_admin)):
    """Stats graphe pour une boite mail."""
    info = _lookup_connection(conn_id)
    if not info:
        return {"status": "error",
                "message": f"Connexion {conn_id} introuvable"}
    tenant_id = info["tenant_id"]

    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        # Total noeuds Mail dans le graphe pour cette connexion
        c.execute(
            "SELECT COUNT(*) FROM semantic_graph_nodes "
            "WHERE tenant_id = %s AND node_type = 'Mail' "
            "AND deleted_at IS NULL "
            "AND (node_properties->>'connection_id')::int = %s",
            (tenant_id, conn_id))
        nb_in_graph = c.fetchone()[0] or 0
        # Total mails ingere dans mail_memory pour cette connexion
        c.execute(
            "SELECT COUNT(*) FROM mail_memory WHERE connection_id = %s",
            (conn_id,))
        nb_in_memory = c.fetchone()[0] or 0
        # Top expediteurs dans le graphe pour cette boite
        c.execute(
            "SELECT node_properties->>'from_email' as sender, COUNT(*) "
            "FROM semantic_graph_nodes "
            "WHERE tenant_id = %s AND node_type = 'Mail' "
            "AND deleted_at IS NULL "
            "AND (node_properties->>'connection_id')::int = %s "
            "AND node_properties->>'from_email' IS NOT NULL "
            "GROUP BY 1 ORDER BY 2 DESC LIMIT 10",
            (tenant_id, conn_id))
        top_senders = [{"sender": r[0], "count": r[1]}
                        for r in c.fetchall()]
        # Repartition par categorie IA
        c.execute(
            "SELECT node_properties->>'category' as cat, COUNT(*) "
            "FROM semantic_graph_nodes "
            "WHERE tenant_id = %s AND node_type = 'Mail' "
            "AND deleted_at IS NULL "
            "AND (node_properties->>'connection_id')::int = %s "
            "GROUP BY 1 ORDER BY 2 DESC LIMIT 15",
            (tenant_id, conn_id))
        by_category = [{"category": r[0] or "(non classe)",
                         "count": r[1]} for r in c.fetchall()]
        # Edges sortantes du noeud Mail (delivered_to, sent_by, etc.)
        c.execute(
            "SELECT e.edge_type, COUNT(*) "
            "FROM semantic_graph_edges e "
            "JOIN semantic_graph_nodes n ON n.id = e.edge_from "
            "WHERE e.tenant_id = %s AND n.node_type = 'Mail' "
            "AND e.deleted_at IS NULL "
            "AND (n.node_properties->>'connection_id')::int = %s "
            "GROUP BY 1 ORDER BY 2 DESC", (tenant_id, conn_id))
        edges_out = [{"edge_type": r[0], "count": r[1]}
                      for r in c.fetchall()]
    except Exception as e:
        logger.error("[AdminMail] graph-stats : %s", str(e)[:200])
        return {"status": "error", "message": str(e)[:300]}
    finally:
        if conn:
            conn.close()

    coverage_pct = round(100 * nb_in_graph / nb_in_memory, 1) if nb_in_memory else 0
    return {
        "status": "ok",
        "connection": info,
        "nb_in_memory": nb_in_memory,
        "nb_in_graph": nb_in_graph,
        "coverage_pct": coverage_pct,
        "top_senders": top_senders,
        "by_category": by_category,
        "edges_out": edges_out,
    }


@router.post("/admin/mail/migrate-to-graph/{conn_id}")
def admin_mail_migrate_to_graph(conn_id: int,
                                  _: dict = Depends(require_admin)):
    """Rattrape les mails ingere mais pas dans le graphe.
    Idempotent : peut etre relance sans risque.
    """
    info = _lookup_connection(conn_id)
    if not info:
        return {"status": "error", "message": "Connexion introuvable"}
    tenant_id = info["tenant_id"]

    # Trouve les mail_memory.id qui ne sont PAS dans semantic_graph_nodes
    conn = None
    missing_ids = []
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute(
            "SELECT id FROM mail_memory mm "
            "WHERE mm.connection_id = %s "
            "AND NOT EXISTS ("
            "  SELECT 1 FROM semantic_graph_nodes sgn "
            "  WHERE sgn.tenant_id = %s "
            "  AND sgn.node_type = 'Mail' "
            "  AND sgn.deleted_at IS NULL "
            "  AND sgn.source_record_id = mm.id::text"
            ") "
            "ORDER BY id ASC LIMIT 5000",
            (conn_id, tenant_id))
        missing_ids = [r[0] for r in c.fetchall()]
    except Exception as e:
        return {"status": "error", "message": str(e)[:300]}
    finally:
        if conn:
            conn.close()

    if not missing_ids:
        return {"status": "ok",
                "message": "Tous les mails sont deja dans le graphe",
                "pushed": 0, "skipped": 0, "errors": 0}

    # Lance le push en thread (le push de chaque mail prend 50-100ms)
    import threading
    from app.mail_to_graph import push_mail_to_graph

    def _run():
        for mid in missing_ids:
            try:
                push_mail_to_graph(mid)
            except Exception as e:
                logger.warning("[AdminMail] migrate mail %d : %s",
                               mid, str(e)[:200])

    t = threading.Thread(target=_run, daemon=True,
                          name=f"mail_migrate_{conn_id}")
    t.start()

    return {"status": "started",
            "message": f"Migration lancee en arriere-plan pour {len(missing_ids)} mails",
            "to_push": len(missing_ids)}
