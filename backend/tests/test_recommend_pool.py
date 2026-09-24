"""recommend_pool offline tests — sina fetch is monkeypatched (no network).

Covers the adapter (normalize/persist into RecommendPool) and the read service
(list/summary) that backs GET /api/pool.
"""
from __future__ import annotations

from importlib import import_module

import pandas as pd
from sqlalchemy import select

from app.ingestion import throttle
from app.models.research import RecommendPool
from app.models.security import Security
from app.services import recommend_pool as pool_svc

# Package __init__ re-exports the adapter instance under the same name; grab the
# real module so monkeypatch can replace its fetch_pool global.
pool_mod = import_module("app.ingestion.adapters.recommend_pool")

throttle.configure(0.0)  # no artificial delay in tests


def _fake_fetch_pool(url: str) -> pd.DataFrame:
    if "vIR_RatingUp" in url:
        return pd.DataFrame([
            # int code → must zfill to 6 digits; 评级日期↓ renamed by fetch/normalize
            {"股票代码": 1328, "股票名称": "XX公司", "最新评级": "买入", "评级机构": "国泰君安",
             "分析师": "张三", "行业": "半导体", "评级日期↓": "2026-09-20", "目标价": 45.5},
            {"股票代码": "600519", "股票名称": "贵州茅台", "最新评级": "增持", "评级机构": "中信证券",
             "分析师": "李四", "行业": "白酒", "评级日期↓": "2026-09-22", "目标价": None},
            {"股票代码": None, "股票名称": "坏行"},  # skipped: no code
        ])
    if "vIR_RatingDown" in url:
        return pd.DataFrame([
            {"股票代码": "000001", "股票名称": "平安银行", "最新评级": "减持", "评级机构": "招商证券",
             "分析师": "王五", "行业": "银行", "评级日期↓": "2026-09-21", "目标价": 10.0},
        ])
    return pd.DataFrame([
        {"股票代码": "300750", "股票名称": "宁德时代", "最新评级": "买入", "评级机构": "国泰君安",
         "分析师": "赵六", "行业": "电池", "评级日期↓": "2026-09-18", "目标价": None},
    ])


def test_recommend_pool_persists_three_kinds(session, monkeypatch):
    session.add(Security(code="600519", name="贵州茅台", type="stock", exchange="SSE",
                         industry_sw="食品饮料", industry_group="消费服务"))
    session.flush()
    monkeypatch.setattr(pool_mod, "fetch_pool", _fake_fetch_pool)

    res = pool_mod.adapter.run(session)
    assert res.status == "ok", res.error
    rows = session.scalars(select(RecommendPool)).all()
    assert {r.kind for r in rows} == {"upgrade", "downgrade", "first"}
    assert len(rows) == 4  # third upgrade row (no code) skipped

    up = next(r for r in rows if r.code == "001328")  # int 1328 → 001328
    assert up.kind == "upgrade" and up.rating == "买入"
    assert up.org == "国泰君安" and up.target_price == 45.5
    assert up.trade_date.isoformat() == "2026-09-20"
    assert up.direction == "买入" and up.strength == "强"

    moutai = next(r for r in rows if r.code == "600519")
    assert moutai.industry_group == "消费服务"  # mapped from Security.industry_sw
    assert moutai.security_id is not None

    down = next(r for r in rows if r.kind == "downgrade")
    assert down.direction == "减持" and down.strength == "中"

    # idempotent
    res2 = pool_mod.adapter.run(session)
    assert res2.status == "ok", res2.error
    assert len(session.scalars(select(RecommendPool)).all()) == 4


def test_pool_service_list_and_summary(session, monkeypatch):
    monkeypatch.setattr(pool_mod, "fetch_pool", _fake_fetch_pool)
    pool_mod.adapter.run(session)

    rows, total, ref = pool_svc.list_pool(session, days=30, page=1, size=50)
    assert total == 4 and ref is not None
    assert rows[0]["trade_date"] >= rows[-1]["trade_date"]  # ordered desc

    ups, up_total, _ = pool_svc.list_pool(session, kind="upgrade", days=365)
    assert up_total == 2 and all(r["kind"] == "upgrade" for r in ups)

    s = pool_svc.summary(session, days=30)
    assert s["counts"] == {"upgrade": 2, "downgrade": 1, "first": 1}
    assert s["total"] == 4 and s["ref"] is not None
    assert {i["industry"] for i in s["industries"]}  # groups resolved


def test_pool_service_empty_db_is_safe(session):
    rows, total, ref = pool_svc.list_pool(session)
    assert rows == [] and total == 0 and ref is None
    s = pool_svc.summary(session)
    assert s["ref"] is None and s["counts"] == {} and s["total"] == 0
