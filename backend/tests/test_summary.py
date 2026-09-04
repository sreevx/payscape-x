"""Tests for the Phase B dashboard summary (GET /api/v1/summary).

The summary must be computed by the EXACT Part 5 deterministic outcome
path over the seeded journeys (never a second outcome calculation), and
its numbers must match the dataset ground truth:

    scenario_instances (seed 42): NORMAL 70, PAYMENT_FAILED 15,
    DUPLICATE 10, DELAYED 10, INVENTORY 10, DELIVERY 10, REFUND 10,
    MISSING 5, CONTRADICTORY 5, COMPOUND 5   -> total 150

    engine outcome split: FULFILLED 90 (70 NORMAL + 10 DUPLICATE +
    10 DELAYED), FAILED 50 (15+10+10+10+5), UNVERIFIABLE 10 (5+5),
    AT_RISK 0

    payments: 120 CAPTURED + 10 REFUNDED (130 success) + 20 FAILED

These tests run on the standard in-memory SQLite engine used by the rest
of the suite; SQLite always takes the sequential scan path. The threaded
PostgreSQL path (one session per worker, input-order reassembly) is
exercised by `test_failures_scan.py`, which proves threaded == sequential
for the identical scan implementation, so it is not re-duplicated here on
a file-backed SQLite engine (unstable under concurrency in this test
environment). Determinism and full-dataset completeness are asserted
directly instead.
"""

import threading
import time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.main import create_app
from app.models import Payment, ScenarioInstance
from app.services import summary_service
from app.synthetic.generator import DatasetGenerator

EXPECTED_SCENARIOS = {
    "NORMAL_SUCCESS": 70,
    "PAYMENT_FAILED": 15,
    "DUPLICATE_WEBHOOK": 10,
    "DELAYED_WEBHOOK": 10,
    "INVENTORY_FAILURE": 10,
    "DELIVERY_FAILURE": 10,
    "REFUND_FLOW": 10,
    "MISSING_EVENT": 5,
    "CONTRADICTORY_EVENT": 5,
    "COMPOUND_FAILURE": 5,
}


