"""Tests for app/services/insights.py — sentiment / replay / lhb_research."""
from __future__ import annotations

from datetime import date, timedelta

from app.models.flow import LhbRecord
from app.models.market import DailyQuote
from app.models.research import ResearchReport, Signal
from app.services import insights as svc

REF = date(2026, 10, 23)


def _seed_quotes(session, ref: date = REF):
    """Benchmark + 3 stocks with 90d of qfq closes. Dates walk backwards from REF,
    so the drift coefficients are negated to make stock A trend UP (+10%) and B
    trend DOWN (−10%) toward the present."""
    d = 0
    day = ref
    while d < 90:
        if day.weekday() < 5:  # weekdays only; gaps fine for bisect logic
            session.add(DailyQuote(
                security_id=1, code="sh000300", trade_date=day, close=3000.0 + d, adjust="none"))
            session.add(DailyQuote(
                security_id=2, code="000001", trade_date=day,
                close=10.0 * (1 - 0.0016 * d), adjust="qfq"))
            session.add(DailyQuote(
                security_id=3, code="000002", trade_date=day,
                close=10.0 * (1 + 0.0016 * d), adjust="qfq"))
            session.add(DailyQuote(
                security_id=4, code="000003", trade_date=day, close=10.0, adjust="qfq"))
            d += 1
        day -= timedelta(days=1)


def _seed_reports(session, codes_orgs: list[tuple[str, str, str, date]]):
    for i, (code, org, rating, pub) in enumerate(codes_orgs):
        session.add(ResearchReport(
            code=code, name=f"股票{code}", title=f"t{i}", org=org, rating=rating,
            publish_date=pub, source="em",
        ))


# ------------------------------- sentiment -------------------------------
def test_sentiment_dispersion_and_labels(session):
    _seed_reports(session, [
        # 分歧股: 两个机构一个买入一个卖出
        ("000003", "甲证券", "买入", REF - timedelta(days=2)),
        ("000003", "乙证券", "卖出", REF - timedelta(days=1)),
        # 一致看多股
        ("000001", "甲证券", "买入", REF - timedelta(days=2)),
        ("000001", "乙证券", "增持", REF - timedelta(days=1)),
        ("000001", "丙证券", "买入", REF - timedelta(days=1)),
        # 单机构 — 无分歧信息, 应被排除
        ("000002", "甲证券", "卖出", REF - timedelta(days=1)),
    ])
    out = svc.sentiment(session, days=30, min_reports=2)
    by_code = {r["code"]: r for r in out["rows"]}
    assert set(by_code) == {"000001", "000003"}
    assert by_code["000003"]["label"] == "重大分歧"
    assert by_code["000003"]["dispersion"] >= 1.0
    assert by_code["000001"]["label"] in ("一致看多", "偏多")
    assert by_code["000001"]["orgs"] == 3
    assert out["market"]["stocks"] == 2
    assert out["market"]["high_dispersion"] == 1


def test_sentiment_empty_db(session):
    out = svc.sentiment(session)
    assert out["rows"] == [] and out["ref"] is None


# -------------------------------- replay --------------------------------
def _seed_signals(session, ref: date = REF):
    horizon_end = ref - timedelta(days=32)  # entry old enough for h20 window to close
    session.add(Signal(code="000001", name="A", trade_date=horizon_end, kind="upgrade",
                       direction="买入", strength="强", reason="上调"))
    session.add(Signal(code="000002", name="B", trade_date=horizon_end, kind="downgrade",
                       direction="卖出", strength="强", reason="下调"))
    # too recent — window not closed, must be skipped
    session.add(Signal(code="000003", name="C", trade_date=ref - timedelta(days=2), kind="upgrade",
                       direction="买入", strength="强", reason="新信号"))


def test_replay_hit_miss(session):
    _seed_quotes(session)
    _seed_signals(session)
    out = svc.replay(session, horizon=20, days=90)
    assert out["summary"]["evaluated"] == 2  # recent signal excluded
    assert out["summary"]["hits"] == 2        # A beat bench, B lost to bench
    assert out["summary"]["win_rate"] == 1.0
    by_code = {r["code"]: r for r in out["rows"]}
    assert by_code["000001"]["excess"] > 0
    assert by_code["000002"]["hit"] is True
    assert not any(r["code"] == "000003" for r in out["rows"])


def test_replay_kind_filter(session):
    _seed_quotes(session)
    _seed_signals(session)
    out = svc.replay(session, horizon=20, days=90, kind="upgrade")
    assert all(r["kind"] == "upgrade" for r in out["rows"])
    assert out["summary"]["evaluated"] == 1


# ----------------------------- lhb_research -----------------------------
def _seed_lhb(session, ref: date = REF):
    session.add(LhbRecord(code="000001", name="A", trade_date=ref - timedelta(days=1),
                          reason="日涨幅偏离值达到7%", close=11.0, change_pct=7.1,
                          buy_amt=1e8, sell_amt=2e7, net_amt=8e7, turnover=5.0))
    session.add(LhbRecord(code="000009", name="X", trade_date=ref - timedelta(days=1),
                          reason="日跌幅偏离值达到7%", close=9.0, change_pct=-7.2,
                          buy_amt=1e7, sell_amt=3e7, net_amt=-2e7, turnover=3.0))


def test_lhb_research_dual_signal_first(session):
    _seed_lhb(session)
    _seed_reports(session, [
        ("000001", "甲证券", "买入", REF - timedelta(days=3)),
        ("000001", "乙证券", "增持", REF - timedelta(days=2)),
    ])
    out = svc.lhb_research(session, lhb_days=10, window_days=30)
    assert out["summary"]["lhb_stocks"] == 2
    assert out["summary"]["dual_signal"] == 1
    assert out["rows"][0]["code"] == "000001"          # dual-signal ranked first
    assert out["rows"][0]["coverage"]["orgs"] == 2
    assert out["rows"][1]["coverage"] is None


def test_lhb_research_direction_filter(session):
    _seed_lhb(session)
    out = svc.lhb_research(session, lhb_days=10, direction="sell")
    assert [r["code"] for r in out["rows"]] == ["000009"]
