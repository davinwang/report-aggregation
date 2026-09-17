"""Offline news_flash adapter tests — fake akshare frames, assert DB writes.

Frames mirror the real akshare 1.18.x shapes:
- ``stock_info_global_em``: 标题/摘要/发布时间(str datetime)/链接
- ``stock_info_global_cls``: 标题(可空)/内容/发布日期(date)/发布时间(datetime.time)
"""
from __future__ import annotations

from datetime import date, time

import pandas as pd
from sqlalchemy import select

from app.core.config import settings
from app.ingestion import throttle
from app.ingestion.adapters.news_flash import NewsFlashAdapter
from app.ingestion.sentiment import classify
from app.models.news import NewsItem
from app.models.security import Security
from app.models.system import DataFreshness

throttle.configure(0.0)


def _em_frame() -> pd.DataFrame:
    return pd.DataFrame([
        {"标题": "贵州茅台获大额回购，业绩超预期", "摘要": "公司公告回购方案，市场反应积极。",
         "发布时间": "2026-09-16 14:30:00", "链接": "https://finance.eastmoney.com/a/1001.html"},
        {"标题": "某公司遭立案调查", "摘要": "公司收到证监会立案告知书。",
         "发布时间": "2026-09-16 15:00:00", "链接": "https://finance.eastmoney.com/a/1002.html"},
    ])


def _cls_frame() -> pd.DataFrame:
    return pd.DataFrame([
        {"标题": "", "内容": "财联社9月16日讯，央行宣布降准0.5个百分点，释放长期资金。",
         "发布日期": date(2026, 9, 16), "发布时间": time(9, 5, 21)},
        {"标题": "贵州茅台：控股股东拟增持公司股份", "内容": "增持金额不低于30亿元。",
         "发布日期": date(2026, 9, 16), "发布时间": time(10, 12, 0)},
    ])


def _seed_stock(session):
    session.add(Security(code="600519", name="贵州茅台", type="stock", exchange="SSE"))
    session.flush()


def test_news_flash_persists_annotates_and_dedupes(session, fake_ak):
    _seed_stock(session)
    fake_ak.stock_info_global_em = _em_frame
    fake_ak.stock_info_global_cls = lambda symbol="全部": _cls_frame()

    adapter = NewsFlashAdapter()
    res = adapter.run(session)
    assert res.status == "ok", res.error
    assert res.rows_seen == 4

    rows = session.scalars(select(NewsItem).order_by(NewsItem.publish_at)).all()
    assert len(rows) == 4

    by_title = {r.title: r for r in rows}
    # em rows keep title/content/link and get str-datetime parsed
    em = by_title["贵州茅台获大额回购，业绩超预期"]
    assert em.source == "em" and em.publish_at.hour == 14 and em.sentiment == "利好"
    assert em.url.endswith("1001.html")
    assert em.related_codes == [{"code": "600519", "name": "贵州茅台"}]
    assert by_title["某公司遭立案调查"].sentiment == "利空"

    # cls rows: empty title falls back to a content snippet; date+time combined
    cls_fallback = next(r for r in rows if r.source == "cls" and r.title.startswith("财联社9月16日讯"))
    assert cls_fallback.publish_at.time() == time(9, 5, 21)
    cls_moutai = by_title["贵州茅台：控股股东拟增持公司股份"]
    assert cls_moutai.source == "cls" and cls_moutai.publish_at.hour == 10
    assert cls_moutai.related_codes == [{"code": "600519", "name": "贵州茅台"}]

    # freshness stamped for the feed
    fresh = session.scalar(select(DataFreshness).where(DataFreshness.feed == "news_flash"))
    assert fresh is not None and fresh.latest_data_date == date(2026, 9, 16)

    # idempotent: a second run upserts instead of duplicating
    adapter.run(session)
    assert len(session.scalars(select(NewsItem)).all()) == 4


def test_news_flash_single_source_failure_is_ok(session, fake_ak):
    def _boom(**kwargs):
        raise RuntimeError("cls down")

    fake_ak.stock_info_global_em = _em_frame
    fake_ak.stock_info_global_cls = _boom

    res = NewsFlashAdapter().run(session)
    assert res.status == "ok", res.error
    rows = session.scalars(select(NewsItem)).all()
    assert len(rows) == 2 and {r.source for r in rows} == {"em"}


def test_news_flash_total_failure_reports_error(session, fake_ak, monkeypatch):
    monkeypatch.setattr(settings, "akshare_max_retries", 1)  # no backoff sleeps

    def _boom(**kwargs):
        raise RuntimeError("down")

    fake_ak.stock_info_global_em = _boom
    fake_ak.stock_info_global_cls = _boom

    res = NewsFlashAdapter().run(session)
    assert res.status == "error"
    assert session.scalars(select(NewsItem)).all() == []


def test_sentiment_classify_labels():
    assert classify("公司获得大额中标，业绩超预期")[0] == "利好"
    assert classify("遭立案调查，股价跌停")[0] == "利空"
    assert classify("公司发布日常经营公告")[0] == "中性"
    assert classify("")[0] == "中性"
