"""Tests for the Part 3 journey API endpoints.

Exercises /api/v1/journeys, /api/v1/journeys/{id}/graph and
/api/v1/journeys/{id}/integrity against a fully seeded in-memory database.
"""

import pytest
from fastapi.testclient import TestClient

from app.core.database import get_db
from app.main import create_app
from tests.seed_helpers import build_seeded_engine


@pytest.fixture(scope="module")
def client():
    """TestClient bound to a fully seeded in-memory database."""
    engine, factory = build_seeded_engine()
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


def _transaction_id(client, scenario_slug: str, index: int = 0) -> str:
    body = client.get(
        f"/api/v1/transactions?scenario={scenario_slug}&limit=200"
    ).json()
    return body["items"][index]["id"]


# ---------------------------------------------------------------------------
# /journeys/{transaction_id}
# ---------------------------------------------------------------------------

def test_journey_full_response_shape(client):
    transaction_id = _transaction_id(client, "normal_success")
    response = client.get(f"/api/v1/journeys/{transaction_id}")
    assert response.status_code == 200
    body = response.json()
    for key in ("transaction_id", "order_id", "payment_id", "correlation_id",
                "events", "graph", "integrity"):
        assert key in body, key
    assert body["transaction_id"] == transaction_id
    assert body["events"]
    # Events are chronological with full per-event context.
    stamps = [event["timestamp"] for event in body["events"]]
    assert stamps == sorted(stamps)
    event = body["events"][0]
    for key in ("id", "order_id", "payment_id", "event_type", "source",
                "timestamp", "correlation_id", "idempotency_key", "payload",
                "ingestion_position", "is_duplicate", "is_unknown", "is_orphan"):
        assert key in event, key
    # Graph section.
    for key in ("transaction_id", "correlation_id", "layout", "nodes", "edges"):
        assert key in body["graph"], key
    # Integrity section.
    for key in ("total_events", "linked_events", "orphan_count",
                "duplicate_count", "unknown_count", "delayed_count",
                "out_of_order_count", "first_event_at", "last_event_at",
                "duration_seconds", "missing_expected_event_candidates",
                "contradictions", "duplicates", "out_of_order_events",
                "delayed_events", "unknown_events", "orphan_events"):
        assert key in body["integrity"], key


def test_journey_unknown_and_invalid_ids(client):
    assert client.get("/api/v1/journeys/not-a-uuid").status_code == 404
    assert client.get(
        "/api/v1/journeys/00000000-0000-0000-0000-000000000000"
    ).status_code == 404


def test_journey_deterministic_across_calls(client):
    transaction_id = _transaction_id(client, "compound_failure")
    first = client.get(f"/api/v1/journeys/{transaction_id}").json()
    second = client.get(f"/api/v1/journeys/{transaction_id}").json()
    assert first == second


# ---------------------------------------------------------------------------
# /journeys/{transaction_id}/graph
# ---------------------------------------------------------------------------

def test_graph_endpoint(client):
    transaction_id = _transaction_id(client, "normal_success")
    response = client.get(f"/api/v1/journeys/{transaction_id}/graph")
    assert response.status_code == 200
    body = response.json()
    assert body["layout"] == "deterministic_linear"
    assert body["nodes"]
    assert body["edges"]
    node_ids = {node["id"] for node in body["nodes"]}
    for edge in body["edges"]:
        assert edge["source"] in node_ids
        assert edge["target"] in node_ids
        assert edge["relationship_type"]
        assert edge["rule_id"]
        assert edge["reason"]
    assert client.get("/api/v1/journeys/not-a-uuid/graph").status_code == 404


def test_graph_compound_failure_nodes_cover_chain(client):
    transaction_id = _transaction_id(client, "compound_failure")
    body = client.get(f"/api/v1/journeys/{transaction_id}/graph").json()
    labels = {node["event_type"] for node in body["nodes"] if node["kind"] == "event"}
    for expected in ("PAYMENT_CAPTURED", "WEBHOOK_DELAYED", "ORDER_NOT_CONFIRMED",
                     "INVENTORY_RESERVATION_EXPIRED", "INVENTORY_OUT_OF_STOCK",
                     "NO_FULFILLMENT", "CUSTOMER_COMPLAINT"):
        assert expected in labels, expected


