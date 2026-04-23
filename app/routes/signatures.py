"""
CRUD signatures email utilisateur.
GET  /signatures              → liste
POST /signatures              → créer
PATCH /signatures/{id}        → modifier
DELETE /signatures/{id}       → supprimer
GET  /signatures/mailboxes    → boîtes mail disponibles
"""
from fastapi import APIRouter, Request, Depends
from fastapi.responses import JSONResponse
from app.routes.deps import require_user
from app.logging_config import get_logger

logger = get_logger("raya.signatures")
router = APIRouter(tags=["signatures"])


def _get_conn():
    from app.database import get_pg_conn
    return get_pg_conn()


@router.get("/signatures")
def list_signatures(user: dict = Depends(require_user)):
    username = user["username"]
    tenant_id = user["tenant_id"]
    conn = None
    try:
        conn = _get_conn(); c = conn.cursor()
        c.execute("""
            SELECT id, name, signature_html, apply_to_emails, is_default, updated_at
            FROM email_signatures WHERE username = %s
              AND (tenant_id = %s OR tenant_id IS NULL)
            ORDER BY is_default DESC, updated_at DESC
        """, (username, tenant_id))
        rows = c.fetchall()
        return [{"id": r[0], "name": r[1] or f"Signature {r[0]}",
                 "signature_html": r[2], "apply_to_emails": r[3] or [],
                 "is_default": r[4] or False,
                 "updated_at": str(r[5]) if r[5] else ""} for r in rows]
    except Exception as e:
        return JSONResponse({"error": str(e)[:100]}, status_code=500)
    finally:
        if conn: conn.close()


@router.post("/signatures")
async def create_signature(request: Request, user: dict = Depends(require_user)):
    username = user["username"]
    tenant_id = user.get("tenant_id", "couffrant_solar")
    data = await request.json()
    name = (data.get("name") or "Nouvelle signature").strip()[:100]
    html = data.get("signature_html", "").strip()
    emails = data.get("apply_to_emails", [])
    is_default = bool(data.get("is_default", False))
    if not html:
        return JSONResponse({"error": "signature_html requis"}, status_code=400)
    conn = None
    try:
        conn = _get_conn(); c = conn.cursor()
        if is_default:
            c.execute(
                "UPDATE email_signatures SET is_default=false "
                "WHERE username=%s AND (tenant_id = %s OR tenant_id IS NULL)",
                (username, tenant_id))
        c.execute("""
            INSERT INTO email_signatures
              (username, tenant_id, name, signature_html, apply_to_emails, is_default, updated_at)
            VALUES (%s,%s,%s,%s,%s,%s,NOW()) RETURNING id
        """, (username, tenant_id, name, html, emails, is_default))
        new_id = c.fetchone()[0]
        conn.commit()
        return {"ok": True, "id": new_id}
    except Exception as e:
        return JSONResponse({"error": str(e)[:100]}, status_code=500)
    finally:
        if conn: conn.close()


@router.patch("/signatures/{sig_id}")
async def update_signature(sig_id: int, request: Request, user: dict = Depends(require_user)):
    username = user["username"]
    tenant_id = user["tenant_id"]
    data = await request.json()
    conn = None
    try:
        conn = _get_conn(); c = conn.cursor()
        c.execute(
            "SELECT id FROM email_signatures WHERE id=%s AND username=%s "
            "AND (tenant_id = %s OR tenant_id IS NULL)",
            (sig_id, username, tenant_id))
        if not c.fetchone():
            return JSONResponse({"error": "Introuvable"}, status_code=404)
        fields, vals = [], []
        for key, col in [("name","name"), ("signature_html","signature_html"),
                         ("apply_to_emails","apply_to_emails"), ("is_default","is_default")]:
            if key in data:
                fields.append(f"{col}=%s"); vals.append(data[key])
        if not fields:
            return {"ok": True}
        if "is_default" in data and data["is_default"]:
            c.execute(
                "UPDATE email_signatures SET is_default=false "
                "WHERE username=%s AND id!=%s AND (tenant_id = %s OR tenant_id IS NULL)",
                (username, sig_id, tenant_id))
        vals += [sig_id, username, tenant_id]
        c.execute(f"UPDATE email_signatures SET {','.join(fields)},updated_at=NOW() "
                  f"WHERE id=%s AND username=%s "
                  f"AND (tenant_id = %s OR tenant_id IS NULL)", vals)
        conn.commit()
        return {"ok": True}
    except Exception as e:
        return JSONResponse({"error": str(e)[:100]}, status_code=500)
    finally:
        if conn: conn.close()


