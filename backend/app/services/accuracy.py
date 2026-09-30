"""研报准确率 (rating accuracy) — org/analyst hit-rate & net-skill, rule-based.

Methodology (fixed per plan §2.6):
- Events = rating calls from ``research_report`` (org dimension) / ``rating_event``
  (analyst dimension), deduped per (subject, code) to the **earliest** call inside
  the lookback window (one call per stock & institution).
- Entry = first trading day ≥ publish date (stock's own 前复权 close);
  exit = ``horizon`` trading days later.
- **Hit** — 买入/增持: stock return > 沪深300 return over the same window;
  减持/卖出: stock return < 沪深300 return. 中性/未评级 are skipped.
- ``hit_rate = hits/total``; ``net_skill = hit_rate − (1 − hit_rate)`` (= 2·hit_rate−1).
- Snapshots are stored in ``AccuracySnapshot`` with ``period_type = "h20"/"h60"``
  and ``period_key`` = the as-of trade date.

``compute_accuracy`` writes snapshots; ``leaderboard`` reads them for /accuracy.
"""
from __future__ import annotations

from bisect import bisect_left
from datetime import date, timedelta
from typing import Any

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.ingestion.normalizers import norm_rating
from app.models.base import RatingDirection
from app.models.market import DailyQuote
from app.models.research import AccuracySnapshot, RatingEvent, ResearchReport

HORIZONS = (20, 60)
BENCHMARK_CODE = "sh000300"
DEFAULT_LOOKBACK_DAYS = 180
DEFAULT_MIN_EVENTS = 5
BULLISH = (RatingDirection.buy, RatingDirection.overweight)
BEARISH = (RatingDirection.underweight, RatingDirection.sell)


# ------------------------------ write path ------------------------------
def compute_accuracy(
    session: Session,
    horizon: int = 20,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    ref: date | None = None,
    subject_type: str = "org",
) -> dict[str, Any]:
    """Evaluate rating calls over ``horizon`` trading days and store snapshots."""
    ref = ref or session.scalar(select(func.max(DailyQuote.trade_date)))
    if ref is None:
        return {"ref": None, "total": 0, "subjects": 0}

    events = _load_events(session, ref, lookback_days, subject_type)
    if not events:
        return {"ref": ref.isoformat(), "horizon": horizon, "subject_type": subject_type,
                "total": 0, "subjects": 0}

    bench = _load_benchmark(session)
    closes = _load_closes(session, sorted({code for _s, code, _r, _d in events}))
    stats = _evaluate(events, closes, bench, horizon)

    period_type = f"h{horizon}"
    prev = _prev_net_skill(session, period_type, subject_type, ref)
    rows = []
    for subject, s in stats.items():
        net = s["net_skill"]
        rows.append({
            "period_type": period_type,
            "period_key": ref.isoformat(),
            "subject_type": subject_type,
            "subject": subject,
            "hits": s["hits"],
            "total": s["total"],
            "hit_rate": s["hit_rate"],
            "net_skill": net,
            "prev_delta": (net - prev[subject]) if net is not None and subject in prev else None,
            "horizon_days": horizon,
        })

    if rows:
        existing = {
            s.subject: s
            for s in session.scalars(
                select(AccuracySnapshot).where(
                    AccuracySnapshot.period_type == period_type,
                    AccuracySnapshot.period_key == ref.isoformat(),
                    AccuracySnapshot.subject_type == subject_type,
                )
            ).all()
        }
        for r in rows:
            snap = existing.get(r["subject"])
            if snap is None:
                session.add(AccuracySnapshot(**r))
            else:
                for k, v in r.items():
                    setattr(snap, k, v)
        session.flush()

    return {
        "ref": ref.isoformat(),
        "horizon": horizon,
        "subject_type": subject_type,
        "total": sum(s["total"] for s in stats.values()),
        "subjects": len(stats),
    }


def _load_events(
    session: Session, ref: date, lookback_days: int, subject_type: str,
) -> list[tuple[str, str, str, date]]:
    """Return deduped (subject, code, rating, call_date) calls in the window."""
    since = ref - timedelta(days=lookback_days)
    if subject_type == "analyst":
        raw = session.execute(
            select(RatingEvent.analyst, RatingEvent.code, RatingEvent.rating, RatingEvent.trade_date)
            .where(RatingEvent.trade_date >= since, RatingEvent.analyst.isnot(None))
            .order_by(RatingEvent.trade_date)
        ).all()
    else:
        raw = session.execute(
            select(ResearchReport.org, ResearchReport.code, ResearchReport.rating,
                   ResearchReport.publish_date)
            .where(ResearchReport.publish_date >= since, ResearchReport.org.isnot(None))
            .order_by(ResearchReport.publish_date)
        ).all()

    seen: set[tuple[str, str]] = set()
    calls: list[tuple[str, str, str, date]] = []
    for subject, code, rating, call_date in raw:
        if subject_type == "analyst":
            names = [s.strip() for s in str(subject).split(",") if s.strip()]
        else:
            names = [str(subject).strip()] if subject else []
        for name in names:
            if (name, code) in seen:
                continue
            seen.add((name, code))  # earliest call per (subject, stock) wins
            if rating and call_date:
                calls.append((name, code, rating, call_date))
    return calls


