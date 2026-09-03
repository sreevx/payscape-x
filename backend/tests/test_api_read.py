"""Tests for the Part 2 read-only APIs.

Exercises /api/v1/transactions, /api/v1/events and /api/v1/scenarios
against a full deterministic dataset in an in-memory SQLite database.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base, get_db
from app.main import create_app
from app.synthetic.generator import DatasetGenerator


@pytest.fixture(scope="module")
def client():
    """TestClient bound to a fully seeded in-memory database."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with factory() as session:
        dataset = DatasetGenerator(seed=42).generate()
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
    with TestClient(app) as test_client:
        yield test_client
    engine.dispose()


# ---------------------------------------------------------------------------
# /transactions
# ---------------------------------------------------------------------------

def test_transactions_list_paginated(client):
    response = client.get("/api/v1/transactions")
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 150
    assert len(body["items"]) == 50  # default limit
    assert body["limit"] == 50
    assert body["offset"] == 0

    first = body["items"][0]
    for key in ("id", "order_id", "external_order_id", "customer_name",
                "customer_email", "amount", "currency", "payment_status",
                "provider", "method", "scenario_type", "scenario_slug",
                "event_count", "created_at"):
        assert key in first, key
    assert first["provider"] == "razorpay"


def test_transactions_pagination(client):
    page_one = client.get("/api/v1/transactions?limit=10&offset=0").json()
    page_two = client.get("/api/v1/transactions?limit=10&offset=10").json()
    assert len(page_one["items"]) == 10
    assert len(page_two["items"]) == 10
    ids_one = {item["id"] for item in page_one["items"]}
    ids_two = {item["id"] for item in page_two["items"]}
    assert ids_one.isdisjoint(ids_two)


def test_transactions_filter_by_scenario(client):
    body = client.get(
        "/api/v1/transactions?scenario=compound_failure"
    ).json()
    assert body["total"] == 5
    assert all(item["scenario_slug"] == "compound_failure"
               for item in body["items"])

    # Enum-value spelling also works.
    body = client.get(
        "/api/v1/transactions?scenario=NORMAL_SUCCESS"
    ).json()
    assert body["total"] == 70

    # Unknown scenario -> empty result, not an error.
    body = client.get("/api/v1/transactions?scenario=nonsense").json()
    assert body["total"] == 0
    assert body["items"] == []


def test_transactions_filter_by_payment_status(client):
    body = client.get("/api/v1/transactions?payment_status=REFUNDED").json()
    assert body["total"] == 10
    assert all(item["payment_status"] == "REFUNDED" for item in body["items"])

    # Scenario + status can be combined.
    body = client.get(
        "/api/v1/transactions?scenario=payment_failed&payment_status=FAILED"
    ).json()
    assert body["total"] == 15
    assert all(item["payment_status"] == "FAILED" for item in body["items"])


def test_transaction_detail_full_journey(client):
    listing = client.get("/api/v1/transactions?limit=1").json()
    transaction_id = listing["items"][0]["id"]

    response = client.get(f"/api/v1/transactions/{transaction_id}")
    assert response.status_code == 200
    detail = response.json()

    assert detail["id"] == transaction_id
    assert detail["provider"] == "razorpay"
    assert detail["scenario_slug"] is not None
    assert detail["customer_name"]
    # Events are returned chronologically with full context.
    events = detail["events"]
    assert events, "expected at least one event"
    stamps = [event["timestamp"] for event in events]
    assert stamps == sorted(stamps)
    event = events[0]
    for key in ("event_type", "source", "timestamp", "correlation_id",
                "idempotency_key", "payload"):
        assert key in event, key
    correlations = {event["correlation_id"] for event in events}
    assert len(correlations) == 1  # one journey, one correlation


def test_transaction_detail_invalid_ids(client):
    response = client.get("/api/v1/transactions/not-a-uuid")
    assert response.status_code == 404

    response = client.get(
        "/api/v1/transactions/00000000-0000-0000-0000-000000000000"
    )
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# /events
# ---------------------------------------------------------------------------

