"""Provider-agnostic LLM client stub (Phase 3).

Configure via env when AI is enabled, e.g.:
    LLM_BASE_URL=https://api.openai.com/v1   (or any OpenAI-compatible / 国产大模型 gateway)
    LLM_API_KEY=...
    LLM_MODEL=...
The MVP never calls this; it raises so accidental use is obvious.
"""
from __future__ import annotations

import os
from typing import Any


class LLMNotConfigured(RuntimeError):
    pass


def chat_completion(messages: list[dict[str, str]], **kwargs: Any) -> str:
    base_url = os.getenv("LLM_BASE_URL")
    api_key = os.getenv("LLM_API_KEY")
    model = os.getenv("LLM_MODEL")
    if not (base_url and api_key and model):
        raise LLMNotConfigured("LLM_BASE_URL / LLM_API_KEY / LLM_MODEL not set (AI is Phase 3).")
    # Phase 3 will implement the actual OpenAI-compatible call here.
    raise NotImplementedError("AI chat is deferred to Phase 3.")
