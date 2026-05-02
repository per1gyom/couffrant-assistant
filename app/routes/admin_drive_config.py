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

from app.routes.deps import require_admin, require_tenant_admin
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


def _roots_to_js(roots: list) -> str:
    """Serialise la liste des racines pour injection dans une balise <script>.

    Filtre les champs pertinents pour le JS frontend (pas les timestamps
    ni le drive_id technique). Echappe les caracteres dangereux.
    """
    import json
    safe_roots = []
    for r in roots:
        safe_roots.append({
            "id": r.get("id"),
            "provider": r.get("provider"),
            "folder_name": r.get("folder_name"),
            "site_name": r.get("site_name"),
            "folder_path": r.get("folder_path") or "",
            "enabled": bool(r.get("enabled")),
        })
    # ensure_ascii=True garantit pas de caracteres unicode bizarres dans le HTML.
    return json.dumps(safe_roots, ensure_ascii=True)


# =====================================================================
# ENDPOINTS API JSON
# =====================================================================

@router.get("/admin/drive_config/drives/{tenant_id}")
def api_list_drives(
    tenant_id: str,
    admin: dict = Depends(require_tenant_admin),
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
    admin: dict = Depends(require_tenant_admin),
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
    admin: dict = Depends(require_tenant_admin),
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
    admin: dict = Depends(require_tenant_admin),
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


# =====================================================================
# ENDPOINTS API JSON - GESTION DES RACINES (drive_folders)
# =====================================================================
# Permet de modifier la racine de scan d un drive directement dans l UI,
# sans avoir a passer par la console DB.
# Cas typiques :
#   1. Elargir : passer folder_path de '1_Photovoltaique' a '' (= toute
#      la racine du site SharePoint, soit le Drive Commun en entier)
#   2. Ajouter une nouvelle racine : Drive Direction sur un autre site
#   3. Desactiver temporairement une racine sans la supprimer
#   4. Supprimer une racine devenue obsolete
#
# Les champs techniques (drive_id, folder_id) ne sont PAS modifiables ici :
# ils sont resolus automatiquement par drive_scanner au prochain scan via
# Graph API, en se basant sur site_name + folder_path. L admin manipule
# juste des labels lisibles.

@router.post("/admin/drive_config/roots/{tenant_id}")
def api_add_or_update_root(
    tenant_id: str,
    payload: dict = Body(...),
    admin: dict = Depends(require_tenant_admin),
):
    """Cree ou met a jour une racine surveillee.

    payload = {
      "id": 1,                          # optionnel : si fourni, UPDATE
      "provider": "sharepoint",
      "folder_name": "Commun complet",  # libelle libre
      "site_name": "Commun",            # nom du site SharePoint
      "folder_path": "",                # vide = scanner tout le site
      "enabled": true
    }

    Si id present -> UPDATE de la racine existante.
    Sinon -> INSERT d une nouvelle racine.
    """
    if not _can_access_tenant(admin, tenant_id):
        return JSONResponse(
            {"status": "error", "message": "Acces refuse"},
            status_code=403,
        )

    root_id = payload.get("id")
    provider = (payload.get("provider") or "sharepoint").strip()
    folder_name = (payload.get("folder_name") or "").strip()
    site_name = (payload.get("site_name") or "").strip() or None
    folder_path = payload.get("folder_path", "")
    if folder_path is None:
        folder_path = ""
    folder_path = str(folder_path).strip().strip("/")
    enabled = bool(payload.get("enabled", True))

    if not folder_name:
        return JSONResponse(
            {"status": "error", "message": "folder_name requis (libelle de la racine)"},
            status_code=400,
        )
    if provider not in ("sharepoint", "google_drive", "drive", "nas"):
        return JSONResponse(
            {"status": "error", "message": f"provider {provider} non supporte"},
            status_code=400,
        )

    from app.database import get_pg_conn

    try:
        with get_pg_conn() as conn:
            cur = conn.cursor()
            if root_id:
                # UPDATE : on garde drive_id/folder_id existants
                # (ils seront re-resolus au prochain scan si folder_path
                # change). On reset folder_id si folder_path change pour
                # forcer le re-discovery via Graph API.
                cur.execute(
                    "SELECT folder_path FROM drive_folders "
                    "WHERE id = %s AND tenant_id = %s",
                    (root_id, tenant_id),
                )
                old = cur.fetchone()
                if not old:
                    return JSONResponse(
                        {"status": "error", "message": "Racine introuvable pour ce tenant"},
                        status_code=404,
                    )
                old_path = old[0] if not isinstance(old, dict) else old.get("folder_path")
                # Si le folder_path change, on reset folder_id pour
                # forcer drive_scanner a re-resoudre via Graph API
                reset_folder_id = (old_path or "") != folder_path

                if reset_folder_id:
                    cur.execute(
                        """
                        UPDATE drive_folders SET
                          provider = %s,
                          folder_name = %s,
                          site_name = %s,
                          folder_path = %s,
                          enabled = %s,
                          folder_id = NULL,
                          last_full_scan_at = NULL,
                          updated_at = NOW()
                        WHERE id = %s AND tenant_id = %s
                        RETURNING id
                        """,
                        (provider, folder_name, site_name, folder_path,
                         enabled, root_id, tenant_id),
                    )
                else:
                    cur.execute(
                        """
                        UPDATE drive_folders SET
                          provider = %s,
                          folder_name = %s,
                          site_name = %s,
                          enabled = %s,
                          updated_at = NOW()
                        WHERE id = %s AND tenant_id = %s
                        RETURNING id
                        """,
                        (provider, folder_name, site_name,
                         enabled, root_id, tenant_id),
                    )
                row = cur.fetchone()
                action = "updated"
            else:
                # INSERT
                cur.execute(
                    """
                    INSERT INTO drive_folders
                      (tenant_id, provider, folder_name, site_name,
                       folder_path, enabled)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (tenant_id, provider, folder_name)
                    DO UPDATE SET
                      site_name = EXCLUDED.site_name,
                      folder_path = EXCLUDED.folder_path,
                      enabled = EXCLUDED.enabled,
                      updated_at = NOW()
                    RETURNING id
                    """,
                    (tenant_id, provider, folder_name, site_name,
                     folder_path, enabled),
                )
                row = cur.fetchone()
                action = "created"

            new_id = row[0] if not isinstance(row, dict) else row.get("id")
            conn.commit()

        logger.info(
            "[admin_drive_config] racine %s id=%s par %s "
            "(provider=%s, site=%s, path='%s', enabled=%s)",
            action, new_id, admin.get("username"),
            provider, site_name, folder_path, enabled,
        )
        return {
            "status": "ok",
            "root_id": new_id,
            "action": action,
            "reset_folder_id": (root_id is not None and
                                action == "updated" and
                                payload.get("folder_path") is not None),
        }
    except Exception as e:
        logger.exception("[admin_drive_config] api_add_or_update_root crash")
        return JSONResponse(
            {"status": "error", "message": str(e)[:300]},
            status_code=500,
        )


@router.delete("/admin/drive_config/roots/{root_id}")
def api_delete_root(
    root_id: int,
    admin: dict = Depends(require_tenant_admin),
):
    """Supprime une racine surveillee. ATTENTION : ne supprime PAS le
    contenu deja vectorise (drive_semantic_content) - juste la config
    de la racine. Pour purger le vectorise, action manuelle separee.
    """
    from app.database import get_pg_conn

    try:
        with get_pg_conn() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT tenant_id FROM drive_folders WHERE id = %s",
                (root_id,),
            )
            r = cur.fetchone()
            if not r:
                return JSONResponse(
                    {"status": "error", "message": "Racine introuvable"},
                    status_code=404,
                )
            tenant_id = r[0] if not isinstance(r, dict) else r.get("tenant_id")
            if not _can_access_tenant(admin, tenant_id):
                return JSONResponse(
                    {"status": "error", "message": "Acces refuse"},
                    status_code=403,
                )
            cur.execute(
                "DELETE FROM drive_folders WHERE id = %s",
                (root_id,),
            )
            conn.commit()
        logger.info(
            "[admin_drive_config] racine id=%s supprimee par %s",
            root_id, admin.get("username"),
        )
        return {"status": "ok"}
    except Exception as e:
        logger.exception("[admin_drive_config] api_delete_root crash")
        return JSONResponse(
            {"status": "error", "message": str(e)[:300]},
            status_code=500,
        )