def test_events_list_paginated(client):
    body = client.get("/api/v1/events").json()
    assert body["total"] == 2170
    assert len(body["items"]) == 50
    item = body["items"][0]
    for key in ("id", "order_id", "external_order_id", "payment_id",
                "event_type", "source", "timestamp", "correlation_id",
                "idempotency_key", "payload"):
        assert key in item, key


def test_events_are_chronological(client):
    body = client.get("/api/v1/events?limit=200").json()
    stamps = [item["timestamp"] for item in body["items"]]
    assert stamps == sorted(stamps)


def test_events_filter_by_type_and_source(client):
    captured = client.get("/api/v1/events?event_type=PAYMENT_CAPTURED").json()
    assert captured["total"] == 135
    assert all(item["event_type"] == "PAYMENT_CAPTURED"
               for item in captured["items"])

    provider = client.get("/api/v1/events?source=PAYMENT_PROVIDER").json()
    assert provider["total"] == 615
    assert all(item["source"] == "PAYMENT_PROVIDER"
               for item in provider["items"])

    combined = client.get(
        "/api/v1/events?event_type=PAYMENT_CAPTURED&source=PAYMENT_PROVIDER"
    ).json()
    assert combined["total"] == 135


def test_events_filter_by_correlation_id(client):
    # Any event carries its journey correlation; fetch one and filter by it.
    sample = client.get("/api/v1/events?limit=1").json()["items"][0]
    correlation = sample["correlation_id"]

    body = client.get(f"/api/v1/events?correlation_id={correlation}").json()
    assert body["total"] > 0
    assert all(item["correlation_id"] == correlation for item in body["items"])


def test_events_bad_correlation_id_returns_empty(client):
    body = client.get(
        "/api/v1/events?correlation_id=not-a-uuid"
    ).json()
    assert body["total"] == 0
    assert body["items"] == []


# ---------------------------------------------------------------------------
# /scenarios
# ---------------------------------------------------------------------------

def test_scenarios_list_ten_types(client):
    body = client.get("/api/v1/scenarios").json()
    assert len(body) == 10
    slugs = {item["scenario_id"] for item in body}
    assert {
        "normal_success", "payment_failed", "duplicate_webhook",
        "delayed_webhook", "inventory_failure", "delivery_failure",
        "refund_flow", "missing_event", "contradictory_event",
        "compound_failure",
    } == slugs
    summary = next(item for item in body
                   if item["scenario_id"] == "normal_success")
    assert summary["transaction_count"] == 70
    assert summary["event_count"] == 70 * 17


def test_scenario_detail_with_transactions_and_timeline(client):
    response = client.get("/api/v1/scenarios/compound_failure")
    assert response.status_code == 200
    detail = response.json()
    assert detail["scenario_id"] == "compound_failure"
    assert detail["correlation_count"] == 5
    assert detail["event_count"] > 0
    assert len(detail["transactions"]) == 5

    transaction = detail["transactions"][0]
    for key in ("id", "order_id", "external_order_id", "customer_name",
                "amount", "currency", "payment_status"):
        assert key in transaction, key

    timeline = detail["timeline"]
    assert timeline
    stamps = [item["timestamp"] for item in timeline]
    assert stamps == sorted(stamps)
    # The compound chain is visible in the timeline.
    types = [item["event_type"] for item in timeline]
    assert "PAYMENT_CAPTURED" in types
    assert "CUSTOMER_COMPLAINT" in types
    assert types[-1] == "CUSTOMER_COMPLAINT"


def test_scenario_detail_unknown_id(client):
    response = client.get("/api/v1/scenarios/does_not_exist")
    assert response.status_code == 404


def test_normal_scenario_timeline_full_chain(client):
    detail = client.get("/api/v1/scenarios/normal_success").json()
    types = [item["event_type"] for item in detail["timeline"]]
    for expected in ("ORDER_CREATED", "PAYMENT_CAPTURED", "WEBHOOK_RECEIVED",
                     "ORDER_CONFIRMED", "INVENTORY_RESERVED",
                     "FULFILLMENT_CREATED", "SHIPMENT_CREATED",
                     "DELIVERY_COMPLETED"):
        assert expected in types, expected
