"""AI endpoints — RESERVED (Phase 3). Feature-flagged; return 501 until enabled.

The tables (AiSynthesis) and client stub (app/ai) exist so wiring the LLM later does not
require schema or routing changes. With FEATURE_AI=false these endpoints are inert.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.api.common import envelope
from app.core.config import settings

router = APIRouter(prefix="/api", tags=["ai"])


def _guard() -> None:
    if not settings.feature_ai:
        raise HTTPException(status_code=501, detail="AI 功能未启用 (Phase 3, FEATURE_AI=false)")


@router.post("/chat")
def chat() -> dict:
    _guard()
    from app.ai.chat import answer  # lazy

    return envelope(answer())


@router.post("/ai/synthesis")
def synthesis() -> dict:
    _guard()
    from app.ai.synthesis import synthesize  # lazy

    return envelope(synthesize())


@router.get("/ai/status")
def ai_status() -> dict:
    return envelope({"enabled": settings.feature_ai, "phase": 3,
                     "note": "AI综合研判/AI助手 deferred; interfaces reserved"})
