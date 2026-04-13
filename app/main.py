""" 
Raya
Point d'entree principal.
"""
import os
import time
import io

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse, FileResponse, Response
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
from app.routes.downloads import router as downloads_router
from app.routes.chat_history import router as chat_history_router


# Inactivite (secondes) avant deconnexion automatique. Defaut : 2h.
SESSION_INACTIVITY_TIMEOUT = int(os.getenv("SESSION_INACTIVITY_TIMEOUT", "7200"))

# Cache des icones PNG generees
_PNG_CACHE: dict = {}


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
            "img-src 'self' data: https://couffrant-solar.fr https://oaidalleapiprodscus.blob.core.windows.net; "
            "connect-src 'self' https://api.anthropic.com; "
            "media-src 'self' blob:"
        )
        return response


class InactivityTimeoutMiddleware(BaseHTTPMiddleware):
    _PUBLIC = (
        "/login-app", "/logout", "/health", "/webhook/",
        "/static/", "/sw.js", "/forgot-password",
        "/reset-password", "/forced-reset",
        "/pwa/",
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
app.include_router(downloads_router)
app.include_router(chat_history_router)


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


def _generate_raya_png(size: int) -> bytes:
    """
    Genere un PNG carre OPAQUE violet (#6366f1) avec un eclair blanc centre.
    IMPORTANT: RGB (pas RGBA) — iOS Safari refuse les icones transparentes.
    iOS ajoute automatiquement ses propres coins arrondis.
    """
    if size in _PNG_CACHE:
        return _PNG_CACHE[size]
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        _PNG_CACHE[size] = (
            b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01'
            b'\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f'
            b'\x00\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82'
        )
        return _PNG_CACHE[size]

    # Fond opaque violet — pas de transparence
    color = (99, 102, 241)  # #6366f1
    img = Image.new("RGB", (size, size), color)
    draw = ImageDraw.Draw(img)

    # Eclair blanc (polygone)
    s = size
    bolt = [
        (s * 0.58, s * 0.10),
        (s * 0.35, s * 0.52),
        (s * 0.52, s * 0.52),
        (s * 0.42, s * 0.90),
        (s * 0.65, s * 0.48),
        (s * 0.48, s * 0.48),
    ]
    draw.polygon(bolt, fill=(255, 255, 255))

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    result = buf.getvalue()
    _PNG_CACHE[size] = result
    return result


@app.get("/pwa/icon-180.png")
def pwa_icon_180():
    png = _generate_raya_png(180)
    return Response(
        content=png,
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=604800"},
    )


@app.get("/pwa/icon-192.png")
def pwa_icon_192():
    png = _generate_raya_png(192)
    return Response(
        content=png,
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=604800"},
    )


@app.get("/pwa/icon-512.png")
def pwa_icon_512():
    png = _generate_raya_png(512)
    return Response(
        content=png,
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=604800"},
    )


def _init_heartbeats():
    try:
        from app.database import get_pg_conn
        conn = get_pg_conn()
        c = conn.cursor()
        components = [
            "scheduler", "proactivity_scan", "heartbeat_morning",
            "webhook_microsoft", "gmail_polling",
        ]
        for component in components:
            c.execute("""
                INSERT INTO system_heartbeat (component, last_seen_at, status)
                VALUES (%s, NOW(), 'ok')
                ON CONFLICT (component)
                DO UPDATE SET last_seen_at = NOW(), status = 'ok'
                WHERE system_heartbeat.status != 'disabled'
            """, (component,))
        conn.commit()
        conn.close()
        logger.info(f"[Heartbeat] {len(components)} composants initialises au demarrage")
    except Exception as e:
        logger.warning(f"[Heartbeat] Erreur init heartbeats: {e}")


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

    _init_heartbeats()


@app.on_event("shutdown")
def shutdown_event():
    try:
        job_scheduler.stop()
    except Exception as e:
        logger.error(f"[Scheduler] Erreur arret: {e}")
