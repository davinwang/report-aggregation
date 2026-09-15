"""衍生品 (derivatives) — 股指期货基差 (Phase 2). 股指期权 lands in the next step."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.common import envelope, parse_date
from app.core.db import get_db
from app.services import basis as basis_svc

router = APIRouter(prefix="/api/derivatives", tags=["derivatives"])


@router.get("/futures/basis")
def futures_basis(
    variety: str = Query(default="IF", description="IF|IH|IC|IM"),
    days: int = Query(default=60, ge=5, le=250, description="history window (trading days)"),
    date_: Optional[str] = Query(default=None, alias="date", description="reference date YYYY-MM-DD"),
    db: Session = Depends(get_db),
) -> dict:
    """Term structure + front-month basis trend for one CFFEX equity-index variety."""
    v = (variety or "IF").upper()
    if v not in basis_svc.VARIETIES:
        v = "IF"
    ref = parse_date(date_)
    code, name = basis_svc.VARIETY_UNDERLYING[v]
    return envelope(
        {
            "varieties": basis_svc.VARIETIES,
            "variety": v,
            "underlying": {"code": code, "name": name},
            "termStructure": basis_svc.term_structure(db, v, ref),
            "history": basis_svc.history(db, v, days),
            "overview": basis_svc.overview(db, ref),
        },
        variety=v,
        days=days,
    )
