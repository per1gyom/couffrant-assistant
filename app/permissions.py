"""
Module de gestion des permissions Read / Write / Delete par connexion.

Plan strategique : docs/raya_permissions_plan.md

Hierarchie :
    Super admin (Guillaume) : plafond par connexion du tenant
         -> Tenant admin : distribue les permissions aux users
                -> User (v1 : subit / v2 : peut se restreindre)

V1 implementee ici :
- Super admin fixe super_admin_permission_level sur tenant_connections
- Tenant admin fixe tenant_admin_permission_level (<= plafond)
- La valeur effective utilisee par Raya est tenant_admin_permission_level
- Toute tentative d action est loggee dans permission_audit_log
"""

import logging
from typing import Optional, Tuple

logger = logging.getLogger("raya.permissions")

# Les 3 niveaux, ordonnes du moins permissif au plus permissif
PERMISSION_LEVELS = ("read", "read_write", "read_write_delete")

# Rang numerique pour comparer les niveaux
_LEVEL_RANK = {level: i for i, level in enumerate(PERMISSION_LEVELS)}


# Mapping tag ACTION -> niveau requis
# Base : docs/raya_permissions_plan.md section 6
# Tout tag non liste = 'read_write_delete' (principe de securite : on bloque
# par defaut, on autorise explicitement)
ACTION_PERMISSION_MAP = {
    # --- Niveau 'read' : lecture seule ---
    # Odoo
    "ODOO_SEARCH": "read",
    "ODOO_SEMANTIC": "read",
    "ODOO_CLIENT_360": "read",
    "ODOO_INTROSPECT": "read",
    "ODOO_GET": "read",
    "ODOO_LIST": "read",
    # Recherche unifiee multi-source (etape A commit 3/5, 21/04/2026)
    # Balaie Odoo + Drive + mails + conversations en une seule passe.
    "SEARCH": "read",
    # Mail
    "READ_MAIL": "read",
    "SEARCHMAIL": "read",
    "LIST_MAILS": "read",
    "GETMAIL": "read",
    # Drive
    "SEARCHDRIVE": "read",
    "READ_DOCUMENT": "read",
    "LIST_FOLDERS": "read",
    "LISTDRIVE": "read",
    # Calendar
    "LIST_EVENTS": "read",
    "SEARCH_CALENDAR": "read",
    "READ_EVENT": "read",
    "GETEVENT": "read",
    # Messagerie (lecture)
    "READ_TEAMS": "read",
    "LIST_TEAMS_CHATS": "read",

    # --- Niveau 'read_write' : lecture + modification (pas de suppression) ---
    # Mail
    "SEND_MAIL": "read_write",
    "REPLY_MAIL": "read_write",
    "FORWARD_MAIL": "read_write",
    "DRAFT_MAIL": "read_write",
    "MARK_READ": "read_write",
    "MARK_UNREAD": "read_write",
    "FLAG_MAIL": "read_write",
    # Odoo
    "ODOO_CREATE": "read_write",
    "ODOO_UPDATE": "read_write",
    "ODOO_ASSIGN": "read_write",
    # Calendar
    "CREATEEVENT": "read_write",
    "UPDATE_EVENT": "read_write",
    "REPLY_EVENT": "read_write",
    # Drive
    "CREATEFOLDER": "read_write",
    "UPLOAD_DOCUMENT": "read_write",
    "UPDATE_DOCUMENT": "read_write",
    # Messagerie
    "SEND_TEAMS": "read_write",
    "REPLY_TEAMS": "read_write",
    # --- Niveau 'read_write_delete' : tout y compris suppression ---
    "ODOO_DELETE": "read_write_delete",
    "ODOO_UNLINK": "read_write_delete",
    "DELETE_EVENT": "read_write_delete",
    "DELETE_MAIL": "read_write_delete",
    "DELETE_DOCUMENT": "read_write_delete",
    "DELETE_FOLDER": "read_write_delete",
    "DELETE_TEAMS": "read_write_delete",
}


def get_required_permission(action_tag: str) -> str:
    """Retourne le niveau de permission requis pour un tag d action.

    Par defaut 'read_write_delete' pour les tags inconnus (principe
    de securite : on bloque ce qu on ne connait pas).
    """
    return ACTION_PERMISSION_MAP.get(action_tag.upper(), "read_write_delete")


def level_satisfies(current: str, required: str) -> bool:
    """Verifie si le niveau courant satisfait le niveau requis.

    'read_write_delete' satisfait tout.
    'read_write' satisfait 'read' et 'read_write'.
    'read' ne satisfait que 'read'.
    """
    current_rank = _LEVEL_RANK.get(current, -1)
    required_rank = _LEVEL_RANK.get(required, len(PERMISSION_LEVELS))
    return current_rank >= required_rank


