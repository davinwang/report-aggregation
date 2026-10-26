"""研报洞察 (research insights) — 情绪分歧度 / 信号复盘 / 龙虎榜×研报联动.

Rule-based read models over stored data (no LLM, no new ingestion):

* ``sentiment`` — per-stock 研报情绪聚合: recent reports (default 30d) are scored
  via ``RATING_SCORE`` (买入=+2 … 卖出=−2). ``consensus`` = mean score ∈ [−2,2];
  ``dispersion`` (分歧度) = std-dev of scores across orgs. High dispersion =
  analyst disagreement (Diether et al. 2002: 分歧大的股票未来收益更差).
* ``replay`` — 信号复盘卡片: for each stored ``Signal`` whose entry date is at
  least ``horizon`` trading days old, compute the forward stock vs 沪深300
  return over ``horizon`` days and report hit/miss (same rule as accuracy:
  买入 beats benchmark, 卖出/减持 loses to it).
* ``lhb_research`` — 龙虎榜×研报联动: LHB records (default 10d) joined with
  research coverage in the ``window_days`` before/after the LHB date. Both
  signals on the same stock = 双重信号 (smart-money + analyst attention).
"""
from __future__ import annotations

from bisect import bisect_left
from datetime import date, timedelta
from typing import Any

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.ingestion.normalizers import RATING_SCORE, norm_rating
from app.models.base import RatingDirection
from app.models.flow import LhbRecord
from app.models.market import DailyQuote
from app.models.research import ResearchReport, Signal

BENCHMARK_CODE = "sh000300"
NEUTRAL_EPS = 1e-9


# ================================ 情绪/分歧 ================================
def sentiment(
    session: Session,
    days: int = 30,
    min_reports: int = 2,
    limit: int = 200,
    order: str = "dispersion",
) -> dict[str, Any]:
    """Per-stock report sentiment & dispersion over the recent window."""
    ref = session.scalar(select(func.max(ResearchReport.publish_date)))
    if ref is None:
        return {"ref": None, "days": days, "rows": [], "market": {}}
    since = ref - timedelta(days=days)

    rows = session.execute(
        select(
            ResearchReport.code, ResearchReport.name, ResearchReport.org,
            ResearchReport.rating, ResearchReport.publish_date,
        )
        .where(ResearchReport.publish_date >= since, ResearchReport.org.isnot(None))
        .order_by(ResearchReport.publish_date)
    ).all()

    per_code: dict[str, dict[str, Any]] = {}
    for code, name, org, rating, _pub in rows:
        d = norm_rating(rating)
        if d is RatingDirection.unknown:
            continue
        s = per_code.setdefault(
            code, {"name": name, "scores": [], "orgs": set(), "bull": 0, "bear": 0, "neutral": 0},
        )
        s["scores"].append(RATING_SCORE[d])
        s["orgs"].add(str(org))
        if d in (RatingDirection.buy, RatingDirection.overweight):
            s["bull"] += 1
        elif d in (RatingDirection.underweight, RatingDirection.sell):
            s["bear"] += 1
        else:
            s["neutral"] += 1

    out = []
    for code, s in per_code.items():
        n = len(s["scores"])
        if n < max(1, min_reports):
            continue
        mean = sum(s["scores"]) / n
        var = sum((x - mean) ** 2 for x in s["scores"]) / n
        std = var ** 0.5
        orgs = len(s["orgs"])
        # 分歧度 needs cross-org comparison; single-org stocks carry no disagreement info
        if orgs < 2:
            continue
        out.append({
            "code": code,
            "name": s["name"],
            "reports": n,
            "orgs": orgs,
            "bull": s["bull"],
            "bear": s["bear"],
            "neutral": s["neutral"],
            "consensus": round(mean, 3),
            "dispersion": round(std, 3),
            "label": _sentiment_label(mean, std),
        })

    key = {"dispersion": lambda r: (-r["dispersion"], -abs(r["consensus"])),
           "consensus": lambda r: (-r["consensus"], -r["dispersion"])}[order]
    out.sort(key=key)
    out = out[:limit]

    market_mean = (
        round(sum(r["consensus"] * r["reports"] for r in out) / sum(r["reports"] for r in out), 3)
        if out else None
    )
    return {
        "ref": ref.isoformat(),
        "days": days,
        "rows": out,
        "market": {
            "stocks": len(out),
            "reports": sum(r["reports"] for r in out),
            "avg_consensus": market_mean,
            "high_dispersion": sum(1 for r in out if r["dispersion"] >= 1.0),
        },
    }


