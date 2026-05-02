"""
Endpoints admin pour configurer les regles d inclusion/exclusion des
racines Drive (SharePoint, Google Drive, NAS, etc.) du tenant.

Phase Drive multi-racines (02/05/2026).
Cf. docs/journal_02mai_2026_drive_multi_racines.md

PERMISSIONS :
  - Tenant admin : peut configurer son propre tenant.
  - Super admin : peut acceder pour debug/depannage tous tenants.

ENDPOINTS API (JSON) :
  GET  /admin/drive_config/drives/{tenant_id}
       -> liste des connexions drive du tenant + leurs etats
  GET  /admin/drive_config/folders/{connection_id}?path=
       -> arborescence d un drive (lazy-load par path)
  GET  /admin/drive_config/rules/{connection_id}
       -> liste des regles configurees pour cette connexion
  POST /admin/drive_config/rules/{connection_id}
       -> ajoute une regle (include/exclude) sur un path
  DELETE /admin/drive_config/rules/{rule_id}
       -> supprime une regle
  GET  /admin/drive_config/preview/{connection_id}?path=
       -> simule "Raya verra-t-elle ce path ?" + explication

PAGES HTML :
  GET  /admin/drive_config             -> page principale (liste drives)
  GET  /admin/drive_config/configure/{connection_id}  -> config detaillee
"""
from typing import Optional
from fastapi import APIRouter, Request, Depends, Body
from fastapi.responses import JSONResponse, HTMLResponse

from app.routes.deps import require_admin
from app.logging_config import get_logger

logger = get_logger("raya.admin_drive_config")
router = APIRouter(tags=["admin_drive_config"])


# =====================================================================
# Helpers DB
# =====================================================================

def _list_drive_connections(tenant_id: str) -> list:
    """Retourne les connexions de type drive/sharepoint/google_drive
    pour ce tenant, avec leurs metadonnees principales et l etat des
    regles configurees.
    """
    from app.database import get_pg_conn

    rows = []
    with get_pg_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT tc.id, tc.tool_type, tc.label, tc.status,
                   tc.config, tc.created_at,
                   (SELECT COUNT(*) FROM tenant_drive_blacklist tdb
                    WHERE tdb.connection_id = tc.id AND tdb.scope='tenant')
                   AS rules_count
            FROM tenant_connections tc
            WHERE tc.tenant_id = %s
              AND tc.tool_type IN ('drive', 'sharepoint', 'google_drive')
            ORDER BY tc.id ASC
            """,
            (tenant_id,),
        )
        for r in cur.fetchall():
            row = dict(r) if isinstance(r, dict) else {
                "id": r[0], "tool_type": r[1], "label": r[2],
                "status": r[3], "config": r[4], "created_at": r[5],
                "rules_count": r[6],
            }
            rows.append(row)
    return rows


def _list_drive_roots(tenant_id: str) -> list:
    """Retourne les racines surveillees pour ce tenant (table drive_folders)."""
    from app.database import get_pg_conn

    rows = []
    with get_pg_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, provider, folder_name, site_name, drive_id,
                   folder_id, folder_path, enabled, last_full_scan_at
            FROM drive_folders
            WHERE tenant_id = %s
            ORDER BY id ASC
            """,
            (tenant_id,),
        )
        for r in cur.fetchall():
            row = dict(r) if isinstance(r, dict) else {
                "id": r[0], "provider": r[1], "folder_name": r[2],
                "site_name": r[3], "drive_id": r[4], "folder_id": r[5],
                "folder_path": r[6], "enabled": r[7],
                "last_full_scan_at": r[8],
            }
            rows.append(row)
    return rows


def _list_rules_for_connection(connection_id: int) -> list:
    """Retourne les regles configurees pour cette connexion."""
    from app.database import get_pg_conn

    rows = []
    with get_pg_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, folder_path, rule_type, scope, owner_username,
                   reason, created_by, created_at
            FROM tenant_drive_blacklist
            WHERE connection_id = %s
            ORDER BY length(folder_path) ASC, folder_path ASC
            """,
            (connection_id,),
        )
        for r in cur.fetchall():
            row = dict(r) if isinstance(r, dict) else {
                "id": r[0], "folder_path": r[1], "rule_type": r[2],
                "scope": r[3], "owner_username": r[4],
                "reason": r[5], "created_by": r[6], "created_at": r[7],
            }
            rows.append(row)
    return rows


def _get_connection_meta(connection_id: int) -> Optional[dict]:
    """Retourne id/tenant_id/tool_type/label/config d une connexion."""
    from app.database import get_pg_conn

    with get_pg_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, tenant_id, tool_type, label, status, config
            FROM tenant_connections WHERE id = %s
            """,
            (connection_id,),
        )
        r = cur.fetchone()
        if not r:
            return None
        return dict(r) if isinstance(r, dict) else {
            "id": r[0], "tenant_id": r[1], "tool_type": r[2],
            "label": r[3], "status": r[4], "config": r[5],
        }


