"""Shared test fixtures — in-memory SQLite DB, seeded flights, FastAPI TestClient."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from sqlalchemy.pool import StaticPool

from api.db import Base, get_db
from api.main import app
from api.models import Booking, Flight  # noqa: F401
from api.seed import generate_flights

TEST_DATABASE_URL = "sqlite://"

# StaticPool ensures all connections share the single in-memory database.
_engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
_TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_engine)


def _override_get_db():
    db = _TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    Base.metadata.create_all(bind=_engine)
    # Seed 2 days of flights for speed
    with _TestingSessionLocal() as session:
        session.add_all(generate_flights(days=2))
        session.commit()
    yield
    Base.metadata.drop_all(bind=_engine)


@pytest.fixture
def db():
    """Raw DB session for direct ORM access in tests."""
    session = _TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client():
    """FastAPI test client wired to the test database."""
    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
