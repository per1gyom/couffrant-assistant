"""
Endpoint d'historique des conversations Raya. (CHAT-HISTORY)

GET /chat/history?limit=20
  - Vérifie session["user"] (sinon 401)
  - Retourne les derniers échanges de aria_memory, ordre chronologique
  - [{"user": "...", "raya": "...", "ts": "...", "id": 123}, ...]
"""
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter(tags=["chat"])


@router.get("/chat/history")
def get_chat_history(request: Request, limit: int = 20):
    """
    Retourne les derniers échanges de l'utilisateur connecté.
    Limite entre 1 et 100. Ordre chronologique (plus ancien en premier).
    """
    username = request.session.get("user")
    if not username:
        return JSONResponse({"error": "Non authentifié."}, status_code=401)

    limit = max(1, min(limit, 100))

    try:
        from app.database import get_pg_conn
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            SELECT user_input, aria_response, created_at, id
            FROM aria_memory
            WHERE username = %s
            ORDER BY created_at DESC
            LIMIT %s
        """, (username, limit))
        rows = c.fetchall()
        conn.close()

        # Inverser pour ordre chronologique (plus ancien → plus récent)
        rows = list(reversed(rows))

        return [
            {
                "user": row[0] or "",
                "raya": row[1] or "",
                "ts":   str(row[2]) if row[2] else "",
                "id":   row[3],
            }
            for row in rows
        ]

    except Exception as e:
        return JSONResponse({"error": str(e)[:100]}, status_code=500)
