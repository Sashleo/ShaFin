"""
app.py — ShaFin FastAPI application.

Mounts routers, middleware, static files and templates. Startup fails closed: no
liboqs, no database key or a failed security self-test stops the app.
"""

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.httpsredirect import HTTPSRedirectMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
import structlog

from config.settings import settings
from database.connection import init_database
from database.schema import run_migrations
from security.auth import SessionMiddleware
from core.scheduler import run_scheduler
from core.logging import configure_logging, RequestIdMiddleware

from routers import (
    analyser,
    auth,
    dashboard,
    data,
    reports,
    settings as settings_router,
    health as health_router,
)

log = structlog.get_logger()

configure_logging(
    level="DEBUG" if settings.DEBUG else "INFO",
    json_output=not settings.DEBUG,
)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    log.info("ShaFin starting up", version=settings.APP_VERSION)
    from security.pqc import require_pqc
    log.info("liboqs ready", version=require_pqc())
    init_database()
    try:
        from database.backup import backup_database
        backup_database()
        log.info("Pre-migration backup taken")
    except Exception as _e:
        log.warning("Pre-migration backup failed — continuing startup", error=str(_e)[:120])
    run_migrations()
    log.info("Database initialised")
    from security.selftest import run_self_test
    failures = run_self_test()
    if failures:
        raise RuntimeError("Security self-test failed: " + "; ".join(failures))
    if settings.DEMO_MODE:
        from demo.loader import ensure_demo_owner, load_demo_companies
        ensure_demo_owner()
    from database.connection import get_db
    if get_db().execute("SELECT 1 FROM users LIMIT 1").fetchone():
        from reports.signer import ensure_signing_key
        from security.keys import get_master_key
        info = ensure_signing_key(get_master_key())
        log.info("Signing key ready", fingerprint=info["fingerprint"])
    if settings.DEMO_MODE:
        load_demo_companies()
    scheduler = asyncio.create_task(run_scheduler())
    log.info("Job scheduler started")
    yield
    scheduler.cancel()
    from database.connection import close_database
    close_database()


def create_app() -> FastAPI:
    app = FastAPI(
        title="ShaFin",
        description="Financial statement analysis from figures you enter",
        version=settings.APP_VERSION,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )

    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(HTTPSRedirectMiddleware)
    app.add_middleware(SessionMiddleware, secret_key=settings.APP_SECRET_KEY)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["https://localhost:8000", "https://127.0.0.1:8000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.mount("/static", StaticFiles(directory="static"), name="static")

    app.include_router(auth.router,             prefix="",           tags=["auth"])
    app.include_router(dashboard.router,        prefix="/dashboard",  tags=["dashboard"])
    app.include_router(analyser.router,         prefix="/analyser",   tags=["analyser"])
    app.include_router(reports.router,          prefix="/reports",    tags=["reports"])
    app.include_router(data.router,             prefix="/settings/data", tags=["data"])
    app.include_router(settings_router.router,  prefix="/settings",   tags=["settings"])
    app.include_router(health_router.router,    prefix="/health",     tags=["health"])

    @app.get("/healthz")
    async def healthz():
        """Public liveness probe for Docker. Deliberately says nothing else."""
        try:
            from database.connection import get_db
            get_db().execute("SELECT 1")
        except Exception:
            return JSONResponse({"status": "unavailable"}, status_code=503)
        return {"status": "ok"}

    @app.exception_handler(StarletteHTTPException)
    async def http_error_page(request: Request, exc: StarletteHTTPException):
        """HTML pages for browsers, JSON for everything else."""
        if "text/html" in request.headers.get("accept", "") and "HX-Request" not in request.headers:
            from routers.common import templates
            return templates.TemplateResponse(request, "error.html", {
                "status": exc.status_code, "detail": exc.detail}, status_code=exc.status_code)
        return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)

    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        import traceback as _tb, uuid as _uuid
        from fastapi.responses import HTMLResponse as _HTML
        rid = _uuid.uuid4().hex[:12]
        log.error(
            "Unhandled exception",
            request_id=rid,
            path=str(request.url.path),
            error=str(exc),
            traceback=_tb.format_exc(),
        )
        accept = request.headers.get("accept", "")
        is_htmx = "HX-Request" in request.headers
        if "text/html" in accept and not is_htmx:
            return _HTML(
                status_code=500,
                content=f"""<!doctype html>
<html lang="en"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Error — ShaFin</title>
<link rel="stylesheet" href="/static/css/tokens.css">
<link rel="stylesheet" href="/static/css/base.css">
</head><body style="max-width:600px;margin:5rem auto;padding:0 1rem">
<h2 style="color:var(--neg)">Something went wrong</h2>
<p>An unexpected error occurred. Reference ID: <code style="font-family:var(--font-mono);background:var(--surface-2);padding:2px 6px;border-radius:4px">{rid}</code></p>
<p style="color:var(--text-muted);font-size:0.9rem">Find the full traceback in the server logs by searching for <code>request_id={rid}</code>.</p>
<p style="margin-top:2rem"><a href="/" style="color:var(--accent)">Return to dashboard</a></p>
</body></html>""",
            )
        return JSONResponse(
            status_code=500,
            content={"detail": "An internal error occurred.", "request_id": rid},
        )

    return app


app = create_app()
