"""Aggregate all v1 endpoint routers into a single APIRouter."""
from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.endpoints import (
    accuracy,
    auth,
    chat,
    derivatives,
    financials,
    flow,
    health,
    linkage,
    market,
    meta,
    news,
    ops,
    pool,
    quant,
    research,
    signals,
    stock,
    stream,
    weekly,
)

api_router = APIRouter()
for module in (health, meta, market, research, news, quant, financials, stock, derivatives, flow,
               signals, pool, accuracy, weekly, linkage, stream, ops, auth, chat):
    api_router.include_router(module.router)

__all__ = ["api_router"]
