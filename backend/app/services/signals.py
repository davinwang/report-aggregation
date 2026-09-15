"""可操作信号 (actionable signals) — rule-based derivation, no LLM.

Computes ``Signal`` rows from ``research_report`` (东财个股研报):

* ``upgrade`` / ``downgrade`` — per (code, org), the latest rating vs the previous
  one inside the lookback window (``RATING_SCORE`` movement → 上调/下调).
* ``first`` — the institution's first-ever coverage of the code (its earliest
  report overall falls inside the window).
* ``consensus`` — ≥``MIN_ORGS`` institutions covered the code within
  ``CONSENSUS_DAYS`` and the latest stance per institution tilts bullish/bearish.

``refresh_signals`` recomputes the window and upserts the table; both the
``/signals`` page and 市场看板 (``aggregation._top_signals``) read from it.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Optional

from sqlalchemy import delete, desc, func, select
from sqlalchemy.orm import Session

from app.ingestion.base import bulk_upsert
from app.ingestion.normalizers import RATING_SCORE, norm_rating
from app.ingestion.secmap import security_id_map
from app.models.base import RatingDirection
from app.models.research import ResearchReport, Signal
from app.models.security import group_of

KINDS = ("upgrade", "downgrade", "first", "consensus")
MIN_ORGS = 3           # minimum institutions for a consensus signal
CONSENSUS_DAYS = 90
DEFAULT_LOOKBACK_DAYS = 180

_UP_STRENGTH = {RatingDirection.buy: "强", RatingDirection.overweight: "中"}
_DOWN_STRENGTH = {RatingDirection.sell: "强", RatingDirection.underweight: "中"}


# --------------------------- refresh (write path) ---------------------------
def refresh_signals(
    session: Session,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    consensus_days: int = CONSENSUS_DAYS,
) -> dict[str, Any]:
    """Recompute upgrade/downgrade/first/consensus signals for the window."""
    ref = session.scalar(select(func.max(ResearchReport.publish_date)))
    if ref is None:
        return {"ref": None, "total": 0}

    since = ref - timedelta(days=lookback_days)
    rows = session.execute(
        select(
            ResearchReport.code, ResearchReport.name, ResearchReport.org,
            ResearchReport.rating, ResearchReport.publish_date,
            ResearchReport.industry_group, ResearchReport.industry,
        )
        .where(ResearchReport.publish_date >= since, ResearchReport.org.isnot(None))
        .order_by(ResearchReport.code, ResearchReport.org, ResearchReport.publish_date)
    ).all()

    # Earliest report ever per (code, org) → detects first-time coverage.
    firsts = {
        (code, org): d
        for code, org, d in session.execute(
            select(ResearchReport.code, ResearchReport.org, func.min(ResearchReport.publish_date))
            .group_by(ResearchReport.code, ResearchReport.org)
        ).all()
    }

    name_of: dict[str, Optional[str]] = {}
    grp_of: dict[str, Optional[str]] = {}
    signals: list[dict[str, Any]] = []
    prev_map: dict[tuple[str, str], tuple[Optional[str], date]] = {}

    for code, name, org, rating, pub, grp, ind in rows:
        name_of.setdefault(code, name)
        # Canonical broad sector: security mapping first, then the report's own 行业.
        eff_grp = grp if grp and grp != "未分类" else group_of(ind or grp)
        if eff_grp:
            grp_of.setdefault(code, eff_grp)
        prev = prev_map.get((code, org))
        prev_map[(code, org)] = (rating, pub)
        if prev is None:
            # First report inside the window: 首次 only if it is the org's very first.
            if firsts.get((code, org)) == pub:
                direction = norm_rating(rating)
                signals.append({
                    "code": code, "name": name, "trade_date": pub, "kind": "first",
                    "direction": direction.value, "strength": _UP_STRENGTH.get(direction, "中"),
                    "score": float(RATING_SCORE[direction]),
                    "reason": f"{org}首次覆盖：{rating or '未评级'}",
                    "industry_group": eff_grp,
                    "sources_json": [{"org": org, "rating": rating}],
                })
            continue

        prev_rating, _prev_date = prev
        p, c = norm_rating(prev_rating), norm_rating(rating)
        if c == RatingDirection.unknown or p == RatingDirection.unknown:
            continue
        if RATING_SCORE[c] > RATING_SCORE[p]:
            kind, strength = "upgrade", _UP_STRENGTH.get(c, "弱")
            reason = f"{org}上调评级：{prev_rating} → {rating}"
        elif RATING_SCORE[c] < RATING_SCORE[p]:
            kind, strength = "downgrade", _DOWN_STRENGTH.get(c, "弱")
            reason = f"{org}下调评级：{prev_rating} → {rating}"
        else:
            continue
        signals.append({
            "code": code, "name": name, "trade_date": pub, "kind": kind,
            "direction": c.value, "strength": strength,
            "score": float(RATING_SCORE[c] - RATING_SCORE[p]),
            "reason": reason, "industry_group": eff_grp,
            "sources_json": [{"org": org, "prev": prev_rating, "rating": rating}],
        })

    signals.extend(_consensus_signals(session, ref, consensus_days, name_of, grp_of))

    # Deterministic rebuild of the window.
    session.execute(delete(Signal).where(Signal.trade_date >= since))
    id_map = security_id_map(session, [s["code"] for s in signals])
    for s in signals:
        s["security_id"] = id_map.get(s["code"])
    n = bulk_upsert(
        session, Signal, signals,
        key_fields=["code", "trade_date", "kind"],
        scope=select(Signal).where(Signal.trade_date >= since),
    )
    by_kind = {k: sum(1 for s in signals if s["kind"] == k) for k in KINDS}
    return {"ref": ref.isoformat(), "since": since.isoformat(), "total": n, **by_kind}


def _consensus_signals(
    session: Session, ref: date, consensus_days: int,
    name_of: dict[str, Optional[str]], grp_of: dict[str, Optional[str]],
) -> list[dict[str, Any]]:
    """一致评级 — latest stance per institution over the consensus window."""
    c_since = ref - timedelta(days=consensus_days)
    latest: dict[str, dict[str, Optional[str]]] = {}
    for code, org, rating in session.execute(
        select(ResearchReport.code, ResearchReport.org, ResearchReport.rating)
        .where(ResearchReport.publish_date >= c_since, ResearchReport.org.isnot(None))
        .order_by(ResearchReport.code, ResearchReport.org, ResearchReport.publish_date)
    ).all():
        latest.setdefault(code, {})[org] = rating

    out: list[dict[str, Any]] = []
    for code, orgs in latest.items():
        n = len(orgs)
        if n < MIN_ORGS:
            continue
        counts: dict[RatingDirection, int] = {}
        for rating in orgs.values():
            d = norm_rating(rating)
            if d != RatingDirection.unknown:
                counts[d] = counts.get(d, 0) + 1
        known = sum(counts.values())
        if not known:
            continue
        bull = (counts.get(RatingDirection.buy, 0) + counts.get(RatingDirection.overweight, 0)) / known
        bear = (counts.get(RatingDirection.sell, 0) + counts.get(RatingDirection.underweight, 0)) / known
        if bull >= 0.8:
            direction, strength = RatingDirection.buy.value, "强"
        elif bull >= 0.6:
            direction, strength = RatingDirection.buy.value, "中"
        elif bear >= 0.5:
            direction, strength = RatingDirection.neutral.value, "中"
        else:
            continue
        detail = "、".join(
            f"{label}{counts.get(d, 0)}"
            for d, label in ((RatingDirection.buy, "买入"), (RatingDirection.overweight, "增持"),
                             (RatingDirection.neutral, "中性"), (RatingDirection.underweight, "减持"),
                             (RatingDirection.sell, "卖出"))
        )
        out.append({
            "code": code, "name": name_of.get(code), "trade_date": ref, "kind": "consensus",
            "direction": direction, "strength": strength, "score": float(n),
            "reason": f"近{consensus_days}日{n}家机构覆盖：{detail}",
            "industry_group": grp_of.get(code),
            "sources_json": [{"orgs": n, **{d.value: c for d, c in counts.items()}}],
        })
    return out


# ---------------------------- read path (API) ----------------------------
def list_signals(
    session: Session,
    action: Optional[str] = None,
    industry: Optional[str] = None,
    days: int = 30,
    date_: Optional[date] = None,
    page: int = 1,
    size: int = 50,
) -> tuple[list[dict[str, Any]], int, Optional[date]]:
    where = []
    if date_:
        where.append(Signal.trade_date == date_)
    else:
        ref = session.scalar(select(func.max(Signal.trade_date)))
        if ref is None:
            return [], 0, None
        date_ = ref
        where.append(Signal.trade_date >= ref - timedelta(days=max(1, days)))
    if action in KINDS:
        where.append(Signal.kind == action)
    if industry:
        where.append(Signal.industry_group == industry)

    total = session.scalar(select(func.count()).select_from(Signal).where(*where)) or 0
    rows = session.scalars(
        select(Signal).where(*where)
        .order_by(desc(Signal.trade_date), desc(Signal.score), Signal.code)
        .offset((page - 1) * size).limit(size)
    ).all()
    return [
        {
            "id": r.id, "code": r.code, "name": r.name,
            "trade_date": r.trade_date.isoformat(),
            "kind": r.kind, "direction": r.direction, "strength": r.strength,
            "score": r.score, "reason": r.reason, "industry_group": r.industry_group,
            "sources": r.sources_json,
        }
        for r in rows
    ], total, date_


def summary(session: Session, days: int = 30) -> dict[str, Any]:
    """Headline counts for the /signals stat cards."""
    ref = session.scalar(select(func.max(Signal.trade_date)))
    if ref is None:
        return {"ref": None, "days": days, "counts": {}, "industries": []}
    since = ref - timedelta(days=max(1, days))
    counts = {
        kind: n
        for kind, n in session.execute(
            select(Signal.kind, func.count())
            .where(Signal.trade_date >= since)
            .group_by(Signal.kind)
        ).all()
    }
    industries = session.execute(
        select(Signal.industry_group, func.count())
        .where(Signal.trade_date >= since, Signal.industry_group.isnot(None))
        .group_by(Signal.industry_group)
        .order_by(desc(func.count())).limit(10)
    ).all()
    return {
        "ref": ref.isoformat(),
        "days": days,
        "counts": {k: counts.get(k, 0) for k in KINDS},
        "total": sum(counts.values()),
        "industries": [{"industry": i, "count": c} for i, c in industries],
    }
