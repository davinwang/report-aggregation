"""Period-window helpers (transform of the reference's 周四16:00 futures cycle).

For stocks the natural window is the trading week (Mon–Fri). ``resolve_window`` maps a
period token + optional reference date into an inclusive [start, end] date range and a
canonical ``week_key`` (Friday of that week) used across 周统计/准确率.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional


@dataclass
class Window:
    start: date
    end: date
    label: str
    week_key: str

    def to_dict(self) -> dict:
        return {
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "label": self.label,
            "week_key": self.week_key,
        }


def _friday(d: date) -> date:
    # weekday(): Mon=0 .. Sun=6 → move to Friday(4)
    return d + timedelta(days=(4 - d.weekday()))


def _monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


def resolve_window(period: str = "week", ref: Optional[date] = None) -> Window:
    ref = ref or date.today()
    p = (period or "week").lower()
    if p == "today":
        return Window(ref, ref, "今日", _friday(ref).isoformat())
    if p in ("week", "thisweek"):
        return Window(_monday(ref), _friday(ref), "本周", _friday(ref).isoformat())
    if p in ("twoweek", "2week", "twoweeks"):
        start = _monday(ref) - timedelta(days=7)
        return Window(start, _friday(ref), "近两周", _friday(ref).isoformat())
    if p == "month":
        start = ref.replace(day=1)
        return Window(start, ref, "本月", _friday(ref).isoformat())
    # fallback: last 7 days
    return Window(ref - timedelta(days=7), ref, "近7日", _friday(ref).isoformat())


def window_from_range(start: Optional[date], end: Optional[date], ref: Optional[date] = None) -> Window:
    ref = ref or date.today()
    s = start or _monday(ref)
    e = end or ref
    return Window(s, e, "自定义", _friday(e).isoformat())
