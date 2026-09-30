"""技术信号矩阵 tests — the voting rules, the net tally, and the exclusions.

Rules are tested against hand-built frames rather than recorded market data so each
assertion states the rule's own 口径 (e.g. "RSI=85 abstains instead of voting 偏多").
"""
from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.db import Base
from app.models.market import DailyQuote
from app.models.security import Security
from app.services import signal_matrix as S

# ---------------------------- fixtures ----------------------------

def _bars(n: int, start: float, drift: float, volume: float = 1e7,
          amount: float | None = 5e8, start_date: str = "2025-01-01",
          rng_seed: int | None = None) -> pd.DataFrame:
    """A clean frame: ``high``/``low`` always envelope open and close.

    A constant ``drift`` gives a perfectly one-sided series (good for asserting trend
    rules); pass ``rng_seed`` for a random walk (needed wherever the rule under test
    depends on two-sided movement, e.g. 波动分位 or BR/AR).
    """
    if rng_seed is not None:
        rng = np.random.default_rng(rng_seed)
        close = start + np.cumsum(rng.normal(drift, abs(drift) or 0.2, n))
    else:
        close = start + np.arange(n) * drift
    open_ = np.concatenate([[close[0]], close[:-1]])
    span = np.maximum(np.abs(np.diff(close, prepend=close[0])), abs(drift)) + 0.01
    return pd.DataFrame({
        "date": pd.date_range(start_date, periods=n, freq="B").strftime("%Y-%m-%d"),
        "open": open_, "high": np.maximum(open_, close) + span,
        "low": np.minimum(open_, close) - span, "close": close,
        "volume": np.full(n, volume, dtype=float),
        **({"amount": np.full(n, amount, dtype=float)} if amount is not None else {}),
    })


def _session(db_path: str):
    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _seed(db, code: str, df: pd.DataFrame, sec_type: str = "stock", name: str | None = None):
    sec = Security(code=code, name=name or code, type=sec_type, is_active=True)
    db.add(sec)
    db.flush()
    db.query(DailyQuote).filter(DailyQuote.code == code).delete()
    db.add_all([
        DailyQuote(security_id=sec.id, code=code, trade_date=date.fromisoformat(r["date"]),
                   open=r["open"], high=r["high"], low=r["low"], close=r["close"],
                   volume=r["volume"], amount=r.get("amount"), adjust="none", source="test")
        for r in df.to_dict("records")
    ])
    db.commit()


def _vote_one(df: pd.DataFrame) -> dict:
    """Run the full default rule set over one frame and return its votes."""
    votes, *_ = S._vote(df, list(S.DEFAULT_RULES), float(df["close"].iloc[-1]))
    return votes


# ---------------------------- states ----------------------------

def test_every_state_has_a_label():
    assert set(S.STATE_LABELS) == {S.BULL, S.BEAR, S.NEUTRAL, S.ABSTAIN, S.NA}
    assert S.STATE_LABELS[S.ABSTAIN] == "弃权"


def test_rsi_abstains_instead_of_voting_at_the_extremes():
    """The headline 口径 rule: 超买不能读成偏多. Momentum rules must abstain, not guess."""
    up = _vote_one(_bars(120, 10, 0.4))
    assert up["rsi"]["state"] == S.ABSTAIN
    assert up["rsi"]["voted"] is False
    assert up["rsi"]["score"] == 0.0
    assert "超买" in up["rsi"]["note"]

    down = _vote_one(_bars(120, 100, -0.4))
    assert down["rsi"]["state"] == S.ABSTAIN
    assert "超卖" in down["rsi"]["note"]


def test_abstaining_rule_contributes_nothing_to_the_net_tally():
    """An abstain carrying a weight must still add zero, or the net is silently wrong."""
    up = _vote_one(_bars(120, 10, 0.4))
    voted = [v["score"] for v in up.values() if v["voted"]]
    abstained = [v["score"] for v in up.values() if not v["voted"]]
    assert abstained and set(abstained) == {0.0}
    assert voted and all(s > 0 for s in voted)  # pure uptrend: nothing votes bearish


def test_trend_rules_agree_on_a_clean_uptrend():
    votes = _vote_one(_bars(120, 10, 0.4))
    for key in ("ma_trend", "ma_align", "macd", "boll", "roc"):
        assert votes[key]["state"] == S.BULL, key
        assert votes[key]["score"] > 0


