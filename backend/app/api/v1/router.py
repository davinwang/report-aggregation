"""Aggregate all v1 endpoint routers into a single APIRouter."""
from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.endpoints import (
    accuracy,
    admin,
    auth,
    chat,
    derivatives,
    financials,
    flow,
    health,
    linkage,
    market,
    meta,
    ops,
    quant,
    research,
    signals,
    stock,
    stream,
    weekly,
)

api_router = APIRouter()
for module in (health, meta, market, research, quant, financials, stock, derivatives, flow, signals, accuracy, weekly, linkage, stream, ops, admin, auth, chat):
    api_router.include_router(module.router)

__all__ = ["api_router"]
