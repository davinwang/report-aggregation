"""Scheduler / feed-group tests — fully offline (no network, no scheduler start)."""
from __future__ import annotations

import pytest

from app.core.config import parse_cron
from app.ingestion import scheduler as sched
from app.ingestion.adapters import FEED_GROUP_OF, FEED_GROUPS, REGISTRY
from app.ingestion.pipeline import run_group


def test_feed_groups_cover_every_registered_feed_exactly_once():
    """Every registered feed belongs to exactly one frequency group (bootstrap seed
    must run each feed once)."""
    grouped = [f for feeds in FEED_GROUPS.values() for f in feeds]
    assert sorted(grouped) == sorted(REGISTRY.keys())
    assert len(grouped) == len(set(grouped))
    # reverse map is consistent
    for group, feeds in FEED_GROUPS.items():
        for feed in feeds:
            assert group in FEED_GROUP_OF[feed]


def test_group_ordering_dependencies():
    """Intra-group dependency order: security_master first (security_id_map),
    index_daily before index_futures (basis spot leg)."""
    assert FEED_GROUPS["weekly_master"][0] == "security_master"
    assert FEED_GROUPS["daily_close"].index("index_daily") < FEED_GROUPS["daily_close"].index("index_futures")
    # per-symbol feeds keep universe resolution (they resolve codes via run_feed)
    for name in ("price_history", "research_reports", "financials_em", "fin_indicators"):
        assert REGISTRY[name].per_symbol


def test_parse_cron_valid_and_invalid():
    parts = parse_cron("*/10 9-11,13-15 * * mon-fri")
    assert parts == {
        "minute": "*/10", "hour": "9-11,13-15", "day": "*", "month": "*", "day_of_week": "mon-fri",
    }
    with pytest.raises(ValueError):
        parse_cron("30 16 * *")
    with pytest.raises(ValueError):
        parse_cron("30 16 * * mon-fri extra")


def test_scheduler_valid_scopes():
    """Scopes accepted by trigger_now/ops: groups + legacy + every feed name."""
    assert set(FEED_GROUPS) <= sched.VALID_SCOPES
    assert {"all", "bulk", "per_symbol"} <= sched.VALID_SCOPES
    assert set(REGISTRY) <= sched.VALID_SCOPES


def test_execute_unknown_scope_is_logged_not_raised():
    sched._execute("no_such_scope")  # must not raise


def test_run_group_unknown_raises(session):
    with pytest.raises(ValueError):
        run_group(session, "nope")


def test_job_specs_crons_parse():
    """All default cron expressions are valid 5-field APScheduler strings."""
    for _job_id, _group, _setting, default_cron, _grace in sched._JOB_SPECS:
        parse_cron(default_cron)


def test_trigger_now_rejects_unknown_scope():
    assert sched.trigger_now("no_such_scope") is False


def test_bootstrap_oneoff_is_scheduled_ahead_of_now(monkeypatch):
    """Regression: the one-off bootstrap must be scheduled ~5s AHEAD of the
    scheduler's timezone now. A naive datetime.now() is interpreted in the
    scheduler tz, which in a UTC container put run_date 8h in the past and
    silently discarded the job (empty first-deploy seed never ran)."""
    from datetime import datetime, timezone

    from app.core.config import settings

    monkeypatch.setattr(sched, "_scheduler", None)
    monkeypatch.setattr(settings, "scheduler_enabled", True)
    sched.start_scheduler()
    try:
        sched.bootstrap_on_startup()
        job = sched._scheduler.get_job(sched.BOOTSTRAP_JOB_ID)
        assert job is not None
        nrt = job.next_run_time
        assert nrt is not None and nrt.tzinfo is not None
        ahead = nrt.timestamp() - datetime.now(timezone.utc).timestamp()
        assert 0 <= ahead <= 15, f"bootstrap run_date not ~now: {ahead}s"
    finally:
        sched.shutdown_scheduler()


def test_start_scheduler_registers_all_jobs(monkeypatch):
    """With the scheduler enabled, start_scheduler registers one cron job per group."""
    from app.core.config import settings

    monkeypatch.setattr(sched, "_scheduler", None)
    monkeypatch.setattr(settings, "scheduler_enabled", True)
    sched.start_scheduler()
    try:
        assert sched.is_running()
        jobs = {j["id"] for j in sched.jobs_info()}
        assert jobs == {
            sched.INTRADAY_JOB_ID, sched.DAILY_CLOSE_JOB_ID, sched.DAILY_EVENING_JOB_ID,
            sched.WEEKLY_MASTER_JOB_ID, sched.WEEKLY_FINANCIALS_JOB_ID,
        }
        info = {j["id"]: j for j in sched.jobs_info()}
        assert all(j["next_run"] for j in info.values())
    finally:
        sched.shutdown_scheduler()
    assert sched.jobs_info() == []
