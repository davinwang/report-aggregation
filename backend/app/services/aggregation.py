"""Aggregation service — assembles read models for the dashboard, 研报库, and 个股详情.

All functions read from the DB only (never AkShare) and return JSON-ready dicts. This
is the single place where cross-table aggregation lives, keeping endpoints thin.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Optional

from sqlalchemy import desc, func, or_, select
from sqlalchemy.orm import Session

from app.models.financial import FinancialIndicator
from app.models.market import DailyQuote
from app.models.research import RatingEvent, ResearchReport, Signal
from app.models.security import IndustryBoard, Security
from app.models.system import DataFreshness
from app.services.period import Window, resolve_window

_RATING_LABEL = {
    "买入": "buy", "增持": "overweight", "中性": "neutral",
    "减持": "underweight", "卖出": "sell", "未评级": "unknown",
}


def latest_trade_date(session: Session) -> Optional[date]:
    return session.scalar(select(func.max(DailyQuote.trade_date)))


def freshness_map(session: Session) -> dict[str, dict]:
    rows = session.execute(
        select(DataFreshness.feed, DataFreshness.last_success_at, DataFreshness.latest_data_date,
               DataFreshness.rows_total, DataFreshness.weeks_behind)
    ).all()
    return {
        feed: {
            "last_success_at": ls.isoformat() if ls else None,
            "latest_data_date": ld.isoformat() if ld else None,
            "rows_total": rt or 0,
            "weeks_behind": wb,
        }
        for feed, ls, ld, rt, wb in rows
    }


def _index_quotes(session: Session) -> list[dict]:
    out: list[dict] = []
    idx = session.scalars(select(Security).where(Security.type == "index")).all()
    for sec in idx:
        rows = session.execute(
            select(DailyQuote).where(DailyQuote.security_id == sec.id)
            .order_by(desc(DailyQuote.trade_date)).limit(2)
        ).scalars().all()
        if not rows:
            continue
        last = rows[0]
        prev_close = rows[1].close if len(rows) > 1 else last.pre_close
        chg = None
        if last.close is not None and prev_close:
            chg = round((last.close - prev_close) / prev_close * 100, 2)
        out.append({
            "code": sec.code, "name": sec.name, "close": last.close,
            "change_pct": chg, "volume": last.volume, "trade_date": last.trade_date.isoformat(),
        })
    return out


def _sector_heatmap(session: Session, sector: Optional[str] = None, limit: int = 90) -> list[dict]:
    q = select(IndustryBoard).where(IndustryBoard.source == "em")
    if sector:
        q = q.where(IndustryBoard.group == sector)
    q = q.order_by(desc(IndustryBoard.change_pct)).limit(limit)
    return [
        {"name": b.name, "group": b.group, "change_pct": b.change_pct, "turnover": b.turnover,
         "company_count": b.company_count}
        for b in session.scalars(q).all()
    ]


def _rating_summary(session: Session, w: Window, sector: Optional[str] = None) -> dict[str, Any]:
    q = (select(RatingEvent.rating_norm, func.count())
         .where(RatingEvent.trade_date.between(w.start, w.end)))
    if sector:
        q = q.join(Security, Security.code == RatingEvent.code).where(Security.industry_group == sector)
    q = q.group_by(RatingEvent.rating_norm)
    counts = {r or "unknown": c for r, c in session.execute(q).all()}
    total = sum(counts.values())
    orgs = session.scalar(
        select(func.count(func.distinct(RatingEvent.org)))
        .where(RatingEvent.trade_date.between(w.start, w.end))
    ) or 0
    return {"total": total, "by_rating": counts, "orgs": orgs}


def _top_signals(session: Session, w: Window, kind: str, sector: Optional[str] = None, limit: int = 10) -> list[dict]:
    q = select(Signal).where(Signal.kind == kind, Signal.trade_date.between(w.start, w.end))
    if sector:
        q = q.where(Signal.industry_group == sector)
    q = q.order_by(desc(Signal.trade_date), desc(Signal.score)).limit(limit)
    return [
        {"code": s.code, "name": s.name, "direction": s.direction, "strength": s.strength,
         "reason": s.reason, "trade_date": s.trade_date.isoformat(), "industry_group": s.industry_group}
        for s in session.scalars(q).all()
    ]


def _latest_reports(session: Session, w: Window, sector: Optional[str] = None, limit: int = 20) -> list[dict]:
    q = select(ResearchReport).where(ResearchReport.publish_date.between(w.start, w.end))
    if sector:
        q = q.where(or_(ResearchReport.industry_group == sector, ResearchReport.industry == sector))
    q = q.order_by(desc(ResearchReport.publish_date)).limit(limit)
    return [_report_brief(r) for r in session.scalars(q).all()]


def _report_brief(r: ResearchReport) -> dict:
    return {
        "id": r.id, "code": r.code, "name": r.name, "title": r.title, "org": r.org,
        "analysts": r.analysts, "rating": r.rating, "rating_change": r.rating_change,
        "target_price_low": r.target_price_low, "target_price_high": r.target_price_high,
        "industry": r.industry, "industry_group": r.industry_group,
        "publish_date": r.publish_date.isoformat() if r.publish_date else None,
        "pdf_url": r.pdf_url, "source": r.source,
    }


def market_dashboard(session: Session, period: str = "week", ref: Optional[date] = None,
                     sector: Optional[str] = None) -> dict[str, Any]:
    w = resolve_window(period, ref)
    return {
        "window": w.to_dict(),
        "indices": _index_quotes(session),
        "sectorHeatmap": _sector_heatmap(session, sector),
        "ratingSummary": _rating_summary(session, w, sector),
        "topUpgrades": _top_signals(session, w, "upgrade", sector),
        "topDowngrades": _top_signals(session, w, "downgrade", sector),
        "latestReports": _latest_reports(session, w, sector),
        "freshness": freshness_map(session),
        "latestTradeDate": (latest_trade_date(session) or w.end).isoformat(),
    }


def research_reports_query(
    session: Session,
    keyword: Optional[str] = None,
    org: Optional[str] = None,
    industry: Optional[str] = None,
    rating: Optional[str] = None,
    code: Optional[str] = None,
    start: Optional[date] = None,
    end: Optional[date] = None,
    page: int = 1,
    size: int = 20,
    sort: str = "-publish_date",
) -> tuple[list[dict], int]:
    q = select(ResearchReport)
    if keyword:
        like = f"%{keyword}%"
        q = q.where(or_(ResearchReport.title.like(like), ResearchReport.name.like(like)))
    if org:
        q = q.where(ResearchReport.org == org)
    if industry:
        q = q.where(or_(ResearchReport.industry_group == industry, ResearchReport.industry == industry))
    if rating:
        q = q.where(ResearchReport.rating == rating)
    if code:
        q = q.where(ResearchReport.code == code)
    if start:
        q = q.where(ResearchReport.publish_date >= start)
    if end:
        q = q.where(ResearchReport.publish_date <= end)

    total = session.scalar(select(func.count()).select_from(q.subquery())) or 0

    desc_flag = sort.startswith("-")
    sort_field = sort.lstrip("-")
    col = getattr(ResearchReport, sort_field, ResearchReport.publish_date)
    q = q.order_by(desc(col) if desc_flag else col)
    q = q.offset(max(0, (page - 1) * size)).limit(size)
    return [_report_brief(r) for r in session.scalars(q).all()], total


def research_facets(session: Session) -> dict[str, Any]:
    """Distinct filter values for the 研报库 UI (orgs, industries, ratings)."""
    orgs = [o for (o,) in session.execute(
        select(ResearchReport.org).where(ResearchReport.org.isnot(None))
        .group_by(ResearchReport.org).order_by(desc(func.count())).limit(200)).all() if o]
    industries = [i for (i,) in session.execute(
        select(ResearchReport.industry_group).where(ResearchReport.industry_group.isnot(None))
        .group_by(ResearchReport.industry_group)).all() if i]
    ratings = [r for (r,) in session.execute(
        select(ResearchReport.rating).where(ResearchReport.rating.isnot(None))
        .group_by(ResearchReport.rating)).all() if r]
    return {"orgs": orgs, "industries": industries, "ratings": ratings}


def stock_detail(session: Session, code: str) -> Optional[dict[str, Any]]:
    sec = session.scalar(select(Security).where(Security.code == code))
    if sec is None:
        return None
    # latest quote (prefer qfq/raw history, fall back to any)
    last = session.scalar(
        select(DailyQuote).where(DailyQuote.security_id == sec.id)
        .order_by(desc(DailyQuote.trade_date)).limit(1)
    )
    fin = session.scalar(
        select(FinancialIndicator).where(FinancialIndicator.code == code)
        .order_by(desc(FinancialIndicator.report_period)).limit(1)
    )
    reports, report_total = research_reports_query(session, code=code, page=1, size=10)
    ratings = session.execute(
        select(RatingEvent).where(RatingEvent.code == code)
        .order_by(desc(RatingEvent.trade_date)).limit(20)
    ).scalars().all()
    return {
        "security": {
            "code": sec.code, "name": sec.name, "type": sec.type, "exchange": sec.exchange,
            "industry_sw": sec.industry_sw, "industry_group": sec.industry_group,
        },
        "quote": {
            "close": last.close, "change_pct": last.change_pct, "open": last.open,
            "high": last.high, "low": last.low, "volume": last.volume, "amount": last.amount,
            "turnover_rate": last.turnover_rate,
            "trade_date": last.trade_date.isoformat() if last else None,
        } if last else None,
        "financials": {
            "report_period": fin.report_period, "eps": fin.eps, "bps": fin.bps, "roe": fin.roe,
            "revenue_yoy": fin.revenue_yoy, "net_profit_yoy": fin.net_profit_yoy,
            "gross_margin": fin.gross_margin, "net_margin": fin.net_margin, "debt_ratio": fin.debt_ratio,
        } if fin else None,
        "reports": reports,
        "report_total": report_total,
        "ratings": [
            {"trade_date": r.trade_date.isoformat(), "org": r.org, "analyst": r.analyst,
             "rating": r.rating, "rating_change": r.rating_change,
             "target_low": r.target_low, "target_high": r.target_high}
            for r in ratings
        ],
    }


def rating_norm_label(norm: Optional[str]) -> str:
    for cn, en in _RATING_LABEL.items():
        if en == norm:
            return cn
    return norm or "未评级"