@router.get("/admin/drive_config/preview/{connection_id}")
def api_preview_path(
    connection_id: int,
    path: str = "",
    admin: dict = Depends(require_tenant_admin),
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
# ENDPOINT BROWSE - Explorateur de dossiers (02/05/2026)
# =====================================================================
# Permet a l UI de naviguer dans l arborescence d un drive sans connaitre
# les ids ni les paths a l avance. Utilise par la modale "Configurer
# dossiers" pour les boutons "Parcourir" sur les champs path (racines + regles).
#
# Pour SharePoint : utilise le token Microsoft du super_admin qui a connecte
# le drive. Token recupere via get_connection_token sur le created_by.
#
# Pour Google Drive : meme principe avec token google.
#
# Pour NAS : non implemente (V2).

def _resolve_admin_token_for_connection(connection_id: int, current_admin: dict) -> tuple:
    """Retourne (token, source_username, error_msg).

    Strategie pour trouver un token valide :
    1. Token Microsoft du super_admin courant (si super_admin)
    2. Token Microsoft du tenant_admin courant (si il a connecte sa boite)
    3. Token Microsoft du created_by de la connexion (qui a fait le OAuth)

    On a besoin d'un token utilisateur valide avec scope Sites.Read.All
    (deja dans GRAPH_SCOPES).
    """
    from app.connection_token_manager import get_connection_token
    from app.database import get_pg_conn

    # Tente le user courant d'abord
    username = current_admin.get("username", "")
    if username:
        tok = get_connection_token(username, "microsoft")
        if tok:
            return (tok, username, None)

    # Sinon : created_by de la connexion
    try:
        with get_pg_conn() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT created_by FROM tenant_connections WHERE id = %s",
                (connection_id,),
            )
            r = cur.fetchone()
            if r:
                created_by = r[0] if not isinstance(r, dict) else r.get("created_by")
                if created_by and created_by != username:
                    tok = get_connection_token(created_by, "microsoft")
                    if tok:
                        return (tok, created_by, None)
    except Exception as e:
        logger.warning("[browse] resolve token : %s", e)

    return (None, None, "Aucun token Microsoft disponible. "
                        "Le super-admin doit reconnecter sa boite Microsoft "
                        "pour permettre l'exploration SharePoint.")


