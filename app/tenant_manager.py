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
import re
import json
import unicodedata
from app.database import get_pg_conn

DEFAULT_TENANT = 'couffrant_solar'


def _normalize_tenant_id(value: str) -> str:
    """
    Normalise un identifiant tenant (FIX-TENANT-FORM) :
    - Supprime les accents
    - Convertit en minuscules
    - Remplace espaces et tirets par des underscores
    - Supprime les caractères non autorisés (garde a-z, 0-9, _)
    ex: "Charlotte Solar" -> "charlotte_solar"
        "Énergie Verte" -> "energie_verte"
    """
    nfd = unicodedata.normalize('NFD', value.strip())
    without_accents = ''.join(c for c in nfd if unicodedata.category(c) != 'Mn')
    lowered = without_accents.lower().replace(' ', '_').replace('-', '_')
    return re.sub(r'[^a-z0-9_]', '', lowered)


def create_tenant(tenant_id: str, name: str, settings: dict = None) -> dict:
    if not tenant_id or not name:
        return {"status": "error", "message": "tenant_id et name requis."}
    # Normalisation de l'ID côté serveur (FIX-TENANT-FORM)
    normalized_id = _normalize_tenant_id(tenant_id)
    if not normalized_id:
        return {"status": "error", "message": "Identifiant invalide après normalisation."}
    conn = None
    try:
        conn = get_pg_conn(); c = conn.cursor()
        c.execute("""
            INSERT INTO tenants (id, name, settings) VALUES (%s, %s, %s)
            ON CONFLICT (id) DO UPDATE SET name=EXCLUDED.name, settings=EXCLUDED.settings
        """, (normalized_id, name.strip(), json.dumps(settings or {})))
        conn.commit()
        return {"status": "ok", "tenant_id": normalized_id}
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


def get_user_tenants(username: str) -> list[dict]:
    """
    Retourne tous les tenants auxquels un utilisateur a accès.
    JOIN sur `tenants` pour récupérer le nom.
    Retourne : [{"tenant_id": str, "role": str, "tenant_name": str}]
    Trié par rôle (owner > admin > user) puis par tenant_name.
    Si aucun résultat, retourne [].
    """
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            SELECT uta.tenant_id, uta.role, t.name AS tenant_name
            FROM user_tenant_access uta
            JOIN tenants t ON t.id = uta.tenant_id
            WHERE uta.username = %s
            ORDER BY CASE uta.role
                WHEN 'owner' THEN 1
                WHEN 'admin' THEN 2
                ELSE 3
            END, t.name
        """, (username,))
        return [
            {"tenant_id": r[0], "role": r[1], "tenant_name": r[2]}
            for r in c.fetchall()
        ]
    except Exception:
        return []
    finally:
        if conn:
            conn.close()
