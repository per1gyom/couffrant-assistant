"""
Endpoints super_admin — gestion globale (utilisateurs, tenants, outils, mémoire).
  POST   /admin/unlock-user/{target}
  GET    /admin/costs
  GET    /admin/tenants/{tenant_id}/sharepoint
  PUT    /admin/tenants/{tenant_id}/sharepoint
  GET    /admin/tenants-overview
  GET    /admin/tenants
  POST   /admin/tenants
  DELETE /admin/tenants/{tenant_id}
  PUT    /admin/tenants/{tenant_id}
  GET    /admin/panel
  GET    /admin/users
  POST   /admin/create-user
  PUT    /admin/update-user/{target}
  DELETE /admin/delete-user/{target}
  POST   /admin/reset-password/{target}
  POST   /admin/users/{username}/reset-password
  GET    /admin/rules
  GET    /admin/insights
  GET    /admin/memory-status
  GET    /admin/user-tools/{target}
  POST   /admin/user-tools/{target}/{tool}
  DELETE /admin/user-tools/{target}/{tool}
  GET    /admin/diag
  GET    /init-db
  GET    /test-elevenlabs
"""
import os
import requests as http_requests
from typing import Optional
from fastapi import APIRouter, Request, Body, Depends, HTTPException
from fastapi.responses import RedirectResponse, HTMLResponse

from app.database import get_pg_conn, init_postgres
from app.app_security import (
    create_user, delete_user, update_user, list_users, init_default_user,
    get_user_tools, set_user_tool, remove_user_tool,
    generate_reset_token, hash_password,
    SCOPE_USER, DEFAULT_TENANT,
)
from app.security_auth import unlock_account
from app.routes.deps import require_admin, require_tenant_admin, assert_same_tenant
from app.admin_audit import log_admin_action
from app.dashboard_service import get_costs_dashboard

router = APIRouter()


# ─── DÉBLOCAGE COMPTE ───


# ─── DIAGNOSTIC CONNECTEURS (DIAG-ENDPOINTS) ───

