"""
Raya — Assistant IA personnel (ex Couffrant Solar Assistant)
Point d'entrée principal. Setup, middleware, startup, routes.
"""
import os
import threading
import time

from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware

from app.config import SESSION_SECRET
from app.database import init_postgres
from app.feedback_store import init_db
from app.mail_memory_store import init_mail_db
from app.token_manager import get_valid_microsoft_token, get_all_users_with_tokens
from app.app_security import init_default_user
from app.memory_loader import MEMORY_OK, rebuild_hot_summary, seed_default_rules

from app.routes.auth import router as auth_router
from app.routes.admin import router as admin_router
from app.routes.aria import router as raya_router
from app.routes.memory import router as memory_router
from app.routes.mail import router as mail_router
from app.routes.reset_password import router as reset_router

app = FastAPI(title="Raya — Assistant IA")
app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET, max_age=30 * 24 * 3600)

app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(raya_router)
app.include_router(memory_router)
app.include_router(mail_router)
app.include_router(reset_router)


@app.get("/health")
def health():
    return {"status": "ok", "app": "Raya", "memory_module": MEMORY_OK}


@app.on_event("startup")
def startup_event():
    init_postgres()
    init_db()
    init_mail_db()
    try:
        init_default_user()
    except Exception as e:
        print(f"[Auth] Erreur init_default_user: {e}")
    try:
        admin_username = os.getenv("APP_USERNAME", "guillaume").strip()
        seed_default_rules(admin_username)
    except Exception as e:
        print(f"[Seed] Erreur seed_default_rules: {e}")

    def auto_ingest():
        cycle = 0
        while True:
            try:
                from app.graph_client import graph_get as _graph_get
                from app.ai_client import analyze_single_mail_with_ai as _analyze_ai
                from app.feedback_store import get_global_instructions as _get_instructions
                from app.assistant_analyzer import analyze_single_mail as _analyze
                from app.mail_memory_store import insert_mail, mail_exists
                from app.rule_engine import get_antispam_keywords as _get_spam, get_memoire_param as _get_param
                from app.app_security import get_tenant_id as _get_tenant

                users = get_all_users_with_tokens()

                for username in users:
                    try:
                        token = get_valid_microsoft_token(username)
                        if not token: continue
                        tenant_id = _get_tenant(username)
                        instructions = _get_instructions(tenant_id=tenant_id)
                        data = _graph_get(token, "/me/mailFolders/inbox/messages",
                            params={"$top": 10, "$select": "id,subject,from,receivedDateTime,bodyPreview",
                                    "$orderby": "receivedDateTime DESC"})
                        spam_kw = _get_spam(username)
                        for msg in data.get("value", []):
                            message_id = msg["id"]
                            if mail_exists(message_id, username): continue
                            _from = msg.get("from", {}).get("emailAddress", {}).get("address", "").lower()
                            _txt = f"{_from} {(msg.get('subject') or '').lower()} {(msg.get('bodyPreview') or '').lower()}"
                            if any(kw in _txt for kw in spam_kw): continue
                            try:
                                item = _analyze_ai(msg, instructions, username); analysis_status = "done_ai"
                            except Exception:
                                item = _analyze(msg, username); analysis_status = "fallback"
                            insert_mail({
                                "username": username, "message_id": message_id,
                                "received_at": msg.get("receivedDateTime"),
                                "from_email": msg.get("from", {}).get("emailAddress", {}).get("address"),
                                "subject": msg.get("subject"), "display_title": item.get("display_title"),
                                "category": item.get("category"), "priority": item.get("priority"),
                                "reason": item.get("reason"), "suggested_action": item.get("suggested_action"),
                                "short_summary": item.get("short_summary"), "group_hints": item.get("group_hints", []),
                                "confidence": item.get("confidence", 0.0), "needs_review": item.get("needs_review", False),
                                "raw_body_preview": msg.get("bodyPreview"), "analysis_status": analysis_status,
                                "needs_reply": item.get("needs_reply"), "reply_urgency": item.get("reply_urgency"),
                                "reply_reason": item.get("reply_reason"),
                                "suggested_reply_subject": item.get("suggested_reply_subject"),
                                "suggested_reply": item.get("suggested_reply"), "mailbox_source": "outlook",
                            })
                    except Exception as e:
                        print(f"[AutoIngest] Erreur pour {username}: {e}")

                cycle += 1
                try:
                    _rebuild_cycle = _get_param(users[0] if users else 'guillaume', "rebuild_cycles", 40)
                except Exception:
                    _rebuild_cycle = 40
                if cycle % _rebuild_cycle == 0 and MEMORY_OK:
                    for username in users:
                        try:
                            tenant_id = _get_tenant(username)
                            rebuild_hot_summary(username, tenant_id=tenant_id)
                        except Exception as e: print(f"[Memory] Erreur rebuild {username}: {e}")

            except Exception as e:
                print(f"[AutoIngest] Erreur générale: {e}")
            time.sleep(30)

    threading.Thread(target=auto_ingest, daemon=True).start()

    def token_refresh_loop():
        time.sleep(120)
        while True:
            try:
                for username in get_all_users_with_tokens():
                    try:
                        token = get_valid_microsoft_token(username)
                        print(f"[Token] Refresh {username}: {'OK' if token else 'ECHEC'}")
                    except Exception as e:
                        print(f"[Token] Erreur {username}: {e}")
            except Exception as e:
                print(f"[Token] Erreur générale: {e}")
            time.sleep(45 * 60)

    threading.Thread(target=token_refresh_loop, daemon=True).start()
