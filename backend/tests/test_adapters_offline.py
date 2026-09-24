"""Offline adapter tests — run adapters against a fake akshare and assert DB writes.

No network. Throttle is disabled to keep tests fast.
"""
from __future__ import annotations

import pandas as pd
from sqlalchemy import select

from app.ingestion import throttle
from app.ingestion.adapters.northbound import NorthboundAdapter
from app.ingestion.adapters.ratings_daily import RatingsDailyAdapter
from app.ingestion.adapters.research_reports import ResearchReportsAdapter
from app.ingestion.adapters.security_master import SecurityMasterAdapter
from app.ingestion.adapters.stock_flow import StockFlowAdapter
from app.models.flow import FundFlowDaily, NorthboundDaily
from app.models.research import RatingEvent, ResearchReport
from app.models.security import Security

throttle.configure(0.0)  # no artificial delay in tests


def test_security_master_persists(session, fake_ak):
    fake_ak.stock_info_a_code_name = lambda: pd.DataFrame([
        {"code": "600519", "name": "贵州茅台"},
        {"code": "000001", "name": "平安银行"},
    ])
    res = SecurityMasterAdapter().run(session)
    assert res.status == "ok", res.error
    assert res.rows_upserted == 2
    rows = session.scalars(select(Security)).all()
    assert {r.code for r in rows} == {"600519", "000001"}
    moutai = next(r for r in rows if r.code == "600519")
    assert moutai.exchange == "SSE" and moutai.name == "贵州茅台"


def test_security_master_idempotent(session, fake_ak):
    fake_ak.stock_info_a_code_name = lambda: pd.DataFrame([{"code": "600519", "name": "贵州茅台"}])
    a = SecurityMasterAdapter()
    a.run(session)
    a.run(session)  # second run should not duplicate
    assert len(session.scalars(select(Security)).all()) == 1


def test_ratings_daily_persists(session, fake_ak):
    fake_ak.stock_rank_forecast_cninfo = lambda date=None: pd.DataFrame([
        {"证券代码": "600519", "证券简称": "贵州茅台", "发布日期": "2026-09-10",
         "研究机构简称": "国泰君安", "研究员名称": "张三", "投资评级": "买入",
         "是否首次评级": "否", "评级变化": "维持", "前一次投资评级": "买入",
         "目标价格-下限": 1800.0, "目标价格-上限": 2000.0},
        {"证券代码": "000001", "证券简称": "平安银行", "发布日期": "2026-09-10",
         "研究机构简称": "中信证券", "研究员名称": "李四", "投资评级": "增持",
         "是否首次评级": "是", "评级变化": "首次", "前一次投资评级": "--",
         "目标价格-下限": "--", "目标价格-上限": "--"},
    ])
    res = RatingsDailyAdapter().run(session)
    assert res.status == "ok", res.error
    events = session.scalars(select(RatingEvent)).all()
    assert len(events) == 2
    moutai = next(e for e in events if e.code == "600519")
    assert moutai.rating_norm == "买入" and moutai.target_low == 1800.0
    pab = next(e for e in events if e.code == "000001")
    assert pab.is_first is True and pab.target_low is None  # '--' normalized to None


def test_research_reports_per_symbol(session, fake_ak):
    fake_ak.stock_research_report_em = lambda symbol=None: pd.DataFrame([
        {"股票代码": symbol, "股票简称": "样例", "报告名称": "深度报告：价值重估",
         "东财评级": "买入", "机构": "国泰君安", "近一月个股研报数": 12,
         "2025-盈利预测-收益": 3.2, "2025-盈利预测-市盈率": 25.0,
         "行业": "白酒", "日期": "2026-09-01", "报告PDF链接": "https://pdf.dfcfw.com/x.pdf"},
    ])
    res = ResearchReportsAdapter().run(session, codes=["600519"])
    assert res.status == "ok", res.error
    reports = session.scalars(select(ResearchReport)).all()
    assert len(reports) == 1
    r = reports[0]
    assert r.title.startswith("深度报告") and r.org == "国泰君安"
    assert r.pdf_url.endswith("x.pdf")
    assert r.forecast_json["2025"]["eps"] == 3.2