@router.delete("/signatures/{sig_id}")
def delete_signature(sig_id: int, user: dict = Depends(require_user)):
    username = user["username"]
    tenant_id = user["tenant_id"]
    conn = None
    try:
        conn = _get_conn(); c = conn.cursor()
        c.execute(
            "DELETE FROM email_signatures WHERE id=%s AND username=%s "
            "AND (tenant_id = %s OR tenant_id IS NULL)",
            (sig_id, username, tenant_id))
        conn.commit()
        return {"ok": True}
    except Exception as e:
        return JSONResponse({"error": str(e)[:100]}, status_code=500)
    finally:
        if conn: conn.close()


@router.get("/signatures/mailboxes")
def get_mailboxes(user: dict = Depends(require_user)):
    """Retourne toutes les boîtes mail connectées de l'utilisateur."""
    username = user["username"]
    mailboxes = []
    seen = set()

    # 1. Connexions V2 (tenant_connections) — source principale
    try:
        from app.connection_token_manager import get_user_tool_connections
        conns = get_user_tool_connections(username)
        for tool_type, info in conns.items():
            if tool_type in ("microsoft", "outlook") and info.get("email"):
                addr = info["email"]
                if addr not in seen:
                    seen.add(addr)
                    mailboxes.append({"address": addr, "label": f"Outlook — {addr}", "provider": "microsoft"})
            elif tool_type in ("gmail", "google") and info.get("email"):
                addr = info["email"]
                if addr not in seen:
                    seen.add(addr)
                    mailboxes.append({"address": addr, "label": f"Gmail — {addr}", "provider": "gmail"})
    except Exception:
        pass

    # 2. Fallback legacy si aucune connexion V2
    conn = None
    try:
        conn = _get_conn(); c = conn.cursor()

        # Microsoft — via Graph /me si absent
        if not any(m["provider"] == "microsoft" for m in mailboxes):
            c.execute("SELECT email FROM users WHERE username=%s LIMIT 1", (username,))
            row = c.fetchone()
            ms_email = (row[0] if row and row[0] and 'raya-ia.fr' not in row[0] else None)
            if not ms_email:
                try:
                    from app.token_manager import get_valid_microsoft_token
                    from app.graph_client import graph_get
                    token = get_valid_microsoft_token(username)
                    if token:
                        me = graph_get(token, "/me", params={"$select": "mail,userPrincipalName"})
                        candidate = me.get("mail") or me.get("userPrincipalName") or ""
                        if candidate and '@' in candidate and 'raya-ia.fr' not in candidate:
                            ms_email = candidate
                            c.execute(
                                "UPDATE users SET email=%s WHERE username=%s "
                                "AND (email IS NULL OR email ILIKE '%%raya-ia.fr%%')",
                                (ms_email, username)
                            )
                            conn.commit()
                except Exception:
                    pass
            if ms_email and ms_email not in seen:
                seen.add(ms_email)
                mailboxes.append({"address": ms_email, "label": f"Outlook — {ms_email}", "provider": "microsoft"})

        # Gmail legacy
        if not any(m["provider"] == "gmail" for m in mailboxes):
            c.execute("SELECT email FROM gmail_tokens WHERE username=%s LIMIT 1", (username,))
            row = c.fetchone()
            if row and row[0] and row[0] not in seen:
                seen.add(row[0])
                mailboxes.append({"address": row[0], "label": f"Gmail — {row[0]}", "provider": "gmail"})

        # Boîtes extra (user_tools config)
        from app.app_security import get_user_tools
        tools = get_user_tools(username)
        extra = tools.get("outlook", {}).get("config", {}).get("mailboxes", [])
        for addr in extra:
            if addr and addr not in seen:
                seen.add(addr)
                mailboxes.append({"address": addr, "label": addr, "provider": "microsoft"})
    except Exception:
        pass
    finally:
        if conn: conn.close()
    return mailboxes