@router.get("/admin/drive_config/browse/{connection_id}")
def api_browse_folder(
    connection_id: int,
    path: str = "",
    admin: dict = Depends(require_tenant_admin),
):
    """Liste les enfants (dossiers + fichiers) d un path donne dans un drive.

    Query params :
      path : path complet relatif a la racine du site/drive
             "" = racine
             "Documents" = dans le dossier Documents
             "Documents/Sous-dossier" = dans un sous-sous-dossier

    Retour :
      {
        "status": "ok",
        "provider": "sharepoint",
        "current_path": "Documents",
        "parent_path": "",         (None si on est a la racine)
        "items": [
          {"name": "Sous-dossier1", "type": "folder", "path": "Documents/Sous-dossier1"},
          {"name": "fichier.docx", "type": "file", "path": "Documents/fichier.docx", "size": 12345}
        ]
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
            {"status": "error", "message": "Acces refuse"},
            status_code=403,
        )

    tool_type = meta.get("tool_type", "")
    cfg = meta.get("config") or {}
    if not isinstance(cfg, dict):
        cfg = {}

    # Normalise le path
    path = (path or "").strip().strip("/").replace("\\", "/")

    # Calcule le parent_path pour le bouton "remonter"
    parent_path = None
    if path:
        if "/" in path:
            parent_path = path.rsplit("/", 1)[0]
        else:
            parent_path = ""  # racine

    try:
        if tool_type == "sharepoint":
            return _browse_sharepoint(connection_id, cfg, path, parent_path, admin)
        elif tool_type == "google_drive":
            return _browse_google_drive(connection_id, cfg, path, parent_path, admin)
        elif tool_type == "drive":
            # 'drive' generique = on essaie sharepoint (fallback historique)
            return _browse_sharepoint(connection_id, cfg, path, parent_path, admin)
        else:
            return JSONResponse(
                {"status": "error",
                 "message": f"Provider {tool_type} non supporte pour browse"},
                status_code=400,
            )
    except Exception as e:
        logger.exception("[admin_drive_config] api_browse_folder crash")
        return JSONResponse(
            {"status": "error", "message": str(e)[:300]},
            status_code=500,
        )


def _browse_sharepoint(connection_id, cfg, path, parent_path, admin):
    """Browse SharePoint via Graph API."""
    import requests

    token, src_user, err = _resolve_admin_token_for_connection(connection_id, admin)
    if not token:
        return JSONResponse(
            {"status": "error", "message": err or "Token MS introuvable"},
            status_code=400,
        )

    # Resolution du drive_id pour ce site SharePoint
    site_name = cfg.get("site_name", "")
    site_id = cfg.get("site_id", "")
    if not site_id and site_name:
        # Tente de retrouver le site_id via Graph
        try:
            from app.connectors.drive_connector import _find_sharepoint_site_and_drive
            _, drive_id_resolved, _ = _find_sharepoint_site_and_drive(
                token, {"site_name": site_name}
            )
        except Exception as e:
            logger.warning("[browse] resolve site %s : %s", site_name, e)
            drive_id_resolved = None
    else:
        drive_id_resolved = None

    # Si on a site_id direct, on le prefere
    headers = {"Authorization": f"Bearer {token}"}
    GRAPH = "https://graph.microsoft.com/v1.0"

    # Etape 1 : trouver le drive (Documents library) du site
    drive_id = drive_id_resolved
    if not drive_id and site_id:
        try:
            r = requests.get(f"{GRAPH}/sites/{site_id}/drive",
                             headers=headers, timeout=15)
            if r.ok:
                drive_id = r.json().get("id")
        except Exception as e:
            logger.warning("[browse] /sites/%s/drive : %s", site_id, e)

    if not drive_id:
        return JSONResponse(
            {"status": "error",
             "message": f"Impossible de resoudre le drive pour ce site "
                        f"(site_id={site_id[:30] if site_id else '-'}, "
                        f"site_name={site_name})"},
            status_code=500,
        )

    # Etape 2 : lister les enfants
    if not path:
        # Racine
        url = f"{GRAPH}/drives/{drive_id}/root/children"
    else:
        # Sous-dossier (Graph utilise :/path:/children pour resoudre par path)
        # Encoder les caracteres speciaux dans le path
        from urllib.parse import quote
        encoded_path = quote(path, safe="/")
        url = f"{GRAPH}/drives/{drive_id}/root:/{encoded_path}:/children"

    params = {
        "$top": 200,
        "$select": "name,id,size,folder,file,lastModifiedDateTime",
        "$orderby": "name",
    }

    try:
        r = requests.get(url, headers=headers, params=params, timeout=20)
        if not r.ok:
            return JSONResponse(
                {"status": "error",
                 "message": f"Graph API {r.status_code} : {r.text[:200]}"},
                status_code=500,
            )
        data = r.json()
    except Exception as e:
        return JSONResponse(
            {"status": "error", "message": f"Erreur reseau : {str(e)[:200]}"},
            status_code=500,
        )

    items = []
    for raw in data.get("value", []):
        name = raw.get("name", "")
        if not name:
            continue
        is_folder = "folder" in raw
        # Path complet de l item
        item_path = f"{path}/{name}" if path else name
        items.append({
            "name": name,
            "type": "folder" if is_folder else "file",
            "path": item_path,
            "size": raw.get("size", 0),
            "modified": (raw.get("lastModifiedDateTime") or "")[:10],
            "child_count": (raw.get("folder", {}) or {}).get("childCount", 0)
                if is_folder else None,
        })

    # Tri : dossiers d'abord, puis fichiers, alphabetique
    items.sort(key=lambda x: (0 if x["type"] == "folder" else 1, x["name"].lower()))

    return {
        "status": "ok",
        "provider": "sharepoint",
        "site_name": site_name,
        "current_path": path,
        "parent_path": parent_path,
        "items": items,
        "count": len(items),
    }


def _browse_google_drive(connection_id, cfg, path, parent_path, admin):
    """Browse Google Drive via API v3.

    Google Drive ne fonctionne pas avec des paths mais des parent_id.
    On reconstruit la navigation a partir d'un id de dossier qu'on
    encode dans le 'path' (path = id du dossier courant, ou "" pour root).
    """
    from app.connection_token_manager import get_connection_token
    import requests

    # Token google_drive du user courant ou du created_by
    username = admin.get("username", "")
    token = get_connection_token(username, "google_drive") if username else None
    if not token:
        # Tente created_by
        from app.database import get_pg_conn
        try:
            with get_pg_conn() as conn:
                cur = conn.cursor()
                cur.execute(
                    "SELECT created_by FROM tenant_connections WHERE id = %s",
                    (connection_id,),
                )
                r = cur.fetchone()
                if r:
                    created_by = r[0] if not isinstance(r, dict) else r.get("created_by")
                    if created_by:
                        token = get_connection_token(created_by, "google_drive")
        except Exception:
            pass

    if not token:
        return JSONResponse(
            {"status": "error",
             "message": "Aucun token Google Drive disponible pour cette connexion"},
            status_code=400,
        )

    # path = id du parent (ou "root" pour la racine)
    parent_id = path if path else "root"

    # Liste les enfants
    url = "https://www.googleapis.com/drive/v3/files"
    params = {
        "q": f"'{parent_id}' in parents and trashed=false",
        "pageSize": 200,
        "fields": "files(id,name,mimeType,size,modifiedTime)",
        "orderBy": "folder,name",
    }
    headers = {"Authorization": f"Bearer {token}"}

    try:
        r = requests.get(url, headers=headers, params=params, timeout=20)
        if not r.ok:
            return JSONResponse(
                {"status": "error",
                 "message": f"Google API {r.status_code} : {r.text[:200]}"},
                status_code=500,
            )
        data = r.json()
    except Exception as e:
        return JSONResponse(
            {"status": "error", "message": f"Erreur reseau : {str(e)[:200]}"},
            status_code=500,
        )

    items = []
    for raw in data.get("files", []):
        is_folder = raw.get("mimeType") == "application/vnd.google-apps.folder"
        items.append({
            "name": raw.get("name", ""),
            "type": "folder" if is_folder else "file",
            "path": raw.get("id"),  # pour Google : path = id du dossier
            "size": int(raw.get("size", 0) or 0),
            "modified": (raw.get("modifiedTime") or "")[:10],
        })

    items.sort(key=lambda x: (0 if x["type"] == "folder" else 1, x["name"].lower()))

    return {
        "status": "ok",
        "provider": "google_drive",
        "current_path": parent_id,
        "parent_path": parent_path,  # devra etre re-resolu cote frontend pour Google
        "items": items,
        "count": len(items),
        "note_google": "Pour Google Drive, le 'path' est un id de dossier",
    }


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
    admin: dict = Depends(require_tenant_admin),
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
<div class="breadcrumb">
  <a href="/admin">Admin Raya</a> /
  Configuration Drive / Vue d ensemble
</div>
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

    # Section gestion des racines (modifier/ajouter/supprimer)
    body += f"""