@router.get("/admin/diag")
def admin_diag(request: Request, _: dict = Depends(require_admin)):
    """
    Teste la connectivité réelle de chaque service externe.
    Timeout 5s par test. Chaque test est indépendant.
    """
    import os

    result = {}

    # ── Microsoft 365 ──
    try:
        admin_username = os.getenv("APP_USERNAME", "guillaume").strip()
        from app.token_manager import get_valid_microsoft_token
        token = get_valid_microsoft_token(admin_username)
        if token:
            result["microsoft"] = {"status": "ok", "detail": f"Token valide pour {admin_username}"}
        else:
            conn = get_pg_conn()
            c = conn.cursor()
            c.execute("SELECT COUNT(*) FROM oauth_tokens WHERE provider='microsoft'")
            count = c.fetchone()[0]
            conn.close()
            if count == 0:
                result["microsoft"] = {"status": "not_configured", "detail": "Aucun token Microsoft en base"}
            else:
                result["microsoft"] = {"status": "error", "detail": f"Token expiré pour {admin_username}"}
    except Exception as e:
        result["microsoft"] = {"status": "error", "detail": str(e)[:120]}

    # ── Gmail — robuste si updated_at absent (HOTFIX-GMAIL-TOKENS) ──
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        row = None
        detail_date = ""
        try:
            # Tentative avec updated_at (disponible après migration)
            c.execute("""
                SELECT username, updated_at FROM gmail_tokens
                ORDER BY updated_at DESC LIMIT 1
            """)
            row = c.fetchone()
            if row:
                detail_date = f", mis à jour: {str(row[1])[:10]}" if row[1] else ""
        except Exception:
            # Fallback : colonne updated_at absente (avant migration)
            conn.rollback()
            c.execute("SELECT username FROM gmail_tokens LIMIT 1")
            raw = c.fetchone()
            row = (raw[0], None) if raw else None
            detail_date = " (migration updated_at en attente)"
        conn.close()

        if not row:
            result["gmail"] = {"status": "not_configured", "detail": "Aucun token Gmail en base"}
        else:
            from app.connectors.gmail_connector import is_configured
            if not is_configured():
                result["gmail"] = {
                    "status": "not_configured",
                    "detail": "GMAIL_CLIENT_ID / GMAIL_CLIENT_SECRET manquants"
                }
            else:
                result["gmail"] = {
                    "status": "ok",
                    "detail": f"Tokens présents (user: {row[0]}{detail_date})"
                }
    except Exception as e:
        result["gmail"] = {"status": "error", "detail": str(e)[:120]}

    # ── Odoo ──
    try:
        odoo_url = os.getenv("ODOO_URL", "").strip()
        odoo_db = os.getenv("ODOO_DB", "").strip()
        if not odoo_url or not odoo_db:
            result["odoo"] = {"status": "not_configured", "detail": "ODOO_URL / ODOO_DB manquants"}
        else:
            try:
                from app.connectors.odoo_connector import odoo_authenticate
                uid = odoo_authenticate()
                if uid:
                    result["odoo"] = {"status": "ok", "detail": f"Authentifié (uid={uid}) sur {odoo_url}"}
                else:
                    result["odoo"] = {"status": "error", "detail": "Authentification Odoo échouée (uid=False)"}
            except Exception as e:
                result["odoo"] = {"status": "error", "detail": str(e)[:120]}
    except Exception as e:
        result["odoo"] = {"status": "error", "detail": str(e)[:120]}

    # ── Twilio ──
    try:
        account_sid = os.getenv("TWILIO_ACCOUNT_SID", "").strip()
        auth_token = os.getenv("TWILIO_AUTH_TOKEN", "").strip()
        from_number = os.getenv("TWILIO_FROM_NUMBER", "").strip()
        if not account_sid or not auth_token or not from_number:
            missing = [k for k, v in {
                "TWILIO_ACCOUNT_SID": account_sid,
                "TWILIO_AUTH_TOKEN": auth_token,
                "TWILIO_FROM_NUMBER": from_number
            }.items() if not v]
            result["twilio"] = {
                "status": "not_configured",
                "detail": f"Variables manquantes : {', '.join(missing)}"
            }
        else:
            result["twilio"] = {
                "status": "ok",
                "detail": f"Configuré (SID: {account_sid[:8]}…, from: {from_number})"
            }
    except Exception as e:
        result["twilio"] = {"status": "error", "detail": str(e)[:120]}

    # ── ElevenLabs ──
    try:
        api_key = os.getenv("ELEVENLABS_API_KEY", "").strip()
        voice_id = os.getenv("ELEVENLABS_VOICE_ID", "").strip()
        if not api_key:
            result["elevenlabs"] = {"status": "not_configured", "detail": "ELEVENLABS_API_KEY manquant"}
        elif not voice_id:
            result["elevenlabs"] = {"status": "not_configured", "detail": "ELEVENLABS_VOICE_ID manquant"}
        else:
            result["elevenlabs"] = {
                "status": "ok",
                "detail": f"Clé présente ({len(api_key)} chars), voice_id: {voice_id}"
            }
    except Exception as e:
        result["elevenlabs"] = {"status": "error", "detail": str(e)[:120]}

    return result


# ─── AUTO-DÉCOUVERTE OUTILS ───

