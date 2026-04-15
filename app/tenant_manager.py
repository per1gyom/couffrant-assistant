"""
Gestion des tenants (sociétés clientes).

Settings tenant (JSONB) :
  email_provider   : "microsoft" | "google" | "both" | "" (configuré après création)
  sharepoint_folder: dossier racine SharePoint (configuré après création)
  odoo_url         : URL Odoo
  azure_tenant_id  : tenant Microsoft 365
  google_domain    : domaine Google Workspace
  custom_tools     : liste [{id, label, description, config_fields}]
  legal_form       : forme juridique (SAS, SARL, etc.)
  siret            : 14 chiffres
  address          : adresse du siège social
"""
import re
import json
import unicodedata
from app.database import get_pg_conn

DEFAULT_TENANT = 'couffrant_solar'


def _normalize_tenant_id(value: str) -> str:
    """
    Normalise un identifiant tenant :
    - Supprime les accents
    - Convertit en minuscules
    - Remplace espaces et tirets par des underscores
    - Supprime les caractères non autorisés
    """
    nfd = unicodedata.normalize('NFD', value.strip())
    without_accents = ''.join(c for c in nfd if unicodedata.category(c) != 'Mn')
    lowered = without_accents.lower().replace(' ', '_').replace('-', '_')
    return re.sub(r'[^a-z0-9_]', '', lowered)


def create_tenant(tenant_id: str, name: str, settings: dict = None) -> dict:
    """
    Crée un tenant.
    BUG 5 : vérifie d'abord si l'ID existe — retourne une erreur si oui (plus d'écrasement silencieux).
    """
    if not tenant_id or not name:
        return {"status": "error", "message": "tenant_id et name requis."}
    normalized_id = _normalize_tenant_id(tenant_id)
    if not normalized_id:
        return {"status": "error", "message": "Identifiant invalide après normalisation."}
    conn = None
    try:
        conn = get_pg_conn(); c = conn.cursor()
        # BUG 5 : vérification d'existence avant INSERT
        c.execute("SELECT id FROM tenants WHERE id = %s", (normalized_id,))
        if c.fetchone():
            return {"status": "error",
                    "message": f"Le tenant '{normalized_id}' existe déjà."}
        c.execute(
            "INSERT INTO tenants (id, name, settings) VALUES (%s, %s, %s)",
            (normalized_id, name.strip(), json.dumps(settings or {}))
        )
        conn.commit()
        return {"status": "ok", "tenant_id": normalized_id}
    except Exception as e:
        return {"status": "error", "message": str(e)[:100]}
    finally:
        if conn: conn.close()


def update_tenant(tenant_id: str, name: str = None, settings: dict = None) -> dict:
    """Met à jour un tenant existant (nom et/ou settings complets)."""
    conn = None
    try:
        conn = get_pg_conn(); c = conn.cursor()
        if name is not None:
            c.execute("UPDATE tenants SET name=%s WHERE id=%s", (name.strip(), tenant_id))
        if settings is not None:
            c.execute("UPDATE tenants SET settings=%s WHERE id=%s",
                      (json.dumps(settings), tenant_id))
        conn.commit()
        return {"status": "ok", "tenant_id": tenant_id}
    except Exception as e:
        return {"status": "error", "message": str(e)[:100]}
    finally:
        if conn: conn.close()


def get_tenant(tenant_id: str) -> dict | None:
    conn = None
    try:
        conn = get_pg_conn(); c = conn.cursor()
        c.execute("SELECT id, name, settings, created_at FROM tenants WHERE id=%s", (tenant_id,))
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
        conn = get_pg_conn(); c = conn.cursor()
        c.execute("SELECT id, name, settings, created_at FROM tenants ORDER BY created_at")
        return [{"id": r[0], "name": r[1], "settings": r[2] or {}, "created_at": str(r[3])}
                for r in c.fetchall()]
    except Exception:
        return []
    finally:
        if conn: conn.close()


def get_tenant_settings(tenant_id: str) -> dict:
    """
    Retourne les settings du tenant avec des défauts neutres.
    BUG 4 : plus de présupposition sur email_provider ou sharepoint_folder.
    """
    defaults = {
        "email_provider": "",        # pas de présupposition
        "sharepoint_folder": "",     # pas de présupposition
        "odoo_url": None,
        "azure_tenant_id": None,
        "google_domain": None,
        "custom_tools": [],
        "legal_form": "",
        "siret": "",
        "address": "",
    }
    tenant = get_tenant(tenant_id)
    if not tenant: return defaults
    return {**defaults, **(tenant.get("settings") or {})}


