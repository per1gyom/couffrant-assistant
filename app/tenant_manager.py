"""
Gestion des tenants (sociétés clientes).

Settings tenant (JSONB) :
  email_provider   : "microsoft" | "google" | "both"
  sharepoint_folder: dossier racine SharePoint
  odoo_url         : URL Odoo
  azure_tenant_id  : tenant Microsoft 365
  google_domain    : domaine Google Workspace
  custom_tools     : liste [{id, label, description, config_fields}]
                     Outils tiers à connecter (Salesforce, Monday, HubSpot...)
"""
import json
from app.database import get_pg_conn

DEFAULT_TENANT = 'couffrant_solar'


def create_tenant(tenant_id: str, name: str, settings: dict = None) -> dict:
    if not tenant_id or not name:
        return {"status": "error", "message": "tenant_id et name requis."}
    conn = None
    try:
        conn = get_pg_conn(); c = conn.cursor()
        c.execute("""
            INSERT INTO tenants (id, name, settings) VALUES (%s, %s, %s)
            ON CONFLICT (id) DO UPDATE SET name=EXCLUDED.name, settings=EXCLUDED.settings
        """, (tenant_id.strip(), name.strip(), json.dumps(settings or {})))
        conn.commit()
        return {"status": "ok", "tenant_id": tenant_id}
    except Exception as e: return {"status": "error", "message": str(e)[:100]}
    finally:
        if conn: conn.close()


def get_tenant(tenant_id: str) -> dict | None:
    conn = None
    try:
        conn = get_pg_conn(); c = conn.cursor()
        c.execute("SELECT id, name, settings, created_at FROM tenants WHERE id=%s", (tenant_id,))
        row = c.fetchone()
        if not row: return None
        return {"id":row[0],"name":row[1],"settings":row[2] or {},"created_at":str(row[3])}
    except Exception: return None
    finally:
        if conn: conn.close()


def list_tenants() -> list:
    conn = None
    try:
        conn = get_pg_conn(); c = conn.cursor()
        c.execute("SELECT id, name, settings, created_at FROM tenants ORDER BY created_at")
        return [{"id":r[0],"name":r[1],"settings":r[2] or {},"created_at":str(r[3])} for r in c.fetchall()]
    except Exception: return []
    finally:
        if conn: conn.close()


def get_tenant_settings(tenant_id: str) -> dict:
    defaults = {
        "email_provider": "microsoft",
        "sharepoint_folder": "1_Photovoltaïque",
        "odoo_url": None,
        "azure_tenant_id": None,
        "google_domain": None,
        "custom_tools": [],
    }
    tenant = get_tenant(tenant_id)
    if not tenant: return defaults
    return {**defaults, **(tenant.get("settings") or {})}


def update_tenant_settings(tenant_id: str, updates: dict) -> dict:
    """Met à jour partiellement les settings d'un tenant."""
    current = get_tenant_settings(tenant_id)
    merged = {**current, **updates}
    return create_tenant(tenant_id, (get_tenant(tenant_id) or {}).get("name", tenant_id), merged)


def add_custom_tool(tenant_id: str, tool_id: str, label: str,
                   description: str = "", config_fields: list = None) -> dict:
    """
    Ajoute un outil custom au tenant.
    config_fields : liste de champs de config [{name, label, type}]
      ex: [{"name":"api_key","label":"API Key","type":"password"}]
    """
    settings = get_tenant_settings(tenant_id)
    tools = settings.get("custom_tools", [])
    if any(t["id"] == tool_id for t in tools):
        return {"status": "error", "message": f"L'outil '{tool_id}' existe déjà."}
    tools.append({"id": tool_id, "label": label, "description": description,
                  "config_fields": config_fields or [{"name": "api_key", "label": "API Key / Token", "type": "password"}]})
    settings["custom_tools"] = tools
    return update_tenant_settings(tenant_id, {"custom_tools": tools})


def remove_custom_tool(tenant_id: str, tool_id: str) -> dict:
    settings = get_tenant_settings(tenant_id)
    tools = [t for t in settings.get("custom_tools", []) if t["id"] != tool_id]
    return update_tenant_settings(tenant_id, {"custom_tools": tools})


def uses_microsoft(tenant_id: str) -> bool:
    return get_tenant_settings(tenant_id).get("email_provider", "microsoft") in ("microsoft", "both")

def uses_google(tenant_id: str) -> bool:
    return get_tenant_settings(tenant_id).get("email_provider", "microsoft") in ("google", "both")


def delete_tenant(tenant_id: str) -> dict:
    if tenant_id == DEFAULT_TENANT:
        return {"status": "error", "message": "Impossible de supprimer le tenant par défaut."}
    conn = None
    try:
        conn = get_pg_conn(); c = conn.cursor()
        c.execute("DELETE FROM tenants WHERE id=%s", (tenant_id,))
        if c.rowcount == 0: return {"status": "error", "message": "Tenant introuvable."}
        conn.commit()
        return {"status": "ok", "message": f"Tenant '{tenant_id}' supprimé."}
    except Exception as e: return {"status": "error", "message": str(e)[:100]}
    finally:
        if conn: conn.close()


def ensure_default_tenant():
    create_tenant(DEFAULT_TENANT, "Couffrant Solar", {
        "email_provider": "microsoft",
        "sharepoint_folder": "1_Photovoltaïque",
        "custom_tools": [],
    })
