"""Offline adapter tests — run adapters against a fake akshare and assert DB writes.

No network. Throttle is disabled to keep tests fast.
"""
from __future__ import annotations

import pandas as pd
from sqlalchemy import select

from app.ingestion import throttle
from app.ingestion.adapters.ratings_daily import RatingsDailyAdapter
from app.ingestion.adapters.research_reports import ResearchReportsAdapter
from app.ingestion.adapters.security_master import SecurityMasterAdapter
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