<h2>Racines surveillees ({len(roots)})</h2>
<div class="info">
La <b>racine</b> definit OU Raya commence a regarder dans ton drive.
Mettre <code>folder_path = ""</code> (vide) = scanner TOUT le site SharePoint.
Mettre <code>folder_path = "1_Photovoltaique"</code> = scanner ce sous-dossier seulement.<br>
Tu peux avoir plusieurs racines (Drive Commun + Drive Direction par exemple).
</div>
<div class="card">
"""

    if not roots:
        body += "<div class='warn'>Aucune racine. Ajoute-en une ci-dessous pour que Raya commence a scanner.</div>"
    else:
        body += """
<table>
<thead><tr>
  <th>Provider</th><th>Site</th><th>Libelle</th><th>Path</th>
  <th>Enabled</th><th>Dernier scan</th><th>Action</th>
</tr></thead>
<tbody>
"""
        for r in roots:
            last_scan = r.get("last_full_scan_at")
            last_scan_str = (last_scan.strftime("%Y-%m-%d %H:%M")
                             if last_scan else "-")
            rid = r["id"]
            path_display = (
                f"<code>{r.get('folder_path')}</code>"
                if r.get("folder_path") else "<i>(racine du site)</i>"
            )
            enabled_emoji = "✅" if r.get("enabled") else "❌"
            body += (
                "<tr>"
                f"<td>{r.get('provider', '?')}</td>"
                f"<td>{r.get('site_name') or '-'}</td>"
                f"<td>{r.get('folder_name') or '-'}</td>"
                f"<td>{path_display}</td>"
                f"<td>{enabled_emoji}</td>"
                f"<td>{last_scan_str}</td>"
                f"<td>"
                f"<button class='btn' onclick='editRoot({rid})'>Modifier</button> "
                f"<button class='btn btn-danger' onclick='deleteRoot({rid})'>Supprimer</button>"
                f"</td>"
                "</tr>"
            )
        body += "</tbody></table>"
    body += "</div>"

    # Formulaire d'ajout de racine
    body += f"""
