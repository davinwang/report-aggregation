"""周统计 (weekly statistics) — 机构×行业矩阵 aggregation (Tab2 of /weekly).

Derived from ``research_report``: per ISO week (week-ending Sunday) and per
institution, count reports and their distribution across the canonical industry
groups. Materialized into ``WeeklyStat`` by ``refresh_weekly`` so the page reads
a pre-aggregated matrix. Tab1 (友商报告与活动) reads ``PeerActivity``, which is
populated by the upload flow (deferred to Phase 3).
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Optional

from sqlalchemy import delete, desc, func, select
from sqlalchemy.orm import Session

from app.models.research import PeerActivity, ResearchReport, WeeklyStat
from app.models.security import group_of

DEFAULT_WEEKS_BACK = 12


def week_end(d: date) -> date:
    """ISO week end (Sunday) for the given date — the week key."""
    return d + timedelta(days=6 - d.weekday())


# ------------------------------ write path ------------------------------
def refresh_weekly(session: Session, weeks_back: int = DEFAULT_WEEKS_BACK) -> dict[str, Any]:
    """Recompute WeeklyStat (org × industry-group counts) for recent weeks."""
    ref = session.scalar(select(func.max(ResearchReport.publish_date)))
    if ref is None:
        return {"ref": None, "weeks": 0, "orgs": 0}

    start = week_end(ref) - timedelta(weeks=weeks_back)
    rows = session.execute(
        select(ResearchReport.org, ResearchReport.industry, ResearchReport.publish_date)
        .where(ResearchReport.publish_date >= start, ResearchReport.org.isnot(None))
    ).all()

    agg: dict[tuple[str, str], dict[str, Any]] = {}
    for org, industry, pub in rows:
        if not org:
            continue
        key = (week_end(pub).isoformat(), org)
        entry = agg.setdefault(key, {"total": 0, "by_group": {}})
        entry["total"] += 1
        grp = group_of(industry)
        entry["by_group"][grp] = entry["by_group"].get(grp, 0) + 1

    # Deterministic rebuild of the range.
    session.execute(delete(WeeklyStat).where(WeeklyStat.week_key >= start.isoformat()))
    for (wk, org), entry in agg.items():
        session.add(WeeklyStat(
            week_key=wk, org=org, total=entry["total"], by_group_json=entry["by_group"],
        ))
    session.flush()
    return {
        "ref": ref.isoformat(),
        "weeks": len({k[0] for k in agg}),
        "orgs": len({k[1] for k in agg}),
        "rows": len(agg),
    }


# ------------------------------ read path ------------------------------
def weeks(session: Session, limit: int = 26) -> list[dict[str, Any]]:
    rows = session.execute(
        select(WeeklyStat.week_key, func.count(), func.sum(WeeklyStat.total))
        .group_by(WeeklyStat.week_key)
        .order_by(desc(WeeklyStat.week_key))
        .limit(limit)
    ).all()
    return [{"week_key": wk, "orgs": n, "reports": int(total or 0)} for wk, n, total in rows]


def matrix(session: Session, week_key: Optional[str] = None) -> dict[str, Any]:
    """机构×行业 matrix for one week (defaults to the latest *completed* week)."""
    week_list = weeks(session)
    if not week_key and week_list:
        today_iso = date.today().isoformat()
        complete = [w for w in week_list if w["week_key"] <= today_iso]
        week_key = (complete or week_list)[0]["week_key"]
    if not week_key:
        return {"week_key": None, "weeks": [], "groups": [], "orgs": [], "group_totals": {}}

    rows = session.scalars(
        select(WeeklyStat).where(WeeklyStat.week_key == week_key).order_by(desc(WeeklyStat.total))
    ).all()

    groups: list[str] = []
    for r in rows:
        for g in (r.by_group_json or {}):
            if g not in groups:
                groups.append(g)
    group_totals = {g: sum((r.by_group_json or {}).get(g, 0) for r in rows) for g in groups}
    groups.sort(key=lambda g: group_totals.get(g, 0), reverse=True)

    return {
        "week_key": week_key,
        "weeks": week_list,
        "groups": groups,
        "group_totals": group_totals,
        "orgs": [
            {"org": r.org, "total": r.total, "by_group": r.by_group_json or {}}
            for r in rows
        ],
    }


def peer(session: Session, period_key: Optional[str] = None) -> dict[str, Any]:
    """Tab1 友商报告与活动 — uploaded rows (upload flow arrives in Phase 3)."""
    periods = [
        p for (p,) in session.execute(
            select(PeerActivity.period_key).distinct().order_by(desc(PeerActivity.period_key))
        ).all()
    ]
    if not period_key:
        period_key = periods[0] if periods else None
    rows: list[dict[str, Any]] = []
    if period_key:
        rows = [
            {
                "id": r.id, "kind": r.kind, "industry_group": r.industry_group,
                "source": r.source, "title": r.title, "covered_by_us": r.covered_by_us,
                "url": r.url, "uploaded_by": r.uploaded_by,
            }
            for r in session.scalars(
                select(PeerActivity).where(PeerActivity.period_key == period_key)
                .order_by(PeerActivity.kind, PeerActivity.industry_group)
            ).all()
        ]
    return {"period_key": period_key, "periods": periods, "rows": rows}