def _load_benchmark(session: Session) -> tuple[list[date], dict[date, float | None]]:
    rows = session.execute(
        select(DailyQuote.trade_date, DailyQuote.close)
        .where(DailyQuote.code == BENCHMARK_CODE)
        .order_by(DailyQuote.trade_date)
    ).all()
    return [d for d, _c in rows], {d: c for d, c in rows}


def _load_closes(session: Session, codes: list[str]) -> dict[str, tuple[list[date], list[float | None]]]:
    out: dict[str, tuple[list[date], list[float | None]]] = {}
    for i in range(0, len(codes), 200):
        chunk = codes[i : i + 200]
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


def _evaluate(
    events: list[tuple[str, str, str, date]],
    closes: dict[str, tuple[list[date], list[float | None]]],
    bench: tuple[list[date], dict[date, float | None]],
    horizon: int,
) -> dict[str, dict[str, Any]]:
    bench_dates, bench_map = bench
    stats: dict[str, dict[str, Any]] = {}

    def add(subject: str, hit: bool) -> None:
        s = stats.setdefault(subject, {"hits": 0, "total": 0})
        s["total"] += 1
        if hit:
            s["hits"] += 1

    for subject, code, rating, call_date in events:
        direction = norm_rating(rating)
        if direction not in BULLISH and direction not in BEARISH:
            continue
        series = closes.get(code)
        if not series:
            continue
        dates, cs = series
        entry_idx = bisect_left(dates, call_date)      # first trading day >= call date
        exit_idx = entry_idx + horizon
        if entry_idx >= len(dates) or exit_idx >= len(dates):
            continue                                   # still within the forward window
        entry, exit_ = cs[entry_idx], cs[exit_idx]
        b_entry = _bench_close(bench_dates, bench_map, dates[entry_idx])
        b_exit = _bench_close(bench_dates, bench_map, dates[exit_idx])
        if None in (entry, exit_, b_entry, b_exit) or not entry or not b_entry:
            continue
        stock_ret = exit_ / entry - 1.0
        bench_ret = b_exit / b_entry - 1.0
        hit = stock_ret > bench_ret if direction in BULLISH else stock_ret < bench_ret
        add(subject, hit)

    for s in stats.values():
        r = s["hits"] / s["total"] if s["total"] else None
        s["hit_rate"] = round(r, 4) if r is not None else None
        s["net_skill"] = round(2 * r - 1, 4) if r is not None else None
    return stats


def _prev_net_skill(
    session: Session, period_type: str, subject_type: str, ref: date,
) -> dict[str, float]:
    """net_skill of the previous snapshot per subject (for 环比 delta)."""
    prev_key = session.scalar(
        select(func.max(AccuracySnapshot.period_key)).where(
            AccuracySnapshot.period_type == period_type,
            AccuracySnapshot.subject_type == subject_type,
            AccuracySnapshot.period_key < ref.isoformat(),
        )
    )
    if not prev_key:
        return {}
    rows = session.scalars(
        select(AccuracySnapshot).where(
            AccuracySnapshot.period_type == period_type,
            AccuracySnapshot.subject_type == subject_type,
            AccuracySnapshot.period_key == prev_key,
        )
    ).all()
    return {r.subject: r.net_skill for r in rows if r.net_skill is not None}


# ------------------------------ read path ------------------------------
def leaderboard(
    session: Session,
    horizon: int = 20,
    by: str = "org",
    min_events: int = DEFAULT_MIN_EVENTS,
    limit: int = 200,
) -> dict[str, Any]:
    """Snapshot leaderboard for the latest period of the given horizon."""
    period_type = f"h{horizon}"
    ref = session.scalar(
        select(func.max(AccuracySnapshot.period_key)).where(
            AccuracySnapshot.period_type == period_type,
            AccuracySnapshot.subject_type == by,
        )
    )
    if not ref:
        return {"ref": None, "rows": [], "summary": {}}

    rows = session.scalars(
        select(AccuracySnapshot).where(
            AccuracySnapshot.period_type == period_type,
            AccuracySnapshot.subject_type == by,
            AccuracySnapshot.period_key == ref,
            AccuracySnapshot.total >= max(1, min_events),
        ).order_by(desc(AccuracySnapshot.net_skill), desc(AccuracySnapshot.total))
        .limit(limit)
    ).all()

    data = [
        {
            "rank": i + 1,
            "subject": r.subject,
            "hits": r.hits,
            "total": r.total,
            "hit_rate": r.hit_rate,
            "net_skill": r.net_skill,
            "prev_delta": r.prev_delta,
        }
        for i, r in enumerate(rows)
    ]
    total_events = sum(r.total for r in rows)
    hits = sum(r.hits for r in rows)
    overall = hits / total_events if total_events else None
    return {
        "ref": ref,
        "horizon": horizon,
        "by": by,
        "min_events": min_events,
        "rows": data,
        "summary": {
            "subjects": len(data),
            "events": total_events,
            "hits": hits,
            "hit_rate": round(overall, 4) if overall is not None else None,
            "net_skill": round(2 * overall - 1, 4) if overall is not None else None,
        },
    }
