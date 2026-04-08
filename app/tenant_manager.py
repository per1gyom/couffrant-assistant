"""
Gestion des tenants (sociétés clientes) — isolation multi-client.

Architecture :
  tenant = société cliente (Couffrant Solar, Acme Corp, ...)
  Chaque utilisateur appartient à un tenant.
  Données partagées (contacts, consignes) sont scopées par tenant.
  Données personnelles (mémoire, règles) restent par username.
  Config ténant : SharePoint, Odoo, Azure dans settings JSONB.
"""
import json
from app.database import get_pg_conn

DEFAULT_TENANT = 'couffrant_solar'


def create_tenant(tenant_id: str, name: str, settings: dict = None) -> dict:
    """
    Crée ou met à jour un tenant.
    settings possibles :
      sharepoint_folder  : dossier racine SharePoint (défaut: '1_Photovoltaïque')
      odoo_url           : URL de l'instance Odoo
      azure_tenant_id    : tenant Microsoft 365
    """
    if not tenant_id or not name:
        return {"status": "error", "message": "tenant_id et name requis."}
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            INSERT INTO tenants (id, name, settings)
            VALUES (%s, %s, %s)
            ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name, settings = EXCLUDED.settings
        """, (tenant_id.strip(), name.strip(), json.dumps(settings or {})))
        conn.commit()
        return {"status": "ok", "tenant_id": tenant_id}
    except Exception as e:
        return {"status": "error", "message": str(e)[:100]}
    finally:
        if conn: conn.close()


def get_tenant(tenant_id: str) -> dict | None:
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("SELECT id, name, settings, created_at FROM tenants WHERE id = %s", (tenant_id,))
        row = c.fetchone()
        if not row: return None
        return {"id": row[0], "name": row[1], "settings": row[2] or {}, "created_at": str(row[3])}
    except Exception:
        return None
    finally:
        if conn: conn.close()


def list_tenants() -> list:
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("SELECT id, name, settings, created_at FROM tenants ORDER BY created_at")
        return [{"id": r[0], "name": r[1], "settings": r[2] or {}, "created_at": str(r[3])}
                for r in c.fetchall()]
    except Exception:
        return []
    finally:
        if conn: conn.close()


def get_tenant_settings(tenant_id: str) -> dict:
    """Retourne les settings avec valeurs par défaut."""
    tenant = get_tenant(tenant_id)
    defaults = {
        "sharepoint_folder": "1_Photovoltaïque",
        "odoo_url": None,
        "azure_tenant_id": None,
    }
    if not tenant:
        return defaults
    return {**defaults, **(tenant.get("settings") or {})}


def delete_tenant(tenant_id: str) -> dict:
    """Supprime un tenant. Ne supprime pas les données utilisateurs."""
    if tenant_id == DEFAULT_TENANT:
        return {"status": "error", "message": "Impossible de supprimer le tenant par défaut."}
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("DELETE FROM tenants WHERE id = %s", (tenant_id,))
        if c.rowcount == 0:
            return {"status": "error", "message": "Tenant introuvable."}
        conn.commit()
        return {"status": "ok", "message": f"Tenant '{tenant_id}' supprimé."}
    except Exception as e:
        return {"status": "error", "message": str(e)[:100]}
    finally:
        if conn: conn.close()


def ensure_default_tenant():
    """Crée le tenant Couffrant Solar s'il n'existe pas encore."""
    create_tenant(DEFAULT_TENANT, "Couffrant Solar", {
        "sharepoint_folder": "1_Photovoltaïque"
    })
