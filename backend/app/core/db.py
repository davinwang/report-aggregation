"""SQLAlchemy 2.0 engine/session setup and declarative Base.

Design goals:
- SQLite only (zero-config, WAL mode for concurrent reads/writes).
- A single declarative ``Base`` with common naming convention so Alembic autogenerate
  produces stable constraint names.
- ``get_db`` FastAPI dependency yielding a scoped session.
"""
from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import MetaData, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# Deterministic constraint names -> cleaner migrations across SQLite/Postgres.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def _make_engine():
    url = settings.resolved_database_url()
    # SQLite WAL mode + relaxed synchronous for concurrent reads/writes (APScheduler + FastAPI).
    connect_args = {"check_same_thread": False, "timeout": 30}
    engine = create_engine(url, echo=False, future=True, connect_args=connect_args, pool_pre_ping=True)

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, _record):  # noqa: ANN001
        cursor = dbapi_connection.cursor()
        # Use DELETE journal mode for cross-platform compatibility
        # (WAL creates -wal/-shm files that break Docker bind mounts on Windows).
        cursor.execute("PRAGMA journal_mode=DELETE")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine


engine = _make_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency: yields a session and always closes it."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    """Transactional scope for scripts / ingestion jobs (commit on success, rollback on error)."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def init_db() -> None:
    """Create all tables + ensure hot-path indexes exist.

    Import models first so they register on Base.metadata. ``create_all`` only
    creates *missing* tables, so composite indexes added to existing deployments
    are created here explicitly (``IF NOT EXISTS`` — idempotent, one-time cost).

    For production use Alembic migrations (``alembic upgrade head``); this helper is
    a convenience for dev and is also exposed via ``python -m app.core.db --create-all``.
    """
    import app.models  # noqa: F401  (ensures all models are imported/registered)

    Base.metadata.create_all(bind=engine)
    _ensure_indexes()
    logger.info("Database initialized at %s", settings.resolved_database_url())


#: Indexes added after the table already existed on deployed databases.
#: Mirrors app/models/market.py; keep the two in sync when adding new ones.
_ENSURE_INDEXES: tuple[tuple[str, str], ...] = (
    ("ix_daily_quote_code_adj_date", "daily_quote (code, adjust, trade_date)"),
    ("ix_daily_quote_code_date", "daily_quote (code, trade_date)"),
    ("ix_daily_quote_adj_code_close", "daily_quote (adjust, code, close)"),
)


def _ensure_indexes() -> None:
    """Create read-path indexes on pre-existing tables (idempotent)."""
    import time

    with engine.begin() as conn:
        for name, target in _ENSURE_INDEXES:
            t0 = time.monotonic()
            try:
                conn.exec_driver_sql(f"CREATE INDEX IF NOT EXISTS {name} ON {target}")
            except Exception as exc:  # noqa: BLE001 - never block startup on an index
                logger.warning("Failed to ensure index %s: %s", name, exc)
            else:
                logger.info("Index %s ensured (%.1fs)", name, time.monotonic() - t0)


if __name__ == "__main__":
    import sys

    from app.core.logging import configure_logging

    configure_logging()
    if "--create-all" in sys.argv:
        init_db()
        print("Schema created.")
