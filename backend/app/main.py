"""FastAPI application entry point.

Lifespan handles: logging, DB schema (dev), default-user seeding, binding the asyncio
loop for thread-safe SSE, and starting/stopping the ingestion scheduler.

Run:  uvicorn app.main:app --reload --port 8000
Docs: http://localhost:8000/docs   Health: http://localhost:8000/health/deep
"""
from __future__ import annotations

import asyncio
from contextlib import AsyncExitStack, asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.v1.router import api_router
from app.core.bootstrap import ensure_default_users
from app.core.config import REPO_ROOT, settings
from app.core.db import SessionLocal, init_db
from app.core.logging import configure_logging, get_logger
from app.ingestion import scheduler
from app.sse import bus

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging("INFO")
    logger.info("Starting %s (env=%s)", settings.app_name, settings.env)

    # 1) schema + seed (dev convenience; prod uses alembic + managed users)
    init_db()
    with SessionLocal() as session:
        ensure_default_users(session)

    # 2) bind the running loop so worker-thread ingestion can publish SSE events
    bus.set_loop(asyncio.get_running_loop())

    # 3) scheduler + startup bootstrap (seed empty DB / catch up stale data)
    scheduler.start_scheduler()
    scheduler.bootstrap_on_startup()

    async with AsyncExitStack() as stack:
        # Optional MCP tool outlet: run its streamable-HTTP session manager for
        # the whole app lifetime (a mounted sub-app's own lifespan never runs).
        if _mcp_lifespan is not None:
            await stack.enter_async_context(_mcp_lifespan())
        yield

    logger.info("Shutting down %s", settings.app_name)
    scheduler.shutdown_scheduler()
    bus.set_loop(None)


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="股票研报聚合平台 — 研报/评级/行情/财务/股指期货期权 聚合 (数据来源: AkShare + 巨潮/交易所)",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)

# MCP tool outlet for external AI clients — mounted BEFORE the SPA catch-all so
# "/mcp" wins. Optional: only when FEATURE_MCP=true and the 'mcp' package is
# installed; a missing package degrades to a logged error, never a boot failure.
_mcp_lifespan = None
if settings.feature_mcp:
    try:
        from app.mcp.server import mcp_asgi, mcp_lifespan

        app.mount(settings.mcp_path, mcp_asgi())
        _mcp_lifespan = mcp_lifespan
        if settings.mcp_token:
            logger.info("MCP endpoint mounted at %s (token required)", settings.mcp_path)
        else:
            logger.warning("MCP endpoint mounted at %s WITHOUT a token (MCP_TOKEN empty)", settings.mcp_path)
    except Exception as exc:  # noqa: BLE001 - optional outlet must never block boot
        logger.error("MCP endpoint disabled: %s. Install 'mcp>=1.9,<2' and restart.", exc)


@app.get("/", include_in_schema=False)
def root() -> JSONResponse:
    return JSONResponse({
        "app": settings.app_name,
        "docs": "/docs",
        "health": "/health/deep",
        "frontend": "run `npm run dev` in frontend/ (http://localhost:5173)",
    })


# Optional: serve the built SPA (frontend/dist) in production so one process hosts both.
_dist = REPO_ROOT / "frontend" / "dist"
if _dist.exists() and (_dist / "index.html").exists():
    app.mount("/", StaticFiles(directory=str(_dist), html=True), name="spa")
    logger.info("Mounted SPA from %s", _dist)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host=settings.host, port=settings.port, reload=settings.env == "dev")