def test_trend_rules_agree_on_a_clean_downtrend():
    votes = _vote_one(_bars(120, 100, -0.4))
    for key in ("ma_trend", "ma_align", "macd", "boll", "roc"):
        assert votes[key]["state"] == S.BEAR, key
        assert votes[key]["score"] < 0


def test_scores_are_signed_consistently_with_state():
    """The sign convention is the one place a rule author could get it wrong."""
    for drift in (0.4, -0.4, 0.0):
        for vote in _vote_one(_bars(120, 10, drift)).values():
            if vote["state"] == S.BULL:
                assert vote["score"] > 0 and vote["voted"]
            elif vote["state"] == S.BEAR:
                assert vote["score"] < 0 and vote["voted"]
            else:
                assert vote["score"] == 0.0 and not vote["voted"]


def test_dmi_abstains_without_a_trend():
    """A flat series has no ADX to speak with — the rule must decline, not guess."""
    votes = _vote_one(_bars(200, 50, 0.0))
    assert votes["dmi"]["state"] == S.ABSTAIN
    assert "无明显趋势" in votes["dmi"]["note"]


def test_dmi_speaks_once_there_is_a_trend():
    votes = _vote_one(_bars(200, 50, 0.05, rng_seed=3))
    assert votes["dmi"]["state"] in (S.BULL, S.BEAR)
    assert votes["dmi"]["voted"] is True


def test_hv_abstains_on_short_history():
    short = _vote_one(_bars(60, 10, 0.3, rng_seed=1))
    assert short["hv"]["state"] == S.ABSTAIN
    assert "样本不足" in short["hv"]["note"]
    # ...and speaks once the sample is long enough to place a percentile.
    long = _vote_one(_bars(260, 10, 0.05, rng_seed=1))
    assert long["hv"]["state"] in (S.NEUTRAL, S.ABSTAIN)
    assert "样本不足" not in long["hv"]["note"]


def test_hv_only_describes_risk_never_direction():
    """波动分位 must never vote — high volatility means any directional read is weaker."""
    for drift in (0.5, -0.5, 0.0):
        vote = _vote_one(_bars(260, 10, drift, rng_seed=5))["hv"]
        assert vote["state"] in (S.NEUTRAL, S.ABSTAIN)
        assert vote["voted"] is False


def test_macd_cross_is_an_event_not_a_state():
    """A persistent trend has no *crossing*, so the cross column stays 中性 while the
    MACD state column reads 偏多 — the two columns must not collapse into one."""
    votes = _vote_one(_bars(120, 10, 0.4))
    assert votes["macd"]["state"] == S.BULL
    assert votes["macd_cross"]["state"] == S.NEUTRAL


def test_a_rule_outside_the_default_set_still_gets_data():
    """``_vote`` must compute the requested rules' own indicators, not a fixed set."""
    df = _bars(120, 10, 0.3, rng_seed=2)
    assert "dpo" not in S.REQUIRED_INDICATORS

    def dpo_rule(ind, close):
        """收盘价在其 N/2+1 日前的均线之上即偏多."""
        v = S._last(ind.get("dpo"), "dpo")
        return (S.NA, 0.0, "未算出") if v is None else (
            (S.BULL, 1.0, "在均线之上") if close > v else (S.BEAR, 1.0, "在均线之下"))

    custom = S.Rule("custom", "自定义", ("dpo",), dpo_rule)
    votes, *_ = S._vote(df, [custom], float(df["close"].iloc[-1]))
    assert votes["custom"]["state"] == S.BULL
    assert votes["custom"]["voted"] is True


def test_missing_indicator_yields_na_with_an_explanation():
    """A rule whose indicator produced nothing must say so, not fall back to 中性."""
    df = _bars(120, 10, 0.3, rng_seed=2).drop(columns=["high", "low"])
    votes, *_ = S._vote(df, [S.RULES["kdj"]], float(df["close"].iloc[-1]))
    assert votes["kdj"]["state"] == S.NA
    assert votes["kdj"]["note"] == "指标不适用于该品种"
    assert votes["kdj"]["voted"] is False


def test_every_rule_has_a_doc_and_needed_indicators():
    items = S.rules_catalog()
    assert len(items) == len(S.DEFAULT_RULES)
    for item in items:
        assert item["doc"] and item["needs"]


def test_required_indicators_cover_every_rule():
    assert set(S.REQUIRED_INDICATORS) == {k for r in S.DEFAULT_RULES for k in r.needs}


# ---------------------------- build / summary ----------------------------

