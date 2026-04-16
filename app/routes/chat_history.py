"""
Endpoint d'historique des conversations Raya. (CHAT-HISTORY)

GET /chat/history?limit=20
  - Vérifie session["user"] (sinon 401)
  - Retourne les derniers échanges de aria_memory + action cards liées, ordre chronologique
"""
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter(tags=["chat"])


@router.get("/chat/history")
def get_chat_history(request: Request, limit: int = 20):
    username = request.session.get("user")
    if not username:
        return JSONResponse({"error": "Non authentifié."}, status_code=401)

    limit = max(1, min(limit, 100))

    try:
        from app.database import get_pg_conn
        conn = get_pg_conn()
        c = conn.cursor()

        # 1. Historique des échanges
        c.execute("""
            SELECT user_input, aria_response, created_at, id
            FROM aria_memory
            WHERE username = %s
            ORDER BY created_at DESC
            LIMIT %s
        """, (username, limit))
        rows = list(reversed(c.fetchall()))

        if not rows:
            conn.close()
            return []

        # Action cards liées (optionnel — ne bloque pas si colonne absente)
        actions_by_conv = {}
        try:
            memory_ids = [row[3] for row in rows]
            placeholders = ','.join(['%s'] * len(memory_ids))
            c.execute(f"""
                SELECT id, action_type, action_label, payload_json, status, conversation_id
                FROM pending_actions
                WHERE conversation_id IN ({placeholders}) AND username = %s
                ORDER BY created_at ASC
            """, (*memory_ids, username))
            for ar in c.fetchall():
                aid, atype, alabel, apayload, astatus, aconv_id = ar
                if aconv_id not in actions_by_conv:
                    actions_by_conv[aconv_id] = []
                actions_by_conv[aconv_id].append({
                    "id": aid, "action_type": atype, "label": alabel,
                    "payload": apayload, "status": astatus,
                })
        except Exception:
            pass  # La colonne conversation_id peut ne pas exister encore
        conn.close()

        return [
            {
                "user":       row[0] or "",
                "raya":       row[1] or "",
                "ts":         str(row[2]) if row[2] else "",
                "created_at": str(row[2]) if row[2] else "",
                "id":         row[3],
                "actions":    actions_by_conv.get(row[3], []),
            }
            for row in rows
        ]

    except Exception as e:
        return JSONResponse({"error": str(e)[:100]}, status_code=500)

