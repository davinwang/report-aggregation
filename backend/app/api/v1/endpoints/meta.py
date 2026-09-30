"""Meta endpoints: securities search, industry taxonomy, period windows, indicator aliases."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.api.common import envelope
from app.core.db import get_db
from app.models.security import INDUSTRY_GROUPS, IndustryBoard, Security
from app.services.aggregation import latest_trade_date
from app.services.indicators import ALIASES, FREQS, INDICATORS, catalog
from app.services.signal_matrix import SCOPES, STATE_LABELS

router = APIRouter(prefix="/api/meta", tags=["meta"])

#: Security kinds the search box can filter by. ``etf``/``bond`` were added with the
#: 场内基金/可转债 technical feeds; they share ``daily_quote`` with stocks and indices.
SECURITY_TYPES: tuple[str, ...] = ("stock", "index", "etf", "bond", "future", "option")


@router.get("/securities")
def securities(
    keyword: Optional[str] = None,
    type: Optional[str] = Query(default=None, description="|".join(SECURITY_TYPES)),
    limit: int = Query(default=50, le=500),
    db: Session = Depends(get_db),
) -> dict:
    q = select(Security)
    if type:
        q = q.where(Security.type == type)
    if keyword:
        like = f"%{keyword}%"
        q = q.where(or_(Security.code.like(like), Security.name.like(like)))
    q = q.order_by(Security.code).limit(limit)
    rows = [
        {"code": s.code, "name": s.name, "type": s.type, "exchange": s.exchange,
         "industry_sw": s.industry_sw, "industry_group": s.industry_group}
        for s in db.scalars(q).all()
    ]
    return envelope(rows)


@router.get("/industries")
def industries(db: Session = Depends(get_db)) -> dict:
    groups = sorted(set(INDUSTRY_GROUPS.values()))
    boards = db.scalars(select(IndustryBoard).where(IndustryBoard.source == "em")).all()
    return envelope({
        "groups": groups,
        "group_of": INDUSTRY_GROUPS,
        "boards": [{"name": b.name, "group": b.group} for b in boards],
    })


@router.get("/dates")
def dates(db: Session = Depends(get_db)) -> dict:
    ltd = latest_trade_date(db)
    return envelope({
        "latest_trade_date": ltd.isoformat() if ltd else None,
        "periods": [
            {"key": "today", "label": "今日"},
            {"key": "week", "label": "本周"},
            {"key": "twoweek", "label": "近两周"},
            {"key": "month", "label": "本月"},
        ],
    })


@router.get("/indicator-aliases")
def indicator_aliases() -> dict:
    return envelope({
        "indicators": sorted(INDICATORS.keys()),
        "aliases": ALIASES,
    })


@router.get("/indicator-catalog")
def indicator_catalog() -> dict:
    """Same catalog as ``/api/quant/indicator-catalog``, with the raw key registries.

    Duplicated here on purpose: ``/api/meta`` is the page that answers "what does this
    platform know", and the header's indicator search shouldn't need the quant client.
    """
    items = catalog()
    return envelope({
        "items": items,
        "indicators": sorted(INDICATORS.keys()),
        "aliases": ALIASES,
        "freqs": list(FREQS),
        "groups": sorted({i["group"] for i in items}),
        "signal_states": STATE_LABELS,
        "signal_scopes": list(SCOPES),
    })
