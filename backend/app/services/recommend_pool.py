"""机构推荐池 (institutional recommend pool) — read path for ``/api/pool``.

Mirrors ``services.signals``: list pages/filtered rows inside a trailing window
anchored at the newest ``trade_date``; summary returns per-kind headline counts
for the stat cards. Data is written by the ``recommend_pool`` ingest feed (sina).
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.models.research import RecommendPool

KINDS = ("upgrade", "downgrade", "first")
DEFAULT_DAYS = 30


def list_pool(
    session: Session,
    kind: str | None = None,
    industry: str | None = None,
    days: int = DEFAULT_DAYS,
    date_: date | None = None,
    page: int = 1,
    size: int = 50,
) -> tuple[list[dict[str, Any]], int, date | None]:
    where = []
    if date_:
        where.append(RecommendPool.trade_date == date_)
        ref = date_
    else:
        ref = session.scalar(select(func.max(RecommendPool.trade_date)))
        if ref is None:
            return [], 0, None
        where.append(RecommendPool.trade_date >= ref - timedelta(days=max(1, days)))
    if kind in KINDS:
        where.append(RecommendPool.kind == kind)
    if industry:
        where.append(RecommendPool.industry_group == industry)

    total = session.scalar(select(func.count()).select_from(RecommendPool).where(*where)) or 0
    rows = session.scalars(
        select(RecommendPool).where(*where)
        .order_by(desc(RecommendPool.trade_date), desc(RecommendPool.target_price), RecommendPool.code)
        .offset((page - 1) * size).limit(size)
    ).all()
    return [
        {
            "id": r.id,
            "code": r.code,
            "name": r.name,
            "trade_date": r.trade_date.isoformat(),
            "kind": r.kind,
            "rating": r.rating,
            "direction": r.direction,
            "strength": r.strength,
            "org": r.org,
            "analysts": r.analysts,
            "target_price": r.target_price,
            "industry": r.industry,
            "industry_group": r.industry_group,
            "sources": r.sources_json,
        }
        for r in rows
    ], total, ref


def summary(session: Session, days: int = DEFAULT_DAYS) -> dict[str, Any]:
    """Headline counts for the /pool stat cards."""
    ref = session.scalar(select(func.max(RecommendPool.trade_date)))
    if ref is None:
        return {"ref": None, "days": days, "counts": {}, "total": 0, "industries": []}
    since = ref - timedelta(days=max(1, days))
    counts = {
        kind: n
        for kind, n in session.execute(
            select(RecommendPool.kind, func.count())
            .where(RecommendPool.trade_date >= since)
            .group_by(RecommendPool.kind)
        ).all()
    }
    industries = session.execute(
        select(RecommendPool.industry_group, func.count())
        .where(RecommendPool.trade_date >= since, RecommendPool.industry_group.isnot(None))
        .group_by(RecommendPool.industry_group)
        .order_by(desc(func.count())).limit(10)
    ).all()
    return {
        "ref": ref.isoformat(),
        "days": days,
        "counts": {k: counts.get(k, 0) for k in KINDS},
        "total": sum(counts.values()),
        "industries": [{"industry": i, "count": c} for i, c in industries],
    }
