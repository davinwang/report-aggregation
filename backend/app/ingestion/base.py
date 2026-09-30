"""Adapter base class + FeedResult.

Every feed subclasses ``BaseAdapter`` and implements ``fetch`` → ``normalize`` →
``persist``. ``run()`` wraps that with retries/backoff, an ``IngestionLog`` row, a
``DataFreshness`` stamp, and an SSE progress event — so each adapter stays tiny and
all cross-cutting concerns live here.
"""
from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import get_logger
from app.ingestion import throttle
from app.ingestion.db_utils import bulk_upsert  # re-export for adapters
from app.models.base import utcnow
from app.models.system import DataFreshness, IngestionLog

logger = get_logger(__name__)


@dataclass
class FeedResult:
    feed: str
    status: str = "ok"                     # ok|error|partial|empty
    rows_seen: int = 0
    rows_upserted: int = 0
    started_at: Any | None = None
    finished_at: Any | None = None
    latency_ms: int = 0
    error: str | None = None
    latest_data_date: date | None = None
    detail: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "feed": self.feed,
            "status": self.status,
            "rows_seen": self.rows_seen,
            "rows_upserted": self.rows_upserted,
            "latency_ms": self.latency_ms,
            "error": self.error,
            "latest_data_date": self.latest_data_date.isoformat() if self.latest_data_date else None,
            "detail": self.detail,
        }


class BaseAdapter(ABC):
    #: unique feed name (used in logs, freshness, CLI --feed, SSE)
    name: str = "base"
    #: human description
    description: str = ""
    #: whether the feed iterates over a universe (per-symbol) vs a single bulk call
    per_symbol: bool = False

    # ---- to implement ----
    @abstractmethod
    def fetch(self, **kwargs) -> Any:
        """Call AkShare (via get_ak()) and return the raw frame/object."""

    def normalize(self, raw: Any, **kwargs) -> list[dict[str, Any]]:
        """Transform raw frame into a list of model-shaped dicts. Default: assume list."""
        if raw is None:
            return []
        if isinstance(raw, list):
            return raw
        return []

    @abstractmethod
    def persist(self, session: Session, rows: list[dict[str, Any]], **kwargs) -> int:
        """Write normalized rows; return count inserted+updated."""

    def latest_date(self, rows: list[dict[str, Any]]) -> date | None:
        """Best-effort newest data date in the batch (for freshness)."""
        for key in ("trade_date", "publish_date", "ann_date", "date"):
            vals = [r.get(key) for r in rows if isinstance(r.get(key), date)]
            if vals:
                return max(vals)
        return None

    # ---- orchestration ----
    def fetch_with_retry(self, **kwargs) -> Any:
        last_exc: Exception | None = None
        attempts = max(1, settings.akshare_max_retries)
        for i in range(attempts):
            throttle.default_throttle.wait()
            try:
                return self.fetch(**kwargs)
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                backoff = min(2**i, 8) + 0.1 * i
                logger.warning("[%s] fetch attempt %d/%d failed: %s (retry in %.1fs)",
                               self.name, i + 1, attempts, exc, backoff)
                if i < attempts - 1:
                    time.sleep(backoff)
        raise last_exc if last_exc else RuntimeError("fetch failed")

    def run(self, session: Session, **kwargs) -> FeedResult:
        started = utcnow()
        t0 = time.monotonic()
        log = IngestionLog(feed=self.name, started_at=started, status="running")
        session.add(log)
        session.flush()
        self._publish("ingest:start", {"feed": self.name})

        result = FeedResult(feed=self.name, started_at=started)
        try:
            raw = self.fetch_with_retry(**kwargs)
            rows = self.normalize(raw, **kwargs)
            result.rows_seen = len(rows)
            if rows:
                result.rows_upserted = self.persist(session, rows, **kwargs)
                result.latest_data_date = self.latest_date(rows)
            result.status = "ok" if rows else "empty"
            session.commit()
        except Exception as exc:  # noqa: BLE001
            session.rollback()
            result.status = "error"
            result.error = f"{type(exc).__name__}: {exc}"
            logger.exception("[%s] ingestion failed", self.name)
        finally:
            finished = utcnow()
            result.finished_at = finished
            result.latency_ms = int((time.monotonic() - t0) * 1000)
            self._finalize(session, log, result)
            self._invalidate_read_caches()
            self._publish("ingest:end", result.to_dict())
        return result

    def _invalidate_read_caches(self) -> None:
        """Drop cached read payloads so the next page load picks up the new data.

        Derived read endpoints (e.g. 全市场速览 matrix, 板块联动 beta) cache their
        computed payloads for a short TTL; ingestion finishing is the only event
        that changes their inputs, so clear here (any feed, any trigger: scheduler,
        CLI or API).
        """
        try:
            from app.core.cache import cache_clear  # lazy to avoid import cycle

            cache_clear()
        except Exception:  # noqa: BLE001 - cache failures must never fail ingestion
            pass

    def _finalize(self, session: Session, log: IngestionLog, result: FeedResult) -> None:
        try:
            log.status = result.status
            log.finished_at = result.finished_at
            log.rows_seen = result.rows_seen
            log.rows_upserted = result.rows_upserted
            log.latency_ms = result.latency_ms
            log.error = result.error
            if result.status in ("ok", "partial", "empty"):
                self._stamp_freshness(session, result)
            session.commit()
        except Exception:  # noqa: BLE001
            session.rollback()
            logger.exception("[%s] failed to finalize ingestion log", self.name)

    def _stamp_freshness(self, session: Session, result: FeedResult) -> None:
        fresh = session.scalar(select(DataFreshness).where(DataFreshness.feed == self.name))
        if fresh is None:
            fresh = DataFreshness(feed=self.name)
            session.add(fresh)
        fresh.last_success_at = result.finished_at
        if result.latest_data_date:
            fresh.latest_data_date = result.latest_data_date
        fresh.rows_total = (fresh.rows_total or 0) + result.rows_upserted
        if result.latest_data_date:
            delta_days = (utcnow().date() - result.latest_data_date).days
            fresh.weeks_behind = round(max(0, delta_days) / 7.0, 2)

    def _publish(self, event: str, data: dict) -> None:
        try:
            from app.sse.bus import publish  # lazy to avoid import cycle

            publish(event, data)
        except Exception:  # noqa: BLE001
            pass


