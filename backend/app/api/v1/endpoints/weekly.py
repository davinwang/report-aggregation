"""周统计 (weekly statistics) — 机构×行业 matrix + 友商报告与活动 (Phase 2)."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.common import envelope
from app.core.db import get_db
from app.services import weekly as weekly_svc

router = APIRouter(prefix="/api/weekly", tags=["weekly"])


@router.get("/weeks")
def weeks(
    limit: int = Query(default=26, ge=1, le=104),
    db: Session = Depends(get_db),
) -> dict:
    """Available week keys (week-ending Sundays) for the selector."""
    return envelope(weekly_svc.weeks(db, limit))


@router.get("/matrix")
def matrix(
    week: Optional[str] = Query(default=None, description="week-ending date YYYY-MM-DD"),
    db: Session = Depends(get_db),
) -> dict:
    """Tab2 — 机构×行业 report-count matrix for one week."""
    return envelope(weekly_svc.matrix(db, week))


@router.get("/peer")
def peer(
    period: Optional[str] = Query(default=None, description="period key YYYY-MM-DD"),
    db: Session = Depends(get_db),
) -> dict:
    """Tab1 — 友商报告与活动 (upload-driven; upload flow arrives in Phase 3)."""
    return envelope(weekly_svc.peer(db, period))


@router.post("/refresh")
def refresh(
    weeks_back: int = Query(default=12, ge=1, le=52),
    db: Session = Depends(get_db),
) -> dict:
    """Recompute the WeeklyStat matrix from stored reports."""
    stats = weekly_svc.refresh_weekly(db, weeks_back=weeks_back)
    db.commit()
    return envelope(stats)