def test_northbound_skips_preopen_placeholder_rows(session, fake_ak):
    """EM rolls the summary report to the next session's placeholder row (every
    stock 持平, 上涨/下跌 = 0) once the evening clearing finishes; such rows must be
    dropped so they never shadow the real session's breadth."""
    fake_ak.stock_hsgt_fund_flow_summary_em = lambda: pd.DataFrame([
        {"交易日": "2026-09-16", "类型": "沪港通", "板块": "沪股通", "资金方向": "北向",
         "交易状态": 3, "成交净买额": 0.0, "资金净流入": 0.0, "当日资金余额": 0.0,
         "上涨数": 0, "持平数": 1643, "下跌数": 0, "相关指数": "上证指数", "指数涨跌幅": -0.08},
        {"交易日": "2026-09-15", "类型": "沪港通", "板块": "沪股通", "资金方向": "北向",
         "交易状态": 3, "成交净买额": 0.0, "资金净流入": 0.0, "当日资金余额": 0.0,
         "上涨数": 421, "持平数": 26, "下跌数": 1196, "相关指数": "上证指数", "指数涨跌幅": -0.54},
        {"交易日": "2026-09-15", "类型": "深港通", "板块": "深股通", "资金方向": "北向",
         "交易状态": 3, "成交净买额": 0.0, "资金净流入": 0.0, "当日资金余额": 0.0,
         "上涨数": 413, "持平数": 19, "下跌数": 1447, "相关指数": "深证成指", "指数涨跌幅": -0.72},
    ])
    res = NorthboundAdapter().run(session)
    assert res.status == "ok", res.error
    assert res.rows_seen == 2  # the placeholder row was dropped before persist
    rows = session.scalars(select(NorthboundDaily).order_by(NorthboundDaily.board)).all()
    assert {r.trade_date.isoformat() for r in rows} == {"2026-09-15"}
    assert {r.board for r in rows} == {"沪股通", "深股通"}
    sh = next(r for r in rows if r.board == "沪股通")
    assert sh.extra_json["up"] == 421 and sh.extra_json["down"] == 1196
    assert sh.extra_json["index_pct"] == -0.54


def test_northbound_all_placeholder_run_is_empty_not_junk(session, fake_ak):
    """A pre-open/evening run that sees only placeholder rows stores nothing (the
    day's frozen counts stay intact) and reports status='empty'."""
    fake_ak.stock_hsgt_fund_flow_summary_em = lambda: pd.DataFrame([
        {"交易日": "2026-09-16", "类型": "沪港通", "板块": "沪股通", "资金方向": "北向",
         "交易状态": 3, "成交净买额": 0.0, "资金净流入": 0.0, "当日资金余额": 0.0,
         "上涨数": 0, "持平数": 1643, "下跌数": 0, "相关指数": "上证指数", "指数涨跌幅": -0.08},
    ])
    res = NorthboundAdapter().run(session)
    assert res.status == "empty"
    assert res.rows_upserted == 0
    assert session.scalars(select(NorthboundDaily)).all() == []


def test_stock_flow_per_symbol(session, fake_ak):
    """个股资金流写入 FundFlowDaily，供 GET /api/stock/{code}/flow 读取。"""
    fake_ak.stock_individual_fund_flow = lambda stock=None, market=None: pd.DataFrame([
        {"日期": "2026-09-15", "收盘价": 1700.0, "涨跌幅": 1.23,
         "主力净流入-净额": 1.5e8, "主力净流入-净占比": 8.1,
         "超大单净流入-净额": 9e7, "大单净流入-净额": 6e7,
         "中单净流入-净额": -4e7, "小单净流入-净额": -1.1e8},
        {"日期": "bad-date", "收盘价": None},  # skipped: unparseable date
    ])
    res = StockFlowAdapter().run(session, codes=["600519"])
    assert res.status == "ok", res.error
    rows = session.scalars(select(FundFlowDaily)).all()
    assert len(rows) == 1
    r = rows[0]
    assert r.code == "600519" and r.trade_date.isoformat() == "2026-09-15"
    assert r.main_net_inflow == 1.5e8 and r.main_net_inflow_pct == 8.1
    assert r.super_large_net == 9e7 and r.small_net == -1.1e8
    # idempotent
    res2 = StockFlowAdapter().run(session, codes=["600519"])
    assert res2.status == "ok", res2.error
    assert len(session.scalars(select(FundFlowDaily)).all()) == 1
