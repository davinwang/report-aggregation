"""APScheduler wiring for ingestion.

Multiple frequency-based cron jobs (all Asia/Shanghai), one per FEED_GROUPS entry:

- ``intraday_refresh``   盘中实时快照 — 交易时段每10分钟 (市场看板/全市场速览/板块热力/沪深港通涨跌家数)
- ``daily_close``        收盘后日频行情 — 工作日 16:30 (技术指标/基差/期权)
- ``daily_evening``      晚间日频数据 — 工作日 19:00 (两融/龙虎榜/评级/研报/公告)
- ``weekly_master``      周度主数据 — 周一 08:00 (证券主档/行业成分)
- ``weekly_financials``  周度财报 — 周六 12:00 (业绩/财务指标/三大报表)
- ``news_refresh``       资讯舆情·快讯 — 每日 07:00-23:00 每20分钟 (东财快讯/财联社; 分钟取 :02/:22/:42, 避开 intraday 的 */10 网格以免锁竞争饿死)

Crons are configurable via ``SCHEDULER_CRON_*`` settings (5-field cron; day-of-week
uses APScheduler names like ``mon-fri`` because APScheduler maps 0→Monday, unlike
classic cron where 0=Sunday).

On startup a one-off bootstrap job seeds an empty database (fresh deploy) or runs
the daily groups when market data is stale, so a new deployment is never blank.

Jobs run in worker threads behind a global ingest lock (overlapping triggers are
skipped with a warning instead of piling onto SQLite); SSE publishing is thread-safe.
"""
from __future__ import annotations

import threading
import time
from datetime import date, datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.core.config import parse_cron, settings
from app.core.db import session_scope
from app.core.logging import get_logger
from app.ingestion import throttle
from app.ingestion.adapters import FEED_GROUPS, REGISTRY
from app.ingestion.pipeline import run_all, run_bulk, run_feed, run_group, run_per_symbol

logger = get_logger(__name__)

_scheduler: Optional[BackgroundScheduler] = None

#: Market timezone for one-off job run dates. Always pass timezone-aware datetimes
#: to APScheduler: a naive ``datetime.now()`` is interpreted in the scheduler's
#: timezone, which silently misfires by the UTC offset inside containers (UTC).
_TZ = ZoneInfo("Asia/Shanghai")

# Serializes ingestion runs: one group at a time. On conflict the loser retries
# briefly in-place instead of dropping the run (prevents cron collisions — e.g.
# news_refresh vs intraday_refresh — from starving a job forever).
_INGEST_LOCK = threading.Lock()

_LOCK_RETRY_DELAYS: tuple[float, ...] = (20.0, 60.0, 90.0)


def _acquire_ingest_lock(scope: str) -> bool:
    """Try to take the global ingest lock; on conflict wait-and-retry a few times.

    Returns True once the lock is held (release happens in ``_execute``'s finally).
    Only gives up when another run keeps holding the lock for all retry windows —
    at that point the next cron tick is a better recovery than an unbounded wait.
    """
    for attempt, delay in enumerate((0.0,) + _LOCK_RETRY_DELAYS):
        if delay:
            logger.info("Ingestion '%s' waiting %.0fs: another run is in progress (retry %d/%d)",
                        scope, delay, attempt, len(_LOCK_RETRY_DELAYS))
            time.sleep(delay)
        if _INGEST_LOCK.acquire(blocking=False):
            return True
    logger.warning("Ingestion '%s' skipped: another run held the lock through all retries", scope)
    return False

INTRADAY_JOB_ID = "intraday_refresh"
DAILY_CLOSE_JOB_ID = "daily_close"
DAILY_EVENING_JOB_ID = "daily_evening"
WEEKLY_MASTER_JOB_ID = "weekly_master"
WEEKLY_FINANCIALS_JOB_ID = "weekly_financials"
NEWS_JOB_ID = "news_refresh"
BOOTSTRAP_JOB_ID = "bootstrap_ingest"

LEGACY_SCOPES = ("all", "bulk", "per_symbol")

#: (job_id, group, setting name, default cron, misfire grace seconds)
_JOB_SPECS: list[tuple[str, str, str, str, int]] = [
    (INTRADAY_JOB_ID, "intraday", "scheduler_cron_intraday", "*/10 9-11,13-15 * * mon-fri", 300),
    (DAILY_CLOSE_JOB_ID, "daily_close", "scheduler_cron_daily_close", "30 16 * * mon-fri", 6 * 3600),
    (DAILY_EVENING_JOB_ID, "daily_evening", "scheduler_cron_daily_evening", "0 19 * * mon-fri", 6 * 3600),
    (WEEKLY_MASTER_JOB_ID, "weekly_master", "scheduler_cron_weekly_master", "0 8 * * mon", 12 * 3600),
    (WEEKLY_FINANCIALS_JOB_ID, "weekly_financials", "scheduler_cron_weekly_financials", "0 12 * * sat", 48 * 3600),
    (NEWS_JOB_ID, "news_refresh", "scheduler_cron_news", "*/20 7-23 * * *", 600),
]

