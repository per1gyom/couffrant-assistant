"""
Endpoints admin pour configurer les regles d inclusion/exclusion des
racines Drive (SharePoint, Google Drive, NAS, etc.) du tenant.

Phase Drive multi-racines (02/05/2026).
Cf. docs/journal_02mai_2026_drive_multi_racines.md

PERMISSIONS :
  - Tenant admin : peut configurer son propre tenant.
  - Super admin : peut acceder pour debug/depannage tous tenants.

ENDPOINTS API (JSON UNIQUEMENT) :
  GET  /admin/drive_config/drives/{tenant_id}
       -> liste des connexions drive du tenant + leurs etats
  GET  /admin/drive_config/browse/{connection_id}?path=
       -> liste enfants d un path (explorateur de dossiers)
  GET  /admin/drive_config/rules/{connection_id}
       -> liste des regles configurees pour cette connexion
  POST /admin/drive_config/rules/{connection_id}
       -> ajoute une regle (include/exclude) sur un path
  DELETE /admin/drive_config/rules/{rule_id}
       -> supprime une regle
  POST /admin/drive_config/roots/{tenant_id}
       -> ajoute ou met a jour une racine surveillee
  DELETE /admin/drive_config/roots/{root_id}
       -> supprime une racine
  GET  /admin/drive_config/preview/{connection_id}?path=
       -> simule "Raya verra-t-elle ce path ?" + explication

PAGES HTML : aucune. L UI charte admin est servie par admin_connexions.html
(super_admin) et tenant_panel.html (tenant_admin) qui consomment les
endpoints JSON ci-dessus. Les anciennes pages HTML inline (charte
hors-style) ont ete supprimees le 02/05/2026.
"""
from typing import Optional
from fastapi import APIRouter, Depends, Body
from fastapi.responses import JSONResponse

from app.routes.deps import require_tenant_admin
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
    """Browse SharePoint via Graph API.

    Gere 3 formats de config (historique du projet) :
    - Format legacy : {sharepoint_site, sharepoint_drive, sharepoint_folder}
    - Format new : {site_name, site_id, site_url}
    - Mixte : un peu des deux
    """
    import requests

    token, src_user, err = _resolve_admin_token_for_connection(connection_id, admin)
    if not token:
        return JSONResponse(
            {"status": "error", "message": err or "Token MS introuvable"},
            status_code=400,
        )

    # Resolution du nom de site (multi-formats config)
    site_name = (
        cfg.get("site_name")
        or cfg.get("sharepoint_site")
        or ""
    )
    site_id = cfg.get("site_id", "")

    # Si on n a ni site_id ni site_name, on ne peut rien faire
    if not site_id and not site_name:
        return JSONResponse(
            {"status": "error",
             "message": "Connexion SharePoint sans site identifie. "
                        "Config attendue : {site_name} ou {sharepoint_site} "
                        f"ou {{site_id}}. Recue : {list(cfg.keys())}"},
            status_code=500,
        )

    headers = {"Authorization": f"Bearer {token}"}
    GRAPH = "https://graph.microsoft.com/v1.0"

    # Etape 1 : trouver le drive_id du site
    drive_id = None

    # Cas 1 : on a deja un site_id direct -> appel Graph rapide
    if site_id:
        try:
            r = requests.get(f"{GRAPH}/sites/{site_id}/drive",
                             headers=headers, timeout=15)
            if r.ok:
                drive_id = r.json().get("id")
            else:
                logger.warning("[browse] /sites/%s/drive : %s %s",
                               site_id[:30], r.status_code, r.text[:200])
        except Exception as e:
            logger.warning("[browse] /sites/%s/drive : %s", site_id, e)

    # Cas 2 : on a juste un site_name -> resoudre via la fonction existante
    # qui cherche le site puis recupere le drive_id
    if not drive_id and site_name:
        try:
            from app.connectors.drive_connector import _find_sharepoint_site_and_drive
            # _find_sharepoint_site_and_drive attend un dict avec site_name
            _, drive_id_resolved, _ = _find_sharepoint_site_and_drive(
                token, {"site_name": site_name}
            )
            if drive_id_resolved:
                drive_id = drive_id_resolved
                logger.info(
                    "[browse] site %s -> drive_id %s (resolu via _find_sharepoint_site_and_drive)",
                    site_name, drive_id[:30]
                )
        except Exception as e:
            logger.warning("[browse] resolve site %s : %s", site_name, e)

    # Cas 3 : fallback - chercher directement via Graph search
    if not drive_id and site_name:
        try:
            r = requests.get(
                f"{GRAPH}/sites",
                headers=headers,
                params={"search": site_name, "$top": 5},
                timeout=15,
            )
            if r.ok:
                sites = r.json().get("value", [])
                # Prend le 1er site qui matche le nom (insensitive)
                for s in sites:
                    s_name = (s.get("displayName") or s.get("name") or "").lower()
                    if site_name.lower() in s_name or s_name in site_name.lower():
                        site_id_found = s.get("id")
                        if site_id_found:
                            r2 = requests.get(
                                f"{GRAPH}/sites/{site_id_found}/drive",
                                headers=headers, timeout=15,
                            )
                            if r2.ok:
                                drive_id = r2.json().get("id")
                                logger.info(
                                    "[browse] site %s -> site_id %s -> drive_id %s (fallback search)",
                                    site_name, site_id_found[:30], drive_id[:30]
                                )
                                break
        except Exception as e:
            logger.warning("[browse] fallback search %s : %s", site_name, e)

    if not drive_id:
        return JSONResponse(
            {"status": "error",
             "message": (f"Impossible de resoudre le drive pour ce site. "
                         f"site_name='{site_name}' / site_id='{site_id[:30] if site_id else ''}'. "
                         f"Verifie que le super-admin a bien connecte sa boite "
                         f"Microsoft et que le site SharePoint existe.")},
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


# Pages HTML (page_drive_config_home, page_drive_configure) supprimees le
# 02/05/2026 : doublonnaient l UI charte admin du tenant_panel et
# admin_connexions. Les endpoints API JSON ci-dessus suffisent au frontend.
