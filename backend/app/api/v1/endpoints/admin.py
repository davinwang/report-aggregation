"""管理设置 (admin) — configuration overview + scheduler status.

Login is disabled by design (the app runs as a hardcoded admin), so these
endpoints are open; they are read-only except for the ingest trigger, which
mirrors /api/ops/ingest but allows choosing a universe.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Query

from app.api.common import envelope
from app.core.config import settings
from app.ingestion import scheduler

router = APIRouter(prefix="/api/admin", tags=["admin"])

UNIVERSES = ["hs300", "zz500", "zz1000", "sz50"]


@router.get("/config")
def config() -> dict:
    """Effective runtime configuration (no secrets) + scheduler state."""
    sched = getattr(scheduler, "_scheduler", None)
    next_run: Optional[str] = None
    if sched is not None:
        job = sched.get_job(scheduler.NIGHTLY_JOB_ID)
        if job is not None and getattr(job, "next_run_time", None) is not None:
            next_run = job.next_run_time.isoformat()
    return envelope({
        "app": settings.app_name,
        "env": settings.env,
        "universe": settings.universe,
        "universes": UNIVERSES,
        "auth_enabled": settings.auth_enabled,
        "feature_ai": settings.feature_ai,
        "akshare": {
            "timeout": settings.akshare_timeout,
            "max_retries": settings.akshare_max_retries,
            "throttle_seconds": settings.akshare_throttle_seconds,
        },
        "scheduler": {
            "enabled": settings.scheduler_enabled,
            "running": scheduler.is_running(),
            "cron": settings.scheduler_cron,
            "timezone": "Asia/Shanghai",
            "next_run_at": next_run,
        },
        "database": {"kind": "sqlite" if settings.is_sqlite else "other", "url": settings.resolved_database_url()},
    })


@router.post("/ingest")
def trigger_ingest(
    scope: str = Query(default="all", description="all|bulk|per_symbol"),
    universe: Optional[str] = Query(default=None),
) -> dict:
    """Kick off an ingestion run (non-blocking)."""
    ok = scheduler.trigger_now(scope=scope, universe=universe)
    return envelope({"scheduled": ok, "scope": scope, "universe": universe or settings.universe})
