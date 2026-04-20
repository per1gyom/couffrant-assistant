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
from typing import Optional

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



@router.post("/admin/odoo/introspect/start")
def admin_odoo_introspect_start(
    request: Request,
    include_empty: bool = False,
    include_system: bool = False,
    fetch_fields_for_top: int = 30,
    _: dict = Depends(require_admin),
):
    """Lance une introspection en BACKGROUND. Retourne immediatement un
    run_id. Utiliser /admin/odoo/introspect/status?run_id=... pour poller."""
    try:
        from app.jobs.odoo_introspect import start_introspect_run
        run_id = start_introspect_run(
            include_empty=include_empty,
            include_system=include_system,
            fetch_fields_for_top=fetch_fields_for_top,
        )
        return {"status": "started", "run_id": run_id}
    except Exception as e:
        return {"status": "error", "message": str(e)[:300]}


@router.post("/admin/scanner/debug/extract-document")
async def admin_scanner_debug_extract(
    request: Request,
    _: dict = Depends(require_admin),
):
    """Diagnostic Phase 6 : teste l extraction de texte sur un fichier
    uploade. Accepte un fichier via multipart form-data.

    Usage :
        curl -X POST /admin/scanner/debug/extract-document \\
             -F "file=@/path/to/document.pdf"

    Retourne :
        {"filename": "...", "mime_type": "...", "size": N,
         "text_extracted": "...", "text_length": N, "method": "pdf"}
    """
    try:
        form = await request.form()
        upload = form.get("file")
        if not upload:
            return {"status": "error",
                    "message": "Pas de fichier, utiliser -F 'file=@path'"}
        content = await upload.read()
        filename = upload.filename or "unknown"
        mime_type = upload.content_type or ""
        from app.scanner.document_extractors import extract_document_text
        text = extract_document_text(
            content_bytes=content,
            filename=filename,
            mime_type=mime_type,
            context_hint=f"Document upload depuis panel admin : {filename}",
        )
        return {
            "status": "ok",
            "filename": filename,
            "mime_type": mime_type,
            "size_bytes": len(content),
            "size_kb": round(len(content) / 1024, 1),
            "text_extracted": text[:500] + "..." if text and len(text) > 500 else text,
            "text_length": len(text) if text else 0,
            "full_text_preview": text,
        }
    except Exception as e:
        import traceback
        return {"status": "error", "message": str(e)[:300],
                "trace": traceback.format_exc()[:1500]}