def cap_level(wanted: str, cap: str) -> str:
    """Retourne le minimum entre wanted et cap.

    Utilise quand un tenant admin tente de se donner plus de droits
    que le plafond super admin.
    """
    wanted_rank = _LEVEL_RANK.get(wanted, 0)
    cap_rank = _LEVEL_RANK.get(cap, 0)
    effective_rank = min(wanted_rank, cap_rank)
    return PERMISSION_LEVELS[effective_rank]


def get_connection_permission(tenant_id: str, tool_type: str) -> Optional[dict]:
    """Recupere les infos de permission d une connexion d un tenant.

    Args:
        tenant_id: identifiant du tenant (ex: 'couffrant')
        tool_type: type de connexion (ex: 'odoo', 'gmail', 'sharepoint')

    Retourne un dict {connection_id, super_admin_perm, tenant_admin_perm,
    previous_perm} ou None si pas de connexion trouvee.
    """
    from app.database import get_pg_conn
    try:
        with get_pg_conn() as conn:
            cur = conn.cursor()
            cur.execute(
                """SELECT id, super_admin_permission_level,
                          tenant_admin_permission_level,
                          previous_permission_level
                   FROM tenant_connections
                   WHERE tenant_id = %s AND tool_type = %s
                   ORDER BY id DESC LIMIT 1""",
                (tenant_id, tool_type),
            )
            row = cur.fetchone()
            if not row:
                return None
            return {
                "connection_id": row[0],
                "super_admin_permission_level": row[1] or "read",
                "tenant_admin_permission_level": row[2] or "read",
                "previous_permission_level": row[3],
            }
    except Exception as e:
        logger.exception("[Permissions] get_connection_permission : %s", e)
        return None


def _tool_type_for_action(action_tag: str) -> Optional[str]:
    """Deduit le tool_type concerne par un tag d action.

    Exemple : ODOO_SEARCH -> 'odoo'
              SEND_MAIL -> 'gmail' ou 'microsoft' (on prend 'mailbox' generique)
              CREATEEVENT -> 'mailbox' (meme connecteur)
              SEARCHDRIVE -> 'drive'
    """
    tag = action_tag.upper()
    if tag.startswith("ODOO_"):
        return "odoo"
    if tag in ("SEND_MAIL", "REPLY_MAIL", "FORWARD_MAIL", "DRAFT_MAIL",
              "READ_MAIL", "SEARCHMAIL", "LIST_MAILS", "GETMAIL",
              "MARK_READ", "MARK_UNREAD", "FLAG_MAIL", "DELETE_MAIL"):
        return "mailbox"  # generique mail (gmail OU microsoft)
    if tag in ("CREATEEVENT", "UPDATE_EVENT", "DELETE_EVENT",
              "LIST_EVENTS", "SEARCH_CALENDAR", "READ_EVENT", "GETEVENT",
              "REPLY_EVENT"):
        return "mailbox"  # calendar = meme connecteur
    if tag in ("SEARCHDRIVE", "READ_DOCUMENT", "LIST_FOLDERS", "LISTDRIVE",
              "CREATEFOLDER", "UPLOAD_DOCUMENT", "UPDATE_DOCUMENT",
              "DELETE_DOCUMENT", "DELETE_FOLDER"):
        return "drive"
    if tag in ("SEND_TEAMS", "REPLY_TEAMS", "READ_TEAMS",
              "LIST_TEAMS_CHATS", "DELETE_TEAMS"):
        return "teams"
    return None


def check_permission(
    tenant_id: str,
    username: str,
    action_tag: str,
    user_input_excerpt: str = "",
) -> Tuple[bool, str]:
    """Verifie qu un user a le droit d executer une action sur son tenant.

    Args:
        tenant_id: identifiant du tenant
        username: identifiant de l utilisateur qui tente l action
        action_tag: tag d action (ex: 'ODOO_CREATE')
        user_input_excerpt: debut du prompt user pour contextualiser l audit

    Retourne (allowed, reason) :
        (True, 'ok') si autorise
        (False, 'explanation') si refuse
    """
    required = get_required_permission(action_tag)
    tool_type = _tool_type_for_action(action_tag)
    # Actions sans connexion specifique (ex: SENDMESSAGE interne) -> autorise
    if not tool_type:
        return (True, "ok_no_connection_check")

    perm_info = get_connection_permission(tenant_id, tool_type)
    if not perm_info:
        # Pas de connexion = pas d action possible de toute facon
        return (False, f"Aucune connexion '{tool_type}' configuree pour ce tenant")

    current = perm_info["tenant_admin_permission_level"]
    connection_id = perm_info["connection_id"]
    allowed = level_satisfies(current, required)

    # Log dans permission_audit_log
    _log_audit(tenant_id, username, connection_id, action_tag,
               current, required, allowed, user_input_excerpt)

    if not allowed:
        label = {"read": "LECTURE SEULE",
                 "read_write": "LECTURE + ECRITURE",
                 "read_write_delete": "CONTROLE TOTAL"}.get(current, current)
        reason = (f"Ta connexion '{tool_type}' est en mode {label}. "
                  f"L action '{action_tag}' necessite le niveau '{required}'. "
                  f"Demande a ton admin de modifier la permission si besoin.")
        return (False, reason)
    return (True, "ok")


