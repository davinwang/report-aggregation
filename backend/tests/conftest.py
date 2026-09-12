"""Shared fixtures: in-memory DB session + fake akshare injection."""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401  (register all tables on Base.metadata)
from app.core.db import Base
from app.ingestion import akshare_client


@pytest.fixture()
def session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    s = Session()
    try:
        yield s
    finally:
        s.close()
        engine.dispose()


@pytest.fixture()
def fake_ak():
    """Inject a fake akshare module; tests set attributes on it. Reset after."""
    fake = SimpleNamespace(__version__="fake-test")
    akshare_client.set_fake_ak(fake)
    try:
        yield fake
    finally:
        akshare_client.set_fake_ak(None)
