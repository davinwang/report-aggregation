"""MCP tool tests — plain functions over the in-memory DB (no transport, no network).

The MCP transport (mount + session-manager handshake + tools/call round-trip) is
exercised by the deploy smoke checklist; here we lock the tool behaviors and
response shapes, plus the static-token middleware branches.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.mcp import tools
from app.mcp.auth import TokenAuthMiddleware
from app.models.financial import FinancialIndicator, FinancialStatement
from app.models.market import DailyQuote
from app.models.research import ResearchReport, Signal
from app.models.security import Security


def test_search_reports_filters(session):
    session.add(ResearchReport(code="600519", name="贵州茅台", title="深度报告：价值重估",
                               org="华创证券", rating="买入", publish_date=date(2026, 9, 1)))
    session.add(ResearchReport(code="000001", name="平安银行", title="银行行业月度跟踪",
                               org="中信证券", rating="增持", publish_date=date(2026, 9, 2)))
    session.flush()

    out = tools.search_reports(session, keyword="价值")
    assert out["total"] == 1
    assert out["rows"][0]["code"] == "600519"
    assert tools.search_reports(session, code="000001")["total"] == 1
    assert tools.search_reports(session, org="中信证券")["total"] == 1


def test_stock_snapshot_aggregates_and_unknown_raises(session):
    sec = Security(code="600519", name="贵州茅台", type="stock", exchange="SSE")
    session.add(sec)
    session.flush()
    session.add(DailyQuote(security_id=sec.id, code="600519", trade_date=date(2026, 9, 10),
                           close=1500.0, change_pct=1.2, adjust="qfq"))
    session.flush()

    out = tools.stock_snapshot(session, "600519")
    assert out["security"]["code"] == "600519"
    assert out["quote"]["close"] == 1500.0
    assert out["reports"] == []

    with pytest.raises(ValueError):
        tools.stock_snapshot(session, "999999")


def test_list_signals_window_and_kind(session):
    session.add(Signal(code="600519", name="贵州茅台", trade_date=date(2026, 9, 10), kind="upgrade",
                       direction="买入", strength="强", score=2.0, reason="机构上调评级",
                       industry_group="消费"))
    session.add(Signal(code="000001", name="平安银行", trade_date=date(2026, 9, 10), kind="consensus",
                       direction="买入", strength="中", score=3.0, reason="机构一致", industry_group="金融"))
    session.flush()

    out = tools.list_signals(session, kind="upgrade", days=30)
    assert out["total"] == 1
    assert out["ref"] == "2026-09-10"
    assert out["rows"][0]["kind"] == "upgrade"
    assert tools.list_signals(session, days=30)["total"] == 2


def test_market_matrix_from_index_bars(session, monkeypatch):
    from app.services import matrix as matrix_svc

    # Hermetic: the change-counter cache reads the real DB file stamp even for
    # an in-memory test session, so stub the cache to avoid host-cache hits and
    # keep test junk out of data/cache.pkl.
    monkeypatch.setattr(matrix_svc, "cache_get", lambda key: None)
    monkeypatch.setattr(matrix_svc, "cache_set", lambda key, value: None)

    idx = Security(code="sh000300", name="沪深300", type="index")
    session.add(idx)
    session.flush()
    d0 = date(2026, 7, 1)
    for i in range(30):
        session.add(DailyQuote(security_id=idx.id, code="sh000300", trade_date=d0 + timedelta(days=i),
                               close=4000.0 + i, adjust=""))
    session.flush()

    out = tools.market_matrix(session, scope="index+active", limit=60)
    assert out["count"] == 1
    row = out["rows"][0]
    assert row["code"] == "sh000300"
    assert row["trend"] in ("多", "空") and row["macd"] in ("金叉", "死叉")
    assert set(row) >= {"close", "ma20", "rsi12"}


def test_flow_overview_empty_is_safe(session):
    lhb = tools.flow_overview(session, kind="lhb")
    assert lhb["rows"] == [] and lhb["trade_date"] is None
    nb = tools.flow_overview(session, kind="northbound", days=30)
    assert nb["dates"] == [] and nb["boards"] == []
    # Unknown kind falls back to northbound instead of erroring.
    assert tools.flow_overview(session, kind="nope")["latest"] == []


def test_financial_summary_and_accuracy_empty(session):
    session.add(FinancialStatement(code="600519", statement="income", source="em",
                                   report_period="20260630", data_json={"revenue": 100.0}))
    session.add(FinancialIndicator(code="600519", report_period="20260630", eps=3.2, roe=12.5))
    session.flush()

    out = tools.financial_summary(session, "600519")
    assert out["statements"][0]["data"]["revenue"] == 100.0
    assert out["indicators"][0]["eps"] == 3.2

    assert tools.accuracy_leaderboard(session)["rows"] == []


# ------------------------- static-token middleware -------------------------

async def _call_mw(app, headers):
    scope = {"type": "http", "method": "POST", "path": "/", "headers": headers}
    seen = {}

    async def receive():
        return {"type": "http.request", "body": b""}

    async def send(msg):
        if msg["type"] == "http.response.start":
            seen["status"] = msg["status"]

    await app(scope, receive, send)
    return seen["status"]


async def test_token_middleware_branches(monkeypatch):
    from app.core.config import settings

    async def ok_app(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    mw = TokenAuthMiddleware(ok_app)

    monkeypatch.setattr(settings, "mcp_token", "")
    assert await _call_mw(mw, []) == 200  # no token configured -> pass through

    monkeypatch.setattr(settings, "mcp_token", "secret")
    assert await _call_mw(mw, []) == 401
    assert await _call_mw(mw, [(b"authorization", b"Bearer wrong")]) == 401
    assert await _call_mw(mw, [(b"authorization", b"Bearer secret")]) == 200