def _can_access_tenant(admin: dict, tenant_id: str) -> bool:
    """Verifie qu un admin peut acceder a la config d un tenant donne.

    - super_admin : oui pour tous tenants (debug Guillaume)
    - tenant admin : seulement son propre tenant
    """
    if not admin:
        return False
    scope = admin.get("scope", "")
    if scope == "super_admin":
        return True
    user_tenant = admin.get("tenant_id") or ""
    return user_tenant == tenant_id


# =====================================================================
# ENDPOINTS API JSON
# =====================================================================

@router.get("/admin/drive_config/drives/{tenant_id}")
def api_list_drives(
    tenant_id: str,
    admin: dict = Depends(require_admin),
):
    """Liste les connexions drive d un tenant + leurs racines + nb regles."""
    if not _can_access_tenant(admin, tenant_id):
        return JSONResponse(
            {"status": "error", "message": "Acces refuse pour ce tenant"},
            status_code=403,
        )
    try:
        connections = _list_drive_connections(tenant_id)
        roots = _list_drive_roots(tenant_id)
        return {
            "status": "ok",
            "tenant_id": tenant_id,
            "connections": connections,
            "roots": roots,
        }
    except Exception as e:
        logger.exception("[admin_drive_config] api_list_drives crash")
        return JSONResponse(
            {"status": "error", "message": str(e)[:300]},
            status_code=500,
        )


@router.get("/admin/drive_config/rules/{connection_id}")
def api_list_rules(
    connection_id: int,
    admin: dict = Depends(require_admin),
):
    """Liste les regles configurees pour cette connexion."""
    meta = _get_connection_meta(connection_id)
    if not meta:
        return JSONResponse(
            {"status": "error", "message": "Connexion introuvable"},
            status_code=404,
        )
    if not _can_access_tenant(admin, meta["tenant_id"]):
        return JSONResponse(
            {"status": "error", "message": "Acces refuse pour ce tenant"},
            status_code=403,
        )
    try:
        rules = _list_rules_for_connection(connection_id)
        return {
            "status": "ok",
            "connection": meta,
            "rules": rules,
        }
    except Exception as e:
        logger.exception("[admin_drive_config] api_list_rules crash")
        return JSONResponse(
            {"status": "error", "message": str(e)[:300]},
            status_code=500,
        )


