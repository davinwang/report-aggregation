"""研报准确率 (rating accuracy) — org/analyst hit-rate & net-skill leaderboard (Phase 2).

``POST /refresh`` evaluates stored rating calls against forward returns (20/60
trading days vs 沪深300) and writes ``AccuracySnapshot`` rows; the read endpoint
serves the leaderboard. Rule-based, no LLM.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.common import envelope
from app.core.db import get_db
from app.services import accuracy as accuracy_svc

router = APIRouter(prefix="/api/accuracy", tags=["accuracy"])


@router.get("/leaderboard")
def leaderboard(
    horizon: int = Query(default=20, description="forward window in trading days (20|60)"),
    by: str = Query(default="org", description="org|analyst"),
    min_events: int = Query(default=5, ge=1, le=100, description="minimum evaluated calls"),
    limit: int = Query(default=200, ge=5, le=500),
    db: Session = Depends(get_db),
) -> dict:
    return envelope(accuracy_svc.leaderboard(db, horizon=horizon, by=by, min_events=min_events, limit=limit))


@router.post("/refresh")
def refresh(
    horizon: int = Query(default=0, ge=0, le=60, description="0 = compute 20 & 60"),
    lookback_days: int = Query(default=180, ge=30, le=730),
    db: Session = Depends(get_db),
) -> dict:
    """Recompute accuracy snapshots from stored reports + daily quotes."""
    horizons = accuracy_svc.HORIZONS if horizon == 0 else (horizon,)
    out = []
    for h in horizons:
        for subject_type in ("org", "analyst"):
            out.append(accuracy_svc.compute_accuracy(
                db, horizon=h, lookback_days=lookback_days, subject_type=subject_type,
            ))
    db.commit()
    return envelope(out)
