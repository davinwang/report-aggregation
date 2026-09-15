"""Adapter registry.

Importing this package registers every feed by name so the pipeline/scheduler/CLI can
look them up uniformly. Add new adapters here (and to the ordering lists) as they land.
"""
from __future__ import annotations

from app.ingestion.base import BaseAdapter

from app.ingestion.adapters.security_master import adapter as security_master
from app.ingestion.adapters.spot_snapshot import adapter as spot_snapshot
from app.ingestion.adapters.index_daily import adapter as index_daily
from app.ingestion.adapters.ratings_daily import adapter as ratings_daily
from app.ingestion.adapters.recommend_pool import adapter as recommend_pool
from app.ingestion.adapters.industry_boards import adapter as industry_boards
from app.ingestion.adapters.industry_constituents import adapter as industry_constituents
from app.ingestion.adapters.earnings import adapter as earnings
from app.ingestion.adapters.price_history import adapter as price_history
from app.ingestion.adapters.research_reports import adapter as research_reports
from app.ingestion.adapters.financials_em import adapter as financials_em
from app.ingestion.adapters.fin_indicators import adapter as fin_indicators
from app.ingestion.adapters.disclosures import adapter as disclosures
from app.ingestion.adapters.index_futures import adapter as index_futures

REGISTRY: dict[str, BaseAdapter] = {a.name: a for a in (
    security_master,
    spot_snapshot,
    index_daily,
    ratings_daily,
    recommend_pool,
    industry_boards,
    industry_constituents,
    earnings,
    price_history,
    research_reports,
    financials_em,
    fin_indicators,
    disclosures,
    index_futures,
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
    "ratings_daily",
    "recommend_pool",
    "disclosures",
]
PER_SYMBOL_ORDER = [
    "price_history",
    "research_reports",
    "fin_indicators",
    "financials_em",
]


def get_adapter(name: str) -> BaseAdapter:
    if name not in REGISTRY:
        raise KeyError(f"Unknown feed '{name}'. Available: {', '.join(sorted(REGISTRY))}")
    return REGISTRY[name]


__all__ = [
    "REGISTRY",
    "PER_SYMBOL_FEEDS",
    "BULK_ORDER",
    "PER_SYMBOL_ORDER",
    "get_adapter",
]