def _sentiment_label(mean: float, std: float) -> str:
    if std >= 1.0:
        return "重大分歧"
    if mean > NEUTRAL_EPS:
        return "一致看多" if std < 0.5 else "偏多"
    if mean < -NEUTRAL_EPS:
        return "一致看空" if std < 0.5 else "偏空"
    return "中性"


# ================================ 信号复盘 ================================
def replay(
    session: Session,
    horizon: int = 20,
    days: int = 90,
    kind: str | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    """Closed-loop review of stored signals: forward return vs 沪深300."""
    ref = session.scalar(select(func.max(DailyQuote.trade_date)))
    if ref is None:
        return {"ref": None, "horizon": horizon, "rows": [], "summary": {}}

    since = ref - timedelta(days=days + horizon * 2)  # raw-day margin for the window
    q = select(Signal).where(
        Signal.trade_date >= since,
        Signal.trade_date <= ref - timedelta(days=horizon),  # entry window fully closed
    )
    if kind:
        q = q.where(Signal.kind == kind)
    signals = session.scalars(q.order_by(desc(Signal.trade_date)).limit(limit * 3)).all()
    if not signals:
        return {"ref": ref.isoformat(), "horizon": horizon, "rows": [], "summary": {}}

    bench_dates, bench = _load_benchmark(session)
    closes = _load_closes(session, sorted({s.code for s in signals}))

    rows: list[dict[str, Any]] = []
    hits = evaluated = 0
    rets: list[float] = []
    for sig in signals:
        series = closes.get(sig.code)
        if not series:
            continue
        dates, cs = series
        entry_idx = bisect_left(dates, sig.trade_date)
        exit_idx = entry_idx + horizon
        if entry_idx >= len(dates) or exit_idx >= len(dates):
            continue
        entry, exit_ = cs[entry_idx], cs[exit_idx]
        b_entry = _bench_close(bench_dates, bench, dates[entry_idx])
        b_exit = _bench_close(bench_dates, bench, dates[exit_idx])
        if None in (entry, exit_, b_entry, b_exit) or not entry or not b_entry:
            continue
        stock_ret = exit_ / entry - 1.0
        bench_ret = b_exit / b_entry - 1.0
        excess = stock_ret - bench_ret
        evaluated += 1
        rets.append(excess)
        bullish = (sig.direction or "") in ("买入", "增持")
        hit = excess > 0 if bullish else excess < 0
        if hit:
            hits += 1
        rows.append({
            "code": sig.code,
            "name": sig.name,
            "trade_date": sig.trade_date.isoformat(),
            "kind": sig.kind,
            "direction": sig.direction,
            "strength": sig.strength,
            "reason": sig.reason,
            "entry": entry,
            "exit": exit_,
            "stock_ret": round(stock_ret, 4),
            "bench_ret": round(bench_ret, 4),
            "excess": round(excess, 4),
            "hit": hit,
            "bullish": bullish,
        })
        if evaluated >= limit:
            break

    rows.sort(key=lambda r: r["trade_date"], reverse=True)
    win = hits / evaluated if evaluated else None
    avg_excess = sum(rets) / len(rets) if rets else None
    return {
        "ref": ref.isoformat(),
        "horizon": horizon,
        "rows": rows,
        "summary": {
            "evaluated": evaluated,
            "hits": hits,
            "win_rate": round(win, 4) if win is not None else None,
            "avg_excess": round(avg_excess, 4) if avg_excess is not None else None,
            "best": max(rows, key=lambda r: r["excess"]) if rows else None,
            "worst": min(rows, key=lambda r: r["excess"]) if rows else None,
        },
    }


# ============================ 龙虎榜 × 研报联动 ============================
def lhb_research(
    session: Session,
    lhb_days: int = 10,
    window_days: int = 30,
    direction: str | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    """LHB stocks with research coverage around the same period."""
    ref = session.scalar(select(func.max(LhbRecord.trade_date)))
    if ref is None:
        return {"ref": None, "rows": [], "summary": {}}
    since = ref - timedelta(days=lhb_days)
    where = [LhbRecord.trade_date >= since]
    if direction == "buy":
        where.append(LhbRecord.net_amt > 0)
    elif direction == "sell":
        where.append(LhbRecord.net_amt < 0)
    lhb_rows = session.scalars(select(LhbRecord).where(*where).order_by(desc(LhbRecord.trade_date))).all()
    if not lhb_rows:
        return {"ref": ref.isoformat(), "rows": [], "summary": {}}

    codes = sorted({r.code for r in lhb_rows})
    cov_since = since - timedelta(days=window_days)
    cov_until = ref + timedelta(days=window_days)
    reports = session.execute(
        select(
            ResearchReport.code, func.count(), func.min(ResearchReport.publish_date),
            func.max(ResearchReport.publish_date),
        )
        .where(
            ResearchReport.code.in_(codes),
            ResearchReport.publish_date >= cov_since,
            ResearchReport.publish_date <= cov_until,
            ResearchReport.org.isnot(None),
        )
        .group_by(ResearchReport.code)
    ).all()
    coverage: dict[str, dict[str, Any]] = {
        code: {
            "reports": cnt, "first": first, "last": last,
            "orgs": _org_count(session, code, cov_since, cov_until),
        }
        for code, cnt, first, last in reports
    }

    by_code: dict[str, dict[str, Any]] = {}
    for r in lhb_rows:
        c = by_code.setdefault(r.code, {
            "code": r.code, "name": r.name, "events": 0, "net_amt": 0.0,
            "last_date": None, "reasons": set(),
        })
        c["events"] += 1
        c["net_amt"] += r.net_amt or 0.0
        c["last_date"] = max(c["last_date"], r.trade_date) if c["last_date"] else r.trade_date
        c["reasons"].add(r.reason)

    rows = []
    dual = 0
    for code, c in by_code.items():
        cov = coverage.get(code)
        if cov:
            dual += 1
        rows.append({
            "code": code,
            "name": c["name"],
            "lhb_events": c["events"],
            "last_lhb_date": c["last_date"].isoformat(),
            "net_amt": round(c["net_amt"], 0),
            "reasons": sorted(c["reasons"])[:3],
            "coverage": (
                {
                    "reports": cov["reports"],
                    "orgs": cov["orgs"],
                    "first": cov["first"].isoformat(),
                    "last": cov["last"].isoformat(),
                }
                if cov else None
            ),
        })
    rows.sort(key=lambda r: (r["coverage"] is not None, -abs(r["net_amt"])), reverse=False)
    # dual-signal first, then by |net_amt| desc
    rows.sort(key=lambda r: (0 if r["coverage"] else 1, -abs(r["net_amt"])))
    rows = rows[:limit]

    total_net = sum(r["net_amt"] for r in rows)
    return {
        "ref": ref.isoformat(),
        "rows": rows,
        "summary": {
            "lhb_stocks": len(by_code),
            "dual_signal": dual,
            "covered_ratio": round(dual / len(by_code), 4) if by_code else None,
            "net_total": round(total_net, 0),
        },
    }


def _org_count(session: Session, code: str, since: date, until: date) -> int:
    return session.scalar(
        select(func.count(func.distinct(ResearchReport.org))).where(
            ResearchReport.code == code,
            ResearchReport.publish_date >= since,
            ResearchReport.publish_date <= until,
            ResearchReport.org.isnot(None),
        )
    ) or 0


# ------------------------------ shared quote helpers ------------------------------
def _load_benchmark(session: Session) -> tuple[list[date], dict[date, float | None]]:
    rows = session.execute(
        select(DailyQuote.trade_date, DailyQuote.close)
        .where(DailyQuote.code == BENCHMARK_CODE).order_by(DailyQuote.trade_date)
    ).all()
    return [d for d, _c in rows], {d: c for d, c in rows}


def _load_closes(session: Session, codes: list[str]) -> dict[str, tuple[list[date], list[float | None]]]:
    out: dict[str, tuple[list[date], list[float | None]]] = {}
    for i in range(0, len(codes), 200):
        chunk = codes[i:i + 200]
        rows = session.execute(
            select(DailyQuote.code, DailyQuote.trade_date, DailyQuote.close)
            .where(DailyQuote.code.in_(chunk), DailyQuote.adjust == "qfq")
            .order_by(DailyQuote.code, DailyQuote.trade_date)
        ).all()
        for code, d, c in rows:
            dates, closes = out.setdefault(code, ([], []))
            dates.append(d)
            closes.append(c)
    return out


def _bench_close(bench_dates: list[date], bench: dict[date, float | None], d: date) -> float | None:
    i = bisect_left(bench_dates, d)
    if i < len(bench_dates) and bench_dates[i] == d:
        return bench[d]
    if i == 0:
        return None
    return bench[bench_dates[i - 1]]