@router.get("/admin/scanner/integrity")
def admin_scanner_integrity(
    request: Request,
    tenant_id: str = "couffrant",
    source: str = "odoo",
    _: dict = Depends(require_admin),
):
    """Dashboard d integrite Phase 8 : retourne pour chaque modele son
    niveau de vectorisation (Odoo vs Raya).

    Pour chaque modele avec manifest actif :
    - records_count_odoo : nombre de records cote Odoo (au moment du
      dernier scan complet)
    - records_count_raya : nombre de records vectorises cote Raya
    - integrity_pct : ratio raya/odoo (100% = parfait, <50% = alerte rouge)
    - chunks_in_db : nombre reel de chunks actuellement en base
    - nodes_in_db : nombre de noeuds du graphe pour ce modele
    - severity : 'ok' / 'warning' / 'critical' selon integrity_pct
    - last_scanned_at : timestamp du dernier scan reussi
    """
    try:
        from app.database import get_pg_conn
        with get_pg_conn() as conn:
            cur = conn.cursor()
            # 1. Liste des manifests + compteurs des colonnes
            cur.execute(
                """SELECT model_name, priority, enabled, records_count_odoo,
                          records_count_raya, integrity_pct, last_scanned_at
                   FROM connector_schemas
                   WHERE tenant_id=%s AND source=%s
                   ORDER BY priority ASC, records_count_odoo DESC NULLS LAST""",
                (tenant_id, source),
            )
            rows = cur.fetchall()

            # 2. Comptage REEL des chunks + nodes actuellement en DB
            #    (independant des stats des runs, source de verite live)
            cur.execute(
                """SELECT source_model, COUNT(*) AS n
                   FROM odoo_semantic_content
                   WHERE tenant_id=%s AND source_model IS NOT NULL
                     AND deleted_at IS NULL
                   GROUP BY source_model""",
                (tenant_id,),
            )
            chunks_by_model = {r[0]: r[1] for r in cur.fetchall()}

            cur.execute(
                """SELECT node_type, COUNT(*) AS n
                   FROM semantic_graph_nodes
                   WHERE tenant_id=%s AND source=%s
                     AND deleted_at IS NULL
                   GROUP BY node_type""",
                (tenant_id, source),
            )
            # node_type peut etre 'contact', 'devis', etc. — mapping rapide
            nodes_by_type = {r[0]: r[1] for r in cur.fetchall()}

            # 2bis. Recupere les manifests pour detecter les modeles graph-only
            #       (pas de vectorize_fields = pas de chunks attendus)
            cur.execute(
                """SELECT model_name, manifest FROM connector_schemas
                   WHERE tenant_id=%s AND source=%s""",
                (tenant_id, source),
            )
            manifests_by_model = {r[0]: r[1] for r in cur.fetchall()}

        # 3. Construction du rapport par modele
        # Severity avancee (19/04/2026) :
        # - 'ok'         : integrity >= 90% (vert)
        # - 'warning'    : 50 <= integrity < 90% (orange)
        # - 'critical'   : integrity < 50% (rouge) — SEULEMENT si pas limit/graph
        # - 'limited'    : modele plafonne par MODEL_RECORD_LIMITS (orange doux)
        # - 'graph_only' : manifest sans vectorize_fields (gris, normal)
        # - 'unknown'    : pas encore scanne
        from app.scanner.runner import MODEL_RECORD_LIMITS
        models = []
        for r in rows:
            model_name, priority, enabled, odoo_count = r[0], r[1], r[2], r[3]
            raya_count, integrity, last_scan = r[4], r[5], r[6]
            chunks = chunks_by_model.get(model_name, 0)
            manifest = manifests_by_model.get(model_name) or {}
            vec_fields = manifest.get("vectorize_fields") or []
            is_graph_only = len(vec_fields) == 0
            limit = MODEL_RECORD_LIMITS.get(model_name)
            # Detection du plafond volontaire :
            # - limit is None => pas de plafond, logique classique
            # - limit == 0   => skip volontaire (ex: res.city)
            # - limit > 0    => plafond, si on a atteint >= 95% du plafond -> "limited"
            is_capped = (limit is not None and limit > 0 and raya_count and
                         raya_count >= limit * 0.95)
            if is_graph_only:
                # Pas de vectorize_fields = on ne cree pas de chunks, c'est normal
                severity = "graph_only"
            elif is_capped:
                # Plafond atteint volontairement (ex: product.template 5000/133k)
                severity = "limited"
            elif integrity is None or enabled is False:
                severity = "unknown"
            elif integrity >= 90:
                severity = "ok"
            elif integrity >= 50:
                severity = "warning"
            else:
                severity = "critical"
            models.append({
                "model_name": model_name,
                "priority": priority,
                "enabled": enabled,
                "records_count_odoo": odoo_count,
                "records_count_raya": raya_count,
                "chunks_in_db": chunks,
                "integrity_pct": float(integrity) if integrity else None,
                "severity": severity,
                "applicative_limit": limit,
                "is_graph_only": is_graph_only,
                "last_scanned_at": last_scan.isoformat() if last_scan else None,
            })

        # 4. Totaux
        # Intégrité globale calculée UNIQUEMENT sur les modèles qui doivent
        # être vectorisés (on exclut graph_only qui sont normaux à 0, et
        # limited qui ont atteint leur plafond volontairement).
        models_countable = [m for m in models
                            if m["severity"] not in ("graph_only", "limited")]
        total_odoo = sum(m["records_count_odoo"] or 0 for m in models_countable)
        total_raya = sum(m["records_count_raya"] or 0 for m in models_countable)
        total_chunks = sum(m["chunks_in_db"] for m in models)
        overall_integrity = round(100 * total_raya / total_odoo, 1) if total_odoo else 0
        return {
            "status": "ok",
            "tenant_id": tenant_id,
            "source": source,
            "overall": {
                "models_total": len(models),
                "models_ok": sum(1 for m in models if m["severity"] == "ok"),
                "models_warning": sum(1 for m in models if m["severity"] == "warning"),
                "models_critical": sum(1 for m in models if m["severity"] == "critical"),
                "models_limited": sum(1 for m in models if m["severity"] == "limited"),
                "models_graph_only": sum(1 for m in models if m["severity"] == "graph_only"),
                "models_unknown": sum(1 for m in models if m["severity"] == "unknown"),
                "total_records_odoo": total_odoo,
                "total_records_raya": total_raya,
                "total_chunks_in_db": total_chunks,
                "overall_integrity_pct": overall_integrity,
            },
            "models": models,
        }
    except Exception as e:
        import traceback
        return {"status": "error", "message": str(e)[:300],
                "trace": traceback.format_exc()[:1500]}


