"""Application configuration via pydantic-settings.

Reads from environment variables and an optional ``backend/.env`` file.
All tunables (DB URL, universe, ingestion throttling, feature flags) live here so
no other module hard-codes them.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/ directory (…/backend/app/core/config.py -> parents[2] == backend)
BACKEND_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ---- App ----
    app_name: str = "股票研报聚合平台"
    env: str = "dev"
    host: str = "0.0.0.0"
    port: int = 8000
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # ---- Database (SQLite only) ----
    database_url: str = "sqlite:///../data/srp.sqlite3"

    # ---- Cache (in-process TTL + pickle file; no external cache service) ----

    # ---- Auth (Phase 2) ----
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 720
    # Login is disabled by default: every request acts as a hardcoded admin so the
    # gated tools (/ops, /admin, /contrib) work without a login flow. Set true to
    # re-enable JWT auth.
    auth_enabled: bool = False

    # ---- Ingestion ----
    universe: str = "hs300"
    akshare_timeout: int = 30
    akshare_max_retries: int = 3
    akshare_throttle_seconds: float = 0.4
    scheduler_enabled: bool = True
    scheduler_cron: str = "30 15 * * 1-5"  # minute hour dom mon dow

    # ---- Feature flags ----
    feature_ai: bool = False

    # ---- Derived ----
    default_bars: int = Field(default=250, description="Default K-line bars for /api/quant/series")

    @field_validator("cors_origins")
    @classmethod
    def _strip_origins(cls, v: str) -> str:
        return v.strip()

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    def resolved_database_url(self) -> str:
        """Resolve a relative SQLite path (relative to backend/) to an absolute URL,
        ensuring the parent directory exists."""
        url = self.database_url
        if url.startswith("sqlite:///") and not url.startswith("sqlite:////"):
            rel = url[len("sqlite:///"):]
            p = (BACKEND_DIR / rel).resolve()
            p.parent.mkdir(parents=True, exist_ok=True)
            return f"sqlite:///{p.as_posix()}"
        return url

    @property
    def scheduler_cron_parts(self) -> dict[str, str]:
        """Parse a 5-field cron string into APScheduler CronTrigger kwargs."""
        parts = self.scheduler_cron.split()
        if len(parts) != 5:
            parts = ["30", "15", "*", "*", "1-5"]
        minute, hour, day, month, day_of_week = parts
        return {
            "minute": minute,
            "hour": hour,
            "day": day,
            "month": month,
            "day_of_week": day_of_week,
        }


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
