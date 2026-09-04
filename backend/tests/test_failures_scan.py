"""Tests for the compound-failure dataset scan (Part 6).

The dataset list endpoint re-runs the deterministic Part 3-6 pipeline per
candidate transaction. On PostgreSQL the scan runs across a small thread
pool (one session/connection per worker) and is briefly memoized; other
engines (tests) keep the sequential single-session path. These tests
prove the threaded path returns exactly the same items as the sequential
path and that repeated scans are deterministic, using a file-backed
SQLite database (multiple connections are safe for reads there).
"""

import threading
import time

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


# ---------------------------------------------------------------------------
# Cache freshness semantics (PostgreSQL path)
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_failures_cache():
    """Isolate the module-level TTL cache between cache-behaviour tests."""
    failures_service._list_cache = {}
    failures_service._list_scan_inflight = None
    failures_service._list_refresh_inflight = False
    yield
    failures_service._list_cache = {}
    failures_service._list_scan_inflight = None
    failures_service._list_refresh_inflight = False


def test_cached_items_memoized_within_ttl(monkeypatch):
    calls: list[int] = []

    def fake_scan(bind, ordered_instances):
        calls.append(1)
        return ["detected-a"]

    monkeypatch.setattr(failures_service, "_scan_parallel", fake_scan)
    first = failures_service._cached_dataset_items(object(), [])
    second = failures_service._cached_dataset_items(object(), [])
    assert first == second == ["detected-a"]
    # A fresh entry is served without re-running the scan.
    assert len(calls) == 1


def test_stale_entry_served_and_refreshed_in_background(monkeypatch):
    monkeypatch.setattr(
        failures_service, "_scan_parallel", lambda bind, ordered: ["fresh"]
    )
    failures_service._list_cache = {
        "entry": {
            "at": time.monotonic()
            - failures_service._LIST_CACHE_TTL_SECONDS
            - 1,
            "items": ["old"],
        }
    }
    # An expired TTL never strands the request on the full scan: the stale
    # deterministic payload is returned immediately...
    value = failures_service._cached_dataset_items(object(), [])
    assert value == ["old"]
    # ...while one background thread recomputes and replaces the entry.
    deadline = time.monotonic() + 5.0
    refreshed = False
    while time.monotonic() < deadline:
        with failures_service._list_cache_lock:
            entry = failures_service._list_cache.get("entry")
            refreshed = entry is not None and entry["items"] == ["fresh"]
        if refreshed:
            break
        time.sleep(0.02)
    assert refreshed


def test_cold_callers_join_inflight_scan_without_duplicating(monkeypatch):
    def should_never_scan(bind, ordered_instances):
        raise AssertionError("a joining caller must not start its own scan")

    monkeypatch.setattr(failures_service, "_scan_parallel", should_never_scan)

    # Simulate a scan already running (the startup warm-up): the entry is
    # still empty and the in-flight event is set.
    inflight = threading.Event()
    failures_service._list_scan_inflight = inflight

    result: dict[str, object] = {}

    def joiner():
        result["value"] = failures_service._cached_dataset_items(object(), [])

    thread = threading.Thread(target=joiner)
    thread.start()
    time.sleep(0.1)  # let the joiner reach the wait
    assert thread.is_alive()

    # The running scan completes and stores its deterministic result.
    with failures_service._list_cache_lock:
        failures_service._list_cache = {
            "entry": {"at": time.monotonic(), "items": ["warm"]}
        }
        failures_service._list_scan_inflight = None
    inflight.set()
    thread.join(timeout=5.0)

    assert result["value"] == ["warm"]
    assert not thread.is_alive()