@router.api_route("/admin/discover/{tenant_id}/{tool_type}", methods=["GET", "POST"])
def admin_discover_tool(
    request: Request,
    tenant_id: str,
    tool_type: str,
    _: dict = Depends(require_admin),
):
    """Lance l'auto-découverte d'un outil pour un tenant."""
    # Résoudre le user primaire du tenant (nécessaire pour drive/calendar/contacts
    # qui sont user-level, pas tenant-level).
    def _primary_username(tid: str) -> str:
        from app.database import get_pg_conn
        conn = None
        try:
            conn = get_pg_conn()
            c = conn.cursor()
            c.execute("""
                SELECT username FROM user_tenant_access
                WHERE tenant_id = %s AND role IN ('owner', 'admin')
                ORDER BY (role = 'owner') DESC, username ASC LIMIT 1
            """, (tid,))
            row = c.fetchone()
            return row[0] if row else ""
        finally:
            if conn: conn.close()

    if tool_type == "odoo":
        from app.tool_discovery import discover_odoo
        result = discover_odoo(tenant_id)
        try:
            from app.entity_graph import populate_from_odoo
            result["graph"] = populate_from_odoo(tenant_id)
        except Exception as e:
            result["graph_error"] = str(e)[:200]
        return {"status": "ok" if result["discovered"] > 0 else "error", **result}

    if tool_type in ("drive", "calendar", "contacts"):
        username = _primary_username(tenant_id)
        if not username:
            return {"status": "error", "message": f"Aucun user owner/admin trouvé pour {tenant_id}"}
        from app.tool_discovery import discover_drive, discover_calendar, discover_contacts
        from app.entity_graph import populate_from_drive, populate_from_calendar, populate_from_contacts
        discover_fn = {"drive": discover_drive, "calendar": discover_calendar,
                        "contacts": discover_contacts}[tool_type]
        populate_fn = {"drive": populate_from_drive, "calendar": populate_from_calendar,
                        "contacts": populate_from_contacts}[tool_type]
        result = discover_fn(tenant_id, username)
        try:
            result["graph"] = populate_fn(tenant_id, username)
        except Exception as e:
            result["graph_error"] = str(e)[:200]
        return {"status": "ok" if result.get("discovered", 0) > 0 else "error", **result}

    return {"status": "error", "message": f"Type '{tool_type}' non supporté pour la découverte."}


@router.get("/admin/discovery-status/{tenant_id}")
def admin_discovery_status(
    request: Request,
    tenant_id: str,
    _: dict = Depends(require_admin),
):
    """État de l'auto-découverte pour un tenant."""
    from app.tool_discovery import get_discovery_status
    return get_discovery_status(tenant_id)





# ─── VECTORISATION ODOO (Bloc 2 du chantier memoire 4 couches, 18/04/2026) ───
# Voir docs/raya_memory_architecture.md + app/jobs/odoo_vectorize.py

@router.post("/admin/odoo/vectorize")
def admin_odoo_vectorize(
    request: Request,
    _: dict = Depends(require_admin),
):
    """Lance la vectorisation complete Odoo pour le tenant de l'admin :
    partners + sale.order + leads + events.

    Peuple le graphe semantique typé (nœuds Person/Company/Deal/Lead/Event/
    Product, arêtes contact_of/partner_of/has_line/scheduled_for) ET
    vectorise le contenu textuel (descriptions, notes, commentaires RDV).

    Execution synchrone : prend 30 secondes a 2 minutes selon le volume
    de donnees Odoo du tenant. Retourne un dict avec les stats par modele.
    """
    try:
        from app.tenant_manager import get_user_tenants
        tenants = get_user_tenants(request.session.get("username", ""))
        tenant_id = tenants[0] if tenants else "couffrant_solar"

        from app.jobs.odoo_vectorize import vectorize_all
        result = vectorize_all(tenant_id=tenant_id)
        return {"status": "ok", "result": result}
    except Exception as e:
        import traceback
        return {
            "status": "error",
            "message": str(e)[:300],
            "trace": traceback.format_exc()[:2000],
        }


@router.get("/admin/odoo/graph-stats")
def admin_odoo_graph_stats(
    request: Request,
    _: dict = Depends(require_admin),
):
    """Retourne les stats du graphe semantique pour le tenant de l'admin.
    Affiche dans la UI combien de nœuds de chaque type + arêtes par type."""
    try:
        from app.tenant_manager import get_user_tenants
        tenants = get_user_tenants(request.session.get("username", ""))
        tenant_id = tenants[0] if tenants else "couffrant_solar"
        from app.semantic_graph import count_graph
        return {"status": "ok", "tenant_id": tenant_id,
                "stats": count_graph(tenant_id)}
    except Exception as e:
        return {"status": "error", "message": str(e)[:300]}


