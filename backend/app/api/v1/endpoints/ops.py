"""运营数据 (ops) — ingestion control + observability.

GET stats are public (the UI shows freshness); triggering ingestion requires admin.
This is where the header "扫描/刷新" action lands.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.api.common import envelope
from app.core.config import settings
from app.core.db import get_db
from app.core.security import require_admin
from app.ingestion import scheduler
from app.ingestion.adapters import FEED_GROUP_OF, REGISTRY
from app.models.system import DataFreshness, IngestionLog

router = APIRouter(prefix="/api/ops", tags=["ops"])


@router.get("/feeds")
def feeds() -> dict:
    return envelope([
        {"name": a.name, "description": a.description, "per_symbol": a.per_symbol,
         "groups": FEED_GROUP_OF.get(a.name, [])}
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


@router.get("/jobs")
def jobs() -> dict:
    """Scheduled ingestion jobs (id, cron trigger, next run time)."""
    return envelope(scheduler.jobs_info())


@router.get("/mcp")
def mcp_status() -> dict:
    """MCP tool outlet status — endpoint path, token requirement, tool registry."""
    tool_names: list[str] = []
    if settings.feature_mcp:
        try:
            from app.mcp import tools as mcp_tools  # lazy: tools module has no SDK dependency

            tool_names = list(mcp_tools.__all__)
        except Exception:  # noqa: BLE001 - status must not fail the request
            tool_names = []
    return envelope({
        "enabled": settings.feature_mcp,
        "path": settings.mcp_path,
        "token_required": bool(settings.mcp_token),
        "tools": tool_names,
        "client_hint": (
            "Streamable HTTP MCP. Claude Code: "
            "claude mcp add --transport http srp <base_url><path>/ "
            '--header "Authorization: Bearer <MCP_TOKEN>"'
        ),
    })


@router.post("/ingest")
def trigger_ingest(
    scope: str = Query(default="all", description="frequency group | all|bulk|per_symbol | <feed_name>"),
    universe: str | None = Query(default=None),
    _admin=Depends(require_admin),
) -> dict:
    if scope not in scheduler.VALID_SCOPES:
        raise HTTPException(status_code=400, detail={
            "message": f"unknown scope '{scope}'",
            "valid": sorted(scheduler.VALID_SCOPES),
        })
    ok = scheduler.trigger_now(scope=scope, universe=universe)
    return envelope({"scheduled": ok, "scope": scope, "universe": universe})