@router.post("/admin/scanner/scan-nuit-complet")
def admin_scanner_scan_nuit_complet(
    request: Request,
    _: dict = Depends(require_admin),
):
    """Lance le scan de nuit COMPLET en arriere-plan sur Railway.
    Enchaine les 4 etapes : mail.tracking + res.partner + products utiles + P2 complet.
    Duree 2h-3h. Suivi via dashboard Integrite."""
    try:
        from app.jobs.scan_nuit_complet_job import launch_async
        return launch_async(tenant_id="couffrant", source="odoo")
    except Exception as e:
        import traceback
        return {"status": "error", "message": str(e)[:300],
                "trace": traceback.format_exc()[:1500]}


@router.get("/admin/scanner/scan-nuit-complet/status")
def admin_scanner_scan_nuit_complet_status(
    request: Request,
    _: dict = Depends(require_admin),
):
    """Retourne l etat du scan de nuit (en cours / pas en cours)."""
    try:
        from app.jobs.scan_nuit_complet_job import is_running
        return {"status": "ok", "running": is_running()}
    except Exception as e:
        return {"status": "error", "message": str(e)[:300]}


@router.post("/admin/drive/scan-start")
def admin_drive_scan_start(
    request: Request,
    _: dict = Depends(require_admin),
):
    """Lance un scan complet du dossier SharePoint configure pour le tenant.
    Tourne en arriere-plan (thread daemon Railway). Applique le principe
    memoire 3 niveaux (meta + detail + live via re-fetch)."""
    try:
        from app.jobs.drive_scanner import launch_async
        import os
        username = os.getenv("APP_USERNAME", "guillaume").strip()
        return launch_async(tenant_id="couffrant_solar", username=username)
    except Exception as e:
        import traceback
        return {"status": "error", "message": str(e)[:300],
                "trace": traceback.format_exc()[:1500]}


@router.get("/admin/drive/scan-status")
def admin_drive_scan_status(
    request: Request,
    _: dict = Depends(require_admin),
):
    """Retourne l etat du scan Drive (en cours + stats du dernier scan
    par dossier surveille). Utilise par le panel admin pour l affichage."""
    try:
        from app.jobs.drive_scanner import get_last_scan_stats
        return get_last_scan_stats(tenant_id="couffrant_solar")
    except Exception as e:
        return {"status": "error", "message": str(e)[:300]}


@router.get("/admin/webhooks/status")
def admin_webhooks_status(
    request: Request,
    tenant_id: Optional[str] = None,
    _: dict = Depends(require_admin),
):
    """Dashboard de monitoring des webhooks Odoo (Phase A.2 roadmap v4).

    Retourne compteurs 24h + etat du worker + derniers rapports ronde de nuit.
    Si tenant_id absent : aggregat global (tous tenants confondus).
    """
    import os
    try:
        from app.webhook_queue import get_stats
        from app.database import get_pg_conn

        # 1. Stats de la queue (tous tenants ou un seul)
        stats = get_stats(tenant_id=tenant_id)

        # 2. Liste des tenants avec secret configure
        prefix = "ODOO_WEBHOOK_SECRET_"
        configured_tenants = sorted({
            key[len(prefix):].lower().strip() for key in os.environ
            if key.startswith(prefix) and os.environ[key]
        })

        # 3. Derniers rapports ronde de nuit (dernier par tenant)
        with get_pg_conn() as conn:
            cur = conn.cursor()
            cur.execute(
                """SELECT tenant_id, severity, message, details,
                          acknowledged, updated_at
                   FROM system_alerts
                   WHERE alert_type='webhook_night_patrol'
                     AND component='webhook_queue'
                   ORDER BY updated_at DESC
                   LIMIT 10""",
            )
            patrol_reports = [
                {"tenant_id": r[0], "severity": r[1], "message": r[2],
                 "details": r[3], "acknowledged": r[4],
                 "updated_at": r[5].isoformat() if r[5] else None}
                for r in cur.fetchall()
            ]

            # 4. Details des 20 derniers webhooks traites
            where_tenant = "AND tenant_id=%s" if tenant_id else ""
            params = (tenant_id,) if tenant_id else ()
            cur.execute(
                f"""SELECT tenant_id, source, model_name, record_id, action,
                          attempts, last_error, created_at, completed_at,
                          nonce IS NOT NULL AS via_webhook
                   FROM vectorization_queue
                   WHERE 1=1 {where_tenant}
                   ORDER BY COALESCE(completed_at, created_at) DESC
                   LIMIT 20""",
                params,
            )
            recent = [
                {"tenant_id": r[0], "source": r[1], "model": r[2],
                 "record_id": r[3], "action": r[4], "attempts": r[5],
                 "error": (r[6] or "")[:200],
                 "created_at": r[7].isoformat() if r[7] else None,
                 "completed_at": r[8].isoformat() if r[8] else None,
                 "via_webhook": r[9]}
                for r in cur.fetchall()
            ]

        return {
            "status": "ok",
            "tenant_filter": tenant_id,
            "stats": stats,
            "configured_tenants": configured_tenants,
            "patrol_reports": patrol_reports,
            "recent_jobs": recent,
        }
    except Exception as e:
        import traceback
        return {"status": "error", "message": str(e)[:300],
                "trace": traceback.format_exc()[:1500]}


