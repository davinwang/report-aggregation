"""Health & deep-health probe (analog of the reference's /health/deep).

Reports dependency availability, DB row counts, per-feed freshness, scheduler and SSE
status — so operators (and the UI 功能导航 page) can see data currency at a glance.
"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import get_db
from app.ingestion.akshare_client import akshare_version
from app.services.aggregation import freshness_map, latest_trade_date
from app.sse import bus

router = APIRouter(tags=["health"])

_COUNT_MODELS = [
    ("security", "app.models.security:Security"),
    ("daily_quote", "app.models.market:DailyQuote"),
    ("research_report", "app.models.research:ResearchReport"),
    ("rating_event", "app.models.research:RatingEvent"),
    ("financial_statement", "app.models.financial:FinancialStatement"),
    ("disclosure", "app.models.financial:Disclosure"),
    ("signal", "app.models.research:Signal"),
]


def _resolve(path: str):
    mod, cls = path.split(":")
    import importlib

    return getattr(importlib.import_module(mod), cls)


def _counts(session: Session) -> dict[str, int]:
    out: dict[str, int] = {}
    for label, path in _COUNT_MODELS:
        try:
            model = _resolve(path)
            out[label] = session.scalar(select(func.count()).select_from(model)) or 0
        except Exception:  # noqa: BLE001
            out[label] = 0
    return out


def _overall_status(checks: dict) -> str:
    if any(c.get("ok") is False for c in checks.values() if isinstance(c, dict) and "ok" in c):
        # degraded if a core feed is stale, but still "ok" if DB reachable
        return "degraded" if checks.get("database", {}).get("ok") else "down"
    return "ok"


@router.get("/health/deep")
@router.get("/api/health/deep")
def health_deep(db: Session = Depends(get_db)) -> dict:
    from app.ingestion import scheduler

    counts = _counts(db)
    ltd = latest_trade_date(db)
    weeks_behind = round((date.today() - ltd).days / 7.0, 2) if ltd else None
    ak_ver = akshare_version()
    checks = {
        "database": {"ok": True, "counts": counts, "latest_trade_date": ltd.isoformat() if ltd else None},
        "dependencies": {"ok": ak_ver is not None, "akshare": ak_ver, "fastapi": True, "pandas": True},
        "scheduler": {"ok": scheduler.is_running(), "enabled": settings.scheduler_enabled,
                      "jobs": scheduler.jobs_info()},
        "sse": {"ok": True, "subscribers": bus.subscriber_count()},
        "market_data": {"ok": ltd is not None, "latest": ltd.isoformat() if ltd else None,
                        "weeks_behind": weeks_behind},
        "feature_flags": {"ai": settings.feature_ai},
    }
    return {
        "status": _overall_status(checks),
        "app": settings.app_name,
        "env": settings.env,
        "universe": settings.universe,
        "checks": checks,
        "freshness": freshness_map(db),
    }


@router.get("/api/health")
def health() -> dict:
    return {"status": "ok", "app": settings.app_name}
