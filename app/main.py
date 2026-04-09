"""
Raya — Assistant IA personnel
Point d'entrée principal. Setup, middleware, startup, routes.
"""
import os
import threading
import time

from fastapi import FastAPI, Request
from fastapi.responses import Response, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import SESSION_SECRET
from app.database import init_postgres
from app.feedback_store import init_db
from app.mail_memory_store import init_mail_db
from app.token_manager import get_valid_microsoft_token, get_all_users_with_tokens
from app.app_security import init_default_user
from app.memory_loader import MEMORY_OK, seed_default_rules

from app.routes.auth import router as auth_router
from app.routes.admin import router as admin_router
from app.routes.raya import router as raya_router
from app.routes.memory import router as memory_router
from app.routes.mail import router as mail_router
from app.routes.reset_password import router as reset_router
from app.routes.webhook import router as webhook_router
from app.routes.forced_reset import router as forced_reset_router


# ─── MIDDLEWARE HEADERS DE SÉCURITÉ ───

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Ajoute les headers HTTP de sécurité sur toutes les réponses.
    - X-Content-Type-Options : empêche le sniffing MIME
    - X-Frame-Options : empêche le clickjacking
    - X-XSS-Protection : protection XSS navigateurs anciens
    - Referrer-Policy : limite les fuites d'URL
    - Content-Security-Policy : restreint les sources de contenu
    """
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        # CSP adaptée à l'app : Google Fonts, inline styles/scripts nécessaires
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com; "
            "img-src 'self' data: https://couffrant-solar.fr; "
            "connect-src 'self' https://api.anthropic.com; "
            "media-src 'self' blob:"
        )
        return response


app = FastAPI(title="Raya — Assistant IA")

# Ordre important : SecurityHeaders avant SessionMiddleware
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET, max_age=30 * 24 * 3600)

# Fichiers statiques (CSS, JS)
app.mount("/static", StaticFiles(directory="app/static"), name="static")

app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(raya_router)
app.include_router(memory_router)
app.include_router(mail_router)
app.include_router(reset_router)
app.include_router(webhook_router)
app.include_router(forced_reset_router)


@app.get("/")
def root():
    return RedirectResponse("/chat")


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
        print(f"[Raya] Erreur init_default_user: {e}")
    try:
        admin_username = os.getenv("APP_USERNAME", "guillaume").strip()
        seed_default_rules(admin_username)
    except Exception as e:
        print(f"[Raya] Erreur seed_default_rules: {e}")

    def setup_webhooks():
        time.sleep(30)
        try:
            from app.connectors.microsoft_webhook import ensure_all_subscriptions
            ensure_all_subscriptions()
        except Exception as e:
            print(f"[Webhook] Erreur setup initial: {e}")

    threading.Thread(target=setup_webhooks, daemon=True).start()

    def webhook_renewal_loop():
        time.sleep(60)
        while True:
            try:
                time.sleep(6 * 3600)
                from app.connectors.microsoft_webhook import ensure_all_subscriptions
                ensure_all_subscriptions()
            except Exception as e:
                print(f"[Webhook] Erreur renouvellement: {e}")

    threading.Thread(target=webhook_renewal_loop, daemon=True).start()

    def token_refresh_loop():
        time.sleep(120)
        while True:
            try:
                for username in get_all_users_with_tokens():
                    try:
                        token = get_valid_microsoft_token(username)
                        if not token:
                            print(f"[Token] ECHEC refresh {username} — alerte envoyée")
                            try:
                                from app.connectors.microsoft_webhook import _send_revoked_alert
                                _send_revoked_alert(username)
                            except Exception:
                                pass
                        else:
                            print(f"[Token] Refresh {username}: OK")
                    except Exception as e:
                        print(f"[Token] Erreur {username}: {e}")
            except Exception as e:
                print(f"[Token] Erreur générale: {e}")
            time.sleep(45 * 60)

    threading.Thread(target=token_refresh_loop, daemon=True).start()