# ---------------------------------------------------------------------------
# /journeys/{transaction_id}/integrity
# ---------------------------------------------------------------------------

def test_integrity_normal_success_is_clean(client):
    transaction_id = _transaction_id(client, "normal_success")
    body = client.get(f"/api/v1/journeys/{transaction_id}/integrity").json()
    assert body["total_events"] == 17
    assert body["linked_events"] == 17
    assert body["orphan_count"] == 0
    assert body["duplicate_count"] == 0
    assert body["unknown_count"] == 0
    assert body["contradictions"] == []
    assert body["missing_expected_event_candidates"] == []
    assert body["duration_seconds"] is not None


def test_integrity_missing_event_candidates(client):
    transaction_id = _transaction_id(client, "missing_event")
    body = client.get(f"/api/v1/journeys/{transaction_id}/integrity").json()
    candidates = [
        item["event_type"] for item in body["missing_expected_event_candidates"]
    ]
    assert "WEBHOOK_RECEIVED" in candidates
    # Structural observation only — never an outcome classification.
    assert body["contradictions"] == []


def test_integrity_duplicate_webhook(client):
    transaction_id = _transaction_id(client, "duplicate_webhook")
    body = client.get(f"/api/v1/journeys/{transaction_id}/integrity").json()
    rule_ids = {item["rule_id"] for item in body["duplicates"]}
    assert "DUPLICATE_IDEMPOTENCY_KEY" in rule_ids
    for item in body["duplicates"]:
        assert item["canonical_event_id"]
        assert item["idempotency_key"]


def test_integrity_contradictory_event(client):
    transaction_id = _transaction_id(client, "contradictory_event")
    body = client.get(f"/api/v1/journeys/{transaction_id}/integrity").json()
    types = {item["type"] for item in body["contradictions"]}
    assert "PAYMENT_STATE_CONTRADICTION" in types
    contradiction = body["contradictions"][0]
    assert contradiction["rule_id"]
    assert len(contradiction["involved_event_ids"]) >= 2
    assert len(contradiction["timestamps"]) >= 2
    assert contradiction["explanation"]


def test_integrity_compound_failure(client):
    transaction_id = _transaction_id(client, "compound_failure")
    body = client.get(f"/api/v1/journeys/{transaction_id}/integrity").json()
    candidates = {
        (item["event_type"], item["rule_id"])
        for item in body["missing_expected_event_candidates"]
    }
    assert ("ORDER_CONFIRMED", "MISSING_CONFIRMATION_AFTER_CAPTURE") in candidates
    assert ("FULFILLMENT_CREATED", "MISSING_FULFILLMENT_AFTER_RESERVATION") in candidates
    assert body["delayed_count"] >= 1
    assert client.get(
        f"/api/v1/journeys/{transaction_id}/integrity"
    ).json()["out_of_order_count"] == 0


def test_integrity_endpoint_unknown_id(client):
    assert client.get("/api/v1/journeys/nope/integrity").status_code == 404


def test_all_scenario_journeys_serve_200(client):
    slugs = [
        "normal_success", "payment_failed", "duplicate_webhook", "delayed_webhook",
        "inventory_failure", "delivery_failure", "refund_flow", "missing_event",
        "contradictory_event", "compound_failure",
    ]
    for slug in slugs:
        transaction_id = _transaction_id(client, slug)
        assert client.get(f"/api/v1/journeys/{transaction_id}").status_code == 200, slug
        assert client.get(
            f"/api/v1/journeys/{transaction_id}/graph"
        ).status_code == 200, slug
        assert client.get(
            f"/api/v1/journeys/{transaction_id}/integrity"
        ).status_code == 200, slug