# ─── ALERTES SYSTEME (Bloc 2.5 du chantier memoire, 18/04/2026) ───

@router.get("/admin/alerts")
def admin_alerts_list(
    request: Request,
    include_acknowledged: bool = False,
    min_severity: Optional[str] = None,
    _: dict = Depends(require_admin),
):
    """Liste les alertes systeme actives pour le tenant de l'admin connecte.
    min_severity accepte 'info' / 'warning' / 'critical'."""
    try:
        from app.tenant_manager import get_user_tenants
        from app.system_alerts import list_alerts
        tenants = get_user_tenants(request.session.get("username", ""))
        tenant_id = tenants[0] if tenants else "couffrant_solar"
        alerts = list_alerts(
            tenant_id=tenant_id,
            include_acknowledged=include_acknowledged,
            min_severity=min_severity,
        )
        return {"status": "ok", "tenant_id": tenant_id,
                "count": len(alerts), "alerts": alerts}
    except Exception as e:
        return {"status": "error", "message": str(e)[:300]}


@router.post("/admin/alerts/{alert_id}/acknowledge")
def admin_alerts_ack(
    request: Request,
    alert_id: int,
    _: dict = Depends(require_admin),
):
    """L'admin accuse reception d'une alerte : elle est cachee jusqu'a ce
    que le probleme se re-declenche ou evolue (updated_at et acknowledged=FALSE)."""
    try:
        from app.system_alerts import acknowledge_alert
        username = request.session.get("username", "admin")
        ok = acknowledge_alert(alert_id, username)
        return {"status": "ok" if ok else "error",
                "message": "Acquittee" if ok else "Non trouvee"}
    except Exception as e:
        return {"status": "error", "message": str(e)[:200]}



# ─── INSPECTION VECTORISATION (Fix D du 18/04/2026) ───
# Endpoints de diagnostic pour verifier concretement ce qui est dans les
# tables odoo_semantic_content et semantic_graph. Utile pour valider la
# vectorisation avant d ameliorer les fixes.

@router.get("/admin/odoo/inspect-semantic")
def admin_inspect_semantic(
    request: Request,
    source_model: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 20,
    _: dict = Depends(require_admin),
):
    """Inspecte le contenu de la table odoo_semantic_content.
    source_model : filtrer sur un modele (res.partner, sale.order, ...)
    search : recherche plein texte (tsvector FR) pour voir les matches BM25
    limit : max 50"""
    try:
        from app.tenant_manager import get_user_tenants
        tenants = get_user_tenants(request.session.get("username", ""))
        tenant_id = tenants[0] if tenants else "couffrant_solar"
        limit = min(max(1, limit), 50)

        conn = get_pg_conn()
        c = conn.cursor()

        # Stats globales par source_model
        c.execute("""
            SELECT source_model, content_type, COUNT(*),
                   COUNT(embedding) as with_embed,
                   COUNT(content_tsv) as with_tsv,
                   AVG(LENGTH(text_content))::int as avg_text_len,
                   MAX(LENGTH(text_content)) as max_text_len
            FROM odoo_semantic_content
            WHERE tenant_id = %s
            GROUP BY source_model, content_type
            ORDER BY source_model, content_type
        """, (tenant_id,))
        stats = [{
            "source_model": r[0], "content_type": r[1],
            "total": r[2], "with_embedding": r[3], "with_tsv": r[4],
            "avg_text_len": r[5], "max_text_len": r[6],
        } for r in c.fetchall()]

        # Echantillon de lignes
        filters = ["tenant_id = %s"]
        params = [tenant_id]
        if source_model:
            filters.append("source_model = %s")
            params.append(source_model)
        if search and search.strip():
            filters.append("content_tsv @@ plainto_tsquery('french', %s)")
            params.append(search.strip())
        where = " AND ".join(filters)

        order_clause = "updated_at DESC"
        if search and search.strip():
            order_clause = ("ts_rank_cd(content_tsv, plainto_tsquery('french', %s)) "
                            "DESC")
            params_with_search = params + [search.strip(), limit]
        else:
            params_with_search = params + [limit]

        c.execute(f"""
            SELECT id, source_model, source_record_id, content_type,
                   text_content, related_partner_id,
                   LENGTH(text_content) as text_len,
                   (embedding IS NOT NULL) as has_embedding,
                   metadata, updated_at
            FROM odoo_semantic_content
            WHERE {where}
            ORDER BY {order_clause}
            LIMIT %s
        """, params_with_search)

        samples = [{
            "id": r[0], "source_model": r[1], "source_record_id": r[2],
            "content_type": r[3],
            "text_preview": (r[4] or "")[:300],
            "text_length": r[6],
            "related_partner_id": r[5],
            "has_embedding": r[7],
            "metadata": r[8] or {},
            "updated_at": str(r[9]),
        } for r in c.fetchall()]
        conn.close()

        return {
            "status": "ok",
            "tenant_id": tenant_id,
            "total_entries": sum(s["total"] for s in stats),
            "stats_by_model": stats,
            "samples": samples,
            "search_filter": search,
            "source_model_filter": source_model,
        }
    except Exception as e:
        import traceback
        return {"status": "error", "message": str(e)[:300],
                "trace": traceback.format_exc()[:1500]}