<h3>Ajouter une nouvelle racine</h3>
<div class="card">
<form id="addRootForm" onsubmit="addRoot(event); return false;">
  <div style="margin-bottom: 10px;">
    <label>Provider : </label>
    <select id="rootProvider">
      <option value="sharepoint">SharePoint</option>
      <option value="google_drive">Google Drive</option>
      <option value="drive">Drive (autre)</option>
      <option value="nas">NAS</option>
    </select>
  </div>
  <div style="margin-bottom: 10px;">
    <label>Libelle (folder_name UNIQUE) : </label>
    <input type="text" id="rootFolderName" placeholder="ex: Drive Direction">
  </div>
  <div style="margin-bottom: 10px;">
    <label>Site (SharePoint) : </label>
    <input type="text" id="rootSiteName" placeholder="ex: Direction">
  </div>
  <div style="margin-bottom: 10px;">
    <label>Path (vide = tout le site) : </label>
    <input type="text" id="rootFolderPath" placeholder="ex: Comptabilite (vide = tout)">
  </div>
  <button type="submit" class="btn btn-primary">Ajouter cette racine</button>
</form>
</div>

<!-- Modal d edition de racine -->
<div id="editRootModal" style="display:none; position:fixed; top:0; left:0; right:0; bottom:0;
     background:rgba(0,0,0,0.5); z-index:1000; align-items:center; justify-content:center;">
  <div style="background:white; padding:24px; border-radius:8px; max-width:500px; width:90%;">
    <h3 style="margin-top:0;">Modifier la racine</h3>
    <input type="hidden" id="editRootId">
    <div style="margin-bottom:10px;"><label>Libelle : </label>
      <input type="text" id="editRootFolderName"></div>
    <div style="margin-bottom:10px;"><label>Site : </label>
      <input type="text" id="editRootSiteName"></div>
    <div style="margin-bottom:10px;"><label>Path : </label>
      <input type="text" id="editRootFolderPath" placeholder="vide = tout le site"></div>
    <div style="margin-bottom:10px;"><label>Enabled : </label>
      <input type="checkbox" id="editRootEnabled"></div>
    <div class="warn">Si tu changes le path, le folder_id sera reset pour
    forcer une re-resolution via Graph API au prochain scan.</div>
    <button class="btn btn-primary" onclick="saveRoot()">Enregistrer</button>
    <button class="btn" onclick="closeEditRoot()">Annuler</button>
  </div>