@router.get("/admin/scanner/db-size")
def admin_scanner_db_size(
    request: Request,
    _: dict = Depends(require_admin),
):
    """Retourne la taille actuelle de la DB PostgreSQL + taille des principales
    tables du Scanner Universel. Permet de surveiller le remplissage du volume
    Railway en temps reel pendant un scan."""
    try:
        from app.database import get_pg_conn
        with get_pg_conn() as conn:
            cur = conn.cursor()
            # Taille totale de la DB
            cur.execute("SELECT pg_database_size(current_database())")
            total_bytes = cur.fetchone()[0]
            # Taille par table (relevantes pour le Scanner)
            cur.execute("""
                SELECT
                    tablename,
                    pg_total_relation_size('public.' || quote_ident(tablename)) AS total_bytes,
                    pg_relation_size('public.' || quote_ident(tablename)) AS table_bytes,
                    (SELECT reltuples::bigint FROM pg_class WHERE relname = tablename) AS row_estimate
                FROM pg_tables
                WHERE schemaname = 'public'
                  AND tablename IN ('odoo_semantic_content', 'semantic_graph_nodes',
                                    'semantic_graph_edges', 'scanner_runs',
                                    'connector_schemas', 'vectorization_queue',
                                    'mail_memory', 'conversation_history')
                ORDER BY total_bytes DESC
            """)
            tables = [{
                "table": r[0],
                "total_bytes": r[1],
                "total_mb": round(r[1] / 1024 / 1024, 2),
                "row_estimate": r[3],
            } for r in cur.fetchall()]
        return {
            "total_db_bytes": total_bytes,
            "total_db_mb": round(total_bytes / 1024 / 1024, 2),
            "total_db_gb": round(total_bytes / 1024 / 1024 / 1024, 3),
            "railway_volume_gb": 5,
            "usage_pct": round(100 * total_bytes / (5 * 1024**3), 1),
            "tables": tables,
        }
    except Exception as e:
        return {"status": "error", "message": str(e)[:300]}