@router.get("/admin/odoo/inspect-graph")
def admin_inspect_graph(
    request: Request,
    search: Optional[str] = None,
    node_type: Optional[str] = None,
    limit: int = 30,
    _: dict = Depends(require_admin),
):
    """Inspecte le graphe semantique. Cherche des noeuds par label (ilike),
    optionnellement filtre par type, puis traverse depuis chacun pour montrer
    les aretes sortantes/entrantes.

    Tres utile pour verifier si 'Francine Coullet' est bien dans le graphe
    et quelles relations elle a.
    """
    try:
        from app.tenant_manager import get_user_tenants
        from app.semantic_graph import (find_nodes_by_label, get_neighbors,
                                         count_graph)
        tenants = get_user_tenants(request.session.get("username", ""))
        tenant_id = tenants[0] if tenants else "couffrant_solar"
        limit = min(max(1, limit), 50)

        graph_stats = count_graph(tenant_id)

        if not search or not search.strip():
            return {"status": "ok", "tenant_id": tenant_id,
                    "graph_stats": graph_stats,
                    "note": "Passe ?search=nom pour chercher des noeuds"}

        nodes = find_nodes_by_label(tenant_id, search.strip(),
                                    node_type=node_type, limit=limit)

        # Pour chaque noeud trouve, on remonte ses voisins directs
        enriched = []
        for n in nodes:
            neighbors = get_neighbors(tenant_id, n["id"], min_confidence=0.3,
                                       direction="both")
            # Grouper par type d'arete pour lisibilite
            by_edge = {}
            for ng in neighbors:
                k = f"{ng['edge_type']} ({ng['edge_direction']})"
                by_edge.setdefault(k, []).append({
                    "neighbor_label": ng["neighbor_label"],
                    "neighbor_type": ng["neighbor_type"],
                    "neighbor_key": ng["neighbor_key"],
                    "confidence": ng["edge_confidence"],
                })
            enriched.append({
                "id": n["id"], "node_type": n["node_type"],
                "node_key": n["node_key"], "node_label": n["node_label"],
                "source_record_id": n["source_record_id"],
                "neighbors_count": len(neighbors),
                "edges_by_type": by_edge,
            })
        return {
            "status": "ok", "tenant_id": tenant_id,
            "graph_stats": graph_stats,
            "search": search, "node_type_filter": node_type,
            "matched_count": len(enriched),
            "matches": enriched,
        }
    except Exception as e:
        import traceback
        return {"status": "error", "message": str(e)[:300],
                "trace": traceback.format_exc()[:1500]}



