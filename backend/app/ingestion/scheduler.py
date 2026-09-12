"""APScheduler wiring for ingestion.

A BackgroundScheduler runs the nightly pipeline on a cron trigger (default 15:30 on
weekdays, after the A-share close) and supports on-demand one-off runs triggered from
the API ("扫描/刷新"). Jobs run in worker threads; SSE publishing is thread-safe.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.core.config import settings
from app.core.db import session_scope
from app.core.logging import get_logger
from app.ingestion import throttle
from app.ingestion.pipeline import run_all, run_bulk, run_per_symbol

logger = get_logger(__name__)

_scheduler: Optional[BackgroundScheduler] = None

NIGHTLY_JOB_ID = "nightly_ingest"


def _job(scope: str = "all", universe: Optional[str] = None) -> None:
    throttle.configure(settings.akshare_throttle_seconds)
    logger.info("Scheduled ingestion started (scope=%s, universe=%s)", scope, universe or settings.universe)
    try:
        with session_scope() as session:
            if scope == "bulk":
                run_bulk(session)
            elif scope == "per_symbol":
                run_per_symbol(session, universe=universe)
            else:
                run_all(session, universe=universe)
        logger.info("Scheduled ingestion finished (scope=%s)", scope)
    except Exception:  # noqa: BLE001
        logger.exception("Scheduled ingestion crashed (scope=%s)", scope)


def start_scheduler() -> Optional[BackgroundScheduler]:
    """Start the background scheduler if enabled. Idempotent."""
    global _scheduler
    if not settings.scheduler_enabled:
        logger.info("Scheduler disabled via config (SCHEDULER_ENABLED=false)")
        return None
    if _scheduler is not None:
        return _scheduler
    _scheduler = BackgroundScheduler(daemon=True, timezone="Asia/Shanghai")
    trigger = CronTrigger(**settings.scheduler_cron_parts, timezone="Asia/Shanghai")
    _scheduler.add_job(_job, trigger=trigger, id=NIGHTLY_JOB_ID, replace_existing=True,
                       max_instances=1, coalesce=True, kwargs={"scope": "all"})
    _scheduler.start()
    logger.info("Scheduler started; nightly cron = %s", settings.scheduler_cron)
    return _scheduler


def shutdown_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        try:
            _scheduler.shutdown(wait=False)
        except Exception:  # noqa: BLE001
            pass
        _scheduler = None
        logger.info("Scheduler shut down")


def trigger_now(scope: str = "all", universe: Optional[str] = None) -> bool:
    """Enqueue an immediate one-off ingestion run (non-blocking). Returns True if scheduled."""
    if _scheduler is None:
        # No scheduler (disabled or not started): run in a daemon thread instead.
        import threading

        threading.Thread(target=_job, kwargs={"scope": scope, "universe": universe}, daemon=True).start()
        return True
    run_at = datetime.now()
    _scheduler.add_job(_job, trigger="date", run_date=run_at,
                       kwargs={"scope": scope, "universe": universe},
                       max_instances=3, coalesce=True)
    return True


def is_running() -> bool:
    return _scheduler is not None and _scheduler.running