@router.get("/admin/scanner/debug/embed-test")
def admin_scanner_debug_embed(
    request: Request,
    _: dict = Depends(require_admin),
):
    """Diagnostic Phase 3 : teste embed() + insert chunk + verifie l env.
    Retourne un rapport detaille pour identifier pourquoi les chunks ne
    s ecrivent pas (0 chunks malgre N records scannes)."""
    import os, json, traceback
    from app.database import get_pg_conn
    report = {
        "env_openai_api_key_set": bool(os.getenv("OPENAI_API_KEY")),
        "env_openai_api_key_len": len(os.getenv("OPENAI_API_KEY") or ""),
    }
    # 1. Test import embedding module
    try:
        from app.embedding import embed, _get_client
        report["embedding_module_import"] = "ok"
        client = _get_client()
        report["embedding_client_init"] = "ok" if client else "FAIL - client None"
    except Exception as e:
        report["embedding_module_import"] = f"ERR: {str(e)[:200]}"
        return report
    # 2. Test embed() sur un texte simple
    try:
        vec = embed("Test diagnostic scanner P1")
        if vec is None:
            report["embed_test_call"] = "FAIL - returned None"
        else:
            report["embed_test_call"] = f"ok - {len(vec)} dims, first={vec[0]:.4f}"
    except Exception as e:
        report["embed_test_call"] = f"EXCEPTION: {str(e)[:300]}"
        return report
    # 3. Test format pgvector
    try:
        vec_str = "[" + ",".join(str(x) for x in vec) + "]"
        report["pgvector_format_len"] = len(vec_str)
        report["pgvector_format_preview"] = vec_str[:80] + "..."
    except Exception as e:
        report["pgvector_format"] = f"ERR: {str(e)[:200]}"
        return report
    # 4. Test INSERT dans odoo_semantic_content
    try:
        with get_pg_conn() as conn:
            cur = conn.cursor()
            cur.execute(
                """INSERT INTO odoo_semantic_content
                   (tenant_id, source_model, source_record_id, content_type,
                    text_content, embedding, metadata, odoo_write_date, updated_at)
                   VALUES (%s, %s, %s, 'record_summary', %s, %s::vector, %s, NOW(), NOW())
                   ON CONFLICT (tenant_id, source_model, source_record_id, content_type)
                   DO UPDATE SET text_content=EXCLUDED.text_content, updated_at=NOW()
                   RETURNING id""",
                ("couffrant", "debug.test", "999999",
                 "Test chunk diagnostic", vec_str, json.dumps({"test": True})),
            )
            row = cur.fetchone()
            conn.commit()
            report["insert_test"] = f"ok - chunk_id={row[0] if row else None}"
            # Cleanup : on supprime ce chunk de test
            cur.execute(
                """DELETE FROM odoo_semantic_content
                   WHERE source_model='debug.test'""")
            conn.commit()
            report["cleanup"] = "ok"
    except Exception as e:
        report["insert_test"] = f"EXCEPTION: {str(e)[:400]}"
        report["insert_trace"] = traceback.format_exc()[:800]
    # 5. Check table structure (dim de la colonne embedding)
    try:
        with get_pg_conn() as conn:
            cur = conn.cursor()
            cur.execute(
                """SELECT atttypmod FROM pg_attribute
                   WHERE attrelid='odoo_semantic_content'::regclass
                     AND attname='embedding'""")
            row = cur.fetchone()
            report["embedding_column_typmod"] = row[0] if row else "N/A"
    except Exception as e:
        report["embedding_column_check"] = f"ERR: {str(e)[:200]}"
    return report


@router.post("/admin/scanner/run/start")
def admin_scanner_run_start(
    request: Request,
    tenant_id: str = "couffrant",
    source: str = "odoo",
    priority_max: int = 1,
    purge_first: bool = True,
    run_type: str = "init",
    _: dict = Depends(require_admin),
):
    """Lance un scan de vectorisation en background thread.

    Phase 3 du Scanner Universel : execute les manifests actifs jusqu a la
    priorite max demandee. priority_max=1 par defaut pour scanner P1 seul.

    Args de query string :
    - tenant_id : defaut 'couffrant'
    - source : defaut 'odoo'
    - priority_max : 1 (P1) / 2 (P1+P2)
    - purge_first : true pour rebuild complet avec purge prealable
    - run_type : 'init' (default) / 'rebuild'

    Retourne {run_id} immediat. Utiliser /admin/scanner/run/status pour poller."""
    try:
        from app.scanner.runner import start_scan_p1
        run_id = start_scan_p1(
            tenant_id=tenant_id, source=source,
            priority_max=priority_max, purge_first=purge_first,
            run_type=run_type,
        )
        return {"status": "started", "run_id": run_id,
                "priority_max": priority_max, "purge_first": purge_first}
    except Exception as e:
        import traceback
        return {"status": "error", "message": str(e)[:300],
                "trace": traceback.format_exc()[:1500]}


@router.get("/admin/scanner/run/status")
def admin_scanner_run_status(
    request: Request, run_id: str,
    _: dict = Depends(require_admin),
):
    """Retourne le statut d un run (en cours ou termine) via orchestrator."""
    try:
        from app.scanner import orchestrator
        from app.scanner.runner import is_run_active
        status = orchestrator.get_run_status(run_id)
        if not status:
            return {"status": "not_found",
                    "message": f"Run {run_id} inconnu"}
        status["thread_alive"] = is_run_active(run_id)
        return status
    except Exception as e:
        return {"status": "error", "message": str(e)[:300]}