@pytest.fixture()
def store(tmp_path):
    db = _session(str(tmp_path / "sig.sqlite3"))
    _seed(db, "AAA", _bars(300, 10, 0.4), "stock", "上涨一号")
    _seed(db, "BBB", _bars(300, 100, -0.4), "stock", "下跌一号")
    _seed(db, "CCC", _bars(300, 50, 0.0), "stock", "横盘一号")
    # Same shape but barely traded: must be excluded from the tally, still listed.
    _seed(db, "DDD", _bars(300, 50, 0.4, volume=100.0, amount=1e4), "stock", "低流动")
    # ...and one whose data stops long before the market's latest session.
    _seed(db, "EEE", _bars(300, 50, 0.4, start_date="2020-01-01"), "stock", "已停牌")
    yield db
    db.close()


def test_build_orders_rows_and_flags_exclusions(store):
    res = S.build(store, scope="stock", limit=50, bars=300)
    by_code = {r["code"]: r for r in res.rows}
    assert set(by_code) == {"AAA", "BBB", "CCC", "DDD", "EEE"}
    assert by_code["DDD"]["excluded"] == "低流动"
    assert by_code["EEE"]["excluded"] == "滞后/停牌"
    # Excluded rows keep their real readings — only the tally skips them.
    assert by_code["DDD"]["signals"]["ma_trend"]["state"] == S.BULL
    assert by_code["AAA"]["excluded"] is None


def test_excluded_rows_do_not_move_the_market_tally(store):
    res = S.build(store, scope="stock", limit=50, bars=300)
    summary = res.summary
    assert summary["participating"] == 3
    assert summary["total"] == 5
    assert summary["excluded"]["低流动"] == 1
    assert summary["excluded"]["滞后/停牌"] == 1
    live = [r for r in res.rows if r["excluded"] is None]
    assert summary["market_net"] == sum(r["bulls"] - r["bears"] for r in live)
    # A row that doesn't vote must not be counted as either side.
    assert summary["breadth"]["bull"] + summary["breadth"]["bear"] \
        + summary["breadth"]["split"] + summary["breadth"]["flat"] == summary["participating"]


def test_net_sign_follows_the_verdict(store):
    res = S.build(store, scope="stock", limit=50, bars=300)
    by_code = {r["code"]: r for r in res.rows}
    assert by_code["AAA"]["verdict"] == "偏多" and by_code["AAA"]["net"] > 0
    assert by_code["BBB"]["verdict"] == "偏空" and by_code["BBB"]["net"] < 0
    assert by_code["AAA"]["bulls"] > by_code["AAA"]["bears"]


def test_column_tallies_match_the_rows(store):
    res = S.build(store, scope="stock", limit=50, bars=300)
    live = [r for r in res.rows if r["excluded"] is None]
    for key, tally in res.summary["columns"].items():
        counted = {S.BULL: 0, S.BEAR: 0, S.NEUTRAL: 0, S.ABSTAIN: 0, S.NA: 0}
        for r in live:
            counted[r["signals"][key]["state"]] += 1
        for state, n in counted.items():
            assert tally[state] == n, (key, state)
        assert tally["net"] == counted[S.BULL] - counted[S.BEAR]


def test_liquidity_floor_is_configurable(store):
    loose = S.build(store, scope="stock", limit=50, bars=300, liquidity_floor=0)
    assert all(r["excluded"] != "低流动" for r in loose.rows if r["signals"])
    assert any(r["excluded"] == "低流动"
               for r in S.build(store, scope="stock", limit=50, bars=300).rows)
    strict = S.build(store, scope="stock", limit=50, bars=300, liquidity_floor=1e15)
    assert strict.summary["participating"] < loose.summary["participating"]


def test_bonds_without_amount_fall_back_to_a_volume_proxy(tmp_path):
    """可转债 bars carry no 成交额; a gate returning "unknown" would read as "liquid"."""
    db = _session(str(tmp_path / "bond.sqlite3"))
    df = _bars(300, 100, 0.1, volume=500.0, amount=None)
    _seed(db, "113050", df, "bond", "某转债")
    res = S.build(db, scope="bond", limit=10, bars=300, liquidity_floor=1e6)
    row = res.rows[0]
    assert row["turnover"] == pytest.approx(500.0 * row["close"], rel=1e-3)
    assert row["excluded"] == "低流动"
    db.close()


