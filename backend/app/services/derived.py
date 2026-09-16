"""Derived read-model refresh — signals / accuracy / weekly rebuilds.

``Signal``, ``AccuracySnapshot`` and ``WeeklyStat`` are *derived* tables: they are
recomputed from ``research_report`` (+ ``DailyQuote`` for accuracy) rather than
ingested from AkShare. Nothing in the pipeline writes them, so they must be
refreshed explicitly after the feeds they depend on change — otherwise the
可操作信号 / 研报准确率 / 周统计 pages silently go empty after a fresh deploy or
until someone clicks 重算 on each page.

``refresh_derived`` is called by the scheduler after the ``daily_evening`` group
(ratings/reports landed) and by ``all``-scope runs and the startup bootstrap, so
the pages stay populated without manual action. Each step is isolated: a failing
step is logged and skipped so the rest still run.
"""
from __future__ import annotations

from typing import Any, Optional

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.services import accuracy as accuracy_svc
from app.services import signals as signals_svc
from app.services import weekly as weekly_svc

logger = get_logger(__name__)


def refresh_derived(session: Session, accuracy_lookback_days: int = 180) -> dict[str, Any]:
    """Rebuild signals + weekly stats + accuracy snapshots from stored reports.

    Order matters only for readability — each step reads ``research_report``
    independently. Returns one stats dict per step (or ``{"error": ...}`` when
    that step raised, so one bad derivation never blocks the others).
    """
    out: dict[str, Any] = {}
    try:
        out["signals"] = signals_svc.refresh_signals(session)
    except Exception as exc:  # noqa: BLE001 - keep the remaining steps running
        session.rollback()
        logger.exception("Derived refresh: signals failed")
        out["signals"] = {"error": f"{type(exc).__name__}: {exc}"}

    try:
        out["weekly"] = weekly_svc.refresh_weekly(session)
    except Exception as exc:  # noqa: BLE001
        session.rollback()
        logger.exception("Derived refresh: weekly failed")
        out["weekly"] = {"error": f"{type(exc).__name__}: {exc}"}

    # Accuracy needs forward returns: h20/h60 × org/analyst. Snapshots for a
    # given as-of date are only meaningful once ``horizon`` trading days have
    # passed, so this recomputes the *current* window every run (cheap: reads
    # stored quotes only) and upserts.
    acc: dict[str, Any] = {}
    for horizon in accuracy_svc.HORIZONS:
        for subject_type in ("org", "analyst"):
            try:
                acc[f"h{horizon}_{subject_type}"] = accuracy_svc.compute_accuracy(
                    session, horizon=horizon, lookback_days=accuracy_lookback_days,
                    subject_type=subject_type,
                )
            except Exception as exc:  # noqa: BLE001
                session.rollback()
                logger.exception("Derived refresh: accuracy h%d/%s failed", horizon, subject_type)
                acc[f"h{horizon}_{subject_type}"] = {"error": f"{type(exc).__name__}: {exc}"}
    out["accuracy"] = acc
    return out
