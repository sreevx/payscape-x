"""Database wiring: engine, session factory, declarative base.

The engine is created lazily so the application can start (and /health can
report) even when PostgreSQL is unreachable. Tests swap `get_engine` with an
in-memory SQLite engine.
"""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings

_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


class Base(DeclarativeBase):
    """Declarative base for all PAYSCAPE-X ORM models."""


def get_engine() -> Engine:
    """Return the lazily-created SQLAlchemy engine for the configured URL."""
    global _engine
    if _engine is None:
        settings = get_settings()
        # Short connect timeout so health checks fail fast when the DB is down.
        connect_args: dict[str, object] = {}
        if settings.database_url.startswith("postgresql"):
            # Keep the health probe fast: psycopg tries each host address
            # sequentially, so 1s per host stays well under the client
            # timeout while PostgreSQL is down.
            connect_args["connect_timeout"] = 1
        _engine = create_engine(
            settings.database_url,
            pool_pre_ping=True,
            connect_args=connect_args,
        )
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    """Return the lazily-created session factory bound to the engine."""
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(
            bind=get_engine(),
            autoflush=False,
            expire_on_commit=False,
        )
    return _session_factory


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency yielding a database session."""
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()