def update_tenant_settings(tenant_id: str, updates: dict) -> dict:
    """Met à jour partiellement les settings d'un tenant."""
    current = get_tenant_settings(tenant_id)
    merged = {**current, **updates}
    tenant = get_tenant(tenant_id)
    if not tenant:
        return {"status": "error", "message": "Tenant introuvable."}
    return update_tenant(tenant_id, name=tenant["name"], settings=merged)


def add_custom_tool(tenant_id: str, tool_id: str, label: str,
                    description: str = "", config_fields: list = None) -> dict:
    settings = get_tenant_settings(tenant_id)
    tools = settings.get("custom_tools", [])
    if any(t["id"] == tool_id for t in tools):
        return {"status": "error", "message": f"L'outil '{tool_id}' existe déjà."}
    tools.append({"id": tool_id, "label": label, "description": description,
                  "config_fields": config_fields or [{"name": "api_key", "label": "API Key / Token", "type": "password"}]})
    return update_tenant_settings(tenant_id, {"custom_tools": tools})


def remove_custom_tool(tenant_id: str, tool_id: str) -> dict:
    settings = get_tenant_settings(tenant_id)
    tools = [t for t in settings.get("custom_tools", []) if t["id"] != tool_id]
    return update_tenant_settings(tenant_id, {"custom_tools": tools})


def uses_microsoft(tenant_id: str) -> bool:
    return get_tenant_settings(tenant_id).get("email_provider", "") in ("microsoft", "both")


def uses_google(tenant_id: str) -> bool:
    return get_tenant_settings(tenant_id).get("email_provider", "") in ("google", "both")


def delete_tenant(tenant_id: str) -> dict:
    """
    Supprime un tenant.
    BUG 2 : vérifie qu'il n'y a plus d'utilisateurs rattachés avant de supprimer.
    """
    if tenant_id == DEFAULT_TENANT:
        return {"status": "error", "message": "Impossible de supprimer le tenant par défaut."}
    conn = None
    try:
        conn = get_pg_conn(); c = conn.cursor()
        # BUG 2 : vérification des utilisateurs rattachés
        c.execute("SELECT COUNT(*) FROM users WHERE tenant_id = %s", (tenant_id,))
        user_count = c.fetchone()[0]
        if user_count > 0:
            return {
                "status": "error",
                "message": (
                    f"Impossible de supprimer : {user_count} utilisateur(s) encore rattaché(s). "
                    "Réaffectez-les à un autre tenant avant de supprimer."
                ),
            }
        c.execute("DELETE FROM tenants WHERE id=%s", (tenant_id,))
        if c.rowcount == 0:
            return {"status": "error", "message": "Tenant introuvable."}
        conn.commit()
        return {"status": "ok", "message": f"Tenant '{tenant_id}' supprimé."}
    except Exception as e:
        return {"status": "error", "message": str(e)[:100]}
    finally:
        if conn: conn.close()


def ensure_default_tenant():
    """Crée le tenant par défaut s'il n'existe pas."""
    conn = None
    try:
        conn = get_pg_conn(); c = conn.cursor()
        c.execute("SELECT id FROM tenants WHERE id = %s", (DEFAULT_TENANT,))
        if c.fetchone():
            return  # déjà présent
        c.execute(
            "INSERT INTO tenants (id, name, settings) VALUES (%s, %s, %s)",
            (DEFAULT_TENANT, "Couffrant Solar",
             json.dumps({"email_provider": "microsoft",
                         "sharepoint_site": "Commun",
                         "sharepoint_folder": "1_Photovoltaïque",
                         "custom_tools": []}))
        )
        conn.commit()
    except Exception as e:
        print(f"[Tenant] ensure_default_tenant: {e}")
    finally:
        if conn: conn.close()


def get_user_tenants(username: str) -> list[dict]:
    """
    Retourne tous les tenants auxquels un utilisateur a accès.
    Retourne : [{"tenant_id": str, "role": str, "tenant_name": str}]
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