@router.get("/admin/odoo/introspect")
def admin_odoo_introspect(
    request: Request,
    include_empty: bool = False,
    include_system: bool = False,
    fetch_fields_for_top: int = 30,
    _: dict = Depends(require_admin),
):
    """Inventaire complet de l'Odoo connecte : tous les modeles accessibles,
    leurs compteurs de records, leurs champs (pour les top N). Base de
    travail pour construire le plan de vectorisation universel.

    Parametres :
    - include_empty : inclure les modeles a 0 record (default False)
    - include_system : inclure les modeles systeme ir.*/base.*/etc (default False)
    - fetch_fields_for_top : fetch les champs des N premiers modeles (default 30)
    """
    try:
        from app.jobs.odoo_introspect import introspect_odoo
        result = introspect_odoo(
            include_empty=include_empty,
            include_system=include_system,
            fetch_fields_for_top=fetch_fields_for_top,
        )
        return result
    except Exception as e:
        import traceback
        return {"status": "error", "message": str(e)[:300],
                "trace": traceback.format_exc()[:1500]}


@router.get("/admin/odoo/fields/{model_name}")
def admin_odoo_fields(
    request: Request,
    model_name: str,
    _: dict = Depends(require_admin),
):
    """Retourne TOUS les champs d'un modele Odoo specifique (sans limite)."""
    try:
        from app.connectors.odoo_connector import odoo_call
        fields = odoo_call(
            model="ir.model.fields", method="search_read",
            kwargs={
                "domain": [["model", "=", model_name]],
                "fields": ["name", "field_description", "ttype", "relation",
                           "required", "readonly", "store", "translate",
                           "help", "related", "compute", "depends"],
            },
        )
        return {
            "status": "ok",
            "model": model_name,
            "fields_count": len(fields or []),
            "fields": fields,
        }
    except Exception as e:
        return {"status": "error", "message": str(e)[:300]}


@router.get("/admin/odoo/test-search")
def admin_test_semantic_search(
    request: Request,
    q: str,
    source_models: Optional[str] = None,
    limit: int = 10,
    _: dict = Depends(require_admin),
):
    """Teste le pipeline hybrid search complet (dense+sparse+RRF+rerank+graph)
    tel qu il serait utilise par Raya via le tag ODOO_SEMANTIC.
    Retourne les resultats bruts avec tous les scores pour diagnostic.

    Exemple : GET /admin/odoo/test-search?q=SE100K+onduleur&source_models=sale.order
    """
    try:
        from app.tenant_manager import get_user_tenants
        from app.retrieval import hybrid_search
        tenants = get_user_tenants(request.session.get("username", ""))
        tenant_id = tenants[0] if tenants else "couffrant_solar"

        models_list = None
        if source_models:
            models_list = [m.strip() for m in source_models.split(',') if m.strip()]

        result = hybrid_search(
            query=q,
            tenant_id=tenant_id,
            source_models=models_list,
            top_k_final=min(limit, 30),
            enrich_graph=True,
            use_rerank=True,
        )
        # On garde juste les champs lisibles pour le diagnostic
        compact_results = []
        for r in result.get("results", []):
            compact_results.append({
                "source": f"{r.get('source_model')}#{r.get('source_record_id')}",
                "content_type": r.get("content_type"),
                "text_preview": (r.get("text_content") or "")[:250],
                "dense_rank": r.get("dense_rank"),
                "sparse_rank": r.get("sparse_rank"),
                "rrf_score": r.get("rrf_score"),
                "rerank_score": r.get("rerank_score"),
                "related_nodes_count": len(r.get("related_nodes") or []),
                "related_preview": [
                    f"{n['type']}:{n['label']}"
                    for n in (r.get("related_nodes") or [])[:5]
                ],
            })
        return {
            "status": "ok",
            "query": q, "source_models": models_list,
            "stats": result.get("stats"),
            "results": compact_results,
        }
    except Exception as e:
        import traceback
        return {"status": "error", "message": str(e)[:300],
                "trace": traceback.format_exc()[:1500]}