@router.post("/admin/scanner/run/stop")
def admin_scanner_run_stop(
    request: Request, run_id: str,
    _: dict = Depends(require_admin),
):
    """Demande l arret propre d un run en cours (bouton Stop).

    Option A validee par Guillaume : le worker finit le modele en cours
    puis s arrete proprement avant le modele suivant. Les chunks deja
    vectorises sont conserves en DB.

    Retourne {ok: bool} - ok=false si le run n existe pas ou est deja
    termine."""
    try:
        from app.scanner import orchestrator
        ok = orchestrator.request_stop(run_id)
        if ok:
            return {"status": "ok", "message": "Stop demande, le worker s arretera apres le modele en cours"}
        return {"status": "not_found",
                "message": f"Run {run_id} introuvable ou deja termine"}
    except Exception as e:
        return {"status": "error", "message": str(e)[:300]}


@router.get("/admin/scanner/run/list")
def admin_scanner_run_list(
    request: Request,
    tenant_id: str = "couffrant",
    limit: int = 10,
    _: dict = Depends(require_admin),
):
    """Liste les N derniers runs d un tenant (tries par started_at DESC).
    Utile pour le bouton Stop qui a besoin de trouver le run en cours."""
    try:
        from app.scanner import orchestrator
        runs = orchestrator.list_recent_runs(tenant_id, limit=limit)
        return {"status": "ok", "runs": runs}
    except Exception as e:
        return {"status": "error", "message": str(e)[:300]}


@router.post("/admin/scanner/run/test-missing")
def admin_scanner_run_test_missing(
    request: Request,
    tenant_id: str = "couffrant",
    source: str = "odoo",
    sample_size: int = 200,
    priority_max: int = 1,
    _: dict = Depends(require_admin),
):
    """Scanner TEST / COMPLET sur modeles manquants ou partiels.

    - sample_size<=1000 : TEST rapide. Selectionne uniquement les modeles
      avec 0 chunks en DB. Objectif : diagnostiquer rapidement.
    - sample_size>=10000 : COMPLET. Selectionne les modeles avec 0 chunks
      OU qui n ont PAS atteint records_count_odoo (donc partiels). Objectif :
      completer la vectorisation apres correction d un manifest.

    - priority_max=1 (default) : modeles P1 uniquement
    - priority_max=2 : P1+P2 (utile pour tester P2 sans toucher P1)

    Toujours :
    - purge_first=False (jamais destructif sur les chunks existants)
    - Les modeles 'OK' (complets) sont skippes (record_limits[m]=0)
    """
    try:
        from app.scanner.runner import start_scan_p1
        from app.database import get_pg_conn
        is_complet = sample_size >= 10000
        # On recupere aussi records_count_odoo pour detecter les partiels
        with get_pg_conn() as conn:
            cur = conn.cursor()
            cur.execute(
                """SELECT cs.model_name,
                          cs.priority,
                          cs.records_count_odoo,
                          COALESCE((SELECT COUNT(*) FROM odoo_semantic_content
                                    WHERE tenant_id=cs.tenant_id
                                      AND source_model=cs.model_name
                                      AND deleted_at IS NULL), 0) AS chunks_db
                   FROM connector_schemas cs
                   WHERE cs.tenant_id=%s AND cs.source=%s
                     AND cs.enabled=TRUE AND cs.priority<=%s""",
                (tenant_id, source, priority_max),
            )
            rows = cur.fetchall()
        # Logique de selection :
        # - mode TEST : manquants = chunks_db == 0
        # - mode COMPLET : manquants = chunks_db == 0 OU chunks_db < records_count_odoo
        #   (en tenant compte des limites applicatives MODEL_RECORD_LIMITS)
        from app.scanner.runner import MODEL_RECORD_LIMITS
        to_scan = []
        ok_models = []
        for model_name, prio, rc_odoo, chunks_db in rows:
            rc_odoo = rc_odoo or 0
            # Limite applicative : plafond eventuel
            app_limit = MODEL_RECORD_LIMITS.get(model_name)
            expected = min(rc_odoo, app_limit) if app_limit and app_limit > 0 else rc_odoo
            if app_limit == 0:
                # Modele explicitement skippe (ex: res.city)
                ok_models.append(model_name)
                continue
            if chunks_db == 0:
                to_scan.append(model_name)
            elif is_complet and chunks_db < (expected * 0.90):
                # Partiel : il manque plus de 10% des records attendus
                # (tolerance 10% alignee sur le seuil OK>=90% du dashboard
                # Integrite, car records_count_odoo est parfois une estimation
                # et certains records n ont pas de display_name donc pas de chunk)
                to_scan.append(model_name)
            else:
                ok_models.append(model_name)
        # Construire record_limits : sample_size pour a-scanner, 0 pour OK (skip)
        record_limits = {m: sample_size for m in to_scan}
        for m in ok_models:
            record_limits[m] = 0
        run_id = start_scan_p1(
            tenant_id=tenant_id, source=source,
            priority_max=priority_max, purge_first=False,
            run_type="test" if not is_complet else "complete",
            record_limits=record_limits,
        )
        return {
            "status": "started", "run_id": run_id,
            "mode": "complete" if is_complet else "test-missing",
            "priority_max": priority_max,
            "sample_size": sample_size,
            "missing_models": to_scan,
            "skipped_models_ok": ok_models,
        }
    except Exception as e:
        import traceback
        return {"status": "error", "message": str(e)[:300],
                "trace": traceback.format_exc()[:1500]}


