"""Shared test fixtures.

Tests run against an in-memory SQLite database so the suite needs no live
PostgreSQL. Production runs PostgreSQL; the schema is portable (UUID, JSON
with a JSONB variant on PostgreSQL).
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base


@pytest.fixture()
def db_engine():
    """In-memory SQLite engine with the full PAYSCAPE-X schema."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture()
def db_session_factory(db_engine):
    """Session factory bound to the test engine."""
    return sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)