def test_securities_without_bars_are_not_listed(tmp_path):
    """A bar-less Security is left out of the table, not rendered as a row of 无数据.

    ``scope=stock`` spans thousands of names; filling the matrix with securities nobody
    has ever collected would bury the ones that did trade. An empty table is the honest
    "this scope has no data yet" signal, which the endpoint reports as ``count=0``.
    """
    db = _session(str(tmp_path / "empty.sqlite3"))
    db.add(Security(code="ZZZ", name="无行情", type="stock", is_active=True))
    db.commit()
    assert S.build(db, scope="stock", limit=10, bars=300).rows == []
    db.close()


def test_scope_selects_only_that_kind(tmp_path):
    db = _session(str(tmp_path / "scope.sqlite3"))
    _seed(db, "600000", _bars(300, 10, 0.2), "stock", "个股")
    _seed(db, "510300", _bars(300, 4, 0.02), "etf", "沪深300ETF")
    _seed(db, "113050", _bars(300, 100, 0.1), "bond", "转债")
    _seed(db, "sh000300", _bars(300, 4000, 1.0), "index", "沪深300")
    assert [r["code"] for r in S.build(db, scope="etf", limit=10).rows] == ["510300"]
    assert [r["code"] for r in S.build(db, scope="bond", limit=10).rows] == ["113050"]
    assert [r["code"] for r in S.build(db, scope="stock", limit=10).rows] == ["600000"]
    assert len(S.build(db, scope="all", limit=10).rows) == 4
    db.close()


def test_unknown_scope_falls_back_to_the_default(tmp_path):
    db = _session(str(tmp_path / "bad.sqlite3"))
    _seed(db, "sh000300", _bars(300, 4000, 1.0), "index", "沪深300")
    res = S.build(db, scope="nonsense", limit=10, bars=300)
    # The reported scope must be the one actually used, not the raw input.
    assert res.meta["scope"] == "index"
    assert [r["code"] for r in res.rows] == ["sh000300"]
    db.close()


def test_column_subset_and_cache_key(store):
    res = S.build(store, scope="stock", limit=50, bars=300, columns=["ma_trend", "rsi"])
    assert [c["key"] for c in res.columns] == ["ma_trend", "rsi"]
    assert set(res.rows[0]["signals"]) == {"ma_trend", "rsi"}
    # An unknown column resolves to the full set rather than an empty table.
    assert len(S.build(store, scope="stock", limit=5, bars=300, columns=["nope"]).columns) \
        == len(S.DEFAULT_RULES)


def test_cache_key_distinguishes_every_input():
    base = S.cache_key_for()
    assert base != S.cache_key_for(scope="etf")
    assert base != S.cache_key_for(freq="weekly")
    assert base != S.cache_key_for(limit=30)
    assert base != S.cache_key_for(columns=["rsi"])
    assert base != S.cache_key_for(liquidity_floor=1e8)
    # Unspecified columns and the default set must share one entry.
    assert base == S.cache_key_for(columns=list(S.DEFAULT_RULES and [r.key for r in S.DEFAULT_RULES]))


def test_snapshot_is_cached(store, monkeypatch):
    calls = []
    real = S.build

    def counting(*args, **kwargs):
        calls.append(1)
        return real(*args, **kwargs)

    monkeypatch.setattr(S, "build", counting)
    first = S.snapshot(store, scope="stock", limit=50)
    second = S.snapshot(store, scope="stock", limit=50)
    assert first["rows"] == second["rows"]
    assert len(calls) <= 1, "the second read must come from cache"


def test_weekly_matrix_uses_resampled_bars(store):
    daily = S.build(store, scope="stock", limit=50, bars=300, freq="daily")
    weekly = S.build(store, scope="stock", limit=50, bars=300, freq="weekly")
    assert weekly.freq == "weekly"
    assert weekly.rows[0]["date"] <= daily.rows[0]["date"]
    # Weekly readings must exist and still vote, not silently degrade to 无数据.
    assert any(r["voted"] for r in weekly.rows)