@router.post("/admin/scanner/purge")
def admin_scanner_purge(
    request: Request,
    tenant_id: str = "couffrant",
    source: str = "odoo",
    confirm: str = "",
    _: dict = Depends(require_admin),
):
    """DANGER : supprime toutes les donnees vectorisees + graphe pour un
    tenant+source. Necessite confirm='yes' pour eviter les erreurs."""
    if confirm != "yes":
        return {"status": "blocked",
                "message": "Operation destructrice. Passer confirm=yes pour confirmer."}
    try:
        from app.scanner.runner import purge_tenant_data
        counts = purge_tenant_data(tenant_id, source)
        return {"status": "ok", "counts": counts}
    except Exception as e:
        return {"status": "error", "message": str(e)[:300]}


@router.post("/admin/scanner/manifests/generate")
def admin_scanner_generate_manifests(
    request: Request,
    tenant_id: str = "couffrant",
    source: str = "odoo",
    _: dict = Depends(require_admin),
):
    """Genere tous les manifests P1+P2 pour un tenant/source depuis Odoo.
    Phase 2 du Scanner Universel (voir docs/raya_scanner_universel_plan.md).

    Fetch les champs de chaque modele via ir.model.fields et classifie
    automatiquement chaque champ (vectorize/edge/metadata/ignore) selon
    son type Odoo. Sauve les manifests dans connector_schemas.

    Duree : ~30-60s pour 31 modeles (appels XML-RPC sequentiels)."""
    try:
        from app.scanner.manifest_generator import generate_all_manifests_from_odoo
        result = generate_all_manifests_from_odoo(tenant_id, source)
        return result
    except Exception as e:
        import traceback
        return {"status": "error", "message": str(e)[:300],
                "trace": traceback.format_exc()[:1500]}


@router.get("/admin/scanner/manifests")
def admin_scanner_list_manifests(
    request: Request,
    tenant_id: str = "couffrant",
    source: str = "odoo",
    _: dict = Depends(require_admin),
):
    """Liste les manifests existants pour un tenant+source, tries par priorite."""
    try:
        from app.scanner.manifest_generator import list_manifests
        manifests = list_manifests(tenant_id, source)
        return {"status": "ok", "count": len(manifests), "manifests": manifests}
    except Exception as e:
        return {"status": "error", "message": str(e)[:300]}


@router.get("/admin/scanner/manifests/{model_name}")
def admin_scanner_get_manifest(
    request: Request,
    model_name: str,
    tenant_id: str = "couffrant",
    source: str = "odoo",
    _: dict = Depends(require_admin),
):
    """Recupere le detail d un manifest specifique (pour edition)."""
    try:
        from app.scanner.manifest_generator import get_manifest
        m = get_manifest(tenant_id, source, model_name)
        if not m:
            return {"status": "not_found",
                    "message": f"Manifest {model_name} absent"}
        return {"status": "ok", "manifest": m}
    except Exception as e:
        return {"status": "error", "message": str(e)[:300]}


