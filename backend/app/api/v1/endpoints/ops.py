"""运营数据 (ops) — ingestion control + observability.

GET stats are public (the UI shows freshness); triggering ingestion requires admin.
This is where the header "扫描/刷新" action lands (mirrors the reference's 扫描研报).
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.api.common import envelope
from app.core.db import get_db
from app.core.security import require_admin
from app.ingestion import scheduler
from app.ingestion.adapters import REGISTRY
from app.models.system import DataFreshness, IngestionLog

router = APIRouter(prefix="/api/ops", tags=["ops"])


@router.get("/feeds")
def feeds() -> dict:
    return envelope([
        {"name": a.name, "description": a.description, "per_symbol": a.per_symbol}
        for a in REGISTRY.values()
    ])


@router.get("/freshness")
def freshness(db: Session = Depends(get_db)) -> dict:
    rows = db.scalars(select(DataFreshness)).all()
    return envelope([{
        "feed": f.feed,
        "last_success_at": f.last_success_at.isoformat() if f.last_success_at else None,
        "latest_data_date": f.latest_data_date.isoformat() if f.latest_data_date else None,
        "rows_total": f.rows_total, "weeks_behind": f.weeks_behind, "note": f.note,
    } for f in rows])


@router.get("/ingestions")
def ingestions(limit: int = Query(default=50, ge=1, le=500), db: Session = Depends(get_db)) -> dict:
    rows = db.scalars(select(IngestionLog).order_by(desc(IngestionLog.started_at)).limit(limit)).all()
    return envelope([{
        "id": r.id, "feed": r.feed, "status": r.status,
        "started_at": r.started_at.isoformat() if r.started_at else None,
        "finished_at": r.finished_at.isoformat() if r.finished_at else None,
        "rows_seen": r.rows_seen, "rows_upserted": r.rows_upserted,
        "latency_ms": r.latency_ms, "error": r.error,
    } for r in rows])


@router.post("/ingest")
def trigger_ingest(
    scope: str = Query(default="all", description="all|bulk|per_symbol|<feed_name>"),
    universe: Optional[str] = Query(default=None),
    _admin=Depends(require_admin),
) -> dict:
    if scope in REGISTRY:  # single feed
        scheduler.trigger_now(scope="all")  # scheduler runs full pipeline; single-feed via CLI
        return envelope({"scheduled": True, "scope": scope,
                         "note": "single-feed runs are queued via the full pipeline; use CLI for one feed"})
    ok = scheduler.trigger_now(scope=scope, universe=universe)
    return envelope({"scheduled": ok, "scope": scope, "universe": universe})