def _log_audit(
    tenant_id: str, username: str, connection_id: Optional[int],
    action_tag: str, current: str, required: str,
    allowed: bool, user_input_excerpt: str = "",
):
    """Insere une ligne dans permission_audit_log. Silencieux en cas d erreur
    (ne doit jamais bloquer l execution de Raya)."""
    from app.database import get_pg_conn
    try:
        with get_pg_conn() as conn:
            cur = conn.cursor()
            cur.execute(
                """INSERT INTO permission_audit_log
                   (tenant_id, username, connection_id, action_tag,
                    current_permission_level, required_permission_level,
                    allowed, user_input_excerpt)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                (tenant_id, username, connection_id, action_tag,
                 current, required, allowed,
                 (user_input_excerpt or "")[:500]),
            )
            conn.commit()
    except Exception as e:
        logger.warning("[Permissions] Audit log fail : %s", str(e)[:100])


def get_all_permissions_for_tenant(tenant_id: str) -> list:
    """Retourne la liste de toutes les connexions du tenant avec leurs
    permissions. Utile pour l injection dans le prompt systeme de Raya.

    Format : [
        {"tool_type": "odoo", "tenant_admin": "read_write", "super_admin": "read_write_delete"},
        {"tool_type": "gmail", "tenant_admin": "read", ...},
    ]
    """
    from app.database import get_pg_conn
    try:
        with get_pg_conn() as conn:
            cur = conn.cursor()
            cur.execute(
                """SELECT tool_type, super_admin_permission_level,
                          tenant_admin_permission_level
                   FROM tenant_connections
                   WHERE tenant_id = %s
                   ORDER BY tool_type""",
                (tenant_id,),
            )
            return [{
                "tool_type": r[0],
                "super_admin_permission_level": r[1] or "read",
                "tenant_admin_permission_level": r[2] or "read",
            } for r in cur.fetchall()]
    except Exception as e:
        logger.exception("[Permissions] get_all : %s", e)
        return []


def update_permission(
    tenant_id: str,
    connection_id: int,
    new_level: str,
    actor_role: str = "tenant_admin",
) -> Tuple[bool, str]:
    """Met a jour la permission d une connexion.

    Args:
        tenant_id: identifiant du tenant
        connection_id: id de la connexion dans tenant_connections
        new_level: 'read' / 'read_write' / 'read_write_delete'
        actor_role: 'super_admin' ou 'tenant_admin'

    Regles :
    - Si actor_role='super_admin' : met a jour super_admin_permission_level
      ET applique le cap sur tenant_admin_permission_level si celui-ci depasse
    - Si actor_role='tenant_admin' : met a jour tenant_admin_permission_level
      en cappant au plafond super_admin
    """
    if new_level not in PERMISSION_LEVELS:
        return (False, f"Niveau invalide : {new_level}")
    from app.database import get_pg_conn
    try:
        with get_pg_conn() as conn:
            cur = conn.cursor()
            # Recupere le plafond actuel
            cur.execute(
                """SELECT super_admin_permission_level,
                          tenant_admin_permission_level
                   FROM tenant_connections
                   WHERE id = %s AND tenant_id = %s""",
                (connection_id, tenant_id),
            )
            row = cur.fetchone()
            if not row:
                return (False, "Connexion introuvable")
            super_perm = row[0] or "read"
            tenant_perm = row[1] or "read"

            if actor_role == "super_admin":
                # Met a jour super_admin + cap tenant_admin si depasse
                effective_tenant = cap_level(tenant_perm, new_level)
                cur.execute(
                    """UPDATE tenant_connections
                       SET super_admin_permission_level = %s,
                           tenant_admin_permission_level = %s,
                           updated_at = NOW()
                       WHERE id = %s""",
                    (new_level, effective_tenant, connection_id),
                )
            else:
                # Tenant admin : cap au plafond super_admin
                effective = cap_level(new_level, super_perm)
                cur.execute(
                    """UPDATE tenant_connections
                       SET tenant_admin_permission_level = %s,
                           updated_at = NOW()
                       WHERE id = %s""",
                    (effective, connection_id),
                )
            conn.commit()
            return (True, "ok")
    except Exception as e:
        logger.exception("[Permissions] update_permission : %s", e)
        return (False, str(e)[:200])


def get_tenant_lock_status(tenant_id: str = None) -> dict:
    """Retourne l etat de verrouillage d un tenant (ou global si tenant_id=None).

    Format : {
        "is_locked": True|False,  # majorite en read avec previous != NULL
        "total_connections": N,
        "locked_connections": N,
        "tenant_id": "..." ou None,
    }
    """
    from app.database import get_pg_conn
    try:
        with get_pg_conn() as conn:
            cur = conn.cursor()
            if tenant_id:
                cur.execute(
                    """SELECT COUNT(*),
                              SUM(CASE WHEN tenant_admin_permission_level='read'
                                        AND previous_permission_level IS NOT NULL
                                       THEN 1 ELSE 0 END)
                       FROM tenant_connections WHERE tenant_id=%s""",
                    (tenant_id,),
                )
            else:
                cur.execute(
                    """SELECT COUNT(*),
                              SUM(CASE WHEN tenant_admin_permission_level='read'
                                        AND previous_permission_level IS NOT NULL
                                       THEN 1 ELSE 0 END)
                       FROM tenant_connections""",
                )
            row = cur.fetchone()
            total = row[0] or 0
            locked = row[1] or 0
            is_locked = total > 0 and locked >= total / 2
            return {
                "is_locked": bool(is_locked),
                "total_connections": total,
                "locked_connections": locked,
                "tenant_id": tenant_id,
            }
    except Exception as e:
        logger.exception("[Permissions] get_tenant_lock_status : %s", e)
        return {"is_locked": False, "total_connections": 0, "locked_connections": 0, "error": str(e)[:200]}


def toggle_all_read_only(
    tenant_id: Optional[str] = None,
    actor_role: str = "tenant_admin",
) -> dict:
    """Bouton 'Tout en lecture seule' : bascule toutes les connexions en 'read'
    ou restaure depuis previous_permission_level.

    Args:
        tenant_id: si fourni, limite au tenant. Si None (super admin global),
                   s applique a TOUS les tenants.
        actor_role: 'super_admin' (toutes les colonnes) ou 'tenant_admin'
                    (uniquement tenant_admin_permission_level)

    Retourne un dict avec le nombre de connexions affectees et l action
    ('locked' ou 'restored').
    """
    from app.database import get_pg_conn
    try:
        with get_pg_conn() as conn:
            cur = conn.cursor()
            # Determine si on est actuellement en mode 'tout read' (majorite
            # des connexions en 'read' avec un previous != NULL)
            where_tenant = "WHERE tenant_id = %s" if tenant_id else ""
            params = (tenant_id,) if tenant_id else ()
            cur.execute(
                f"""SELECT COUNT(*) FROM tenant_connections
                    {where_tenant}
                    {'AND' if tenant_id else 'WHERE'}
                    tenant_admin_permission_level = 'read'
                    AND previous_permission_level IS NOT NULL""",
                params,
            )
            locked_count = cur.fetchone()[0]
            cur.execute(
                f"""SELECT COUNT(*) FROM tenant_connections
                    {where_tenant}""",
                params,
            )
            total = cur.fetchone()[0]
            is_locked = locked_count > 0 and locked_count >= total / 2

            if is_locked:
                # Mode actuellement locked : on restaure les permissions
                # precedentes depuis previous_permission_level
                # NOTE : on ne touche PAS a super_admin_permission_level
                # (le plafond ne doit JAMAIS etre ecrase par le toggle,
                # sinon bug : cycle lock/unlock effondre le plafond a 'read')
                cur.execute(
                    f"""UPDATE tenant_connections
                        SET tenant_admin_permission_level =
                            COALESCE(previous_permission_level, 'read'),
                            previous_permission_level = NULL,
                            updated_at = NOW()
                        {where_tenant}""",
                    params,
                )
                action = "restored"
            else:
                # Mode normal : on passe tenant_admin_level en read, on
                # sauvegarde l ancien dans previous. On ne touche PAS au
                # plafond super_admin_permission_level.
                cur.execute(
                    f"""UPDATE tenant_connections
                        SET previous_permission_level =
                            tenant_admin_permission_level,
                            tenant_admin_permission_level = 'read',
                            updated_at = NOW()
                        {where_tenant}""",
                    params,
                )
                action = "locked"
            affected = cur.rowcount
            conn.commit()
        logger.info("[Permissions] toggle_all_read_only tenant=%s actor=%s "
                    "action=%s affected=%d",
                    tenant_id or "ALL", actor_role, action, affected)
        return {"action": action, "affected": affected, "tenant_id": tenant_id}
    except Exception as e:
        logger.exception("[Permissions] toggle_all_read_only : %s", e)
        return {"action": "error", "message": str(e)[:200]}
