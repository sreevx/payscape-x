"""Shared helpers for Part 3 test suites.

Builds an in-memory SQLite engine seeded with the deterministic synthetic
dataset (same pattern as test_api_read, factored out so ingestion and
journey suites reuse it).
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.synthetic.generator import DatasetGenerator


def build_seeded_engine(seed: int = 42):
    """Create an in-memory engine with the full schema + seeded dataset.

    Returns (engine, session_factory).
    """
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with factory() as session:
        dataset = DatasetGenerator(seed).generate()
        session.add_all(
            [dataset.merchant]
            + dataset.customers
            + dataset.products
            + dataset.inventory_records
            + dataset.records
            + dataset.unified
            + dataset.instances
        )
        session.commit()
    return engine, factory