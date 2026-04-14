"""
RGPD — Export et suppression des données personnelles. (C3-1)

GET  /account/export  → JSON de toutes les données de l'utilisateur (pièce jointe)
DELETE /account/delete → Suppression du compte (require ?confirm=yes)
"""
import io
import json
from datetime import datetime, date

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from app.routes.deps import require_user
from app.logging_config import get_logger

logger = get_logger("raya.rgpd")
router = APIRouter(tags=["rgpd"])

# Tables personnelles exportées — même liste que delete_user() dans security_users.py
_PERSONAL_TABLES = [
    "user_tools", "oauth_tokens", "aria_memory", "aria_hot_summary",
    "aria_style_examples", "aria_session_digests", "aria_profile",
    "reply_learning_memory", "sent_mail_memory", "proactive_alerts",
    "daily_reports", "email_signatures", "bug_reports",
    "aria_rules", "aria_insights", "user_topics",
]


def _json_default(obj):
    """Sérialiseur JSON pour les types non natifs (dates, etc.)."""
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    return str(obj)


@router.get("/account/export")
def export_account_data(user: dict = Depends(require_user)):
    """
    Exporte toutes les données personnelles de l'utilisateur en JSON.
    Retourne un fichier en pièce jointe.
    """
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


@router.delete("/account/delete")
def delete_account(
    request: Request,
    user: dict = Depends(require_user),
    confirm: str = "",
):
    """
    Supprime définitivement le compte de l'utilisateur connecté.
    Requiert ?confirm=yes pour éviter les suppressions accidentelles.
    """
    if confirm.lower() != "yes":
        return {"ok": False, "message": "Ajoute ?confirm=yes pour confirmer la suppression."}

    username = user["username"]
    logger.warning("[RGPD] Suppression compte demandée par %s", username)

    try:
        from app.security_users import delete_user
        result = delete_user(username, requesting_user="system")
    except Exception as e:
        logger.error("[RGPD] Échec suppression %s : %s", username, e)
        return {"ok": False, "message": f"Erreur suppression : {str(e)[:100]}"}

    if result.get("status") != "ok":
        return {"ok": False, "message": result.get("message", "Erreur inconnue")}

    try:
        request.session.clear()
    except Exception:
        pass

    logger.info("[RGPD] Compte %s supprimé avec succès", username)
    return {"ok": True, "message": "Compte supprimé. Toutes vos données personnelles ont été effacées."}
