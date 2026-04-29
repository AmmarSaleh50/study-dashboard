import logging
from contextlib import asynccontextmanager
from importlib.metadata import PackageNotFoundError, version as _pkg_version

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from . import db as db_module
from .config import get_settings

# Single source of truth for the running app's version: pyproject.toml.
# Falls back to "0.0.0" when running uninstalled (e.g. ad-hoc scripts).
try:
    APP_VERSION = _pkg_version("openstudy-api")
except PackageNotFoundError:
    APP_VERSION = "0.0.0"

# httpx logs every outbound request URL at INFO ("HTTP Request: POST <url>"),
# which leaked the Telegram bot token and n8n webhook path into docker logs
# (rotated 2026-04-28). Bumping the logger to WARNING keeps error/timeout
# diagnostics but suppresses the per-request URL line.
logging.getLogger("httpx").setLevel(logging.WARNING)
from .mcp_http import build_mcp_http_app


@asynccontextmanager
async def _lifespan(app: FastAPI):
    """Manage the Postgres pool's lifecycle. Opens on startup, closes on shutdown.

    Test environments swap `app.db._pool` directly via monkeypatch (see
    tests/conftest.py) and skip this lifespan; init_pool() is idempotent
    so calling it under those conditions is harmless either way.
    """
    await db_module.init_pool()
    try:
        yield
    finally:
        await db_module.close_pool()
from .routers import (
    auth as auth_router,
    dashboard as dashboard_router,
    courses as courses_router,
    slots as slots_router,
    exams as exams_router,
    study_topics as study_topics_router,
    deliverables as deliverables_router,
    tasks as tasks_router,
    events as events_router,
    lectures as lectures_router,
    oauth as oauth_router,
    files as files_router,
    settings as settings_router,
    internal as internal_router,
)


def create_app() -> FastAPI:
    settings = get_settings()

    # build_mcp_http_app() returns a per-request handler that spins up a
    # fresh MCP server + lifespan context for every inbound request.
    # Heavy compared to a long-lived session manager, but bulletproof
    # under ASGI runtimes that don't fire lifespan events reliably.
    mcp_app = build_mcp_http_app()

    # /api/docs (Swagger UI) and /api/openapi.json off by default. The schema
    # is recon assist for any attacker enumerating attack surface. Flip on
    # via EXPOSE_DOCS=true in .env when working locally.
    app = FastAPI(
        title="OpenStudy API",
        version=APP_VERSION,
        docs_url="/api/docs" if settings.expose_docs else None,
        redoc_url=None,
        openapi_url="/api/openapi.json" if settings.expose_docs else None,
        lifespan=_lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Health — checked by deploy.sh during rollouts. `ok` is true ONLY if
    # every dependency is reachable (db, storage). Returns 200 either way so
    # the caller can read the body for diagnostics.
    @app.get("/api/health")
    async def health() -> JSONResponse:
        from .services import storage as storage_svc

        out: dict = {"ok": True, "version": APP_VERSION}
        # DB check: trivial round-trip through the async pool. Uses
        # `SELECT 1` rather than a real table read so it stays cheap and
        # doesn't depend on any specific schema state.
        try:
            await db_module.fetchval("SELECT 1")
            out["db"] = "ok"
        except Exception as exc:
            out["db"] = f"error: {exc!s}"[:200]
            out["ok"] = False
        # Storage check: STUDY_ROOT must exist and be readable
        try:
            entries = await storage_svc.list_files("", limit=1)
            out["storage"] = f"ok ({len(entries)} entries seen)"
        except Exception as exc:
            out["storage"] = f"error: {exc!s}"[:200]
            out["ok"] = False
        return JSONResponse(out)

    # Mount routers under /api
    for r in [
        auth_router.router,
        dashboard_router.router,
        courses_router.router,
        slots_router.router,
        exams_router.router,
        study_topics_router.router,
        deliverables_router.router,
        tasks_router.router,
        events_router.router,
        lectures_router.router,
        files_router.router,
        settings_router.router,
        internal_router.router,
    ]:
        app.include_router(r, prefix="/api")

    # OAuth AS + well-known discovery live at the root (not /api/*) because
    # Claude.ai spec requires /.well-known/* at the resource server origin.
    app.include_router(oauth_router.router)

    # MCP Streamable HTTP endpoint at /mcp (auth-gated by the OAuth Bearer token).
    app.mount("/mcp", mcp_app)

    return app


app = create_app()
