"""股指期权 board date anchoring — a newer *stock* bar must not blank the board.

Regression: ``services.options`` used to pin every read to
``MAX(daily_quote.trade_date)``. Sina's daily feed writes partial same-day stock bars
for the in-progress session, which advance that max one day past the option snapshot,
so the T型报价 board resolved to a date with no option rows and rendered empty.
"""
from __future__ import annotations

from datetime import date

from sqlalchemy import select

from app.ingestion.adapters.index_options import IndexOptionsAdapter
from app.models.market import DailyQuote, OptionQuote
from app.models.security import Security
from app.services import options as options_svc

SNAP = date(2026, 9, 14)   # newest session with option quotes
NEXT = date(2026, 9, 15)   # in-progress session (partial stock bars only)


def _index_bar(session, d: date, close: float) -> None:
    session.add(
        DailyQuote(security_id=1, code="sh000300", trade_date=d, close=close, adjust="none", source="sina")
    )


def _stock_bar(session, d: date) -> None:
    session.add(
        DailyQuote(security_id=2, code="600009", trade_date=d, close=23.06, adjust="qfq", source="sina")
    )


def _option(session, contract_code: str, cp: str, strike: float, d: date = SNAP) -> None:
    session.add(
        OptionQuote(
            underlying="沪深300股指期权", end_month=d.strftime("%y%m"), contract_code=contract_code,
            trade_date=d, strike=strike, cp=cp, close=100.0, pre_settle=98.0, volume=10.0, oi=20.0,
        )
    )


def test_board_anchors_to_option_snapshot(session):
    session.add(Security(code="sh000300", name="沪深300", type="index", exchange="SSE"))
    _index_bar(session, SNAP, 4480.0)
    _option(session, "IO2609-C-3900", "call", 3900.0)
    _option(session, "IO2609-P-3900", "put", 3900.0)
    _stock_bar(session, NEXT)
    session.commit()

    b = options_svc.board(session, "沪深300股指期权")
    assert b["trade_date"] == SNAP.isoformat()   # not the newer stock-bar date
    assert b["month"] == "2609" and b["months"] == ["2609"]
    assert len(b["rows"]) == 1 and b["rows"][0]["strike"] == 3900.0
    assert b["spot"] == 4480.0 and b["atm_strike"] == 3900.0
    assert b["totals"]["contracts"] == 2
    assert b["totals"]["pcr_oi"] == 1.0

    # overview (frontend 各品种概览) resolves through the same anchor.
    row = next(o for o in options_svc.overview(session) if o["underlying"] == "沪深300股指期权")
    assert row["trade_date"] == SNAP.isoformat() and row["spot"] == 4480.0


def test_spot_looks_back_when_index_bar_lags(session):
    session.add(Security(code="sh000300", name="沪深300", type="index", exchange="SSE"))
    _index_bar(session, SNAP, 4480.0)  # index feed one session behind the snapshot
    _option(session, "IO2609-C-3900", "call", 3900.0, d=NEXT)
    session.commit()

    b = options_svc.board(session, "沪深300股指期权")
    assert b["trade_date"] == NEXT.isoformat()
    assert b["spot"] == 4480.0   # falls back to the newest close on or before the snapshot


def test_persist_stamps_the_index_session(session):
    session.add(Security(code="sh000300", name="沪深300", type="index", exchange="SSE"))
    _index_bar(session, SNAP, 4480.0)
    _stock_bar(session, NEXT)
    session.commit()

    rows = [{
        "underlying": "沪深300股指期权", "end_month": "2609", "contract_code": "IO2609-C-3900",
        "strike": 3900.0, "cp": "call", "close": 100.0, "pre_settle": 98.0, "volume": 10.0, "oi": 20.0,
    }]
    assert IndexOptionsAdapter().persist(session, rows) == 1
    session.commit()
    stored = session.scalars(select(OptionQuote)).all()
    assert [q.trade_date for q in stored] == [SNAP]
