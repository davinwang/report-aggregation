"""MCP tool implementations — plain read-only functions over the service layer.

Each function takes an explicit ``Session`` and returns a JSON-ready dict, which
keeps them unit-testable and reusable: ``server.py`` registers them as MCP tools
(session plumbing lives there) and a future AI function-calling layer can reuse
the same registry. No tool writes to the database.
"""
from __future__ import annotations

from datetime import timedelta
from typing import Optional

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.api.common import clamp_page, parse_date
from app.api.v1.endpoints.quant import WARMUP, _resolve_bars
from app.models.financial import FinancialIndicator, FinancialStatement
from app.services import basis as basis_svc
from app.services import flow as flow_svc
from app.services import linkage as linkage_svc
from app.services import matrix as matrix_svc
from app.services import news as news_svc
from app.services import options as options_svc
from app.services import signals as signals_svc
from app.services.accuracy import leaderboard
from app.services.aggregation import market_dashboard as market_dashboard_svc
from app.services.aggregation import research_reports_query, stock_detail
from app.services.indicators import DEFAULT_INDICATORS, build_series
from app.services.quotes import load_bars

__all__ = [
    "market_dashboard",
    "stock_snapshot",
    "search_reports",
    "technical_series",
    "market_matrix",
    "list_signals",
    "accuracy_leaderboard",
    "basis_overview",
    "options_overview",
    "flow_overview",
    "linkage_overview",
    "financial_summary",
    "list_news",
]


def market_dashboard(db: Session) -> dict:
    """市场看板: 指数行情、板块热力图、评级变动与最新研报 (最近一周窗口)."""
    return market_dashboard_svc(db, period="week")


def stock_snapshot(db: Session, code: str) -> dict:
    """个股快照: 行情 + 财务指标 + 最新研报 + 评级 + 资金流 (aggregated stock page)."""
    data = stock_detail(db, code)
    if data is None:
        raise ValueError(f"Unknown security code: {code}")
    return data


def search_reports(
    db: Session,
    keyword: Optional[str] = None,
    code: Optional[str] = None,
    org: Optional[str] = None,
    industry: Optional[str] = None,
    rating: Optional[str] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
    page: int = 1,
    size: int = 20,
) -> dict:
    """研报库检索 (title/name keyword, org, industry, rating, code, YYYY-MM-DD range)."""
    page, size = clamp_page(page, min(max(1, size), 100))
    rows, total = research_reports_query(
        db, keyword=keyword, code=code, org=org, industry=industry, rating=rating,
        start=parse_date(start), end=parse_date(end), page=page, size=size,
    )
    return {"total": total, "page": page, "size": size, "rows": rows}


def technical_series(
    db: Session,
    code: str,
    period: str = "1y",
    indicators: Optional[str] = None,
) -> dict:
    """技术指标序列 (ECharts-ready): MA/EMA/BOLL/MACD/KDJ/RSI... over stored bars.

    ``period``: 6m|1y|2y|3y|5y (or a bar count, capped at 1500). ``indicators``:
    comma-separated (e.g. "ma,macd,kdj"); defaults to the platform 6-indicator set.
    """
    names = [x.strip() for x in (indicators or "").split(",") if x.strip()] or DEFAULT_INDICATORS
    bars = _resolve_bars(period)
    df = load_bars(db, code, limit=bars + WARMUP)
    return build_series(df, names=names, bars=bars, code=code)


def market_matrix(db: Session, scope: str = "index+active", limit: int = 60) -> dict:
    """全市场速览: 指数(+活跃个股) 技术快照 matrix (trend/MA20/MACD/RSI states)."""
    scope = scope if scope in ("index", "index+active") else "index+active"
    limit = max(1, min(int(limit), 300))
    rows = matrix_svc.snapshot(db, scope=scope, limit=limit)
    return {"count": len(rows), "rows": rows}


def list_signals(
    db: Session,
    kind: Optional[str] = None,
    days: int = 30,
    industry: Optional[str] = None,
    page: int = 1,
    size: int = 50,
) -> dict:
    """可操作信号: upgrade|downgrade|first|consensus 评级信号 within a day window."""
    page, size = clamp_page(page, min(max(1, size), 200))
    rows, total, ref = signals_svc.list_signals(
        db, action=kind, industry=industry, days=days, page=page, size=size
    )
    return {"ref": ref.isoformat() if ref else None, "total": total,
            "page": page, "size": size, "rows": rows}


