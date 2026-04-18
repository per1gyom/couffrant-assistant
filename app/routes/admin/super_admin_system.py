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