</div>

<script>
const TENANT_ID = '{tenant_id}';
const ROOTS_DATA = {_roots_to_js(roots)};

async function addRoot(event) {{
  const payload = {{
    provider: document.getElementById('rootProvider').value,
    folder_name: document.getElementById('rootFolderName').value.trim(),
    site_name: document.getElementById('rootSiteName').value.trim(),
    folder_path: document.getElementById('rootFolderPath').value.trim(),
    enabled: true,
  }};
  if (!payload.folder_name) {{ alert('Libelle requis'); return; }}
  const r = await fetch('/admin/drive_config/roots/' + TENANT_ID, {{
    method: 'POST',
    headers: {{'Content-Type': 'application/json'}},
    body: JSON.stringify(payload)
  }});
  const data = await r.json();
  if (data.status === 'ok') {{ location.reload(); }}
  else {{ alert('Erreur: ' + (data.message || 'inconnue')); }}
}}

function editRoot(id) {{
  const root = ROOTS_DATA.find(r => r.id === id);
  if (!root) {{ alert('Racine introuvable'); return; }}
  document.getElementById('editRootId').value = root.id;
  document.getElementById('editRootFolderName').value = root.folder_name || '';
  document.getElementById('editRootSiteName').value = root.site_name || '';
  document.getElementById('editRootFolderPath').value = root.folder_path || '';
  document.getElementById('editRootEnabled').checked = !!root.enabled;
  document.getElementById('editRootModal').style.display = 'flex';
}}