#: Schedulable scopes = frequency groups + legacy scopes + single feed names.
VALID_SCOPES: set[str] = set(FEED_GROUPS) | set(LEGACY_SCOPES) | set(REGISTRY)


def _execute(scope: str, universe: Optional[str] = None, prewarm: bool = True) -> None:
    """Run one ingestion scope in the caller's thread (used by all jobs).

    Valid scopes: a FEED_GROUPS key, 'all' | 'bulk' | 'per_symbol', or a single
    feed name. A global lock prevents overlapping runs from locking SQLite; a
    run that loses the race retries briefly instead of being silently dropped
    (two jobs with overlapping triggers must not starve one another).
    """
    throttle.configure(settings.akshare_throttle_seconds)
    if scope not in VALID_SCOPES:
        logger.error("Unknown ingestion scope '%s'; valid: %s", scope, ", ".join(sorted(VALID_SCOPES)))
        return
    if not _acquire_ingest_lock(scope):
        return
    try:
        _run_scope(scope, universe=universe, prewarm=prewarm)
    finally:
        _INGEST_LOCK.release()


def _run_scope(scope: str, universe: Optional[str] = None, prewarm: bool = True) -> None:
    """Execute one ingestion scope; caller must hold ``_INGEST_LOCK``."""
    started = datetime.now()
    logger.info("Ingestion started (scope=%s, universe=%s)", scope, universe or settings.universe)
    try:
        with session_scope() as session:
            if scope in FEED_GROUPS:
                run_group(session, scope, universe=universe)
            elif scope == "bulk":
                run_bulk(session)
            elif scope == "per_symbol":
                run_per_symbol(session, universe=universe)
            elif scope == "all":
                run_all(session, universe=universe)
            else:  # single feed
                run_feed(scope, session, universe=universe)
        logger.info("Ingestion finished (scope=%s) in %.1fs", scope, (datetime.now() - started).total_seconds())
        if prewarm:
            _refresh_derived_after_ingest(scope)
            _prewarm_after_ingest()
    except Exception:  # noqa: BLE001
        logger.exception("Ingestion crashed (scope=%s)", scope)


#: Groups whose feeds land the source rows the derived read models are built
#: from (ratings/reports → signal/accuracy/weekly). After these groups finish,
#: rebuild the derived tables so 可操作信号/研报准确率/周统计 stay populated
#: without anyone clicking 重算. The startup bootstrap runs daily_evening, so a
#: fresh full seed derives them too.
_DERIVED_AFTER_GROUPS = frozenset({"daily_evening", "all"})


def _refresh_derived_after_ingest(group: str) -> None:
    """Rebuild signal/weekly/accuracy read models (best-effort, own session)."""
    if group not in _DERIVED_AFTER_GROUPS:
        return
    from app.core.db import session_scope as _scope  # lazy: import-graph hygiene
    from app.services.derived import refresh_derived

    try:
        with _scope() as session:
            stats = refresh_derived(session)
        logger.info(
            "Derived read models refreshed after '%s': %s", group,
            {k: ("ERROR" if "error" in v else v.get("total", "ok")) for k, v in stats.items() if k != "accuracy"},
        )
    except Exception:  # noqa: BLE001 - ingestion itself already committed; never propagate
        logger.exception("Derived read-model refresh after '%s' failed", group)


def _prewarm_after_ingest() -> None:
    """Rebuild the hot read caches so the first page visit after a run is fast."""
    from app.services.prewarm import prewarm_hot_caches  # lazy: keep import graph lean

    prewarm_hot_caches()


def _add_group_job(sched: BackgroundScheduler, job_id: str, group: str,
                   setting: str, default_cron: str, grace: int) -> None:
    cron = getattr(settings, setting, default_cron) or default_cron
    try:
        parts = parse_cron(cron)
    except ValueError as exc:
        logger.warning("Invalid %s=%s (%s); falling back to %s", setting, cron, exc, default_cron)
        parts = parse_cron(default_cron)
        cron = default_cron
    sched.add_job(
        _execute,
        trigger=CronTrigger(**parts, timezone="Asia/Shanghai"),
        id=job_id,
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        misfire_grace_time=grace,
        kwargs={"scope": group},
    )
    logger.info("Scheduled job %-20s group=%-18s cron=%s", job_id, group, cron)


