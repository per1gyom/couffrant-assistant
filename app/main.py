"""
Raya
Point d'entree principal.
"""
import os
import time

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import SESSION_SECRET
from app.database import init_postgres
from app.feedback_store import init_db
from app.mail_memory_store import init_mail_db
from app.app_security import init_default_user
from app.memory_loader import MEMORY_OK
from app.logging_config import setup_logging, get_logger
import app.scheduler as job_scheduler

from app.routes.auth import router as auth_router
from app.routes.admin import router as admin_router
from app.routes.raya import router as raya_router
from app.routes.memory import router as memory_router
from app.routes.mail import router as mail_router
from app.routes.reset_password import router as reset_router
from app.routes.webhook import router as webhook_router
from app.routes.forced_reset import router as forced_reset_router
from app.routes.onboarding import router as onboarding_router
from app.routes.elicitation import router as elicitation_router


# Inactivité (secondes) avant déconnexion automatique. Défaut : 2h.
SESSION_INACTIVITY_TIMEOUT = int(os.getenv("SESSION_INACTIVITY_TIMEOUT", "7200"))


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com; "
            "img-src 'self' data: https://couffrant-solar.fr; "
            "connect-src 'self' https://api.anthropic.com; "
            "media-src 'self' blob:"
        )
        return response


class InactivityTimeoutMiddleware(BaseHTTPMiddleware):
    """
    Déconnecte l'utilisateur après SESSION_INACTIVITY_TIMEOUT secondes
    d'inactivité (défaut 2h). Met à jour last_activity à chaque requête.
    Ignore les routes publiques.
    """
    _PUBLIC = (
        "/login-app", "/logout", "/health", "/webhook/",
        "/static/", "/sw.js", "/forgot-password",
        "/reset-password", "/forced-reset",
    )

    async def dispatch(self, request: Request, call_next):
        if any(request.url.path.startswith(p) for p in self._PUBLIC):
            return await call_next(request)

        user = request.session.get("user")
        if user:
            last_activity = request.session.get("last_activity", 0)
            now = time.time()
            if last_activity and (now - last_activity) > SESSION_INACTIVITY_TIMEOUT:
                request.session.clear()
                from fastapi.responses import RedirectResponse as _Redir
                return _Redir("/login-app")
            request.session["last_activity"] = now

        return await call_next(request)


app = FastAPI(title="Raya")

setup_logging()
logger = get_logger("raya.main")

# Ordre d'ajout : inversé par Starlette → SecurityHeaders s'exécute en dernier,
# InactivityTimeout au milieu, SessionMiddleware en premier.
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(InactivityTimeoutMiddleware)
app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET, max_age=24 * 3600)

app.mount("/static", StaticFiles(directory="app/static"), name="static")

app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(raya_router)
app.include_router(memory_router)
app.include_router(mail_router)
app.include_router(reset_router)
app.include_router(webhook_router)
app.include_router(forced_reset_router)
app.include_router(onboarding_router)
app.include_router(elicitation_router)


@app.get("/")
def root():
    return RedirectResponse("/chat")


@app.get("/health")
def health():
    checks = {"app": "Raya", "memory_module": MEMORY_OK}
    try:
        from app.database import get_pg_conn
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("SELECT 1")
        conn.close()
        checks["database"] = "ok"
    except Exception as e:
        checks["database"] = f"error: {str(e)[:100]}"
        checks["status"] = "degraded"
    try:
        from app.config import ANTHROPIC_API_KEY
        checks["llm"] = "ok" if ANTHROPIC_API_KEY else "missing_key"
    except Exception:
        checks["llm"] = "error"
    if "status" not in checks:
        checks["status"] = "ok"
    return checks


@app.get("/sw.js")
def service_worker():
    return FileResponse(
        "app/static/sw.js",
        media_type="application/javascript",
        headers={"Service-Worker-Allowed": "/"},
    )


@app.on_event("startup")
def startup_event():
    init_postgres()
    init_db()
    init_mail_db()
    try:
        init_default_user()
    except Exception as e:
        logger.error(f"[Raya] Erreur init_default_user: {e}")

    try:
        from app.seeding import seed_tenant, is_tenant_seeded
        admin_username = os.getenv("APP_USERNAME", "guillaume").strip()
        if not is_tenant_seeded(admin_username):
            logger.info(f"[Raya] Seeding initial pour {admin_username}")
            counts = seed_tenant("couffrant_solar", admin_username, profile="pv_french")
            logger.info(f"[Raya] Seeding termine : {counts}")
        else:
            logger.info(f"[Raya] {admin_username} deja seede, skip")
    except Exception as e:
        logger.error(f"[Raya] Erreur seeding: {e}")

    try:
        from app.tools_registry import seed_tools_registry
        seed_tools_registry()
    except Exception as e:
        logger.error(f"[ToolsRegistry] Erreur seed: {e}")

    try:
        job_scheduler.start()
    except Exception as e:
        logger.error(f"[Scheduler] Erreur demarrage: {e}")


@app.on_event("shutdown")
def shutdown_event():
    try:
        job_scheduler.stop()
    except Exception as e:
        logger.error(f"[Scheduler] Erreur arret: {e}")
