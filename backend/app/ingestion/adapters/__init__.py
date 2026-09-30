"""Adapter registry.

Importing this package registers every feed by name so the pipeline/scheduler/CLI can
look them up uniformly. Add new adapters here (and to the ordering lists) as they land.
"""
from __future__ import annotations

from app.ingestion.adapters.cov_bond_daily import adapter as cov_bond_daily
from app.ingestion.adapters.cov_bond_daily import universe_adapter as cov_bond_universe
from app.ingestion.adapters.disclosures import adapter as disclosures
from app.ingestion.adapters.earnings import adapter as earnings
from app.ingestion.adapters.etf_daily import adapter as etf_daily
from app.ingestion.adapters.etf_daily import universe_adapter as etf_universe
from app.ingestion.adapters.fin_indicators import adapter as fin_indicators
from app.ingestion.adapters.financials_em import adapter as financials_em
from app.ingestion.adapters.index_daily import adapter as index_daily
from app.ingestion.adapters.index_futures import adapter as index_futures
from app.ingestion.adapters.index_options import adapter as index_options
from app.ingestion.adapters.industry_boards import adapter as industry_boards
from app.ingestion.adapters.industry_constituents import adapter as industry_constituents
from app.ingestion.adapters.lhb import adapter as lhb
from app.ingestion.adapters.margin import adapter as margin
from app.ingestion.adapters.news_flash import adapter as news_flash
from app.ingestion.adapters.northbound import adapter as northbound
from app.ingestion.adapters.price_history import adapter as price_history
from app.ingestion.adapters.ratings_daily import adapter as ratings_daily
from app.ingestion.adapters.recommend_pool import adapter as recommend_pool
from app.ingestion.adapters.research_reports import adapter as research_reports
from app.ingestion.adapters.security_master import adapter as security_master
from app.ingestion.adapters.spot_snapshot import adapter as spot_snapshot
from app.ingestion.adapters.stock_flow import adapter as stock_flow
from app.ingestion.base import BaseAdapter

REGISTRY: dict[str, BaseAdapter] = {a.name: a for a in (
    security_master,
    spot_snapshot,
    index_daily,
    etf_universe,
    cov_bond_universe,
    ratings_daily,
    recommend_pool,
    industry_boards,
    industry_constituents,
    earnings,
    price_history,
    etf_daily,
    cov_bond_daily,
    research_reports,
    financials_em,
    fin_indicators,
    disclosures,
    index_futures,
    index_options,
    northbound,
    margin,
    lhb,
    stock_flow,
    news_flash,
)}

# Feeds that iterate the universe (need codes=[...]).
PER_SYMBOL_FEEDS = [name for name, a in REGISTRY.items() if a.per_symbol]

# Default nightly ordering: cheap bulk feeds first, then per-symbol universe passes.
BULK_ORDER = [
    "security_master",
    "industry_boards",
    "industry_constituents",
    "spot_snapshot",
    "index_daily",
    "index_futures",
    "index_options",
    "etf_daily",
    "cov_bond_daily",
    "northbound",
    "margin",
    "lhb",
    "ratings_daily",
    "recommend_pool",
    "disclosures",
    "news_flash",
]
PER_SYMBOL_ORDER = [
    "price_history",
    "research_reports",
    "fin_indicators",
    "financials_em",
    "stock_flow",
]

# Frequency-based schedule groups (Asia/Shanghai). Each group is one scheduled
# job whose feed list is ordered so intra-group dependencies hold (e.g.
# index_futures needs index_daily bars for the basis spot leg, and
# security_master must exist before anything maps code → security_id).
# northbound sits in ``intraday`` (not daily_evening) because its upstream report
# only carries the current session and rolls to the next session's all-flat
# placeholder row once the evening clearing finishes (~16:30 CST) — the post-close
# intraday runs (15:10-15:50) are what persist the frozen closing 涨跌家数.
#   intraday          实时/盘中: 交易时段每10分钟 (市场看板/全市场速览/板块热力/沪深港通涨跌家数)
#   daily_close       日频·收盘后: 工作日 16:30 (技术指标/基差/期权/ETF/可转债)
#   daily_evening     日频·晚间: 工作日 19:00 (两融/龙虎榜/研报库/信号/公告)
#   weekly_master     周度主数据: 周一 (证券主档/行业成分/ETF与可转债代码表)
#   weekly_financials 周期·财报: 周六 (业绩/财务指标/三大报表)
#   news_refresh      资讯舆情·快讯: 每日 07:00-23:00 每20分钟 (东财快讯/财联社)
FEED_GROUPS: dict[str, list[str]] = {
    "intraday": ["northbound", "spot_snapshot", "industry_boards"],
    "daily_close": ["index_daily", "index_futures", "index_options", "price_history",
                    "etf_daily", "cov_bond_daily"],
    "daily_evening": [
        "margin",
        "lhb",
        "ratings_daily",
        "recommend_pool",
        "research_reports",
        "stock_flow",
        "disclosures",
    ],
    "weekly_master": ["security_master", "industry_constituents", "etf_universe",
                      "cov_bond_universe"],
    "weekly_financials": ["earnings", "fin_indicators", "financials_em"],
    "news_refresh": ["news_flash"],
}

# feed name -> groups it belongs to (for /ops feeds listing).
FEED_GROUP_OF: dict[str, list[str]] = {}
for _group, _feeds in FEED_GROUPS.items():
    for _feed in _feeds:
        FEED_GROUP_OF.setdefault(_feed, []).append(_group)


def get_adapter(name: str) -> BaseAdapter:
    if name not in REGISTRY:
        raise KeyError(f"Unknown feed '{name}'. Available: {', '.join(sorted(REGISTRY))}")
    return REGISTRY[name]


__all__ = [
    "REGISTRY",
    "PER_SYMBOL_FEEDS",
    "BULK_ORDER",
    "PER_SYMBOL_ORDER",
    "FEED_GROUPS",
    "FEED_GROUP_OF",
    "get_adapter",
]