def test_staleness_is_judged_within_the_universe_not_globally(tmp_path):
    """A freshly-refreshed feed must not mark a merely un-refreshed peer group as 停牌.

    Regression: with a global ``max(trade_date)`` reference, running the ETF feed (which
    had a newer last session) made every stock look 2 weeks stale, emptied the 个股 tab's
    participating count, and reported a `全市场分歧` verdict over zero voters.
    """
    db = _session(str(tmp_path / "cohort.sqlite3"))
    etf_bars = _bars(300, 4, 0.01, start_date="2025-01-01")
    stock_bars = _bars(300, 10, 0.1, start_date="2025-06-01")
    _seed(db, "510300", etf_bars, "etf", "ETF新")
    _seed(db, "600000", stock_bars, "stock", "个股旧")
    _seed(db, "600001", stock_bars, "stock", "个股旧2")

    etf = S.build(db, scope="etf", limit=10, bars=300)
    stock = S.build(db, scope="stock", limit=10, bars=300)
    # Each scope reports its own cohort's latest session...
    assert etf.as_of == etf_bars["date"].iloc[-1]
    assert stock.as_of == stock_bars["date"].iloc[-1]
    assert etf.as_of != stock.as_of, "the two cohorts must genuinely differ for this to prove anything"
    # ...and neither cohort is written off as 停牌 for lagging the other.
    assert stock.summary["excluded"]["滞后/停牌"] == 0
    assert stock.summary["participating"] == 2
    assert etf.summary["excluded"]["滞后/停牌"] == 0
    db.close()


def test_still_detects_a_name_that_lags_its_own_cohort(tmp_path):
    db = _session(str(tmp_path / "lag.sqlite3"))
    _seed(db, "600000", _bars(300, 10, 0.1, start_date="2025-01-01"), "stock", "正常")
    _seed(db, "600001", _bars(300, 10, 0.1, start_date="2024-01-01"), "stock", "停牌")
    res = S.build(db, scope="stock", limit=10, bars=300)
    by_code = {r["code"]: r for r in res.rows}
    assert by_code["600000"]["excluded"] is None
    assert by_code["600001"]["excluded"] == "滞后/停牌"
    assert res.summary["participating"] == 1
    db.close()


def test_missing_column_stays_missing_after_resampling(tmp_path):
    """An all-NULL 成交额 column must resample to NaN, not to 0.

    Regression: ``Series.sum()`` turns an all-missing bucket into ``0.0``, which reads as
    the thinnest possible book. Every resampled index row was therefore excluded from the
    weekly/monthly matrix as 低流动 — the tab rendered 17 rows and zero participants.
    """
    db = _session(str(tmp_path / "noamount.sqlite3"))
    df = _bars(300, 4000, 1.0, amount=None)
    df["amount"] = None  # the stored shape: column present, every value NULL
    _seed(db, "sh000300", df, "index", "沪深300")
    res = S.build(db, scope="index", limit=10, bars=300, freq="weekly")
    assert res.rows[0]["excluded"] != "低流动"
    assert res.summary["participating"] == 1
    # The volume×close proxy still supplies a usable figure.
    assert res.rows[0]["turnover"] > 0
    db.close()


def test_empty_ballot_is_not_reported_as_disagreement():
    assert S._summarize([], list(S.DEFAULT_RULES), {})["market_verdict"] == "无表决"
    rows = [_placeholder_row_like() for _ in range(3)]
    assert S._summarize(rows, list(S.DEFAULT_RULES), {})["market_verdict"] == "无表决"


def _placeholder_row_like() -> dict:
    """A row that carries signals but never votes (every column abstained)."""
    votes = {r.key: {"state": S.ABSTAIN, "label": "弃权", "score": 0.0,
                     "voted": False, "note": ""} for r in S.DEFAULT_RULES}
    return {"code": "X", "name": "X", "excluded": None, "signals": votes,
            "bulls": 0, "bears": 0, "verdict": "无方向", "voted": 0}


def test_turnover_proxy_when_amount_is_absent_but_volume_present():
    df = _bars(10, 10, 0.1, amount=None)
    assert S._turnover(df) == pytest.approx(float(df["volume"].iloc[-1])
                                            * float(df["close"].iloc[-1]), rel=1e-6)
    assert S._turnover(df.drop(columns=["volume"])) is None


def test_turnover_prefers_the_real_amount():
    df = _bars(10, 10, 0.1, amount=12345.0)
    assert S._turnover(df) == 12345.0


def test_stale_detection_uses_a_calendar_tolerance():
    """A run of holidays spans more calendar days than sessions; it must not read as 停牌."""
    from datetime import date

    ref = date(2025, 10, 8)  # 国庆假期后的首个交易日
    fresh = pd.DataFrame({"date": ["2025-09-30"]})          # 5 sessions before, 8 days
    assert S._is_stale(fresh, ref) is False
    dead = pd.DataFrame({"date": ["2025-08-20"]})
    assert S._is_stale(dead, ref) is True
    assert S._is_stale(fresh, None) is False
