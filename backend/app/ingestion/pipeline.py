"""Ingestion pipeline orchestration + CLI.

Coordinates bulk and per-symbol feeds, resolves the universe, and records results.
Usable programmatically (``run_all``) from the scheduler/API, or from the shell:

    python -m app.ingestion.pipeline --feed ratings_daily --date 2026-09-10
    python -m app.ingestion.pipeline --all --universe hs300
    python -m app.ingestion.pipeline --resolve-universe hs300
"""
from __future__ import annotations

import argparse
from datetime import date, datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import init_db, session_scope
from app.core.logging import configure_logging, get_logger
from app.ingestion import throttle
from app.ingestion.adapters import BULK_ORDER, PER_SYMBOL_ORDER, get_adapter
from app.ingestion.base import FeedResult
from app.ingestion.universe import resolve_universe

logger = get_logger(__name__)


def _configure_throttle() -> None:
    throttle.configure(settings.akshare_throttle_seconds)


def _parse_date(s: Optional[str]) -> Optional[date]:
    if not s:
        return None
    return datetime.strptime(s, "%Y-%m-%d").date()


def run_feed(name: str, session: Session, **kwargs) -> FeedResult:
    adapter = get_adapter(name)
    # Per-symbol feeds require a resolved universe.
    if adapter.per_symbol and "codes" not in kwargs:
        kwargs["codes"] = resolve_universe(kwargs.pop("universe", None), session=session)
    logger.info("▶ run feed '%s' (%s)", name, adapter.description)
    return adapter.run(session, **kwargs)


def run_bulk(session: Session, trade_date: Optional[date] = None, feeds: Optional[list[str]] = None) -> list[FeedResult]:
    results: list[FeedResult] = []
    for name in feeds or BULK_ORDER:
        kwargs: dict = {}
        if name in ("ratings_daily", "recommend_pool", "spot_snapshot") and trade_date:
            kwargs["trade_date"] = trade_date
        results.append(run_feed(name, session, **kwargs))
    return results


def run_per_symbol(
    session: Session,
    universe: Optional[str] = None,
    feeds: Optional[list[str]] = None,
    **kwargs,
) -> list[FeedResult]:
    codes = resolve_universe(universe, session=session)
    if not codes:
        logger.warning("Universe '%s' resolved to 0 codes; skipping per-symbol feeds.", universe or settings.universe)
        return []
    logger.info("Per-symbol universe: %d codes", len(codes))
    results: list[FeedResult] = []
    for name in feeds or PER_SYMBOL_ORDER:
        results.append(run_feed(name, session, codes=codes, **kwargs))
    return results


def run_all(session: Session, universe: Optional[str] = None, trade_date: Optional[date] = None) -> list[FeedResult]:
    results = run_bulk(session, trade_date=trade_date)
    results += run_per_symbol(session, universe=universe)
    ok = sum(1 for r in results if r.status in ("ok", "empty"))
    logger.info("Pipeline complete: %d/%d feeds ok", ok, len(results))
    return results


def main(argv: Optional[list[str]] = None) -> int:
    configure_logging()
    p = argparse.ArgumentParser(description="股票研报聚合平台 ingestion pipeline")
    p.add_argument("--feed", help="run a single feed by name")
    p.add_argument("--all", action="store_true", help="run bulk + per-symbol pipeline")
    p.add_argument("--bulk", action="store_true", help="run bulk feeds only")
    p.add_argument("--per-symbol", action="store_true", help="run per-symbol feeds only")
    p.add_argument("--universe", default=None, help="hs300|zz500|hs300+zz500|all|<code,code>")
    p.add_argument("--date", default=None, help="trading date YYYY-MM-DD for date-keyed feeds")
    p.add_argument("--start", default=None, help="start YYYYMMDD for history feeds")
    p.add_argument("--end", default=None, help="end YYYYMMDD for history feeds")
    p.add_argument("--resolve-universe", default=None, help="print resolved universe codes and exit")
    p.add_argument("--list", action="store_true", help="list available feeds and exit")
    args = p.parse_args(argv)

    _configure_throttle()
    init_db()  # idempotent (create_all); use alembic in prod

    if args.list:
        from app.ingestion.adapters import REGISTRY

        for name, a in REGISTRY.items():
            print(f"{name:22} per_symbol={str(a.per_symbol):5} {a.description}")
        return 0

    if args.resolve_universe:
        with session_scope() as session:
            codes = resolve_universe(args.resolve_universe, session=session)
        print(f"{len(codes)} codes: {', '.join(codes[:50])}{' ...' if len(codes) > 50 else ''}")
        return 0

    trade_date = _parse_date(args.date)
    extra: dict = {}
    if args.start:
        extra["start"] = args.start
    if args.end:
        extra["end"] = args.end

    with session_scope() as session:
        if args.feed:
            r = run_feed(args.feed, session, universe=args.universe, trade_date=trade_date, **extra)
            print(f"[{r.feed}] {r.status} seen={r.rows_seen} upserted={r.rows_upserted} "
                  f"{r.latency_ms}ms err={r.error or '-'}")
            return 0 if r.status != "error" else 1
        if args.bulk:
            results = run_bulk(session, trade_date=trade_date)
        elif args.per_symbol:
            results = run_per_symbol(session, universe=args.universe, **extra)
        elif args.all:
            results = run_all(session, universe=args.universe, trade_date=trade_date)
        else:
            p.print_help()
            return 0
        for r in results:
            print(f"[{r.feed}] {r.status} seen={r.rows_seen} upserted={r.rows_upserted} err={r.error or '-'}")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