def accuracy_leaderboard(
    db: Session,
    horizon: int = 20,
    by: str = "org",
    min_events: int = 5,
    limit: int = 50,
) -> dict:
    """研报准确率排行: hit-rate & net-skill vs 沪深300 (horizon 20|60), by org|analyst."""
    horizon = 60 if int(horizon) == 60 else 20
    by = "analyst" if by == "analyst" else "org"
    limit = max(1, min(int(limit), 200))
    return leaderboard(db, horizon=horizon, by=by, min_events=max(1, int(min_events)), limit=limit)


def basis_overview(db: Session, variety: Optional[str] = None) -> dict:
    """股指期货基差: term structure + latest basis snapshot (IF|IH|IC|IM)."""
    v = (variety or "IF").upper()
    if v not in basis_svc.VARIETIES:
        v = "IF"
    code, name = basis_svc.VARIETY_UNDERLYING[v]
    return {
        "varieties": basis_svc.VARIETIES,
        "variety": v,
        "underlying": {"code": code, "name": name},
        "term_structure": basis_svc.term_structure(db, v),
        "overview": basis_svc.overview(db),
    }


def options_overview(db: Session) -> dict:
    """股指期权概览: per-underlying PCR / volume / OI summary (IO/MO/HO 系列)."""
    return {"underlyings": options_svc.UNDERLYING_NAMES, "overview": options_svc.overview(db)}


def flow_overview(db: Session, kind: str = "northbound", days: int = 30) -> dict:
    """资金流向: northbound(沪深港通 net flow + breadth) | margin(两融) | lhb(龙虎榜)."""
    kind = kind if kind in ("northbound", "margin", "lhb") else "northbound"
    if kind == "northbound":
        return flow_svc.northbound_history(db, days=max(1, min(int(days), 250)))
    if kind == "margin":
        return flow_svc.margin_history(db, days=max(5, min(int(days), 250)))
    data = flow_svc.lhb_query(db, page=1, size=50)
    return {"trade_date": data["trade_date"], "stats": data["stats"], "rows": data["rows"]}


def linkage_overview(db: Session, window: int = 120) -> dict:
    """板块/指数联动: index return-correlation matrix + per-stock beta vs 沪深300."""
    window = max(20, min(int(window), 500))
    return {
        "correlation": linkage_svc.correlation_matrix(db, window=window),
        "beta": linkage_svc.beta_table(db, window=window, limit=100),
    }


def financial_summary(db: Session, code: str, statement: str = "income", limit: int = 12) -> dict:
    """财务摘要: 三大报表期序列 (balance|income|cashflow) + key financial indicators."""
    statement = statement if statement in ("balance", "income", "cashflow") else "income"
    limit = max(1, min(int(limit), 40))
    rows = db.scalars(
        select(FinancialStatement)
        .where(FinancialStatement.code == code, FinancialStatement.statement == statement,
               FinancialStatement.source == "em")
        .order_by(desc(FinancialStatement.report_period)).limit(limit)
    ).all()
    if not rows:
        # transparent fallback to the other source (mirrors /api/financials)
        rows = db.scalars(
            select(FinancialStatement)
            .where(FinancialStatement.code == code, FinancialStatement.statement == statement)
            .order_by(desc(FinancialStatement.report_period)).limit(limit)
        ).all()
    inds = db.scalars(
        select(FinancialIndicator).where(FinancialIndicator.code == code)
        .order_by(desc(FinancialIndicator.report_period)).limit(limit)
    ).all()
    return {
        "code": code,
        "statement": statement,
        "statements": [
            {"report_period": r.report_period, "source": r.source, "data": r.data_json} for r in rows
        ],
        "indicators": [
            {
                "report_period": r.report_period, "eps": r.eps, "bps": r.bps, "roe": r.roe,
                "revenue_yoy": r.revenue_yoy, "net_profit_yoy": r.net_profit_yoy,
                "gross_margin": r.gross_margin, "net_margin": r.net_margin, "debt_ratio": r.debt_ratio,
            }
            for r in inds
        ],
    }


def list_news(
    db: Session,
    q: Optional[str] = None,
    sentiment: Optional[str] = None,
    source: Optional[str] = None,
    days: int = 1,
    page: int = 1,
    size: int = 50,
) -> dict:
    """资讯舆情快讯: 关键词/情绪(利好|中性|利空)/来源(em|cls) 过滤, 近 ``days`` 天."""
    page, size = clamp_page(page, min(max(1, size), 200))
    ref = news_svc.latest_news_date(db)
    start = ref - timedelta(days=max(0, int(days) - 1)) if ref else None
    rows, total = news_svc.list_news(
        db, q=q, sentiment=sentiment, source=source, start=start, page=page, size=size
    )
    return {"total": total, "page": page, "size": size, "ref": ref.isoformat() if ref else None, "rows": rows}