class SymbolLoopAdapter(BaseAdapter):
    """Base for per-symbol feeds that iterate a universe.

    Subclasses implement ``fetch_symbol(code, **kwargs)`` and ``normalize_symbol(code,
    raw, **kwargs)``. ``fetch`` loops the universe with throttling and per-code error
    isolation (one bad symbol never aborts the batch); ``normalize`` flattens results.
    ``run(codes=[...])`` is invoked by the pipeline with a resolved universe.
    """

    per_symbol = True

    def fetch_symbol(self, code: str, **kwargs) -> Any:  # pragma: no cover - abstract
        raise NotImplementedError

    def normalize_symbol(self, code: str, raw: Any, **kwargs) -> list[dict[str, Any]]:  # pragma: no cover
        raise NotImplementedError

    def fetch(self, codes: list[str] | None = None, per_code_retries: int = 2,
              **kwargs) -> list[tuple[str, Any]]:
        codes = codes or []
        out: list[tuple[str, Any]] = []
        failures = 0
        for code in codes:
            raw = None
            for attempt in range(max(1, per_code_retries)):
                throttle.default_throttle.wait()
                try:
                    raw = self.fetch_symbol(code=code, **kwargs)
                    break
                except Exception as exc:  # noqa: BLE001
                    failures += 1
                    logger.debug("[%s] %s attempt %d failed: %s", self.name, code, attempt + 1, exc)
                    if attempt < per_code_retries - 1:
                        time.sleep(min(2**attempt, 4))
            if raw is not None:
                out.append((code, raw))
        if failures:
            logger.warning("[%s] %d symbol fetch(es) failed out of %d", self.name, failures, len(codes))
        return out

    def normalize(self, raw: Any, **kwargs) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for code, frame in raw or []:
            try:
                rows.extend(self.normalize_symbol(code, frame, **kwargs))
            except Exception as exc:  # noqa: BLE001
                logger.warning("[%s] normalize failed for %s: %s", self.name, code, exc)
        return rows


# Re-export for adapter convenience.
__all__ = ["BaseAdapter", "SymbolLoopAdapter", "FeedResult", "bulk_upsert"]