function closeEditRoot() {{
  document.getElementById('editRootModal').style.display = 'none';
}}

async function saveRoot() {{
  const payload = {{
    id: parseInt(document.getElementById('editRootId').value),
    provider: 'sharepoint',  // garde le provider existant (lookup ROOTS_DATA)
    folder_name: document.getElementById('editRootFolderName').value.trim(),
    site_name: document.getElementById('editRootSiteName').value.trim(),
    folder_path: document.getElementById('editRootFolderPath').value.trim(),
    enabled: document.getElementById('editRootEnabled').checked,
  }};
  // Garde le provider existant
  const existing = ROOTS_DATA.find(r => r.id === payload.id);
  if (existing) payload.provider = existing.provider;
  const r = await fetch('/admin/drive_config/roots/' + TENANT_ID, {{
    method: 'POST',
    headers: {{'Content-Type': 'application/json'}},
    body: JSON.stringify(payload)
  }});
  const data = await r.json();
  if (data.status === 'ok') {{ location.reload(); }}
  else {{ alert('Erreur: ' + (data.message || 'inconnue')); }}
}}

async function deleteRoot(id) {{
  if (!confirm('Supprimer cette racine ?\\n\\nLe contenu deja indexe ne sera PAS supprime, seulement la config.')) return;
  const r = await fetch('/admin/drive_config/roots/' + id, {{ method: 'DELETE' }});
  const data = await r.json();
  if (data.status === 'ok') {{ location.reload(); }}
  else {{ alert('Erreur: ' + (data.message || 'inconnue')); }}
}}
</script>
"""

    body += "</body></html>"
    return HTMLResponse(body)


@router.get(
    "/admin/drive_config/configure/{connection_id}",
    response_class=HTMLResponse,
)
def page_drive_configure(
    connection_id: int,
    admin: dict = Depends(require_tenant_admin),
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
  <a href="/admin">Admin Raya</a> /
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