@pytest.fixture(scope="module")
def summary_env():
    """In-memory SQLite engine + TestClient seeded with seed 42."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
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

    app = create_app()

    def override_get_db():
        db = factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as client:
        yield engine, factory, client
    Base.metadata.drop_all(engine)
    engine.dispose()


def _stringify(value):
    """Enum members and plain strings both normalize to their value."""
    return value.value if hasattr(value, "value") else value


def test_dataset_ground_truth_counts(summary_env):
    """The seeded dataset is the expected scenario + payment mix."""
    _engine, factory, _client = summary_env
    with factory() as session:
        scenario_counts = {
            _stringify(row[0]): row[1]
            for row in session.execute(
                select(ScenarioInstance.scenario_type, func.count(ScenarioInstance.id))
                .group_by(ScenarioInstance.scenario_type)
            )
        }
        payment_counts = {
            _stringify(row[0]): row[1]
            for row in session.execute(
                select(Payment.status, func.count(Payment.id)).group_by(Payment.status)
            )
        }
    assert scenario_counts == EXPECTED_SCENARIOS
    assert payment_counts == {
        "CAPTURED": 120,
        "FAILED": 20,
        "REFUNDED": 10,
    }


def test_summary_endpoint_returns_real_aggregates(summary_env):
    """GET /api/v1/summary returns the deterministic engine truth."""
    _engine, _factory, client = summary_env
    response = client.get("/api/v1/summary")
    assert response.status_code == 200
    body = response.json()

    assert body["total_transactions"] == 150
    # Payment lifecycle (direct table counts).
    assert body["payment_success_count"] == 130
    assert body["payment_failed_count"] == 20
    assert body["payment_pending_count"] == 0
    assert body["payment_success_rate"] == 86.7
    assert body["payment_failed_rate"] == 13.3
    # Deterministic outcome buckets (Part 5 engine over every journey).
    assert body["outcomes"] == {
        "fulfilled": 90,
        "at_risk": 0,
        "failed": 50,
        "unverifiable": 10,
    }
    assert body["fulfilled_rate"] == 60.0
    assert body["at_risk_rate"] == 0.0
    assert body["failed_rate"] == 33.3
    assert body["unverifiable_rate"] == 6.7
    assert "Deterministic outcome engine" in body["source"]
    assert body["computed_at"]


# ---------------------------------------------------------------------------
# Cache freshness semantics (PostgreSQL path)
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_summary_cache():
    """Isolate the module-level TTL cache between cache-behaviour tests."""
    summary_service._cache = {}
    summary_service._scan_inflight = None
    summary_service._refresh_inflight = False
    yield
    summary_service._cache = {}
    summary_service._scan_inflight = None
    summary_service._refresh_inflight = False


def test_cached_outcomes_memoized_within_ttl(monkeypatch):
    calls: list[int] = []

    def fake_scan(bind, ordered_instances):
        calls.append(1)
        return ["FULFILLED"]

    monkeypatch.setattr(summary_service, "_scan_parallel", fake_scan)
    first = summary_service._cached_outcomes(object(), [])
    second = summary_service._cached_outcomes(object(), [])
    assert first == second == ["FULFILLED"]
    # A fresh entry is served without re-running the scan.
    assert len(calls) == 1


def test_stale_outcomes_served_and_refreshed_in_background(monkeypatch):
    monkeypatch.setattr(
        summary_service, "_scan_parallel", lambda bind, ordered: ["FAILED"]
    )
    summary_service._cache = {
        "outcomes": {
            "at": time.monotonic() - summary_service._CACHE_TTL_SECONDS - 1,
            "outcomes": ["FULFILLED"],
        }
    }
    # An expired TTL never strands the request on the full scan: the stale
    # deterministic payload is returned immediately...
    value = summary_service._cached_outcomes(object(), [])
    assert value == ["FULFILLED"]
    # ...while one background thread recomputes and replaces the entry.
    deadline = time.monotonic() + 5.0
    refreshed = False
    while time.monotonic() < deadline:
        with summary_service._cache_lock:
            entry = summary_service._cache.get("outcomes")
            refreshed = (
                entry is not None and entry["outcomes"] == ["FAILED"]
            )
        if refreshed:
            break
        time.sleep(0.02)
    assert refreshed


def test_cold_callers_join_inflight_scan_without_duplicating(monkeypatch):
    def should_never_scan(bind, ordered_instances):
        raise AssertionError("a joining caller must not start its own scan")

    monkeypatch.setattr(summary_service, "_scan_parallel", should_never_scan)

    # Simulate a scan already running (the startup warm-up).
    inflight = threading.Event()
    summary_service._scan_inflight = inflight

    result: dict[str, object] = {}

    def joiner():
        result["value"] = summary_service._cached_outcomes(object(), [])

    thread = threading.Thread(target=joiner)
    thread.start()
    time.sleep(0.1)  # let the joiner reach the wait
    assert thread.is_alive()

    # The running scan completes and stores its deterministic result.
    with summary_service._cache_lock:
        summary_service._cache = {
            "outcomes": {"at": time.monotonic(), "outcomes": ["FAILED"]}
        }
        summary_service._scan_inflight = None
    inflight.set()
    thread.join(timeout=5.0)

    assert result["value"] == ["FAILED"]
    assert not thread.is_alive()


def test_summary_scan_is_deterministic_and_complete(summary_env):
    """The scan classifies every journey and repeats byte-identically.

    Runs the sequential scan (the SQLite path) twice over the full ordered
    instance set: results must cover all 150 journeys, repeat exactly, and
    reproduce the engine split asserted by the endpoint test.
    """
    engine, factory, _client = summary_env
    with factory() as session:
        instances = summary_service._ordered_instances(session)
        first = summary_service._scan_sequential(session, instances)
        second = summary_service._scan_sequential(session, instances)
    assert len(instances) == 150
    assert first == second
    assert len(first) == 150
    assert first.count("FULFILLED") == 90
    assert first.count("AT_RISK") == 0
    assert first.count("FAILED") == 50
    assert first.count("UNVERIFIABLE") == 10
    assert engine.dialect.name != "postgresql"  # sanity: tests use SQLite
