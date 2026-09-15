"""Aggregate all v1 endpoint routers into a single APIRouter."""
from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.endpoints import (
    auth,
    chat,
    derivatives,
    financials,
    health,
    market,
    meta,
    ops,
    quant,
    research,
    stock,
    stream,
)

api_router = APIRouter()
for module in (health, meta, market, research, quant, financials, stock, derivatives, stream, ops, auth, chat):
    api_router.include_router(module.router)

__all__ = ["api_router"]
