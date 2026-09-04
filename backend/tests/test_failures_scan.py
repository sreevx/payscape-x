"""Tests for the compound-failure dataset scan (Part 6).

The dataset list endpoint re-runs the deterministic Part 3-6 pipeline per
candidate transaction. On PostgreSQL the scan runs across a small thread
pool (one session/connection per worker) and is briefly memoized; other
engines (tests) keep the sequential single-session path. These tests
prove the threaded path returns exactly the same items as the sequential
path and that repeated scans are deterministic, using a file-backed
SQLite database (multiple connections are safe for reads there).
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.services import failures_service
from app.synthetic.generator import DatasetGenerator


@pytest.fixture(scope="module")
def scan_engine(tmp_path_factory):
    """File-backed SQLite engine seeded with the deterministic dataset."""
    path = (tmp_path_factory.mktemp("scan") / "seed42.db").as_posix()
    engine = create_engine(
        f"sqlite:///{path}", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with factory() as session:
        dataset = DatasetGenerator(42).generate()
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
    return engine


def _dumps(items):
    return [item.model_dump() for item in items]


def test_scan_has_candidates(scan_engine):
    factory = sessionmaker(bind=scan_engine, autoflush=False, expire_on_commit=False)
    with factory() as session:
        ordered = failures_service._marker_ordered_instances(session)
    assert len(ordered) > 0


def test_parallel_scan_matches_sequential(scan_engine):
    factory = sessionmaker(bind=scan_engine, autoflush=False, expire_on_commit=False)
    with factory() as session:
        ordered = failures_service._marker_ordered_instances(session)
        sequential = failures_service._scan_sequential(session, ordered)
    parallel = failures_service._scan_parallel(scan_engine, ordered)

    assert len(parallel) > 0
    # Same detected set, same order (results reassembled by input order).
    assert _dumps(parallel) == _dumps(sequential)
    # Seed 42: 10 inventory + 10 delivery + 5 compound failures detected.
    assert len(parallel) == 25


def test_parallel_scan_deterministic(scan_engine):
    factory = sessionmaker(bind=scan_engine, autoflush=False, expire_on_commit=False)
    with factory() as session:
        ordered = failures_service._marker_ordered_instances(session)
    first = failures_service._scan_parallel(scan_engine, ordered)
    second = failures_service._scan_parallel(scan_engine, ordered)
    assert _dumps(first) == _dumps(second)