def start_scheduler() -> Optional[BackgroundScheduler]:
    """Start the background scheduler and register all frequency jobs. Idempotent."""
    global _scheduler
    if not settings.scheduler_enabled:
        logger.info("Scheduler disabled via config (SCHEDULER_ENABLED=false)")
        return None
    if _scheduler is not None:
        return _scheduler
    _scheduler = BackgroundScheduler(daemon=True, timezone="Asia/Shanghai")
    for job_id, group, setting, default_cron, grace in _JOB_SPECS:
        _add_group_job(_scheduler, job_id, group, setting, default_cron, grace)
    _scheduler.start()
    logger.info("Scheduler started with %d frequency jobs", len(_JOB_SPECS))
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
    """Enqueue an immediate one-off ingestion run (non-blocking).

    Returns True if scheduled. Accepts any VALID_SCOPES entry (frequency group,
    legacy scope, or single feed name).
    """
    if scope not in VALID_SCOPES:
        logger.error("trigger_now: unknown scope '%s'", scope)
        return False
    if _scheduler is None:
        # No scheduler (disabled or not started): run in a daemon thread instead.
        threading.Thread(target=_execute, kwargs={"scope": scope, "universe": universe},
                         daemon=True).start()
        return True
    _scheduler.add_job(_execute, trigger="date", run_date=datetime.now(_TZ),
                       id=f"oneoff_{scope}_{datetime.now(_TZ).strftime('%H%M%S')}",
                       kwargs={"scope": scope, "universe": universe},
                       max_instances=3, coalesce=True)
    return True


def jobs_info() -> list[dict]:
    """Scheduled jobs for /ops and /health observability (id, cron, next run)."""
    if _scheduler is None:
        return []
    out: list[dict] = []
    for job in _scheduler.get_jobs():
        nrt = getattr(job, "next_run_time", None)
        out.append({
            "id": job.id,
            "trigger": str(job.trigger),
            "next_run": nrt.isoformat() if nrt else None,
        })
    return sorted(out, key=lambda j: str(j["id"]))


# ---- Startup bootstrap (fixes empty-data-after-fresh-deploy) ----

#: Group order for the empty-database seed: master data first (security_id_map),
#: then realtime/EOD/financial groups; every registered feed runs exactly once.
_BOOTSTRAP_GROUPS = ("weekly_master", "intraday", "daily_close", "daily_evening",
                     "weekly_financials", "news_refresh")


def bootstrap_on_startup() -> None:
    """Schedule a one-off catch-up run shortly after boot.

    Empty database → full seed of every feed group. Data present but older than
    ``ingest_bootstrap_stale_days`` → daily groups only. Else: no-op.
    """
    if not settings.ingest_bootstrap:
        logger.info("Bootstrap ingestion disabled (INGEST_BOOTSTRAP=false)")
        return
    if _scheduler is not None and _scheduler.running:
        run_at = datetime.now(_TZ) + timedelta(seconds=5)
        _scheduler.add_job(_bootstrap_job, trigger="date", run_date=run_at,
                           id=BOOTSTRAP_JOB_ID, replace_existing=True, max_instances=1,
                           misfire_grace_time=300)
        logger.info("Bootstrap ingestion scheduled at %s", run_at.strftime("%H:%M:%S"))
    else:
        threading.Thread(target=_bootstrap_job, name="bootstrap-ingest", daemon=True).start()


def _bootstrap_job() -> None:
    from sqlalchemy import func, select

    from app.core.db import init_db
    from app.models.market import DailyQuote
    from app.models.news import NewsItem
    from app.services.aggregation import latest_trade_date

    try:
        init_db()  # idempotent: guarantees the schema exists even standalone
        with session_scope() as session:
            n_quotes = session.scalar(select(func.count()).select_from(DailyQuote)) or 0
            n_news = session.scalar(select(func.count()).select_from(NewsItem)) or 0
            ltd = latest_trade_date(session)
    except Exception:  # noqa: BLE001
        logger.exception("Bootstrap: failed to inspect database state")
        return

    if n_quotes == 0:
        logger.info("Bootstrap: empty database detected → full seed (%s)", " → ".join(_BOOTSTRAP_GROUPS))
        for group in _BOOTSTRAP_GROUPS:
            _execute(group, prewarm=False)
        logger.info("Bootstrap: full seed finished")
    else:
        stale_before = date.today() - timedelta(days=settings.ingest_bootstrap_stale_days)
        if ltd is None or ltd < stale_before:
            logger.info("Bootstrap: market data stale (latest trade date %s) → daily catch-up", ltd)
            _execute("daily_close", prewarm=False)
            _execute("daily_evening", prewarm=False)
        else:
            logger.info("Bootstrap: data current (latest trade date %s); scheduled jobs will maintain it", ltd)
        if n_news == 0:
            # News lives outside the market-data staleness check: a fresh deploy
            # over a current DB (e.g. redeploy between cron ticks) leaves the
            # news table empty until the next news_refresh tick — seed it now.
            logger.info("Bootstrap: news table empty → seeding news_refresh")
            _execute("news_refresh", prewarm=False)
    _prewarm_after_ingest()


def is_running() -> bool:
    return _scheduler is not None and _scheduler.running
