"""Derived read-model refresh (signals / weekly / accuracy) — offline tests.

Regression coverage for the 可操作信号/研报准确率/周统计 empty-page bug: the
derived tables were only written by the manual POST /refresh endpoints, so a
fresh deploy (or any restart) left all three pages empty until someone clicked
重算 on each page.
"""
from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import select

from app.ingestion import scheduler as sched
from app.models.market import DailyQuote
from app.models.research import AccuracySnapshot, ResearchReport, Signal, WeeklyStat
from app.services.derived import refresh_derived


def _add_report(session, code: str, org: str, rating: str, pub: date, title: str | None = None):
    session.add(ResearchReport(
        code=code, name=f"股{x}" if (x := code) else code, title=title or f"报告-{code}-{pub}",
        org=org, rating=rating, publish_date=pub,
    ))


def test_refresh_derived_populates_signals_and_weekly(session):
    """Given stored reports, refresh_derived writes Signal + WeeklyStat rows."""
    d = date(2026, 9, 10)
    _add_report(session, "600519", "中信证券", "买入", d)
    _add_report(session, "600519", "中信证券", "增持", d - timedelta(days=30))
    _add_report(session, "600519", "国泰君安", "买入", d)
    _add_report(session, "000001", "中信证券", "增持", d)
    _add_report(session, "000001", "华泰证券", "买入", d)
    _add_report(session, "000001", "招商证券", "买入", d)  # 3 orgs → consensus
    session.commit()

    stats = refresh_derived(session)
    session.commit()

    assert stats["signals"]["total"] > 0
    assert stats["weekly"]["rows"] > 0
    # accuracy has no quotes here → evaluates 0 events but must not fail
    assert "error" not in stats["accuracy"]["h20_org"]
    assert session.scalar(select(Signal).limit(1)) is not None
    assert session.scalar(select(WeeklyStat).limit(1)) is not None


def test_refresh_derived_accuracy_writes_snapshots(session):
    """With quotes + benchmark present, accuracy snapshots are stored."""
    code = "600519"
    d0 = date(2026, 6, 1)
    _add_report(session, code, "中信证券", "买入", d0)
    # 25 trading-ish days of quotes for the stock and the benchmark: stock rises,
    # benchmark flat → the 买入 call is a hit over h20.
    for i in range(25):
        d = d0 + timedelta(days=i)
        session.add(DailyQuote(security_id=1, code=code, trade_date=d, close=10.0 + i * 0.1,
                               open=10.0, high=10.0, low=9.9, volume=1, adjust="qfq"))
        session.add(DailyQuote(security_id=2, code="sh000300", trade_date=d, close=4000.0,
                               open=4000.0, high=4000.0, low=3999.0, volume=1, adjust="qfq"))
    session.commit()

    stats = refresh_derived(session)
    session.commit()

    org20 = stats["accuracy"]["h20_org"]
    assert "error" not in org20
    assert org20["total"] >= 1
    snaps = session.scalars(select(AccuracySnapshot)).all()
    assert snaps, "accuracy snapshots must be persisted"


def test_refresh_derived_with_empty_db_is_safe(session):
    """Empty database: every step no-ops without raising (fresh-deploy case)."""
    stats = refresh_derived(session)
    assert stats["signals"] == {"ref": None, "total": 0}
    assert stats["weekly"]["weeks"] == 0


def test_refresh_derived_is_hooked_into_scheduler(monkeypatch, session):
    """The scheduler rebuilds derived models after daily_evening / all runs."""
    calls: list[str] = []

    class _FakeScope:
        def __enter__(self):
            return session

        def __exit__(self, *exc):
            return False

    def fake_refresh(s):
        calls.append("derived")
        return {"signals": {"total": 1}, "weekly": {"rows": 1}, "accuracy": {}}

    import app.services.derived as derived_mod
    monkeypatch.setattr(derived_mod, "refresh_derived", fake_refresh)
    monkeypatch.setattr(sched, "session_scope", lambda: _FakeScope())

    # Non-source groups must NOT trigger the rebuild.
    sched._refresh_derived_after_ingest("daily_close")
    assert calls == []

    # Source groups do.
    sched._refresh_derived_after_ingest("daily_evening")
    assert calls == ["derived"]
    assert "daily_evening" in sched._DERIVED_AFTER_GROUPS
    assert "all" in sched._DERIVED_AFTER_GROUPS


def test_execute_prewarm_path_invokes_derived_refresh(monkeypatch, session):
    """_execute(scope='all', prewarm=True) calls the derived refresh hook."""
    ran = {"derived": 0, "prewarm": 0}

    class _FakeScope:
        def __enter__(self):
            return session

        def __exit__(self, *exc):
            return False

    import app.services.derived as derived_mod

    # NOTE: scheduler does `from app.ingestion.pipeline import run_all`, so the
    # name lives in sched's namespace — patch sched.run_all, not the pipeline module.
    monkeypatch.setattr(sched, "run_all", lambda s, universe=None, trade_date=None: [])
    monkeypatch.setattr(sched, "session_scope", lambda: _FakeScope())
    monkeypatch.setattr(sched, "_prewarm_after_ingest", lambda: ran.__setitem__("prewarm", ran["prewarm"] + 1))

    def fake_refresh(s):
        ran["derived"] += 1
        return {"signals": {"total": 0}, "weekly": {"rows": 0}, "accuracy": {}}

    monkeypatch.setattr(derived_mod, "refresh_derived", fake_refresh)
    sched._execute("all", prewarm=True)

    assert ran["derived"] == 1
    assert ran["prewarm"] == 1
