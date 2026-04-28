"""
RGPD — Export et suppression des données personnelles. (C3-1)

GET    /account/export          → JSON de toutes les données (pièce jointe)
POST   /account/delete/request  → Demande de suppression (vérif. mot de passe)
DELETE /account/delete/cancel   → Annule sa propre demande
DELETE /account/delete          → Suppression directe (super_admin uniquement)
"""
import io
import json
from datetime import datetime, date

from fastapi import APIRouter, Depends, Request, Body
from fastapi.responses import StreamingResponse

from app.routes.deps import require_user
from app.app_security import SCOPE_ADMIN, SCOPE_SUPER_ADMIN
from app.logging_config import get_logger

logger = get_logger("raya.rgpd")
router = APIRouter(tags=["rgpd"])

_PERSONAL_TABLES = [
    "user_tools", "oauth_tokens", "aria_memory", "aria_hot_summary",
    "aria_style_examples", "aria_session_digests", "aria_profile",
    "reply_learning_memory", "sent_mail_memory", "proactive_alerts",
    "daily_reports", "email_signatures", "bug_reports",
    "aria_rules", "aria_insights", "user_topics",
]


def _json_default(obj):
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    return str(obj)


@router.get("/account/export")
def export_account_data(user: dict = Depends(require_user)):
    """Exporte toutes les données personnelles de l'utilisateur en JSON."""
    username = user["username"]
    export_data = {"username": username, "exported_at": datetime.utcnow().isoformat(), "tables": {}}
    conn = None
    try:
        from app.database import get_pg_conn
        conn = get_pg_conn()
        c = conn.cursor()
        for table in _PERSONAL_TABLES:
            try:
                c.execute(f"SELECT * FROM {table} WHERE username = %s", (username,))
                cols = [d[0] for d in c.description]
                rows = [dict(zip(cols, r)) for r in c.fetchall()]
                export_data["tables"][table] = rows
            except Exception as e:
                export_data["tables"][table] = {"error": str(e)[:100]}
        logger.info("[RGPD] Export données pour %s (%d tables)", username, len(_PERSONAL_TABLES))
    except Exception as e:
        logger.warning("[RGPD] Export échoué pour %s : %s", username, e)
        export_data["error"] = str(e)[:200]
    finally:
        if conn:
            conn.close()

    json_bytes = json.dumps(export_data, ensure_ascii=False, indent=2, default=_json_default).encode("utf-8")
    date_str = datetime.utcnow().strftime("%Y%m%d")
    filename = f"raya_export_{username}_{date_str}.json"
    return StreamingResponse(
        io.BytesIO(json_bytes),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/account/delete/request")
def request_account_deletion(
    request: Request,
    payload: dict = Body(...),
    user: dict = Depends(require_user),
):
    """
    L'utilisateur demande la suppression de son compte.
    Vérifie son mot de passe, pose le flag deletion_requested_at.
    L'admin de la société doit ensuite confirmer.
    """
    from app.user_crud import authenticate
    from app.database import get_pg_conn

    username = user["username"]
    password = payload.get("password", "")

    if not password:
        return {"status": "error", "message": "Mot de passe requis pour confirmer la demande."}

    if not authenticate(username, password):
        return {"status": "error", "message": "Mot de passe incorrect."}

    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute(
            "UPDATE users SET deletion_requested_at = NOW() WHERE username = %s",
            (username,)
        )
        conn.commit()
        logger.warning("[RGPD] Demande suppression compte : %s", username)
        return {
            "status": "ok",
            "message": "Demande envoyée. Votre administrateur sera notifié et devra valider la suppression."
        }
    except Exception as e:
        return {"status": "error", "message": str(e)[:100]}
    finally:
        if conn:
            conn.close()


@router.delete("/account/delete/cancel")
def cancel_account_deletion(
    request: Request,
    user: dict = Depends(require_user),
):
    """L'utilisateur annule sa propre demande de suppression."""
    from app.database import get_pg_conn
    username = user["username"]
    conn = None
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("UPDATE users SET deletion_requested_at = NULL WHERE username = %s", (username,))
        conn.commit()
        logger.info("[RGPD] Demande suppression annulée par %s", username)
        return {"status": "ok", "message": "Demande de suppression annulée."}
    except Exception as e:
        return {"status": "error", "message": str(e)[:100]}
    finally:
        if conn:
            conn.close()


@router.delete("/account/delete")
def delete_account(
    request: Request,
    user: dict = Depends(require_user),
    confirm: str = "",
):
    """
    Suppression directe — réservée au super admin (auto-suppression via panel admin).
    Les utilisateurs classiques passent par /account/delete/request.
    """
    if user.get("scope") not in (SCOPE_ADMIN, SCOPE_SUPER_ADMIN):
        return {"ok": False, "message": "Utilisez la procédure de demande de suppression."}
    if confirm.lower() != "yes":
        return {"ok": False, "message": "Ajoute ?confirm=yes pour confirmer."}

    username = user["username"]
    logger.warning("[RGPD] Suppression directe (super_admin) : %s", username)
    try:
        from app.security_users import delete_user
        result = delete_user(username, requesting_user="system")
    except Exception as e:
        return {"ok": False, "message": str(e)[:100]}
    if result.get("status") != "ok":
        return {"ok": False, "message": result.get("message", "Erreur inconnue")}
    try:
        request.session.clear()
    except Exception:
        pass
    return {"ok": True, "message": "Compte supprimé."}
