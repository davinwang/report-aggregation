"""财务数据 (financials) endpoints — a NEW module for the stock version."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.api.common import clamp_page, envelope, paged
from app.core.db import get_db
from app.models.financial import Disclosure, EarningsReport, FinancialIndicator, FinancialStatement

router = APIRouter(prefix="/api/financials", tags=["financials"])


@router.get("/{code}/statements")
def statements(
    code: str,
    type: str = Query(default="balance", description="balance|income|cashflow"),
    source: str = Query(default="em", description="em|sina"),
    limit: int = Query(default=12, ge=1, le=40),
    db: Session = Depends(get_db),
) -> dict:
    rows = db.scalars(
        select(FinancialStatement)
        .where(FinancialStatement.code == code, FinancialStatement.statement == type,
               FinancialStatement.source == source)
        .order_by(desc(FinancialStatement.report_period)).limit(limit)
    ).all()
    if not rows and source == "em":
        # transparent fallback to the other source if available
        rows = db.scalars(
            select(FinancialStatement)
            .where(FinancialStatement.code == code, FinancialStatement.statement == type)
            .order_by(desc(FinancialStatement.report_period)).limit(limit)
        ).all()
    return envelope(
        [{"report_period": r.report_period, "source": r.source, "data": r.data_json} for r in rows],
        code=code, statement=type, count=len(rows),
    )


@router.get("/{code}/indicators")
def indicators(code: str, limit: int = Query(default=16, ge=1, le=40), db: Session = Depends(get_db)) -> dict:
    rows = db.scalars(
        select(FinancialIndicator).where(FinancialIndicator.code == code)
        .order_by(desc(FinancialIndicator.report_period)).limit(limit)
    ).all()
    return envelope([{
        "report_period": r.report_period, "eps": r.eps, "bps": r.bps, "roe": r.roe, "roa": r.roa,
        "revenue_yoy": r.revenue_yoy, "net_profit_yoy": r.net_profit_yoy, "gross_margin": r.gross_margin,
        "net_margin": r.net_margin, "debt_ratio": r.debt_ratio, "ocfps": r.ocfps,
    } for r in rows], code=code, count=len(rows))


@router.get("/{code}/earnings")
def earnings(code: str, limit: int = Query(default=12, ge=1, le=40), db: Session = Depends(get_db)) -> dict:
    rows = db.scalars(
        select(EarningsReport).where(EarningsReport.code == code)
        .order_by(desc(EarningsReport.report_period)).limit(limit)
    ).all()
    return envelope([{
        "report_period": r.report_period, "revenue": r.revenue, "revenue_yoy": r.revenue_yoy,
        "net_profit": r.net_profit, "net_profit_yoy": r.net_profit_yoy, "eps": r.eps,
        "roe": r.roe, "gross_margin": r.gross_margin,
        "disclose_date": r.disclose_date.isoformat() if r.disclose_date else None,
    } for r in rows], code=code, count=len(rows))


@router.get("/{code}/disclosures")
def disclosures(
    code: str,
    category: str | None = None,
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> dict:
    page, size = clamp_page(page, size)
    q = select(Disclosure).where(Disclosure.code == code)
    if category:
        q = q.where(Disclosure.category == category)
    q = q.order_by(desc(Disclosure.ann_date)).offset((page - 1) * size).limit(size)
    rows = db.scalars(q).all()
    return paged([{
        "ann_date": r.ann_date.isoformat(), "title": r.title, "category": r.category,
        "url": r.url, "source": r.source,
    } for r in rows], total=len(rows), page=page, size=size, code=code)