@router.patch("/admin/scanner/manifests/{model_name}")
async def admin_scanner_update_manifest(
    request: Request,
    model_name: str,
    tenant_id: str = "couffrant",
    source: str = "odoo",
    _: dict = Depends(require_admin),
):
    """Met a jour un manifest (enabled flag et/ou patch du JSON manifest).

    Body JSON attendu : {"enabled": true/false, "manifest_patch": {...}}"""
    try:
        body = await request.json()
        from app.scanner.manifest_generator import update_manifest
        ok = update_manifest(
            tenant_id, source, model_name,
            enabled=body.get("enabled"),
            manifest_patch=body.get("manifest_patch"),
        )
        if not ok:
            return {"status": "not_found",
                    "message": f"Manifest {model_name} absent"}
        return {"status": "ok"}
    except Exception as e:
        return {"status": "error", "message": str(e)[:300]}


@router.get("/admin/scanner/health")
def admin_scanner_health(request: Request, _: dict = Depends(require_admin)):
    """Verifie l etat du Scanner Universel.

    Retourne :
    - existence des 3 tables (scanner_runs, connector_schemas, vectorization_queue)
    - dernier run par source
    - taille de la queue de vectorisation
    - nombre de schemas actifs par source

    C est le health check de la Phase 1 du Scanner Universel (voir
    docs/raya_scanner_universel_plan.md)."""
    from app.database import get_pg_conn
    result = {"status": "ok", "tables": {}, "runs": {}, "queue": {}, "schemas": {}}
    try:
        with get_pg_conn() as conn:
            cur = conn.cursor()
            # 1. Verifier existence des 3 tables
            for table in ["scanner_runs", "connector_schemas", "vectorization_queue"]:
                cur.execute(
                    """SELECT COUNT(*) FROM information_schema.tables
                       WHERE table_name=%s""", (table,))
                result["tables"][table] = cur.fetchone()[0] > 0
            # 2. Dernier run par source (tous tenants confondus pour l admin)
            cur.execute("""SELECT source, run_type, status, started_at,
                                  finished_at, stats
                           FROM scanner_runs ORDER BY started_at DESC LIMIT 20""")
            result["runs"]["recent"] = [{
                "source": r[0], "run_type": r[1], "status": r[2],
                "started_at": r[3].isoformat() if r[3] else None,
                "finished_at": r[4].isoformat() if r[4] else None,
                "stats": r[5],
            } for r in cur.fetchall()]
            # 3. Queue de vectorisation
            cur.execute("""SELECT
                             COUNT(*) FILTER (WHERE completed_at IS NULL) pending,
                             COUNT(*) FILTER (WHERE completed_at IS NOT NULL) done,
                             COUNT(*) FILTER (WHERE attempts > 0 AND completed_at IS NULL) failed
                           FROM vectorization_queue""")
            row = cur.fetchone()
            result["queue"] = {"pending": row[0], "done": row[1], "failed": row[2]}
            # 4. Schemas enregistres par source
            cur.execute("""SELECT source, COUNT(*) FILTER (WHERE enabled) enabled,
                                  COUNT(*) total FROM connector_schemas
                           GROUP BY source""")
            result["schemas"] = {r[0]: {"enabled": r[1], "total": r[2]}
                                 for r in cur.fetchall()}
        # 5. Statut global : OK si toutes les tables existent
        if not all(result["tables"].values()):
            result["status"] = "missing_tables"
        return result
    except Exception as e:
        import traceback
        return {"status": "error", "message": str(e)[:300],
                "trace": traceback.format_exc()[:1500]}


@router.get("/admin/odoo/introspect/status")
def admin_odoo_introspect_status(
    request: Request,
    run_id: str,
    _: dict = Depends(require_admin),
):
    """Retourne le status d'un run en cours ou son resultat final."""
    try:
        from app.jobs.odoo_introspect import get_run_status
        status = get_run_status(run_id)
        if not status:
            return {"status": "not_found",
                    "message": f"Run {run_id} inconnu (expire ou jamais lance)"}
        return status
    except Exception as e:
        return {"status": "error", "message": str(e)[:300]}


@router.get("/admin/odoo/introspect")
def admin_odoo_introspect(
    request: Request,
    include_empty: bool = False,
    include_system: bool = False,
    fetch_fields_for_top: int = 30,
    _: dict = Depends(require_admin),
):
    """[OBSOLETE — timeout probable] Version synchrone de l'introspection.
    Pour ~300 modeles, peut prendre 2-5 min et depasser le timeout HTTP.
    Preferer /admin/odoo/introspect/start + /admin/odoo/introspect/status."""
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
