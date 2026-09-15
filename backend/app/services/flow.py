"""资金流向 (capital flow) read helpers — 沪深港通 / 融资融券 / 龙虎榜.

Shapes the three stored flow feeds for the /flow page:

* 沪深港通 — per-board 资金净流入 plus 上涨/持平/下跌家数 (breadth). Note that the exchanges
  suspended mainland-leg net-flow disclosure, so 北向 net figures are 0 while the
  breadth counters stay live.
* 融资融券 — 上交所 has a daily range; 深交所 is a single-day snapshot (both normalized to 元).
* 龙虎榜 — daily detail ranked by 净买额.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.models.flow import LhbRecord, MarginData, NorthboundDaily

BOARD_ORDER = ["沪股通", "深股通", "港股通(沪)", "港股通(深)"]


def _sorted_boards(boards: set[str]) -> list[str]:
    known = [b for b in BOARD_ORDER if b in boards]
    return known + sorted(boards - set(known))


# ----------------------------- 沪深港通 -----------------------------
def northbound_history(session: Session, days: int = 30) -> dict:
    ref = session.scalar(select(func.max(NorthboundDaily.trade_date)))
    if ref is None:
        return {"dates": [], "boards": [], "net_inflow": {}, "up": {}, "down": {}, "latest": []}
    since = ref - timedelta(days=max(7, days * 2))
    rows = session.scalars(
        select(NorthboundDaily)
        .where(NorthboundDaily.trade_date >= since)
        .order_by(NorthboundDaily.trade_date)
    ).all()

    dates = sorted({r.trade_date for r in rows})
    if len(dates) > days:
        dates = dates[-days:]
    keep = set(dates)
    boards = _sorted_boards({r.board for r in rows})

    def series(board: str, pick) -> list[Optional[float]]:
        by_date = {r.trade_date: r for r in rows if r.board == board}
        return [pick(by_date[d]) if d in by_date else None for d in dates]

    def extra(r: NorthboundDaily) -> dict:
        return r.extra_json or {}

    net_inflow = {b: series(b, lambda r: r.net_inflow) for b in boards}
    up = {b: series(b, lambda r: extra(r).get("up")) for b in boards}
    down = {b: series(b, lambda r: extra(r).get("down")) for b in boards}

    latest_rows = [r for r in rows if r.trade_date == dates[-1]] if dates else []
    latest = [
        {
            "trade_date": r.trade_date.isoformat(),
            "board": r.board,
            "type": extra(r).get("type"),
            "direction": extra(r).get("direction"),
            "net_inflow": r.net_inflow,
            "net_buy": extra(r).get("net_buy"),
            "balance": extra(r).get("balance"),
            "up": extra(r).get("up"),
            "flat": extra(r).get("flat"),
            "down": extra(r).get("down"),
            "index": extra(r).get("index"),
            "index_pct": extra(r).get("index_pct"),
        }
        for r in latest_rows
    ]
    return {
        "dates": [d.isoformat() for d in dates],
        "boards": boards,
        "net_inflow": net_inflow,
        "up": up,
        "down": down,
        "latest": latest,
        "ref": dates[-1].isoformat() if dates else None,
    }


# ----------------------------- 融资融券 -----------------------------
def _margin_series(session: Session, exchange: str, days: int) -> tuple[list[date], list[MarginData]]:
    latest = session.scalar(
        select(func.max(MarginData.trade_date)).where(MarginData.exchange == exchange)
    )
    if latest is None:
        return [], []
    since = latest - timedelta(days=max(10, days * 2))
    rows = session.scalars(
        select(MarginData)
        .where(
            MarginData.exchange == exchange,
            MarginData.code.is_(None),
            MarginData.trade_date >= since,
        )
        .order_by(MarginData.trade_date)
    ).all()
    if len(rows) > days:
        rows = rows[-days:]
    return [r.trade_date for r in rows], list(rows)


def margin_history(session: Session, days: int = 60) -> dict:
    dates, sse_rows = _margin_series(session, "SSE", days)
    _szse_dates, szse_rows = _margin_series(session, "SZSE", 1)

    def col(rows: list[MarginData], field: str) -> list[Optional[float]]:
        return [getattr(r, field) for r in rows]

    sse_latest = sse_rows[-1] if sse_rows else None
    szse_latest = szse_rows[-1] if szse_rows else None

    return {
        "dates": [d.isoformat() for d in dates],
        "sse": {
            "rzye": col(sse_rows, "rzye"),
            "rzmre": col(sse_rows, "rzmre"),
            "rqye": col(sse_rows, "rqye"),
            "rzrqye": col(sse_rows, "rzrqye"),
        },
        "szse": (
            {
                "trade_date": szse_latest.trade_date.isoformat(),
                "rzye": szse_latest.rzye,
                "rzmre": szse_latest.rzmre,
                "rqye": szse_latest.rqye,
                "rzrqye": szse_latest.rzrqye,
            }
            if szse_latest
            else None
        ),
        "latest": (
            {
                "trade_date": sse_latest.trade_date.isoformat(),
                "rzye": sse_latest.rzye,
                "rzmre": sse_latest.rzmre,
                "rqye": sse_latest.rqye,
                "rzrqye": sse_latest.rzrqye,
            }
            if sse_latest
            else None
        ),
    }


# ----------------------------- 龙虎榜 -----------------------------
def latest_lhb_date(session: Session) -> Optional[date]:
    return session.scalar(select(func.max(LhbRecord.trade_date)))


def lhb_query(
    session: Session,
    ref: Optional[date] = None,
    direction: Optional[str] = None,
    page: int = 1,
    size: int = 50,
) -> dict:
    """Paged 龙虎榜 for one session, ranked by 净买额 desc.

    ``direction`` = ``buy`` (净买入) | ``sell`` (净卖出) | None (all).
    """
    ref = ref or latest_lhb_date(session)
    if ref is None:
        return {"rows": [], "total": 0, "page": page, "size": size, "trade_date": None, "stats": {}}

    where = [LhbRecord.trade_date == ref]
    if direction == "buy":
        where.append(LhbRecord.net_amt > 0)
    elif direction == "sell":
        where.append(LhbRecord.net_amt < 0)

    total = session.scalar(select(func.count()).select_from(LhbRecord).where(*where)) or 0
    rows = session.scalars(
        select(LhbRecord).where(*where).order_by(desc(LhbRecord.net_amt)).offset((page - 1) * size).limit(size)
    ).all()

    all_net = session.scalar(
        select(func.sum(LhbRecord.net_amt)).where(LhbRecord.trade_date == ref)
    )
    return {
        "trade_date": ref.isoformat(),
        "rows": [
            {
                "code": r.code, "name": r.name, "reason": r.reason,
                "close": r.close, "change_pct": r.change_pct,
                "buy_amt": r.buy_amt, "sell_amt": r.sell_amt, "net_amt": r.net_amt,
                "turnover": r.turnover,
            }
            for r in rows
        ],
        "total": total,
        "page": page,
        "size": size,
        "stats": {"net_total": all_net},
    }


def summary(session: Session) -> dict:
    """Headline numbers for the /flow stat cards."""
    nb = northbound_history(session, days=1)
    mg = margin_history(session, days=1)
    lhb_date = latest_lhb_date(session)
    lhb_net = (
        session.scalar(select(func.sum(LhbRecord.net_amt)).where(LhbRecord.trade_date == lhb_date))
        if lhb_date
        else None
    )
    south_rows = [r for r in nb["latest"] if r.get("direction") == "南向"]
    south_buy = sum(r.get("net_buy") or 0 for r in south_rows) or None
    north_boards = [r for r in nb["latest"] if r.get("direction") == "北向"]
    return {
        "northbound_date": nb.get("ref"),
        "north_up": sum(r.get("up") or 0 for r in north_boards) or None,
        "north_down": sum(r.get("down") or 0 for r in north_boards) or None,
        "southbound_net": south_rows[0].get("net_inflow") if south_rows else None,
        # 成交净买额 is the real southbound money flow (资金净流入 is a quota figure).
        "southbound_net_buy": south_buy,
        "margin_sse": mg.get("latest"),
        "margin_szse": mg.get("szse"),
        "lhb_date": lhb_date.isoformat() if lhb_date else None,
        "lhb_net_total": lhb_net,
    }