@router.post("/admin/drive_config/rules/{connection_id}")
def api_add_rule(
    connection_id: int,
    payload: dict = Body(...),
    admin: dict = Depends(require_admin),
):
    """Ajoute une regle include/exclude.

    payload = {
      "folder_path": "Drive Direction/RH",
      "rule_type": "exclude",
      "reason": "RH confidentiel"
    }
    """
    meta = _get_connection_meta(connection_id)
    if not meta:
        return JSONResponse(
            {"status": "error", "message": "Connexion introuvable"},
            status_code=404,
        )
    if not _can_access_tenant(admin, meta["tenant_id"]):
        return JSONResponse(
            {"status": "error", "message": "Acces refuse pour ce tenant"},
            status_code=403,
        )

    folder_path = (payload.get("folder_path") or "").strip().strip("/")
    rule_type = (payload.get("rule_type") or "exclude").lower()
    reason = (payload.get("reason") or "").strip() or None

    if not folder_path:
        return JSONResponse(
            {"status": "error", "message": "folder_path requis"},
            status_code=400,
        )
    if rule_type not in ("include", "exclude"):
        return JSONResponse(
            {"status": "error", "message": "rule_type doit etre include ou exclude"},
            status_code=400,
        )

    from app.database import get_pg_conn

    try:
        with get_pg_conn() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO tenant_drive_blacklist
                  (tenant_id, connection_id, folder_path,
                   rule_type, scope, reason, created_by)
                VALUES (%s, %s, %s, %s, 'tenant', %s, %s)
                ON CONFLICT (connection_id, folder_path)
                DO UPDATE SET
                    rule_type = EXCLUDED.rule_type,
                    reason = EXCLUDED.reason,
                    created_by = EXCLUDED.created_by
                RETURNING id
                """,
                (
                    meta["tenant_id"],
                    connection_id,
                    folder_path,
                    rule_type,
                    reason,
                    admin.get("username", "unknown"),
                ),
            )
            row = cur.fetchone()
            new_id = row[0] if not isinstance(row, dict) else row.get("id")
            conn.commit()
        logger.info(
            "[admin_drive_config] rule %s ajoutee/maj : conn=%s path=%s type=%s par %s",
            new_id, connection_id, folder_path, rule_type,
            admin.get("username"),
        )
        return {"status": "ok", "rule_id": new_id}
    except Exception as e:
        logger.exception("[admin_drive_config] api_add_rule crash")
        return JSONResponse(
            {"status": "error", "message": str(e)[:300]},
            status_code=500,
        )


@router.delete("/admin/drive_config/rules/{rule_id}")
def api_delete_rule(
    rule_id: int,
    admin: dict = Depends(require_admin),
):
    """Supprime une regle. Verifie l acces tenant via la regle."""
    from app.database import get_pg_conn

    try:
        with get_pg_conn() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT tenant_id FROM tenant_drive_blacklist WHERE id = %s",
                (rule_id,),
            )
            r = cur.fetchone()
            if not r:
                return JSONResponse(
                    {"status": "error", "message": "Regle introuvable"},
                    status_code=404,
                )
            tenant_id = r[0] if not isinstance(r, dict) else r.get("tenant_id")
            if not _can_access_tenant(admin, tenant_id):
                return JSONResponse(
                    {"status": "error", "message": "Acces refuse"},
                    status_code=403,
                )
            cur.execute(
                "DELETE FROM tenant_drive_blacklist WHERE id = %s",
                (rule_id,),
            )
            conn.commit()
        logger.info(
            "[admin_drive_config] rule %s supprimee par %s",
            rule_id, admin.get("username"),
        )
        return {"status": "ok"}
    except Exception as e:
        logger.exception("[admin_drive_config] api_delete_rule crash")
        return JSONResponse(
            {"status": "error", "message": str(e)[:300]},
            status_code=500,
        )


@router.get("/admin/drive_config/preview/{connection_id}")
def api_preview_path(
    connection_id: int,
    path: str = "",
    admin: dict = Depends(require_admin),
):
    """Simule la decision is_path_indexable pour un path donne.

    Permet a l admin de tester ses regles avant de scanner.
    """
    meta = _get_connection_meta(connection_id)
    if not meta:
        return JSONResponse(
            {"status": "error", "message": "Connexion introuvable"},
            status_code=404,
        )
    if not _can_access_tenant(admin, meta["tenant_id"]):
        return JSONResponse(
            {"status": "error", "message": "Acces refuse"},
            status_code=403,
        )
    try:
        from app.connectors.drive_path_rules import explain_path_decision
        explanation = explain_path_decision(connection_id, path)
        return {"status": "ok", "explanation": explanation}
    except Exception as e:
        logger.exception("[admin_drive_config] api_preview_path crash")
        return JSONResponse(
            {"status": "error", "message": str(e)[:300]},
            status_code=500,
        )


# =====================================================================
# PAGES HTML
# =====================================================================

# Style commun aux pages admin (reutilise le pattern admin_jobs_trigger)
_HTML_HEAD = """<!DOCTYPE html>
<html lang="fr"><head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, sans-serif;
         max-width: 1100px; margin: 24px auto; padding: 0 24px;
         color: #2c3e50; background: #f8f9fa; }}
  h1 {{ font-size: 22px; margin-bottom: 6px; }}
  h2 {{ font-size: 17px; margin-top: 28px; color: #34495e; }}
  .breadcrumb {{ font-size: 13px; color: #7f8c8d; margin-bottom: 18px; }}
  .breadcrumb a {{ color: #3498db; text-decoration: none; }}
  .card {{ background: white; border-radius: 8px; padding: 18px;
          margin-bottom: 14px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); }}
  .card-title {{ font-weight: 600; font-size: 15px; }}
  .card-meta {{ font-size: 12px; color: #7f8c8d; margin-top: 4px; }}
  .badge {{ display: inline-block; padding: 2px 8px; border-radius: 4px;
           font-size: 11px; font-weight: 500; }}
  .badge-include {{ background: #d4edda; color: #155724; }}
  .badge-exclude {{ background: #f8d7da; color: #721c24; }}
  .badge-tenant {{ background: #e8f4fd; color: #0c5494; }}
  .badge-empty {{ background: #f5f5f5; color: #7f8c8d; }}
  .btn {{ display: inline-block; padding: 6px 14px; border-radius: 4px;
         border: 1px solid #3498db; background: white; color: #3498db;
         cursor: pointer; font-size: 13px; text-decoration: none; }}
  .btn:hover {{ background: #3498db; color: white; }}
  .btn-primary {{ background: #3498db; color: white; }}
  .btn-primary:hover {{ background: #2980b9; border-color: #2980b9; }}
  .btn-danger {{ border-color: #e74c3c; color: #e74c3c; }}
  .btn-danger:hover {{ background: #e74c3c; color: white; }}
  table {{ width: 100%; border-collapse: collapse; margin-top: 8px; }}
  th, td {{ text-align: left; padding: 8px 10px; border-bottom: 1px solid #ecf0f1;
           font-size: 13px; }}
  th {{ background: #f8f9fa; font-weight: 600; color: #34495e; }}
  .info {{ background: #e8f4fd; padding: 10px 14px; border-radius: 4px;
          margin-bottom: 12px; font-size: 13px; color: #0c5494; }}
  .warn {{ background: #fef9e7; padding: 10px 14px; border-radius: 4px;
          margin-bottom: 12px; font-size: 13px; color: #7d6608; }}
  code {{ background: #f5f5f5; padding: 1px 5px; border-radius: 3px;
         font-size: 12px; }}
  input[type=text] {{ padding: 6px 10px; border: 1px solid #bdc3c7;
                     border-radius: 4px; font-size: 13px; width: 320px; }}
  select {{ padding: 6px 10px; border: 1px solid #bdc3c7; border-radius: 4px;
           font-size: 13px; }}
</style>
</head><body>
"""


@router.get("/admin/drive_config", response_class=HTMLResponse)
def page_drive_config_home(
    request: Request,
    admin: dict = Depends(require_admin),
):
    """Page d accueil : liste des connexions drive du tenant courant."""
    # Tenant a afficher : pour super_admin, par defaut son propre tenant ;
    # pour admin tenant : forcement le sien.
    tenant_id = admin.get("tenant_id") or "couffrant_solar"

    try:
        connections = _list_drive_connections(tenant_id)
        roots = _list_drive_roots(tenant_id)
    except Exception as e:
        logger.exception("[admin_drive_config] page_home crash")
        return HTMLResponse(
            f"<h1>Erreur</h1><pre>{str(e)[:500]}</pre>",
            status_code=500,
        )

    body = _HTML_HEAD.format(title="Configuration Drive - Raya")
    body += f"""
<div class="breadcrumb">Configuration Drive / Vue d ensemble</div>
<h1>📁 Configuration des dossiers Drive</h1>
<div class="info">
Ici tu choisis quels dossiers de tes drives connectes Raya peut consulter.
La regle est simple : <b>le chemin le plus long gagne</b>. Tu inclus
un dossier, tu peux exclure des sous-dossiers, et re-inclure encore plus profond.
</div>

<h2>Tenant : <code>{tenant_id}</code></h2>
"""

    if not connections:
        body += """
<div class="card">
<div class="warn">
Aucune connexion Drive trouvee pour ce tenant. Connecte d abord un drive
SharePoint, Google Drive ou autre via la page de configuration des connexions.
</div>
</div>
"""
    else:
        for conn in connections:
            cid = conn["id"]
            ttype = conn["tool_type"]
            label = conn.get("label") or "Sans nom"
            status = conn.get("status") or "unknown"
            n_rules = conn.get("rules_count") or 0
            cfg = conn.get("config") or {}
            site_name = cfg.get("site_name", "") if isinstance(cfg, dict) else ""

            badge_class = "badge-include" if status == "connected" else "badge-empty"
            rules_label = (f"{n_rules} regle(s) configuree(s)"
                           if n_rules else "Aucune regle")

            body += f"""
<div class="card">
<div class="card-title">
  📁 {label}
  <span class="badge {badge_class}">{status}</span>
  <span class="badge badge-tenant">{ttype}</span>
</div>
<div class="card-meta">
  Connection ID: <code>{cid}</code>
  {' / Site : <code>' + site_name + '</code>' if site_name else ''}
  <br>{rules_label}
</div>
<div style="margin-top: 12px;">
  <a class="btn btn-primary" href="/admin/drive_config/configure/{cid}">
    Configurer en detail
  </a>
</div>
</div>
"""

    if roots:
        body += """
<h2>Racines actuellement surveillees</h2>
<div class="card">
<table>
<thead><tr>
  <th>Provider</th><th>Site</th><th>Dossier</th><th>Path</th>
  <th>Enabled</th><th>Dernier scan</th>
</tr></thead>
<tbody>
"""
        for r in roots:
            last_scan = r.get("last_full_scan_at")
            last_scan_str = (last_scan.strftime("%Y-%m-%d %H:%M")
                             if last_scan else "-")
            body += (
                "<tr>"
                f"<td>{r.get('provider', '?')}</td>"
                f"<td>{r.get('site_name') or '-'}</td>"
                f"<td>{r.get('folder_name') or '-'}</td>"
                f"<td><code>{r.get('folder_path') or '-'}</code></td>"
                f"<td>{'✅' if r.get('enabled') else '❌'}</td>"
                f"<td>{last_scan_str}</td>"
                "</tr>"
            )
        body += "</tbody></table></div>"

    body += "</body></html>"
    return HTMLResponse(body)


@router.get(
    "/admin/drive_config/configure/{connection_id}",
    response_class=HTMLResponse,
)
def page_drive_configure(
    connection_id: int,
    admin: dict = Depends(require_admin),
):
    """Page de configuration detaillee d une connexion drive."""
    meta = _get_connection_meta(connection_id)
    if not meta:
        return HTMLResponse("<h1>Connexion introuvable</h1>", status_code=404)
    if not _can_access_tenant(admin, meta["tenant_id"]):
        return HTMLResponse("<h1>Acces refuse</h1>", status_code=403)

    rules = _list_rules_for_connection(connection_id)
    label = meta.get("label") or "Sans nom"
    ttype = meta.get("tool_type") or "?"

    body = _HTML_HEAD.format(title=f"Configuration {label} - Raya")
    body += f"""
<div class="breadcrumb">
  <a href="/admin/drive_config">Configuration Drive</a> /
  Configuration de <b>{label}</b>
</div>
<h1>📁 {label}</h1>
<div class="card-meta">
  Type : <code>{ttype}</code> /
  Connection ID : <code>{connection_id}</code> /
  Tenant : <code>{meta['tenant_id']}</code>
</div>

<div class="info">
<b>Regle "le chemin le plus long gagne"</b> :<br>
- Inclus <code>Drive Direction/Comptabilite</code> -> tout indexe sous ce dossier<br>
- Exclus <code>Drive Direction/Comptabilite/Salaires</code> -> sauf ce sous-dossier<br>
- Inclus <code>Drive Direction/Comptabilite/Salaires/Public</code> -> sauf ce sous-sous-dossier
</div>

<h2>Regles configurees ({len(rules)})</h2>
<div class="card">
"""

    if not rules:
        body += "<div class='warn'>Aucune regle. Par defaut, seules les racines surveillees seront indexees.</div>"
    else:
        body += """
<table>
<thead><tr>
  <th>Path</th><th>Type</th><th>Scope</th>
  <th>Raison</th><th>Cree par</th><th>Action</th>
</tr></thead>
<tbody>
"""
        for r in rules:
            badge_cls = ("badge-include" if r["rule_type"] == "include"
                         else "badge-exclude")
            rid = r["id"]
            body += (
                "<tr>"
                f"<td><code>{r['folder_path']}</code></td>"
                f"<td><span class='badge {badge_cls}'>{r['rule_type']}</span></td>"
                f"<td><span class='badge badge-tenant'>{r['scope']}</span></td>"
                f"<td>{r.get('reason') or '-'}</td>"
                f"<td>{r.get('created_by') or '-'}</td>"
                f"<td><button class='btn btn-danger' onclick='deleteRule({rid})'>Supprimer</button></td>"
                "</tr>"
            )
        body += "</tbody></table>"
    body += "</div>"

    # Formulaire d ajout
    body += f"""
<h2>Ajouter une regle</h2>
<div class="card">
<form id="addForm" onsubmit="addRule(event); return false;">
  <div style="margin-bottom: 10px;">
    <label>Chemin : </label>
    <input type="text" id="folderPath" placeholder="ex: Drive Direction/RH">
  </div>
  <div style="margin-bottom: 10px;">
    <label>Type : </label>
    <select id="ruleType">
      <option value="exclude">Exclure (ne pas indexer)</option>
      <option value="include">Inclure (re-inclure dans un parent exclu)</option>
    </select>
  </div>
  <div style="margin-bottom: 10px;">
    <label>Raison (optionnel) : </label>
    <input type="text" id="reason" placeholder="ex: RH confidentiel">
  </div>
  <button type="submit" class="btn btn-primary">Ajouter la regle</button>
</form>
</div>

<h2>Tester un chemin</h2>
<div class="card">
<div style="margin-bottom: 10px;">
  <label>Path a tester : </label>
  <input type="text" id="testPath" placeholder="ex: Drive Direction/RH/contrat.docx">
  <button class="btn" onclick="testPath()">Tester</button>
</div>
<div id="testResult"></div>
</div>

<script>
const CONN_ID = {connection_id};

async function addRule(event) {{
  const folder_path = document.getElementById('folderPath').value.trim();
  const rule_type = document.getElementById('ruleType').value;
  const reason = document.getElementById('reason').value.trim();
  if (!folder_path) {{ alert('Path requis'); return; }}
  const r = await fetch('/admin/drive_config/rules/' + CONN_ID, {{
    method: 'POST',
    headers: {{'Content-Type': 'application/json'}},
    body: JSON.stringify({{folder_path, rule_type, reason}})
  }});
  const data = await r.json();
  if (data.status === 'ok') {{
    location.reload();
  }} else {{
    alert('Erreur: ' + (data.message || 'inconnue'));
  }}
}}

async function deleteRule(rule_id) {{
  if (!confirm('Supprimer cette regle ?')) return;
  const r = await fetch('/admin/drive_config/rules/' + rule_id, {{
    method: 'DELETE'
  }});
  const data = await r.json();
  if (data.status === 'ok') {{
    location.reload();
  }} else {{
    alert('Erreur: ' + (data.message || 'inconnue'));
  }}
}}

async function testPath() {{
  const p = document.getElementById('testPath').value.trim();
  if (!p) {{ alert('Path requis'); return; }}
  const r = await fetch('/admin/drive_config/preview/' + CONN_ID +
                       '?path=' + encodeURIComponent(p));
  const data = await r.json();
  const out = document.getElementById('testResult');
  if (data.status !== 'ok') {{
    out.innerHTML = '<div class="warn">Erreur : ' +
                    (data.message || 'inconnue') + '</div>';
    return;
  }}
  const e = data.explanation;
  let html = '<div class="info">';
  html += '<b>Path</b> : <code>' + e.path + '</code><br>';
  html += '<b>Decision</b> : ' + (e.indexable
    ? '<span class="badge badge-include">INDEXE</span>'
    : '<span class="badge badge-exclude">NON INDEXE</span>') + '<br>';
  html += '<b>Sous une racine surveillee</b> : ' + (e.in_root ? '✅ ' + (e.matching_root || '') : '❌ Non') + '<br>';
  if (e.winning_rule) {{
    html += '<b>Regle gagnante</b> : <code>' + e.winning_rule[0] + '</code> (' + e.winning_rule[1] + ')<br>';
  }} else {{
    html += '<b>Regle gagnante</b> : aucune (defaut = sous racine donc indexe)<br>';
  }}
  if (e.all_matching_rules && e.all_matching_rules.length > 1) {{
    html += '<b>Toutes les regles qui matchaient</b> :<ul>';
    for (const r of e.all_matching_rules) {{
      html += '<li><code>' + r[0] + '</code> (' + r[1] + ')</li>';
    }}
    html += '</ul>';
  }}
  html += '</div>';
  out.innerHTML = html;
}}
</script>
</body></html>
"""
    return HTMLResponse(body)
